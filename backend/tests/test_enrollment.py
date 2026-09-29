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
    [item] = r.json()
    assert item["course_id"] == course["id"]
    assert (item["total_lessons"], item["done_lessons"], item["progress_pct"]) == (1, 0, 0)
