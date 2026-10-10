"""Readiness: service có dùng được không (khác /health chỉ báo tiến trình còn sống)."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.storage import Storage, get_storage

router = APIRouter(prefix="/api/v1", tags=["health"])

CHECK_TIMEOUT_S = 2.0
RedisPing = Callable[[], Awaitable[None]]


def get_redis_ping() -> RedisPing:
    async def ping() -> None:
        r = Redis.from_url(get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1)
        try:
            await r.ping()
        finally:
            await r.aclose()

    return ping


@router.get("/ready")
async def ready(
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
    redis_ping: RedisPing = Depends(get_redis_ping),
) -> JSONResponse:
    async def check_db() -> None:
        await db.execute(text("SELECT 1"))

    checks: dict[str, str] = {}
    for name, fn in (("db", check_db), ("redis", redis_ping), ("storage", storage.ping)):
        try:
            await asyncio.wait_for(fn(), timeout=CHECK_TIMEOUT_S)
            checks[name] = "ok"
        except Exception as e:  # noqa: BLE001 — mọi lỗi đều nghĩa là chưa sẵn sàng
            checks[name] = f"error: {type(e).__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503
    )
