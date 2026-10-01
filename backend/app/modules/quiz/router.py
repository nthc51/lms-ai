import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_staff
from app.core.pagination import PageParams, page_params
from app.modules.auth.models import User
from app.modules.jobs.queue import JobQueue, get_queue
from app.modules.materials.schemas import JobRef
from app.modules.quiz import questions, quizzes
from app.modules.quiz.models import ReviewStatus
from app.modules.quiz.schemas import (
    QuestionOut,
    QuestionPage,
    QuestionReview,
    QuizCreate,
    QuizGenerateIn,
    QuizOut,
    QuizPage,
    QuizUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["quiz"])


@router.post("/lessons/{lesson_id}/questions/generate", response_model=JobRef, status_code=202)
async def generate_questions(
    lesson_id: uuid.UUID,
    data: QuizGenerateIn | None = None,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    queue: JobQueue = Depends(get_queue),
):
    job = await questions.request_generation(db, queue, user, lesson_id, data or QuizGenerateIn())
    return JobRef(job_id=job.id)


@router.get("/lessons/{lesson_id}/questions", response_model=QuestionPage)
async def lesson_questions(
    lesson_id: uuid.UUID,
    review_status: ReviewStatus | None = None,
    params: PageParams = Depends(page_params),
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    return await questions.list_questions(db, user, lesson_id, review_status, params)


@router.patch("/questions/{question_id}", response_model=QuestionOut)
async def review_question(
    question_id: uuid.UUID,
    data: QuestionReview,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    question = await questions.get_owned_question(db, question_id, user)
    return await questions.review_question(db, question, data)


@router.post("/quizzes", response_model=QuizOut, status_code=201)
async def create_quiz(
    data: QuizCreate, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
):
    return await quizzes.create_quiz(db, user, data)


@router.get("/quizzes", response_model=QuizPage)
async def lesson_quizzes(
    lesson_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await quizzes.list_lesson_quizzes(db, user, lesson_id, params)


@router.get("/quizzes/{quiz_id}", response_model=QuizOut)
async def quiz_detail(
    quiz_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await quizzes.get_quiz_for_viewer(db, user, quiz_id)


@router.patch("/quizzes/{quiz_id}", response_model=QuizOut)
async def update_quiz(
    quiz_id: uuid.UUID,
    data: QuizUpdate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    quiz = await quizzes.get_owned_quiz(db, quiz_id, user)
    return await quizzes.update_quiz(db, user, quiz, data)


@router.delete("/quizzes/{quiz_id}", status_code=204)
async def delete_quiz(
    quiz_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
) -> None:
    quiz = await quizzes.get_owned_quiz(db, quiz_id, user)
    await quizzes.delete_quiz(db, quiz)


@router.post("/quizzes/{quiz_id}/publish", response_model=QuizOut)
async def publish_quiz(
    quiz_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
):
    quiz = await quizzes.get_owned_quiz(db, quiz_id, user)
    return await quizzes.publish_quiz(db, user, quiz)
