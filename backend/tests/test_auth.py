from tests.helpers import API, login, register_user


async def test_register_student(client):
    body = await register_user(client, "a@x.com")
    assert body["role"] == "student"
    assert body["teacher_status"] is None
    assert "password_hash" not in body


async def test_register_teacher_is_pending(client):
    body = await register_user(client, "gv@x.com", role="teacher")
    assert body["teacher_status"] == "pending"


async def test_register_cannot_create_admin(client):
    r = await client.post(
        f"{API}/auth/register",
        json={"email": "ad@x.com", "password": "password123", "role": "admin", "full_name": "A"},
    )
    assert r.status_code == 422


async def test_register_duplicate_email_is_case_insensitive(client):
    await register_user(client, "A@x.com")
    r = await client.post(
        f"{API}/auth/register", json={"email": "a@x.com", "password": "password123", "full_name": "B"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_db_rejects_uppercase_email_even_outside_the_api(db):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.modules.auth.models import Role, User

    db.add(User(email="Admin@lms.local", password_hash="x", full_name="A", role=Role.admin))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_register_short_password_is_422(client):
    r = await client.post(
        f"{API}/auth/register", json={"email": "b@x.com", "password": "123", "full_name": "B"}
    )
    assert r.status_code == 422


async def test_login_returns_access_token_and_sets_refresh_cookie(client):
    await register_user(client, "c@x.com")
    r = await client.post(f"{API}/auth/login", json={"email": "c@x.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    set_cookie = r.headers["set-cookie"]
    assert "refresh_token=" in set_cookie and "HttpOnly" in set_cookie and "Path=/api/v1/auth" in set_cookie


async def test_login_wrong_password(client):
    await register_user(client, "d@x.com")
    r = await client.post(f"{API}/auth/login", json={"email": "d@x.com", "password": "wrongpass1"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_requires_token(client):
    r = await client.get(f"{API}/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_me_returns_current_user(client):
    await register_user(client, "e@x.com", full_name="Chiến")
    headers = await login(client, "e@x.com")
    r = await client.get(f"{API}/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "e@x.com" and r.json()["full_name"] == "Chiến"


async def test_concurrent_duplicate_registration_gives_one_201_one_409(client):
    import asyncio

    body = {"email": "race@x.com", "password": "password123", "full_name": "R"}
    r1, r2 = await asyncio.gather(
        client.post(f"{API}/auth/register", json=body), client.post(f"{API}/auth/register", json=body)
    )
    assert sorted([r1.status_code, r2.status_code]) == [201, 409]
    loser = r1 if r1.status_code == 409 else r2
    assert loser.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_register_integrity_error_on_commit_maps_to_email_taken(client, monkeypatch):
    """Ép đúng nhánh race: bỏ qua bước kiểm tra trước, để unique constraint bắt lúc commit."""
    from app.modules.auth import service

    await register_user(client, "race2@x.com")
    real_scalar = service.AsyncSession.scalar
    calls = {"n": 0}

    async def first_check_misses(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return await real_scalar(self, *args, **kwargs)

    monkeypatch.setattr(service.AsyncSession, "scalar", first_check_misses)
    r = await client.post(
        f"{API}/auth/register", json={"email": "race2@x.com", "password": "password123", "full_name": "B"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_TAKEN"
