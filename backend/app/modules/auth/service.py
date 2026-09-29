from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, new_refresh_token, verify_password
from app.core.time import utcnow
from app.modules.auth.models import RefreshToken, Role, TeacherStatus, User
from app.modules.auth.schemas import LoginIn, RegisterIn


async def register(db: AsyncSession, data: RegisterIn) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise AppError("EMAIL_TAKEN", "Email đã được sử dụng", 409)
    role = Role(data.role)
    user = User(email=email, password_hash=hash_password(data.password), full_name=data.full_name,
                role=role, teacher_status=TeacherStatus.pending if role == Role.teacher else None)
    db.add(user)
    await db.commit()
    return user


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    """Trả về (access_token, refresh_token_raw). Commit luôn cả các thay đổi đang chờ trong session."""
    raw, hashed = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hashed,
                        expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days)))
    await db.commit()
    return create_access_token(user.id, user.role.value), raw


async def login(db: AsyncSession, data: LoginIn) -> tuple[str, str]:
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng", 401)
    if user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    return await issue_tokens(db, user)
