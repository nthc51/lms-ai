"""Hồ sơ cá nhân: sửa họ tên, đổi mật khẩu khi đang đăng nhập."""

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.auth.models import RefreshToken
from tests.helpers import API, login, register_user

NEW_PASSWORD = "mat-khau-moi-123"


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def _active_sessions(user_id: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )


async def test_update_full_name_trims_spaces(client):
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    h = await login(client, "an@x.com")

    r = await client.patch(f"{API}/me", json={"full_name": "  Nguyễn   Văn  Bình "}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Nguyễn Văn Bình"
    assert (await client.get(f"{API}/me", headers=h)).json()["full_name"] == "Nguyễn Văn Bình"


async def test_update_full_name_rejects_blank_and_too_long(client):
    await register_user(client, "an@x.com")
    h = await login(client, "an@x.com")
    assert (await client.patch(f"{API}/me", json={"full_name": "   "}, headers=h)).status_code == 422
    assert (await client.patch(f"{API}/me", json={"full_name": "a" * 121}, headers=h)).status_code == 422


async def test_profile_endpoints_need_login(client):
    assert (await client.patch(f"{API}/me", json={"full_name": "X"})).status_code == 401
    r = await client.post(f"{API}/me/password", json={"current_password": "x", "new_password": NEW_PASSWORD})
    assert r.status_code == 401


async def test_change_password_keeps_this_browser_and_revokes_others(client):
    user = await register_user(client, "an@x.com")
    await login(client, "an@x.com")  # phiên trên "máy khác"
    h = await login(client, "an@x.com")  # phiên đang dùng; client giữ cookie refresh của phiên này
    assert await _active_sessions(user["id"]) == 2

    r = await client.post(
        f"{API}/me/password",
        json={"current_password": "password123", "new_password": NEW_PASSWORD},
        headers=h,
    )
    assert r.status_code == 200, r.text
    new_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get(f"{API}/me", headers=new_h)).status_code == 200
    assert "refresh_token=" in r.headers["set-cookie"]
    assert await _active_sessions(user["id"]) == 1  # chỉ còn phiên vừa cấp

    # cookie mới dùng được để refresh
    assert (await client.post(f"{API}/auth/refresh")).status_code == 200
    old = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": "password123"})
    assert _code(old) == (401, "INVALID_CREDENTIALS")
    assert (
        await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": NEW_PASSWORD})
    ).status_code == 200


async def test_change_password_wrong_current_or_same_or_short(client):
    user = await register_user(client, "an@x.com")
    h = await login(client, "an@x.com")

    wrong = await client.post(
        f"{API}/me/password",
        json={"current_password": "sai-mat-khau", "new_password": NEW_PASSWORD},
        headers=h,
    )
    assert _code(wrong) == (400, "WRONG_PASSWORD")
    same = await client.post(
        f"{API}/me/password",
        json={"current_password": "password123", "new_password": "password123"},
        headers=h,
    )
    assert _code(same) == (400, "SAME_PASSWORD")
    short = await client.post(
        f"{API}/me/password", json={"current_password": "password123", "new_password": "ngan"}, headers=h
    )
    assert short.status_code == 422
    assert await _active_sessions(user["id"]) == 1  # không lần nào ở trên thu hồi phiên


async def test_change_password_is_rate_limited_per_account(client):
    await register_user(client, "an@x.com")
    h = await login(client, "an@x.com")
    body = {"current_password": "sai-mat-khau", "new_password": NEW_PASSWORD}
    for _ in range(10):
        assert (await client.post(f"{API}/me/password", json=body, headers=h)).status_code == 400
    r = await client.post(f"{API}/me/password", json=body, headers=h)
    assert _code(r) == (429, "RATE_LIMITED")
    assert r.headers["retry-after"] == "3600"
