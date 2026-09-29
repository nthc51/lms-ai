import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.modules.auth.models import User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.enrollment.models import Enrollment, LessonProgress, ProgressStatus
from app.modules.enrollment.schemas import EnrollmentOut, MyCourseOut


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
