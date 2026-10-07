import enum
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class EmailStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class EmailOutbox(IdMixin, TimestampMixin, Base):
    """Hộp thư đi (outbox pattern): email được ghi CÙNG transaction với thay đổi sinh ra nó (đăng ký,
    duyệt giảng viên...), worker gửi sau. API không bao giờ chờ SMTP, và không mất mail khi SMTP lỗi."""

    __tablename__ = "email_outbox"
    __table_args__ = (
        Index("ix_email_outbox_pending", "created_at", postgresql_where=text("status = 'pending'")),
    )

    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(40))  # verify_email | teacher_approved | ...
    status: Mapped[EmailStatus] = mapped_column(
        SAEnum(EmailStatus, name="email_status"), default=EmailStatus.pending, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
