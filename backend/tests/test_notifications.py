"""B6: thông báo trong app (danh sách, đánh dấu đã đọc, luồng SSE) và các nơi tạo thông báo."""

import asyncio
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.inbox import service as inbox
from app.modules.inbox.models import Notification, NotificationKind
from app.modules.jobs.models import Job, JobStatus
from app.worker.tasks import _notify_job_owner
from tests.factories import make_question
from tests.helpers import API, make_published_course, make_student, make_teacher


async def _seed(user_id: str, n: int) -> None:
    async with SessionLocal() as db:
        for i in range(n):
            inbox.add(db, [uuid.UUID(user_id)], NotificationKind.quiz_published, f"Quiz {i}", f"/x/{i}")
            await db.commit()


async def test_list_read_one_read_all(client):
    sv_id, sv = await make_student(client)
    other_id, other = await make_student(client, "khac@x.com")
    await _seed(sv_id, 3)
    await _seed(other_id, 1)

    page = (await client.get(f"{API}/me/notifications", headers=sv)).json()
    assert page["total"] == 3 and page["unread"] == 3
    assert [i["title"] for i in page["items"]] == ["Quiz 2", "Quiz 1", "Quiz 0"]  # mới nhất trước
    first = page["items"][0]["id"]

    assert (await client.post(f"{API}/me/notifications/{first}/read", headers=other)).status_code == 404
    assert (await client.post(f"{API}/me/notifications/{first}/read", headers=sv)).status_code == 204
    assert (await client.get(f"{API}/me/notifications/unread", headers=sv)).json() == {"unread": 2}
    assert (await client.post(f"{API}/me/notifications/read-all", headers=sv)).status_code == 204
    assert (await client.get(f"{API}/me/notifications/unread", headers=sv)).json() == {"unread": 0}
    assert (await client.get(f"{API}/me/notifications/unread", headers=other)).json() == {"unread": 1}
    assert (await client.get(f"{API}/me/notifications")).status_code == 401


async def test_publishing_quiz_notifies_enrolled_students(client, db, hub):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    sv_id, sv = await make_student(client)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    q = await make_question(db, uuid.UUID(lesson["id"]))
    body = {"lesson_id": lesson["id"], "title": "Kiểm tra chương 1", "question_ids": [str(q.id)]}
    quiz = (await client.post(f"{API}/quizzes", json=body, headers=gv)).json()
    assert (await client.post(f"{API}/quizzes/{quiz['id']}/publish", headers=gv)).status_code == 200

    (item,) = (await client.get(f"{API}/me/notifications", headers=sv)).json()["items"]
    assert item["kind"] == "quiz_published" and item["title"] == "Quiz mới: Kiểm tra chương 1"
    assert item["link"] == f"/learn/{course['slug']}/{lesson['id']}/quiz/{quiz['id']}"
    assert sv_id in hub.published


async def test_worker_notifies_job_owner(client, hub):
    gv_id, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    async with SessionLocal() as db:
        ok = Job(
            type="quiz_gen",
            ref_id=uuid.UUID(lesson["id"]),
            status=JobStatus.done,
            created_by=uuid.UUID(gv_id),
        )
        bad = Job(
            type="quiz_gen",
            ref_id=uuid.UUID(lesson["id"]),
            status=JobStatus.failed,
            error_msg="Bài chưa có tài liệu đủ dài",
            created_by=uuid.UUID(gv_id),
        )
        db.add_all([ok, bad])
        await db.commit()
    await _notify_job_owner({"hub": hub}, ok.id, SessionLocal)
    await _notify_job_owner({"hub": hub}, bad.id, SessionLocal)

    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(Notification)
                .where(Notification.user_id == uuid.UUID(gv_id))
                .order_by(Notification.kind)
            )
        ).all()
    assert [(n.kind, n.link) for n in rows] == [
        ("questions_failed", f"/teach/{course['slug']}/lessons/{lesson['id']}/questions"),
        ("questions_ready", f"/teach/{course['slug']}/lessons/{lesson['id']}/questions"),
    ]
    assert rows[0].body == "Bài chưa có tài liệu đủ dài"
    assert hub.published.count(gv_id) == 2


async def test_stream_sends_count_then_updates_on_signal(client, hub):
    sv_id, _ = await make_student(client)
    await _seed(sv_id, 1)
    stop = asyncio.Event()

    async def disconnected() -> bool:
        return stop.is_set()

    events = inbox.notification_events(uuid.UUID(sv_id), hub, is_disconnected=disconnected, heartbeat_s=5)
    first = await anext(events)
    assert first.startswith("event: unread\n") and '"unread": 1' in first and '"title": "Quiz 0"' in first

    async def later():
        await asyncio.sleep(0.05)
        await _seed(sv_id, 1)
        await hub.publish([sv_id])

    task = asyncio.create_task(later())
    second = await asyncio.wait_for(anext(events), timeout=3)
    await task
    assert '"unread": 2' in second
    stop.set()
    await events.aclose()


async def test_stream_endpoint_requires_login(client):
    assert (await client.get(f"{API}/me/notifications/stream")).status_code == 401
