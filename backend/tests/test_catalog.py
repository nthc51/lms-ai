from tests.helpers import API, create_course, make_published_course, make_student, make_teacher


async def test_catalog_lists_only_published(client):
    _, gv = await make_teacher(client)
    await make_published_course(client, gv, title="Cấu trúc dữ liệu")
    await create_course(client, gv, title="Bản nháp bí mật")
    r = await client.get(f"{API}/courses")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Cấu trúc dữ liệu"
    assert body["items"][0]["teacher_name"] == "Giảng viên"


async def test_catalog_search_ignores_diacritics_and_case(client):
    _, gv = await make_teacher(client)
    await make_published_course(client, gv, title="Cấu trúc dữ liệu")
    await make_published_course(client, gv, title="Mạng máy tính")
    r = await client.get(f"{API}/courses", params={"q": "CAU TRUC"})
    assert [c["title"] for c in r.json()["items"]] == ["Cấu trúc dữ liệu"]


async def test_catalog_pagination(client):
    _, gv = await make_teacher(client)
    for i in range(3):
        await make_published_course(client, gv, title=f"Khóa số {i}")
    r = await client.get(f"{API}/courses", params={"page": 2, "size": 2})
    assert r.json()["total"] == 3 and len(r.json()["items"]) == 1


async def test_course_detail_anonymous_shows_outline_without_content(client):
    _, gv = await make_teacher(client)
    course, section, lesson = await make_published_course(client, gv)
    client.cookies.clear()
    r = await client.get(f"{API}/courses/{course['slug']}")
    assert r.status_code == 200
    d = r.json()
    assert d["is_enrolled"] is False and d["is_owner"] is False
    assert d["sections"][0]["id"] == section["id"]
    lesson_brief = d["sections"][0]["lessons"][0]
    assert lesson_brief["id"] == lesson["id"]
    assert "content_md" not in lesson_brief


async def test_course_detail_shows_enrolled_flag(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    r = await client.get(f"{API}/courses/{course['slug']}", headers=sv)
    assert r.json()["is_enrolled"] is True


async def test_draft_detail_hidden_from_public_visible_to_owner(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    draft = await create_course(client, gv)
    assert (await client.get(f"{API}/courses/{draft['slug']}")).status_code == 404
    assert (await client.get(f"{API}/courses/{draft['slug']}", headers=sv)).status_code == 404
    r = await client.get(f"{API}/courses/{draft['slug']}", headers=gv)
    assert r.status_code == 200 and r.json()["is_owner"] is True


async def test_course_routes_are_not_shadowed_by_slug(client):
    """Canh luật thứ tự route: GET /courses (không có slug) vẫn là catalog, không bị hiểu thành slug rỗng."""
    r = await client.get(f"{API}/courses")
    assert r.status_code == 200 and "items" in r.json()


async def test_invalid_token_on_optional_auth_is_401(client):
    _, gv = await make_teacher(client)
    course, _, _ = await make_published_course(client, gv)
    r = await client.get(f"{API}/courses/{course['slug']}", headers={"Authorization": "Bearer rac"})
    assert r.status_code == 401
