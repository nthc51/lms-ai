import asyncio
import uuid

from app.core.config import get_settings
from app.core.ratelimit import RedisRateLimiter, rate_limited


async def test_redis_limiter_blocks_after_limit_and_reports_ttl():
    limiter = RedisRateLimiter.from_url(get_settings().redis_url)
    key = f"test:{uuid.uuid4().hex}"
    try:
        assert [await limiter.hit(key, 3, 60) for _ in range(3)] == [None, None, None]
        retry = await limiter.hit(key, 3, 60)
        assert retry is not None and 1 <= retry <= 60
        assert await limiter.hit(f"{key}:khac", 3, 60) is None  # key khác đếm riêng
    finally:
        await limiter._redis.delete(limiter.PREFIX + key, limiter.PREFIX + key + ":khac")
        await limiter.aclose()


async def test_redis_down_fails_open():
    limiter = RedisRateLimiter.from_url("redis://127.0.0.1:1/0")
    try:
        assert await limiter.hit("x", 1, 60) is None
        assert await limiter.hit("x", 1, 60) is None
    finally:
        await limiter.aclose()


async def test_redis_hang_fails_open_fast():
    async def silent(reader, writer):  # nhận kết nối nhưng không bao giờ trả lời
        await asyncio.sleep(30)

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    limiter = RedisRateLimiter.from_url(f"redis://127.0.0.1:{port}/0")
    try:
        async with asyncio.timeout(5):
            assert await limiter.hit("x", 1, 60) is None
    finally:
        await limiter.aclose()
        server.close()


def test_rate_limited_error_has_retry_after_header():
    err = rate_limited(42)
    assert (err.code, err.status) == ("RATE_LIMITED", 429)
    assert err.headers == {"Retry-After": "42"} and err.details == {"retry_after": 42}
