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
from app.core.storage import get_storage
from app.core.time import utcnow
from app.ingestion.pipeline import error_text, ingest_pdf_source
from app.modules.assignment.grading import fail_unfinished as fail_unfinished_grading
from app.modules.assignment.grading import grade_submission as run_grading
from app.modules.courses.models import Course, Lesson, Section
from app.modules.inbox import service as inbox
from app.modules.inbox.hub import get_hub
from app.modules.inbox.models import NotificationKind
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.queue import ArqQueue, JobQueue
from app.modules.jobs.service import create_and_enqueue, finish_job
from app.modules.materials.models import Asset, Source, SourceStatus
from app.modules.quiz.attempts import finalize_overdue_attempts
from app.modules.quiz.generation import QuizGenerationError, generate_questions_for_lesson
from app.modules.quiz.schemas import QuizGenerateIn
from app.modules.studio.jobs import run_notes_synth, run_source_guide, run_studio
from app.modules.tutor.waiting import answer_waiting, has_waiting

logger = logging.getLogger(__name__)

# job_timeout riêng cho từng loại job (spec K4), đơn vị giây. arq hủy job chạy quá thời gian này.
JOB_TIMEOUTS: dict[str, int] = {
    "ingest_pdf": 600,
    "quiz_gen": 900,
    "source_guide": 300,
    "studio_gen": 900,
    "notes_synth": 300,
    "tutor_waiting": 600,
    "grade_submission": 300,
}
# tutor_waiting dừng nhận câu hỏi mới khi còn chừng này giây trước hạn của handler (một câu trả lời có thể mất
# vài chục giây); câu còn lại để job sau hoặc cron.
TUTOR_WAITING_RESERVE_S = 120
TUTOR_WAITING_CRON_BUDGET_S = 180
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
# grade_submission (ref_id = submissions.id, ref_version = version): bài nộp còn chờ AI chuyển ai_failed.
GRADE_JOB_TYPE = "grade_submission"
# quiz_gen: lỗi nghiệp vụ (QuizGenerationError, vd. NO_CHUNKS_ERROR) ghi nguyên văn vào job; lỗi khác
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
    await _notify_job_owner(ctx, uuid.UUID(job_id), session_factory)
    await _queue_source_guide(ctx, uuid.UUID(job_id), session_factory)
    await _queue_waiting_answers(ctx, uuid.UUID(job_id), session_factory)


async def _notify_job_owner(ctx: dict, job_id: uuid.UUID, session_factory: async_sessionmaker) -> None:
    """Job xử lý PDF / sinh câu hỏi kết thúc thì báo người tạo job (B6): xong → mở bài để xem, lỗi → kèm lý do.
    Lỗi ở đây chỉ ghi log: thông báo là phần phụ, trạng thái job đã được ghi."""
    try:
        async with session_factory() as db:
            job = await db.get(Job, job_id)
            if job is None or job.created_by is None or job.status not in (JobStatus.done, JobStatus.failed):
                return
            ok = job.status == JobStatus.done
            if job.type == "ingest_pdf":
                row = (
                    await db.execute(
                        select(Asset.original_name, Lesson, Course)
                        .select_from(Source)
                        .join(Asset, Asset.id == Source.asset_id)
                        .join(Lesson, Lesson.id == Source.lesson_id)
                        .join(Section, Section.id == Lesson.section_id)
                        .join(Course, Course.id == Section.course_id)
                        .where(Source.id == job.ref_id)
                    )
                ).first()
                if row is None:
                    return
                name, lesson, course = row
                kind = NotificationKind.doc_ready if ok else NotificationKind.doc_failed
                title = (
                    f"Tài liệu đã sẵn sàng · {lesson.title}"
                    if ok
                    else f"Xử lý tài liệu không thành công · {lesson.title}"
                )
                body = (name or "Tài liệu PDF") + ("" if ok else f": {job.error_msg or 'lỗi không rõ'}")
                link = f"/teach/{course.slug}/lessons/{lesson.id}"
            elif job.type == "quiz_gen":
                row = (
                    await db.execute(
                        select(Lesson, Course)
                        .join(Section, Section.id == Lesson.section_id)
                        .join(Course, Course.id == Section.course_id)
                        .where(Lesson.id == job.ref_id)
                    )
                ).first()
                if row is None:
                    return
                lesson, course = row
                kind = NotificationKind.questions_ready if ok else NotificationKind.questions_failed
                title = (
                    f"Câu hỏi AI đã soạn xong · {lesson.title}"
                    if ok
                    else f"Sinh câu hỏi không thành công · {lesson.title}"
                )
                body = "Câu hỏi đang chờ bạn duyệt" if ok else (job.error_msg or "")
                link = f"/teach/{course.slug}/lessons/{lesson.id}/questions"
            else:
                return
            ids = inbox.add(db, [job.created_by], kind, title, link, body=body)
            await db.commit()
        await inbox.publish(ctx.get("hub") or get_hub(), ids)
    except Exception:
        logger.exception("Không tạo được thông báo cho job %s", job_id)


