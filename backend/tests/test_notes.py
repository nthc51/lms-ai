"""Sổ ghi chú (AI Studio S4) và nhật ký token ai_calls."""

import uuid

from sqlalchemy import select

from app.ai.llm import FakeLLMProvider
from app.ai.models import AiCall
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_job
from app.modules.materials.models import Source
from app.modules.studio.jobs import merge_notes
from app.modules.studio.models import Note, SourceGuide, StudioStatus
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from app.worker.tasks import notes_synth
from tests.helpers import API, make_admin, make_published_course, make_student, make_teacher
from tests.test_studio import _course_with_chunks, _llm


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def _enrolled(client):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    sv_id, sv = await make_student(client)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    return sv_id, sv, course, lesson


async def test_note_crud_is_private(client):
    _, sv, course, lesson = await _enrolled(client)
    r = await client.post(
        f"{API}/notes",
        json={
            "course_id": course["id"],
            "lesson_id": lesson["id"],
            "title": "  Ghi   nhớ ",
            "content_md": "Nội dung",
        },
        headers=sv,
    )
    assert r.status_code == 201 and r.json()["title"] == "Ghi nhớ" and r.json()["status"] == "ready"
    with_sources = await client.post(
        f"{API}/notes",
        json={
            "course_id": course["id"],
            "title": "Từ Studio",
            "content_md": "Ý [1]",
            "citations": [{"n": 1, "page_no": 2}],
        },
        headers=sv,
    )
    assert with_sources.json()["citations"] == [{"n": 1, "page_no": 2}]
    await client.delete(f"{API}/notes/{with_sources.json()['id']}", headers=sv)
    note_id = r.json()["id"]
    assert (
        await client.post(f"{API}/notes", json={"course_id": course["id"], "title": "   "}, headers=sv)
    ).status_code == 422
    r = await client.patch(f"{API}/notes/{note_id}", json={"content_md": "Đã sửa"}, headers=sv)
    assert r.json()["content_md"] == "Đã sửa"
    listed = (await client.get(f"{API}/notes", params={"course_id": course["id"]}, headers=sv)).json()
    assert [n["id"] for n in listed["items"]] == [note_id]

    _, other = await make_student(client, "khac@x.com")
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=other)
    assert (await client.get(f"{API}/notes", headers=other)).json()["total"] == 0
    assert (
        await client.patch(f"{API}/notes/{note_id}", json={"title": "x"}, headers=other)
    ).status_code == 404
    assert (await client.delete(f"{API}/notes/{note_id}", headers=other)).status_code == 404
    assert (await client.delete(f"{API}/notes/{note_id}", headers=sv)).status_code == 204
    # khóa chưa đăng ký: không ghi chú được
    _, stranger = await make_student(client, "la@x.com")
    r = await client.post(f"{API}/notes", json={"course_id": course["id"], "title": "x"}, headers=stranger)
    assert _code(r) == (403, "NOT_ENROLLED")


async def test_save_tutor_answer_as_note(client):
    sv_id, sv, course, lesson = await _enrolled(client)
    async with SessionLocal() as db:
        session = ChatSession(
            user_id=uuid.UUID(sv_id), course_id=uuid.UUID(course["id"]), lesson_id=uuid.UUID(lesson["id"])
        )
        db.add(session)
        await db.flush()
        db.add(ChatMessage(session_id=session.id, role=ChatRole.user, content="Đạo hàm là gì? " * 10))
        await db.flush()
        citations = [
            {
                "n": 1,
                "chunk_id": str(uuid.uuid4()),
                "lesson_id": lesson["id"],
                "page_no": 4,
                "start_sec": None,
            }
        ]
        answer = ChatMessage(
            session_id=session.id, role=ChatRole.assistant, content="Là giới hạn [1].", citations=citations
        )
        refused = ChatMessage(session_id=session.id, role=ChatRole.assistant, content="Xin lỗi", refused=True)
        db.add_all([answer, refused])
        await db.commit()
    r = await client.post(f"{API}/notes/from-message", json={"message_id": str(answer.id)}, headers=sv)
    assert r.status_code == 201
    note = r.json()
    assert note["content_md"] == "Là giới hạn [1]." and note["citations"] == citations
    assert note["title"].endswith("…") and len(note["title"]) <= 80 and note["lesson_id"] == lesson["id"]
    r = await client.post(f"{API}/notes/from-message", json={"message_id": str(refused.id)}, headers=sv)
    assert _code(r) == (409, "NOTHING_TO_SAVE")
    _, other = await make_student(client, "khac@x.com")
    r = await client.post(f"{API}/notes/from-message", json={"message_id": str(answer.id)}, headers=other)
    assert r.status_code == 404
    # sửa bỏ [1] thì nguồn cũng bỏ
    r = await client.patch(
        f"{API}/notes/{note['id']}", json={"content_md": "Viết lại không nguồn."}, headers=sv
    )
    assert r.json()["citations"] == []


