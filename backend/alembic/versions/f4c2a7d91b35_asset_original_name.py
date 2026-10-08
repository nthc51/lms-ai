"""assets.original_name: tên file gốc để hiện tài liệu trong bài và tải về đúng tên

Revision ID: f4c2a7d91b35
Revises: e3b8c1f4a902
Create Date: 2026-10-08 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4c2a7d91b35"
down_revision: str | Sequence[str] | None = "e3b8c1f4a902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Chỉ thêm cột nullable: file tải lên trước đây vẫn hiện được (tên "Tài liệu N")
    op.add_column("assets", sa.Column("original_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assets", "original_name")
