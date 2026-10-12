"""B1: quiz có giới hạn thời gian (deadline, chốt bài khi hết giờ) và xáo trộn thứ tự câu hỏi."""

import random
import uuid
from datetime import timedelta

from sqlalchemy import func, select, update

from app.core.db import SessionLocal
from app.modules.quiz.attempts import LATE_GRACE, finalize_overdue_attempts
from app.modules.quiz.models import AttemptAnswer, AttemptStatus, QuizAttempt
from app.worker.tasks import finalize_overdue_quiz_attempts
from tests.helpers import API, make_published_quiz, make_student


async def _start(client, headers, quiz):
    return await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=headers)


async def _move_deadline(attempt_id: str, seconds_from_now: float) -> None:
    """Đặt deadline_at = giờ DB hiện tại + seconds_from_now (âm = đã qua)."""
    async with SessionLocal() as s:
        await s.execute(
            update(QuizAttempt)
            .where(QuizAttempt.id == uuid.UUID(attempt_id))
            .values(deadline_at=func.clock_timestamp() + timedelta(seconds=seconds_from_now))
        )
        await s.commit()


async def _attempt(db, attempt_id: str) -> QuizAttempt:
    return await db.scalar(
        select(QuizAttempt)
        .where(QuizAttempt.id == uuid.UUID(attempt_id))
        .execution_options(populate_existing=True)
    )


async def test_quiz_settings_time_limit_and_shuffle(client, db):
    gv, _, _, quiz, qs = await make_published_quiz(client, db, time_limit_sec=600, shuffle=True)
    assert (quiz["time_limit_sec"], quiz["shuffle"]) == (600, True)
    # Quiz đã xuất bản: không đổi được giới hạn thời gian; gửi lại đúng giá trị cũ thì được
    r = await client.patch(f"{API}/quizzes/{quiz['id']}", json={"time_limit_sec": None}, headers=gv)
    assert r.status_code == 409
    r = await client.patch(
        f"{API}/quizzes/{quiz['id']}",
        json={"time_limit_sec": 600, "shuffle": True, "title": "Mới"},
        headers=gv,
    )
    assert r.status_code == 200 and r.json()["title"] == "Mới"

    body = {"lesson_id": quiz["lesson_id"], "title": "Nháp", "question_ids": [str(qs[0].id)]}
    draft = (await client.post(f"{API}/quizzes", json=body, headers=gv)).json()
    assert (draft["time_limit_sec"], draft["shuffle"]) == (None, False)
    r = await client.patch(f"{API}/quizzes/{draft['id']}", json={"time_limit_sec": 300}, headers=gv)
    assert r.json()["time_limit_sec"] == 300
    r = await client.patch(f"{API}/quizzes/{draft['id']}", json={"title": "Nháp 2"}, headers=gv)
    assert r.json()["time_limit_sec"] == 300  # không gửi thì giữ nguyên
    r = await client.patch(f"{API}/quizzes/{draft['id']}", json={"time_limit_sec": None}, headers=gv)
    assert r.json()["time_limit_sec"] is None  # null tường minh = bỏ giới hạn
    r = await client.patch(f"{API}/quizzes/{draft['id']}", json={"time_limit_sec": 30}, headers=gv)
    assert r.status_code == 422  # tối thiểu 60 giây


async def test_timed_attempt_has_deadline_and_server_clock(client, db):
    _, sv, _, quiz, _ = await make_published_quiz(client, db, time_limit_sec=600)
    attempt = (await _start(client, sv, quiz)).json()
    stored = await _attempt(db, attempt["id"])
    assert abs((stored.deadline_at - stored.started_at).total_seconds() - 600) < 2
    assert attempt["deadline_at"] is not None and attempt["server_now"] is not None


