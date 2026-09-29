import secrets
import uuid

from slugify import slugify
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, not_found
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.courses.schemas import (
    CourseCard,
    CourseCreate,
    CourseDetail,
    CourseOut,
    CoursePage,
    CourseUpdate,
    LessonCreate,
    LessonUpdate,
    ReorderIn,
    SectionBrief,
    SectionCreate,
    SectionUpdate,
)


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
    course = Course(
        teacher_id=teacher.id,
        title=data.title,
        description=data.description,
        slug=make_slug(data.title),
        status=CourseStatus.draft,
    )
    db.add(course)
    await db.commit()
    return course


async def list_teacher_courses(db: AsyncSession, teacher: User) -> list[Course]:
    rows = await db.scalars(
        select(Course).where(Course.teacher_id == teacher.id).order_by(Course.created_at.desc())
    )
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
    return await db.scalar(
        select(func.count(Lesson.id))
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course_id)
    )


async def publish_course(db: AsyncSession, course: Course) -> Course:
    if await count_lessons(db, course.id) == 0:
        raise AppError("COURSE_EMPTY", "Khóa học cần ít nhất một bài học trước khi xuất bản", 409)
    course.status = CourseStatus.published
    await db.commit()
    return course


async def _next_position(db: AsyncSession, column, condition) -> int:
    return (await db.scalar(select(func.coalesce(func.max(column), 0)).where(condition))) + 1


async def add_section(db: AsyncSession, course: Course, data: SectionCreate) -> Section:
    position = await _next_position(db, Section.position, Section.course_id == course.id)
    section = Section(course_id=course.id, title=data.title, position=position)
    db.add(section)
    await db.commit()
    return section


async def get_owned_section(db: AsyncSession, section_id: uuid.UUID, user: User) -> Section:
    row = (
        await db.execute(
            select(Section, Course)
            .join(Course, Course.id == Section.course_id)
            .where(Section.id == section_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Chương")
    section, course = row
    ensure_owner(course, user)
    return section


async def update_section(db: AsyncSession, section: Section, data: SectionUpdate) -> Section:
    section.title = data.title
    await db.commit()
    return section


async def delete_section(db: AsyncSession, section: Section) -> None:
    await db.execute(delete(Section).where(Section.id == section.id))
    await db.commit()


async def add_lesson(db: AsyncSession, section: Section, data: LessonCreate) -> Lesson:
    position = await _next_position(db, Lesson.position, Lesson.section_id == section.id)
    lesson = Lesson(section_id=section.id, title=data.title, content_md=data.content_md, position=position)
    db.add(lesson)
    await db.commit()
    return lesson


async def get_lesson_with_course(db: AsyncSession, lesson_id: uuid.UUID) -> tuple[Lesson, Course]:
    row = (
        await db.execute(
            select(Lesson, Course)
            .join(Section, Section.id == Lesson.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Lesson.id == lesson_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Bài học")
    return row[0], row[1]


async def get_owned_lesson(db: AsyncSession, lesson_id: uuid.UUID, user: User) -> tuple[Lesson, Course]:
    lesson, course = await get_lesson_with_course(db, lesson_id)
    ensure_owner(course, user)
    return lesson, course


async def update_lesson(db: AsyncSession, lesson: Lesson, data: LessonUpdate) -> Lesson:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(lesson, field, value)
    await db.commit()
    return lesson


async def delete_lesson(db: AsyncSession, lesson: Lesson) -> None:
    await db.execute(delete(Lesson).where(Lesson.id == lesson.id))
    await db.commit()


async def reorder(db: AsyncSession, course: Course, data: ReorderIn) -> None:
    sections = {s.id: s for s in await db.scalars(select(Section).where(Section.course_id == course.id))}
    lessons = {
        lesson.id: lesson
        for lesson in await db.scalars(
            select(Lesson)
            .join(Section, Section.id == Lesson.section_id)
            .where(Section.course_id == course.id)
        )
    }
    given_sections = [s.id for s in data.sections]
    given_lessons = [lid for s in data.sections for lid in s.lesson_ids]
    if sorted(given_sections) != sorted(sections) or sorted(given_lessons) != sorted(lessons):
        raise AppError("INVALID_REORDER", "Danh sách sắp xếp không khớp với khóa học", 400)
    for s_pos, item in enumerate(data.sections, start=1):
        sections[item.id].position = s_pos
        for l_pos, lesson_id in enumerate(item.lesson_ids, start=1):
            lessons[lesson_id].section_id = item.id
            lessons[lesson_id].position = l_pos
    await db.commit()


async def list_published(db: AsyncSession, q: str | None, page: int, size: int) -> CoursePage:
    base = (
        select(Course, User.full_name)
        .join(User, User.id == Course.teacher_id)
        .where(Course.status == CourseStatus.published)
    )
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        base = base.where(
            func.immutable_unaccent(func.lower(Course.title)).like(func.immutable_unaccent(pattern))
        )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await db.execute(base.order_by(Course.created_at.desc()).offset((page - 1) * size).limit(size))
    ).all()
    items = [
        CourseCard(id=c.id, title=c.title, slug=c.slug, description=c.description, teacher_name=name)
        for c, name in rows
    ]
    return CoursePage(items=items, total=total, page=page, size=size)


async def get_course_detail(db: AsyncSession, slug: str, user: User | None) -> CourseDetail:
    from app.modules.enrollment.service import is_enrolled  # import trong hàm để tránh vòng import

    course = await db.scalar(
        select(Course)
        .where(Course.slug == slug)
        .options(selectinload(Course.sections).selectinload(Section.lessons))
    )
    if course is None:
        raise not_found("Khóa học")
    is_owner = user is not None and (user.role == Role.admin or course.teacher_id == user.id)
    if course.status != CourseStatus.published and not is_owner:
        raise not_found("Khóa học")
    teacher_name = await db.scalar(select(User.full_name).where(User.id == course.teacher_id))
    enrolled = user is not None and await is_enrolled(db, user.id, course.id)
    return CourseDetail(
        **CourseOut.model_validate(course).model_dump(),
        teacher_name=teacher_name,
        sections=[SectionBrief.model_validate(s) for s in course.sections],
        is_enrolled=enrolled,
        is_owner=is_owner,
    )
