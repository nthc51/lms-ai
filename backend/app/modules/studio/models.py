import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class StudioStatus(str, enum.Enum):
    generating = "generating"
    ready = "ready"
    failed = "failed"


class ArtifactKind(str, enum.Enum):
    study_guide = "study_guide"  # Đề cương ôn tập
    briefing = "briefing"  # Tóm tắt nhanh
    faq = "faq"  # Hỏi đáp
    timeline = "timeline"  # Dòng thời gian
    flashcards = "flashcards"


class SourceGuide(TimestampMixin, Base):
    """Hướng dẫn tài liệu (S1): tóm tắt, chủ đề chính, câu hỏi gợi ý. Một dòng mỗi source, sinh lại khi xử lý lại."""

    __tablename__ = "source_guides"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[StudioStatus] = mapped_column(SAEnum(StudioStatus, name="studio_status"))
    title: Mapped[str] = mapped_column(
        String(200), default=""
    )  # tên tài liệu AI suy ra (file gốc không lưu tên)
    summary: Mapped[str] = mapped_column(Text, default="")
    topics: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    questions: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    error_msg: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(80))


class StudyArtifact(IdMixin, TimestampMixin, Base):
    """Một tài liệu học AI sinh (S2 báo cáo, S3 flashcard) cho một phạm vi: một bài, hoặc cả khóa (lesson_id NULL).

    Sinh một lần, mọi người trong khóa dùng chung. fingerprint = băm danh sách đoạn tài liệu lúc sinh: tài liệu
    đổi thì fingerprint hiện tại khác → bản này "cũ" (stale), lần yêu cầu sau sinh bản mới. Bản giảng viên đã
    sửa (reviewed_at) không bao giờ bị thay tự động."""

    __tablename__ = "study_artifacts"
    __table_args__ = (Index("ix_study_artifacts_scope", "course_id", "lesson_id", "kind", "created_at"),)

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    kind: Mapped[ArtifactKind] = mapped_column(SAEnum(ArtifactKind, name="artifact_kind"))
    status: Mapped[StudioStatus] = mapped_column(
        SAEnum(StudioStatus, name="studio_status", create_type=False)
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    content_md: Mapped[str] = mapped_column(Text, default="")  # báo cáo
    cards: Mapped[list[dict] | None] = mapped_column(JSONB)  # flashcard: [{front, back, sources: [n]}]
    # [{n, chunk_id, lesson_id, page_no, heading_path}] cho mọi [n] xuất hiện trong nội dung
    citations: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    error_msg: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlashcardReview(Base):
    """Học viên đánh dấu một thẻ là đã nhớ / chưa nhớ (S3)."""

    __tablename__ = "flashcard_reviews"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("study_artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    card_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    known: Mapped[bool] = mapped_column(Boolean)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Note(IdMixin, TimestampMixin, Base):
    """Ghi chú riêng của một học viên (S4): tự viết, lưu từ câu trả lời AI Tutor, hoặc AI tổng hợp từ ghi chú khác."""

    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_user_course", "user_id", "course_id", "updated_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    content_md: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    from_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL")
    )
    # ready, hoặc generating / failed khi đang được AI tổng hợp từ ghi chú khác (job notes_synth)
    status: Mapped[StudioStatus] = mapped_column(
        SAEnum(StudioStatus, name="studio_status", create_type=False), default=StudioStatus.ready
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
