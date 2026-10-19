"""Báo cho các tab đang mở biết người dùng có thông báo mới (B6).

Thông báo nằm trong bảng `notifications`; hub chỉ phát một tín hiệu "có thay đổi" theo người dùng qua Redis
pub/sub, luồng SSE của người đó nhận được thì đọc lại số chưa đọc từ DB. Mất tín hiệu (Redis lỗi, tab đang mất
mạng) không mất thông báo: lần kết nối lại sau sẽ đọc lại từ DB."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import lru_cache
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CHANNEL = "notif:{}"


class Subscription(Protocol):
    async def wait(self, timeout: float) -> bool:
        """Chờ tín hiệu tối đa `timeout` giây. True = có tín hiệu, False = hết giờ."""
        ...


class NotificationHub(Protocol):
    async def publish(self, user_ids: list[str]) -> None: ...

    def subscribe(self, user_id: str) -> AbstractAsyncContextManager[Subscription]: ...


class _RedisSubscription:
    def __init__(self, pubsub) -> None:
        self._pubsub = pubsub

    async def wait(self, timeout: float) -> bool:
        msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        return msg is not None


class RedisHub:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> "RedisHub":
        return cls(Redis.from_url(url, socket_connect_timeout=1.0))

    async def publish(self, user_ids: list[str]) -> None:
        """Phát tín hiệu cho từng người. Redis lỗi thì chỉ ghi log: thông báo đã nằm trong DB."""
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for uid in dict.fromkeys(user_ids):
                    pipe.publish(CHANNEL.format(uid), "1")
                await pipe.execute()
        except RedisError:
            logger.warning("Không phát được tín hiệu thông báo qua Redis", exc_info=True)

    @asynccontextmanager
    async def subscribe(self, user_id: str) -> AsyncIterator[_RedisSubscription]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL.format(user_id))
        try:
            yield _RedisSubscription(pubsub)
        finally:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except (RedisError, asyncio.CancelledError):
                pass


@lru_cache
def get_hub() -> RedisHub:
    """Dependency FastAPI và worker dùng chung. Test override bằng InMemoryHub (tests/fakes.py)."""
    return RedisHub.from_url(get_settings().redis_url)
