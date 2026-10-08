"""review fixes: users.lock_reason, email_outbox.next_attempt_at

Revision ID: d7a4b9c2e615
Revises: c5d2e8f1a734
Create Date: 2026-10-07 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a4b9c2e615"
down_revision: str | Sequence[str] | None = "c5d2e8f1a734"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("lock_reason", sa.String(length=500), nullable=True))
    # Trước đây lý do khóa nằm chung review_note: chuyển sang cột mới (giữ lý do từ chối giảng viên).
    op.execute(
        "UPDATE users SET lock_reason = review_note, review_note = NULL "
        "WHERE locked_at IS NOT NULL AND teacher_status IS DISTINCT FROM 'rejected'"
    )
    op.add_column("email_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("email_outbox", "next_attempt_at")
    op.execute(
        "UPDATE users SET review_note = lock_reason WHERE lock_reason IS NOT NULL AND review_note IS NULL"
    )
    op.drop_column("users", "lock_reason")
