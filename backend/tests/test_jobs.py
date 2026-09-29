import asyncio
import uuid

from app.core.db import SessionLocal
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_and_enqueue, create_job
from tests.fakes import RecordingQueue
from tests.helpers import API, make_student


async def test_active_job_is_deduplicated(db):
    ref = uuid.uuid4()
    j1, created1 = await create_job(db, "quiz_gen", ref)
    await db.commit()
    j2, created2 = await create_job(db, "quiz_gen", ref)
    await db.commit()
    assert created1 is True and created2 is False
    assert j1.id == j2.id


async def test_new_ref_version_creates_new_job(db):
    ref = uuid.uuid4()
    j1, _ = await create_job(db, "grade_submission", ref, ref_version=1)
    await db.commit()
    j2, created = await create_job(db, "grade_submission", ref, ref_version=2)
    await db.commit()
    assert created is True and j1.id != j2.id


async def test_finished_job_allows_a_new_one(db):
    ref = uuid.uuid4()
    j1, _ = await create_job(db, "ingest_pdf", ref)
    j1.status = JobStatus.done
    await db.commit()
    j2, created = await create_job(db, "ingest_pdf", ref)
    await db.commit()
    assert created is True and j2.id != j1.id


async def test_concurrent_creates_produce_one_job():
    ref = uuid.uuid4()

    async def attempt() -> bool:
        async with SessionLocal() as s:
            _, created = await create_job(s, "quiz_gen", ref)
            await s.commit()
            return created

    results = await asyncio.gather(attempt(), attempt())
    assert sorted(results) == [False, True]


async def test_create_and_enqueue_commits_first_and_enqueues_once(db):
    queue = RecordingQueue()
    ref = uuid.uuid4()
    job = await create_and_enqueue(db, queue, "ingest_pdf", ref)
    again = await create_and_enqueue(db, queue, "ingest_pdf", ref)
    assert again.id == job.id
    assert queue.jobs == [("ingest_pdf", ref)]


async def test_get_job_endpoint(client, db):
    _, sv = await make_student(client)
    job = Job(type="ingest_pdf", ref_id=uuid.uuid4())
    db.add(job)
    await db.commit()
    r = await client.get(f"{API}/jobs/{job.id}", headers=sv)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert (await client.get(f"{API}/jobs/{uuid.uuid4()}", headers=sv)).status_code == 404
    assert (await client.get(f"{API}/jobs/{job.id}")).status_code == 401
