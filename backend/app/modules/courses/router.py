import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_staff, require_teacher_approved
from app.modules.auth.models import User
from app.modules.courses import service
from app.modules.courses.schemas import CourseCreate, CourseOut, CourseUpdate

router = APIRouter(prefix="/api/v1", tags=["courses"])


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(data: CourseCreate, user: User = Depends(require_teacher_approved),
                        db: AsyncSession = Depends(get_db)):
    return await service.create_course(db, user, data)


@router.get("/teacher/courses", response_model=list[CourseOut])
async def my_teaching_courses(user: User = Depends(require_teacher_approved), db: AsyncSession = Depends(get_db)):
    return await service.list_teacher_courses(db, user)


@router.patch("/courses/{course_id}", response_model=CourseOut)
async def update_course(course_id: uuid.UUID, data: CourseUpdate, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)):
    course = await service.get_owned_course(db, course_id, user)
    return await service.update_course(db, course, data)


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(course_id: uuid.UUID, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)) -> None:
    course = await service.get_owned_course(db, course_id, user)
    await service.delete_course(db, course)


@router.post("/courses/{course_id}/publish", response_model=CourseOut)
async def publish_course(course_id: uuid.UUID, user: User = Depends(require_staff),
                         db: AsyncSession = Depends(get_db)):
    course = await service.get_owned_course(db, course_id, user)
    return await service.publish_course(db, course)
