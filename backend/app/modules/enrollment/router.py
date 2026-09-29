import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_role
from app.core.pagination import PageParams, page_params
from app.modules.auth.models import Role, User
from app.modules.enrollment import service
from app.modules.enrollment.schemas import EnrollmentOut, LessonDetail, MyCoursePage, ProgressIn, ProgressOut

router = APIRouter(prefix="/api/v1", tags=["enrollment"])

_require_student = require_role(Role.student)


@router.post("/courses/{course_id}/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(
    course_id: uuid.UUID, user: User = Depends(_require_student), db: AsyncSession = Depends(get_db)
):
    return await service.enroll(db, user, course_id)


@router.get("/me/courses", response_model=MyCoursePage)
async def my_courses(
    params: PageParams = Depends(page_params),
    user: User = Depends(_require_student),
    db: AsyncSession = Depends(get_db),
):
    return await service.my_courses(db, user, params)


@router.get("/lessons/{lesson_id}", response_model=LessonDetail)
async def lesson_detail(
    lesson_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.get_lesson_detail(db, lesson_id, user)


@router.put("/lessons/{lesson_id}/progress", response_model=ProgressOut)
async def save_progress(
    lesson_id: uuid.UUID,
    data: ProgressIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_progress(db, lesson_id, user, data)