def test_merge_notes_renumbers_citations():
    a = Note(
        title="A",
        content_md="Ý a [1] và [2]",
        citations=[{"n": 1, "chunk_id": "x"}, {"n": 2, "chunk_id": "y"}],
    )
    b = Note(title="B", content_md="Ý b [1], lạ [7]", citations=[{"n": 1, "chunk_id": "z"}])
    text, merged = merge_notes([a, b])
    assert text == "### A\nÝ a [1] và [2]\n\n### B\nÝ b [3], lạ "
    assert [(c["n"], c["chunk_id"]) for c in merged] == [(1, "x"), (2, "y"), (3, "z")]


async def test_synthesize_notes_into_study_guide(client, db, queue):
    _, sv, course, lesson = await _enrolled(client)
    ids = []
    for title in ("Một", "Hai"):
        r = await client.post(
            f"{API}/notes",
            json={
                "course_id": course["id"],
                "lesson_id": lesson["id"],
                "title": title,
                "content_md": f"Nội dung {title}",
            },
            headers=sv,
        )
        ids.append(r.json()["id"])
    r = await client.post(f"{API}/notes/synthesize", json={"note_ids": ids}, headers=sv)
    assert r.status_code == 202
    target = r.json()["note"]
    assert (
        target["status"] == "generating"
        and target["title"] == "Đề cương từ 2 ghi chú"
        and target["lesson_id"] == lesson["id"]
    )
    assert queue.jobs[-1] == ("notes_synth", uuid.UUID(target["id"]))
    assert _code(await client.patch(f"{API}/notes/{target['id']}", json={"title": "x"}, headers=sv)) == (
        409,
        "NOTE_GENERATING",
    )

    provider = FakeLLMProvider()
    await notes_synth({"llm": _llm(provider)}, r.json()["job_id"])
    assert "### Một\nNội dung Một" in provider.calls[0].prompt
    note = await db.get(Note, uuid.UUID(target["id"]))
    assert note.status.value == "ready" and note.content_md.startswith("## Đề cương từ ghi chú")


async def test_synthesize_rejects_foreign_or_mixed_notes(client):
    _, sv, course, _lesson = await _enrolled(client)
    mine = (
        await client.post(f"{API}/notes", json={"course_id": course["id"], "title": "A"}, headers=sv)
    ).json()
    r = await client.post(
        f"{API}/notes/synthesize", json={"note_ids": [mine["id"], str(uuid.uuid4())]}, headers=sv
    )
    assert r.status_code == 404
    _, gv2 = await make_teacher(client, "gv2@x.com")
    course2, _, _ = await make_published_course(client, gv2, title="Khóa khác")
    await client.post(f"{API}/courses/{course2['id']}/enroll", headers=sv)
    other = (
        await client.post(f"{API}/notes", json={"course_id": course2["id"], "title": "B"}, headers=sv)
    ).json()
    r = await client.post(f"{API}/notes/synthesize", json={"note_ids": [mine["id"], other["id"]]}, headers=sv)
    assert _code(r) == (422, "MIXED_COURSES")


# ---------- nhật ký token ----------


async def test_llm_calls_are_logged_and_shown_to_admin(client):
    llm = _llm(FakeLLMProvider(), ai_usage_log_enabled=True)
    from app.ai.prompts import load_prompt

    prompt = load_prompt("studio_briefing").render(scope="x", context="[1] nội dung")
    await llm.generate(prompt, op="studio_briefing")
    async with SessionLocal() as db:
        (row,) = (await db.scalars(select(AiCall))).all()
    assert (row.op, row.status, row.cached, row.prompt_version) == (
        "studio_briefing",
        "ok",
        False,
        "studio_briefing@v1",
    )
    assert row.tokens_in > 0 and row.tokens_out > 0
    # tắt nhật ký (mặc định trong test) thì không ghi
    await _llm(FakeLLMProvider()).generate(prompt, op="studio_briefing")
    _, ad = await make_admin(client)
    usage = (await client.get(f"{API}/admin/stats", headers=ad)).json()["ai_usage_7d"]
    assert usage == [
        {
            "op": "studio_briefing",
            "calls": 1,
            "cached_calls": 0,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
        }
    ]
    assert get_settings().ai_usage_log_enabled is False


# ---------- sửa lệch plan: hạn mức, kiểu nguồn, hàng kẹt generating ----------


