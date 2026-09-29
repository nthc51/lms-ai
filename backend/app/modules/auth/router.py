from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

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
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    return await service.register(db, data)


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
