import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.time import utcnow
from app.ingestion.pipeline import error_text, ingest_pdf_source
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.queue import ArqQueue, JobQueue
from app.modules.jobs.service import finish_job
from app.modules.materials.models import Source, SourceStatus
from app.modules.quiz.generation import generate_questions_for_lesson
from app.modules.quiz.schemas import QuizGenerateIn

logger = logging.getLogger(__name__)

# job_timeout riêng cho từng loại job (spec K4), đơn vị giây. arq hủy job chạy quá thời gian này.
JOB_TIMEOUTS: dict[str, int] = {"ingest_pdf": 600, "quiz_gen": 900}
# Handler bị hủy sớm hơn job_timeout của arq một khoảng này, để run_job kịp ghi job + source failed
# ngay (arq hủy ở đúng job_timeout thì không còn cơ hội ghi, phải đợi sweeper).
JOB_TIMEOUT_MARGIN_S = 30
# Job 'processing' quá job_timeout + STALE_GRACE coi như worker đã chết giữa chừng
STALE_GRACE = timedelta(minutes=5)
STALE_JOB_ERROR = "Worker bị gián đoạn"
# Job 'pending' đã được enqueue lại một lần mà vẫn không có worker nhận (Redis mất job, arq hết hạn...)
PENDING_JOB_ERROR = "Không đưa được job vào hàng đợi"
# Loại job có ref_id trỏ tới sources.id: sweeper đánh dấu luôn source failed để giảng viên bấm "Xử lý lại".
# quiz_gen (ref_id = lessons.id) không cần: câu hỏi chỉ được ghi ở commit cuối cùng với job done, nên job bị
# sweeper chốt failed không để lại dữ liệu dở dang nào.
SOURCE_JOB_TYPES = frozenset({"ingest_pdf"})
# quiz_gen: lỗi nghiệp vụ (ValueError của generation, vd. NO_CHUNKS_ERROR) ghi nguyên văn vào job; lỗi khác
# (LLM/hạ tầng) ghi thông báo chung này, chi tiết nằm trong log.
QUIZ_GEN_ERROR = "Không sinh được câu hỏi do lỗi hệ thống hoặc dịch vụ AI, vui lòng thử lại sau"
QUIZ_GEN_PAYLOAD_ERROR = "Tham số sinh câu hỏi không hợp lệ"


def handler_timeout(job_type: str) -> float:
    """Thời gian tối đa cho handler của một loại job: job_timeout của arq trừ JOB_TIMEOUT_MARGIN_S.
    job_timeout không lớn hơn hẳn margin thì dùng một nửa job_timeout (luôn dương, luôn trước arq)."""
    timeout = JOB_TIMEOUTS[job_type]
    return timeout - JOB_TIMEOUT_MARGIN_S if timeout > 2 * JOB_TIMEOUT_MARGIN_S else timeout / 2


def timeout_error(timeout_s: float) -> str:
    return f"Quá thời gian xử lý ({timeout_s:g} giây)"


