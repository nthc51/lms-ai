import uuid

import pytest
from sqlalchemy import update

from app.core import cache as cache_mod
from app.core.cache import RedisCache
from app.core.config import get_settings
from app.modules.courses.models import Course
from tests.helpers import (
    API,
    add_lesson,
    add_section,
    create_course,
    make_admin,
    make_published_course,
    make_student,
    make_teacher,
)


@pytest.fixture
async def redis_cache(monkeypatch):
    c = RedisCache.from_url(get_settings().redis_url, prefix=f"test-{uuid.uuid4().hex}")
    monkeypatch.setattr(cache_mod, "get_cache", lambda: c)
    yield c
    await c.aclose()


async def _titles(client) -> list[str]:
    return [c["title"] for c in (await client.get(f"{API}/courses")).json()["items"]]


async def test_catalog_served_from_cache_until_course_changes(client, db, redis_cache):
    _, gv = await make_teacher(client)
    course, _, _ = await make_published_course(client, gv, title="Cấu trúc dữ liệu")
    assert await _titles(client) == ["Cấu trúc dữ liệu"]

    # Sửa thẳng DB (không qua service nên không bump) → vẫn thấy bản cache: chứng minh có cache
    await db.execute(update(Course).where(Course.id == uuid.UUID(course["id"])).values(title="Đổi ngầm"))
    await db.commit()
    assert await _titles(client) == ["Cấu trúc dữ liệu"]

    # Sửa qua API → service bump → thấy bản mới ngay
    r = await client.patch(f"{API}/courses/{course['id']}", json={"title": "Giải thuật nâng cao"}, headers=gv)
    assert r.status_code == 200
    assert await _titles(client) == ["Giải thuật nâng cao"]


async def test_detail_cache_keeps_per_user_flags(client, redis_cache):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    url = f"{API}/courses/{course['slug']}"

    anon = (await client.get(url)).json()
    student = (await client.get(url, headers=sv)).json()
    owner = (await client.get(url, headers=gv)).json()
    assert (anon["is_enrolled"], anon["is_owner"]) == (False, False)
    assert (student["is_enrolled"], student["is_owner"]) == (True, False)
    assert owner["is_owner"] is True


async def test_draft_detail_is_not_cached_and_stays_private(client, redis_cache):
    _, gv = await make_teacher(client)
    draft = await create_course(client, gv)
    url = f"{API}/courses/{draft['slug']}"
    assert (await client.get(url, headers=gv)).status_code == 200
    assert (await client.get(url)).status_code == 404  # bản giáo viên vừa xem không bị cache cho khách


async def test_adding_lesson_invalidates_detail(client, redis_cache):
    _, gv = await make_teacher(client)
    course, section, _ = await make_published_course(client, gv)
    url = f"{API}/courses/{course['slug']}"
    assert len((await client.get(url)).json()["sections"][0]["lessons"]) == 1
    await add_lesson(client, gv, section["id"], "Bài 2")
    assert len((await client.get(url)).json()["sections"][0]["lessons"]) == 2


async def test_admin_hide_and_unhide_take_effect_immediately(client, redis_cache):
    _, gv = await make_teacher(client)
    _, ad = await make_admin(client)
    course, _, _ = await make_published_course(client, gv, title="Khóa vi phạm")
    url = f"{API}/courses/{course['slug']}"
    assert await _titles(client) == ["Khóa vi phạm"]
    assert (await client.get(url)).status_code == 200  # đã nằm trong cache

    r = await client.post(f"{API}/admin/courses/{course['id']}/hide", json={"reason": "Vi phạm"}, headers=ad)
    assert r.status_code == 200
    assert await _titles(client) == []
    assert (await client.get(url)).status_code == 404
    owner = (await client.get(url, headers=gv)).json()
    assert owner["hidden_reason"] == "Vi phạm"

    assert (await client.post(f"{API}/admin/courses/{course['id']}/unhide", headers=ad)).status_code == 200
    assert await _titles(client) == ["Khóa vi phạm"]


async def test_detail_cache_never_leaks_flags_between_users(client, redis_cache):
    _, gv = await make_teacher(client)
    _, sv1 = await make_student(client, "sv1@x.com")
    _, sv2 = await make_student(client, "sv2@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv1)
    url = f"{API}/courses/{course['slug']}"

    # Người đầu tiên làm đầy cache là chủ khóa; những người sau phải vẫn nhận cờ của riêng họ
    owner = (await client.get(url, headers=gv)).json()
    assert owner["is_owner"] is True
    s1 = (await client.get(url, headers=sv1)).json()
    s2 = (await client.get(url, headers=sv2)).json()
    other_teacher = (await client.get(url, headers=gv2)).json()
    assert (s1["is_owner"], s1["is_enrolled"]) == (False, True)
    assert (s2["is_owner"], s2["is_enrolled"]) == (False, False)
    assert (other_teacher["is_owner"], other_teacher["is_enrolled"]) == (False, False)


async def test_publish_and_delete_invalidate_catalog(client, redis_cache):
    _, gv = await make_teacher(client)
    course = await create_course(client, gv, title="Khóa nháp mới")
    section = await add_section(client, gv, course["id"])
    await add_lesson(client, gv, section["id"])
    assert await _titles(client) == []
    assert (await client.post(f"{API}/courses/{course['id']}/publish", headers=gv)).status_code == 200
    assert await _titles(client) == ["Khóa nháp mới"]
    assert (await client.delete(f"{API}/courses/{course['id']}", headers=gv)).status_code == 204
    assert await _titles(client) == []
    assert (await client.get(f"{API}/courses/{course['slug']}")).status_code == 404


def test_catalog_key_uses_the_whole_search_text():
    from app.core.pagination import PageParams
    from app.modules.courses.service import _catalog_key

    p = PageParams(page=1, size=12)
    long_a, long_b = "a" * 100 + "x", "a" * 100 + "y"
    assert _catalog_key(long_a, p) != _catalog_key(long_b, p)
    assert _catalog_key(" Toán ", p) == _catalog_key("toán", p)
    assert _catalog_key("toán", p) != _catalog_key("toán", PageParams(page=2, size=12))
