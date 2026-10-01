from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.ai.embedder import FakeEmbedder
from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.core.config import get_settings
from app.core.time import utcnow
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_and_enqueue, create_job
from app.modules.quiz.generation import NO_CHUNKS_ERROR
from app.modules.quiz.models import Question, ReviewStatus
from app.modules.quiz.schemas import QuizGenerateIn
from app.worker.settings import WorkerSettings
from app.worker.tasks import (
    JOB_TIMEOUTS,
    QUIZ_GEN_ERROR,
    QUIZ_GEN_PAYLOAD_ERROR,
    SOURCE_JOB_TYPES,
    STALE_GRACE,
    STALE_JOB_ERROR,
    handler_timeout,
    quiz_gen,
    sweep_stale_jobs,
)
from tests.factories import LONG_LESSON_TEXT, make_lesson, make_user, seed_chunks
from tests.fakes import RecordingQueue
from tests.test_ai_retry import Sleeps


def _ctx(provider=None) -> dict:
    llm = LLMClient(provider or FakeLLMProvider(), get_settings(), sleep=Sleeps())
    return {"llm": llm, "embedder": FakeEmbedder(768)}


async def test_quiz_gen_job_reads_payload_and_saves_pending_questions(db):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    await seed_chunks(db, lesson.id, [LONG_LESSON_TEXT])
    payload = {"count": 3, "difficulty": {"easy": 1, "medium": 0, "hard": 0}}
    job, _ = await create_job(db, "quiz_gen", lesson.id, created_by=teacher.id, payload=payload)
    await db.commit()
    provider = FakeLLMProvider()
    await quiz_gen(_ctx(provider), str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.status == JobStatus.done and job.error_msg is None and job.payload == payload
    rows = (await db.scalars(select(Question).where(Question.lesson_id == lesson.id))).all()
    assert len(rows) == 3 and {r.review_status for r in rows} == {ReviewStatus.pending}
    gen_call = next(c for c in provider.calls if c.op == "quiz_generate")
    assert "Số câu cần sinh: 3" in gen_call.prompt and "Độ khó lần lượt: easy, easy, easy" in gen_call.prompt


async def test_quiz_gen_without_ready_chunks_fails_job(db):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    job, _ = await create_job(db, "quiz_gen", lesson.id, created_by=teacher.id, payload={"count": 2})
    await db.commit()
    await quiz_gen(_ctx(), str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg == NO_CHUNKS_ERROR


async def test_quiz_gen_unexpected_error_fails_job_with_generic_message(db):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    await seed_chunks(db, lesson.id, [LONG_LESSON_TEXT])
    job, _ = await create_job(db, "quiz_gen", lesson.id, created_by=teacher.id, payload={"count": 2})
    await db.commit()

    def boom(call):
        raise RuntimeError("internal provider detail")

    await quiz_gen(_ctx(FakeLLMProvider(reply_for=boom)), str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg == QUIZ_GEN_ERROR
    assert job.finished_at is not None
    assert (await db.scalars(select(Question).where(Question.lesson_id == lesson.id))).all() == []


class _ShortEmbedder(FakeEmbedder):
    """Trả thiếu một vector: zip(strict=True) trong bước lọc trùng ném ValueError tiếng Anh."""

    async def embed_documents(self, texts):
        return (await super().embed_documents(texts))[:-1]


async def test_quiz_gen_non_generation_value_error_gets_generic_message(db):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    await seed_chunks(db, lesson.id, [LONG_LESSON_TEXT])
    job, _ = await create_job(db, "quiz_gen", lesson.id, created_by=teacher.id, payload={"count": 2})
    await db.commit()
    ctx = _ctx() | {"embedder": _ShortEmbedder(768)}
    await quiz_gen(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg == QUIZ_GEN_ERROR
    assert (await db.scalars(select(Question).where(Question.lesson_id == lesson.id))).all() == []


@pytest.mark.parametrize("body", [{"cnt": 5}, {"count": True}, {"count": "7"}, {"count": 7.0}])
def test_quiz_generate_in_is_strict(body):
    with pytest.raises(ValidationError):
        QuizGenerateIn.model_validate(body)


def test_quiz_generate_in_defaults_and_json_roundtrip():
    params = QuizGenerateIn.model_validate({"count": 7})
    assert params.count == 7 and params.difficulty.as_mapping()
    assert QuizGenerateIn.model_validate(params.model_dump(mode="json")) == params


async def test_quiz_gen_invalid_payload_fails_job_in_vietnamese(db):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    job, _ = await create_job(db, "quiz_gen", lesson.id, created_by=teacher.id, payload={"count": 99})
    await db.commit()
    provider = FakeLLMProvider()
    await quiz_gen(_ctx(provider), str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg == QUIZ_GEN_PAYLOAD_ERROR
    assert provider.calls == []


async def test_create_and_enqueue_stores_payload_and_enqueues_quiz_gen(db):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    queue = RecordingQueue()
    payload = {"count": 5, "difficulty": {"easy": 0.2, "medium": 0.5, "hard": 0.3}}
    job = await create_and_enqueue(db, queue, "quiz_gen", lesson.id, created_by=teacher.id, payload=payload)
    assert queue.jobs == [("quiz_gen", lesson.id)]
    again = await create_and_enqueue(
        db, queue, "quiz_gen", lesson.id, created_by=teacher.id, payload={"count": 1}
    )
    assert again.id == job.id and queue.jobs == [("quiz_gen", lesson.id)]
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.payload == payload and job.created_by == teacher.id


async def test_sweeper_covers_quiz_gen_jobs(db):
    assert "quiz_gen" not in SOURCE_JOB_TYPES
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    stale, _ = await create_job(db, "quiz_gen", lesson.id, created_by=None)
    stale.status = JobStatus.processing
    stale.started_at = (
        utcnow() - timedelta(seconds=JOB_TIMEOUTS["quiz_gen"]) - STALE_GRACE - timedelta(minutes=1)
    )
    await db.commit()
    assert await sweep_stale_jobs({"queue": RecordingQueue()}) == 1
    stale = await db.get(Job, stale.id, populate_existing=True)
    assert stale.status == JobStatus.failed and stale.error_msg == STALE_JOB_ERROR

    pending, _ = await create_job(db, "quiz_gen", lesson.id, created_by=None)
    pending.created_at = utcnow() - timedelta(minutes=get_settings().pending_job_requeue_after_min + 1)
    await db.commit()
    queue = RecordingQueue()
    await sweep_stale_jobs({"queue": queue})
    assert queue.jobs == [("quiz_gen", lesson.id)]


def test_worker_registers_quiz_gen_with_its_own_timeout():
    funcs = {f.name: f for f in WorkerSettings.functions}
    assert funcs["quiz_gen"].timeout_s == JOB_TIMEOUTS["quiz_gen"] == 900
    assert handler_timeout("quiz_gen") == 870