def _queue_of(ctx: dict) -> JobQueue | None:
    return ctx.get("queue") or (ArqQueue(pool=ctx["redis"]) if "redis" in ctx else None)


async def _queue_source_guide(
    ctx: dict, ingest_job_id: uuid.UUID, session_factory: async_sessionmaker
) -> None:
    """Xử lý PDF xong (job done) thì xếp hàng job hướng dẫn tài liệu (AI Studio S1). Lỗi chỉ ghi log: hướng dẫn
    là phần phụ, không làm hỏng việc xử lý tài liệu."""
    queue = _queue_of(ctx)
    if queue is None:  # test chạy job ingest đơn lẻ, không có hàng đợi
        return
    try:
        async with session_factory() as db:
            job = await db.get(Job, ingest_job_id)
            if job is None or job.status != JobStatus.done:
                return
            await create_and_enqueue(db, queue, "source_guide", job.ref_id, created_by=job.created_by)
    except Exception:
        logger.exception("Không xếp hàng được job hướng dẫn tài liệu cho job %s", ingest_job_id)


async def _queue_waiting_answers(
    ctx: dict, ingest_job_id: uuid.UUID, session_factory: async_sessionmaker
) -> None:
    """Xử lý PDF kết thúc (xong hoặc lỗi) mà bài có câu hỏi chờ thì xếp job tutor_waiting (ref_id = lessons.id).
    Lỗi ở đây chỉ ghi log: cron answer_waiting_cron sẽ vét lại."""
    queue = _queue_of(ctx)
    if queue is None:
        return
    try:
        async with session_factory() as db:
            job = await db.get(Job, ingest_job_id)
            if job is None or job.status not in (JobStatus.done, JobStatus.failed):
                return
            lesson_id = await db.scalar(select(Source.lesson_id).where(Source.id == job.ref_id))
            if lesson_id is None or not await has_waiting(db, lesson_id):
                return
            await create_and_enqueue(db, queue, "tutor_waiting", lesson_id, created_by=None)
    except Exception:
        logger.exception("Không xếp hàng được job trả lời câu hỏi chờ cho job %s", ingest_job_id)


async def tutor_waiting(ctx: dict, job_id: str) -> None:
    """Trả lời câu hỏi chờ của một bài: ref_id = lessons.id."""
    session_factory = ctx.get("session_factory", SessionLocal)
    timeout_s = handler_timeout("tutor_waiting")

    async def handler(lesson_id: uuid.UUID) -> None:
        await answer_waiting(
            ctx["llm"],
            ctx["embedder"],
            lesson_id=lesson_id,
            session_factory=session_factory,
            budget_s=timeout_s - TUTOR_WAITING_RESERVE_S,
        )

    await run_job(job_id, handler, session_factory, timeout_s=timeout_s)


async def answer_waiting_cron(ctx: dict) -> int:
    """Cron 5 phút: vét câu hỏi chờ mà job sau xử lý PDF bị lỡ (Redis mất job, tài liệu bị sweeper chốt lỗi...)."""
    return await answer_waiting(
        ctx["llm"],
        ctx["embedder"],
        session_factory=ctx.get("session_factory", SessionLocal),
        budget_s=TUTOR_WAITING_CRON_BUDGET_S,
    )


