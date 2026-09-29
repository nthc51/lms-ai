import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError, forbidden
from app.core.security import decode_access_token
from app.modules.auth.models import Role, TeacherStatus, User

_bearer = HTTPBearer(auto_error=False)


async def _user_from_token(token: str, db: AsyncSession) -> User:
    payload = decode_access_token(token)
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise AppError("INVALID_TOKEN", "Token không hợp lệ", 401)
    if user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    return user


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: AsyncSession = Depends(get_db)
) -> User:
    if cred is None:
        raise AppError("NOT_AUTHENTICATED", "Bạn cần đăng nhập", 401)
    return await _user_from_token(cred.credentials, db)


async def get_optional_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: AsyncSession = Depends(get_db)
) -> User | None:
    """Không có token thì trả None. Token có nhưng sai hoặc hết hạn thì vẫn báo 401 để frontend refresh."""
    if cred is None:
        return None
    return await _user_from_token(cred.credentials, db)


def require_role(*roles: Role):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise forbidden()
        return user

    return dependency


def _ensure_approved(user: User) -> None:
    if user.teacher_status != TeacherStatus.approved:
        raise AppError("TEACHER_NOT_APPROVED", "Tài khoản giảng viên chưa được duyệt", 403)


async def require_teacher_approved(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.teacher:
        raise forbidden()
    _ensure_approved(user)
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    """Giảng viên đã được duyệt hoặc admin."""
    if user.role == Role.admin:
        return user
    if user.role == Role.teacher:
        _ensure_approved(user)
        return user
    raise forbidden()
