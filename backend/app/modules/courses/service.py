import secrets
import uuid

from slugify import slugify
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import cache as cache_mod
from app.core.cache import COURSES_NS
from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
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
    TeacherCoursePage,
)


async def invalidate_courses_cache() -> None:
    """Gọi sau mọi commit làm đổi dữ liệu hiển thị trên catalog/chi tiết khóa."""
    await cache_mod.get_cache().bump(COURSES_NS)


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


async def list_teacher_courses(db: AsyncSession, teacher: User, params: PageParams) -> TeacherCoursePage:
    stmt = (
        select(Course)
        .where(Course.teacher_id == teacher.id)
        .order_by(Course.created_at.desc(), Course.id.desc())
    )
    total, paged = await paginate(db, stmt, params)
    items = [CourseOut.model_validate(c) for c in await db.scalars(paged)]
    return TeacherCoursePage(items=items, total=total, page=params.page, size=params.size)


async def update_course(db: AsyncSession, course: Course, data: CourseUpdate) -> Course:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(course, field, value)
    await db.commit()
    await invalidate_courses_cache()
    return course


async def _ensure_no_student_work(
    db: AsyncSession, course: Course, lesson_filter, chat_filter, what: str, *, whole_course: bool
) -> None:
    """Chặn xóa (409) chỉ khi phần bị xóa (cascade) kéo theo dữ liệu của HỌC VIÊN:
    - bất kỳ lượt làm quiz nào trên các bài trong phạm vi;
    - phiên hỏi Tutor có tin nhắn của người không phải staff của khóa (bỏ qua chủ khóa và admin: phiên xem thử);
    - xóa khóa: có ít nhất một lượt đăng ký; xóa chương/bài: có tiến độ học của học viên đang đăng ký khóa.
    Quiz (kể cả đã xuất bản nhưng chưa ai làm), câu hỏi, tài liệu và phiên xem thử của staff vẫn bị xóa theo
    cascade như trước. Khóa FOR UPDATE dòng khóa học (khi xóa khóa) và các bài/quiz trong phạm vi: lệnh tạo
    lượt làm, đăng ký, tiến độ hay phiên Tutor (khóa ngoại tới các dòng này) phải đợi tới khi xóa xong, nên dữ liệu
    học viên không thể chen vào giữa lúc kiểm tra và lúc xóa."""
    from app.modules.enrollment.models import Enrollment, LessonProgress
    from app.modules.quiz.models import Quiz, QuizAttempt
    from app.modules.tutor.models import ChatMessage, ChatSession

    if whole_course:
        await db.execute(select(Course.id).where(Course.id == course.id).with_for_update())
    lesson_ids = select(Lesson.id).join(Section, Section.id == Lesson.section_id).where(lesson_filter)
    await db.execute(select(Lesson.id).where(Lesson.id.in_(lesson_ids)).with_for_update())
    quiz_ids = list(
        (await db.scalars(select(Quiz.id).where(Quiz.lesson_id.in_(lesson_ids)).with_for_update())).all()
    )

    async def exists(stmt) -> bool:
        return bool(await db.scalar(select(stmt.exists())))

    if quiz_ids and await exists(select(QuizAttempt.id).where(QuizAttempt.quiz_id.in_(quiz_ids))):
        raise AppError("INVALID_STATE", f"Không xóa được: {what} đã có bài làm quiz của học viên", 409)
    student_chat = (
        select(ChatSession.id)
        .join(User, User.id == ChatSession.user_id)
        .where(
            chat_filter(ChatSession, lesson_ids),
            ChatSession.user_id != course.teacher_id,
            User.role != Role.admin,
            select(ChatMessage.id).where(ChatMessage.session_id == ChatSession.id).exists(),
        )
    )
    if await exists(student_chat):
        raise AppError("INVALID_STATE", f"Không xóa được: {what} đã có lịch sử hỏi Tutor của học viên", 409)
    if whole_course:
        if await exists(select(Enrollment.user_id).where(Enrollment.course_id == course.id)):
            raise AppError("INVALID_STATE", f"Không xóa được: {what} đã có học viên đăng ký", 409)
    elif await exists(
        select(LessonProgress.user_id)
        .join(
            Enrollment,
            (Enrollment.user_id == LessonProgress.user_id) & (Enrollment.course_id == course.id),
        )
        .where(LessonProgress.lesson_id.in_(lesson_ids))
    ):
        raise AppError("INVALID_STATE", f"Không xóa được: {what} đã có tiến độ học của học viên", 409)


async def delete_course(db: AsyncSession, course: Course) -> None:
    await _ensure_no_student_work(
        db,
        course,
        Section.course_id == course.id,
        lambda cs, _: cs.course_id == course.id,
        "khóa học",
        whole_course=True,
    )
    await db.execute(delete(Course).where(Course.id == course.id))
    await db.commit()
    await invalidate_courses_cache()


async def count_lessons(db: AsyncSession, course_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count(Lesson.id))
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course_id)
    )


async def publish_course(db: AsyncSession, course: Course) -> Course:
    # Khóa bị quản trị viên ẩn chỉ được hiện lại qua POST /admin/courses/{id}/unhide.
    if course.hidden_at is not None:
        raise AppError("COURSE_HIDDEN", "Khóa học đã bị quản trị viên ẩn, không thể tự xuất bản lại", 409)
    if await count_lessons(db, course.id) == 0:
        raise AppError("COURSE_EMPTY", "Khóa học cần ít nhất một bài học trước khi xuất bản", 409)
    course.status = CourseStatus.published
    await db.commit()
    await invalidate_courses_cache()
    return course


