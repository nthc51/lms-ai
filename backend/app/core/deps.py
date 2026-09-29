import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.modules.auth.models import User

_bearer = HTTPBearer(auto_error=False)


async def _user_from_token(token: str, db: AsyncSession) -> User:
    payload = decode_access_token(token)
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise AppError("INVALID_TOKEN", "Token không hợp lệ", 401)
    if user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    return user


async def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                           db: AsyncSession = Depends(get_db)) -> User:
    if cred is None:
        raise AppError("NOT_AUTHENTICATED", "Bạn cần đăng nhập", 401)
    return await _user_from_token(cred.credentials, db)


async def get_optional_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                            db: AsyncSession = Depends(get_db)) -> User | None:
    """Không có token thì trả None. Token có nhưng sai hoặc hết hạn thì vẫn báo 401 để frontend refresh."""
    if cred is None:
        return None
    return await _user_from_token(cred.credentials, db)