async def test_autosave_after_deadline_closes_attempt_with_saved_answers(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db, time_limit_sec=600)
    attempt = (await _start(client, sv, quiz)).json()
    url = f"{API}/attempts/{attempt['id']}/answers"
    assert (
        await client.put(f"{url}/{qs[0].id}", json={"selected_option_id": "A"}, headers=sv)
    ).status_code == 200

    await _move_deadline(attempt["id"], -2)  # vừa hết giờ, còn trong 5 giây bù trễ: vẫn nhận
    assert (
        await client.put(f"{url}/{qs[1].id}", json={"selected_option_id": "B"}, headers=sv)
    ).status_code == 200

    await _move_deadline(attempt["id"], -(LATE_GRACE.total_seconds() + 5))
    r = await client.put(f"{url}/{qs[2].id}", json={"selected_option_id": "A"}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ATTEMPT_CLOSED")
    assert "hết giờ" in r.json()["error"]["message"]
    stored = await _attempt(db, attempt["id"])
    assert stored.status == AttemptStatus.timed_out and stored.score == round(100 / 3, 2)
    answers = list(await db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == stored.id)))
    assert len(answers) == 2  # câu 3 đến muộn không được lưu

    result = (await client.get(f"{API}/attempts/{attempt['id']}/result", headers=sv)).json()
    assert result["status"] == "timed_out" and result["correct_count"] == 1


async def test_submit_within_grace_is_accepted_but_late_submit_ignores_payload(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db, time_limit_sec=600, max_attempts=2)
    final = {"final_answers": [{"question_id": str(q.id), "selected_option_id": "A"} for q in qs]}

    first = (await _start(client, sv, quiz)).json()
    await _move_deadline(first["id"], -2)
    r = await client.post(f"{API}/attempts/{first['id']}/submit", json=final, headers=sv)
    assert r.status_code == 200 and (r.json()["status"], r.json()["score"]) == ("completed", 100.0)

    second = (await _start(client, sv, quiz)).json()
    await _move_deadline(second["id"], -60)
    r = await client.post(f"{API}/attempts/{second['id']}/submit", json=final, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ATTEMPT_CLOSED")
    stored = await _attempt(db, second["id"])
    assert (stored.status, stored.score) == (AttemptStatus.timed_out, 0.0)


async def test_starting_again_closes_overdue_attempt_and_counts_it(client, db):
    _, sv, _, quiz, _ = await make_published_quiz(client, db, time_limit_sec=600, max_attempts=2)
    first = (await _start(client, sv, quiz)).json()
    await _move_deadline(first["id"], -60)
    r = await _start(client, sv, quiz)
    assert r.status_code == 201 and r.json()["attempt_no"] == 2
    assert (await _attempt(db, first["id"])).status == AttemptStatus.timed_out

    await _move_deadline(r.json()["id"], -60)
    r = await _start(client, sv, quiz)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "QUIZ_ATTEMPT_LIMIT")


async def test_cron_closes_only_overdue_attempts(client, db):
    _, sv1, course, quiz, qs = await make_published_quiz(client, db, time_limit_sec=600)
    _, sv2 = await make_student(client, "sv2@x.com")
    assert (await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv2)).status_code == 201
    still_running = (await _start(client, sv2, quiz)).json()
    overdue = (await _start(client, sv1, quiz)).json()
    await client.put(
        f"{API}/attempts/{overdue['id']}/answers/{qs[0].id}", json={"selected_option_id": "A"}, headers=sv1
    )
    await _move_deadline(overdue["id"], -60)
    assert await finalize_overdue_attempts(SessionLocal) == 1
    assert await finalize_overdue_quiz_attempts({}) == 0  # chạy lại: không còn gì
    stored = await _attempt(db, overdue["id"])
    assert stored.status == AttemptStatus.timed_out and stored.score == round(100 / 3, 2)
    assert (await _attempt(db, still_running["id"])).status == AttemptStatus.in_progress


async def test_shuffle_gives_each_attempt_its_own_stable_order(client, db, monkeypatch):
    monkeypatch.setattr(random, "sample", lambda seq, k: list(reversed(seq)))
    _, sv, _, quiz, qs = await make_published_quiz(client, db, shuffle=True, n_questions=4)
    attempt = (await _start(client, sv, quiz)).json()
    expected = [str(q.id) for q in reversed(qs)]
    assert [q["id"] for q in attempt["questions"]] == expected
    again = (await _start(client, sv, quiz)).json()  # mở lại: giữ đúng thứ tự đã xáo
    assert [q["id"] for q in again["questions"]] == expected