async def _next_position(db: AsyncSession, column, condition) -> int:
    return (await db.scalar(select(func.coalesce(func.max(column), 0)).where(condition))) + 1


async def add_section(db: AsyncSession, course: Course, data: SectionCreate) -> Section:
    position = await _next_position(db, Section.position, Section.course_id == course.id)
    section = Section(course_id=course.id, title=data.title, position=position)
    db.add(section)
    await db.commit()
    await invalidate_courses_cache()
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
    await invalidate_courses_cache()
    return section


async def delete_section(db: AsyncSession, section: Section) -> None:
    course = await db.get(Course, section.course_id)
    await _ensure_no_student_work(
        db,
        course,
        Section.id == section.id,
        lambda cs, ids: cs.lesson_id.in_(ids),
        "chương này",
        whole_course=False,
    )
    await db.execute(delete(Section).where(Section.id == section.id))
    await db.commit()
    await invalidate_courses_cache()


async def add_lesson(db: AsyncSession, section: Section, data: LessonCreate) -> Lesson:
    position = await _next_position(db, Lesson.position, Lesson.section_id == section.id)
    lesson = Lesson(section_id=section.id, title=data.title, content_md=data.content_md, position=position)
    db.add(lesson)
    await db.commit()
    await invalidate_courses_cache()
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


# Cột nullable của lesson: gửi null tường minh nghĩa là xóa (vd. gỡ video). Các cột khác bỏ qua null.
_LESSON_NULLABLE_FIELDS = frozenset({"video_asset_id", "duration_sec"})


async def update_lesson(db: AsyncSession, lesson: Lesson, data: LessonUpdate) -> Lesson:
    # exclude_unset: trường không gửi thì giữ nguyên
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field not in _LESSON_NULLABLE_FIELDS:
            continue
        setattr(lesson, field, value)
    await db.commit()
    await invalidate_courses_cache()
    return lesson


async def delete_lesson(db: AsyncSession, lesson: Lesson, course: Course) -> None:
    await _ensure_no_student_work(
        db,
        course,
        Lesson.id == lesson.id,
        lambda cs, ids: cs.lesson_id.in_(ids),
        "bài học này",
        whole_course=False,
    )
    await db.execute(delete(Lesson).where(Lesson.id == lesson.id))
    await db.commit()
    await invalidate_courses_cache()


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
    await invalidate_courses_cache()


async def list_published(db: AsyncSession, q: str | None, params: PageParams) -> CoursePage:
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
    total, paged = await paginate(db, base.order_by(Course.created_at.desc(), Course.id.desc()), params)
    rows = (await db.execute(paged)).all()
    items = [
        CourseCard(id=c.id, title=c.title, slug=c.slug, description=c.description, teacher_name=name)
        for c, name in rows
    ]
    return CoursePage(items=items, total=total, page=params.page, size=params.size)


async def list_published_cached(db: AsyncSession, q: str | None, params: PageParams) -> CoursePage:
    key = f"catalog:{(q or '').strip().lower()[:100]}:{params.page}:{params.size}"

    async def load():
        page = await list_published(db, q, params)
        return page.model_dump(mode="json"), True

    data = await cache_mod.get_cache().get_or_load(COURSES_NS, key, get_settings().cache_ttl_s, load)
    return CoursePage.model_validate(data)


async def _load_detail_base(db: AsyncSession, slug: str) -> dict:
    """Phần giống nhau với mọi người xem (thông tin khóa và mục lục), dạng JSON để cache được."""
    course = await db.scalar(
        select(Course)
        .where(Course.slug == slug)
        .options(selectinload(Course.sections).selectinload(Section.lessons))
    )
    if course is None:
        raise not_found("Khóa học")
    teacher_name = await db.scalar(select(User.full_name).where(User.id == course.teacher_id))
    return {
        **CourseOut.model_validate(course).model_dump(mode="json"),
        "teacher_name": teacher_name,
        "sections": [SectionBrief.model_validate(s).model_dump(mode="json") for s in course.sections],
    }


async def get_course_detail(db: AsyncSession, slug: str, user: User | None) -> CourseDetail:
    from app.modules.enrollment.service import is_enrolled  # import trong hàm để tránh vòng import

    async def load():
        base = await _load_detail_base(db, slug)
        # Chỉ cache khóa đã publish: bản nháp / bị ẩn chỉ chủ khóa xem, không được lọt ra cho người khác
        return base, base["status"] == CourseStatus.published.value

    base = await cache_mod.get_cache().get_or_load(
        COURSES_NS, f"detail:{slug}", get_settings().cache_ttl_s, load
    )
    teacher_id, course_id = uuid.UUID(base["teacher_id"]), uuid.UUID(base["id"])
    is_owner = user is not None and (user.role == Role.admin or teacher_id == user.id)
    if base["status"] != CourseStatus.published.value and not is_owner:
        raise not_found("Khóa học")
    enrolled = user is not None and await is_enrolled(db, user.id, course_id)
    return CourseDetail.model_validate({**base, "is_enrolled": enrolled, "is_owner": is_owner})
