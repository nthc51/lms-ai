import uuid

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.modules.jobs.models import ACTIVE_JOB_PREDICATE, Job, JobStatus
from app.modules.jobs.queue import JobQueue

ACTIVE = (JobStatus.pending, JobStatus.processing)


async def create_job(db: AsyncSession, type_: str, ref_id: uuid.UUID, ref_version: int = 0, *,
                     created_by: uuid.UUID | None) -> tuple[Job, bool]:
    """Tạo job nếu chưa có job đang chạy cho (type, ref_id, ref_version). Chưa commit — caller tự commit.

    Nhờ partial unique index uq_active_job, hai request đồng thời vẫn chỉ tạo được một job.
    created_by: id người dùng thao tác (NULL = job hệ thống). Nếu trả về job đang chạy sẵn thì giữ nguyên
    người tạo của job đó.
    """
    for _ in range(2):  # lặp lại một lần phòng khi job cũ vừa kết thúc giữa hai câu lệnh
        stmt = (
            pg_insert(Job)
            .values(id=uuid.uuid4(), type=type_, ref_id=ref_id, ref_version=ref_version,
                    status=JobStatus.pending, attempts=0, created_by=created_by)
            .on_conflict_do_nothing(index_elements=["type", "ref_id", "ref_version"],
                                    index_where=text(ACTIVE_JOB_PREDICATE))
            .returning(Job.id)
        )
        new_id = await db.scalar(stmt)
        if new_id is not None:
            return await db.get(Job, new_id), True
        existing = await db.scalar(select(Job).where(
            Job.type == type_, Job.ref_id == ref_id, Job.ref_version == ref_version, Job.status.in_(ACTIVE)))
        if existing is not None:
            return existing, False
    raise RuntimeError("Không tạo được job")


async def create_and_enqueue(db: AsyncSession, queue: JobQueue, type_: str, ref_id: uuid.UUID,
                             ref_version: int = 0, *, created_by: uuid.UUID | None) -> Job:
    """Commit mọi thay đổi đang chờ trong session cùng với job, rồi mới đẩy lên hàng đợi."""
    job, created = await create_job(db, type_, ref_id, ref_version, created_by=created_by)
    await db.commit()
    if created:
        await queue.enqueue(job)
    return job


async def finish_job(db: AsyncSession, job_id: uuid.UUID, status: JobStatus, error_msg: str | None = None) -> bool:
    """Ghi trạng thái cuối (done/failed) cho job đang processing. Chưa commit — caller commit chung
    với thay đổi của đối tượng mà job xử lý (vd. source), để hai trạng thái luôn khớp nhau.

    Trả về False nếu job không còn processing (vd. đã bị sweeper đánh dấu failed): caller không được ghi kết quả.
    """
    new_id = await db.scalar(
        update(Job).where(Job.id == job_id, Job.status == JobStatus.processing)
        .values(status=status, error_msg=error_msg, finished_at=utcnow())
        .returning(Job.id))
    return new_id is not None
