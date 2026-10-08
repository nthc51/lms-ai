"""ai studio: ai_calls, source_guides, study_artifacts, flashcard_reviews, notes, chat_messages.followups

Revision ID: e3b8c1f4a902
Revises: d7a4b9c2e615
Create Date: 2026-10-08 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e3b8c1f4a902"
down_revision: str | Sequence[str] | None = "d7a4b9c2e615"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum dùng chung cho 3 bảng: tạo một lần, các cột tham chiếu với create_type=False.
STUDIO_STATUS = postgresql.ENUM("generating", "ready", "failed", name="studio_status", create_type=False)
ARTIFACT_KIND = postgresql.ENUM(
    "study_guide", "briefing", "faq", "timeline", "flashcards", name="artifact_kind", create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    STUDIO_STATUS.create(op.get_bind(), checkfirst=True)
    ARTIFACT_KIND.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ai_calls",
        sa.Column("op", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_calls_created", "ai_calls", ["created_at"], unique=False)
    op.create_table(
        "study_artifacts",
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=True),
        sa.Column("kind", ARTIFACT_KIND, nullable=False),
        sa.Column("status", STUDIO_STATUS, nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("cards", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_study_artifacts_scope",
        "study_artifacts",
        ["course_id", "lesson_id", "kind", "created_at"],
        unique=False,
    )
    op.create_table(
        "flashcard_reviews",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("card_no", sa.Integer(), nullable=False),
        sa.Column("known", sa.Boolean(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["study_artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "artifact_id", "card_no"),
    )
    op.create_table(
        "source_guides",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", STUDIO_STATUS, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "topics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "questions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_table(
        "notes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("from_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", STUDIO_STATUS, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_user_course", "notes", ["user_id", "course_id", "updated_at"], unique=False)
    op.add_column(
        "chat_messages", sa.Column("followups", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_messages", "followups")
    op.drop_index("ix_notes_user_course", table_name="notes")
    op.drop_table("notes")
    op.drop_table("source_guides")
    op.drop_table("flashcard_reviews")
    op.drop_index("ix_study_artifacts_scope", table_name="study_artifacts")
    op.drop_table("study_artifacts")
    op.drop_index("ix_ai_calls_created", table_name="ai_calls")
    op.drop_table("ai_calls")
    ARTIFACT_KIND.drop(op.get_bind(), checkfirst=True)
    STUDIO_STATUS.drop(op.get_bind(), checkfirst=True)
