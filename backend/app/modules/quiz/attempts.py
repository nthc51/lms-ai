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

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.modules.auth.models import User
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.quiz.models import (
    AttemptAnswer,
    AttemptStatus,
    Question,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    QuizStatus,
)
from app.modules.quiz.quizzes import get_quiz_context
from app.modules.quiz.schemas import (
    AnswerIn,
    AnswerOut,
    AttemptOut,
    AttemptQuestion,
    AttemptResult,
    FinalAnswer,
    ResultQuestion,
    SubmitIn,
)

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


async def _user_attempts(db: AsyncSession, quiz_id: uuid.UUID, user_id: uuid.UUID) -> list[QuizAttempt]:
    """MỌI bài làm của học viên cho quiz (≤ max_attempts dòng) trong MỘT câu lệnh = một snapshot."""
    rows = await db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id)
        .order_by(QuizAttempt.attempt_no)
        .execution_options(populate_existing=True)
    )
    return list(rows.all())


def _decide(rows: Sequence[QuizAttempt], max_attempts: int) -> QuizAttempt | int:
    """Từ một snapshot: bài đang làm dở (trả lại nó) hoặc attempt_no cần tạo; hết lượt thì 409."""
    current = next((a for a in rows if a.status == AttemptStatus.in_progress), None)
    if current is not None:
        return current
    if len(rows) >= max_attempts:
        raise AppError("QUIZ_ATTEMPT_LIMIT", "Bạn đã dùng hết số lần làm bài", 409)
    return max((a.attempt_no for a in rows), default=0) + 1


async def start_attempt(db: AsyncSession, user: User, quiz_id: uuid.UUID) -> tuple[AttemptOut, bool]:
    """Trả (bài làm, mới_tạo). Đang có bài in_progress thì trả lại bài đó, nên mở 2 tab không tạo 2 bài.

    Mọi quyết định (trả bài dở / hết lượt / số thứ tự mới) lấy từ MỘT câu SELECT (một snapshot READ COMMITTED),
    nên không có kẽ hở giữa "kiểm tra bài dở" và "đếm số lượt". Hai tab cùng tạo: cả hai tính attempt_no = n + 1;
    UNIQUE (quiz_id, user_id, attempt_no) + ON CONFLICT DO NOTHING cho đúng một bên tạo được, bên kia rollback rồi
    đọc lại và quyết định lại bằng cùng hàm. Giới hạn đếm MỌI bài làm (completed, timed_out và cả in_progress)."""
    quiz, _ = await get_quiz_context(db, quiz_id)
    if quiz.status != QuizStatus.published:
        raise not_found("Quiz")
    await ensure_lesson_access(db, quiz.lesson_id, user)
    # đọc trước: rollback bên dưới làm hết hạn mọi object trong session (kể cả user)
    user_id, qid, max_attempts = user.id, quiz.id, quiz.max_attempts
    order = [
        str(x)
        for x in await db.scalars(
            select(QuizQuestion.question_id)
            .where(QuizQuestion.quiz_id == qid)
            .order_by(QuizQuestion.position)
        )
    ]
    for _ in range(3):
        decision = _decide(await _user_attempts(db, qid, user_id), max_attempts)
        if isinstance(decision, QuizAttempt):
            return await attempt_view(db, decision), False
        new_id = await db.scalar(
            pg_insert(QuizAttempt)
            .values(
                id=uuid.uuid4(),
                quiz_id=qid,
                user_id=user_id,
                attempt_no=decision,
                question_order=order,
                status=AttemptStatus.in_progress,
            )
            .on_conflict_do_nothing(constraint="uq_quiz_attempts_quiz_user_no")
            .returning(QuizAttempt.id)
        )
        if new_id is not None:
            await db.commit()
            return await attempt_view(db, await db.get(QuizAttempt, new_id)), True
        await db.rollback()  # tab khác vừa tạo bài cùng số thứ tự: đọc lại (một snapshot mới) ở vòng sau
    raise AppError("INVALID_STATE", "Không bắt đầu được bài làm, vui lòng thử lại", 409)


async def save_answer(
    db: AsyncSession, user: User, attempt_id: uuid.UUID, question_id: uuid.UUID, data: AnswerIn
) -> AnswerOut:
    """Autosave một đáp án (spec 6.5), ghi đè (lần ghi sau thắng). FOR SHARE trên dòng attempt: lệnh chốt bài
    (UPDATE) phải đợi autosave này commit xong, còn autosave đến sau khi đã chốt thì thấy status mới và nhận
    409 ATTEMPT_CLOSED. answered_at lấy theo đồng hồ DB (clock_timestamp, sau khi đã có khóa). Xem hợp đồng
    khóa ở đầu module."""
    attempt = await _own_attempt(db, attempt_id, user, lock_share=True)
    if attempt.status != AttemptStatus.in_progress:
        raise attempt_closed()
    questions = await _questions(db, attempt.question_order)
    _check_choice(questions, attempt.question_order, str(question_id), data.selected_option_id)
    stmt = pg_insert(AttemptAnswer).values(
        attempt_id=attempt.id,
        question_id=question_id,
        selected_option_id=data.selected_option_id,
        answered_at=func.clock_timestamp(),
    )
    answered_at = await db.scalar(
        stmt.on_conflict_do_update(
            index_elements=[AttemptAnswer.attempt_id, AttemptAnswer.question_id],
            set_={
                "selected_option_id": stmt.excluded.selected_option_id,
                "answered_at": stmt.excluded.answered_at,
            },
        ).returning(AttemptAnswer.answered_at)
    )
    await db.commit()
    return AnswerOut(
        question_id=question_id, selected_option_id=data.selected_option_id, answered_at=answered_at
    )


