"""admin: users.review_note, courses.hidden_*, admin_actions

Revision ID: b81e4c7a2d90
Revises: d2a7f3e81b64
Create Date: 2026-10-07 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b81e4c7a2d90"
down_revision: str | Sequence[str] | None = "d2a7f3e81b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("review_note", sa.String(length=500), nullable=True))
    op.add_column("courses", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("courses", sa.Column("hidden_reason", sa.String(length=500), nullable=True))
    op.create_table(
        "admin_actions",
        sa.Column("admin_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("target_label", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_actions_created", "admin_actions", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_admin_actions_created", table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_column("courses", "hidden_reason")
    op.drop_column("courses", "hidden_at")
    op.drop_column("users", "review_note")
