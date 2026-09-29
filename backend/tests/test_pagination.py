import uuid
from datetime import UTC, datetime

from sqlalchemy import update

from app.modules.courses.models import Course
from app.modules.enrollment.models import Enrollment
from tests.helpers import API, create_course, make_published_course, make_student, make_teacher

SAME_TIME = datetime(2026, 9, 1, tzinfo=UTC)


async def _pages(client, url, headers, size):
    out = []
    for page in (1, 2, 3):
        r = await client.get(url, params={"page": page, "size": size}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["page"], body["size"]) == (page, size)
        out.append(body)
    return out


async def test_teacher_courses_are_paginated_newest_first(client):
    _, gv = await make_teacher(client)
    for n in range(1, 4):
        await create_course(client, gv, title=f"Khóa số {n}")
    p1, p2, p3 = await _pages(client, f"{API}/teacher/courses", gv, size=2)
    assert p1["total"] == p2["total"] == 3
    assert [c["title"] for c in p1["items"]] == ["Khóa số 3", "Khóa số 2"]
    assert [c["title"] for c in p2["items"]] == ["Khóa số 1"]
    assert p3["items"] == []


async def test_teacher_courses_tie_on_created_at_is_broken_by_id(client, db):
    _, gv = await make_teacher(client)
    ids = [(await create_course(client, gv, title=f"Khóa số {n}"))["id"] for n in range(4)]
    await db.execute(update(Course).values(created_at=SAME_TIME))
    await db.commit()
    p1, p2, _ = await _pages(client, f"{API}/teacher/courses", gv, size=2)
    got = [c["id"] for c in p1["items"] + p2["items"]]
    assert got == sorted(ids, key=uuid.UUID, reverse=True)


async def test_my_courses_are_paginated_with_stable_order(client, db):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course_ids = []
    for n in range(3):
        course, _, _ = await make_published_course(client, gv, title=f"Khóa học {n}")
        r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
        assert r.status_code == 201
        course_ids.append(course["id"])
    await db.execute(update(Enrollment).values(enrolled_at=SAME_TIME))
    await db.commit()
    p1, p2, p3 = await _pages(client, f"{API}/me/courses", sv, size=2)
    assert p1["total"] == p2["total"] == 3
    got = [c["course_id"] for c in p1["items"] + p2["items"]]
    assert got == sorted(course_ids, key=uuid.UUID, reverse=True)
    assert len(p1["items"]) == 2 and p3["items"] == []


async def test_catalog_tie_on_created_at_is_broken_by_id(client, db):
    _, gv = await make_teacher(client)
    ids = [(await make_published_course(client, gv, title=f"Khóa công khai {n}"))[0]["id"] for n in range(3)]
    await db.execute(update(Course).values(created_at=SAME_TIME))
    await db.commit()
    p1, p2, _ = await _pages(client, f"{API}/courses", None, size=2)
    assert [c["id"] for c in p1["items"] + p2["items"]] == sorted(ids, key=uuid.UUID, reverse=True)


async def test_list_endpoints_bound_page_and_size(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    for url, headers in ((f"{API}/teacher/courses", gv), (f"{API}/me/courses", sv)):
        for params in ({"page": 0}, {"page": 10001}, {"size": 0}, {"size": 101}):
            r = await client.get(url, params=params, headers=headers)
            assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR"), (url, params)
