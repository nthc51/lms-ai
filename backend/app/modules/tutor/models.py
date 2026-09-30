import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    false,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class ChatSession(IdMixin, TimestampMixin, Base):
    """Phiên hỏi đáp của một người dùng. lesson_id NULL = hỏi trên toàn khóa."""

    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_user_course", "user_id", "course_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))


class ChatMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
        CheckConstraint("feedback IN (1, -1)", name="ck_chat_messages_feedback"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[ChatRole] = mapped_column(SAEnum(ChatRole, name="chat_role"))
    content: Mapped[str] = mapped_column(Text, default="")
    # [{n, chunk_id, lesson_id, page_no, start_sec}]: chỉ các nguồn thực sự được trích trong câu trả lời
    citations: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    refused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    feedback: Mapped[int | None] = mapped_column(SmallInteger)  # 1 | -1 (D1)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    prompt_version: Mapped[str | None] = mapped_column(String(80))
