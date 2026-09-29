import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_role
from app.modules.auth.models import Role, User
from app.modules.enrollment import service
from app.modules.enrollment.schemas import EnrollmentOut, MyCourseOut

router = APIRouter(prefix="/api/v1", tags=["enrollment"])


@router.post("/courses/{course_id}/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(course_id: uuid.UUID, user: User = Depends(require_role(Role.student)),
                 db: AsyncSession = Depends(get_db)):
    return await service.enroll(db, user, course_id)


@router.get("/me/courses", response_model=list[MyCourseOut])
async def my_courses(user: User = Depends(require_role(Role.student)), db: AsyncSession = Depends(get_db)):
    return await service.my_courses(db, user)
