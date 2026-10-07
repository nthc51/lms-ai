import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class TeacherStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    # Email luôn được lưu dạng chữ thường, nên UNIQUE thường cũng chặn được trùng hoa/thường,
    # kể cả khi có ai insert thẳng vào DB bằng script. (Dùng CHECK thay cho index LOWER(email) vì
    # Alembic autogenerate so sánh index biểu thức không ổn định, dễ sinh migration thừa.)
    __table_args__ = (CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    avatar_key: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="user_role"))
    teacher_status: Mapped[TeacherStatus | None] = mapped_column(SAEnum(TeacherStatus, name="teacher_status"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Lý do quản trị viên ghi khi từ chối giảng viên hoặc khóa tài khoản (hiện cho chính người dùng).
    review_note: Mapped[str | None] = mapped_column(String(500))

    # NULL = chưa bấm link xác nhận email (không đăng nhập được khi EMAIL_VERIFICATION_REQUIRED=true).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class RefreshToken(IdMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailToken(IdMixin, TimestampMixin, Base):
    """Token một lần gửi qua email (hiện chỉ dùng để xác nhận email). Chỉ lưu hash, giống refresh token."""

    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))  # verify_email
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
