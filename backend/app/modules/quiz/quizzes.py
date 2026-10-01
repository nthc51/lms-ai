"""Quiz của bài học: CRUD cho giảng viên; học viên chỉ xem quiz đã xuất bản, không bao giờ kèm đáp án."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, Lesson, Section
from app.modules.courses.service import ensure_owner, get_owned_lesson
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.quiz.models import USABLE_REVIEW, Question, Quiz, QuizAttempt, QuizQuestion, QuizStatus
from app.modules.quiz.questions import to_out
from app.modules.quiz.schemas import QuestionOut, QuizCreate, QuizOut, QuizPage, QuizUpdate


async def get_quiz_context(db: AsyncSession, quiz_id: uuid.UUID) -> tuple[Quiz, Course]:
    row = (
        await db.execute(
            select(Quiz, Course)
            .join(Lesson, Lesson.id == Quiz.lesson_id)
            .join(Section, Section.id == Lesson.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Quiz.id == quiz_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Quiz")
    return row[0], row[1]


def is_manager(user: User, course: Course) -> bool:
    return user.role == Role.admin or course.teacher_id == user.id


async def get_owned_quiz(db: AsyncSession, quiz_id: uuid.UUID, user: User) -> Quiz:
    quiz, course = await get_quiz_context(db, quiz_id)
    ensure_owner(course, user)
    return quiz


async def _lock_quiz(db: AsyncSession, quiz: Quiz) -> None:
    """Khóa dòng quiz và đọc lại trạng thái mới nhất (tránh sửa/xuất bản/xóa đồng thời)."""
    await db.refresh(quiz, with_for_update=True)


async def _lock_usable_questions(
    db: AsyncSession, lesson_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Khóa (FOR UPDATE, theo id để không deadlock) các câu hỏi và trả về id của những câu còn dùng được.
    Duyệt/sửa/loại câu hỏi (Task 16) cũng khóa dòng câu hỏi nên không chen vào giữa lúc kiểm tra và ghi."""
    if not ids:
        return set()
    rows = await db.scalars(
        select(Question.id)
        .where(
            Question.id.in_(ids),
            Question.lesson_id == lesson_id,
            Question.review_status.in_(USABLE_REVIEW),
        )
        .order_by(Question.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return set(rows.all())


async def _validate_question_ids(db: AsyncSession, lesson_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> None:
    if len(set(ids)) != len(ids):
        raise AppError("VALIDATION_ERROR", "Danh sách câu hỏi bị trùng", 422)
    found = await _lock_usable_questions(db, lesson_id, ids)
    invalid = [str(i) for i in ids if i not in found]
    if invalid:
        raise AppError(
            "VALIDATION_ERROR",
            "Chỉ thêm được câu hỏi đã duyệt của bài học này",
            422,
            {"invalid_question_ids": invalid},
        )


async def _set_questions(db: AsyncSession, quiz_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> None:
    await db.execute(delete(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id))
    db.add_all(
        [QuizQuestion(quiz_id=quiz_id, question_id=qid, position=i) for i, qid in enumerate(ids, start=1)]
    )


async def _question_counts(db: AsyncSession, quiz_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not quiz_ids:
        return {}
    rows = await db.execute(
        select(QuizQuestion.quiz_id, func.count())
        .where(QuizQuestion.quiz_id.in_(quiz_ids))
        .group_by(QuizQuestion.quiz_id)
    )
    return dict(rows.all())


async def _attempts_used(
    db: AsyncSession, user_id: uuid.UUID, quiz_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not quiz_ids:
        return {}
    rows = await db.execute(
        select(QuizAttempt.quiz_id, func.count())
        .where(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id.in_(quiz_ids))
        .group_by(QuizAttempt.quiz_id)
    )
    return dict(rows.all())


async def quiz_questions(db: AsyncSession, quiz_id: uuid.UUID) -> list[QuestionOut]:
    rows = await db.scalars(
        select(Question)
        .join(QuizQuestion, QuizQuestion.question_id == Question.id)
        .where(QuizQuestion.quiz_id == quiz_id)
        .order_by(QuizQuestion.position)
    )
    return [to_out(q) for q in rows]


async def _to_outs(
    db: AsyncSession, quizzes: Sequence[Quiz], user: User, manager: bool, *, with_questions: bool = False
) -> list[QuizOut]:
    ids = [q.id for q in quizzes]
    counts = await _question_counts(db, ids)
    used = {} if manager else await _attempts_used(db, user.id, ids)
    result = []
    for q in quizzes:
        out = QuizOut(
            id=q.id,
            lesson_id=q.lesson_id,
            title=q.title,
            max_attempts=q.max_attempts,
            pass_score=q.pass_score,
            status=q.status,
            question_count=counts.get(q.id, 0),
            created_at=q.created_at,
            attempts_used=None if manager else used.get(q.id, 0),
        )
        if manager and with_questions:
            out.questions = await quiz_questions(db, q.id)
        result.append(out)
    return result


async def create_quiz(db: AsyncSession, user: User, data: QuizCreate) -> QuizOut:
    lesson, _ = await get_owned_lesson(db, data.lesson_id, user)
    await _validate_question_ids(db, lesson.id, data.question_ids)
    quiz = Quiz(
        lesson_id=lesson.id,
        title=data.title,
        max_attempts=data.max_attempts,
        pass_score=data.pass_score,
        status=QuizStatus.draft,
    )
    db.add(quiz)
    await db.flush()
    await _set_questions(db, quiz.id, data.question_ids)
    await db.commit()
    return (await _to_outs(db, [quiz], user, True, with_questions=True))[0]


async def update_quiz(db: AsyncSession, user: User, quiz: Quiz, data: QuizUpdate) -> QuizOut:
    await _lock_quiz(db, quiz)
    if quiz.status == QuizStatus.published:
        # Quiz đã xuất bản bất biến: chỉ đổi được tiêu đề (cài đặt gửi lại đúng giá trị cũ thì bỏ qua)
        changes_settings = (data.max_attempts is not None and data.max_attempts != quiz.max_attempts) or (
            data.pass_score is not None and data.pass_score != quiz.pass_score
        )
        if data.question_ids is not None or changes_settings:
            raise AppError("INVALID_STATE", "Quiz đã xuất bản, chỉ đổi được tiêu đề", 409)
    elif data.question_ids is not None:
        await _validate_question_ids(db, quiz.lesson_id, data.question_ids)
        await _set_questions(db, quiz.id, data.question_ids)
    for field in ("title", "max_attempts", "pass_score"):
        value = getattr(data, field)
        if value is not None:
            setattr(quiz, field, value)
    await db.commit()
    return (await _to_outs(db, [quiz], user, True, with_questions=True))[0]


async def delete_quiz(db: AsyncSession, quiz: Quiz) -> None:
    await _lock_quiz(db, quiz)
    if quiz.status == QuizStatus.published:
        raise AppError("INVALID_STATE", "Quiz đã xuất bản, không xóa được", 409)
    attempts = await db.scalar(
        select(func.count()).select_from(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id)
    )
    if attempts:
        raise AppError("INVALID_STATE", "Quiz đã có bài làm, không xóa được", 409)
    await db.execute(delete(Quiz).where(Quiz.id == quiz.id))
    await db.commit()


async def publish_quiz(db: AsyncSession, user: User, quiz: Quiz) -> QuizOut:
    await _lock_quiz(db, quiz)
    if quiz.status == QuizStatus.published:
        raise AppError("INVALID_STATE", "Quiz đã được xuất bản", 409)
    ids = list(
        (
            await db.scalars(
                select(QuizQuestion.question_id)
                .where(QuizQuestion.quiz_id == quiz.id)
                .order_by(QuizQuestion.position)
            )
        ).all()
    )
    if not ids:
        raise AppError("INVALID_STATE", "Quiz cần ít nhất một câu hỏi trước khi xuất bản", 409)
    # Khóa câu hỏi rồi kiểm tra lại: câu vừa bị loại/chuyển trạng thái không lọt vào quiz đã xuất bản
    usable = await _lock_usable_questions(db, quiz.lesson_id, ids)
    invalid = [str(i) for i in ids if i not in usable]
    if invalid:
        raise AppError(
            "INVALID_STATE",
            "Quiz có câu hỏi chưa được duyệt, không xuất bản được",
            409,
            {"invalid_question_ids": invalid},
        )
    quiz.status = QuizStatus.published
    await db.commit()
    return (await _to_outs(db, [quiz], user, True, with_questions=True))[0]


async def list_lesson_quizzes(
    db: AsyncSession, user: User, lesson_id: uuid.UUID, params: PageParams
) -> QuizPage:
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    manager = is_manager(user, course)
    stmt = select(Quiz).where(Quiz.lesson_id == lesson.id).order_by(Quiz.created_at, Quiz.id)
    if not manager:
        stmt = stmt.where(Quiz.status == QuizStatus.published)
    total, paged = await paginate(db, stmt, params)
    items = await _to_outs(db, (await db.scalars(paged)).all(), user, manager)
    return QuizPage(items=items, total=total, page=params.page, size=params.size)


async def get_quiz_for_viewer(db: AsyncSession, user: User, quiz_id: uuid.UUID) -> QuizOut:
    quiz, course = await get_quiz_context(db, quiz_id)
    manager = is_manager(user, course)
    if not manager:
        if quiz.status != QuizStatus.published:
            raise not_found("Quiz")
        await ensure_lesson_access(db, quiz.lesson_id, user)
    return (await _to_outs(db, [quiz], user, manager, with_questions=True))[0]
