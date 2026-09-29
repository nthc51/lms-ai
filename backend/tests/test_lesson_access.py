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
    assert r.status_code == 201


async def test_enrolled_student_reads_lesson(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    await _enroll(client, sv, course["id"])
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)
    assert r.status_code == 200
    assert r.json()["content_md"] == "# Nội dung"
    assert r.json()["progress"] is None


async def test_not_enrolled_student_gets_403(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")


async def test_draft_lesson_is_404_for_student(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    lesson = await add_lesson(client, gv, s["id"])
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)
    assert r.status_code == 404


async def test_owner_previews_without_enrolling_other_teacher_cannot(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, _, lesson = await make_published_course(client, gv1)
    assert (await client.get(f"{API}/lessons/{lesson['id']}", headers=gv1)).status_code == 200
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=gv2)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")


async def test_progress_done_completes_course_and_never_downgrades(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    await _enroll(client, sv, course["id"])

    r = await client.put(f"{API}/lessons/{lesson['id']}/progress",
                         json={"status": "done", "video_position_sec": 120}, headers=sv)
    assert r.status_code == 200 and r.json()["status"] == "done"

    [mine] = (await client.get(f"{API}/me/courses", headers=sv)).json()
    assert mine["progress_pct"] == 100 and mine["completed_at"] is not None

    r = await client.put(f"{API}/lessons/{lesson['id']}/progress",
                         json={"status": "in_progress", "video_position_sec": 30}, headers=sv)
    assert r.json()["status"] == "done" and r.json()["video_position_sec"] == 30


async def test_teacher_cannot_save_progress(client):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await client.put(f"{API}/lessons/{lesson['id']}/progress",
                         json={"status": "done", "video_position_sec": 0}, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
