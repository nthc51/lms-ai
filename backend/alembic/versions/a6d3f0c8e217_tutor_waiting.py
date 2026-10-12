"""chat_messages.waiting_for_docs: câu hỏi gửi lúc tài liệu đang xử lý, AI trả lời khi xử lý xong

Revision ID: a6d3f0c8e217
Revises: f4c2a7d91b35
Create Date: 2026-10-12 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6d3f0c8e217"
down_revision: str | Sequence[str] | None = "f4c2a7d91b35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat_messages",
        sa.Column("waiting_for_docs", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Worker chỉ quét các câu đang chờ: index một phần, gần như rỗng
    op.create_index(
        "ix_chat_messages_waiting",
        "chat_messages",
        ["created_at"],
        postgresql_where=sa.text("waiting_for_docs"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chat_messages_waiting", table_name="chat_messages")
    op.drop_column("chat_messages", "waiting_for_docs")
