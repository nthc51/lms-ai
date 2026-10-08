import logging
from datetime import timedelta
from functools import lru_cache
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.time import utcnow
from app.modules.notify.mailer import Mailer
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.templates import Mail

logger = logging.getLogger(__name__)
SEND_BATCH = 5  # 5 × SMTP_TIMEOUT_S (20 giây) < timeout job 120 giây


def queue_email(db: AsyncSession, to: str, template: str, mail: Mail) -> None:
    """Thêm email vào outbox trong transaction đang mở. Nơi gọi tự commit (cùng thay đổi nghiệp vụ)."""
    subject, text, html = mail
    subject = " ".join(subject.split())  # tên khóa / tên người có xuống dòng thì header Subject sẽ lỗi
    db.add(EmailOutbox(to_email=to, subject=subject, body_text=text, body_html=html, template=template))


class MailKicker(Protocol):
    async def kick(self) -> None: ...


class ArqMailKicker:
    """Báo worker gửi ngay sau khi commit (không đợi cron mỗi phút). Lỗi Redis thì bỏ qua: cron vẫn gửi."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def kick(self) -> None:
        try:
            if self._pool is None:
                settings = RedisSettings.from_dsn(self._redis_url)
                # Redis chết thì bỏ qua nhanh (cron vẫn gửi), không để request chờ arq thử kết nối lại nhiều lần.
                settings.conn_retries = 0
                settings.conn_timeout = 1
                self._pool = await create_pool(settings)
            await self._pool.enqueue_job("send_pending_emails")
        except Exception:
            logger.warning("Không báo được worker gửi email, cron sẽ gửi sau", exc_info=True)


@lru_cache
def get_mail_kicker() -> MailKicker:
    return ArqMailKicker(get_settings().redis_url)


CLAIM_LEASE = timedelta(minutes=5)
RETRY_BACKOFF = timedelta(minutes=1)  # lỗi lần n thì chờ n phút rồi thử lại
REDACTED = "[Nội dung đã xóa sau khi gửi]"
# Email chứa link một lần (token thật): xóa nội dung sau khi gửi để DB không giữ token dạng rõ.
SECRET_TEMPLATES = frozenset({"verify_email"})


async def _claim(session_factory: async_sessionmaker) -> tuple[EmailOutbox, int] | None:
    """Nhận một email đến hạn gửi và commit ngay (attempts + 1, đặt hạn thuê), để khóa dòng không bị giữ
    trong lúc chờ SMTP và lần thử được tính kể cả khi worker chết giữa chừng."""
    now = utcnow()
    async with session_factory() as db:
        mail = await db.scalar(
            select(EmailOutbox)
            .where(
                EmailOutbox.status == EmailStatus.pending,
                or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now),
            )
            .order_by(EmailOutbox.created_at, EmailOutbox.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if mail is None:
            return None
        mail.attempts += 1
        mail.next_attempt_at = now + CLAIM_LEASE
        await db.commit()
        db.expunge(mail)
        return mail, mail.attempts


async def _finish(session_factory: async_sessionmaker, mail_id, error: str | None, attempts: int) -> None:
    async with session_factory() as db:
        mail = await db.get(EmailOutbox, mail_id)
        if error is None:
            mail.status = EmailStatus.sent
            mail.sent_at = utcnow()
            mail.last_error = None
            mail.next_attempt_at = None
            if mail.template in SECRET_TEMPLATES:
                mail.body_text = mail.body_html = REDACTED
        else:
            mail.last_error = error[:2000]
            if attempts >= get_settings().mail_max_attempts:
                mail.status = EmailStatus.failed
            else:
                mail.next_attempt_at = utcnow() + RETRY_BACKOFF * attempts
        await db.commit()


async def send_pending(session_factory: async_sessionmaker, mailer: Mailer, limit: int = SEND_BATCH) -> int:
    """Gửi tối đa `limit` email đến hạn, từng email một. Trả số email gửi thành công.

    Mỗi email: nhận (commit) → gửi SMTP → ghi kết quả (commit). Hai lần chạy song song (kick + cron) không
    nhận trùng nhờ SKIP LOCKED + hạn thuê. Gửi lỗi thì chờ lùi dần rồi thử lại, quá MAIL_MAX_ATTEMPTS thì failed.
    `limit` × SMTP_TIMEOUT_S phải nhỏ hơn timeout của job arq (120 giây)."""
    sent = 0
    for _ in range(limit):
        claimed = await _claim(session_factory)
        if claimed is None:
            break
        mail, attempts = claimed
        try:
            await mailer.send(mail.to_email, mail.subject, mail.body_text, mail.body_html)
        except Exception as exc:  # noqa: BLE001 — SMTP lỗi kiểu gì cũng thử lại ở lượt sau
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("Gửi email %s tới %s lỗi: %s", mail.id, mail.to_email, error)
            await _finish(session_factory, mail.id, error, attempts)
        else:
            await _finish(session_factory, mail.id, None, attempts)
            sent += 1
    return sent
