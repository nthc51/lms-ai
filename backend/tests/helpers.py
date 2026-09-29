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


async def create_course(client, headers, title="Cấu trúc dữ liệu và Giải thuật", description="Mô tả") -> dict:
    r = await client.post(f"{API}/courses", json={"title": title, "description": description}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def add_section(client, headers, course_id, title="Chương 1") -> dict:
    r = await client.post(f"{API}/courses/{course_id}/sections", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def add_lesson(client, headers, section_id, title="Bài 1", content_md="# Nội dung") -> dict:
    r = await client.post(f"{API}/sections/{section_id}/lessons",
                          json={"title": title, "content_md": content_md}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def make_published_course(client, teacher_headers, title="Cấu trúc dữ liệu") -> tuple[dict, dict, dict]:
    course = await create_course(client, teacher_headers, title=title)
    section = await add_section(client, teacher_headers, course["id"])
    lesson = await add_lesson(client, teacher_headers, section["id"])
    r = await client.post(f"{API}/courses/{course['id']}/publish", headers=teacher_headers)
    assert r.status_code == 200, r.text
    return r.json(), section, lesson


async def upload_file(client, storage, headers, data: bytes, kind="pdf", mime="application/pdf") -> str:
    """Presign → 'upload' vào key tạm của storage giả → complete. Trả về asset_id."""
    r = await client.post(f"{API}/uploads/presign", json={"kind": kind, "mime": mime, "size": len(data)},
                          headers=headers)
    assert r.status_code == 200, r.text
    storage.client_put(r.json()["put_url"], data, mime)  # vào key tạm; complete sẽ copy sang key chính thức
    done = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=headers)
    assert done.status_code == 200, done.text
    return r.json()["asset_id"]
