"""Xác nhận email khi đăng ký, email thông báo (outbox), gửi lại yêu cầu duyệt, xuất CSV, phản hồi 👎 của AI Tutor."""

import re
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import EmailToken
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.outbox import send_pending
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from tests.fakes import RecordingMailer
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


async def _outbox(to: str | None = None, *, verify: bool = False) -> list[EmailOutbox]:
    """Email trong outbox. Mặc định bỏ qua mail xác nhận (mọi tài khoản đăng ký qua API đều có một)."""
    async with SessionLocal() as db:
        stmt = select(EmailOutbox).order_by(EmailOutbox.created_at, EmailOutbox.id)
        if to:
            stmt = stmt.where(EmailOutbox.to_email == to)
        stmt = stmt.where((EmailOutbox.template == "verify_email") == verify)
        return list((await db.scalars(stmt)).all())


def _token(mail: EmailOutbox) -> str:
    return re.search(r"verify-email\?token=([\w-]+)", mail.body_text).group(1)


async def _login_raw(client, email):
    return await client.post(f"{API}/auth/login", json={"email": email, "password": "password123"})


# ---------- xác nhận email ----------


async def test_register_sends_verification_and_login_waits_for_it(client, kicker):
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An", verify=False)
    (mail,) = await _outbox("an@x.com", verify=True)
    assert (mail.template, mail.status) == ("verify_email", EmailStatus.pending)
    assert "http://localhost:3000/verify-email?token=" in mail.body_text and "Nguyễn Văn An" in mail.body_html
    assert kicker.kicks == 1

    assert _code(await _login_raw(client, "an@x.com")) == (403, "EMAIL_NOT_VERIFIED")
    wrong = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": "sai-mat-khau"})
    assert _code(wrong) == (401, "INVALID_CREDENTIALS")  # sai mật khẩu không lộ trạng thái xác nhận

    r = await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert (await _login_raw(client, "an@x.com")).status_code == 200
    # bấm lại link đã dùng: vẫn thành công
    assert (await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})).status_code == 200


async def test_verify_rejects_bad_and_expired_links(client):
    user = await register_user(client, "b@x.com", verify=False)
    (mail,) = await _outbox("b@x.com", verify=True)
    r = await client.post(f"{API}/auth/verify-email", json={"token": "khong-phai-token-that"})
    assert _code(r) == (400, "INVALID_TOKEN")
    async with SessionLocal() as db:
        await db.execute(
            update(EmailToken)
            .where(EmailToken.user_id == uuid.UUID(user["id"]))
            .values(expires_at=utcnow() - timedelta(minutes=1))
        )
        await db.commit()
    r = await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})
    assert _code(r) == (400, "TOKEN_EXPIRED")


async def test_resend_replaces_old_link_hides_unknown_emails_and_is_rate_limited(client):
    await register_user(client, "c@x.com", verify=False)
    r = await client.post(f"{API}/auth/resend-verification", json={"email": "ai-do@x.com"})
    assert r.status_code == 202
    assert await _outbox("ai-do@x.com", verify=True) == []

    assert (
        await client.post(f"{API}/auth/resend-verification", json={"email": "C@x.com"})
    ).status_code == 202
    old, new = await _outbox("c@x.com", verify=True)
    r = await client.post(f"{API}/auth/verify-email", json={"token": _token(old)})
    assert _code(r) == (400, "INVALID_TOKEN")  # link cũ bị thay
    assert (await client.post(f"{API}/auth/verify-email", json={"token": _token(new)})).status_code == 200

    # đã xác nhận thì không gửi nữa; quá 3 lần/giờ cho một email thì 429
    await client.post(f"{API}/auth/resend-verification", json={"email": "c@x.com"})
    assert len(await _outbox("c@x.com", verify=True)) == 2
    await client.post(f"{API}/auth/resend-verification", json={"email": "c@x.com"})  # lần thứ 3 trong giờ
    r = await client.post(f"{API}/auth/resend-verification", json={"email": "c@x.com"})
    assert _code(r) == (429, "RATE_LIMITED") and r.headers["retry-after"]


