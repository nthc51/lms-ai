"""Khu quản trị: duyệt giảng viên, khóa tài khoản, ẩn khóa học, số liệu tổng quan, nhật ký."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import User
from tests.helpers import (
    API,
    login,
    make_admin,
    make_published_course,
    make_student,
    make_teacher,
    register_user,
)


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/stats"),
        ("get", "/admin/users"),
        ("get", "/admin/courses"),
        ("get", "/admin/actions"),
        ("post", f"/admin/teachers/{uuid.uuid4()}/approve"),
        ("post", f"/admin/users/{uuid.uuid4()}/unlock"),
        ("post", f"/admin/courses/{uuid.uuid4()}/unhide"),
    ],
)
async def test_admin_routes_are_admin_only(client, method, path):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    for headers in (gv, sv):
        r = await getattr(client, method)(f"{API}{path}", headers=headers)
        assert _code(r) == (403, "FORBIDDEN")
    r = await getattr(client, method)(f"{API}{path}")
    assert r.status_code == 401


async def test_pending_list_is_oldest_first_and_approve_lets_teacher_create(client):
    _, ad = await make_admin(client)
    first = await register_user(client, "gv1@x.com", role="teacher", full_name="Lê Văn Một")
    await register_user(client, "gv2@x.com", role="teacher", full_name="Lê Văn Hai")
    await register_user(client, "sv@x.com")

    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["gv1@x.com", "gv2@x.com"]

    r = await client.post(f"{API}/admin/teachers/{first['id']}/approve", headers=ad)
    assert r.status_code == 200 and r.json()["teacher_status"] == "approved"
    gv = await login(client, "gv1@x.com")
    assert (await client.post(f"{API}/courses", json={"title": "Khóa mới"}, headers=gv)).status_code == 201

    r = await client.post(f"{API}/admin/teachers/{first['id']}/approve", headers=ad)
    assert _code(r) == (409, "ALREADY_APPROVED")


async def test_reject_needs_reason_and_teacher_sees_it(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    r = await client.post(f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "   "}, headers=ad)
    assert r.status_code == 422

    r = await client.post(
        f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": " Thiếu thông tin chuyên môn "}, headers=ad
    )
    assert r.status_code == 200
    assert (r.json()["teacher_status"], r.json()["review_note"]) == ("rejected", "Thiếu thông tin chuyên môn")

    me = await client.get(f"{API}/me", headers=await login(client, "gv@x.com"))
    assert (me.json()["teacher_status"], me.json()["review_note"]) == (
        "rejected",
        "Thiếu thông tin chuyên môn",
    )

    # Từ chối lần nữa: không còn ở trạng thái chờ. Đổi ý thì vẫn duyệt được, lý do bị xóa.
    again = await client.post(f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "x"}, headers=ad)
    assert _code(again) == (409, "NOT_PENDING")
    ok = await client.post(f"{API}/admin/teachers/{gv['id']}/approve", headers=ad)
    assert (ok.json()["teacher_status"], ok.json()["review_note"]) == ("approved", None)


async def test_approve_reject_only_for_teachers(client):
    _, ad = await make_admin(client)
    sv_id, _ = await make_student(client)
    r = await client.post(f"{API}/admin/teachers/{sv_id}/approve", headers=ad)
    assert _code(r) == (404, "NOT_FOUND")
    r = await client.post(f"{API}/admin/teachers/{uuid.uuid4()}/reject", json={"reason": "x"}, headers=ad)
    assert _code(r) == (404, "NOT_FOUND")


async def test_lock_revokes_sessions_and_unlock_restores(client):
    admin_id, ad = await make_admin(client)
    sv_id, sv = await make_student(client)
    login_r = await client.post(f"{API}/auth/login", json={"email": "sv@x.com", "password": "password123"})
    raw = login_r.cookies["refresh_token"]

    r = await client.post(f"{API}/admin/users/{sv_id}/lock", json={"reason": "Spam diễn đàn"}, headers=ad)
    assert r.status_code == 200 and r.json()["locked_at"] is not None
    assert r.json()["review_note"] == "Spam diễn đàn"
    assert _code(await client.get(f"{API}/me", headers=sv)) == (403, "ACCOUNT_LOCKED")
    client.cookies.clear()
    refreshed = await client.post(f"{API}/auth/refresh", headers={"Cookie": f"refresh_token={raw}"})
    assert refreshed.status_code in (401, 403)

    r = await client.post(f"{API}/admin/users/{sv_id}/unlock", headers=ad)
    assert (r.json()["locked_at"], r.json()["review_note"]) == (None, None)
    assert (await client.get(f"{API}/me", headers=await login(client, "sv@x.com"))).status_code == 200

    # không khóa được quản trị viên (kể cả chính mình); khóa không cần lý do
    assert _code(await client.post(f"{API}/admin/users/{admin_id}/lock", json={}, headers=ad)) == (
        409,
        "CANNOT_LOCK_ADMIN",
    )
    r = await client.post(f"{API}/admin/users/{sv_id}/lock", json={}, headers=ad)
    assert r.status_code == 200 and r.json()["review_note"] is None


async def test_users_filter_by_role_status_and_search_without_accents(client):
    _, ad = await make_admin(client)
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await register_user(client, "binh@x.com", full_name="Trần Thị Bình")
    gv_id, gv = await make_teacher(client, "gv@x.com")
    await make_published_course(client, gv)

    r = await client.get(f"{API}/admin/users", params={"role": "student", "q": "nguyen van"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["an@x.com"]
    r = await client.get(f"{API}/admin/users", params={"q": "BINH@"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["binh@x.com"]

    r = await client.get(f"{API}/admin/users", params={"role": "teacher"}, headers=ad)
    (teacher,) = r.json()["items"]
    assert (teacher["id"], teacher["course_count"], teacher["enrollment_count"]) == (gv_id, 1, 0)

    async with SessionLocal() as db:
        await db.execute(update(User).where(User.email == "binh@x.com").values(locked_at=utcnow()))
        await db.commit()
    r = await client.get(f"{API}/admin/users", params={"status": "locked"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["binh@x.com"]
    assert (await client.get(f"{API}/admin/users", params={"status": "bogus"}, headers=ad)).status_code == 422


async def test_hide_course_blocks_students_and_teacher_republish(client):
    _, ad = await make_admin(client)
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    _, sv = await make_student(client)
    assert (await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)).status_code == 201

    r = await client.post(
        f"{API}/admin/courses/{course['id']}/hide", json={"reason": "Vi phạm bản quyền"}, headers=ad
    )
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["hidden_reason"]) == ("archived", "Vi phạm bản quyền")
    assert r.json()["enrollment_count"] == 1

    # biến mất khỏi danh mục, học viên đã đăng ký cũng không vào được bài
    assert (await client.get(f"{API}/courses")).json()["total"] == 0
    assert (await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)).status_code == 404
    # giảng viên vẫn thấy khóa (kèm lý do) nhưng không tự xuất bản lại được
    mine = await client.get(f"{API}/courses/{course['slug']}", headers=gv)
    assert mine.json()["hidden_reason"] == "Vi phạm bản quyền"
    assert _code(await client.post(f"{API}/courses/{course['id']}/publish", headers=gv)) == (
        409,
        "COURSE_HIDDEN",
    )
    again = await client.post(f"{API}/admin/courses/{course['id']}/hide", json={"reason": "x"}, headers=ad)
    assert _code(again) == (409, "COURSE_NOT_PUBLISHED")

    r = await client.post(f"{API}/admin/courses/{course['id']}/unhide", headers=ad)
    assert (r.json()["status"], r.json()["hidden_reason"]) == ("published", None)
    assert (await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)).status_code == 200
    assert _code(await client.post(f"{API}/admin/courses/{course['id']}/unhide", headers=ad)) == (
        409,
        "COURSE_NOT_HIDDEN",
    )


async def test_courses_list_all_teachers_with_filters(client):
    _, ad = await make_admin(client)
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    pub, _, _ = await make_published_course(client, gv1, title="Giải tích một")
    r = await client.post(f"{API}/courses", json={"title": "Đại số tuyến tính"}, headers=gv2)
    draft = r.json()

    r = await client.get(f"{API}/admin/courses", headers=ad)
    assert {c["id"] for c in r.json()["items"]} == {pub["id"], draft["id"]}
    r = await client.get(f"{API}/admin/courses", params={"status": "draft"}, headers=ad)
    assert [c["id"] for c in r.json()["items"]] == [draft["id"]]
    r = await client.get(f"{API}/admin/courses", params={"q": "giai tich"}, headers=ad)
    (item,) = r.json()["items"]
    assert (item["teacher_email"], item["lesson_count"]) == ("gv1@x.com", 1)

    await client.post(f"{API}/admin/courses/{pub['id']}/hide", json={"reason": "x"}, headers=ad)
    r = await client.get(f"{API}/admin/courses", params={"status": "hidden"}, headers=ad)
    assert [c["id"] for c in r.json()["items"]] == [pub["id"]]
    r = await client.get(f"{API}/admin/courses", params={"status": "published"}, headers=ad)
    assert r.json()["total"] == 0


async def test_stats_counts_and_14_day_signups(client):
    _, ad = await make_admin(client)
    _, gv = await make_teacher(client)
    await register_user(client, "gv-cho@x.com", role="teacher")
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses", json={"title": "Bản nháp"}, headers=gv)
    _, sv = await make_student(client)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    async with SessionLocal() as db:  # một người đăng ký từ 20 ngày trước: không nằm trong 14 ngày
        await db.execute(
            update(User).where(User.email == "gv-cho@x.com").values(created_at=utcnow() - timedelta(days=20))
        )
        await db.commit()

    s = (await client.get(f"{API}/admin/stats", headers=ad)).json()
    assert (s["students"], s["teachers"], s["pending_teachers"]) == (1, 2, 1)
    assert (s["courses_published"], s["courses_draft"], s["courses_hidden"], s["enrollments"]) == (1, 1, 0, 1)
    assert len(s["signups_14d"]) == 14
    assert s["signups_14d"][0]["day"] < s["signups_14d"][-1]["day"]
    assert sum(d["count"] for d in s["signups_14d"]) == 3  # admin + gv + sv (gv-cho ngoài khoảng)


async def test_actions_log_records_who_did_what(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    await client.post(f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "Chưa đủ hồ sơ"}, headers=ad)
    await client.post(f"{API}/admin/teachers/{gv['id']}/approve", headers=ad)

    r = await client.get(f"{API}/admin/actions", headers=ad)
    items = r.json()["items"]
    assert {(a["action"], a["note"]) for a in items} == {
        ("reject_teacher", "Chưa đủ hồ sơ"),
        ("approve_teacher", None),
    }
    assert all(a["admin_name"] == "Quản trị viên" and a["target_label"] == "gv@x.com" for a in items)


def test_seed_admin_rejects_emails_login_would_refuse():
    from app.scripts.seed_admin import valid_email

    assert valid_email("Admin@Example.com") == "admin@example.com"
    with pytest.raises(SystemExit):
        valid_email("admin@lms.local")
