"""Thảo luận theo bài học (B4): bình luận gốc và một cấp trả lời."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class LessonComment(IdMixin, TimestampMixin, Base):
    __tablename__ = "lesson_comments"
    __table_args__ = (Index("ix_lesson_comments_lesson_created", "lesson_id", "created_at"),)

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # None = bình luận gốc; có giá trị = trả lời (chỉ trả lời bình luận gốc, nên tối đa 2 cấp)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lesson_comments.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # xóa mềm: giữ chỗ trong luồng
