import httpx
import pytest

from app.core.config import Settings
from app.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_preflight_from_allowed_origin_gets_cors_headers():
    async with _client(create_app()) as c:
        r = await c.options(
            "/api/v1/auth/refresh",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert r.headers["access-control-allow-credentials"] == "true"


async def test_simple_request_exposes_request_id():
    async with _client(create_app()) as c:
        r = await c.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-request-id" in r.headers["access-control-expose-headers"].lower()
    # 429 RATE_LIMITED: frontend cần đọc Retry-After
    assert "retry-after" in r.headers["access-control-expose-headers"].lower()


async def test_unknown_origin_gets_no_cors_headers():
    async with _client(create_app()) as c:
        pre = await c.options(
            "/api/v1/auth/refresh",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
        )
        simple = await c.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    for r in (pre, simple):
        assert "access-control-allow-origin" not in r.headers
        assert "access-control-allow-credentials" not in r.headers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://a.test", ["http://a.test"]),
        ("http://a.test, http://b.test", ["http://a.test", "http://b.test"]),
        ('["http://a.test", "http://b.test"]', ["http://a.test", "http://b.test"]),
    ],
)
def test_cors_origins_env_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings(_env_file=None).cors_origins == expected


def test_cors_origins_default(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == ["http://localhost:3000"]
