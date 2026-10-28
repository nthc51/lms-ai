"""refresh_tokens.rotated_at: chỉ token bị xoay mới coi là bị đánh cắp khi dùng lại

Revision ID: c5a8e2f9d104
Revises: b9e1d4c7a352
Create Date: 2026-10-28 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5a8e2f9d104"
down_revision: str | Sequence[str] | None = "b9e1d4c7a352"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))
    # Không biết token đã thu hồi trước đây bị thu hồi vì lý do gì: coi như bị xoay để giữ cách phát hiện cũ.
    op.execute("UPDATE refresh_tokens SET rotated_at = revoked_at WHERE revoked_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("refresh_tokens", "rotated_at")
