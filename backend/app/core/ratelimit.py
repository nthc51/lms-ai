"""Rate limit bằng Redis (spec 5.3 bước 7): cửa sổ cố định tính từ lần đếm đầu tiên, INCR + EXPIRE NX."""

import logging
from functools import lru_cache
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: int) -> int | None:
        """Đếm thêm một lần. Vượt `limit` trong cửa sổ `window_s` giây thì trả số giây phải chờ, không thì None."""
        ...


class RedisRateLimiter:
    PREFIX = "rl:"

    def __init__(self, redis: Redis):
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> "RedisRateLimiter":
        return cls(Redis.from_url(url))

    async def hit(self, key: str, limit: int, window_s: int) -> int | None:
        full = self.PREFIX + key
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(full)
                pipe.expire(full, window_s, nx=True)  # cửa sổ bắt đầu từ lần đếm đầu tiên
                pipe.ttl(full)
                count, _, ttl = await pipe.execute()
        except RedisError:
            # Redis lỗi: cho qua (không chặn học viên vì lỗi hạ tầng), ghi log để biết
            logger.exception("Rate limiter không truy cập được Redis, bỏ qua giới hạn cho %s", key)
            return None
        if count > limit:
            return max(int(ttl), 1)
        return None

    async def aclose(self) -> None:
        await self._redis.aclose()


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """Dependency FastAPI. Test override bằng InMemoryRateLimiter (tests/conftest.py)."""
    return RedisRateLimiter.from_url(get_settings().redis_url)


def rate_limited(retry_after: int) -> AppError:
    return AppError(
        "RATE_LIMITED",
        "Bạn đã hỏi quá nhiều, vui lòng thử lại sau",
        429,
        {"retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )
