import asyncio
import uuid

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.modules.auth.models import User
from app.modules.quiz import attempts
from app.modules.quiz.models import AttemptStatus, QuizAttempt
from tests.helpers import API, keys_in, make_published_quiz, make_student

TIMEOUT = 30  # mọi test đồng thời đều có giới hạn thời gian, không treo cả bộ test


async def _start(client, headers, quiz):
    return await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=headers)


async def _set_status(attempt_id: str, status: AttemptStatus) -> None:
    async with SessionLocal() as s:
        await s.execute(
            update(QuizAttempt).where(QuizAttempt.id == uuid.UUID(attempt_id)).values(status=status)
        )
        await s.commit()


async def test_start_attempt_hides_answers_and_resumes(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    r = await _start(client, sv, quiz)
    assert r.status_code == 201
    attempt = r.json()
    assert (attempt["attempt_no"], attempt["status"], attempt["answers"]) == (1, "in_progress", {})
    assert [q["id"] for q in attempt["questions"]] == [str(q.id) for q in qs]
    assert [o["id"] for o in attempt["questions"][0]["options"]] == ["A", "B", "C", "D"]
    assert not {"correct_option_id", "explanation", "is_correct"} & keys_in(attempt)
    again = await _start(client, sv, quiz)
    assert again.status_code == 200 and again.json()["id"] == attempt["id"]
    stored = await db.scalar(select(QuizAttempt).where(QuizAttempt.id == uuid.UUID(attempt["id"])))
    assert stored.question_order == [str(q.id) for q in qs]
    assert stored.deadline_at is None  # B1 chưa áp dụng


async def test_two_tabs_starting_at_once_get_the_same_attempt(client, db):
    _, sv, _, quiz, _ = await make_published_quiz(client, db)
    r1, r2 = await asyncio.wait_for(
        asyncio.gather(_start(client, sv, quiz), _start(client, sv, quiz)), TIMEOUT
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 201]
    assert r1.json()["id"] == r2.json()["id"]
    rows = (await db.scalars(select(QuizAttempt).where(QuizAttempt.quiz_id == uuid.UUID(quiz["id"])))).all()
    assert [(a.attempt_no, a.status) for a in rows] == [(1, AttemptStatus.in_progress)]


async def test_attempt_limit_counts_finished_attempts_and_holds_under_concurrency(client, db):
    _, sv, _, quiz, _ = await make_published_quiz(client, db, max_attempts=2)
    first = (await _start(client, sv, quiz)).json()
    await _set_status(first["id"], AttemptStatus.completed)
    r1, r2 = await asyncio.wait_for(
        asyncio.gather(_start(client, sv, quiz), _start(client, sv, quiz)), TIMEOUT
    )
    assert sorted([r1.status_code, r2.status_code]) == [200, 201]
    assert r1.json()["id"] == r2.json()["id"] and r1.json()["attempt_no"] == 2
    await _set_status(r1.json()["id"], AttemptStatus.timed_out)
    results = await asyncio.wait_for(asyncio.gather(*[_start(client, sv, quiz) for _ in range(3)]), TIMEOUT)
    assert {(r.status_code, r.json()["error"]["code"]) for r in results} == {(409, "QUIZ_ATTEMPT_LIMIT")}
    count = len((await db.scalars(select(QuizAttempt.id))).all())
    assert count == 2


async def test_start_requires_published_quiz_enrollment_and_student_role(client, db):
    gv, sv, _, quiz, qs = await make_published_quiz(client, db)
    body = {"lesson_id": quiz["lesson_id"], "title": "Nháp", "question_ids": [str(qs[0].id)]}
    draft = (await client.post(f"{API}/quizzes", json=body, headers=gv)).json()
    assert (await _start(client, sv, draft)).status_code == 404
    assert (await _start(client, sv, {"id": uuid.uuid4()})).status_code == 404
    _, outsider = await make_student(client, "sv2@x.com")
    r = await _start(client, outsider, quiz)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")
    r = await _start(client, gv, quiz)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_autosave_validates_and_overwrites_and_blocks_quiz_delete(client, db):
    gv, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt = (await _start(client, sv, quiz)).json()
    url = f"{API}/attempts/{attempt['id']}/answers/{qs[0].id}"
    r = await client.put(url, json={"selected_option_id": "B"}, headers=sv)
    assert r.status_code == 200 and r.json()["selected_option_id"] == "B"
    await client.put(url, json={"selected_option_id": "A"}, headers=sv)  # đổi ý: ghi đè
    assert (await _start(client, sv, quiz)).json()["answers"] == {str(qs[0].id): "A"}
    r = await client.put(url, json={"selected_option_id": "Z"}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    foreign = f"{API}/attempts/{attempt['id']}/answers/{uuid.uuid4()}"
    assert (await client.put(foreign, json={"selected_option_id": "A"}, headers=sv)).status_code == 422
    _, other = await make_student(client, "sv2@x.com")
    assert (await client.put(url, json={"selected_option_id": "A"}, headers=other)).status_code == 404
    assert (await client.put(url, json={"selected_option_id": "A"}, headers=gv)).status_code == 404
    missing = f"{API}/attempts/{uuid.uuid4()}/answers/{qs[0].id}"
    assert (await client.put(missing, json={"selected_option_id": "A"}, headers=sv)).status_code == 404
    r = await client.delete(f"{API}/quizzes/{quiz['id']}", headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")


async def test_autosave_rejected_once_attempt_is_closed(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt = (await _start(client, sv, quiz)).json()
    await _set_status(attempt["id"], AttemptStatus.completed)
    url = f"{API}/attempts/{attempt['id']}/answers/{qs[0].id}"
    r = await client.put(url, json={"selected_option_id": "B"}, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ATTEMPT_CLOSED")


async def test_autosave_waits_for_a_concurrent_finalize_and_then_sees_it_closed(client, db):
    """Hợp đồng với Task 19: chốt bài khóa dòng attempt (UPDATE ... WHERE status='in_progress');
    autosave đang chạy song song phải đợi rồi nhận 409, không ghi đáp án sau khi đã chốt."""
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt = (await _start(client, sv, quiz)).json()
    url = f"{API}/attempts/{attempt['id']}/answers/{qs[0].id}"
    async with SessionLocal() as finalizer:
        closed = await finalizer.scalar(
            update(QuizAttempt)
            .where(
                QuizAttempt.id == uuid.UUID(attempt["id"]), QuizAttempt.status == AttemptStatus.in_progress
            )
            .values(status=AttemptStatus.completed)
            .returning(QuizAttempt.id)
        )
        assert closed is not None
        save = asyncio.create_task(client.put(url, json={"selected_option_id": "B"}, headers=sv))
        await asyncio.sleep(0.5)
        assert not save.done()  # bị chặn bởi khóa dòng của lệnh chốt bài
        await finalizer.commit()
    r = await asyncio.wait_for(save, TIMEOUT)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ATTEMPT_CLOSED")
    r = await _start(client, sv, quiz)  # max_attempts=1 đã dùng hết
    assert (r.status_code, r.json()["error"]["code"]) == (409, "QUIZ_ATTEMPT_LIMIT")


async def test_concurrent_autosaves_last_write_wins_without_errors(client, db):
    _, sv, _, quiz, qs = await make_published_quiz(client, db)
    attempt = (await _start(client, sv, quiz)).json()
    puts = [
        client.put(
            f"{API}/attempts/{attempt['id']}/answers/{q.id}", json={"selected_option_id": o}, headers=sv
        )
        for q in qs
        for o in ("B", "C")
    ]
    results = await asyncio.wait_for(asyncio.gather(*puts), TIMEOUT)
    assert {r.status_code for r in results} == {200}
    assert all(r.json()["answered_at"] for r in results)
    answers = (await _start(client, sv, quiz)).json()["answers"]
    assert set(answers) == {str(q.id) for q in qs} and set(answers.values()) <= {"B", "C"}


async def _start_with_other_tab_in_between(monkeypatch, quiz_id: uuid.UUID, student_id: uuid.UUID):
    """Ép thứ tự xấu một cách tất định: tab B đọc snapshot xong, tab A tạo và commit bài làm, rồi B mới ghi."""
    original = attempts._user_attempts
    fired = False

    async def hooked(db, qid, uid):
        nonlocal fired
        rows = await original(db, qid, uid)
        if not fired:
            fired = True
            async with SessionLocal() as tab_a:
                results.append(
                    await attempts.start_attempt(tab_a, await tab_a.get(User, student_id), quiz_id)
                )
        return rows

    results: list = []
    monkeypatch.setattr(attempts, "_user_attempts", hooked)
    async with SessionLocal() as tab_b:
        user = await tab_b.get(User, student_id)
        results.append(await asyncio.wait_for(attempts.start_attempt(tab_b, user, quiz_id), TIMEOUT))
    return results  # [kết quả tab A, kết quả tab B]


async def _student_id(db) -> uuid.UUID:
    return await db.scalar(select(User.id).where(User.email == "sv@x.com"))


async def test_other_tab_committing_between_read_and_insert_returns_its_attempt(client, db, monkeypatch):
    _, _, _, quiz, _ = await make_published_quiz(client, db, max_attempts=3)
    (a_view, a_created), (b_view, b_created) = await _start_with_other_tab_in_between(
        monkeypatch, uuid.UUID(quiz["id"]), await _student_id(db)
    )
    assert (a_created, b_created) == (True, False) and a_view.id == b_view.id
    rows = (await db.scalars(select(QuizAttempt).where(QuizAttempt.quiz_id == uuid.UUID(quiz["id"])))).all()
    assert [(a.attempt_no, a.status) for a in rows] == [(1, AttemptStatus.in_progress)]


async def test_other_tab_in_between_with_single_attempt_quiz_is_not_a_limit_error(client, db, monkeypatch):
    _, _, _, quiz, _ = await make_published_quiz(client, db, max_attempts=1)
    (a_view, a_created), (b_view, b_created) = await _start_with_other_tab_in_between(
        monkeypatch, uuid.UUID(quiz["id"]), await _student_id(db)
    )
    assert (a_created, b_created) == (True, False) and a_view.id == b_view.id
    assert len((await db.scalars(select(QuizAttempt.id))).all()) == 1
