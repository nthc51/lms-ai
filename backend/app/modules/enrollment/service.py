import uuid

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.courses.service import get_lesson_with_course
from app.modules.enrollment.models import Enrollment, LessonProgress, ProgressStatus
from app.modules.enrollment.schemas import EnrollmentOut, LessonDetail, MyCourseOut, ProgressIn, ProgressOut


async def enroll(db: AsyncSession, user: User, course_id: uuid.UUID) -> EnrollmentOut:
    course = await db.get(Course, course_id)
    if course is None or course.status != CourseStatus.published:
        raise not_found("Khóa học")
    stmt = (pg_insert(Enrollment).values(user_id=user.id, course_id=course_id)
            .on_conflict_do_nothing().returning(Enrollment.course_id, Enrollment.enrolled_at))
    row = (await db.execute(stmt)).first()
    if row is None:
        raise AppError("ALREADY_ENROLLED", "Bạn đã đăng ký khóa học này", 409)
    await db.commit()
    return EnrollmentOut(course_id=row.course_id, enrolled_at=row.enrolled_at)


async def is_enrolled(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    return await db.scalar(select(func.count()).select_from(Enrollment)
                           .where(Enrollment.user_id == user_id, Enrollment.course_id == course_id)) > 0


async def my_courses(db: AsyncSession, user: User) -> list[MyCourseOut]:
    rows = (await db.execute(
        select(Enrollment, Course).join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.user_id == user.id).order_by(Enrollment.enrolled_at.desc())
    )).all()
    course_ids = [course.id for _, course in rows]
    totals = dict((await db.execute(
        select(Section.course_id, func.count(Lesson.id)).join(Lesson, Lesson.section_id == Section.id)
        .where(Section.course_id.in_(course_ids)).group_by(Section.course_id)
    )).all())
    dones = dict((await db.execute(
        select(Section.course_id, func.count(LessonProgress.lesson_id))
        .join(Lesson, Lesson.id == LessonProgress.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(LessonProgress.user_id == user.id, LessonProgress.status == ProgressStatus.done,
               Section.course_id.in_(course_ids))
        .group_by(Section.course_id)
    )).all())
    result = []
    for enrollment, course in rows:
        total, done = totals.get(course.id, 0), dones.get(course.id, 0)
        result.append(MyCourseOut(
            course_id=course.id, title=course.title, slug=course.slug,
            enrolled_at=enrollment.enrolled_at, completed_at=enrollment.completed_at,
            total_lessons=total, done_lessons=done,
            progress_pct=round(done * 100 / total) if total else 0,
        ))
    return result


async def ensure_lesson_access(db: AsyncSession, lesson_id: uuid.UUID, user: User) -> tuple[Lesson, Course]:
    """Admin và giảng viên sở hữu khóa luôn được vào. Học viên phải đăng ký khóa đã xuất bản."""
    lesson, course = await get_lesson_with_course(db, lesson_id)
    if user.role == Role.admin or course.teacher_id == user.id:
        return lesson, course
    if course.status != CourseStatus.published:
        raise not_found("Bài học")
    if not await is_enrolled(db, user.id, course.id):
        raise AppError("NOT_ENROLLED", "Bạn cần đăng ký khóa học để xem bài này", 403)
    return lesson, course


async def get_lesson_detail(db: AsyncSession, lesson_id: uuid.UUID, user: User) -> LessonDetail:
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    progress = await db.get(LessonProgress, (user.id, lesson.id))
    return LessonDetail(id=lesson.id, section_id=lesson.section_id, course_id=course.id, title=lesson.title,
                        content_md=lesson.content_md, duration_sec=lesson.duration_sec,
                        progress=ProgressOut.model_validate(progress) if progress else None)


async def update_progress(db: AsyncSession, lesson_id: uuid.UUID, user: User, data: ProgressIn) -> ProgressOut:
    if user.role != Role.student:
        raise forbidden("Chỉ học viên mới lưu tiến độ")
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    new_status = ProgressStatus(data.status)
    now = utcnow()
    stmt = pg_insert(LessonProgress).values(
        user_id=user.id, lesson_id=lesson.id, status=new_status, video_position_sec=data.video_position_sec,
        completed_at=now if new_status == ProgressStatus.done else None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[LessonProgress.user_id, LessonProgress.lesson_id],
        set_={
            # Đã "done" thì giữ nguyên "done" (học viên xem lại bài không làm mất tiến độ)
            "status": case((LessonProgress.status == ProgressStatus.done, LessonProgress.status),
                           else_=stmt.excluded.status),
            "video_position_sec": stmt.excluded.video_position_sec,
            "completed_at": func.coalesce(LessonProgress.completed_at, stmt.excluded.completed_at),
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)

    total = await db.scalar(select(func.count(Lesson.id)).join(Section, Section.id == Lesson.section_id)
                            .where(Section.course_id == course.id))
    done = await db.scalar(
        select(func.count(LessonProgress.lesson_id))
        .join(Lesson, Lesson.id == LessonProgress.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course.id, LessonProgress.user_id == user.id,
               LessonProgress.status == ProgressStatus.done))
    if total and done >= total:
        await db.execute(update(Enrollment)
                         .where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)
                         .values(completed_at=func.coalesce(Enrollment.completed_at, func.now())))
    await db.commit()
    progress = await db.get(LessonProgress, (user.id, lesson.id), populate_existing=True)
    return ProgressOut.model_validate(progress)
