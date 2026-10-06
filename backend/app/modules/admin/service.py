import uuid
from datetime import date, timedelta

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.core.time import utcnow
from app.modules.admin.models import AdminAction
from app.modules.admin.schemas import (
    AdminActionOut,
    AdminActionPage,
    AdminCourseOut,
    AdminCoursePage,
    AdminStats,
    AdminUserOut,
    AdminUserPage,
    DayCount,
)
from app.modules.auth.models import RefreshToken, Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.enrollment.models import Enrollment
from app.modules.jobs.models import Job, JobStatus
from app.modules.quiz.models import AttemptStatus, QuizAttempt
from app.modules.tutor.models import ChatMessage, ChatRole

VN_TZ = "Asia/Ho_Chi_Minh"


def _log(
    db: AsyncSession,
    admin: User,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    label: str,
    note: str | None,
) -> None:
    db.add(
        AdminAction(
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=label,
            note=note,
        )
    )


def _like(q: str) -> str:
    return f"%{q.strip().lower()}%"


# ---------- người dùng ----------

_course_count = (
    select(func.count())
    .select_from(Course)
    .where(Course.teacher_id == User.id)
    .correlate(User)
    .scalar_subquery()
)
_enroll_count = (
    select(func.count())
    .select_from(Enrollment)
    .where(Enrollment.user_id == User.id)
    .correlate(User)
    .scalar_subquery()
)


def _user_out(user: User, course_count: int, enrollment_count: int) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        teacher_status=user.teacher_status,
        locked_at=user.locked_at,
        review_note=user.review_note,
        created_at=user.created_at,
        course_count=course_count,
        enrollment_count=enrollment_count,
    )


async def list_users(
    db: AsyncSession, role: Role | None, status: str | None, q: str | None, params: PageParams
) -> AdminUserPage:
    stmt: Select = select(User, _course_count, _enroll_count)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if status in ("pending", "approved", "rejected"):
        stmt = stmt.where(User.role == Role.teacher, User.teacher_status == TeacherStatus(status))
    elif status == "locked":
        stmt = stmt.where(User.locked_at.is_not(None))
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
                User.email.like(pattern),
            )
        )
    # Chờ duyệt: ai đăng ký trước được xử lý trước. Còn lại: mới nhất lên đầu.
    order = User.created_at.asc() if status == "pending" else User.created_at.desc()
    total, paged = await paginate(db, stmt.order_by(order, User.id), params)
    rows = (await db.execute(paged)).all()
    return AdminUserPage(
        items=[_user_out(u, cc, ec) for u, cc, ec in rows], total=total, page=params.page, size=params.size
    )


async def _get_user_row(db: AsyncSession, user_id: uuid.UUID) -> AdminUserOut:
    row = (await db.execute(select(User, _course_count, _enroll_count).where(User.id == user_id))).one()
    return _user_out(*row)


async def _get_teacher(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.role != Role.teacher:
        raise not_found("Giảng viên")
    return user


async def approve_teacher(db: AsyncSession, admin: User, user_id: uuid.UUID) -> AdminUserOut:
    """Duyệt giảng viên đang chờ hoặc đã bị từ chối trước đó (đổi ý)."""
    user = await _get_teacher(db, user_id)
    if user.teacher_status == TeacherStatus.approved:
        raise AppError("ALREADY_APPROVED", "Giảng viên này đã được duyệt", 409)
    user.teacher_status = TeacherStatus.approved
    user.review_note = None
    _log(db, admin, "approve_teacher", "user", user.id, user.email, None)
    await db.commit()
    return await _get_user_row(db, user.id)


async def reject_teacher(db: AsyncSession, admin: User, user_id: uuid.UUID, reason: str) -> AdminUserOut:
    """Chỉ từ chối được yêu cầu đang chờ. Giảng viên đã duyệt mà vi phạm thì khóa tài khoản."""
    user = await _get_teacher(db, user_id)
    if user.teacher_status != TeacherStatus.pending:
        raise AppError("NOT_PENDING", "Chỉ từ chối được giảng viên đang chờ duyệt", 409)
    user.teacher_status = TeacherStatus.rejected
    user.review_note = reason
    _log(db, admin, "reject_teacher", "user", user.id, user.email, reason)
    await db.commit()
    return await _get_user_row(db, user.id)


async def lock_user(db: AsyncSession, admin: User, user_id: uuid.UUID, reason: str | None) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Người dùng")
    if user.role == Role.admin:
        raise AppError("CANNOT_LOCK_ADMIN", "Không thể khóa tài khoản quản trị viên", 409)
    if user.locked_at is None:
        user.locked_at = utcnow()
        user.review_note = reason
        # Thu hồi mọi phiên: refresh bị chặn ngay; access token còn hạn cũng bị deps chặn vì locked_at.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        _log(db, admin, "lock_user", "user", user.id, user.email, reason)
        await db.commit()
    return await _get_user_row(db, user.id)


async def unlock_user(db: AsyncSession, admin: User, user_id: uuid.UUID) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Người dùng")
    if user.locked_at is not None:
        user.locked_at = None
        # Lý do khóa không còn đúng nữa; lý do từ chối giảng viên (nếu có) thì giữ.
        if user.teacher_status != TeacherStatus.rejected:
            user.review_note = None
        _log(db, admin, "unlock_user", "user", user.id, user.email, None)
        await db.commit()
    return await _get_user_row(db, user.id)


# ---------- khóa học ----------

_lesson_count = (
    select(func.count())
    .select_from(Lesson)
    .join(Section, Section.id == Lesson.section_id)
    .where(Section.course_id == Course.id)
    .correlate(Course)
    .scalar_subquery()
)
_course_enroll_count = (
    select(func.count())
    .select_from(Enrollment)
    .where(Enrollment.course_id == Course.id)
    .correlate(Course)
    .scalar_subquery()
)


def _course_stmt() -> Select:
    return select(Course, User.full_name, User.email, _lesson_count, _course_enroll_count).join(
        User, User.id == Course.teacher_id
    )


def _course_out(row) -> AdminCourseOut:
    c, name, email, lessons, enrolls = row
    return AdminCourseOut(
        id=c.id,
        title=c.title,
        slug=c.slug,
        status=c.status,
        teacher_id=c.teacher_id,
        teacher_name=name,
        teacher_email=email,
        created_at=c.created_at,
        lesson_count=lessons,
        enrollment_count=enrolls,
        hidden_at=c.hidden_at,
        hidden_reason=c.hidden_reason,
    )


async def list_courses(
    db: AsyncSession, status: str | None, q: str | None, params: PageParams
) -> AdminCoursePage:
    """status: published | draft | hidden (đã bị admin ẩn). Không truyền = tất cả."""
    stmt = _course_stmt()
    if status == "hidden":
        stmt = stmt.where(Course.hidden_at.is_not(None))
    elif status in ("published", "draft"):
        stmt = stmt.where(Course.status == CourseStatus(status), Course.hidden_at.is_(None))
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                func.immutable_unaccent(func.lower(Course.title)).like(func.immutable_unaccent(pattern)),
                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
            )
        )
    total, paged = await paginate(db, stmt.order_by(Course.created_at.desc(), Course.id), params)
    rows = (await db.execute(paged)).all()
    return AdminCoursePage(
        items=[_course_out(r) for r in rows], total=total, page=params.page, size=params.size
    )


