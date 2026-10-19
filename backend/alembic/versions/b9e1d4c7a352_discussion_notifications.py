"""lesson_comments (B4 thảo luận theo bài) và notifications (B6 thông báo trong app)

Revision ID: b9e1d4c7a352
Revises: a6d3f0c8e217
Create Date: 2026-10-19 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9e1d4c7a352"
down_revision: str | Sequence[str] | None = "a6d3f0c8e217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lesson_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["lesson_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lesson_comments_lesson_created", "lesson_comments", ["lesson_id", "created_at"])
    op.create_index(op.f("ix_lesson_comments_parent_id"), "lesson_comments", ["parent_id"])
    op.create_index(op.f("ix_lesson_comments_user_id"), "lesson_comments", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), server_default="", nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])
    op.create_index(
        "ix_notifications_unread", "notifications", ["user_id"], postgresql_where=sa.text("read_at IS NULL")
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notifications_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_lesson_comments_user_id"), table_name="lesson_comments")
    op.drop_index(op.f("ix_lesson_comments_parent_id"), table_name="lesson_comments")
    op.drop_index("ix_lesson_comments_lesson_created", table_name="lesson_comments")
    op.drop_table("lesson_comments")
