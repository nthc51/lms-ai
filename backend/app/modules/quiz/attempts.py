"""Học viên làm quiz — phần A7 (spec 4.3, 6.5): bắt đầu, autosave, nộp, chấm, xem kết quả.
Tính giờ/deadline, xáo trộn câu hỏi và cron chốt bài khi hết giờ là B1 (tuần 3).

Hợp đồng khóa giữa autosave và chốt bài (Task 19 / cron B1 phải tuân theo):
- autosave: `SELECT ... FOR SHARE` dòng quiz_attempts, kiểm tra status = in_progress, rồi upsert
  attempt_answers, tất cả trong một transaction.
- chốt bài: `UPDATE quiz_attempts SET status=... WHERE id=... AND status='in_progress' RETURNING` là lệnh
  ĐẦU TIÊN của transaction (khóa dòng attempt trước, rồi mới ghi attempt_answers và chấm, cùng transaction).
Nhờ đó autosave đang chạy làm lệnh chốt phải đợi, autosave đến sau thấy status mới và nhận 409; hai bên đều
khóa dòng attempt trước rồi mới đụng attempt_answers nên không deadlock."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.time import utcnow
from app.modules.auth.models import User
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.quiz.models import (
    AttemptAnswer,
    AttemptStatus,
    Question,
    QuizAttempt,
    QuizQuestion,
    QuizStatus,
)
from app.modules.quiz.quizzes import get_quiz_context
from app.modules.quiz.schemas import AnswerIn, AnswerOut, AttemptOut, AttemptQuestion

FINISHED = (AttemptStatus.completed, AttemptStatus.timed_out)


def attempt_closed() -> AppError:
    return AppError("ATTEMPT_CLOSED", "Bài làm đã được nộp, không thay đổi được nữa", 409)


def _invalid(message: str) -> AppError:
    return AppError("VALIDATION_ERROR", message, 422)


async def _questions(db: AsyncSession, order: Sequence[str]) -> dict[str, Question]:
    if not order:
        return {}
    rows = await db.scalars(select(Question).where(Question.id.in_([uuid.UUID(q) for q in order])))
    return {str(q.id): q for q in rows}


def _check_choice(
    questions: dict[str, Question], order: Sequence[str], question_id: str, option_id: str
) -> None:
    """spec 6.5: question_id phải nằm trong question_order của bài làm, option phải là lựa chọn của câu đó."""
    if question_id not in order or question_id not in questions:
        raise _invalid("Câu hỏi không thuộc bài làm này")
    if option_id not in {o["id"] for o in questions[question_id].options}:
        raise _invalid("Lựa chọn không hợp lệ")


async def _own_attempt(
    db: AsyncSession, attempt_id: uuid.UUID, user: User, *, lock_share: bool = False
) -> QuizAttempt:
    """Bài làm của chính người gọi; bài của người khác trả 404 (không lộ là có tồn tại)."""
    stmt = select(QuizAttempt).where(QuizAttempt.id == attempt_id, QuizAttempt.user_id == user.id)
    if lock_share:
        stmt = stmt.with_for_update(read=True)
    attempt = await db.scalar(stmt.execution_options(populate_existing=True))
    if attempt is None:
        raise not_found("Bài làm")
    return attempt


async def attempt_view(db: AsyncSession, attempt: QuizAttempt) -> AttemptOut:
    questions = await _questions(db, attempt.question_order)
    answers = (
        await db.execute(
            select(AttemptAnswer.question_id, AttemptAnswer.selected_option_id).where(
                AttemptAnswer.attempt_id == attempt.id
            )
        )
    ).all()
    return AttemptOut(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        questions=[
            AttemptQuestion(id=q.id, stem=q.stem, options=q.options)
            for qid in attempt.question_order
            if (q := questions.get(qid)) is not None
        ],
        answers={str(qid): option for qid, option in answers},
    )


async def start_attempt(db: AsyncSession, user: User, quiz_id: uuid.UUID) -> tuple[AttemptOut, bool]:
    """Trả (bài làm, mới_tạo). Đang có bài in_progress thì trả lại bài đó, nên mở 2 tab không tạo 2 bài.

    Hai tab bấm cùng lúc: cả hai tính attempt_no = n + 1; UNIQUE (quiz_id, user_id, attempt_no) + ON CONFLICT
    DO NOTHING cho đúng một bên tạo được, bên kia rollback rồi đọc lại bài vừa tạo. Giới hạn số lần đếm MỌI
    bài làm (completed, timed_out và cả in_progress); attempt_no liên tục nên cũng không vượt được giới hạn."""
    quiz, _ = await get_quiz_context(db, quiz_id)
    if quiz.status != QuizStatus.published:
        raise not_found("Quiz")
    await ensure_lesson_access(db, quiz.lesson_id, user)
    # đọc trước: rollback bên dưới làm hết hạn mọi object trong session (kể cả user)
    user_id, qid, max_attempts = user.id, quiz.id, quiz.max_attempts
    for _ in range(2):
        current = await db.scalar(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id == qid,
                QuizAttempt.user_id == user_id,
                QuizAttempt.status == AttemptStatus.in_progress,
            )
        )
        if current is not None:
            return await attempt_view(db, current), False
        used, last_no = (
            await db.execute(
                select(func.count(QuizAttempt.id), func.coalesce(func.max(QuizAttempt.attempt_no), 0)).where(
                    QuizAttempt.quiz_id == qid, QuizAttempt.user_id == user_id
                )
            )
        ).one()
        if used >= max_attempts:
            raise AppError("QUIZ_ATTEMPT_LIMIT", "Bạn đã dùng hết số lần làm bài", 409)
        order = [
            str(x)
            for x in await db.scalars(
                select(QuizQuestion.question_id)
                .where(QuizQuestion.quiz_id == qid)
                .order_by(QuizQuestion.position)
            )
        ]
        new_id = await db.scalar(
            pg_insert(QuizAttempt)
            .values(
                id=uuid.uuid4(),
                quiz_id=qid,
                user_id=user_id,
                attempt_no=last_no + 1,
                question_order=order,
                status=AttemptStatus.in_progress,
            )
            .on_conflict_do_nothing(constraint="uq_quiz_attempts_quiz_user_no")
            .returning(QuizAttempt.id)
        )
        if new_id is not None:
            await db.commit()
            return await attempt_view(db, await db.get(QuizAttempt, new_id)), True
        await db.rollback()  # tab khác vừa tạo bài cùng số thứ tự: đọc lại ở vòng sau
    raise AppError("INVALID_STATE", "Không bắt đầu được bài làm, vui lòng thử lại", 409)


async def save_answer(
    db: AsyncSession, user: User, attempt_id: uuid.UUID, question_id: uuid.UUID, data: AnswerIn
) -> AnswerOut:
    """Autosave một đáp án (spec 6.5), ghi đè (lần ghi sau thắng). FOR SHARE trên dòng attempt: lệnh chốt bài
    (UPDATE) phải đợi autosave này commit xong, còn autosave đến sau khi đã chốt thì thấy status mới và nhận
    409 ATTEMPT_CLOSED. Xem hợp đồng khóa ở đầu module."""
    attempt = await _own_attempt(db, attempt_id, user, lock_share=True)
    if attempt.status != AttemptStatus.in_progress:
        raise attempt_closed()
    questions = await _questions(db, attempt.question_order)
    _check_choice(questions, attempt.question_order, str(question_id), data.selected_option_id)
    now = utcnow()
    stmt = pg_insert(AttemptAnswer).values(
        attempt_id=attempt.id,
        question_id=question_id,
        selected_option_id=data.selected_option_id,
        answered_at=now,
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[AttemptAnswer.attempt_id, AttemptAnswer.question_id],
            set_={
                "selected_option_id": stmt.excluded.selected_option_id,
                "answered_at": stmt.excluded.answered_at,
            },
        )
    )
    await db.commit()
    return AnswerOut(question_id=question_id, selected_option_id=data.selected_option_id, answered_at=now)
