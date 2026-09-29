import secrets
import uuid

from slugify import slugify
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.courses.schemas import CourseCreate, CourseUpdate


def make_slug(title: str) -> str:
    base = slugify(title)[:200] or "khoa-hoc"
    return f"{base}-{secrets.token_hex(3)}"


def ensure_owner(course: Course, user: User) -> None:
    """Admin hoặc giảng viên sở hữu khóa. Người khác nhận 404 để không lộ khóa có tồn tại."""
    if user.role != Role.admin and course.teacher_id != user.id:
        raise not_found("Khóa học")


async def get_owned_course(db: AsyncSession, course_id: uuid.UUID, user: User) -> Course:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    ensure_owner(course, user)
    return course


async def create_course(db: AsyncSession, teacher: User, data: CourseCreate) -> Course:
    course = Course(teacher_id=teacher.id, title=data.title, description=data.description,
                    slug=make_slug(data.title), status=CourseStatus.draft)
    db.add(course)
    await db.commit()
    return course


async def list_teacher_courses(db: AsyncSession, teacher: User) -> list[Course]:
    rows = await db.scalars(select(Course).where(Course.teacher_id == teacher.id)
                            .order_by(Course.created_at.desc()))
    return list(rows)


async def update_course(db: AsyncSession, course: Course, data: CourseUpdate) -> Course:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(course, field, value)
    await db.commit()
    return course


async def delete_course(db: AsyncSession, course: Course) -> None:
    await db.execute(delete(Course).where(Course.id == course.id))
    await db.commit()


async def count_lessons(db: AsyncSession, course_id: uuid.UUID) -> int:
    return await db.scalar(select(func.count(Lesson.id)).join(Section, Section.id == Lesson.section_id)
                           .where(Section.course_id == course_id))


async def publish_course(db: AsyncSession, course: Course) -> Course:
    if await count_lessons(db, course.id) == 0:
        raise AppError("COURSE_EMPTY", "Khóa học cần ít nhất một bài học trước khi xuất bản", 409)
    course.status = CourseStatus.published
    await db.commit()
    return course