async def source_guide(ctx: dict, job_id: str) -> None:
    """Hướng dẫn tài liệu: ref_id = sources.id."""
    session_factory = ctx.get("session_factory", SessionLocal)

    async def handler(source_id: uuid.UUID) -> None:
        await run_source_guide(source_id, ctx["llm"], get_settings(), session_factory)

    await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("source_guide"))


async def studio_gen(ctx: dict, job_id: str) -> None:
    """Báo cáo / flashcard: ref_id = study_artifacts.id."""
    session_factory = ctx.get("session_factory", SessionLocal)

    async def handler(artifact_id: uuid.UUID) -> None:
        await run_studio(artifact_id, ctx["llm"], get_settings(), session_factory)

    await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("studio_gen"))


async def notes_synth(ctx: dict, job_id: str) -> None:
    """Tổng hợp ghi chú: ref_id = notes.id (ghi chú đích), payload.note_ids = ghi chú nguồn theo thứ tự."""
    session_factory = ctx.get("session_factory", SessionLocal)
    jid = uuid.UUID(job_id)

    async def handler(note_id: uuid.UUID) -> None:
        async with session_factory() as db:
            payload = await db.scalar(select(Job.payload).where(Job.id == jid)) or {}
        ids = [uuid.UUID(i) for i in payload.get("note_ids", [])]
        await run_notes_synth(note_id, ids, ctx["llm"], get_settings(), session_factory)

    await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("notes_synth"))


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
            raise QuizGenerationError(QUIZ_GEN_PAYLOAD_ERROR) from e
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
        except QuizGenerationError:  # thông báo tiếng Việt cho giảng viên (NO_CHUNKS_ERROR, ...)
            raise
        except Exception as e:  # kể cả ValueError khác: message kỹ thuật; run_job log kèm lỗi gốc
            raise RuntimeError(QUIZ_GEN_ERROR) from e

    await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("quiz_gen"))
    await _notify_job_owner(ctx, jid, session_factory)


async def grade_submission(ctx: dict, job_id: str) -> None:
    """AI gợi ý chấm bài nộp (B5): ref_id = submissions.id, ref_version = version của bài nộp được chấm.
    Bài đã nộp lại (version khác) hoặc đã được giảng viên chấm thì bỏ qua, job vẫn done."""
    session_factory = ctx.get("session_factory", SessionLocal)
    jid = uuid.UUID(job_id)

    async def handler(submission_id: uuid.UUID) -> None:
        async with session_factory() as db:
            version = await db.scalar(select(Job.ref_version).where(Job.id == jid))
        await run_grading(
            submission_id,
            version,
            ctx["llm"],
            ctx.get("storage") or get_storage(),
            session_factory,
            ctx.get("hub") or get_hub(),
        )

    await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("grade_submission"))


async def _fail_jobs(db, jobs_where, error: str, now) -> int:
    """Chuyển các job khớp điều kiện sang failed; source tương ứng (loại ingest_*) còn pending/processing
    cũng failed cùng lỗi, bài nộp đang chờ AI (grade_submission) chuyển ai_failed. Chưa commit — caller commit
    để job, source và bài nộp đổi trạng thái trong cùng transaction."""
    rows = (
        await db.execute(
            update(Job)
            .where(*jobs_where)
            .values(status=JobStatus.failed, error_msg=error, finished_at=now)
            .returning(Job.type, Job.ref_id, Job.ref_version)
        )
    ).all()
    grading = [(ref_id, ref_version) for type_, ref_id, ref_version in rows if type_ == GRADE_JOB_TYPE]
    if grading:
        await fail_unfinished_grading(db, grading, error)
    source_ids = [ref_id for type_, ref_id, _ in rows if type_ in SOURCE_JOB_TYPES]
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


async def finalize_overdue_quiz_attempts(ctx: dict) -> int:
    """Cron mỗi phút: chốt các bài quiz đã hết giờ mà học viên bỏ dở (B1)."""
    return await finalize_overdue_attempts(ctx.get("session_factory", SessionLocal))


async def send_pending_emails(ctx: dict) -> int:
    """Gửi email trong outbox. API gọi ngay sau khi commit (kick), cron chạy mỗi phút để vét phần còn sót."""
    from app.modules.notify.outbox import send_pending

    return await send_pending(ctx.get("session_factory", SessionLocal), ctx["mailer"])
