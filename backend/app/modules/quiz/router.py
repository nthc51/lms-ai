import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_staff
from app.core.pagination import PageParams, page_params
from app.modules.auth.models import User
from app.modules.jobs.queue import JobQueue, get_queue
from app.modules.materials.schemas import JobRef
from app.modules.quiz import questions
from app.modules.quiz.models import ReviewStatus
from app.modules.quiz.schemas import QuestionOut, QuestionPage, QuestionReview, QuizGenerateIn

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
