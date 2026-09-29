import uuid

from app.core.db import SessionLocal
from app.modules.auth.models import TeacherStatus, User

API = "/api/v1"


async def register_user(client, email, password="password123", role="student", full_name="Người dùng"):
    r = await client.post(f"{API}/auth/register",
                          json={"email": email, "password": password, "role": role, "full_name": full_name})
    assert r.status_code == 201, r.text
    return r.json()


async def login(client, email, password="password123") -> dict[str, str]:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def approve_teacher_in_db(user_id: str) -> None:
    async with SessionLocal() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.teacher_status = TeacherStatus.approved
        await db.commit()


async def make_student(client, email="sv@x.com") -> tuple[str, dict]:
    user = await register_user(client, email, role="student")
    return user["id"], await login(client, email)


async def make_teacher(client, email="gv@x.com", approved=True) -> tuple[str, dict]:
    user = await register_user(client, email, role="teacher", full_name="Giảng viên")
    if approved:
        await approve_teacher_in_db(user["id"])
    return user["id"], await login(client, email)


async def make_admin(client, email="admin@x.com") -> tuple[str, dict]:
    from app.modules.auth.service import create_admin

    async with SessionLocal() as db:
        user = await create_admin(db, email, "password123")
    return str(user.id), await login(client, email)
