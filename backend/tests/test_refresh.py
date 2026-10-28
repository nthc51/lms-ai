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


async def test_token_revoked_by_password_change_does_not_log_out_new_session(client):
    """Máy B còn giữ refresh token cũ sau khi người dùng đổi mật khẩu ở máy A: B bị từ chối, A vẫn đăng nhập."""
    await register_user(client, "r4@x.com")
    phone = await _login_raw(client, "r4@x.com")
    login = await client.post(f"{API}/auth/login", json={"email": "r4@x.com", "password": "password123"})
    client.cookies.clear()
    changed = await client.post(
        f"{API}/me/password",
        json={"current_password": "password123", "new_password": "newpass12345"},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert changed.status_code == 200, changed.text
    laptop_new = changed.cookies["refresh_token"]

    stale = await _refresh_with(client, phone)
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "INVALID_TOKEN"

    still = await _refresh_with(client, laptop_new)  # phiên vừa đổi mật khẩu vẫn còn
    assert still.status_code == 200
