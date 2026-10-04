import asyncio
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.auth.models import Role
from app.modules.quiz.attempts import finalize_attempt
from app.modules.quiz.models import AttemptAnswer, AttemptStatus, Quiz, QuizAttempt, QuizQuestion
from tests.factories import make_lesson, make_question, make_user
from tests.helpers import API, make_published_quiz, make_student

TIMEOUT = 30  # mọi test đồng thời đều có giới hạn thời gian, không treo cả bộ test


async def _start(client, headers, quiz) -> dict:
    return (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=headers)).json()


def _answer(q, option="A") -> dict:
    return {"question_id": str(q.id), "selected_option_id": option}


async def _stored_answers(attempt_id: str) -> dict[str, tuple[str, bool | None]]:
    async with SessionLocal() as s:
        rows = await s.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == uuid.UUID(attempt_id)))
        return {str(a.question_id): (a.selected_option_id, a.is_correct) for a in rows}


async def test_submit_grades_with_final_answers_winning_over_autosave(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt_id = (await _start(client, sv, quiz))["id"]
    base = f"{API}/attempts/{attempt_id}"
    await client.put(f"{base}/answers/{qs[0].id}", json={"selected_option_id": "B"}, headers=sv)  # sai
    await client.put(f"{base}/answers/{qs[1].id}", json={"selected_option_id": "A"}, headers=sv)  # đúng
    r = await client.post(f"{base}/submit", json={"final_answers": [_answer(qs[0])]}, headers=sv)
    assert r.status_code == 200
    result = r.json()
    assert (result["status"], result["correct_count"], result["total"]) == ("completed", 2, 3)
    assert result["score"] == 66.67 and result["passed"] is True and result["submitted_at"]
    assert (result["attempt_id"], result["quiz_id"], result["attempt_no"]) == (attempt_id, quiz["id"], 1)
    by_id = {q["id"]: q for q in result["questions"]}
    assert [q["id"] for q in result["questions"]] == [str(q.id) for q in qs]
    assert by_id[str(qs[0].id)]["selected_option_id"] == "A" and by_id[str(qs[0].id)]["is_correct"] is True
    skipped = by_id[str(qs[2].id)]
    assert skipped["selected_option_id"] is None and skipped["is_correct"] is False
    assert skipped["correct_option_id"] == "A" and skipped["explanation"]
    assert len(skipped["options"]) == 4 and skipped["stem"]
    assert (await client.get(f"{base}/result", headers=sv)).json() == result
    # is_correct được ghi vào DB lúc chốt (câu bỏ trống không có dòng)
    assert await _stored_answers(attempt_id) == {str(qs[0].id): ("A", True), str(qs[1].id): ("A", True)}


async def test_submit_without_answers_scores_zero_and_fails(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    base = f"{API}/attempts/{(await _start(client, sv, quiz))['id']}"
    await client.put(f"{base}/answers/{qs[0].id}", json={"selected_option_id": "C"}, headers=sv)
    r = await client.post(f"{base}/submit", json={"final_answers": None}, headers=sv)
    assert r.status_code == 200
    result = r.json()
    assert (result["score"], result["passed"], result["correct_count"], result["total"]) == (0.0, False, 0, 3)
    assert {q["selected_option_id"] for q in result["questions"]} == {"C", None}


async def test_closed_attempt_rejects_resubmit_and_autosave(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    base = f"{API}/attempts/{(await _start(client, sv, quiz))['id']}"
    assert (await client.post(f"{base}/submit", headers=sv)).status_code == 200
    r = await client.post(f"{base}/submit", json={}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ATTEMPT_CLOSED")
    r = await client.put(f"{base}/answers/{qs[0].id}", json={"selected_option_id": "A"}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ATTEMPT_CLOSED")


async def test_concurrent_submits_finalize_exactly_once(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt_id = (await _start(client, sv, quiz))["id"]
    url = f"{API}/attempts/{attempt_id}/submit"
    all_right = {"final_answers": [_answer(q, "A") for q in qs]}
    all_wrong = {"final_answers": [_answer(q, "B") for q in qs]}
    r1, r2 = await asyncio.wait_for(
        asyncio.gather(
            client.post(url, json=all_right, headers=sv), client.post(url, json=all_wrong, headers=sv)
        ),
        TIMEOUT,
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    winner, loser = (r1, r2) if r1.status_code == 200 else (r2, r1)
    assert loser.json()["error"]["code"] == "ATTEMPT_CLOSED"
    # chỉ đáp án của lần nộp thắng được ghi và chấm
    assert winner.json()["score"] in (0.0, 100.0)
    assert (await client.get(f"{API}/attempts/{attempt_id}/result", headers=sv)).json() == winner.json()
    expected = "A" if winner.json()["score"] == 100.0 else "B"
    assert {opt for opt, _ in (await _stored_answers(attempt_id)).values()} == {expected}


async def test_submit_waits_for_an_autosave_in_flight_and_grades_it(client, db):
    """Autosave đang giữ FOR SHARE: lệnh chốt (UPDATE) phải đợi, rồi chấm cả đáp án vừa autosave."""
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt_id = (await _start(client, sv, quiz))["id"]
    async with SessionLocal() as autosave:
        locked = await autosave.scalar(
            select(QuizAttempt.status)
            .where(QuizAttempt.id == uuid.UUID(attempt_id))
            .with_for_update(read=True)
        )
        assert locked == AttemptStatus.in_progress
        submit = asyncio.create_task(client.post(f"{API}/attempts/{attempt_id}/submit", headers=sv))
        await asyncio.sleep(0.5)
        assert not submit.done()  # bị chặn bởi FOR SHARE của autosave
        autosave.add(
            AttemptAnswer(attempt_id=uuid.UUID(attempt_id), question_id=qs[0].id, selected_option_id="A")
        )
        await autosave.commit()
    r = await asyncio.wait_for(submit, TIMEOUT)
    assert r.status_code == 200
    assert (r.json()["correct_count"], r.json()["score"]) == (1, 33.33)


async def test_concurrent_autosave_and_submit_never_writes_after_finalize(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt_id = (await _start(client, sv, quiz))["id"]
    base = f"{API}/attempts/{attempt_id}"
    saves = [client.put(f"{base}/answers/{q.id}", json={"selected_option_id": "A"}, headers=sv) for q in qs]
    *saved, submitted = await asyncio.wait_for(
        asyncio.gather(*saves, client.post(f"{base}/submit", headers=sv)), TIMEOUT
    )
    assert submitted.status_code == 200
    for r in saved:
        assert r.status_code == 200 or (r.status_code, r.json()["error"]["code"]) == (409, "ATTEMPT_CLOSED")
    accepted = {r.json()["question_id"] for r in saved if r.status_code == 200}
    stored = await _stored_answers(attempt_id)
    # đúng những autosave được nhận đã có mặt (và đã chấm) lúc chốt; autosave bị từ chối không để lại gì
    assert set(stored) == accepted and all(ok is True for _, ok in stored.values())
    assert submitted.json()["correct_count"] == len(accepted)


async def test_invalid_final_answers_leave_attempt_open(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt_id = (await _start(client, sv, quiz))["id"]
    base = f"{API}/attempts/{attempt_id}"
    foreign = [{"question_id": str(uuid.uuid4()), "selected_option_id": "A"}]
    assert (
        await client.post(f"{base}/submit", json={"final_answers": foreign}, headers=sv)
    ).status_code == 422
    twice = [_answer(qs[0]), _answer(qs[0], "B")]
    assert (await client.post(f"{base}/submit", json={"final_answers": twice}, headers=sv)).status_code == 422
    bad_option = [_answer(qs[0]), _answer(qs[1], "Z")]
    r = await client.post(f"{base}/submit", json={"final_answers": bad_option}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert await _stored_answers(attempt_id) == {}  # không ghi một phần
    r = await client.get(f"{base}/result", headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")  # chưa nộp
    _, other = await make_student(client, "sv2@x.com")
    assert (await client.get(f"{base}/result", headers=other)).status_code == 404
    assert (await client.post(f"{base}/submit", headers=other)).status_code == 404
    assert (await client.get(f"{API}/attempts/{uuid.uuid4()}/result", headers=sv)).status_code == 404
    # bài vẫn mở: autosave và nộp vẫn được
    r = await client.put(f"{base}/answers/{qs[0].id}", json={"selected_option_id": "A"}, headers=sv)
    assert r.status_code == 200
    assert (await client.post(f"{base}/submit", headers=sv)).json()["correct_count"] == 1
    # bài đã nộp vẫn là 404 với người khác
    assert (await client.get(f"{base}/result", headers=other)).status_code == 404


async def test_attempt_limit(client, db):
    _, sv, _, quiz, _ = await make_published_quiz(client, db, max_attempts=2)
    first = await _start(client, sv, quiz)
    await client.post(f"{API}/attempts/{first['id']}/submit", headers=sv)
    second = await _start(client, sv, quiz)
    assert second["attempt_no"] == 2 and second["id"] != first["id"]
    await client.post(f"{API}/attempts/{second['id']}/submit", headers=sv)
    r = await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "QUIZ_ATTEMPT_LIMIT")
    [item] = (await client.get(f"{API}/quizzes", params={"lesson_id": quiz["lesson_id"]}, headers=sv)).json()[
        "items"
    ]  # Page[QuizOut]
    assert item["attempts_used"] == 2


async def test_finalize_is_atomic_against_another_finalizer(db):
    """Như cron B1 chốt bài hết giờ đúng lúc học viên bấm nộp: chỉ một bên chốt được."""
    teacher = await make_user(db)
    student = await make_user(db, Role.student)
    _, lesson = await make_lesson(db, teacher)
    question = await make_question(db, lesson.id)
    quiz = Quiz(lesson_id=lesson.id, title="Quiz")
    db.add(quiz)
    await db.flush()
    db.add(QuizQuestion(quiz_id=quiz.id, question_id=question.id, position=1))
    attempt = QuizAttempt(
        quiz_id=quiz.id, user_id=student.id, attempt_no=1, question_order=[str(question.id)]
    )
    db.add(attempt)
    await db.commit()
    attempt_id = attempt.id  # đọc trước: rollback() làm các object ORM hết hạn
    assert await finalize_attempt(db, attempt_id, status=AttemptStatus.timed_out) is True
    await db.commit()
    assert await finalize_attempt(db, attempt_id) is False
    await db.rollback()
    attempt = await db.get(QuizAttempt, attempt_id, populate_existing=True)
    assert attempt.status == AttemptStatus.timed_out and attempt.score == 0.0
    assert attempt.submitted_at is not None
