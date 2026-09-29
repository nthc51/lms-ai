"""Tài khoản bị khóa và refresh token hết hạn."""

import uuid
from datetime import timedelta

from sqlalchemy import update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import RefreshToken, User
from tests.helpers import API, login, register_user


async def _lock(user_id: str) -> None:
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == uuid.UUID(user_id)).values(locked_at=utcnow()))
        await db.commit()


async def _login_raw(client, email):
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.cookies["refresh_token"]


async def _refresh_with(client, raw):
    client.cookies.clear()
    return await client.post(f"{API}/auth/refresh", headers={"Cookie": f"refresh_token={raw}"})


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def test_login_of_locked_user_is_403_account_locked(client):
    user = await register_user(client, "lock1@x.com")
    await _lock(user["id"])
    r = await client.post(f"{API}/auth/login", json={"email": "lock1@x.com", "password": "password123"})
    assert _code(r) == (403, "ACCOUNT_LOCKED")


async def test_access_token_of_user_locked_afterwards_is_rejected(client):
    user = await register_user(client, "lock2@x.com")
    headers = await login(client, "lock2@x.com")
    assert (await client.get(f"{API}/me", headers=headers)).status_code == 200
    await _lock(user["id"])
    r = await client.get(f"{API}/me", headers=headers)
    assert _code(r) == (403, "ACCOUNT_LOCKED")


async def test_refresh_for_locked_user_is_403_account_locked(client):
    user = await register_user(client, "lock3@x.com")
    raw = await _login_raw(client, "lock3@x.com")
    await _lock(user["id"])
    r = await _refresh_with(client, raw)
    assert _code(r) == (403, "ACCOUNT_LOCKED")
    assert "refresh_token" not in r.cookies


async def test_refresh_with_expired_token_is_401_token_expired(client):
    user = await register_user(client, "exp@x.com")
    raw = await _login_raw(client, "exp@x.com")
    async with SessionLocal() as db:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == uuid.UUID(user["id"]))
            .values(expires_at=utcnow() - timedelta(seconds=1))
        )
        await db.commit()
    r = await _refresh_with(client, raw)
    assert _code(r) == (401, "TOKEN_EXPIRED")
