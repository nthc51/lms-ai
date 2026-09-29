import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_optional_user, require_staff, require_teacher_approved
from app.modules.auth.models import User
from app.modules.courses import service
from app.modules.courses.schemas import (
    CourseCreate,
    CourseDetail,
    CourseOut,
    CoursePage,
    CourseUpdate,
    LessonCreate,
    LessonOut,
    LessonUpdate,
    ReorderIn,
    SectionCreate,
    SectionOut,
    SectionUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["courses"])


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(
    data: CourseCreate, user: User = Depends(require_teacher_approved), db: AsyncSession = Depends(get_db)
):
    return await service.create_course(db, user, data)


@router.get("/teacher/courses", response_model=list[CourseOut])
async def my_teaching_courses(
    user: User = Depends(require_teacher_approved), db: AsyncSession = Depends(get_db)
):
    return await service.list_teacher_courses(db, user)


@router.patch("/courses/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: uuid.UUID,
    data: CourseUpdate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    course = await service.get_owned_course(db, course_id, user)
    return await service.update_course(db, course, data)


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(
    course_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
) -> None:
    course = await service.get_owned_course(db, course_id, user)
    await service.delete_course(db, course)


@router.post("/courses/{course_id}/publish", response_model=CourseOut)
async def publish_course(
    course_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
):
    course = await service.get_owned_course(db, course_id, user)
    return await service.publish_course(db, course)


@router.post("/courses/{course_id}/sections", response_model=SectionOut, status_code=201)
async def add_section(
    course_id: uuid.UUID,
    data: SectionCreate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    course = await service.get_owned_course(db, course_id, user)
    return await service.add_section(db, course, data)


@router.patch("/sections/{section_id}", response_model=SectionOut)
async def update_section(
    section_id: uuid.UUID,
    data: SectionUpdate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    section = await service.get_owned_section(db, section_id, user)
    return await service.update_section(db, section, data)


@router.delete("/sections/{section_id}", status_code=204)
async def delete_section(
    section_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
) -> None:
    section = await service.get_owned_section(db, section_id, user)
    await service.delete_section(db, section)


@router.post("/sections/{section_id}/lessons", response_model=LessonOut, status_code=201)
async def add_lesson(
    section_id: uuid.UUID,
    data: LessonCreate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    section = await service.get_owned_section(db, section_id, user)
    return await service.add_lesson(db, section, data)


@router.patch("/lessons/{lesson_id}", response_model=LessonOut)
async def update_lesson(
    lesson_id: uuid.UUID,
    data: LessonUpdate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.materials.assets import require_verified_asset
    from app.modules.materials.models import AssetKind

    lesson, _ = await service.get_owned_lesson(db, lesson_id, user)
    if data.video_asset_id is not None:
        await require_verified_asset(db, data.video_asset_id, user, AssetKind.video)
    return await service.update_lesson(db, lesson, data)


@router.delete("/lessons/{lesson_id}", status_code=204)
async def delete_lesson(
    lesson_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
) -> None:
    lesson, _ = await service.get_owned_lesson(db, lesson_id, user)
    await service.delete_lesson(db, lesson)


@router.patch("/courses/{course_id}/reorder", status_code=204)
async def reorder(
    course_id: uuid.UUID,
    data: ReorderIn,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
) -> None:
    course = await service.get_owned_course(db, course_id, user)
    await service.reorder(db, course, data)


@router.get("/courses", response_model=CoursePage)
async def catalog(
    q: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_published(db, q, page, size)


@router.get("/courses/{slug}", response_model=CourseDetail)
async def course_detail(
    slug: str, user: User | None = Depends(get_optional_user), db: AsyncSession = Depends(get_db)
):
    return await service.get_course_detail(db, slug, user)
