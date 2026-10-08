from app.core.config import get_settings
from tests.helpers import API, register_user


async def test_login_is_rate_limited_per_ip(client, limiter):
    await register_user(client, "rl@x.com")
    body = {"email": "rl@x.com", "password": "password123"}
    for _ in range(get_settings().login_rate_limit_per_min):
        assert (await client.post(f"{API}/auth/login", json=body)).status_code == 200
    r = await client.post(f"{API}/auth/login", json=body)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["retry-after"]) > 0
    assert any(k.startswith("login-ip:") for k in limiter.counts)


async def test_wrong_password_attempts_also_count(client):
    await register_user(client, "rl2@x.com")
    bad = {"email": "rl2@x.com", "password": "saimatkhau1"}
    for _ in range(get_settings().login_rate_limit_per_min):
        assert (await client.post(f"{API}/auth/login", json=bad)).status_code == 401
    r = await client.post(f"{API}/auth/login", json=bad)
    assert r.status_code == 429
