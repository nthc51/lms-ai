"""Hỏi AI Tutor lúc tài liệu đang xử lý: trạng thái availability, gửi câu hỏi chờ, worker trả lời khi xong."""

import uuid

from sqlalchemy import select, update

from app.ai.embedder import FakeEmbedder
from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.ai.vision import FakeVision
from app.core.config import get_settings
from app.modules.jobs.service import create_job
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.modules.tutor.models import ChatMessage, ChatRole
from app.modules.tutor.waiting import DOCS_FAILED_ANSWER, answer_waiting
from app.worker.tasks import answer_waiting_cron, ingest_pdf, tutor_waiting
from tests.factories import BINARY_SEARCH, make_pdf_source, seed_chunks
from tests.fakes import InMemoryStorage, RecordingQueue
from tests.helpers import API, create_course, make_published_course, make_student, make_teacher
from tests.test_ai_retry import Sleeps

Q1 = "Tìm kiếm nhị phân là gì?"
Q2 = "Độ phức tạp của nó thế nào?"


async def _setup(client, db, *, source_status=SourceStatus.processing):
    """Khóa đã publish, học viên đã đăng ký, bài có một PDF ở trạng thái source_status (chưa có chunk)."""
    from app.modules.auth.models import Role, User
    from app.modules.courses.models import Lesson

    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    _, sv = await make_student(client)
    assert (await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)).status_code == 201
    lesson_row = await db.get(Lesson, uuid.UUID(lesson["id"]))
    owner = await db.scalar(select(User).where(User.role == Role.teacher))
    source = await make_pdf_source(
        db, InMemoryStorage(), owner, lesson_row, b"%PDF-1.7", status=source_status
    )
    s = (
        await client.post(
            f"{API}/tutor/sessions", json={"course_id": course["id"], "lesson_id": lesson["id"]}, headers=sv
        )
    ).json()
    return course, lesson, source, sv, s["id"]


def _params(course, lesson=None):
    return {"course_id": course["id"], **({"lesson_id": lesson["id"]} if lesson else {})}


async def _availability(client, headers, course, lesson=None):
    r = await client.get(f"{API}/tutor/availability", params=_params(course, lesson), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _queue(client, headers, session_id, text=Q1):
    return await client.post(
        f"{API}/tutor/sessions/{session_id}/questions", json={"content": text}, headers=headers
    )


async def _finish(db, source, *, chunks=True):
    """Tài liệu xử lý xong: source ready + có chunk (seed_chunks gắn thêm một source ready khác)."""
    await db.execute(update(Source).where(Source.id == source.id).values(status=SourceStatus.ready))
    await db.commit()
    if chunks:
        await seed_chunks(db, source.lesson_id, [BINARY_SEARCH])


def _llm(provider=None):
    return LLMClient(provider or FakeLLMProvider(), get_settings(), sleep=Sleeps())


async def _messages(client, headers, session_id):
    r = await client.get(f"{API}/tutor/sessions/{session_id}/messages", headers=headers)
    return r.json()["items"]


# ---------- availability ----------


async def test_availability_states(client, db):
    course, lesson, source, sv, _ = await _setup(client, db)
    a = await _availability(client, sv, course, lesson)
    assert a["state"] == "processing" and a["can_queue"] is True and a["processing_docs"] == 1
    assert a["available"] is False and "AI sẽ trả lời ngay khi xử lý xong" in a["message"]

    await db.execute(update(Source).where(Source.id == source.id).values(status=SourceStatus.failed))
    await db.commit()
    a = await _availability(client, sv, course, lesson)
    assert (a["state"], a["can_queue"]) == ("failed", False)

    await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH])
    await db.execute(update(Chunk).values(embedding_model="model-khac"))
    await db.commit()
    a = await _availability(client, sv, course, lesson)
    assert a["state"] == "model_mismatch" and "model AI khác" in a["message"]

    await db.execute(update(Chunk).values(embedding_model="fake-768"))
    await db.commit()
    a = await _availability(client, sv, course, lesson)
    assert (a["state"], a["available"], a["message"], a["processing_docs"]) == ("ready", True, None, 0)
    a = await _availability(client, sv, course)  # cả khóa (đã publish)
    assert a["state"] == "ready" and a["ready_chunks"] == 1


