"""Câu hỏi của bài học: yêu cầu AI sinh (job quiz_gen) và màn duyệt của giảng viên (spec 5.4, 6.4)."""

import uuid

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.modules.auth.models import User
from app.modules.courses.models import Course, Lesson, Section
from app.modules.courses.service import ensure_owner, get_owned_lesson
from app.modules.jobs.models import Job
from app.modules.jobs.queue import JobQueue
from app.modules.jobs.service import create_and_enqueue
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.modules.quiz.models import Question, Quiz, QuizQuestion, QuizStatus, ReviewStatus
from app.modules.quiz.schemas import QuestionOut, QuestionPage, QuestionReview, QuizGenerateIn
from app.modules.quiz.selection import MIN_CHUNK_TOKENS
from app.modules.quiz.validation import QuestionContent

QUIZ_GEN = "quiz_gen"  # job.type = tên hàm trong worker; job.ref_id = lessons.id
EXCERPT_CHARS = 400


async def request_generation(
    db: AsyncSession, queue: JobQueue, user: User, lesson_id: uuid.UUID, data: QuizGenerateIn
) -> Job:
    lesson, _ = await get_owned_lesson(db, lesson_id, user)
    eligible = await db.scalar(
        select(func.count(Chunk.id))
        .join(Source, Source.id == Chunk.source_id)
        .where(
            Chunk.lesson_id == lesson.id,
            Source.status == SourceStatus.ready,
            Chunk.token_count >= MIN_CHUNK_TOKENS,
        )
    )
    if not eligible:
        raise AppError("INVALID_STATE", "Bài học chưa có tài liệu xử lý xong (đủ dài) để sinh câu hỏi", 409)
    # Bấm "Sinh câu hỏi" 2 lần: uq_active_job chỉ cho một job quiz_gen đang chạy mỗi bài, lần sau nhận lại job đó
    return await create_and_enqueue(
        db, queue, QUIZ_GEN, lesson.id, created_by=user.id, payload=data.model_dump(mode="json")
    )


def to_out(q: Question, page_no: int | None = None, content: str | None = None) -> QuestionOut:
    return QuestionOut.model_validate(q).model_copy(
        update={"source_page_no": page_no, "source_excerpt": content[:EXCERPT_CHARS] if content else None}
    )


async def list_questions(
    db: AsyncSession, user: User, lesson_id: uuid.UUID, review_status: ReviewStatus | None, params: PageParams
) -> QuestionPage:
    await get_owned_lesson(db, lesson_id, user)
    stmt = (
        select(Question, Chunk.page_no, Chunk.content)
        .outerjoin(Chunk, Chunk.id == Question.source_chunk_id)
        .where(Question.lesson_id == lesson_id)
        .order_by(Question.created_at.desc(), Question.id.desc())
    )
    if review_status is not None:
        stmt = stmt.where(Question.review_status == review_status)
    total, paged = await paginate(db, stmt, params)
    rows = (await db.execute(paged)).all()
    return QuestionPage(
        items=[to_out(q, page, content) for q, page, content in rows],
        total=total,
        page=params.page,
        size=params.size,
    )


async def get_owned_question(db: AsyncSession, question_id: uuid.UUID, user: User) -> Question:
    row = (
        await db.execute(
            select(Question, Course)
            .join(Lesson, Lesson.id == Question.lesson_id)
            .join(Section, Section.id == Lesson.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Question.id == question_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Câu hỏi")
    ensure_owner(row[1], user)
    return row[0]


def _invalid_question(e: ValidationError) -> AppError:
    errors = [{"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in e.errors()]
    return AppError("VALIDATION_ERROR", "Câu hỏi không hợp lệ", 422, {"errors": errors})


async def review_question(db: AsyncSession, question: Question, data: QuestionReview) -> QuestionOut:
    quiz_statuses = set(
        (
            await db.scalars(
                select(Quiz.status)
                .join(QuizQuestion, QuizQuestion.quiz_id == Quiz.id)
                .where(QuizQuestion.question_id == question.id)
            )
        ).all()
    )
    if data.action != "approve" and QuizStatus.published in quiz_statuses:
        raise AppError(
            "INVALID_STATE", "Câu hỏi đang nằm trong quiz đã xuất bản, không sửa hay loại được", 409
        )
    if data.action == "reject":
        if quiz_statuses:
            raise AppError("INVALID_STATE", "Gỡ câu hỏi khỏi quiz trước khi loại", 409)
        question.review_status = ReviewStatus.rejected
    elif data.action == "approve":
        # đã sửa rồi duyệt thì giữ "edited" (thống kê giữ/sửa/loại của spec 9.3)
        if question.review_status != ReviewStatus.edited:
            question.review_status = ReviewStatus.approved
    else:
        changes = data.model_dump(exclude={"action"}, exclude_none=True)
        if not changes:
            raise AppError("VALIDATION_ERROR", "Cần gửi ít nhất một trường cần sửa", 422)
        current = {
            "stem": question.stem,
            "options": question.options,
            "correct_option_id": question.correct_option_id,
            "explanation": question.explanation,
            "difficulty": question.difficulty,
        }
        try:
            content = QuestionContent.model_validate({**current, **changes}).normalized()
        except ValidationError as e:
            raise _invalid_question(e) from None
        question.stem = content.stem
        question.options = [o.model_dump() for o in content.options]
        question.correct_option_id = content.correct_option_id
        question.explanation = content.explanation
        question.difficulty = content.difficulty
        question.review_status = ReviewStatus.edited  # ai_original giữ nguyên bản AI (spec 5.4 bước 7)
    await db.commit()
    return to_out(question)