async def _course_row(db: AsyncSession, course_id: uuid.UUID) -> AdminCourseOut:
    return _course_out((await db.execute(_course_stmt().where(Course.id == course_id))).one())


async def hide_course(db: AsyncSession, admin: User, course_id: uuid.UUID, reason: str) -> AdminCourseOut:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    if course.status != CourseStatus.published:
        raise AppError("COURSE_NOT_PUBLISHED", "Chỉ ẩn được khóa học đang xuất bản", 409)
    course.status = CourseStatus.archived
    course.hidden_at = utcnow()
    course.hidden_reason = reason
    _log(db, admin, "hide_course", "course", course.id, course.title, reason)
    await db.commit()
    return await _course_row(db, course.id)


async def unhide_course(db: AsyncSession, admin: User, course_id: uuid.UUID) -> AdminCourseOut:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    if course.hidden_at is None:
        raise AppError("COURSE_NOT_HIDDEN", "Khóa học này không bị ẩn", 409)
    course.status = CourseStatus.published
    course.hidden_at = None
    course.hidden_reason = None
    _log(db, admin, "unhide_course", "course", course.id, course.title, None)
    await db.commit()
    return await _course_row(db, course.id)


# ---------- tổng quan & nhật ký ----------


async def stats(db: AsyncSession) -> AdminStats:
    now = utcnow()
    week_ago = now - timedelta(days=7)

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    by_role = dict((await db.execute(select(User.role, func.count()).group_by(User.role))).all())
    by_status = dict(
        (
            await db.execute(
                select(Course.status, func.count()).where(Course.hidden_at.is_(None)).group_by(Course.status)
            )
        ).all()
    )
    vn_day = func.date(func.timezone(VN_TZ, User.created_at))
    today = await db.scalar(select(func.date(func.timezone(VN_TZ, func.now()))))
    first = today - timedelta(days=13)
    per_day = dict(
        (await db.execute(select(vn_day, func.count()).where(vn_day >= first).group_by(vn_day))).all()
    )
    days: list[date] = [first + timedelta(days=i) for i in range(14)]

    return AdminStats(
        students=by_role.get(Role.student, 0),
        teachers=by_role.get(Role.teacher, 0),
        pending_teachers=await count(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.teacher, User.teacher_status == TeacherStatus.pending)
        ),
        locked_users=await count(select(func.count()).select_from(User).where(User.locked_at.is_not(None))),
        courses_published=by_status.get(CourseStatus.published, 0),
        courses_draft=by_status.get(CourseStatus.draft, 0),
        courses_hidden=await count(
            select(func.count()).select_from(Course).where(Course.hidden_at.is_not(None))
        ),
        enrollments=await count(select(func.count()).select_from(Enrollment)),
        tutor_questions_7d=await count(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.role == ChatRole.user, ChatMessage.created_at >= week_ago)
        ),
        quiz_submissions_7d=await count(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.status != AttemptStatus.in_progress, QuizAttempt.submitted_at >= week_ago)
        ),
        failed_jobs_7d=await count(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.failed, Job.created_at >= week_ago)
        ),
        signups_14d=[DayCount(day=d, count=per_day.get(d, 0)) for d in days],
    )


async def list_actions(db: AsyncSession, params: PageParams) -> AdminActionPage:
    stmt = select(AdminAction, User.full_name).outerjoin(User, User.id == AdminAction.admin_id)
    total, paged = await paginate(db, stmt.order_by(AdminAction.created_at.desc(), AdminAction.id), params)
    rows = (await db.execute(paged)).all()
    items = [
        AdminActionOut(
            id=a.id,
            admin_name=name,
            action=a.action,
            target_type=a.target_type,
            target_id=a.target_id,
            target_label=a.target_label,
            note=a.note,
            created_at=a.created_at,
        )
        for a, name in rows
    ]
    return AdminActionPage(items=items, total=total, page=params.page, size=params.size)
