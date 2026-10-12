"""Quên mật khẩu: gửi link đặt lại qua email (outbox), đặt mật khẩu mới, thu hồi mọi phiên cũ."""

import re
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import EmailToken, RefreshToken, User
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.outbox import REDACTED, send_pending
from tests.fakes import RecordingMailer
from tests.helpers import API, login, make_admin, register_user

NEW_PASSWORD = "mat-khau-moi-123"


async def _reset_mails(to: str) -> list[EmailOutbox]:
    async with SessionLocal() as db:
        stmt = (
            select(EmailOutbox)
            .where(EmailOutbox.to_email == to, EmailOutbox.template == "reset_password")
            .order_by(EmailOutbox.created_at, EmailOutbox.id)
        )
        return list((await db.scalars(stmt)).all())


def _token(mail: EmailOutbox) -> str:
    return re.search(r"reset-password\?token=([\w-]+)", mail.body_text).group(1)


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def _forgot(client, email):
    return await client.post(f"{API}/auth/forgot-password", json={"email": email})


async def _reset(client, token, password=NEW_PASSWORD):
    return await client.post(f"{API}/auth/reset-password", json={"token": token, "password": password})


async def test_forgot_password_sends_link_and_reset_logs_out_everywhere(client, kicker):
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await login(client, "an@x.com")  # một phiên đang mở

    r = await _forgot(client, "AN@x.com")
    assert r.status_code == 202 and kicker.kicks >= 1
    (mail,) = await _reset_mails("an@x.com")
    assert mail.status == EmailStatus.pending
    assert (
        "http://localhost:3000/reset-password?token=" in mail.body_text and "Nguyễn Văn An" in mail.body_html
    )

    assert (await _reset(client, _token(mail))).status_code == 200
    old = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": "password123"})
    assert _code(old) == (401, "INVALID_CREDENTIALS")
    new = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": NEW_PASSWORD})
    assert new.status_code == 200
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "an@x.com"))
        tokens = (await db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))).all()
    # phiên mở trước khi đổi mật khẩu bị thu hồi; chỉ phiên vừa đăng nhập bằng mật khẩu mới còn dùng được
    assert sum(t.revoked_at is None for t in tokens) == 1

    # link chỉ dùng một lần
    assert _code(await _reset(client, _token(mail))) == (400, "INVALID_TOKEN")


async def test_unknown_or_locked_email_gets_202_but_no_mail(client):
    assert (await _forgot(client, "ai-do@x.com")).status_code == 202
    assert await _reset_mails("ai-do@x.com") == []
    user = await register_user(client, "khoa@x.com")
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == uuid.UUID(user["id"])).values(locked_at=utcnow()))
        await db.commit()
    assert (await _forgot(client, "khoa@x.com")).status_code == 202
    assert await _reset_mails("khoa@x.com") == []


async def test_new_request_replaces_old_link_and_expired_link_is_rejected(client):
    user = await register_user(client, "b@x.com")
    await _forgot(client, "b@x.com")
    await _forgot(client, "b@x.com")
    old, new = await _reset_mails("b@x.com")
    assert _code(await _reset(client, _token(old))) == (400, "INVALID_TOKEN")
    async with SessionLocal() as db:
        await db.execute(
            update(EmailToken)
            .where(EmailToken.user_id == uuid.UUID(user["id"]), EmailToken.purpose == "reset_password")
            .values(expires_at=utcnow() - timedelta(minutes=1))
        )
        await db.commit()
    assert _code(await _reset(client, _token(new))) == (400, "TOKEN_EXPIRED")


async def test_reset_validates_password_and_does_not_accept_verify_tokens(client):
    await register_user(client, "c@x.com", verify=False)
    async with SessionLocal() as db:
        verify_mail = await db.scalar(
            select(EmailOutbox).where(
                EmailOutbox.to_email == "c@x.com", EmailOutbox.template == "verify_email"
            )
        )
    verify_token = re.search(r"verify-email\?token=([\w-]+)", verify_mail.body_text).group(1)
    assert _code(await _reset(client, verify_token)) == (400, "INVALID_TOKEN")

    await _forgot(client, "c@x.com")
    (mail,) = await _reset_mails("c@x.com")
    assert (await _reset(client, _token(mail), password="ngan")).status_code == 422
    # đặt lại mật khẩu qua email là đã chứng minh sở hữu hộp thư: coi như đã xác nhận email
    assert (await _reset(client, _token(mail))).status_code == 200
    r = await client.post(f"{API}/auth/login", json={"email": "c@x.com", "password": NEW_PASSWORD})
    assert r.status_code == 200


async def test_reset_by_unverified_pending_teacher_tells_admins(client):
    await make_admin(client)
    await register_user(client, "gv@x.com", role="teacher", full_name="Cô Ba", verify=False)
    await _forgot(client, "gv@x.com")
    (mail,) = await _reset_mails("gv@x.com")
    assert (await _reset(client, _token(mail))).status_code == 200
    async with SessionLocal() as db:
        notices = (
            await db.scalars(select(EmailOutbox).where(EmailOutbox.template == "new_pending_teacher"))
        ).all()
    assert [m.to_email for m in notices] == ["admin@x.com"]


async def test_forgot_password_is_rate_limited(client, limiter):
    await register_user(client, "d@x.com")
    for _ in range(3):
        assert (await _forgot(client, "d@x.com")).status_code == 202
    r = await _forgot(client, "d@x.com")
    assert _code(r) == (429, "RATE_LIMITED") and r.headers["retry-after"]
    assert any(k.startswith("pwd-reset-ip:") for k in limiter.counts)


async def test_reset_mail_body_is_redacted_after_sending(client):
    await register_user(client, "e@x.com")
    await _forgot(client, "e@x.com")
    await send_pending(SessionLocal, RecordingMailer())
    (mail,) = await _reset_mails("e@x.com")
    assert mail.status == EmailStatus.sent and mail.body_text == REDACTED
