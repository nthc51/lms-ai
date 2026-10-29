"""assignments, submissions (B5 bài tập: rubric, bài nộp, điểm AI gợi ý và điểm giảng viên xác nhận)

Revision ID: d8f1a3b6c920
Revises: c5a8e2f9d104
Create Date: 2026-10-29 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8f1a3b6c920"
down_revision: str | Sequence[str] | None = "c5a8e2f9d104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Enum("draft", "published", name="assignment_status"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assignments_lesson_id"), "assignments", ["lesson_id"], unique=False)
    op.create_table(
        "submissions",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("text_content", sa.Text(), server_default="", nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("submitted", "ai_graded", "ai_failed", "graded", name="submission_status"),
            nullable=False,
        ),
        sa.Column("ai_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ai_error", sa.String(length=500), nullable=True),
        sa.Column("final_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("final_total", sa.Float(), nullable=True),
        sa.Column("teacher_feedback", sa.Text(), nullable=True),
        sa.Column("graded_by", sa.Uuid(), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["graded_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "user_id", name="uq_submissions_assignment_user"),
    )
    op.create_index(
        "ix_submissions_assignment_status", "submissions", ["assignment_id", "status"], unique=False
    )
    op.create_index(op.f("ix_submissions_user_id"), "submissions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_submissions_user_id"), table_name="submissions")
    op.drop_index("ix_submissions_assignment_status", table_name="submissions")
    op.drop_table("submissions")
    op.drop_index(op.f("ix_assignments_lesson_id"), table_name="assignments")
    op.drop_table("assignments")
    sa.Enum(name="submission_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="assignment_status").drop(op.get_bind(), checkfirst=True)
