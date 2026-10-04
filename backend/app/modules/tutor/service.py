import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval import SearchScope, count_ready_chunks
from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.core.ratelimit import RateLimiter, rate_limited
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, CourseStatus, Lesson
from app.modules.enrollment.service import ensure_lesson_access, is_enrolled
from app.modules.tutor.answer import AskContext
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from app.modules.tutor.schemas import (
    AvailabilityOut,
    MessageOut,
    MessagePage,
    SessionCreate,
    SessionOut,
    SessionPage,
)

NOT_READY_MESSAGE = "Tài liệu đang được xử lý"
# Tìm tài liệu theo phạm vi cả khóa chỉ xét khóa đã publish; chủ khóa/admin mở được phiên trên khóa nháp nên cần
# thông báo riêng thay vì "đang xử lý" (tài liệu có thể đã xong).
DRAFT_COURSE_SCOPE_MESSAGE = "Hỏi cả khóa chỉ dùng được khi khóa đã xuất bản"
HISTORY_LIMIT = 4  # số tin nhắn gần nhất dùng để viết lại câu hỏi (spec 5.3 bước 1)
RATE_WINDOW_S = 3600


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
    if lesson is None and course.status != CourseStatus.published:
        return AvailabilityOut(available=False, ready_chunks=n, message=DRAFT_COURSE_SCOPE_MESSAGE)
    return AvailabilityOut(available=n > 0, ready_chunks=n, message=None if n else NOT_READY_MESSAGE)


async def load_history(
    db: AsyncSession, session_id: uuid.UUID, limit: int = HISTORY_LIMIT
) -> list[tuple[ChatRole, str]]:
    """Tối đa `limit` tin nhắn gần nhất (bỏ tin rỗng do lỗi), xếp cũ → mới theo đúng thứ tự của list_messages
    (created_at, role, id): lấy theo thứ tự đảo ngược rồi đảo lại."""
    rows = (
        await db.execute(
            select(ChatMessage.role, ChatMessage.content)
            .where(ChatMessage.session_id == session_id, ChatMessage.content != "")
            .order_by(ChatMessage.created_at.desc(), ChatMessage.role.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
    ).all()
    return [(role, content) for role, content in reversed(rows)]


async def prepare_question(
    db: AsyncSession, limiter: RateLimiter, user: User, session_id: uuid.UUID, question: str
) -> AskContext:
    """Chạy trước khi mở stream (lỗi ở đây trả JSON lỗi bình thường), theo thứ tự:
    1. kiểm quyền lại ở MỖI câu hỏi: phiên của chính mình (người khác → 404) và resolve_scope (bị hủy đăng ký /
       khóa bị gỡ publish sau khi tạo phiên → đúng lỗi mà tạo phiên sẽ trả);
    2. rate limit cho học viên (key `tutor:<user_id>`, RedisRateLimiter thêm tiền tố `rl:`), trước khi lưu, nên
       câu bị chặn không được lưu; bị từ chối ở bước 1 thì không tốn lượt;
    3. lấy lịch sử (trước khi lưu câu hỏi, nên không chứa chính câu này);
    4. lưu câu hỏi và COMMIT trong transaction riêng: câu hỏi luôn còn dù LLM lỗi sau đó (spec 5.7)."""
    session = await get_own_session(db, session_id, user)
    course, _ = await resolve_scope(db, user, session.course_id, session.lesson_id)
    if user.role == Role.student:
        retry_after = await limiter.hit(
            f"tutor:{user.id}", get_settings().tutor_rate_limit_per_hour, RATE_WINDOW_S
        )
        if retry_after is not None:
            raise rate_limited(retry_after)
    history = await load_history(db, session.id)
    db.add(ChatMessage(session_id=session.id, role=ChatRole.user, content=question))
    # commit xong thì session trả connection về pool (expire_on_commit=False nên đọc thuộc tính bên dưới không
    # mở lại connection): stream (có thể vài chục giây) không giữ connection này
    await db.commit()
    return AskContext(
        session_id=session.id,
        scope=scope_of(session),
        course_title=course.title,
        question=question,
        history=history,
    )


async def set_feedback(db: AsyncSession, user: User, message_id: uuid.UUID, value: int | None) -> ChatMessage:
    """Đánh giá (D1: 1 / -1 / None) câu trả lời trong phiên của chính mình; tin người khác / tin user → 404."""
    message = await db.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == message_id,
            ChatSession.user_id == user.id,
            ChatMessage.role == ChatRole.assistant,
        )
    )
    if message is None:
        raise not_found("Tin nhắn")
    message.feedback = value
    await db.commit()
    return message
