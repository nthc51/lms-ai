"""AI Studio: sinh báo cáo / flashcard / hướng dẫn tài liệu, API studio, tài liệu và nguồn cho học viên, gợi ý hỏi tiếp."""

import json
import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_job
from app.modules.materials.models import Source
from app.modules.studio.generation import (
    batches,
    fingerprint,
    generate_flashcards,
    generate_report,
    guide_document,
    load_scope_chunks,
)
from app.modules.studio.models import (
    ArtifactKind,
    FlashcardReview,
    SourceGuide,
    StudioStatus,
    StudyArtifact,
)
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from app.worker.tasks import ingest_pdf, source_guide, studio_gen
from tests.factories import LONG_LESSON_TEXT, seed_chunks
from tests.fakes import RecordingQueue
from tests.helpers import API, make_published_course, make_student, make_teacher
from tests.test_ai_retry import Sleeps


def _llm(provider=None, **settings_kw) -> LLMClient:
    return LLMClient(
        provider or FakeLLMProvider(), get_settings().model_copy(update=settings_kw), sleep=Sleeps()
    )


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def _course_with_chunks(client, db, contents=None, headings=None):
    """Giảng viên + khóa đã xuất bản + bài có tài liệu đã xử lý; học viên đã đăng ký. Trả (gv, sv, course, lesson)."""
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    await seed_chunks(
        db,
        uuid.UUID(lesson["id"]),
        contents or [LONG_LESSON_TEXT, "Đoạn hai về độ phức tạp."],
        heading_paths=headings,
    )
    _, sv = await make_student(client)
    assert (await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)).status_code == 201
    return gv, sv, course, lesson


# ---------- sinh nội dung (hàm thuần + DB) ----------


async def test_scope_chunks_fingerprint_and_batches(client, db):
    _, _, course, lesson = await _course_with_chunks(client, db, ["một hai ba", "bốn năm sáu", "bảy tám"])
    chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    assert [c.content for c in chunks] == ["một hai ba", "bốn năm sáu", "bảy tám"]
    assert fingerprint(chunks) == fingerprint(list(chunks)) != fingerprint(chunks[:2])
    parts = batches(chunks, budget=chunks[0].token_count + chunks[1].token_count)
    assert [[n for n, _ in p] for p in parts] == [[1, 2], [3]]  # nhãn [n] toàn cục giữ nguyên giữa các phần


async def test_report_single_call_keeps_only_valid_citations(client, db):
    _, _, course, lesson = await _course_with_chunks(client, db)
    chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    provider = FakeLLMProvider(["## Đề cương\n- Ý A [1]\n- Ý B [2][9]"])
    out = await generate_report(_llm(provider), ArtifactKind.study_guide, "Bài: X", chunks, get_settings())
    assert out.content_md == "## Đề cương\n- Ý A [1]\n- Ý B [2]"  # [9] không tồn tại: bỏ
    assert [c["n"] for c in out.citations] == [1, 2] and out.citations[0]["snippet"]
    assert [c.op for c in provider.calls] == ["studio_study_guide"]
    assert out.prompt_version == "studio_study_guide@v1"


async def test_long_material_is_mapped_then_reduced(client, db):
    _, _, course, lesson = await _course_with_chunks(client, db, ["a " * 50, "b " * 50, "c " * 50])
    chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    provider = FakeLLMProvider(["- ý một [1]", "- ý hai [2]", "- ý ba [3]", "## FAQ\n### Hỏi?\nĐáp [3]"])
    settings = get_settings().model_copy(update={"studio_max_input_tokens": chunks[0].token_count})
    out = await generate_report(_llm(provider), ArtifactKind.faq, "Bài: X", chunks, settings)
    assert [c.op for c in provider.calls] == ["studio_map"] * 3 + ["studio_faq"]
    assert "[2] (Bài:" in provider.calls[1].prompt  # phần thứ hai giữ nhãn toàn cục [2]
    assert "- ý hai [2]" in provider.calls[3].prompt  # bước gộp nhận các bản tóm tắt
    assert [c["n"] for c in out.citations] == [3]


