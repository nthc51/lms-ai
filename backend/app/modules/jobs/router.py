import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.modules.auth.models import Role, User
from app.modules.jobs.models import Job, JobStatus

router = APIRouter(prefix="/api/v1", tags=["jobs"])


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: JobStatus
    attempts: int
    error_msg: str | None
    finished_at: datetime | None


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    # Chỉ người tạo job hoặc admin được xem; người khác (kể cả với job hệ thống created_by NULL)
    # nhận 404 giống hệt job không tồn tại, để không lộ id job.
    if job is None or (user.role != Role.admin and job.created_by != user.id):
        raise not_found("Job")
    return job
