"""Thông báo trong app (B6): tạo, đọc, đánh dấu đã đọc, và luồng SSE báo số chưa đọc theo thời gian thực.

Cách dùng ở module khác: gọi `add(...)` trước khi commit (thông báo vào cùng transaction với việc gây ra nó),
commit xong thì `await hub.publish(ids)` để các tab đang mở cập nhật ngay."""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import SessionLocal
from app.core.errors import not_found
from app.core.pagination import PageParams, paginate
from app.core.time import utcnow
from app.modules.inbox.hub import NotificationHub
from app.modules.inbox.models import Notification, NotificationKind
from app.modules.inbox.schemas import NotificationOut, NotificationPage

logger = logging.getLogger(__name__)

HEARTBEAT_S = 25.0  # giữ kết nối qua proxy (Caddy, Nginx) và đọc lại số chưa đọc nếu lỡ mất tín hiệu


def add(
    db: AsyncSession,
    user_ids: list[uuid.UUID],
    kind: NotificationKind,
    title: str,
    link: str,
    body: str = "",
) -> list[str]:
    """Thêm thông báo cho từng người (bỏ trùng), CHƯA commit. Trả id người nhận dạng chuỗi để publish sau commit."""
    ids = list(dict.fromkeys(u for u in user_ids if u))
    db.add_all(
        Notification(user_id=uid, kind=kind.value, title=title[:200], body=body[:500], link=link)
        for uid in ids
    )
    return [str(u) for u in ids]


async def publish(hub: NotificationHub, user_ids: list[str]) -> None:
    """Phát tín hiệu sau commit. Không bao giờ ném lỗi: thông báo đã an toàn trong DB."""
    if not user_ids:
        return
    try:
        await hub.publish(user_ids)
    except Exception:
        logger.warning("Không phát được tín hiệu thông báo", exc_info=True)


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        link=n.link,
        read=n.read_at is not None,
        created_at=n.created_at,
    )


async def list_for(db: AsyncSession, user_id: uuid.UUID, params: PageParams) -> NotificationPage:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    total, paged = await paginate(db, stmt, params)
    items = [_out(n) for n in (await db.scalars(paged)).all()]
    return NotificationPage(
        items=items, total=total, page=params.page, size=params.size, unread=await unread_count(db, user_id)
    )


async def mark_read(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    """Thông báo của người khác trả 404 như không tồn tại."""
    n = await db.get(Notification, notification_id)
    if n is None or n.user_id != user_id:
        raise not_found("Thông báo")
    if n.read_at is None:
        n.read_at = utcnow()
        await db.commit()


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    await db.commit()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class _NoSignal:
    """Redis không dùng được: không có tín hiệu, luồng tự đọc lại số chưa đọc mỗi nhịp HEARTBEAT_S."""

    async def wait(self, timeout: float) -> bool:
        import asyncio

        await asyncio.sleep(timeout)
        return False


@asynccontextmanager
async def _subscribe(hub: NotificationHub, user_id: str):
    try:
        cm = hub.subscribe(user_id)
        sub = await cm.__aenter__()
    except (RedisError, OSError):
        logger.warning("Không đăng ký được kênh thông báo, chuyển sang đọc lại định kỳ", exc_info=True)
        yield _NoSignal()
        return
    try:
        yield sub
    finally:
        await cm.__aexit__(None, None, None)


async def notification_events(
    user_id: uuid.UUID,
    hub: NotificationHub,
    *,
    is_disconnected: Callable[[], Awaitable[bool]],
    session_factory: async_sessionmaker = SessionLocal,
    heartbeat_s: float = HEARTBEAT_S,
) -> AsyncIterator[str]:
    """Luồng SSE: gửi `unread` {unread, latest} ngay khi mở và mỗi khi số chưa đọc đổi; giữa chừng gửi dòng
    chú thích `: ping` để giữ kết nối. Mỗi lần đọc DB mở session riêng: không giữ connection suốt luồng."""

    async def snapshot() -> dict:
        async with session_factory() as db:
            count = await unread_count(db, user_id)
            latest = await db.scalar(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(1)
            )
            return {"unread": count, "latest": _out(latest).model_dump(mode="json") if latest else None}

    async with _subscribe(
        hub, str(user_id)
    ) as sub:  # đăng ký trước khi đọc: không lỡ thông báo đến giữa chừng
        last = await snapshot()
        yield _sse("unread", last)
        while not await is_disconnected():
            signalled = await sub.wait(heartbeat_s)
            current = await snapshot()
            if signalled or current["unread"] != last["unread"]:
                last = current
                yield _sse("unread", current)
            else:
                yield ": ping\n\n"
