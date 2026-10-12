"""B3: AI giải thích câu học viên làm sai, dựa trên đoạn tài liệu nguồn của câu hỏi."""

import uuid

from sqlalchemy import select, update

from app.core.config import get_settings
from app.modules.quiz.models import AttemptAnswer, Question
from tests.factories import BINARY_SEARCH, seed_chunks
from tests.helpers import API, make_published_quiz, make_student


async def _submitted(client, db, sv, quiz, qs, answers: dict[int, str]):
    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    final = [{"question_id": str(qs[i].id), "selected_option_id": o} for i, o in answers.items()]
    r = await client.post(f"{API}/attempts/{attempt['id']}/submit", json={"final_answers": final}, headers=sv)
    assert r.status_code == 200, r.text
    return attempt["id"]


def _url(attempt_id, question) -> str:
    return f"{API}/attempts/{attempt_id}/answers/{question.id}/explain"


async def test_explains_wrong_answer_from_source_chunk_and_reuses_saved_text(client, db, llm):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    [chunk] = await seed_chunks(db, qs[0].lesson_id, [BINARY_SEARCH])
    await db.execute(update(Question).where(Question.id == qs[0].id).values(source_chunk_id=chunk.id))
    await db.commit()
    attempt_id = await _submitted(client, db, sv, quiz, qs, {0: "B", 1: "A"})

    r = await client.post(_url(attempt_id, qs[0]), headers=sv)
    assert r.status_code == 200, r.text
    assert r.json()["text"] and r.json()["source_page_no"] == chunk.page_no
    [call] = [c for c in llm.calls if c.op == "quiz_explain"]
    assert BINARY_SEARCH[:40] in call.prompt  # gửi đúng đoạn tài liệu nguồn
    assert "B. Mảng rỗng" in call.prompt and "A. Mảng đã sắp xếp" in call.prompt
    saved = await db.scalar(
        select(AttemptAnswer.ai_explanation).where(
            AttemptAnswer.attempt_id == uuid.UUID(attempt_id), AttemptAnswer.question_id == qs[0].id
        )
    )
    assert saved == r.json()["text"]

    again = await client.post(_url(attempt_id, qs[0]), headers=sv)
    assert again.json()["text"] == r.json()["text"]
    assert len([c for c in llm.calls if c.op == "quiz_explain"]) == 1  # lần sau không gọi AI


async def test_blank_answer_is_explained_but_correct_answer_is_not(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt_id = await _submitted(client, db, sv, quiz, qs, {1: "A"})
    r = await client.post(_url(attempt_id, qs[0]), headers=sv)  # bỏ trống
    assert r.status_code == 200 and r.json()["source_page_no"] is None
    r = await client.post(_url(attempt_id, qs[1]), headers=sv)  # làm đúng
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")


async def test_only_owner_after_submitting(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db, max_attempts=2)
    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    r = await client.post(_url(attempt["id"], qs[0]), headers=sv)
    assert (r.status_code, r.json()["error"]["message"]) == (409, "Nộp bài xong mới xem được giải thích")
    await client.post(f"{API}/attempts/{attempt['id']}/submit", json={}, headers=sv)
    _, other = await make_student(client, "sv2@x.com")
    assert (await client.post(_url(attempt["id"], qs[0]), headers=other)).status_code == 404
    assert (
        await client.post(f"{API}/attempts/{attempt['id']}/answers/{uuid.uuid4()}/explain", headers=sv)
    ).status_code == 404


async def test_ai_error_is_503_and_rate_limit_is_429(client, db, llm, monkeypatch):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt_id = await _submitted(client, db, sv, quiz, qs, {0: "B", 1: "B", 2: "B"})
    llm.replies = [ValueError("hỏng")]
    r = await client.post(_url(attempt_id, qs[0]), headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "AI_UNAVAILABLE")

    monkeypatch.setattr(
        get_settings(), "quiz_explain_rate_limit_per_hour", 2
    )  # lần lỗi ở trên đã tính 1 lượt
    assert (await client.post(_url(attempt_id, qs[1]), headers=sv)).status_code == 200
    r = await client.post(_url(attempt_id, qs[2]), headers=sv)
    assert r.status_code == 429 and "Retry-After" in r.headers
