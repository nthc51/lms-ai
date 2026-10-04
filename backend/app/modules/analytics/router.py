import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_staff
from app.modules.analytics import service
from app.modules.analytics.schemas import CourseAnalytics
from app.modules.auth.models import User
from app.modules.courses.service import get_owned_course

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get("/courses/{course_id}/analytics", response_model=CourseAnalytics)
async def course_analytics(
    course_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
):
    course = await get_owned_course(db, course_id, user)  # người khác → 404 (spec 6.6)
    return await service.course_analytics(db, course)
