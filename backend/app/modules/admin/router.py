import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_role
from app.core.pagination import PageParams, page_params
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminActionPage,
    AdminCourseOut,
    AdminCoursePage,
    AdminStats,
    AdminUserOut,
    AdminUserPage,
    OptionalReasonIn,
    ReasonIn,
)
from app.modules.auth.models import Role, User

# Mọi route ở đây chỉ dành cho quản trị viên (người khác nhận 403 FORBIDDEN).
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin_only = require_role(Role.admin)


@router.get("/stats", response_model=AdminStats)
async def get_stats(_: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    return await service.stats(db)


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    role: Literal["student", "teacher", "admin"] | None = None,
    status: Literal["pending", "approved", "rejected", "locked"] | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_users(db, Role(role) if role else None, status, q, params)


@router.post("/teachers/{user_id}/approve", response_model=AdminUserOut)
async def approve_teacher(
    user_id: uuid.UUID, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.approve_teacher(db, admin, user_id)


@router.post("/teachers/{user_id}/reject", response_model=AdminUserOut)
async def reject_teacher(
    user_id: uuid.UUID, data: ReasonIn, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.reject_teacher(db, admin, user_id, data.reason)


@router.post("/users/{user_id}/lock", response_model=AdminUserOut)
async def lock_user(
    user_id: uuid.UUID,
    data: OptionalReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.lock_user(db, admin, user_id, data.reason)


@router.post("/users/{user_id}/unlock", response_model=AdminUserOut)
async def unlock_user(
    user_id: uuid.UUID, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.unlock_user(db, admin, user_id)


@router.get("/courses", response_model=AdminCoursePage)
async def list_courses(
    status: Literal["published", "draft", "hidden"] | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_courses(db, status, q, params)


@router.post("/courses/{course_id}/hide", response_model=AdminCourseOut)
async def hide_course(
    course_id: uuid.UUID,
    data: ReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.hide_course(db, admin, course_id, data.reason)


@router.post("/courses/{course_id}/unhide", response_model=AdminCourseOut)
async def unhide_course(
    course_id: uuid.UUID, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.unhide_course(db, admin, course_id)


@router.get("/actions", response_model=AdminActionPage)
async def list_actions(
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_actions(db, params)