async def test_flashcards_dedupe_filter_sources_and_cap(client, db):
    _, _, course, lesson = await _course_with_chunks(client, db)
    chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    cards = [
        {"front": "Tìm kiếm nhị phân?", "back": "Chia đôi.", "sources": [1, 7]},
        {"front": "  tìm kiếm   NHỊ phân? ", "back": "Trùng.", "sources": [1]},
        {"front": "Độ phức tạp?", "back": "O(log n).", "sources": [2]},
    ]
    provider = FakeLLMProvider([json.dumps({"cards": cards}, ensure_ascii=False)])
    out = await generate_flashcards(_llm(provider), "Bài: X", chunks, get_settings())
    assert [c["front"] for c in out.cards] == ["Tìm kiếm nhị phân?", "Độ phức tạp?"]
    assert out.cards[0]["sources"] == [1] and [c["n"] for c in out.citations] == [1, 2]


async def test_flashcards_all_invalid_raises(client, db):
    _, _, course, lesson = await _course_with_chunks(client, db)
    chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    provider = FakeLLMProvider(["không phải json", "vẫn không phải json"])
    with pytest.raises(ValueError, match="không soạn được flashcard"):
        await generate_flashcards(_llm(provider), "Bài: X", chunks, get_settings())


async def test_guide_document_covers_every_heading_first(client, db):
    contents = ["mở đầu " * 30, "mục một tiếp " * 30, "mục hai " * 30]
    _, _, course, lesson = await _course_with_chunks(client, db, contents, ["Mở đầu", "Mở đầu", "Mục hai"])
    chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    doc = guide_document(chunks, budget=chunks[0].token_count + chunks[2].token_count)
    assert doc.index("## Mở đầu") < doc.index("## Mục hai") and "mục một tiếp" not in doc


# ---------- API studio ----------


async def test_studio_request_creates_job_then_shares_result(client, db, queue):
    gv, sv, course, lesson = await _course_with_chunks(client, db)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    r = await client.post(f"{API}/studio/faq", json=body, headers=sv)
    assert r.status_code == 202 and r.json()["status"] == "generating"
    artifact_id, job_id = r.json()["artifact_id"], r.json()["job_id"]
    assert queue.jobs == [("studio_gen", uuid.UUID(artifact_id))]
    # bấm lại khi đang sinh: không tạo job mới
    again = await client.post(f"{API}/studio/faq", json=body, headers=sv)
    assert again.status_code == 202 and again.json()["job_id"] == job_id and len(queue.jobs) == 1

    await studio_gen({"llm": _llm()}, job_id)
    r = await client.get(f"{API}/studio", params=body, headers=sv)
    faq = next(i for i in r.json()["items"] if i["kind"] == "faq")
    assert (faq["status"], faq["artifact_id"], faq["stale"]) == ("ready", artifact_id, False)
    assert r.json()["has_content"] is True and r.json()["can_regenerate"] is False

    art = (await client.get(f"{API}/studio/artifacts/{artifact_id}", headers=sv)).json()
    assert art["content_md"].startswith("## Nội dung mô phỏng") and art["citations"][0]["n"] == 1
    # người khác trong khóa dùng chung, không sinh lại
    r = await client.post(f"{API}/studio/faq", json=body, headers=gv)
    assert r.status_code == 200 and r.json() == {
        "artifact_id": artifact_id,
        "status": "ready",
        "job_id": None,
    }


async def test_material_change_marks_stale_and_regenerates(client, db, queue):
    _gv, sv, course, lesson = await _course_with_chunks(client, db)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    first = (await client.post(f"{API}/studio/briefing", json=body, headers=sv)).json()
    await studio_gen({"llm": _llm()}, first["job_id"])
    await seed_chunks(db, uuid.UUID(lesson["id"]), ["Tài liệu mới thêm vào bài."])
    item = next(
        i
        for i in (await client.get(f"{API}/studio", params=body, headers=sv)).json()["items"]
        if i["kind"] == "briefing"
    )
    assert item["stale"] is True and item["artifact_id"] == first["artifact_id"]
    r = await client.post(f"{API}/studio/briefing", json=body, headers=sv)
    assert r.status_code == 202 and r.json()["artifact_id"] != first["artifact_id"]