async def test_ready_scope_still_reports_documents_in_progress(client, db):
    course, lesson, _, sv, _ = await _setup(client, db)
    await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH])
    a = await _availability(client, sv, course, lesson)
    assert (a["state"], a["available"], a["processing_docs"], a["can_queue"]) == ("ready", True, 1, False)


async def test_empty_lesson_and_draft_course_scope(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    a = await _availability(client, gv, course, lesson)
    assert (a["state"], a["message"]) == ("empty", "Bài này chưa có tài liệu cho AI Tutor.")
    draft = await create_course(client, gv, title="Khóa nháp")
    a = await _availability(client, gv, draft)
    assert (a["state"], a["can_queue"]) == ("draft", False)


# ---------- gửi câu hỏi chờ ----------


async def test_queue_question_only_while_processing(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    r = await _queue(client, sv, sid)
    assert r.status_code == 202, r.text
    assert r.json()["waiting_for_docs"] is True and r.json()["role"] == "user"
    [m] = await _messages(client, sv, sid)
    assert m["waiting_for_docs"] is True

    await _finish(db, source)
    r = await _queue(client, sv, sid)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "TUTOR_READY")


async def test_queue_rejected_when_nothing_is_processing(client, db):
    _, _, _, sv, sid = await _setup(client, db, source_status=SourceStatus.failed)
    r = await _queue(client, sv, sid)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "NOT_PROCESSING")
    assert "không thành công" in r.json()["error"]["message"]
    assert await _messages(client, sv, sid) == []


async def test_queue_is_capped_per_session_and_checks_ownership(client, db):
    _, _, _, sv, sid = await _setup(client, db)
    for i in range(5):
        assert (await _queue(client, sv, sid, f"Câu {i}")).status_code == 202
    r = await _queue(client, sv, sid, "Câu thứ sáu")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "TOO_MANY_WAITING")
    _, other = await make_student(client, "sv2@x.com")
    assert (await _queue(client, other, sid)).status_code == 404


async def test_queue_counts_against_rate_limit(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "tutor_rate_limit_per_hour", 1)
    _, _, _, sv, sid = await _setup(client, db)
    assert (await _queue(client, sv, sid)).status_code == 202
    r = await _queue(client, sv, sid, Q2)
    assert r.status_code == 429 and "Retry-After" in r.headers


# ---------- worker trả lời ----------


async def test_waiting_questions_answered_in_order_after_processing(client, db):
    _, lesson, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid, Q1)
    await _queue(client, sv, sid, Q2)
    provider = FakeLLMProvider()
    # Tài liệu chưa xong: không trả lời gì, câu hỏi vẫn chờ
    assert await answer_waiting(_llm(provider), FakeEmbedder(768)) == 0
    assert provider.calls == []

    await _finish(db, source)
    assert await answer_waiting(_llm(provider), FakeEmbedder(768), lesson_id=uuid.UUID(lesson["id"])) == 2
    items = await _messages(client, sv, sid)
    assert [(m["role"], m["waiting_for_docs"]) for m in items] == [
        ("user", False),
        ("assistant", False),
        ("user", False),
        ("assistant", False),
    ]
    assert items[0]["content"] == Q1 and items[2]["content"] == Q2
    assert items[1]["content"] and items[1]["citations"]
    # Câu 2 có lịch sử (câu 1 và câu trả lời của nó) nên được viết lại trước khi tìm tài liệu
    rewrites = [c for c in provider.calls if c.op == "tutor_rewrite"]
    assert len(rewrites) == 1 and Q1 in rewrites[0].prompt and Q2 in rewrites[0].prompt


