import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

from sqlalchemy import select

from app.ai.embedder import FakeEmbedder
from app.ai.vision import FakeVision
from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_job
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.worker.tasks import JOB_TIMEOUTS, STALE_GRACE, STALE_JOB_ERROR, ingest_pdf, run_job, sweep_stale_jobs
from tests.factories import make_lesson, make_pdf_source, make_user
from tests.fakes import InMemoryStorage
from tests.pdfs import LONG_TEXT, make_pdf


async def _job_for_new_source(db, storage, pdf):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    source = await make_pdf_source(db, storage, teacher, lesson, pdf)
    job, _ = await create_job(db, "ingest_pdf", source.id)
    await db.commit()
    return source, job


class CommitRecorder:
    """session_factory ghi lại (job.status, source.status) đọc từ một session khác ngay sau mỗi commit,
    để kiểm tra trạng thái cuối của job và source được ghi trong cùng một transaction."""

    def __init__(self, job_id: uuid.UUID, source_id: uuid.UUID):
        self.job_id, self.source_id = job_id, source_id
        self.states: list[tuple[JobStatus, SourceStatus]] = []

    async def _snapshot(self) -> None:
        async with SessionLocal() as s:
            job = await s.get(Job, self.job_id)
            source = await s.get(Source, self.source_id)
            self.states.append((job.status, source.status))

    def __call__(self):
        @asynccontextmanager
        async def cm():
            async with SessionLocal() as session:
                real_commit = session.commit

                async def commit():
                    await real_commit()
                    await self._snapshot()

                session.commit = commit
                yield session
        return cm()


def _consistent(states) -> bool:
    final = {JobStatus.done: SourceStatus.ready, JobStatus.failed: SourceStatus.failed}
    in_flight = (SourceStatus.pending, SourceStatus.processing)
    return all(final[j] == s if j in final else s in in_flight for j, s in states)


async def test_ingest_pdf_job_succeeds(db):
    storage = InMemoryStorage()
    source, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))
    ctx = {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision()}
    await ingest_pdf(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.done and job.attempts == 1 and job.finished_at is not None
    assert job.started_at is not None and job.error_msg is None
    assert source.status == SourceStatus.ready


async def test_failing_handler_marks_job_failed_without_raising(db):
    storage = InMemoryStorage()
    source, job = await _job_for_new_source(db, storage, b"not a pdf")
    ctx = {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision()}
    await ingest_pdf(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg and job.finished_at is not None
    assert source.status == SourceStatus.failed and source.error_msg == job.error_msg


async def test_success_writes_job_done_and_source_ready_in_one_commit(db):
    storage = InMemoryStorage()
    source, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))
    rec = CommitRecorder(job.id, source.id)
    ctx = {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision(), "session_factory": rec}
    await ingest_pdf(ctx, str(job.id))
    assert rec.states[0] == (JobStatus.processing, SourceStatus.pending)  # worker nhận job
    assert rec.states[-1] == (JobStatus.done, SourceStatus.ready)
    assert _consistent(rec.states), rec.states


async def test_pipeline_failure_writes_job_and_source_failed_in_one_commit(db):
    storage = InMemoryStorage()
    source, job = await _job_for_new_source(db, storage, b"not a pdf")
    rec = CommitRecorder(job.id, source.id)
    ctx = {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision(), "session_factory": rec}
    await ingest_pdf(ctx, str(job.id))
    assert rec.states[-1] == (JobStatus.failed, SourceStatus.failed)
    assert _consistent(rec.states), rec.states


async def test_missing_source_still_marks_job_failed(db):
    job, _ = await create_job(db, "ingest_pdf", uuid.uuid4())
    await db.commit()
    ctx = {"storage": InMemoryStorage(), "embedder": FakeEmbedder(768), "vision": FakeVision()}
    await ingest_pdf(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.status == JobStatus.failed and "không tồn tại" in job.error_msg


async def test_finished_job_is_not_run_again(db):
    storage = InMemoryStorage()
    _, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))
    job.status = JobStatus.done
    await db.commit()
    calls = []

    async def handler(ref_id):
        calls.append(ref_id)

    await run_job(str(job.id), handler)
    assert calls == []


async def test_generic_handler_success_marks_done(db):
    job, _ = await create_job(db, "quiz_gen", uuid.uuid4())
    await db.commit()
    calls = []

    async def handler(ref_id):
        calls.append(ref_id)

    await run_job(str(job.id), handler)
    job = await db.get(Job, job.id, populate_existing=True)
    assert calls == [job.ref_id] and job.status == JobStatus.done and job.finished_at is not None


# ---- dọn job bị treo (worker chết giữa chừng) ----

def _threshold(type_: str = "ingest_pdf") -> timedelta:
    return timedelta(seconds=JOB_TIMEOUTS[type_]) + STALE_GRACE


async def _processing_job(db, storage, started_ago: timedelta, source_status=SourceStatus.processing):
    source, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))
    job.status = JobStatus.processing
    job.attempts = 1
    job.started_at = utcnow() - started_ago
    source.status = source_status
    await db.commit()
    return source, job


