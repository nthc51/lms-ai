"""Các sửa sau code review: gửi email từng cái một có hạn thuê, tách lý do khóa, chặn CSV injection,
escape LIKE, tắt bắt buộc xác nhận email, chống spam đăng ký, xóa token khỏi outbox sau khi gửi."""

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.outbox import REDACTED, _claim, queue_email, send_pending
from app.modules.notify.templates import course_hidden
from tests.fakes import RecordingMailer
from tests.helpers import API, login, make_admin, make_student, register_user


async def _outbox(template: str | None = None) -> list[EmailOutbox]:
    async with SessionLocal() as db:
        stmt = select(EmailOutbox).order_by(EmailOutbox.created_at, EmailOutbox.id)
        if template:
            stmt = stmt.where(EmailOutbox.template == template)
        return list((await db.scalars(stmt)).all())


async def test_claimed_email_is_not_sent_twice_while_leased_and_retried_after_lease():
    async with SessionLocal() as db:
        db.add(EmailOutbox(to_email="a@x.com", subject="S", body_text="T", body_html="T", template="t"))
        await db.commit()
    claimed = await _claim(SessionLocal)  # worker nhận email rồi "chết" trước khi gửi xong
    assert claimed is not None and claimed[1] == 1
    mailer = RecordingMailer()
    assert await send_pending(SessionLocal, mailer) == 0  # còn trong hạn thuê: không gửi trùng
    async with SessionLocal() as db:
        await db.execute(update(EmailOutbox).values(next_attempt_at=None))
        await db.commit()
    assert await send_pending(SessionLocal, mailer) == 1  # hết hạn thuê: gửi lại
    (mail,) = await _outbox()
    assert (mail.status, mail.attempts) == (EmailStatus.sent, 2)


async def test_verification_email_body_is_redacted_after_sending(client):
    await register_user(client, "an@x.com", verify=False)
    assert await send_pending(SessionLocal, RecordingMailer()) == 1
    (mail,) = await _outbox("verify_email")
    assert mail.status == EmailStatus.sent and mail.body_text == mail.body_html == REDACTED


async def test_subject_newlines_are_flattened():
    async with SessionLocal() as db:
        queue_email(db, "gv@x.com", "course_hidden", course_hidden("Bình", "Giải tích\r\n1", "x", "http://u"))
        await db.commit()
    (mail,) = await _outbox()
    assert mail.subject == "Khóa học “Giải tích 1” đã bị ẩn"
    mailer = RecordingMailer()
    assert await send_pending(SessionLocal, mailer) == 1


async def test_lock_reason_is_separate_from_rejection_reason(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    await client.post(
        f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "Thiếu minh chứng"}, headers=ad
    )
    r = await client.post(f"{API}/admin/users/{gv['id']}/lock", json={"reason": "Spam"}, headers=ad)
    assert (r.json()["review_note"], r.json()["lock_reason"]) == ("Thiếu minh chứng", "Spam")
    r = await client.post(f"{API}/admin/users/{gv['id']}/unlock", headers=ad)
    assert (r.json()["review_note"], r.json()["lock_reason"]) == ("Thiếu minh chứng", None)
    me = await client.get(f"{API}/me", headers=await login(client, "gv@x.com"))
    assert me.json()["review_note"] == "Thiếu minh chứng"


async def test_csv_neutralises_formulas(client):
    _, ad = await make_admin(client)
    await register_user(client, "x@x.com", full_name='=HYPERLINK("http://evil","x")')
    r = await client.get(f"{API}/admin/users/export", params={"role": "student"}, headers=ad)
    assert "'=HYPERLINK" in r.content.decode("utf-8")


async def test_search_treats_percent_and_underscore_literally(client):
    _, ad = await make_admin(client)
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await register_user(client, "giam_50@x.com", full_name="Giảm 50% học phí")
    for q, expected in (("%", ["giam_50@x.com"]), ("_", ["giam_50@x.com"]), ("an", ["an@x.com"])):
        r = await client.get(f"{API}/admin/users", params={"role": "student", "q": q}, headers=ad)
        assert [u["email"] for u in r.json()["items"]] == expected, q


async def test_without_required_verification_teachers_queue_immediately(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_verification_required", False)
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher", verify=False)
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["id"] for u in r.json()["items"]] == [gv["id"]]
    assert [m.to_email for m in await _outbox("new_pending_teacher")] == ["admin@x.com"]
    assert (
        await client.post(f"{API}/auth/login", json={"email": "gv@x.com", "password": "password123"})
    ).status_code == 200


async def test_without_required_verification_clicking_the_link_does_not_notify_admins_again(
    client, monkeypatch
):
    import re

    monkeypatch.setattr(get_settings(), "email_verification_required", False)
    await make_admin(client)
    await register_user(client, "gv@x.com", role="teacher", verify=False)
    (mail,) = await _outbox("verify_email")
    token = re.search(r"verify-email\?token=([\w-]+)", mail.body_text).group(1)
    assert (await client.post(f"{API}/auth/verify-email", json={"token": token})).status_code == 200
    assert len(await _outbox("new_pending_teacher")) == 1  # chỉ lần báo lúc đăng ký


async def test_register_and_resend_are_rate_limited_per_ip(client, limiter):
    limiter.counts["register-ip:127.0.0.1"] = 20
    r = await client.post(
        f"{API}/auth/register", json={"email": "z@x.com", "password": "password123", "full_name": "Z"}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (429, "RATE_LIMITED")
    limiter.counts["verify-resend-ip:127.0.0.1"] = 10
    r = await client.post(f"{API}/auth/resend-verification", json={"email": "z@x.com"})
    assert r.status_code == 429


async def test_unlock_does_not_touch_other_users(client):
    _, ad = await make_admin(client)
    sv_id, _ = await make_student(client)
    await client.post(f"{API}/admin/users/{sv_id}/lock", json={}, headers=ad)
    r = await client.post(f"{API}/admin/users/{sv_id}/unlock", headers=ad)
    assert r.json()["lock_reason"] is None and r.json()["locked_at"] is None


async def test_mail_kicker_reuses_pool_across_kicks(monkeypatch):
    from app.modules.notify import outbox

    class Pool:
        def __init__(self):
            self.jobs: list[str] = []

        async def enqueue_job(self, name: str) -> None:
            self.jobs.append(name)

    pool, calls = Pool(), []

    async def fake_create_pool(settings):
        calls.append(settings)
        return pool

    monkeypatch.setattr(outbox, "create_pool", fake_create_pool)
    kicker = outbox.ArqMailKicker("redis://localhost:6379/0")
    await kicker.kick()
    await kicker.kick()
    assert len(calls) == 1 and (calls[0].conn_retries, calls[0].conn_timeout) == (0, 1)
    assert pool.jobs == ["send_pending_emails"] * 2
