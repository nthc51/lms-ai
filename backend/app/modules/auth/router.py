from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginIn,
    RegisterIn,
    ResendVerificationIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)
from app.modules.notify.outbox import MailKicker, get_mail_kicker

router = APIRouter(prefix="/api/v1", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
        path=REFRESH_PATH,
        max_age=s.refresh_token_days * 86400,
    )


@router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(
    data: RegisterIn, db: AsyncSession = Depends(get_db), kicker: MailKicker = Depends(get_mail_kicker)
):
    """Tạo tài khoản và gửi email xác nhận. Chưa xác nhận thì đăng nhập nhận 403 EMAIL_NOT_VERIFIED."""
    user = await service.register(db, data)
    await kicker.kick()
    return user


@router.post("/auth/verify-email", response_model=UserOut)
async def verify_email(
    data: VerifyEmailIn, db: AsyncSession = Depends(get_db), kicker: MailKicker = Depends(get_mail_kicker)
):
    """400 INVALID_TOKEN (sai / đã thay bằng link mới) hoặc TOKEN_EXPIRED. Bấm lại link đã dùng thì vẫn 200."""
    user = await service.verify_email(db, data.token)
    await kicker.kick()  # giảng viên vừa xác nhận: báo admin
    return user


RESEND_LIMIT = 3  # mỗi email tối đa 3 lần / giờ


@router.post("/auth/resend-verification", status_code=202)
async def resend_verification(
    data: ResendVerificationIn,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
    kicker: MailKicker = Depends(get_mail_kicker),
) -> dict:
    """Luôn 202 (không lộ email nào đã đăng ký). 429 RATE_LIMITED khi gửi quá 3 lần mỗi giờ cho một email."""
    wait = await limiter.hit(f"verify-resend:{data.email}", RESEND_LIMIT, 3600)
    if wait is not None:
        raise AppError(
            "RATE_LIMITED",
            "Bạn đã yêu cầu gửi lại quá nhiều lần, vui lòng thử lại sau",
            429,
            {"retry_after": wait},
            headers={"Retry-After": str(wait)},
        )
    if await service.resend_verification(db, data.email):
        await kicker.kick()
    return {"status": "accepted"}


@router.post("/me/teacher-request", response_model=UserOut)
async def request_teacher_review(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    """Giảng viên bị từ chối gửi lại yêu cầu duyệt. 409 NOT_REJECTED nếu không ở trạng thái bị từ chối."""
    user = await service.request_teacher_review(db, user)
    await kicker.kick()
    return user


@router.post("/auth/login", response_model=TokenOut)
async def login(data: LoginIn, response: Response, db: AsyncSession = Depends(get_db)):
    access, raw = await service.login(db, data)
    set_refresh_cookie(response, raw)
    return TokenOut(access_token=access)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/refresh", response_model=TokenOut)
async def refresh(
    response: Response, refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)
):
    if not refresh_token:
        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
    access, raw = await service.refresh(db, refresh_token)
    set_refresh_cookie(response, raw)
    return TokenOut(access_token=access)


@router.post("/auth/logout", status_code=204)
async def logout(refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    if refresh_token:
        await service.logout(db, refresh_token)
    resp = Response(status_code=204)
    resp.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    return resp
