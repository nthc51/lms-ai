import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class Difficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class QuestionOrigin(str, enum.Enum):
    ai = "ai"
    manual = "manual"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"


class QuizStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    timed_out = "timed_out"


# Chỉ câu đã duyệt (giữ nguyên hoặc đã sửa) mới được đưa vào quiz
USABLE_REVIEW = (ReviewStatus.approved, ReviewStatus.edited)


class Question(IdMixin, TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_lesson_review", "lesson_id", "review_status"),)

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[list[dict]] = mapped_column(JSONB)  # [{id, text}], id luôn là A–D
    correct_option_id: Mapped[str] = mapped_column(String(8))
    explanation: Mapped[str] = mapped_column(Text, default="", server_default="")
    difficulty: Mapped[Difficulty] = mapped_column(SAEnum(Difficulty, name="question_difficulty"))
    origin: Mapped[QuestionOrigin] = mapped_column(SAEnum(QuestionOrigin, name="question_origin"))
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), index=True
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="review_status"), default=ReviewStatus.pending
    )
    self_check_flag: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    ai_original: Mapped[dict | None] = mapped_column(JSONB)  # bản AI sinh ra, không bao giờ bị sửa
    prompt_version: Mapped[str | None] = mapped_column(String(80))


class Quiz(IdMixin, TimestampMixin, Base):
    __tablename__ = "quizzes"

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    time_limit_sec: Mapped[int | None] = mapped_column(Integer)  # B1 (tuần 3), A7 chưa dùng
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # B1
    pass_score: Mapped[float] = mapped_column(Float, default=50.0)  # phần trăm
    status: Mapped[QuizStatus] = mapped_column(
        SAEnum(QuizStatus, name="quiz_status"), default=QuizStatus.draft
    )


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer)


class QuizAttempt(IdMixin, TimestampMixin, Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        UniqueConstraint("quiz_id", "user_id", "attempt_no", name="uq_quiz_attempts_quiz_user_no"),
    )

    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    question_order: Mapped[list[str]] = mapped_column(JSONB)  # id câu hỏi (chuỗi) theo thứ tự hiển thị
    status: Mapped[AttemptStatus] = mapped_column(
        SAEnum(AttemptStatus, name="attempt_status"), default=AttemptStatus.in_progress
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # B1
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)  # phần trăm, làm tròn 2 chữ số


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    selected_option_id: Mapped[str] = mapped_column(String(8))
    is_correct: Mapped[bool | None] = mapped_column(Boolean)  # ghi lúc chốt bài
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ai_explanation: Mapped[str | None] = mapped_column(Text)  # B3
