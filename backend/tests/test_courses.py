from tests.helpers import API, create_course, make_admin, make_student, make_teacher


async def test_approved_teacher_creates_draft_course(client):
    uid, gv = await make_teacher(client)
    c = await create_course(client, gv)
    assert c["status"] == "draft"
    assert c["teacher_id"] == uid
    assert c["slug"].startswith("cau-truc-du-lieu-va-giai-thuat-")


async def test_pending_teacher_and_student_cannot_create(client):
    _, pending = await make_teacher(client, "p@x.com", approved=False)
    _, sv = await make_student(client)
    r1 = await client.post(f"{API}/courses", json={"title": "Khóa A"}, headers=pending)
    r2 = await client.post(f"{API}/courses", json={"title": "Khóa A"}, headers=sv)
    assert (r1.status_code, r1.json()["error"]["code"]) == (403, "TEACHER_NOT_APPROVED")
    assert (r2.status_code, r2.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_teacher_lists_only_own_courses(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    await create_course(client, gv1, title="Khóa của GV1")
    await create_course(client, gv2, title="Khóa của GV2")
    r = await client.get(f"{API}/teacher/courses", headers=gv1)
    assert [c["title"] for c in r.json()["items"]] == ["Khóa của GV1"]
    assert (r.json()["total"], r.json()["page"], r.json()["size"]) == (1, 1, 20)


async def test_other_teacher_gets_404_but_admin_can_edit(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, ad = await make_admin(client)
    c = await create_course(client, gv1)
    r = await client.patch(f"{API}/courses/{c['id']}", json={"title": "Bị sửa trộm"}, headers=gv2)
    assert r.status_code == 404
    r = await client.patch(f"{API}/courses/{c['id']}", json={"title": "Admin sửa"}, headers=ad)
    assert r.status_code == 200 and r.json()["title"] == "Admin sửa"


async def test_patch_ignores_null_fields(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    r = await client.patch(f"{API}/courses/{c['id']}", json={"title": None, "description": "Mới"}, headers=gv)
    assert r.status_code == 200
    assert r.json()["title"] == c["title"] and r.json()["description"] == "Mới"


async def test_delete_course(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    assert (await client.delete(f"{API}/courses/{c['id']}", headers=gv)).status_code == 204
    assert (
        await client.patch(f"{API}/courses/{c['id']}", json={"title": "Xyz"}, headers=gv)
    ).status_code == 404


async def test_publish_empty_course_is_rejected(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    r = await client.post(f"{API}/courses/{c['id']}/publish", headers=gv)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "COURSE_EMPTY"