async def run_job(
    job_id: str,
    handler: Callable[[uuid.UUID], Awaitable[object]],
    session_factory: async_sessionmaker = SessionLocal,
    timeout_s: float | None = None,
) -> None:
    """Chạy một job: đánh dấu processing, gọi handler(ref_id), ghi done/failed.

    Handler có thể tự ghi trạng thái cuối của job trong cùng transaction với đối tượng nó xử lý
    (ingest_pdf làm vậy); nếu job vẫn còn processing sau handler thì ghi ở đây.
    timeout_s: handler chạy quá thời gian này thì bị hủy; job (và source nếu là job ingest_*) chuyển
    failed "Quá thời gian xử lý (N giây)" ngay trong cùng transaction.
    Không ném lỗi ra ngoài: trạng thái lỗi nằm trong bảng jobs, arq không tự retry."""
    jid = uuid.UUID(job_id)
    async with session_factory() as db:
        # Nhận job bằng một UPDATE có điều kiện (nguyên tử): job đã done/failed (kể cả vừa bị sweeper
        # đánh dấu) thì không bao giờ bị lật lại thành processing. 'processing' vẫn nhận: arq chạy lại
        # job của worker đã chết.
        ref_id = await db.scalar(
            update(Job)
            .where(Job.id == jid, Job.status.in_((JobStatus.pending, JobStatus.processing)))
            .values(status=JobStatus.processing, started_at=utcnow(), attempts=Job.attempts + 1)
            .returning(Job.ref_id)
        )
        if ref_id is None:
            logger.warning("Bỏ qua job %s (không tồn tại hoặc đã kết thúc)", job_id)
            return
        await db.commit()

    status, error = JobStatus.done, None
    deadline = asyncio.timeout(timeout_s)
    try:
        async with deadline:
            await handler(ref_id)
    except Exception as e:  # mọi lỗi đều phải được ghi vào job
        # Chỉ coi là quá hạn khi chính deadline của run_job đã hết (TimeoutError do handler tự ném,
        # vd. asyncio.wait_for bên trong, là lỗi thường → nhánh dưới).
        if deadline.expired():
            logger.error("Job %s quá thời gian xử lý (%s giây), đã hủy", job_id, timeout_s)
            async with session_factory() as db:
                # Cùng điều kiện với finish_job (chỉ job còn processing); source ingest_* failed cùng transaction
                if await _fail_jobs(
                    db,
                    (Job.id == jid, Job.status == JobStatus.processing),
                    timeout_error(timeout_s),
                    utcnow(),
                ):
                    await db.commit()
            return
        logger.exception("Job %s thất bại", job_id)
        status, error = JobStatus.failed, error_text(e)

    async with session_factory() as db:
        if await finish_job(db, jid, status, error):
            await db.commit()


async def ingest_pdf(ctx: dict, job_id: str) -> None:
    session_factory = ctx.get("session_factory", SessionLocal)

    async def handler(source_id: uuid.UUID) -> None:
        await ingest_pdf_source(
            source_id,
            storage=ctx["storage"],
            embedder=ctx["embedder"],
            vision=ctx["vision"],
            session_factory=session_factory,
            job_id=uuid.UUID(job_id),
        )

    await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("ingest_pdf"))


async def quiz_gen(ctx: dict, job_id: str) -> None:
    """Job sinh câu hỏi (spec 5.4). ref_id = lessons.id; tham số (count, difficulty) nằm trong jobs.payload.
    Câu hỏi và trạng thái done được ghi cùng transaction trong generate_questions_for_lesson; mọi lỗi để
    run_job ghi job failed (không có source nào phải đổi theo)."""
    session_factory = ctx.get("session_factory", SessionLocal)
    jid = uuid.UUID(job_id)

    async def handler(lesson_id: uuid.UUID) -> None:
        async with session_factory() as db:
            payload = await db.scalar(select(Job.payload).where(Job.id == jid))
        try:
            params = QuizGenerateIn.model_validate(payload or {})
        except ValidationError as e:
            raise ValueError(QUIZ_GEN_PAYLOAD_ERROR) from e
        try:
            await generate_questions_for_lesson(
                lesson_id,
                count=params.count,
                mix=params.difficulty.as_mapping(),
                llm=ctx["llm"],
                embedder=ctx["embedder"],
                job_id=jid,
                session_factory=session_factory,
            )
        except ValidationError as e:  # ValidationError cũng là ValueError nhưng message tiếng Anh
            raise RuntimeError(QUIZ_GEN_ERROR) from e
        except ValueError:  # thông báo tiếng Việt cho giảng viên (NO_CHUNKS_ERROR, ...)
            raise
        except Exception as e:  # run_job ghi log kèm traceback của lỗi gốc
            raise RuntimeError(QUIZ_GEN_ERROR) from e

    await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("quiz_gen"))


