from tests.helpers import API, register_user


async def _login_raw(client, email):
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200
    return r.cookies["refresh_token"]


async def _refresh_with(client, raw):
    client.cookies.clear()  # chỉ gửi đúng cookie mình chỉ định
    return await client.post(f"{API}/auth/refresh", headers={"Cookie": f"refresh_token={raw}"})


async def test_refresh_rotates_token(client):
    await register_user(client, "r1@x.com")
    old = await _login_raw(client, "r1@x.com")
    r = await _refresh_with(client, old)
    assert r.status_code == 200
    assert r.json()["access_token"]
    new = r.cookies["refresh_token"]
    assert new and new != old


async def test_reusing_rotated_token_revokes_whole_family(client):
    await register_user(client, "r2@x.com")
    old = await _login_raw(client, "r2@x.com")
    new = (await _refresh_with(client, old)).cookies["refresh_token"]

    reuse = await _refresh_with(client, old)
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "TOKEN_REUSED"

    after = await _refresh_with(client, new)  # token mới cũng đã bị thu hồi
    assert after.status_code == 401


async def test_refresh_without_cookie(client):
    client.cookies.clear()
    r = await client.post(f"{API}/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


async def test_logout_revokes_refresh_token(client):
    await register_user(client, "r3@x.com")
    raw = await _login_raw(client, "r3@x.com")
    client.cookies.clear()
    out = await client.post(f"{API}/auth/logout", headers={"Cookie": f"refresh_token={raw}"})
    assert out.status_code == 204
    assert "refresh_token=" in out.headers["set-cookie"]  # cookie bị xóa
    r = await _refresh_with(client, raw)
    assert r.status_code == 401
