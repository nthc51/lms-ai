import logging
from functools import lru_cache
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.time import utcnow
from app.modules.notify.mailer import Mailer
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.templates import Mail

logger = logging.getLogger(__name__)
SEND_BATCH = 20


def queue_email(db: AsyncSession, to: str, template: str, mail: Mail) -> None:
    """Thêm email vào outbox trong transaction đang mở. Nơi gọi tự commit (cùng thay đổi nghiệp vụ)."""
    subject, text, html = mail
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
                self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
            await self._pool.enqueue_job("send_pending_emails")
        except Exception:
            logger.warning("Không báo được worker gửi email, cron sẽ gửi sau", exc_info=True)


@lru_cache
def get_mail_kicker() -> MailKicker:
    return ArqMailKicker(get_settings().redis_url)


async def send_pending(session_factory: async_sessionmaker, mailer: Mailer, limit: int = SEND_BATCH) -> int:
    """Gửi các email đang chờ. Trả số email gửi thành công.

    FOR UPDATE SKIP LOCKED: hai lần chạy song song (kick + cron) không gửi trùng một email.
    Gửi lỗi thì tăng attempts, quá MAIL_MAX_ATTEMPTS thì chuyển failed."""
    max_attempts = get_settings().mail_max_attempts
    sent = 0
    async with session_factory() as db:
        rows = (
            await db.scalars(
                select(EmailOutbox)
                .where(EmailOutbox.status == EmailStatus.pending)
                .order_by(EmailOutbox.created_at, EmailOutbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for mail in rows:
            mail.attempts += 1
            try:
                await mailer.send(mail.to_email, mail.subject, mail.body_text, mail.body_html)
            except Exception as exc:  # noqa: BLE001 — SMTP lỗi kiểu gì cũng thử lại ở lượt sau
                mail.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                if mail.attempts >= max_attempts:
                    mail.status = EmailStatus.failed
                logger.warning("Gửi email %s tới %s lỗi: %s", mail.id, mail.to_email, mail.last_error)
            else:
                mail.status = EmailStatus.sent
                mail.sent_at = utcnow()
                mail.last_error = None
                sent += 1
        await db.commit()
    return sent
