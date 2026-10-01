import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models import Role
from app.modules.courses.models import Lesson
from app.modules.jobs.models import Job
from app.modules.jobs.service import create_job
from app.modules.quiz.models import (
    AttemptAnswer,
    AttemptStatus,
    Question,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    QuizStatus,
    ReviewStatus,
)
from tests.factories import make_lesson, make_question, make_user


async def _quiz(db):
    teacher = await make_user(db)
    student = await make_user(db, Role.student)
    _, lesson = await make_lesson(db, teacher)
    question = await make_question(db, lesson.id)
    quiz = Quiz(lesson_id=lesson.id, title="Quiz 1")
    db.add(quiz)
    await db.flush()
    db.add(QuizQuestion(quiz_id=quiz.id, question_id=question.id, position=1))
    await db.commit()
    return lesson, student, question, quiz


async def test_defaults(db):
    _, _, question, quiz = await _quiz(db)
    quiz = await db.get(Quiz, quiz.id, populate_existing=True)
    assert (quiz.status, quiz.max_attempts, quiz.pass_score, quiz.shuffle, quiz.time_limit_sec) == (
        QuizStatus.draft,
        1,
        50.0,
        False,
        None,
    )
    q = await db.get(Question, question.id, populate_existing=True)
    assert q.self_check_flag is False and q.review_status == ReviewStatus.approved


async def test_attempt_number_is_unique_per_user_and_quiz(db):
    _, student, _, quiz = await _quiz(db)
    db.add(QuizAttempt(quiz_id=quiz.id, user_id=student.id, attempt_no=1, question_order=[]))
    await db.commit()
    db.add(QuizAttempt(quiz_id=quiz.id, user_id=student.id, attempt_no=1, question_order=[]))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_deleting_lesson_cascades_everything(db):
    lesson, student, question, quiz = await _quiz(db)
    attempt = QuizAttempt(
        quiz_id=quiz.id, user_id=student.id, attempt_no=1, question_order=[str(question.id)]
    )
    db.add(attempt)
    await db.flush()
    db.add(AttemptAnswer(attempt_id=attempt.id, question_id=question.id, selected_option_id="A"))
    await db.commit()
    attempt = await db.get(QuizAttempt, attempt.id, populate_existing=True)
    assert attempt.status == AttemptStatus.in_progress and attempt.started_at is not None
    await db.execute(delete(Lesson).where(Lesson.id == lesson.id))
    await db.commit()
    for model in (Question, Quiz, QuizQuestion, QuizAttempt, AttemptAnswer):
        assert await db.scalar(select(func.count()).select_from(model)) == 0


async def test_job_payload_roundtrip(db):
    job, _ = await create_job(db, "quiz_gen", uuid.uuid4(), created_by=None)
    job.payload = {"count": 5}
    await db.commit()
    assert (await db.get(Job, job.id, populate_existing=True)).payload == {"count": 5}
