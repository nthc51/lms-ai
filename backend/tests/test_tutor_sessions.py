import uuid

from app.modules.materials.models import SourceStatus
from tests.factories import BINARY_SEARCH, seed_chunks
from tests.helpers import (
    API,
    add_lesson,
    add_section,
    create_course,
    make_published_course,
    make_student,
    make_teacher,
)


async def _enroll(client, headers, course_id):
    r = await client.post(f"{API}/courses/{course_id}/enroll", headers=headers)
    assert r.status_code == 201, r.text


async def _enrolled(client, gv, email="sv@x.com"):
    course, section, lesson = await make_published_course(client, gv)
    _, sv = await make_student(client, email)
    await _enroll(client, sv, course["id"])
    return course, section, lesson, sv


async def test_enrolled_student_creates_course_and_lesson_sessions(client):
    _, gv = await make_teacher(client)
    course, _, lesson, sv = await _enrolled(client, gv)
    r = await client.post(f"{API}/tutor/sessions", json={"course_id": course["id"]}, headers=sv)
    assert r.status_code == 201 and r.json()["lesson_id"] is None
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    r = await client.post(f"{API}/tutor/sessions", json=body, headers=sv)
    assert r.status_code == 201 and r.json()["lesson_id"] == lesson["id"]
    page = (await client.get(f"{API}/tutor/sessions", params={"course_id": course["id"]}, headers=sv)).json()
    assert page["total"] == 2 and page["items"][0]["lesson_id"] == lesson["id"]  # mới nhất trước


async def test_not_enrolled_is_403_and_draft_course_is_404(client):
    _, gv = await make_teacher(client)
    course, _, _ = await make_published_course(client, gv)
    _, sv = await make_student(client)
    r = await client.post(f"{API}/tutor/sessions", json={"course_id": course["id"]}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")
    draft = await create_course(client, gv, title="Khóa nháp")
    r = await client.post(f"{API}/tutor/sessions", json={"course_id": draft["id"]}, headers=sv)
    assert r.status_code == 404


async def test_lesson_must_belong_to_the_course(client):
    _, gv = await make_teacher(client)
    course, _, _, sv = await _enrolled(client, gv)
    other, _, other_lesson = await make_published_course(client, gv, title="Khóa khác")
    await _enroll(client, sv, other["id"])
    body = {"course_id": course["id"], "lesson_id": other_lesson["id"]}
    r = await client.post(f"{API}/tutor/sessions", json=body, headers=sv)
    assert r.status_code == 404


async def test_owner_teacher_can_use_tutor_on_a_draft_lesson(client):
    _, gv = await make_teacher(client)
    draft = await create_course(client, gv)
    section = await add_section(client, gv, draft["id"])
    lesson = await add_lesson(client, gv, section["id"])
    body = {"course_id": draft["id"], "lesson_id": lesson["id"]}
    assert (await client.post(f"{API}/tutor/sessions", json=body, headers=gv)).status_code == 201


async def test_messages_of_other_users_session_are_404(client):
    _, gv = await make_teacher(client)
    course, _, _, sv1 = await _enrolled(client, gv, "sv1@x.com")
    _, sv2 = await make_student(client, "sv2@x.com")
    s = (await client.post(f"{API}/tutor/sessions", json={"course_id": course["id"]}, headers=sv1)).json()
    r = await client.get(f"{API}/tutor/sessions/{s['id']}/messages", headers=sv1)
    assert r.json() == {"items": [], "total": 0, "page": 1, "size": 20}
    assert (await client.get(f"{API}/tutor/sessions/{s['id']}/messages", headers=sv2)).status_code == 404
    assert (await client.get(f"{API}/tutor/sessions/{uuid.uuid4()}/messages", headers=sv1)).status_code == 404


async def test_availability_signals_when_no_ready_chunks(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson, sv = await _enrolled(client, gv)
    params = {"course_id": course["id"], "lesson_id": lesson["id"]}
    r = await client.get(f"{API}/tutor/availability", params=params, headers=sv)
    assert r.json() == {"available": False, "ready_chunks": 0, "message": "Tài liệu đang được xử lý"}
    await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH], status=SourceStatus.processing)
    assert (await client.get(f"{API}/tutor/availability", params=params, headers=sv)).json()[
        "available"
    ] is False
    await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH])
    r = await client.get(f"{API}/tutor/availability", params={"course_id": course["id"]}, headers=sv)
    assert r.json() == {"available": True, "ready_chunks": 1, "message": None}


async def test_messages_order_is_deterministic_for_same_timestamp(client, db):
    from sqlalchemy import func

    from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession

    _, gv = await make_teacher(client)
    course, _, _, sv = await _enrolled(client, gv)
    s = (await client.post(f"{API}/tutor/sessions", json={"course_id": course["id"]}, headers=sv)).json()
    sid = uuid.UUID(s["id"])
    now = await db.scalar(func.now())
    assert await db.get(ChatSession, sid)
    # assistant có id nhỏ hơn và được thêm trước, vẫn phải đứng sau user
    db.add(
        ChatMessage(session_id=sid, role=ChatRole.assistant, content="a", created_at=now, id=uuid.UUID(int=1))
    )
    db.add(
        ChatMessage(session_id=sid, role=ChatRole.user, content="u", created_at=now, id=uuid.UUID(int=2**100))
    )
    await db.commit()
    r = await client.get(f"{API}/tutor/sessions/{s['id']}/messages", headers=sv)
    assert [m["role"] for m in r.json()["items"]] == ["user", "assistant"]
