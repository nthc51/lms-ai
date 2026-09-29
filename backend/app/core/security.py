import hashlib
import secrets
import uuid
from datetime import timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utcnow

_pwd = PasswordHash.recommended()  # argon2


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd.verify(password, hashed)


def create_access_token(user_id: uuid.UUID, role: str, expires_minutes: int | None = None) -> str:
    s = get_settings()
    minutes = s.access_token_minutes if expires_minutes is None else expires_minutes
    payload = {"sub": str(user_id), "role": role, "type": "access",
               "exp": utcnow() + timedelta(minutes=minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AppError("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn", 401) from None
    except jwt.InvalidTokenError:
        raise AppError("INVALID_TOKEN", "Token không hợp lệ", 401) from None
    if payload.get("type") != "access":
        raise AppError("INVALID_TOKEN", "Token không hợp lệ", 401)
    return payload


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)
