"""Cache JSON trên Redis theo namespace có phiên bản (spec tầng S5).

Fail-open: Redis lỗi thì đọc thẳng DB (chậm hơn nhưng đúng). bump() lỗi thì dữ liệu cũ
còn tồn tại tối đa TTL giây, chấp nhận được với catalog.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

COURSES_NS = "courses"

Loader = Callable[[], Awaitable[tuple[Any, bool]]]  # trả (giá_trị_JSON_được, có_nên_cache)


class Cache(Protocol):
    async def get_or_load(self, ns: str, key: str, ttl_s: int, loader: Loader) -> Any: ...
    async def bump(self, ns: str) -> None: ...


class NullCache:
    async def get_or_load(self, ns: str, key: str, ttl_s: int, loader: Loader) -> Any:
        value, _ = await loader()
        return value

    async def bump(self, ns: str) -> None:
        return None


class RedisCache:
    def __init__(self, redis: Redis, prefix: str = "cache"):
        self._redis = redis
        self._prefix = prefix

    @classmethod
    def from_url(cls, url: str, prefix: str = "cache") -> "RedisCache":
        # Timeout ngắn: cache chậm thì bỏ qua, không được làm chậm request
        return cls(Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5), prefix)

    def _ver_key(self, ns: str) -> str:
        return f"{self._prefix}:ver:{ns}"

    async def get_or_load(self, ns: str, key: str, ttl_s: int, loader: Loader) -> Any:
        try:
            ver = int(await self._redis.get(self._ver_key(ns)) or 0)
            full_key = f"{self._prefix}:{ns}:v{ver}:{key}"
            raw = await self._redis.get(full_key)
        except RedisError:
            logger.warning("Cache: không đọc được Redis (%s/%s), đọc thẳng DB", ns, key)
            value, _ = await loader()
            return value
        if raw is not None:
            return json.loads(raw)
        value, cacheable = await loader()
        if cacheable:
            try:
                await self._redis.set(full_key, json.dumps(value, ensure_ascii=False), ex=ttl_s)
            except RedisError:
                logger.warning("Cache: không ghi được Redis (%s/%s)", ns, key)
        return value

    async def bump(self, ns: str) -> None:
        try:
            await self._redis.incr(self._ver_key(ns))
        except RedisError:
            logger.warning("Cache: không tăng được phiên bản %s, dữ liệu cũ tồn tại tối đa TTL", ns)

    async def aclose(self) -> None:
        await self._redis.aclose()


@lru_cache
def get_cache() -> Cache:
    s = get_settings()
    if not s.cache_enabled:
        return NullCache()
    return RedisCache.from_url(s.redis_url)