async def test_sweep_fails_stale_job_and_its_source(db):
    storage = InMemoryStorage()
    source, job = await _processing_job(db, storage, _threshold() + timedelta(minutes=1))
    assert await sweep_stale_jobs({}) == 1
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg == STALE_JOB_ERROR == "Worker bị gián đoạn"
    assert job.finished_at is not None
    assert source.status == SourceStatus.failed and source.error_msg == STALE_JOB_ERROR


async def test_sweep_leaves_job_within_threshold(db):
    storage = InMemoryStorage()
    source, job = await _processing_job(db, storage, _threshold() - timedelta(minutes=1))
    assert await sweep_stale_jobs({}) == 0
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.processing and job.finished_at is None
    assert source.status == SourceStatus.processing


async def test_sweep_leaves_done_job(db):
    storage = InMemoryStorage()
    source, job = await _processing_job(db, storage, _threshold() * 3, source_status=SourceStatus.ready)
    job.status = JobStatus.done
    await db.commit()
    assert await sweep_stale_jobs({}) == 0
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.done and job.error_msg is None
    assert source.status == SourceStatus.ready


async def test_sweep_does_not_clobber_finished_source(db):
    storage = InMemoryStorage()
    source, job = await _processing_job(db, storage, _threshold() * 2, source_status=SourceStatus.ready)
    assert await sweep_stale_jobs({}) == 1
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.failed
    assert source.status == SourceStatus.ready and source.error_msg is None


async def test_late_worker_does_not_overwrite_swept_job(db):
    """Worker chạy quá lâu, bị sweeper đánh dấu failed: kết quả đến muộn không được ghi đè."""
    storage = InMemoryStorage()
    source, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))

    class SweepingEmbedder(FakeEmbedder):
        async def embed_documents(self, texts):
            async with SessionLocal() as s:  # giả lập: đã quá hạn, sweeper chạy trong lúc worker còn embed
                j = await s.get(Job, job.id)
                j.started_at = utcnow() - _threshold() * 2
                await s.commit()
            await sweep_stale_jobs({})
            return await super().embed_documents(texts)

    ctx = {"storage": storage, "embedder": SweepingEmbedder(768), "vision": FakeVision()}
    await ingest_pdf(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg == STALE_JOB_ERROR
    assert source.status == SourceStatus.failed and source.error_msg == STALE_JOB_ERROR
    assert (await db.scalars(select(Chunk).where(Chunk.source_id == source.id))).all() == []


async def test_job_already_failed_by_sweeper_is_not_claimed(db):
    storage = InMemoryStorage()
    source, job = await _processing_job(db, storage, _threshold() * 2)
    assert await sweep_stale_jobs({}) == 1
    calls = []

    async def handler(ref_id):
        calls.append(ref_id)

    await run_job(str(job.id), handler)
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert calls == []
    assert job.status == JobStatus.failed and job.attempts == 1 and job.error_msg == STALE_JOB_ERROR
    assert source.status == SourceStatus.failed and source.error_msg == STALE_JOB_ERROR


def _sweep_racing_first_claim():
    """session_factory: sweeper chạy xen vào đúng lúc worker nhận job (sau khi đọc job, trước khi ghi)."""
    fired = False

    async def sweep_once():
        nonlocal fired
        if not fired:
            fired = True
            await sweep_stale_jobs({})

    @asynccontextmanager
    async def cm():
        async with SessionLocal() as session:
            real_get, real_scalar, real_execute = session.get, session.scalar, session.execute

            async def get(*a, **kw):
                obj = await real_get(*a, **kw)
                await sweep_once()  # đọc xong (không giữ lock) rồi sweeper mới chạy
                return obj

            async def scalar(*a, **kw):
                await sweep_once()
                return await real_scalar(*a, **kw)

            async def execute(*a, **kw):
                await sweep_once()
                return await real_execute(*a, **kw)

            session.get, session.scalar, session.execute = get, scalar, execute
            yield session
    return cm


async def test_sweep_racing_the_claim_is_not_overwritten(db):
    """arq chạy lại job của worker đã chết; sweeper đánh dấu failed ngay lúc worker mới nhận job."""
    storage = InMemoryStorage()
    source, job = await _processing_job(db, storage, _threshold() * 2)
    calls = []

    async def handler(ref_id):
        calls.append(ref_id)

    await run_job(str(job.id), handler, session_factory=_sweep_racing_first_claim())
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert calls == []
    assert job.status == JobStatus.failed and job.error_msg == STALE_JOB_ERROR and job.attempts == 1
    assert source.status == SourceStatus.failed and source.error_msg == STALE_JOB_ERROR


async def test_late_worker_failure_does_not_overwrite_swept_job(db):
    """Sweeper đánh dấu failed trong lúc worker còn chạy, sau đó pipeline lỗi: giữ nguyên lỗi của sweeper."""
    storage = InMemoryStorage()
    source, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))

    class SweepThenFailEmbedder(FakeEmbedder):
        async def embed_documents(self, texts):
            async with SessionLocal() as s:
                j = await s.get(Job, job.id)
                j.started_at = utcnow() - _threshold() * 2
                await s.commit()
            await sweep_stale_jobs({})
            raise RuntimeError("Embedding API lỗi")

    ctx = {"storage": storage, "embedder": SweepThenFailEmbedder(768), "vision": FakeVision()}
    await ingest_pdf(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg == STALE_JOB_ERROR
    assert source.status == SourceStatus.failed and source.error_msg == STALE_JOB_ERROR