async def _fail_jobs(db, jobs_where, error: str, now) -> int:
    """Chuyển các job khớp điều kiện sang failed; source tương ứng (loại ingest_*) còn pending/processing
    cũng failed cùng lỗi. Chưa commit — caller commit để job và source đổi trạng thái trong cùng transaction."""
    rows = (
        await db.execute(
            update(Job)
            .where(*jobs_where)
            .values(status=JobStatus.failed, error_msg=error, finished_at=now)
            .returning(Job.type, Job.ref_id)
        )
    ).all()
    source_ids = [ref_id for type_, ref_id in rows if type_ in SOURCE_JOB_TYPES]
    if source_ids:
        await db.execute(
            update(Source)
            .where(
                Source.id.in_(source_ids), Source.status.in_((SourceStatus.pending, SourceStatus.processing))
            )
            .values(status=SourceStatus.failed, error_msg=error)
        )
    return len(rows)


async def _requeue_pending(db, queue_factory: Callable[[], JobQueue], cutoff, now) -> int:
    """Job 'pending' quá hạn và chưa từng được enqueue lại → enqueue lại đúng một lần (cùng _job_id nên
    arq tự bỏ qua nếu job vẫn còn trong Redis). requeued_at chỉ được ghi khi enqueue không lỗi;
    enqueue lỗi thì để nguyên cho lần sweep sau."""
    jobs = (
        await db.scalars(
            select(Job).where(
                Job.type.in_(JOB_TIMEOUTS),
                Job.status == JobStatus.pending,
                Job.created_at < cutoff,
                Job.requeued_at.is_(None),
            )
        )
    ).all()
    if not jobs:
        return 0
    queue = queue_factory()
    requeued = 0
    for job in jobs:
        try:
            await queue.enqueue(job)
        except Exception:
            logger.exception("Không enqueue lại được job %s, thử lại ở lần sweep sau", job.id)
            continue
        await db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == JobStatus.pending, Job.requeued_at.is_(None))
            .values(requeued_at=now)
        )
        await db.commit()
        requeued += 1
    return requeued


async def sweep_stale_jobs(ctx: dict) -> int:
    """Cron 5 phút một lần, dọn job bị treo. Trả về số job đã chuyển failed.

    - 'processing' quá job_timeout + STALE_GRACE → failed "Worker bị gián đoạn" (worker chết giữa chừng).
    - 'pending' đã được enqueue lại mà quá PENDING_JOB_REQUEUE_AFTER_MIN phút vẫn pending → failed
      "Không đưa được job vào hàng đợi".
    - 'pending' quá PENDING_JOB_REQUEUE_AFTER_MIN phút, chưa enqueue lại lần nào → enqueue lại một lần qua
      pool arq của worker (ctx['redis']; test truyền ctx['queue']).
    Source tương ứng còn pending/processing chuyển failed cùng transaction với job."""
    session_factory = ctx.get("session_factory", SessionLocal)
    now = utcnow()
    pending_after = timedelta(minutes=get_settings().pending_job_requeue_after_min)
    swept = 0
    async with session_factory() as db:
        for type_, timeout_s in JOB_TIMEOUTS.items():
            cutoff = now - timedelta(seconds=timeout_s) - STALE_GRACE
            swept += await _fail_jobs(
                db,
                (Job.type == type_, Job.status == JobStatus.processing, Job.started_at < cutoff),
                STALE_JOB_ERROR,
                now,
            )
        swept += await _fail_jobs(
            db,
            (
                Job.type.in_(JOB_TIMEOUTS),
                Job.status == JobStatus.pending,
                Job.requeued_at < now - pending_after,
            ),
            PENDING_JOB_ERROR,
            now,
        )
        await db.commit()
        requeued = await _requeue_pending(
            db, lambda: ctx.get("queue") or ArqQueue(pool=ctx["redis"]), now - pending_after, now
        )
    if swept:
        logger.warning("Đã đánh dấu %d job bị treo là failed", swept)
    if requeued:
        logger.warning("Đã enqueue lại %d job pending bị kẹt", requeued)
    return swept
