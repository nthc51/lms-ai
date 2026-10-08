from fastapi import APIRouter, Cookie, Depends, Request, Response
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


REGISTER_IP_LIMIT = 20  # mỗi IP tối đa 20 lần đăng ký / giờ (mỗi lần đăng ký gửi một email)
RESEND_LIMIT = 3  # mỗi email tối đa 3 lần / giờ
RESEND_IP_LIMIT = 10  # mỗi IP tối đa 10 lần / giờ (chặn spam nhiều email khác nhau)


def _too_many(wait: int) -> AppError:
    return AppError(
        "RATE_LIMITED",
        "Bạn thao tác quá nhiều lần, vui lòng thử lại sau",
        429,
        {"retry_after": wait},
        headers={"Retry-After": str(wait)},
    )


async def _limit(limiter: RateLimiter, key: str, limit: int, window_s: int = 3600) -> None:
    wait = await limiter.hit(key, limit, window_s)
    if wait is not None:
        raise _too_many(wait)


def _ip(request: Request) -> str:
    # Sau reverse proxy (Caddy ở tầng S) cần chạy uvicorn với --proxy-headers để đây là IP thật.
    return request.client.host if request.client else "unknown"


@router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(
    data: RegisterIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    """Tạo tài khoản và gửi email xác nhận. Chưa xác nhận thì đăng nhập nhận 403 EMAIL_NOT_VERIFIED.
    429 RATE_LIMITED khi một IP đăng ký quá 20 lần / giờ."""
    await _limit(limiter, f"register-ip:{_ip(request)}", REGISTER_IP_LIMIT)
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


@router.post("/auth/resend-verification", status_code=202)
async def resend_verification(
    data: ResendVerificationIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
    kicker: MailKicker = Depends(get_mail_kicker),
) -> dict:
    """Luôn 202 (không lộ email nào đã đăng ký). 429 RATE_LIMITED khi quá 3 lần/giờ cho một email
    hoặc quá 10 lần/giờ từ một IP."""
    await _limit(limiter, f"verify-resend-ip:{_ip(request)}", RESEND_IP_LIMIT)
    await _limit(limiter, f"verify-resend:{data.email}", RESEND_LIMIT)
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
async def login(
    data: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    """429 RATE_LIMITED khi một IP gọi quá LOGIN_RATE_LIMIT_PER_MIN lần / phút (tính cả lần sai mật khẩu)."""
    await _limit(limiter, f"login-ip:{_ip(request)}", get_settings().login_rate_limit_per_min, 60)
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
