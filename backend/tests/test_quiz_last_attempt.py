"""Lượt làm gần nhất của học viên trả kèm quiz (my_last_attempt): trang bài học biết "Làm tiếp" / "Xem kết quả"
trên mọi thiết bị, không phụ thuộc localStorage của trình duyệt."""

import uuid
from datetime import timedelta

from sqlalchemy import func, update

from app.core.db import SessionLocal
from app.modules.quiz.models import QuizAttempt
from tests.helpers import API, make_published_quiz, make_student


async def _listed(client, headers, quiz):
    r = await client.get(f"{API}/quizzes", params={"lesson_id": quiz["lesson_id"]}, headers=headers)
    assert r.status_code == 200, r.text
    (item,) = r.json()["items"]
    return item


async def test_last_attempt_follows_progress_and_is_per_user(client, db):
    gv, sv, course, quiz, _ = await make_published_quiz(client, db, n_questions=2)
    assert (await _listed(client, sv, quiz))["my_last_attempt"] is None

    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    last = (await _listed(client, sv, quiz))["my_last_attempt"]
    assert (last["id"], last["status"], last["score"], last["expired"]) == (
        attempt["id"],
        "in_progress",
        None,
        False,
    )

    await client.post(f"{API}/attempts/{attempt['id']}/submit", json={}, headers=sv)
    last = (await _listed(client, sv, quiz))["my_last_attempt"]
    assert last["status"] == "completed" and last["score"] == 0.0

    one = (await client.get(f"{API}/quizzes/{quiz['id']}", headers=sv)).json()
    assert one["my_last_attempt"]["id"] == attempt["id"]

    _, other = await make_student(client, "ban-khac@x.com")
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=other)
    assert r.status_code in (200, 201), r.text
    assert (await _listed(client, other, quiz))["my_last_attempt"] is None  # của ai người nấy thấy
    assert (await _listed(client, gv, quiz))["my_last_attempt"] is None  # giảng viên không có trường này


async def test_overdue_attempt_is_marked_expired(client, db):
    _, sv, _, quiz, _ = await make_published_quiz(client, db, n_questions=1, time_limit_sec=600)
    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    async with SessionLocal() as s:
        await s.execute(
            update(QuizAttempt)
            .where(QuizAttempt.id == uuid.UUID(attempt["id"]))
            .values(deadline_at=func.clock_timestamp() - timedelta(seconds=30))
        )
        await s.commit()
    last = (await _listed(client, sv, quiz))["my_last_attempt"]
    assert (last["status"], last["expired"]) == ("in_progress", True)
    # mở kết quả thì bài được chốt timed_out
    r = await client.get(f"{API}/attempts/{attempt['id']}/result", headers=sv)
    assert r.status_code == 200, r.text
    assert (await _listed(client, sv, quiz))["my_last_attempt"]["status"] == "timed_out"
