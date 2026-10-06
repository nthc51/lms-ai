import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class AdminAction(IdMixin, TimestampMixin, Base):
    """Nhật ký thao tác quản trị (ai, làm gì, với đối tượng nào, lý do). Chỉ thêm, không sửa."""

    __tablename__ = "admin_actions"
    __table_args__ = (Index("ix_admin_actions_created", "created_at"),)

    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40))  # approve_teacher | reject_teacher | lock_user | ...
    target_type: Mapped[str] = mapped_column(String(20))  # user | course
    target_id: Mapped[uuid.UUID] = mapped_column()
    target_label: Mapped[str] = mapped_column(String(255))  # email hoặc tên khóa lúc thao tác
    note: Mapped[str | None] = mapped_column(Text)
