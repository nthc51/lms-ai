import uuid

from sqlalchemy import func, select

from app.modules.courses.models import Lesson, Section
from tests.helpers import API, add_lesson, add_section, create_course, make_teacher


async def test_positions_are_sequential(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s1 = await add_section(client, gv, c["id"], "Chương 1")
    s2 = await add_section(client, gv, c["id"], "Chương 2")
    l1 = await add_lesson(client, gv, s1["id"], "Bài 1")
    l2 = await add_lesson(client, gv, s1["id"], "Bài 2")
    assert (s1["position"], s2["position"]) == (1, 2)
    assert (l1["position"], l2["position"]) == (1, 2)


async def test_other_teacher_cannot_add_or_edit_content(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    c = await create_course(client, gv1)
    s = await add_section(client, gv1, c["id"])
    lesson = await add_lesson(client, gv1, s["id"])
    r1 = await client.post(f"{API}/sections/{s['id']}/lessons", json={"title": "Chen"}, headers=gv2)
    r2 = await client.patch(f"{API}/lessons/{lesson['id']}", json={"title": "Sửa"}, headers=gv2)
    r3 = await client.post(f"{API}/courses/{c['id']}/sections", json={"title": "X"}, headers=gv2)
    assert (r1.status_code, r2.status_code, r3.status_code) == (404, 404, 404)


async def test_update_lesson(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    lesson = await add_lesson(client, gv, s["id"])
    r = await client.patch(
        f"{API}/lessons/{lesson['id']}",
        json={"content_md": "## Tìm kiếm nhị phân", "duration_sec": 600},
        headers=gv,
    )
    assert r.status_code == 200
    assert r.json()["content_md"] == "## Tìm kiếm nhị phân" and r.json()["duration_sec"] == 600


async def test_reorder_moves_lesson_between_sections(client, db):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s1 = await add_section(client, gv, c["id"], "Chương 1")
    s2 = await add_section(client, gv, c["id"], "Chương 2")
    a = await add_lesson(client, gv, s1["id"], "A")
    b = await add_lesson(client, gv, s1["id"], "B")
    body = {
        "sections": [{"id": s2["id"], "lesson_ids": [b["id"]]}, {"id": s1["id"], "lesson_ids": [a["id"]]}]
    }
    r = await client.patch(f"{API}/courses/{c['id']}/reorder", json=body, headers=gv)
    assert r.status_code == 204
    sec2 = await db.get(Section, uuid.UUID(s2["id"]))
    lesson_b = await db.get(Lesson, uuid.UUID(b["id"]))
    assert sec2.position == 1
    assert str(lesson_b.section_id) == s2["id"] and lesson_b.position == 1


async def test_reorder_rejects_incomplete_list(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s1 = await add_section(client, gv, c["id"])
    await add_lesson(client, gv, s1["id"], "A")
    body = {"sections": [{"id": s1["id"], "lesson_ids": []}]}
    r = await client.patch(f"{API}/courses/{c['id']}/reorder", json=body, headers=gv)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REORDER"


async def test_delete_section_cascades_lessons(client, db):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    await add_lesson(client, gv, s["id"])
    assert (await client.delete(f"{API}/sections/{s['id']}", headers=gv)).status_code == 204
    assert await db.scalar(select(func.count(Lesson.id))) == 0


async def test_publish_after_adding_lesson(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    await add_lesson(client, gv, s["id"])
    r = await client.post(f"{API}/courses/{c['id']}/publish", headers=gv)
    assert r.status_code == 200 and r.json()["status"] == "published"