async def test_me_reports_email_verified(client):
    await register_user(client, "d@x.com")
    me = await client.get(f"{API}/me", headers=await login(client, "d@x.com"))
    assert me.json()["email_verified"] is True


# ---------- giảng viên chờ duyệt ----------


async def test_unverified_teacher_is_not_in_pending_queue_and_admins_are_told_after_verify(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher", full_name="Phạm Văn Cường", verify=False)
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert r.json()["total"] == 0
    assert (await client.get(f"{API}/admin/stats", headers=ad)).json()["pending_teachers"] == 0
    r = await client.get(f"{API}/admin/users", params={"status": "unverified"}, headers=ad)
    assert [u["id"] for u in r.json()["items"]] == [gv["id"]]

    (mail,) = await _outbox("gv@x.com", verify=True)
    await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["gv@x.com"]
    (notice,) = await _outbox("admin@x.com")
    assert notice.template == "new_pending_teacher" and "Phạm Văn Cường" in notice.subject


async def test_rejected_teacher_can_ask_again(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    headers = await login(client, "gv@x.com")
    assert _code(await client.post(f"{API}/me/teacher-request", headers=headers)) == (409, "NOT_REJECTED")

    await client.post(
        f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "Thiếu minh chứng"}, headers=ad
    )
    r = await client.post(f"{API}/me/teacher-request", headers=headers)
    assert (r.json()["teacher_status"], r.json()["review_note"]) == ("pending", None)
    assert [m.template for m in await _outbox("admin@x.com")] == ["new_pending_teacher"]
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["id"] for u in r.json()["items"]] == [gv["id"]]


# ---------- email từ thao tác quản trị ----------


async def test_admin_actions_email_the_affected_person(client, kicker):
    _, ad = await make_admin(client)
    gv1 = await register_user(client, "gv1@x.com", role="teacher", full_name="Lê Một")
    gv2 = await register_user(client, "gv2@x.com", role="teacher", full_name="Lê Hai")
    sv_id, _ = await make_student(client)
    before = kicker.kicks

    await client.post(f"{API}/admin/teachers/{gv1['id']}/approve", headers=ad)
    await client.post(
        f"{API}/admin/teachers/{gv2['id']}/reject", json={"reason": "Thiếu minh chứng"}, headers=ad
    )
    await client.post(f"{API}/admin/users/{sv_id}/lock", json={"reason": "Spam"}, headers=ad)
    gv1_headers = await login(client, "gv1@x.com")
    course, _, _ = await make_published_course(client, gv1_headers, title="Giải tích")
    await client.post(f"{API}/admin/courses/{course['id']}/hide", json={"reason": "Sao chép"}, headers=ad)
    await client.post(f"{API}/admin/courses/{course['id']}/unhide", headers=ad)

    assert [m.template for m in await _outbox("gv1@x.com")] == [
        "teacher_approved",
        "course_hidden",
        "course_unhidden",
    ]
    (rejected,) = await _outbox("gv2@x.com")
    assert rejected.template == "teacher_rejected" and "Thiếu minh chứng" in rejected.body_text
    (locked,) = await _outbox("sv@x.com")
    assert locked.template == "account_locked" and "Spam" in locked.body_text
    hidden = (await _outbox("gv1@x.com"))[1]
    assert f"/teach/{course['slug']}" in hidden.body_text and "Sao chép" in hidden.body_html
    assert kicker.kicks - before == 5


async def _make_due(to: str | None = None) -> None:
    """Cho email đang chờ lùi (backoff / hạn thuê) đến hạn gửi ngay."""
    async with SessionLocal() as db:
        stmt = update(EmailOutbox).values(next_attempt_at=None)
        if to:
            stmt = stmt.where(EmailOutbox.to_email == to)
        await db.execute(stmt)
        await db.commit()


