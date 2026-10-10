import httpx

from app.core.health import get_redis_ping
from app.core.storage import get_storage
from app.main import create_app
from tests.fakes import InMemoryStorage


def _client(storage, redis_ok=True):
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage

    async def redis_ping():
        if not redis_ok:
            raise ConnectionError("redis giả bị tắt")

    app.dependency_overrides[get_redis_ping] = lambda: redis_ping
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_ready_when_all_dependencies_up():
    async with _client(InMemoryStorage()) as c:
        r = await c.get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {"db": "ok", "redis": "ok", "storage": "ok"}}


async def test_not_ready_reports_failing_dependency():
    storage = InMemoryStorage()
    storage.fail_ping = True
    async with _client(storage, redis_ok=False) as c:
        r = await c.get("/api/v1/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"].startswith("error")
    assert body["checks"]["storage"].startswith("error")


async def test_ready_uses_real_redis_by_default(client):
    r = await client.get("/api/v1/ready")  # fixture client: storage giả, Redis thật của compose/CI
    assert r.json()["checks"]["redis"] == "ok"
