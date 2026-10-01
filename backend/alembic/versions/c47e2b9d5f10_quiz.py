"""quiz tables and jobs.payload

Revision ID: c47e2b9d5f10
Revises: 8a3f6d1c0b27
Create Date: 2026-10-02 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c47e2b9d5f10"
down_revision: str | Sequence[str] | None = "8a3f6d1c0b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("jobs", sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        "questions",
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correct_option_id", sa.String(length=8), nullable=False),
        sa.Column("explanation", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "difficulty", sa.Enum("easy", "medium", "hard", name="question_difficulty"), nullable=False
        ),
        sa.Column("origin", sa.Enum("ai", "manual", name="question_origin"), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=True),
        sa.Column(
            "review_status",
            sa.Enum("pending", "approved", "edited", "rejected", name="review_status"),
            nullable=False,
        ),
        sa.Column("self_check_flag", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ai_original", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questions_lesson_review", "questions", ["lesson_id", "review_status"], unique=False)
    op.create_index(op.f("ix_questions_source_chunk_id"), "questions", ["source_chunk_id"], unique=False)
    op.create_table(
        "quizzes",
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("time_limit_sec", sa.Integer(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("shuffle", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pass_score", sa.Float(), nullable=False),
        sa.Column("status", sa.Enum("draft", "published", name="quiz_status"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quizzes_lesson_id"), "quizzes", ["lesson_id"], unique=False)
    op.create_table(
        "quiz_questions",
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("quiz_id", "question_id"),
    )
    op.create_index(op.f("ix_quiz_questions_question_id"), "quiz_questions", ["question_id"], unique=False)
    op.create_table(
        "quiz_attempts",
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("question_order", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.Enum("in_progress", "completed", "timed_out", name="attempt_status"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quiz_id", "user_id", "attempt_no", name="uq_quiz_attempts_quiz_user_no"),
    )
    op.create_index(op.f("ix_quiz_attempts_user_id"), "quiz_attempts", ["user_id"], unique=False)
    op.create_table(
        "attempt_answers",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("selected_option_id", sa.String(length=8), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["attempt_id"], ["quiz_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("attempt_id", "question_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("attempt_answers")
    op.drop_index(op.f("ix_quiz_attempts_user_id"), table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index(op.f("ix_quiz_questions_question_id"), table_name="quiz_questions")
    op.drop_table("quiz_questions")
    op.drop_index(op.f("ix_quizzes_lesson_id"), table_name="quizzes")
    op.drop_table("quizzes")
    op.drop_index(op.f("ix_questions_source_chunk_id"), table_name="questions")
    op.drop_index("ix_questions_lesson_review", table_name="questions")
    op.drop_table("questions")
    op.drop_column("jobs", "payload")
    op.execute("DROP TYPE IF EXISTS attempt_status")
    op.execute("DROP TYPE IF EXISTS quiz_status")
    op.execute("DROP TYPE IF EXISTS review_status")
    op.execute("DROP TYPE IF EXISTS question_origin")
    op.execute("DROP TYPE IF EXISTS question_difficulty")
