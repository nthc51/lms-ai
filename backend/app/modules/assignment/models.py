"""Bài tập (B5): giảng viên ra đề kèm rubric, học viên nộp bài, AI gợi ý điểm từng tiêu chí, giảng viên xác nhận."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class AssignmentStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class SubmissionStatus(str, enum.Enum):
    submitted = "submitted"  # vừa nộp, chờ AI chấm gợi ý
    ai_graded = "ai_graded"  # AI đã gợi ý điểm, chờ giảng viên xác nhận
    ai_failed = "ai_failed"  # AI không chấm được: giảng viên chấm tay
    graded = "graded"  # giảng viên đã xác nhận điểm (học viên thấy điểm)


class Assignment(IdMixin, TimestampMixin, Base):
    __tablename__ = "assignments"

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text)  # đề bài (Markdown)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # None = không có hạn
    # [{key, criterion, max_points, description}], key do server đặt (c1, c2, ...) theo thứ tự
    rubric: Mapped[list[dict]] = mapped_column(JSONB)
    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(AssignmentStatus, name="assignment_status"), default=AssignmentStatus.draft
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Submission(IdMixin, TimestampMixin, Base):
    """Mỗi học viên một bài nộp cho mỗi bài tập; nộp lại thì cập nhật tại chỗ và tăng version (spec 4.3)."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "user_id", name="uq_submissions_assignment_user"),
        Index("ix_submissions_assignment_status", "assignment_id", "status"),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text_content: Mapped[str] = mapped_column(Text, default="", server_default="")
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, name="submission_status"), default=SubmissionStatus.submitted
    )
    # Gợi ý của AI, không bao giờ bị giảng viên ghi đè: {scores: {key: {score, justification, evidence_quote,
    # evidence_found}}, feedback, total, model, prompt_version, version}
    ai_result: Mapped[dict | None] = mapped_column(JSONB)
    ai_error: Mapped[str | None] = mapped_column(String(500))
    final_scores: Mapped[dict | None] = mapped_column(JSONB)  # {key: điểm} giảng viên xác nhận
    final_total: Mapped[float | None] = mapped_column(Float)
    teacher_feedback: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
