import asyncio
import uuid

from app.core.db import SessionLocal
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_and_enqueue, create_job
from tests.factories import make_user
from tests.fakes import RecordingQueue
from tests.helpers import API, make_admin, make_student, make_teacher


async def test_active_job_is_deduplicated(db):
    ref = uuid.uuid4()
    j1, created1 = await create_job(db, "quiz_gen", ref, created_by=None)
    await db.commit()
    j2, created2 = await create_job(db, "quiz_gen", ref, created_by=None)
    await db.commit()
    assert created1 is True and created2 is False
    assert j1.id == j2.id


async def test_new_ref_version_creates_new_job(db):
    ref = uuid.uuid4()
    j1, _ = await create_job(db, "grade_submission", ref, ref_version=1, created_by=None)
    await db.commit()
    j2, created = await create_job(db, "grade_submission", ref, ref_version=2, created_by=None)
    await db.commit()
    assert created is True and j1.id != j2.id


async def test_finished_job_allows_a_new_one(db):
    ref = uuid.uuid4()
    j1, _ = await create_job(db, "ingest_pdf", ref, created_by=None)
    j1.status = JobStatus.done
    await db.commit()
    j2, created = await create_job(db, "ingest_pdf", ref, created_by=None)
    await db.commit()
    assert created is True and j2.id != j1.id


async def test_concurrent_creates_produce_one_job():
    ref = uuid.uuid4()

    async def attempt() -> bool:
        async with SessionLocal() as s:
            _, created = await create_job(s, "quiz_gen", ref, created_by=None)
            await s.commit()
            return created

    results = await asyncio.gather(attempt(), attempt())
    assert sorted(results) == [False, True]


async def test_create_and_enqueue_commits_first_and_enqueues_once(db):
    queue = RecordingQueue()
    ref = uuid.uuid4()
    job = await create_and_enqueue(db, queue, "ingest_pdf", ref, created_by=None)
    again = await create_and_enqueue(db, queue, "ingest_pdf", ref, created_by=None)
    assert again.id == job.id
    assert queue.jobs == [("ingest_pdf", ref)]


async def test_create_job_records_creator(db):
    teacher = await make_user(db)
    job, _ = await create_job(db, "quiz_gen", uuid.uuid4(), created_by=teacher.id)
    await db.commit()
    assert (await db.get(Job, job.id, populate_existing=True)).created_by == teacher.id


async def _job_by(db, created_by: str | None) -> Job:
    job = Job(
        type="ingest_pdf", ref_id=uuid.uuid4(), created_by=uuid.UUID(created_by) if created_by else None
    )
    db.add(job)
    await db.commit()
    return job


async def test_get_job_creator_sees_it(client, db):
    gv_id, gv = await make_teacher(client)
    job = await _job_by(db, gv_id)
    r = await client.get(f"{API}/jobs/{job.id}", headers=gv)
    assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["id"] == str(job.id)
    assert (await client.get(f"{API}/jobs/{uuid.uuid4()}", headers=gv)).status_code == 404
    assert (await client.get(f"{API}/jobs/{job.id}")).status_code == 401


async def test_get_job_hidden_from_other_users(client, db):
    gv_id, _ = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, sv = await make_student(client)
    job = await _job_by(db, gv_id)
    missing = await client.get(f"{API}/jobs/{uuid.uuid4()}", headers=gv2)
    for headers in (gv2, sv):
        r = await client.get(f"{API}/jobs/{job.id}", headers=headers)
        assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
        # cùng nội dung với job không tồn tại (trừ request_id)
        assert r.json()["error"]["message"] == missing.json()["error"]["message"]


async def test_get_job_admin_sees_any_job(client, db):
    gv_id, _ = await make_teacher(client)
    _, admin = await make_admin(client)
    job = await _job_by(db, gv_id)
    assert (await client.get(f"{API}/jobs/{job.id}", headers=admin)).status_code == 200


async def test_system_job_only_visible_to_admin(client, db):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    _, admin = await make_admin(client)
    job = await _job_by(db, None)
    for headers in (gv, sv):
        r = await client.get(f"{API}/jobs/{job.id}", headers=headers)
        assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert (await client.get(f"{API}/jobs/{job.id}", headers=admin)).status_code == 200
