import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_role, require_staff
from app.core.pagination import PageParams, page_params
from app.core.storage import Storage, get_storage
from app.modules.assignment import service
from app.modules.assignment.models import SubmissionStatus
from app.modules.assignment.schemas import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentPage,
    AssignmentUpdate,
    GradeIn,
    MySubmission,
    SubmissionDetail,
    SubmissionIn,
    SubmissionPage,
)
from app.modules.auth.models import Role, User
from app.modules.inbox.hub import NotificationHub, get_hub
from app.modules.jobs.queue import JobQueue, get_queue
from app.modules.materials.schemas import JobRef

router = APIRouter(prefix="/api/v1", tags=["assignment"])
_require_student = require_role(Role.student)


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
async def create_assignment(
    data: AssignmentCreate, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
):
    """Tạo bài tập (nháp) trong một bài học. Rubric 1–8 tiêu chí; key c1, c2, ... do server đặt."""
    return await service.create_assignment(db, user, data)


@router.get("/assignments", response_model=AssignmentPage)
async def lesson_assignments(
    lesson_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bài tập của bài học. Học viên chỉ thấy bài đã xuất bản, kèm bài nộp của mình (my_submission)."""
    return await service.list_lesson_assignments(db, user, lesson_id, params)


@router.get("/assignments/{assignment_id}", response_model=AssignmentOut)
async def assignment_detail(
    assignment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.get_assignment_for_viewer(db, user, assignment_id)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentOut)
async def update_assignment(
    assignment_id: uuid.UUID,
    data: AssignmentUpdate,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """409 INVALID_STATE khi đổi rubric lúc đã có bài nộp."""
    assignment, _ = await service.get_owned_assignment(db, assignment_id, user)
    return await service.update_assignment(db, user, assignment, data)


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
) -> None:
    """409 INVALID_STATE khi đã có bài nộp."""
    assignment, _ = await service.get_owned_assignment(db, assignment_id, user)
    await service.delete_assignment(db, assignment)


@router.post("/assignments/{assignment_id}/publish", response_model=AssignmentOut)
async def publish_assignment(
    assignment_id: uuid.UUID,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    hub: NotificationHub = Depends(get_hub),
):
    assignment, course = await service.get_owned_assignment(db, assignment_id, user)
    return await service.publish_assignment(db, user, assignment, course, hub)


@router.put("/assignments/{assignment_id}/submission", response_model=MySubmission)
async def submit(
    assignment_id: uuid.UUID,
    data: SubmissionIn,
    user: User = Depends(_require_student),
    db: AsyncSession = Depends(get_db),
    queue: JobQueue = Depends(get_queue),
):
    """Nộp hoặc nộp lại (thay bài cũ). 409 DEADLINE_PASSED khi quá hạn, 409 ALREADY_GRADED khi giảng viên đã chấm,
    400 INVALID_ASSET khi file không phải của mình / chưa upload xong."""
    return await service.submit(db, queue, user, assignment_id, data)


@router.get("/assignments/{assignment_id}/submissions", response_model=SubmissionPage)
async def assignment_submissions(
    assignment_id: uuid.UUID,
    status: SubmissionStatus | None = None,
    params: PageParams = Depends(page_params),
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Bài nộp của một bài tập: bài chờ giảng viên xác nhận lên trước."""
    assignment, _ = await service.get_owned_assignment(db, assignment_id, user)
    return await service.list_submissions(db, assignment, status, params)


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
async def submission_detail(
    submission_id: uuid.UUID,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    sub, _, _ = await service.get_owned_submission(db, submission_id, user)
    return await service.submission_detail(db, storage, sub)


@router.post("/submissions/{submission_id}/grade", response_model=SubmissionDetail)
async def grade_submission(
    submission_id: uuid.UUID,
    data: GradeIn,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
    hub: NotificationHub = Depends(get_hub),
):
    """Xác nhận điểm (đủ mọi tiêu chí, mỗi điểm 0..max_points; sai thì 422 INVALID_SCORES). Học viên được báo."""
    sub, assignment, _ = await service.get_owned_submission(db, submission_id, user)
    await service.grade(db, user, sub, assignment, data, hub)
    return await service.submission_detail(db, storage, sub)


@router.post("/submissions/{submission_id}/regrade", response_model=JobRef, status_code=202)
async def regrade_submission(
    submission_id: uuid.UUID,
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    queue: JobQueue = Depends(get_queue),
):
    """Cho AI chấm lại bài chưa được xác nhận. 409 ALREADY_GRADED nếu giảng viên đã chấm."""
    sub, _, _ = await service.get_owned_submission(db, submission_id, user)
    return JobRef(job_id=await service.regrade(db, queue, user, sub))