async def _two_notes(client, sv, course):
    ids = []
    for title in ("Một", "Hai"):
        r = await client.post(f"{API}/notes", json={"course_id": course["id"], "title": title}, headers=sv)
        ids.append(r.json()["id"])
    return ids


async def test_synthesize_is_rate_limited_and_counts_only_created_jobs(client, queue, limiter):
    sv_id, sv, course, _lesson = await _enrolled(client)
    ids = await _two_notes(client, sv, course)
    key = f"notes_synth:{sv_id}"
    # yêu cầu bị từ chối (404 / 422) không tốn lượt
    bad = await client.post(f"{API}/notes/synthesize", json={"note_ids": [str(uuid.uuid4())]}, headers=sv)
    assert bad.status_code == 404 and key not in limiter.counts
    assert (
        await client.post(f"{API}/notes/synthesize", json={"note_ids": ids}, headers=sv)
    ).status_code == 202
    assert limiter.counts[key] == 1
    limiter.counts[key] = get_settings().studio_rate_limit_per_hour
    jobs = len(queue.jobs)
    r = await client.post(f"{API}/notes/synthesize", json={"note_ids": ids}, headers=sv)
    assert _code(r) == (429, "RATE_LIMITED") and r.headers["Retry-After"] == "3600"
    assert len(queue.jobs) == jobs  # bị chặn thì không tạo ghi chú / job
    listed = (await client.get(f"{API}/notes", params={"course_id": course["id"]}, headers=sv)).json()
    assert listed["total"] == 3


async def test_note_citation_requires_n(client):
    _, sv, course, _lesson = await _enrolled(client)
    body = {"course_id": course["id"], "title": "T", "content_md": "Ý [1]"}
    for bad in ([{"page_no": 2}], [{"n": "x"}], [{"n": 0}]):
        r = await client.post(f"{API}/notes", json={**body, "citations": bad}, headers=sv)
        assert r.status_code == 422, bad
    note = await client.post(
        f"{API}/notes", json={**body, "citations": [{"n": 1, "snippet": "s", "extra": [1]}]}, headers=sv
    )
    assert note.status_code == 201 and note.json()["citations"] == [{"n": 1, "snippet": "s", "extra": [1]}]
    r = await client.patch(f"{API}/notes/{note.json()['id']}", json={"content_md": "Bỏ nguồn"}, headers=sv)
    assert r.status_code == 200 and r.json()["citations"] == []


async def test_note_stuck_generating_reads_as_failed_and_is_editable(client, db, queue):
    _, sv, course, _lesson = await _enrolled(client)
    ids = await _two_notes(client, sv, course)
    r = await client.post(f"{API}/notes/synthesize", json={"note_ids": ids}, headers=sv)
    target, job_id = r.json()["note"]["id"], uuid.UUID(r.json()["job_id"])
    # job còn chạy: vẫn generating, chưa sửa được
    page = (await client.get(f"{API}/notes", params={"course_id": course["id"]}, headers=sv)).json()
    assert [n["status"] for n in page["items"] if n["id"] == target] == ["generating"]
    assert _code(await client.patch(f"{API}/notes/{target}", json={"title": "x"}, headers=sv))[1] == (
        "NOTE_GENERATING"
    )
    # handler bị hủy (CancelledError) hoặc worker chết: job failed nhưng ghi chú còn generating
    (await db.get(Job, job_id)).status = JobStatus.failed
    await db.commit()
    page = (await client.get(f"{API}/notes", params={"course_id": course["id"]}, headers=sv)).json()
    item = next(n for n in page["items"] if n["id"] == target)
    assert item["status"] == "failed" and item["content_md"].startswith("Không tổng hợp được")
    r = await client.patch(f"{API}/notes/{target}", json={"title": "Đã sửa"}, headers=sv)
    assert r.status_code == 200 and r.json()["status"] == "failed" and r.json()["title"] == "Đã sửa"
    db.expire_all()
    assert (await db.get(Note, uuid.UUID(target))).status == StudioStatus.failed


async def test_guide_stuck_generating_reads_as_failed(client, db):
    _, sv, _course, lesson = await _course_with_chunks(client, db)
    source_id = (await db.scalars(select(Source.id).where(Source.lesson_id == uuid.UUID(lesson["id"])))).one()
    job, _ = await create_job(db, "source_guide", source_id, created_by=None)
    db.add(SourceGuide(source_id=source_id, status=StudioStatus.generating))
    await db.commit()
    url = f"{API}/lessons/{lesson['id']}/documents"
    assert (await client.get(url, headers=sv)).json()[0]["guide"]["status"] == "generating"
    job.status = JobStatus.failed
    await db.commit()
    assert (await client.get(url, headers=sv)).json()[0]["guide"]["status"] == "failed"
