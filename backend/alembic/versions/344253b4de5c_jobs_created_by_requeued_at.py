"""jobs created_by requeued_at

Revision ID: 344253b4de5c
Revises: 59f0a33a0060
Create Date: 2026-09-29 16:26:04.931360

"""

from collections.abc import Sequence

import pgvector.sqlalchemy  # noqa: F401
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "344253b4de5c"
down_revision: str | Sequence[str] | None = "59f0a33a0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("jobs", sa.Column("created_by", sa.Uuid(), nullable=True))
    op.add_column("jobs", sa.Column("requeued_at", sa.DateTime(timezone=True), nullable=True))
    # Đặt tên theo quy ước mặc định của PostgreSQL để downgrade drop được
    op.create_foreign_key(
        "jobs_created_by_fkey", "jobs", "users", ["created_by"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("jobs_created_by_fkey", "jobs", type_="foreignkey")
    op.drop_column("jobs", "requeued_at")
    op.drop_column("jobs", "created_by")
