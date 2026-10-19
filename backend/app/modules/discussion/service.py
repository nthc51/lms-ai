"""Thảo luận theo bài học (B4).

- Ai vào được bài học (học viên đã đăng ký khóa đã xuất bản, giảng viên của khóa, admin) thì đọc và viết được.
- Hai cấp: bình luận gốc (câu hỏi) và trả lời; không trả lời một câu trả lời.
- Xóa mềm: tác giả, giảng viên của khóa hoặc admin; luồng vẫn giữ chỗ "Bình luận đã bị xóa" để các trả lời
  bên dưới còn ngữ cảnh.
- Thông báo (B6): trả lời → báo tác giả bình luận gốc; câu hỏi mới của học viên → báo giảng viên của khóa."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.core.ratelimit import RateLimiter, rate_limited
from app.core.time import utcnow
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, Lesson
from app.modules.discussion.models import LessonComment
from app.modules.discussion.schemas import CommentIn, CommentOut, CommentPage
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.inbox import service as inbox
from app.modules.inbox.hub import NotificationHub
from app.modules.inbox.models import NotificationKind

COMMENT_LIMIT_PER_HOUR = 30
SNIPPET = 120


def _can_moderate(user: User, course: Course) -> bool:
    return user.role == Role.admin or course.teacher_id == user.id


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET else text[: SNIPPET - 1].rstrip() + "…"


def _link(course: Course, lesson: Lesson) -> str:
    return f"/learn/{course.slug}/{lesson.id}#thao-luan"


def _out(c: LessonComment, author: User, viewer: User, course: Course) -> CommentOut:
    deleted = c.deleted_at is not None
    return CommentOut(
        id=c.id,
        parent_id=c.parent_id,
        body=None if deleted else c.body,
        deleted=deleted,
        author_name=author.full_name,
        author_role=author.role.value,
        is_course_teacher=author.id == course.teacher_id,
        can_delete=not deleted and (author.id == viewer.id or _can_moderate(viewer, course)),
        created_at=c.created_at,
    )


async def list_threads(db: AsyncSession, user: User, lesson_id: uuid.UUID, params: PageParams) -> CommentPage:
    """Bình luận gốc mới nhất trước (phân trang), mỗi cái kèm mọi trả lời cũ trước mới sau."""
    _, course = await ensure_lesson_access(db, lesson_id, user)
    stmt = (
        select(LessonComment, User)
        .join(User, User.id == LessonComment.user_id)
        .where(LessonComment.lesson_id == lesson_id, LessonComment.parent_id.is_(None))
        .order_by(LessonComment.created_at.desc(), LessonComment.id.desc())
    )
    total, paged = await paginate(db, stmt, params)
    roots = [_out(c, a, user, course) for c, a in (await db.execute(paged)).all()]
    if roots:
        replies = (
            await db.execute(
                select(LessonComment, User)
                .join(User, User.id == LessonComment.user_id)
                .where(LessonComment.parent_id.in_([r.id for r in roots]))
                .order_by(LessonComment.created_at, LessonComment.id)
            )
        ).all()
        by_parent = {r.id: r for r in roots}
        for c, a in replies:
            by_parent[c.parent_id].replies.append(_out(c, a, user, course))
    return CommentPage(items=roots, total=total, page=params.page, size=params.size)


async def create_comment(
    db: AsyncSession,
    limiter: RateLimiter,
    hub: NotificationHub,
    user: User,
    lesson_id: uuid.UUID,
    data: CommentIn,
) -> CommentOut:
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    wait = await limiter.hit(f"comment:{user.id}", COMMENT_LIMIT_PER_HOUR, 3600)
    if wait is not None:
        raise rate_limited(wait)
    parent = None
    if data.parent_id is not None:
        parent = await db.get(LessonComment, data.parent_id)
        if parent is None or parent.lesson_id != lesson_id:
            raise not_found("Bình luận")
        if parent.parent_id is not None:
            raise AppError("INVALID_PARENT", "Chỉ trả lời được bình luận gốc", 422)
        if parent.deleted_at is not None:
            raise AppError("COMMENT_DELETED", "Bình luận này đã bị xóa, không trả lời được nữa", 409)

    comment = LessonComment(lesson_id=lesson_id, user_id=user.id, parent_id=data.parent_id, body=data.body)
    db.add(comment)
    recipients: list[uuid.UUID] = []
    if parent is not None and parent.user_id != user.id:
        recipients = [parent.user_id]
        notified = inbox.add(
            db,
            recipients,
            NotificationKind.comment_reply,
            f"{user.full_name} trả lời bình luận của bạn",
            _link(course, lesson),
            body=f"{lesson.title}: {_snippet(data.body)}",
        )
    elif parent is None and course.teacher_id != user.id:
        notified = inbox.add(
            db,
            [course.teacher_id],
            NotificationKind.new_question,
            f"Câu hỏi mới ở bài {lesson.title}",
            _link(course, lesson),
            body=f"{user.full_name}: {_snippet(data.body)}",
        )
    else:
        notified = []
    await db.commit()
    await db.refresh(comment)
    await inbox.publish(hub, notified)
    return _out(comment, user, user, course)


async def delete_comment(db: AsyncSession, user: User, comment_id: uuid.UUID) -> None:
    comment = await db.get(LessonComment, comment_id)
    if comment is None:
        raise not_found("Bình luận")
    _, course = await ensure_lesson_access(db, comment.lesson_id, user)  # mất quyền vào bài → 404 / 403
    if comment.user_id != user.id and not _can_moderate(user, course):
        raise not_found("Bình luận")  # không lộ là bình luận có tồn tại
    if comment.deleted_at is None:
        comment.deleted_at = utcnow()
        await db.commit()