async def test_failed_generation_is_reported(client, db, queue):
    _, sv, course, lesson = await _course_with_chunks(client, db)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    r = (await client.post(f"{API}/studio/timeline", json=body, headers=sv)).json()
    await studio_gen({"llm": _llm(FakeLLMProvider([RuntimeError("AI sập")]))}, r["job_id"])
    item = next(
        i
        for i in (await client.get(f"{API}/studio", params=body, headers=sv)).json()["items"]
        if i["kind"] == "timeline"
    )
    assert item["status"] == "failed" and item["artifact_id"] is None and item["error"]
    job = await db.get(Job, uuid.UUID(r["job_id"]))
    assert job.status == JobStatus.failed


async def test_studio_access_rules_and_rate_limit(client, db, limiter):
    gv, sv, course, lesson = await _course_with_chunks(client, db)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    _, outsider = await make_student(client, "khac@x.com")
    assert _code(await client.post(f"{API}/studio/faq", json=body, headers=outsider)) == (403, "NOT_ENROLLED")
    assert _code(await client.post(f"{API}/studio/faq", json={**body, "force": True}, headers=sv)) == (
        403,
        "FORBIDDEN",
    )
    other = {"course_id": str(uuid.uuid4()), "lesson_id": lesson["id"]}
    assert (await client.post(f"{API}/studio/faq", json=other, headers=sv)).status_code == 404
    limiter.counts[f"studio:{(await client.get(f'{API}/me', headers=sv)).json()['id']}"] = 10
    assert _code(await client.post(f"{API}/studio/faq", json=body, headers=sv)) == (429, "RATE_LIMITED")
    # giảng viên không bị giới hạn
    assert (await client.post(f"{API}/studio/faq", json=body, headers=gv)).status_code == 202


