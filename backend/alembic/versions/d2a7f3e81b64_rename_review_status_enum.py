"""rename enum review_status to question_review_status

Revision ID: d2a7f3e81b64
Revises: c47e2b9d5f10
Create Date: 2026-10-04 09:00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2a7f3e81b64"
down_revision: str | Sequence[str] | None = "c47e2b9d5f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Tên kiểu enum cụ thể theo bảng, tránh đụng tên chung 'review_status' khi thêm module khác."""
    op.execute("ALTER TYPE review_status RENAME TO question_review_status")


def downgrade() -> None:
    op.execute("ALTER TYPE question_review_status RENAME TO review_status")
