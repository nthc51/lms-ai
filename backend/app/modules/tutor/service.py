import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval import SearchScope, count_ready_chunks
from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, CourseStatus, Lesson
from app.modules.enrollment.service import ensure_lesson_access, is_enrolled
from app.modules.tutor.models import ChatMessage, ChatSession
from app.modules.tutor.schemas import (
    AvailabilityOut,
    MessageOut,
    MessagePage,
    SessionCreate,
    SessionOut,
    SessionPage,
)

NOT_READY_MESSAGE = "Tài liệu đang được xử lý"


async def ensure_course_access(db: AsyncSession, course_id: uuid.UUID, user: User) -> Course:
    """Như ensure_lesson_access nhưng cho cả khóa: admin, giảng viên sở hữu, hoặc học viên đã đăng ký
    một khóa đã publish."""
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    if user.role == Role.admin or course.teacher_id == user.id:
        return course
    if course.status != CourseStatus.published:
        raise not_found("Khóa học")
    if not await is_enrolled(db, user.id, course.id):
        raise AppError("NOT_ENROLLED", "Bạn cần đăng ký khóa học để hỏi AI Tutor", 403)
    return course


async def resolve_scope(
    db: AsyncSession, user: User, course_id: uuid.UUID, lesson_id: uuid.UUID | None
) -> tuple[Course, Lesson | None]:
    if lesson_id is None:
        return await ensure_course_access(db, course_id, user), None
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    if course.id != course_id:
        raise not_found("Bài học")
    return course, lesson


def scope_of(session: ChatSession) -> SearchScope:
    return SearchScope(course_id=session.course_id, lesson_id=session.lesson_id)


async def create_session(db: AsyncSession, user: User, data: SessionCreate) -> ChatSession:
    course, lesson = await resolve_scope(db, user, data.course_id, data.lesson_id)
    session = ChatSession(user_id=user.id, course_id=course.id, lesson_id=lesson.id if lesson else None)
    db.add(session)
    await db.commit()
    return session


async def list_sessions(
    db: AsyncSession, user: User, course_id: uuid.UUID, params: PageParams
) -> SessionPage:
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user.id, ChatSession.course_id == course_id)
        .order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
    )
    total, paged = await paginate(db, stmt, params)
    items = [SessionOut.model_validate(s) for s in await db.scalars(paged)]
    return SessionPage(items=items, total=total, page=params.page, size=params.size)


async def get_own_session(db: AsyncSession, session_id: uuid.UUID, user: User) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise not_found("Phiên hỏi đáp")
    return session


# Tin nhắn user và assistant ghi trong cùng transaction có chung created_at (now() = đầu transaction) và id là
# uuid4, nên thứ tự phải thêm role: enum chat_role khai báo user < assistant, nên user đứng trước câu trả lời.
async def list_messages(db: AsyncSession, session: ChatSession, params: PageParams) -> MessagePage:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at, ChatMessage.role, ChatMessage.id)
    )
    total, paged = await paginate(db, stmt, params)
    items = [MessageOut.model_validate(m) for m in await db.scalars(paged)]
    return MessagePage(items=items, total=total, page=params.page, size=params.size)


async def availability(
    db: AsyncSession, user: User, course_id: uuid.UUID, lesson_id: uuid.UUID | None, embedding_model: str
) -> AvailabilityOut:
    course, lesson = await resolve_scope(db, user, course_id, lesson_id)
    n = await count_ready_chunks(db, SearchScope(course.id, lesson.id if lesson else None), embedding_model)
    return AvailabilityOut(available=n > 0, ready_chunks=n, message=None if n else NOT_READY_MESSAGE)