async def test_waiting_question_is_answered_only_once(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    await _finish(db, source)
    assert await answer_waiting(_llm(), FakeEmbedder(768)) == 1
    assert await answer_waiting(_llm(), FakeEmbedder(768)) == 0
    answers = await db.scalars(select(ChatMessage).where(ChatMessage.role == ChatRole.assistant))
    assert len(list(answers)) == 1


async def test_failed_documents_get_a_notice_instead_of_waiting_forever(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    await db.execute(update(Source).where(Source.id == source.id).values(status=SourceStatus.failed))
    await db.commit()
    provider = FakeLLMProvider()
    assert await answer_waiting(_llm(provider), FakeEmbedder(768)) == 1
    items = await _messages(client, sv, sid)
    assert [m["role"] for m in items] == ["user", "assistant"]
    assert items[1]["content"] == DOCS_FAILED_ANSWER and items[1]["refused"] is True
    assert provider.calls == []


async def test_lost_access_drops_waiting_question(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    from sqlalchemy import delete

    from app.modules.enrollment.models import Enrollment

    await db.execute(delete(Enrollment))  # bị hủy đăng ký sau khi gửi câu hỏi
    await db.commit()
    await _finish(db, source)
    provider = FakeLLMProvider()
    assert await answer_waiting(_llm(provider), FakeEmbedder(768)) == 1
    msgs = list(await db.scalars(select(ChatMessage).execution_options(populate_existing=True)))
    assert [(m.role, m.waiting_for_docs) for m in msgs] == [(ChatRole.user, False)]
    assert provider.calls == []


async def test_ingest_end_queues_tutor_waiting_job_and_job_answers(client, db):
    from tests.pdfs import make_pdf

    _, lesson, source, sv, sid = await _setup(client, db, source_status=SourceStatus.pending)
    await _queue(client, sv, sid)
    storage = InMemoryStorage()
    from app.modules.materials.models import Asset

    asset = await db.get(Asset, source.asset_id)
    await storage.put(asset.storage_key, make_pdf([BINARY_SEARCH]), "application/pdf")
    job, _ = await create_job(db, "ingest_pdf", source.id, created_by=None)
    await db.commit()
    queue = RecordingQueue()
    ctx = {
        "storage": storage,
        "embedder": FakeEmbedder(768),
        "vision": FakeVision(),
        "queue": queue,
        "llm": _llm(),
    }
    await ingest_pdf(ctx, str(job.id))
    assert ("tutor_waiting", uuid.UUID(lesson["id"])) in queue.jobs

    waiting_job, created = await create_job(db, "tutor_waiting", uuid.UUID(lesson["id"]), created_by=None)
    await db.commit()
    assert created is False  # chính job vừa được xếp hàng, chưa chạy
    await tutor_waiting(ctx, str(waiting_job.id))
    items = await _messages(client, sv, sid)
    assert [m["role"] for m in items] == ["user", "assistant"] and items[1]["content"]


async def test_ingest_without_waiting_questions_queues_nothing_extra(client, db):
    from tests.pdfs import make_pdf

    _, _, source, _, _ = await _setup(client, db, source_status=SourceStatus.pending)
    storage = InMemoryStorage()
    from app.modules.materials.models import Asset

    asset = await db.get(Asset, source.asset_id)
    await storage.put(asset.storage_key, make_pdf([BINARY_SEARCH]), "application/pdf")
    job, _ = await create_job(db, "ingest_pdf", source.id, created_by=None)
    await db.commit()
    queue = RecordingQueue()
    await ingest_pdf(
        {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision(), "queue": queue},
        str(job.id),
    )
    assert [t for t, _ in queue.jobs] == ["source_guide"]


async def test_cron_sweeps_waiting_questions(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    await _finish(db, source)
    assert await answer_waiting_cron({"llm": _llm(), "embedder": FakeEmbedder(768)}) == 1
    assert [m["role"] for m in await _messages(client, sv, sid)] == ["user", "assistant"]
