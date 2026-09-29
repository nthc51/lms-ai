from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, hash_refresh_token, new_refresh_token, verify_password
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


async def refresh(db: AsyncSession, raw: str) -> tuple[str, str]:
    token = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)).with_for_update()
    )
    if token is None:
        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
    if token.revoked_at is not None:
        # Token đã bị xoay mà vẫn có người dùng lại, coi như bị đánh cắp: thu hồi toàn bộ phiên của user.
        await db.execute(update(RefreshToken)
                         .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
                         .values(revoked_at=utcnow()))
        await db.commit()
        raise AppError("TOKEN_REUSED", "Phiên đăng nhập đã bị thu hồi, vui lòng đăng nhập lại", 401)
    if token.expires_at <= utcnow():
        raise AppError("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn", 401)
    user = await db.get(User, token.user_id)
    if user is None or user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    token.revoked_at = utcnow()
    return await issue_tokens(db, user)


async def logout(db: AsyncSession, raw: str) -> None:
    token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
    if token is not None and token.revoked_at is None:
        token.revoked_at = utcnow()
        await db.commit()
