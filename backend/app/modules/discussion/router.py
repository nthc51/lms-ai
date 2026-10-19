import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pagination import PageParams, page_params
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.modules.auth.models import User
from app.modules.discussion import service
from app.modules.discussion.schemas import CommentIn, CommentOut, CommentPage
from app.modules.inbox.hub import NotificationHub, get_hub

router = APIRouter(prefix="/api/v1", tags=["discussion"])


@router.get("/lessons/{lesson_id}/comments", response_model=CommentPage)
async def lesson_comments(
    lesson_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Thảo luận của bài: bình luận gốc mới nhất trước, mỗi cái kèm các trả lời. 403 NOT_ENROLLED / 404 như bài học."""
    return await service.list_threads(db, user, lesson_id, params)


@router.post("/lessons/{lesson_id}/comments", response_model=CommentOut, status_code=201)
async def post_comment(
    lesson_id: uuid.UUID,
    data: CommentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
    hub: NotificationHub = Depends(get_hub),
):
    """Hỏi mới (không có parent_id) hoặc trả lời một bình luận gốc. 422 INVALID_PARENT khi trả lời một câu trả
    lời; 409 COMMENT_DELETED; 429 RATE_LIMITED (30 bình luận/giờ/người)."""
    return await service.create_comment(db, limiter, hub, user, lesson_id, data)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Xóa mềm: tác giả, giảng viên của khóa hoặc admin. Người khác nhận 404."""
    await service.delete_comment(db, user, comment_id)
