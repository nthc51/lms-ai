import asyncio
import uuid

from app.modules.jobs.models import Job
from app.modules.quiz.models import ReviewStatus
from tests.factories import LONG_LESSON_TEXT, make_question, seed_chunks
from tests.helpers import API, make_published_course, make_student, make_teacher


async def _lesson_with_material(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    [chunk] = await seed_chunks(db, uuid.UUID(lesson["id"]), [LONG_LESSON_TEXT])
    return gv, course, lesson, chunk


async def test_generate_returns_202_and_enqueues_one_job_for_double_click(client, db, queue):
    gv, _, lesson, _ = await _lesson_with_material(client, db)
    url = f"{API}/lessons/{lesson['id']}/questions/generate"
    r1, r2 = await asyncio.gather(
        client.post(url, json={"count": 5}, headers=gv), client.post(url, json={"count": 5}, headers=gv)
    )
    assert r1.status_code == r2.status_code == 202
    assert r1.json()["job_id"] == r2.json()["job_id"]
    assert queue.jobs == [("quiz_gen", uuid.UUID(lesson["id"]))]
    job = await db.get(Job, uuid.UUID(r1.json()["job_id"]))
    assert job.payload == {"count": 5, "difficulty": {"easy": 0.3, "medium": 0.5, "hard": 0.2}}
    assert (await client.get(f"{API}/jobs/{job.id}", headers=gv)).json()["type"] == "quiz_gen"


async def test_generate_requires_owner_valid_input_and_ready_material(client, db):
    gv, _, lesson, _ = await _lesson_with_material(client, db)
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, sv = await make_student(client)
    url = f"{API}/lessons/{lesson['id']}/questions/generate"
    assert (await client.post(url, json={}, headers=gv2)).status_code == 404
    r = await client.post(url, json={}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
    assert (await client.post(url, json={"count": 0}, headers=gv)).status_code == 422
    bad_mix = {"difficulty": {"easy": 0, "medium": 0, "hard": 0}}
    assert (await client.post(url, json=bad_mix, headers=gv)).status_code == 422
    _, _, empty = await make_published_course(client, gv, title="Khóa chưa có tài liệu")
    r = await client.post(f"{API}/lessons/{empty['id']}/questions/generate", json={}, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")


async def test_list_filters_by_review_status_and_shows_source(client, db):
    gv, _, lesson, chunk = await _lesson_with_material(client, db)
    lid = uuid.UUID(lesson["id"])
    pending = await make_question(
        db,
        lid,
        stem="Câu hỏi chờ duyệt số một?",
        review_status=ReviewStatus.pending,
        source_chunk_id=chunk.id,
    )
    await make_question(db, lid, stem="Câu hỏi đã duyệt số hai?")
    url = f"{API}/lessons/{lesson['id']}/questions"
    [item] = (await client.get(url, params={"review_status": "pending"}, headers=gv)).json()["items"]
    assert item["id"] == str(pending.id) and item["review_status"] == "pending"
    assert item["source_page_no"] == 1 and item["source_excerpt"].startswith("Tìm kiếm nhị phân")
    assert item["correct_option_id"] == "A" and item["ai_original"] == {"stem": "Câu hỏi chờ duyệt số một?"}
    assert (await client.get(url, headers=gv)).json()["total"] == 2


async def test_review_edit_keeps_ai_original_then_approve_and_reject(client, db):
    gv, _, lesson, _ = await _lesson_with_material(client, db)
    lid = uuid.UUID(lesson["id"])
    q = await make_question(db, lid, review_status=ReviewStatus.pending)
    url = f"{API}/questions/{q.id}"
    edit = {"action": "edit", "stem": "Tìm kiếm nhị phân chỉ dùng được khi nào?", "correct_option_id": "A"}
    body = (await client.patch(url, json=edit, headers=gv)).json()
    assert body["review_status"] == "edited" and body["stem"] == "Tìm kiếm nhị phân chỉ dùng được khi nào?"
    assert body["ai_original"] == {"stem": q.stem}  # bản gốc của AI không đổi
    assert (await client.patch(url, json={"action": "approve"}, headers=gv)).json()[
        "review_status"
    ] == "edited"
    two_options = {"action": "edit", "options": [{"id": "A", "text": "x"}, {"id": "B", "text": "y"}]}
    r = await client.patch(url, json=two_options, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert (await client.patch(url, json={"action": "edit"}, headers=gv)).status_code == 422
    assert (await client.patch(url, json={"action": "reject"}, headers=gv)).json()[
        "review_status"
    ] == "rejected"

    q2 = await make_question(db, lid, stem="Câu thứ hai để duyệt thử?", review_status=ReviewStatus.pending)
    r = await client.patch(f"{API}/questions/{q2.id}", json={"action": "approve"}, headers=gv)
    assert r.json()["review_status"] == "approved"
    _, gv2 = await make_teacher(client, "gv2@x.com")
    assert (await client.patch(url, json={"action": "approve"}, headers=gv2)).status_code == 404


async def test_question_in_published_quiz_cannot_be_edited_or_rejected(client, db):
    from app.modules.quiz.models import Quiz, QuizQuestion, QuizStatus

    gv, _, lesson, _ = await _lesson_with_material(client, db)
    lid = uuid.UUID(lesson["id"])
    q = await make_question(db, lid)
    quiz = Quiz(lesson_id=lid, title="Quiz đã xuất bản", status=QuizStatus.published)
    db.add(quiz)
    await db.flush()
    db.add(QuizQuestion(quiz_id=quiz.id, question_id=q.id, position=0))
    await db.commit()
    url = f"{API}/questions/{q.id}"
    for body in ({"action": "reject"}, {"action": "edit", "stem": "Một câu hỏi đã được sửa đổi?"}):
        r = await client.patch(url, json=body, headers=gv)
        assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
    assert (await client.patch(url, json={"action": "approve"}, headers=gv)).status_code == 200
