from tests.helpers import API, create_course, make_published_course, make_student, make_teacher


async def test_student_enrolls_published_course(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    assert r.status_code == 201
    assert r.json()["course_id"] == course["id"]


async def test_enroll_twice_is_conflict(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ALREADY_ENROLLED")


async def test_cannot_enroll_draft_course(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    draft = await create_course(client, gv)
    r = await client.post(f"{API}/courses/{draft['id']}/enroll", headers=sv)
    assert r.status_code == 404


async def test_teacher_cannot_enroll(client):
    _, gv = await make_teacher(client)
    course, _, _ = await make_published_course(client, gv)
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_my_courses_shows_progress(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    r = await client.get(f"{API}/me/courses", headers=sv)
    assert r.status_code == 200
    [item] = r.json()["items"]
    assert item["course_id"] == course["id"]
    assert (item["total_lessons"], item["done_lessons"], item["progress_pct"]) == (1, 0, 0)


async def test_course_detail_lists_done_lessons_for_enrolled_viewer(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    slug = course["slug"]
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    assert (await client.get(f"{API}/courses/{slug}", headers=sv)).json()["done_lesson_ids"] == []

    r = await client.put(
        f"{API}/lessons/{lesson['id']}/progress", json={"status": "done", "video_position_sec": 0}, headers=sv
    )
    assert r.status_code == 200, r.text
    assert (await client.get(f"{API}/courses/{slug}", headers=sv)).json()["done_lesson_ids"] == [lesson["id"]]
    # người khác (chủ khóa, khách) không thấy tiến độ của học viên
    assert (await client.get(f"{API}/courses/{slug}", headers=gv)).json()["done_lesson_ids"] == []
    assert (await client.get(f"{API}/courses/{slug}")).json()["done_lesson_ids"] == []


async def test_huge_video_position_is_rejected_not_500(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    r = await client.put(
        f"{API}/lessons/{lesson['id']}/progress",
        json={"status": "in_progress", "video_position_sec": 3_000_000_000},
        headers=sv,
    )
    assert r.status_code == 422