async def test_send_pending_marks_sent_and_retries_with_backoff_then_gives_up():
    async with SessionLocal() as db:
        db.add(
            EmailOutbox(to_email="a@x.com", subject="S", body_text="T", body_html="<p>T</p>", template="t")
        )
        await db.commit()

    flaky = RecordingMailer(fail_times=1)
    assert await send_pending(SessionLocal, flaky) == 0
    (mail,) = await _outbox()
    assert (mail.status, mail.attempts, mail.last_error) == (
        EmailStatus.pending,
        1,
        "ConnectionError: SMTP down",
    )
    assert mail.next_attempt_at > utcnow()  # chờ lùi, không thử lại ngay
    assert await send_pending(SessionLocal, flaky) == 0
    await _make_due()
    assert await send_pending(SessionLocal, flaky) == 1
    (mail,) = await _outbox()
    assert (mail.status, mail.attempts, mail.last_error) == (EmailStatus.sent, 2, None)
    assert flaky.sent == [{"to": "a@x.com", "subject": "S", "text": "T", "html": "<p>T</p>"}]

    async with SessionLocal() as db:
        db.add(
            EmailOutbox(
                to_email="b@x.com", subject="S", body_text="T", body_html="T", template="t", attempts=4
            )
        )
        await db.commit()
    assert await send_pending(SessionLocal, RecordingMailer(fail_times=9)) == 0
    assert (await _outbox("b@x.com"))[0].status == EmailStatus.failed  # lần thứ 5 vẫn lỗi → bỏ


# ---------- CSV ----------


async def test_export_users_csv_follows_filters(client):
    _, ad = await make_admin(client)
    _, sv = await make_student(client)
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await make_teacher(client)
    r = await client.get(f"{API}/admin/users/export", params={"role": "student"}, headers=ad)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "nguoi-dung.csv" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿Họ tên,Email,Vai trò")
    lines = text.strip().splitlines()
    assert len(lines) == 3 and "Nguyễn Văn An,an@x.com,Học viên" in text and "gv@x.com" not in text
    assert (await client.get(f"{API}/admin/users/export", headers=sv)).status_code == 403


# ---------- phản hồi 👎 của AI Tutor ----------


async def _downvoted_answer(course_id: str, user_id: str, lesson_id: str | None = None) -> None:
    async with SessionLocal() as db:
        session = ChatSession(
            user_id=uuid.UUID(user_id),
            course_id=uuid.UUID(course_id),
            lesson_id=lesson_id and uuid.UUID(lesson_id),
        )
        db.add(session)
        await db.flush()
        db.add(ChatMessage(session_id=session.id, role=ChatRole.user, content="Đạo hàm là gì?"))
        await db.flush()
        db.add(
            ChatMessage(
                session_id=session.id, role=ChatRole.assistant, content="Câu trả lời sai [1].", feedback=-1
            )
        )
        db.add(ChatMessage(session_id=session.id, role=ChatRole.assistant, content="Câu tốt", feedback=1))
        await db.commit()


async def test_tutor_feedback_lists_downvoted_answers(client):
    _, ad = await make_admin(client)
    _, gv = await make_teacher(client)
    _, other = await make_teacher(client, "gv2@x.com")
    course, _, lesson = await make_published_course(client, gv)
    sv_id, _ = await make_student(client)
    await _downvoted_answer(course["id"], sv_id, lesson["id"])

    r = await client.get(f"{API}/admin/tutor-feedback", headers=ad)
    (item,) = r.json()["items"]
    assert (item["question"], item["answer"], item["student_name"]) == (
        "Đạo hàm là gì?",
        "Câu trả lời sai [1].",
        "Người dùng",
    )
    assert (item["course_slug"], item["lesson_title"]) == (course["slug"], lesson["title"])
    assert (await client.get(f"{API}/admin/stats", headers=ad)).json()["tutor_downvotes_7d"] == 1

    mine = await client.get(f"{API}/courses/{course['id']}/tutor-feedback", headers=gv)
    assert mine.json()["total"] == 1 and mine.json()["items"][0]["student_name"] is None
    assert (
        await client.get(f"{API}/courses/{course['id']}/tutor-feedback", headers=other)
    ).status_code == 404
