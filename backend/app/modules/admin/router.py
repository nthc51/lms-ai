import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
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
from app.modules.analytics.schemas import TutorFeedbackPage
from app.modules.analytics.service import downvoted_answers
from app.modules.auth.models import Role, User
from app.modules.notify.outbox import MailKicker, get_mail_kicker

# Mọi route ở đây chỉ dành cho quản trị viên (người khác nhận 403 FORBIDDEN).
# Thao tác có gửi email (duyệt, từ chối, khóa, ẩn/hiện khóa) gọi kicker sau khi commit.
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin_only = require_role(Role.admin)
UserRole = Literal["student", "teacher", "admin"]
UserStatus = Literal["pending", "approved", "rejected", "locked", "unverified"]


@router.get("/stats", response_model=AdminStats)
async def get_stats(_: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    return await service.stats(db)


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    role: UserRole | None = None,
    status: UserStatus | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_users(db, Role(role) if role else None, status, q, params)


@router.get("/users/export", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
async def export_users(
    role: UserRole | None = None,
    status: UserStatus | None = None,
    q: str | None = Query(None, max_length=100),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    """CSV theo bộ lọc đang xem (tối đa 10.000 dòng)."""
    body = await service.export_users_csv(db, Role(role) if role else None, status, q)
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nguoi-dung.csv"'},
    )


@router.post("/teachers/{user_id}/approve", response_model=AdminUserOut)
async def approve_teacher(
    user_id: uuid.UUID,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.approve_teacher(db, admin, user_id)
    await kicker.kick()
    return out


@router.post("/teachers/{user_id}/reject", response_model=AdminUserOut)
async def reject_teacher(
    user_id: uuid.UUID,
    data: ReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.reject_teacher(db, admin, user_id, data.reason)
    await kicker.kick()
    return out


@router.post("/users/{user_id}/lock", response_model=AdminUserOut)
async def lock_user(
    user_id: uuid.UUID,
    data: OptionalReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.lock_user(db, admin, user_id, data.reason)
    await kicker.kick()
    return out


@router.post("/users/{user_id}/unlock", response_model=AdminUserOut)
async def unlock_user(
    user_id: uuid.UUID,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
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
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.hide_course(db, admin, course_id, data.reason)
    await kicker.kick()
    return out


@router.post("/courses/{course_id}/unhide", response_model=AdminCourseOut)
async def unhide_course(
    course_id: uuid.UUID,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.unhide_course(db, admin, course_id)
    await kicker.kick()
    return out


@router.get("/actions", response_model=AdminActionPage)
async def list_actions(
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_actions(db, params)


@router.get("/tutor-feedback", response_model=TutorFeedbackPage)
async def tutor_feedback(
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    """Câu trả lời AI Tutor bị học viên bấm 👎 trên mọi khóa, mới nhất trước (kèm tên học viên)."""
    return await downvoted_answers(db, params, with_student=True)
