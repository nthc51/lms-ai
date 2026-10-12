"""Câu hỏi chờ tài liệu: học viên hỏi lúc tài liệu còn đang xử lý, AI trả lời ngay khi xử lý xong.

Luồng:
1. API `POST /tutor/sessions/{id}/questions` (queue_question): chỉ nhận khi phạm vi chưa có chunk nào và còn
   tài liệu đang xử lý; lưu câu hỏi với waiting_for_docs = true (tính lượt rate limit như câu hỏi thường).
2. Worker xử lý PDF xong (thành công hay lỗi) thì xếp job `tutor_waiting` cho bài đó; cron 5 phút vét phần sót.
3. answer_waiting: nhận từng câu (UPDATE có điều kiện, nên job và cron chạy song song không trả lời hai lần),
   kiểm quyền lại, chạy đúng luồng trả lời của AI Tutor (answer_stream) và lưu câu trả lời ngay sau câu hỏi.
   Tài liệu xử lý lỗi hết (không còn gì để đọc) thì trả lời bằng một thông báo thay vì để câu hỏi chờ mãi."""

import logging
import time
import uuid
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.llm_client import LLMClient
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.ratelimit import RateLimiter, rate_limited
from app.modules.auth.models import Role, User
from app.modules.courses.models import CourseStatus, Lesson, Section
from app.modules.tutor.answer import AskContext, answer_stream
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from app.modules.tutor.service import (
    RATE_WINDOW_S,
    get_own_session,
    load_history,
    resolve_scope,
    scope_of,
)
from app.modules.tutor.state import describe, scope_state

logger = logging.getLogger(__name__)

MAX_WAITING_PER_SESSION = 5
DOCS_FAILED_ANSWER = (
    "Tài liệu của bài này xử lý không thành công nên AI chưa trả lời được câu hỏi này. "
    "Bạn hãy hỏi lại sau khi giảng viên tải lại tài liệu."
)


async def queue_question(
    db: AsyncSession,
    limiter: RateLimiter,
    user: User,
    session_id: uuid.UUID,
    question: str,
    embedding_model: str,
) -> ChatMessage:
    """Kiểm quyền như câu hỏi thường, rồi chỉ nhận khi trạng thái là 'processing' (409 nếu không), tối đa
    MAX_WAITING_PER_SESSION câu chờ mỗi phiên. Rate limit đứng sau các kiểm tra: bị từ chối thì không tốn lượt."""
    session = await get_own_session(db, session_id, user)
    course, lesson = await resolve_scope(db, user, session.course_id, session.lesson_id)
    st = await scope_state(db, scope_of(session), embedding_model)
    info = describe(st, draft_course_scope=lesson is None and course.status != CourseStatus.published)
    if info.state == "ready":
        raise AppError("TUTOR_READY", "Tài liệu đã sẵn sàng, hãy hỏi trực tiếp", 409)
    if not info.can_queue:
        raise AppError("NOT_PROCESSING", info.message or "Chưa hỏi được AI Tutor", 409)
    waiting = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == session.id, ChatMessage.waiting_for_docs
        )
    )
    if waiting >= MAX_WAITING_PER_SESSION:
        raise AppError(
            "TOO_MANY_WAITING",
            f"Bạn đã có {MAX_WAITING_PER_SESSION} câu hỏi đang chờ, hãy đợi tài liệu xử lý xong",
            409,
        )
    if user.role == Role.student:
        retry_after = await limiter.hit(
            f"tutor:{user.id}", get_settings().tutor_rate_limit_per_hour, RATE_WINDOW_S
        )
        if retry_after is not None:
            raise rate_limited(retry_after)
    message = ChatMessage(session_id=session.id, role=ChatRole.user, content=question, waiting_for_docs=True)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


def _waiting_in_lesson(lesson_id: uuid.UUID):
    """Câu chờ có thể được trả lời khi tài liệu của bài này xử lý xong: phiên theo bài này, hoặc phiên theo cả
    khóa chứa bài này."""
    course_of_lesson = (
        select(Section.course_id)
        .join(Lesson, Lesson.section_id == Section.id)
        .where(Lesson.id == lesson_id)
        .scalar_subquery()
    )
    return or_(
        ChatSession.lesson_id == lesson_id,
        (ChatSession.lesson_id.is_(None)) & (ChatSession.course_id == course_of_lesson),
    )


