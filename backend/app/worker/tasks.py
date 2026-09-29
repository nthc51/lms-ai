import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.ingestion.pipeline import error_text, ingest_pdf_source
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import finish_job
from app.modules.materials.models import Source, SourceStatus

logger = logging.getLogger(__name__)

# job_timeout riêng cho từng loại job (spec K4), đơn vị giây. arq hủy job chạy quá thời gian này.
JOB_TIMEOUTS: dict[str, int] = {"ingest_pdf": 600}
# Job 'processing' quá job_timeout + STALE_GRACE coi như worker đã chết giữa chừng
STALE_GRACE = timedelta(minutes=5)
STALE_JOB_ERROR = "Worker bị gián đoạn"
# Loại job có ref_id trỏ tới sources.id: sweeper đánh dấu luôn source failed để giảng viên bấm "Xử lý lại"
SOURCE_JOB_TYPES = frozenset({"ingest_pdf"})


async def run_job(job_id: str, handler: Callable[[uuid.UUID], Awaitable[object]],
                  session_factory: async_sessionmaker = SessionLocal) -> None:
    """Chạy một job: đánh dấu processing, gọi handler(ref_id), ghi done/failed.

    Handler có thể tự ghi trạng thái cuối của job trong cùng transaction với đối tượng nó xử lý
    (ingest_pdf làm vậy); nếu job vẫn còn processing sau handler thì ghi ở đây.
    Không ném lỗi ra ngoài: trạng thái lỗi nằm trong bảng jobs, arq không tự retry."""
    jid = uuid.UUID(job_id)
    async with session_factory() as db:
        job = await db.get(Job, jid)
        if job is None or job.status in (JobStatus.done, JobStatus.failed):
            logger.warning("Bỏ qua job %s (không tồn tại hoặc đã kết thúc)", job_id)
            return
        job.status = JobStatus.processing
        job.attempts += 1
        job.started_at = utcnow()
        ref_id = job.ref_id
        await db.commit()

    status, error = JobStatus.done, None
    try:
        await handler(ref_id)
    except Exception as e:  # mọi lỗi đều phải được ghi vào job
        logger.exception("Job %s thất bại", job_id)
        status, error = JobStatus.failed, error_text(e)

    async with session_factory() as db:
        if await finish_job(db, jid, status, error):
            await db.commit()


async def ingest_pdf(ctx: dict, job_id: str) -> None:
    session_factory = ctx.get("session_factory", SessionLocal)

    async def handler(source_id: uuid.UUID) -> None:
        await ingest_pdf_source(source_id, storage=ctx["storage"], embedder=ctx["embedder"],
                                vision=ctx["vision"], session_factory=session_factory,
                                job_id=uuid.UUID(job_id))

    await run_job(job_id, handler, session_factory)


async def sweep_stale_jobs(ctx: dict) -> int:
    """Cron: job 'processing' quá job_timeout + STALE_GRACE → failed (worker chết/bị kill giữa chừng).
    Source tương ứng còn pending/processing cũng chuyển failed, cùng transaction. Trả về số job đã xử lý."""
    session_factory = ctx.get("session_factory", SessionLocal)
    now = utcnow()
    swept = 0
    async with session_factory() as db:
        for type_, timeout_s in JOB_TIMEOUTS.items():
            cutoff = now - timedelta(seconds=timeout_s) - STALE_GRACE
            ref_ids = (await db.scalars(
                update(Job)
                .where(Job.type == type_, Job.status == JobStatus.processing, Job.started_at < cutoff)
                .values(status=JobStatus.failed, error_msg=STALE_JOB_ERROR, finished_at=now)
                .returning(Job.ref_id))).all()
            swept += len(ref_ids)
            if ref_ids and type_ in SOURCE_JOB_TYPES:
                await db.execute(
                    update(Source)
                    .where(Source.id.in_(ref_ids),
                           Source.status.in_((SourceStatus.pending, SourceStatus.processing)))
                    .values(status=SourceStatus.failed, error_msg=STALE_JOB_ERROR))
        await db.commit()
    if swept:
        logger.warning("Đã đánh dấu %d job bị treo là failed", swept)
    return swept
