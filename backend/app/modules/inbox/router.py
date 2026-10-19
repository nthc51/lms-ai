import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pagination import PageParams, page_params
from app.modules.auth.models import User
from app.modules.inbox import service
from app.modules.inbox.hub import NotificationHub, get_hub
from app.modules.inbox.schemas import NotificationPage, UnreadOut

router = APIRouter(prefix="/api/v1", tags=["notifications"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/me/notifications", response_model=NotificationPage)
async def my_notifications(
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Thông báo của tôi, mới nhất trước, kèm tổng số chưa đọc."""
    return await service.list_for(db, user.id, params)


@router.get("/me/notifications/unread", response_model=UnreadOut)
async def my_unread(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return UnreadOut(unread=await service.unread_count(db, user.id))


@router.post("/me/notifications/{notification_id}/read", status_code=204)
async def read_one(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await service.mark_read(db, user.id, notification_id)


@router.post("/me/notifications/read-all", status_code=204)
async def read_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await service.mark_all_read(db, user.id)


@router.get(
    "/me/notifications/stream",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE: unread {unread, latest} và : ping"}
    },
)
async def notification_stream(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    hub: NotificationHub = Depends(get_hub),
):
    """Số thông báo chưa đọc theo thời gian thực (frontend đọc bằng fetch vì cần header Authorization). Token
    chỉ được kiểm lúc mở luồng; mất kết nối thì frontend tự mở lại (có refresh token nếu cần)."""
    # Trả connection về pool ngay: luồng sống nhiều phút, mỗi lần đọc DB tự mở session ngắn của riêng nó.
    await db.close()
    return StreamingResponse(
        service.notification_events(user.id, hub, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