async def finalize_attempt(
    db: AsyncSession,
    attempt_id: uuid.UUID,
    *,
    status: AttemptStatus = AttemptStatus.completed,
    final_answers: Sequence[FinalAnswer] = (),
) -> bool:
    """Chốt bài nguyên tử (spec 4.3: UPDATE ... WHERE status='in_progress' RETURNING) rồi chấm, trong transaction
    của caller (chưa commit). Trả False nếu bài đã được chốt ở nơi khác (submit khác, cron B1): bỏ qua.
    Dùng lại cho cron B1 (status=timed_out).

    final_answers (caller đã validate) được upsert ngay sau UPDATE, trong cùng transaction nên kết quả vẫn là
    "payload thắng autosave rồi mới chốt" (spec 6.5). UPDATE là lệnh khóa ĐẦU TIÊN trên dòng attempt (hợp đồng
    khóa ở đầu module): autosave đang giữ FOR SHARE làm lệnh này đợi; không deadlock với autosave."""
    order = await db.scalar(
        update(QuizAttempt)
        .where(QuizAttempt.id == attempt_id, QuizAttempt.status == AttemptStatus.in_progress)
        .values(status=status, submitted_at=func.clock_timestamp())
        .returning(QuizAttempt.question_order)
    )
    if order is None:
        return False
    if final_answers:
        stmt = pg_insert(AttemptAnswer).values(
            [
                {
                    "attempt_id": attempt_id,
                    "question_id": a.question_id,
                    "selected_option_id": a.selected_option_id,
                    "answered_at": func.clock_timestamp(),
                }
                for a in final_answers
            ]
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
    # chấm từ chính các dòng trong DB sau upsert; câu bỏ trống không có dòng nên tính sai
    graded = await db.execute(
        update(AttemptAnswer)
        .where(AttemptAnswer.attempt_id == attempt_id, AttemptAnswer.question_id == Question.id)
        .values(is_correct=AttemptAnswer.selected_option_id == Question.correct_option_id)
        .returning(AttemptAnswer.question_id, AttemptAnswer.is_correct)
        .execution_options(synchronize_session=False)
    )
    in_order = set(order)
    correct = sum(1 for qid, ok in graded.all() if ok and str(qid) in in_order)
    score = round(correct * 100 / len(order), 2) if order else 0.0
    await db.execute(update(QuizAttempt).where(QuizAttempt.id == attempt_id).values(score=score))
    return True


async def submit_attempt(
    db: AsyncSession, user: User, attempt_id: uuid.UUID, data: SubmitIn
) -> AttemptResult:
    """Nộp bài (spec 6.5). final_answers không hợp lệ → 422 và bài vẫn mở (chưa ghi gì). Bài đã chốt (kể cả bị
    lần nộp khác chốt đồng thời) → 409 ATTEMPT_CLOSED. SELECT ở đây không khóa; khóa đầu tiên là UPDATE chốt bài."""
    attempt = await _own_attempt(db, attempt_id, user)
    if attempt.status != AttemptStatus.in_progress:
        raise attempt_closed()
    final = data.final_answers or []
    if final:
        if len({a.question_id for a in final}) != len(final):
            raise _invalid("Mỗi câu hỏi chỉ được gửi một đáp án")
        questions = await _questions(db, attempt.question_order)
        for a in final:
            _check_choice(questions, attempt.question_order, str(a.question_id), a.selected_option_id)
    aid, uid = attempt.id, user.id  # đọc trước: rollback làm hết hạn object trong session
    if not await finalize_attempt(db, aid, final_answers=final):
        await db.rollback()  # lần nộp khác (tab khác) hoặc cron vừa chốt bài trước
        raise attempt_closed()
    await db.commit()
    return await _result(db, uid, aid)


async def _result(db: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID) -> AttemptResult:
    attempt = await db.scalar(
        select(QuizAttempt)
        .where(QuizAttempt.id == attempt_id, QuizAttempt.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        raise not_found("Bài làm")
    if attempt.status not in FINISHED:
        raise AppError("INVALID_STATE", "Bài làm chưa được nộp", 409)
    quiz = await db.get(Quiz, attempt.quiz_id)
    questions = await _questions(db, attempt.question_order)
    answers = {
        str(qid): (option, ok)
        for qid, option, ok in await db.execute(
            select(
                AttemptAnswer.question_id, AttemptAnswer.selected_option_id, AttemptAnswer.is_correct
            ).where(AttemptAnswer.attempt_id == attempt.id)
        )
    }
    items = []
    for qid in attempt.question_order:
        q = questions.get(qid)
        if q is None:
            continue  # câu hỏi đã bị xóa sau khi bắt đầu: không hiển thị được (vẫn tính vào total)
        option, ok = answers.get(qid, (None, False))
        items.append(
            ResultQuestion(
                id=q.id,
                stem=q.stem,
                options=q.options,
                selected_option_id=option,
                correct_option_id=q.correct_option_id,
                is_correct=bool(ok),
                explanation=q.explanation,
            )
        )
    score = attempt.score or 0.0
    return AttemptResult(
        attempt_id=attempt.id,
        quiz_id=attempt.quiz_id,
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        score=score,
        passed=score >= quiz.pass_score,
        correct_count=sum(i.is_correct for i in items),
        total=len(attempt.question_order),
        submitted_at=attempt.submitted_at,
        questions=items,
    )


async def get_result(db: AsyncSession, user: User, attempt_id: uuid.UUID) -> AttemptResult:
    """Chỉ khi bài đã completed/timed_out (spec 6.4); chưa nộp → 409 INVALID_STATE; bài người khác → 404."""
    return await _result(db, user.id, attempt_id)
