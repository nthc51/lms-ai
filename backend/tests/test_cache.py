import uuid

from app.core.cache import NullCache, RedisCache
from app.core.config import get_settings


def _cache() -> RedisCache:
    return RedisCache.from_url(get_settings().redis_url, prefix=f"test-{uuid.uuid4().hex}")


def _counting_loader(calls: list, cacheable: bool = True):
    async def loader():
        calls.append(1)
        return {"n": len(calls)}, cacheable

    return loader


async def test_get_or_load_serves_second_call_from_cache():
    c, calls = _cache(), []
    try:
        assert await c.get_or_load("ns", "k", 60, _counting_loader(calls)) == {"n": 1}
        assert await c.get_or_load("ns", "k", 60, _counting_loader(calls)) == {"n": 1}
        assert len(calls) == 1
    finally:
        await c.aclose()


async def test_bump_invalidates_namespace_only():
    c, calls, other = _cache(), [], []
    try:
        await c.get_or_load("ns", "k", 60, _counting_loader(calls))
        await c.get_or_load("khac", "k", 60, _counting_loader(other))
        await c.bump("ns")
        await c.get_or_load("ns", "k", 60, _counting_loader(calls))
        await c.get_or_load("khac", "k", 60, _counting_loader(other))
        assert (len(calls), len(other)) == (2, 1)
    finally:
        await c.aclose()


async def test_not_cacheable_results_are_not_stored():
    c, calls = _cache(), []
    try:
        await c.get_or_load("ns", "k", 60, _counting_loader(calls, cacheable=False))
        await c.get_or_load("ns", "k", 60, _counting_loader(calls, cacheable=False))
        assert len(calls) == 2
    finally:
        await c.aclose()


async def test_load_racing_with_bump_does_not_poison_new_version():
    c = _cache()
    try:

        async def stale_loader():
            await c.bump("ns")  # giả lập: giảng viên sửa khóa đúng lúc đang đọc DB
            return {"v": "cu"}, True

        async def fresh_loader():
            return {"v": "moi"}, True

        assert await c.get_or_load("ns", "k", 60, stale_loader) == {"v": "cu"}
        assert await c.get_or_load("ns", "k", 60, fresh_loader) == {"v": "moi"}
    finally:
        await c.aclose()


async def test_redis_down_falls_back_to_loader():
    c, calls = RedisCache.from_url("redis://127.0.0.1:1/0"), []
    try:
        assert await c.get_or_load("ns", "k", 60, _counting_loader(calls)) == {"n": 1}
        await c.bump("ns")  # không ném lỗi
    finally:
        await c.aclose()


async def test_null_cache_always_loads():
    c, calls = NullCache(), []
    await c.get_or_load("ns", "k", 60, _counting_loader(calls))
    await c.get_or_load("ns", "k", 60, _counting_loader(calls))
    assert len(calls) == 2