async def has_waiting(db: AsyncSession, lesson_id: uuid.UUID) -> bool:
    stmt = (
        select(ChatMessage.id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.waiting_for_docs, _waiting_in_lesson(lesson_id))
        .limit(1)
    )
    return await db.scalar(stmt) is not None


async def _never_disconnected() -> bool:
    return False


async def _answer_one(
    message_id: uuid.UUID,
    llm: LLMClient,
    embedder: Embedder,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> bool:
    """Trả lời một câu chờ. False = chưa đến lúc (tài liệu còn đang xử lý) hoặc đã có worker khác nhận."""
    async with session_factory() as db:
        row = (
            await db.execute(
                select(ChatSession, User)
                .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
                .join(User, User.id == ChatSession.user_id)
                .where(ChatMessage.id == message_id, ChatMessage.waiting_for_docs)
            )
        ).first()
        if row is None:
            return False
        session, user = row
        try:
            course, _ = await resolve_scope(db, user, session.course_id, session.lesson_id)
        except AppError:
            course = None  # mất quyền (bị hủy đăng ký, khóa bị gỡ publish...): bỏ câu chờ, không trả lời
        st = await scope_state(db, scope_of(session), embedder.model) if course is not None else None
        if st is not None and st.ready_chunks == 0 and st.processing_docs > 0:
            return False
        # Nhận câu hỏi bằng UPDATE có điều kiện: job và cron chạy song song cũng chỉ một bên trả lời
        claimed = (
            await db.execute(
                update(ChatMessage)
                .where(ChatMessage.id == message_id, ChatMessage.waiting_for_docs)
                .values(waiting_for_docs=False)
                .returning(ChatMessage.content, ChatMessage.created_at)
            )
        ).first()
        if claimed is None:
            return False
        question, asked_at = claimed
        history = await load_history(db, session.id, before=asked_at) if course is not None else []
        await db.commit()

    if course is None:
        logger.info("Bỏ câu hỏi chờ %s: người hỏi không còn quyền", message_id)
        return True
    if st.ready_chunks == 0:
        await _save_notice(session_factory, session.id, asked_at, DOCS_FAILED_ANSWER)
        return True
    ctx = AskContext(
        session_id=session.id,
        scope=scope_of(session),
        course_title=course.title,
        question=question,
        history=history,
        answer_created_at=asked_at,
    )
    # Cùng luồng với câu hỏi trực tiếp (viết lại câu hỏi, tìm tài liệu, chốt chặn, lưu); không có client nên
    # chỉ chạy hết stream. Lỗi AI → answer_stream tự lưu câu trả lời dở (truncated) như mọi đường lỗi.
    async for _ in answer_stream(
        ctx,
        llm=llm,
        embedder=embedder,
        is_disconnected=_never_disconnected,
        session_factory=session_factory,
        settings=settings,
    ):
        pass
    return True


async def _save_notice(
    session_factory: async_sessionmaker, session_id: uuid.UUID, asked_at: datetime, text: str
) -> None:
    async with session_factory() as db:
        db.add(
            ChatMessage(
                session_id=session_id,
                role=ChatRole.assistant,
                content=text,
                refused=True,
                created_at=asked_at,
            )
        )
        await db.commit()


async def answer_waiting(
    llm: LLMClient,
    embedder: Embedder,
    *,
    lesson_id: uuid.UUID | None = None,
    session_factory: async_sessionmaker = SessionLocal,
    settings: Settings | None = None,
    budget_s: float | None = None,
) -> int:
    """Trả lời các câu chờ (cũ trước), trong một bài (job sau khi xử lý PDF) hoặc tất cả (cron). Trả về số câu
    đã xử lý. budget_s: hết thời gian thì dừng nhận câu mới (câu còn lại để lần sau), tránh job bị arq hủy giữa
    chừng. Lỗi ở một câu chỉ ghi log rồi làm câu tiếp theo."""
    s = settings or get_settings()
    stmt = (
        select(ChatMessage.id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.waiting_for_docs)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    if lesson_id is not None:
        stmt = stmt.where(_waiting_in_lesson(lesson_id))
    async with session_factory() as db:
        ids = list(await db.scalars(stmt))
    started = time.monotonic()
    done = 0
    for message_id in ids:
        if budget_s is not None and time.monotonic() - started > budget_s:
            break
        try:
            if await _answer_one(message_id, llm, embedder, session_factory, s):
                done += 1
        except Exception:
            logger.exception("Không trả lời được câu hỏi chờ %s", message_id)
    return done
