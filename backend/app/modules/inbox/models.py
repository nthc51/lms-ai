"""Thông báo trong app (B6): mỗi dòng là một thông báo cho một người, có liên kết tới nơi cần xem."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class NotificationKind(str, enum.Enum):
    comment_reply = "comment_reply"  # có người trả lời bình luận của bạn
    new_question = "new_question"  # học viên hỏi trong phần thảo luận khóa bạn dạy
    quiz_published = "quiz_published"  # khóa bạn học có quiz mới
    doc_ready = "doc_ready"  # tài liệu bạn tải lên đã xử lý xong
    doc_failed = "doc_failed"  # tài liệu bạn tải lên xử lý lỗi
    questions_ready = "questions_ready"  # AI đã sinh xong câu hỏi chờ duyệt
    questions_failed = "questions_failed"  # sinh câu hỏi không thành công


class Notification(IdMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # đếm thông báo chưa đọc: index một phần, chỉ chứa dòng chưa đọc
        Index("ix_notifications_unread", "user_id", postgresql_where=text("read_at IS NULL")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # chuỗi thay vì enum của Postgres: thêm loại thông báo mới không cần migration
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500), default="", server_default="")
    link: Mapped[str] = mapped_column(String(500))  # đường dẫn trong app, bắt đầu bằng "/"
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
