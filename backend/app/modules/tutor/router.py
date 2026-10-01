import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedder import Embedder, get_api_embedder
from app.ai.llm_client import LLMClient, get_llm_client
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pagination import PageParams, page_params
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.modules.auth.models import User
from app.modules.tutor import service
from app.modules.tutor.answer import answer_stream
from app.modules.tutor.schemas import (
    AskIn,
    AvailabilityOut,
    FeedbackIn,
    MessageOut,
    MessagePage,
    SessionCreate,
    SessionOut,
    SessionPage,
)

router = APIRouter(prefix="/api/v1", tags=["tutor"])

# no-cache: proxy/trình duyệt không giữ lại; X-Accel-Buffering: nginx không gom buffer, token tới ngay
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/tutor/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    data: SessionCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.create_session(db, user, data)


@router.get("/tutor/sessions", response_model=SessionPage)
async def list_sessions(
    course_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_sessions(db, user, course_id, params)


@router.get("/tutor/availability", response_model=AvailabilityOut)
async def availability(
    course_id: uuid.UUID,
    lesson_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedder: Embedder = Depends(get_api_embedder),
):
    return await service.availability(db, user, course_id, lesson_id, embedder.model)


@router.get("/tutor/sessions/{session_id}/messages", response_model=MessagePage)
async def list_messages(
    session_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await service.get_own_session(db, session_id, user)
    return await service.list_messages(db, session, params)


@router.post(
    "/tutor/sessions/{session_id}/messages",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE: sources → token… → done | error"},
        429: {"description": "RATE_LIMITED (chỉ học viên), header Retry-After"},
    },
)
async def ask(
    session_id: uuid.UUID,
    data: AskIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(get_llm_client),
    embedder: Embedder = Depends(get_api_embedder),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    """Hỏi AI Tutor; trả lời stream SSE (frontend đọc bằng fetch + ReadableStream vì cần POST + Authorization).

    Lỗi trước khi mở stream là JSON lỗi bình thường: 404 (phiên của người khác / khóa bị gỡ publish), 403
    NOT_ENROLLED (bị hủy đăng ký), 422 (câu hỏi rỗng), 429 RATE_LIMITED + Retry-After. Câu hỏi được lưu và
    commit trước khi stream bắt đầu, nên vẫn còn dù LLM lỗi.

    Sau khi đã trả 200, mọi lỗi đi qua event `error` {code: "AI_UNAVAILABLE", message}. Frontend phải xử lý:
    - `error` có thể là event ĐẦU TIÊN (quá hạn chót trước khi có nguồn, tutor_prestream_deadline_s), không
      có `sources` trước đó;
    - sau `error` (hoặc khi mất kết nối) không có `done`, nhưng câu trả lời dở vẫn được lưu thành tin assistant
      `truncated = true` (nội dung có thể rỗng) — tải lại danh sách tin nhắn sẽ thấy dòng này."""
    ctx = await service.prepare_question(db, limiter, user, session_id, data.content)
    return StreamingResponse(
        answer_stream(ctx, llm=llm, embedder=embedder, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/tutor/messages/{message_id}/feedback", response_model=MessageOut)
async def feedback(
    message_id: uuid.UUID,
    data: FeedbackIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_feedback(db, user, message_id, data.value)