async def test_no_material_is_409(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    assert _code(await client.post(f"{API}/studio/faq", json=body, headers=gv)) == (409, "NO_CONTENT")
    assert (await client.get(f"{API}/studio", params=body, headers=gv)).json()["has_content"] is False


async def test_course_scope_uses_all_lessons(client, db, queue):
    _, sv, course, _lesson = await _course_with_chunks(client, db)
    r = await client.post(f"{API}/studio/study_guide", json={"course_id": course["id"]}, headers=sv)
    assert r.status_code == 202
    artifact = await db.get(StudyArtifact, uuid.UUID(r.json()["artifact_id"]))
    assert artifact.lesson_id is None


async def test_teacher_edit_marks_reviewed_and_survives_material_change(client, db, queue):
    gv, sv, course, lesson = await _course_with_chunks(client, db)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    r = (await client.post(f"{API}/studio/study_guide", json=body, headers=gv)).json()
    await studio_gen({"llm": _llm()}, r["job_id"])
    aid = r["artifact_id"]
    assert _code(
        await client.patch(f"{API}/studio/artifacts/{aid}", json={"content_md": "x"}, headers=sv)
    ) == (403, "FORBIDDEN")
    edited = await client.patch(
        f"{API}/studio/artifacts/{aid}", json={"content_md": "## Đã sửa\n- chỉ còn nguồn [1]"}, headers=gv
    )
    assert edited.json()["reviewed"] is True and [c["n"] for c in edited.json()["citations"]] == [1]
    await seed_chunks(db, uuid.UUID(lesson["id"]), ["Đoạn mới."])
    item = next(
        i
        for i in (await client.get(f"{API}/studio", params=body, headers=sv)).json()["items"]
        if i["kind"] == "study_guide"
    )
    assert (item["reviewed"], item["stale"]) == (True, False)
    r = await client.post(f"{API}/studio/study_guide", json=body, headers=sv)
    assert r.status_code == 200 and r.json()["artifact_id"] == aid  # học viên không làm mất bản đã duyệt
    forced = await client.post(f"{API}/studio/study_guide", json={**body, "force": True}, headers=gv)
    assert forced.status_code == 202


async def test_flashcard_review_is_per_user(client, db, queue):
    gv, sv, course, lesson = await _course_with_chunks(client, db)
    r = (
        await client.post(
            f"{API}/studio/flashcards",
            json={"course_id": course["id"], "lesson_id": lesson["id"]},
            headers=sv,
        )
    ).json()
    await studio_gen({"llm": _llm()}, r["job_id"])
    aid = r["artifact_id"]
    assert (
        await client.put(f"{API}/studio/artifacts/{aid}/cards/1", json={"known": True}, headers=sv)
    ).status_code == 204
    assert (
        await client.put(f"{API}/studio/artifacts/{aid}/cards/99", json={"known": True}, headers=sv)
    ).status_code == 404
    mine = (await client.get(f"{API}/studio/artifacts/{aid}", headers=sv)).json()
    theirs = (await client.get(f"{API}/studio/artifacts/{aid}", headers=gv)).json()
    assert mine["known_cards"] == [1] and theirs["known_cards"] == []
    assert len(mine["cards"]) >= 5 and mine["cards"][0]["sources"] == [1]
    await client.put(f"{API}/studio/artifacts/{aid}/cards/1", json={"known": False}, headers=sv)
    assert (await client.get(f"{API}/studio/artifacts/{aid}", headers=sv)).json()["known_cards"] == []


async def test_deleting_a_card_keeps_marks_on_the_right_cards(client, db, queue):
    """Lệch plan (8f): xóa một thẻ ở giữa thì dấu "Nhớ" của các thẻ sau đi theo thẻ, không lệch vị trí."""
    gv, sv, course, lesson = await _course_with_chunks(client, db)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    r = (await client.post(f"{API}/studio/flashcards", json=body, headers=sv)).json()
    await studio_gen({"llm": _llm()}, r["job_id"])
    aid = r["artifact_id"]
    cards = (await client.get(f"{API}/studio/artifacts/{aid}", headers=sv)).json()["cards"]
    last = len(cards) - 1
    for n in (0, 1, 3, last):
        await client.put(f"{API}/studio/artifacts/{aid}/cards/{n}", json={"known": True}, headers=sv)
    await client.put(f"{API}/studio/artifacts/{aid}/cards/2", json={"known": False}, headers=sv)
    del cards[1]
    edited = await client.patch(f"{API}/studio/artifacts/{aid}", json={"cards": cards}, headers=gv)
    assert edited.status_code == 200
    mine = (await client.get(f"{API}/studio/artifacts/{aid}", headers=sv)).json()
    assert mine["known_cards"] == [0, 2, last - 1]  # thẻ 1 bị xóa: mất dấu; thẻ 3 và thẻ cuối dời lên một
    rows = (
        await db.scalars(
            select(FlashcardReview)
            .where(FlashcardReview.artifact_id == uuid.UUID(aid))
            .execution_options(populate_existing=True)
        )
    ).all()
    assert sorted((x.card_no, x.known) for x in rows) == [(0, True), (1, False), (2, True), (last - 1, True)]


# ---------- tài liệu, nguồn, hướng dẫn ----------


async def test_documents_file_and_chunk_for_enrolled_students_only(client, db, storage):
    _gv, sv, course, lesson = await _course_with_chunks(client, db)
    docs = (await client.get(f"{API}/lessons/{lesson['id']}/documents", headers=sv)).json()
    assert len(docs) == 1 and docs[0]["title"] == "Tài liệu 1" and docs[0]["guide"] is None
    source_id = docs[0]["source_id"]
    r = await client.get(f"{API}/sources/{source_id}/file", headers=sv)
    assert r.status_code == 200 and r.json()["url"].startswith("memory://get/")
    chunk_id = (await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"])))[0].chunk_id
    c = (await client.get(f"{API}/chunks/{chunk_id}", headers=sv)).json()
    assert c["content"] == LONG_LESSON_TEXT and c["page_no"] == 1 and c["source_id"] == source_id
    _, outsider = await make_student(client, "khac@x.com")
    for path in (f"/lessons/{lesson['id']}/documents", f"/sources/{source_id}/file", f"/chunks/{chunk_id}"):
        assert (await client.get(f"{API}{path}", headers=outsider)).status_code == 403, path


async def test_source_guide_job_fills_guide(client, db):
    _, sv, _course, lesson = await _course_with_chunks(client, db)
    source_id = (await db.scalars(select(Source.id).where(Source.lesson_id == uuid.UUID(lesson["id"])))).one()
    job, _ = await create_job(db, "source_guide", source_id, created_by=None)
    await db.commit()
    provider = FakeLLMProvider()
    await source_guide({"llm": _llm(provider)}, str(job.id))
    assert (
        provider.calls[0].op == "source_guide" and provider.calls[0].model == get_settings().llm_cheap_model
    )
    doc = (await client.get(f"{API}/lessons/{lesson['id']}/documents", headers=sv)).json()[0]
    assert doc["title"] == "Tài liệu mô phỏng" and doc["guide"]["status"] == "ready"
    assert len(doc["guide"]["questions"]) == 5 and doc["guide"]["topics"]


async def test_source_guide_failure_is_recorded(client, db):
    _, _, _, lesson = await _course_with_chunks(client, db)
    source_id = (await db.scalars(select(Source.id).where(Source.lesson_id == uuid.UUID(lesson["id"])))).one()
    job, _ = await create_job(db, "source_guide", source_id, created_by=None)
    await db.commit()
    await source_guide({"llm": _llm(FakeLLMProvider(["không phải json", "vẫn không"]))}, str(job.id))
    guide = await db.get(SourceGuide, source_id, populate_existing=True)
    assert guide.status == StudioStatus.failed and guide.error_msg


async def test_ingest_done_queues_source_guide(db):
    from app.ai.embedder import FakeEmbedder
    from app.ai.vision import FakeVision
    from app.modules.jobs.service import create_job as cj
    from tests.factories import make_lesson, make_pdf_source, make_user
    from tests.fakes import InMemoryStorage
    from tests.pdfs import make_pdf

    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    storage = InMemoryStorage()
    source = await make_pdf_source(
        db, storage, teacher, lesson, make_pdf(["Trang một có nội dung đủ dài để chia đoạn."])
    )
    job, _ = await cj(db, "ingest_pdf", source.id, created_by=teacher.id)
    await db.commit()
    queue = RecordingQueue()
    await ingest_pdf(
        {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision(), "queue": queue},
        str(job.id),
    )
    assert queue.jobs == [("source_guide", source.id)]


# ---------- gợi ý hỏi tiếp ----------


async def _answered(db, course_id, lesson_id, user_id, *, refused=False) -> ChatMessage:
    async with SessionLocal() as s:
        session = ChatSession(
            user_id=uuid.UUID(user_id), course_id=uuid.UUID(course_id), lesson_id=uuid.UUID(lesson_id)
        )
        s.add(session)
        await s.flush()
        s.add(ChatMessage(session_id=session.id, role=ChatRole.user, content="Tìm kiếm nhị phân là gì?"))
        await s.flush()
        answer = ChatMessage(
            session_id=session.id, role=ChatRole.assistant, content="Là chia đôi [1].", refused=refused
        )
        s.add(answer)
        await s.commit()
        return answer


async def test_followups_generated_once_then_cached(client, db, llm):
    gv, sv, course, lesson = await _course_with_chunks(client, db)
    me = (await client.get(f"{API}/me", headers=sv)).json()
    answer = await _answered(db, course["id"], lesson["id"], me["id"])
    r = await client.post(f"{API}/tutor/messages/{answer.id}/followups", headers=sv)
    assert r.json() == {"questions": ["Câu hỏi tiếp 1?", "Câu hỏi tiếp 2?", "Câu hỏi tiếp 3?"]}
    calls = len(llm.calls)
    assert (await client.post(f"{API}/tutor/messages/{answer.id}/followups", headers=sv)).json() == r.json()
    assert len(llm.calls) == calls  # lần hai đọc lại, không gọi AI
    assert "Tìm kiếm nhị phân là gì?" in llm.calls[-1].prompt
    assert (await client.post(f"{API}/tutor/messages/{answer.id}/followups", headers=gv)).status_code == 404


async def test_followups_empty_for_refusal_and_on_ai_error(client, db, llm):
    _gv, sv, course, lesson = await _course_with_chunks(client, db)
    me = (await client.get(f"{API}/me", headers=sv)).json()
    refused = await _answered(db, course["id"], lesson["id"], me["id"], refused=True)
    assert (await client.post(f"{API}/tutor/messages/{refused.id}/followups", headers=sv)).json() == {
        "questions": []
    }
    normal = await _answered(db, course["id"], lesson["id"], me["id"])
    llm.replies.extend(["hỏng"] * 3)
    assert (await client.post(f"{API}/tutor/messages/{normal.id}/followups", headers=sv)).json() == {
        "questions": []
    }
    msg = await db.get(ChatMessage, normal.id, populate_existing=True)
    assert msg.followups is None  # lỗi thì không lưu, lần sau thử lại
