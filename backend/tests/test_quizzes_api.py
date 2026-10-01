import uuid

from sqlalchemy import select

from app.modules.quiz.models import Question, ReviewStatus
from tests.factories import make_question
from tests.helpers import API, keys_in, make_published_course, make_published_quiz, make_student, make_teacher


async def _setup(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    lid = uuid.UUID(lesson["id"])
    approved = [await make_question(db, lid, stem=f"Câu hỏi số {i} về tìm kiếm nhị phân?") for i in range(2)]
    pending = await make_question(
        db, lid, stem="Câu hỏi còn chờ duyệt thì sao?", review_status=ReviewStatus.pending
    )
    return gv, course, lesson, approved, pending


async def _create(client, gv, lesson, question_ids=(), title="Quiz 1"):
    body = {"lesson_id": lesson["id"], "title": title, "question_ids": [str(i) for i in question_ids]}
    return await client.post(f"{API}/quizzes", json=body, headers=gv)


async def test_teacher_creates_quiz_only_from_approved_questions_of_the_lesson(client, db):
    gv, _, lesson, approved, pending = await _setup(client, db)
    r = await _create(client, gv, lesson, [q.id for q in approved])
    assert r.status_code == 201
    quiz = r.json()
    assert (quiz["status"], quiz["question_count"], quiz["max_attempts"], quiz["pass_score"]) == (
        "draft",
        2,
        1,
        50,
    )
    assert [q["id"] for q in quiz["questions"]] == [str(q.id) for q in approved]
    bad = await _create(client, gv, lesson, [pending.id])
    assert bad.status_code == 422 and bad.json()["error"]["details"]["invalid_question_ids"] == [
        str(pending.id)
    ]
    assert (await _create(client, gv, lesson, [approved[0].id, approved[0].id])).status_code == 422
    _, _, other_lesson = await make_published_course(client, gv, title="Khóa khác")
    r = await _create(client, gv, other_lesson, [approved[0].id])
    assert r.status_code == 422


async def test_publish_requires_questions_and_locks_the_question_list(client, db):
    gv, _, lesson, approved, _ = await _setup(client, db)
    quiz = (await _create(client, gv, lesson, title="Rỗng")).json()
    r = await client.post(f"{API}/quizzes/{quiz['id']}/publish", headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
    patch = {"question_ids": [str(approved[0].id)], "max_attempts": 2}
    r = await client.patch(f"{API}/quizzes/{quiz['id']}", json=patch, headers=gv)
    assert (r.json()["question_count"], r.json()["max_attempts"]) == (1, 2)
    assert (await client.post(f"{API}/quizzes/{quiz['id']}/publish", headers=gv)).json()[
        "status"
    ] == "published"
    r = await client.patch(f"{API}/quizzes/{quiz['id']}", json={"question_ids": []}, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
    r = await client.patch(f"{API}/quizzes/{quiz['id']}", json={"title": "Đổi tên"}, headers=gv)
    assert r.json()["title"] == "Đổi tên"
    # câu hỏi trong quiz đã xuất bản không sửa/loại được; câu trong quiz nháp phải gỡ ra trước khi loại
    edit = {"action": "edit", "stem": "Sửa câu khi quiz đã xuất bản?"}
    r = await client.patch(f"{API}/questions/{approved[0].id}", json=edit, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
    await _create(client, gv, lesson, [approved[1].id], title="Nháp")
    r = await client.patch(f"{API}/questions/{approved[1].id}", json={"action": "reject"}, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")


async def test_student_sees_published_quizzes_without_answers(client, db):
    gv, course, lesson, approved, _ = await _setup(client, db)
    quiz = (await _create(client, gv, lesson, [approved[0].id])).json()
    draft = (await _create(client, gv, lesson, title="Nháp")).json()
    await client.post(f"{API}/quizzes/{quiz['id']}/publish", headers=gv)
    _, sv = await make_student(client)
    params = {"lesson_id": lesson["id"]}
    r = await client.get(f"{API}/quizzes", params=params, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    items = (await client.get(f"{API}/quizzes", params=params, headers=sv)).json()["items"]
    assert [q["id"] for q in items] == [quiz["id"]] and items[0]["attempts_used"] == 0
    detail = (await client.get(f"{API}/quizzes/{quiz['id']}", headers=sv)).json()
    assert detail["questions"] is None and "correct_option_id" not in keys_in(detail)
    assert (await client.get(f"{API}/quizzes/{draft['id']}", headers=sv)).status_code == 404
    assert len((await client.get(f"{API}/quizzes", params=params, headers=gv)).json()["items"]) == 2


async def test_only_owner_updates_or_deletes(client, db):
    gv, _, lesson, _, _ = await _setup(client, db)
    quiz = (await _create(client, gv, lesson)).json()
    _, gv2 = await make_teacher(client, "gv2@x.com")
    assert (
        await client.patch(f"{API}/quizzes/{quiz['id']}", json={"title": "x"}, headers=gv2)
    ).status_code == 404
    assert (await client.delete(f"{API}/quizzes/{quiz['id']}", headers=gv2)).status_code == 404
    assert (await client.delete(f"{API}/quizzes/{quiz['id']}", headers=gv)).status_code == 204
    assert (await client.get(f"{API}/quizzes/{quiz['id']}", headers=gv)).status_code == 404


async def test_settings_are_validated_at_the_api(client, db):
    gv, _, lesson, _, _ = await _setup(client, db)
    base = {"lesson_id": lesson["id"], "title": "Q"}
    for bad in ({"max_attempts": 0}, {"pass_score": -1}, {"pass_score": 101}, {"title": ""}):
        r = await client.post(f"{API}/quizzes", json={**base, **bad}, headers=gv)
        assert r.status_code == 422, bad
    quiz = (await client.post(f"{API}/quizzes", json=base, headers=gv)).json()
    for bad in ({"max_attempts": 0}, {"pass_score": 100.5}):
        r = await client.patch(f"{API}/quizzes/{quiz['id']}", json=bad, headers=gv)
        assert r.status_code == 422, bad


async def test_published_quiz_is_immutable_and_cannot_be_deleted(client, db):
    gv, _sv, _, quiz, _ = await make_published_quiz(client, db)
    url = f"{API}/quizzes/{quiz['id']}"
    for patch in ({"max_attempts": 5}, {"pass_score": 90}):
        r = await client.patch(url, json=patch, headers=gv)
        assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
    assert (
        await client.patch(url, json={"max_attempts": quiz["max_attempts"]}, headers=gv)
    ).status_code == 200
    r = await client.delete(url, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
    r = await client.post(f"{url}/publish", headers=gv)
    assert r.status_code == 409


async def test_student_view_never_leaks_answers(client, db):
    gv, sv, _, quiz, _ = await make_published_quiz(client, db)
    detail = (await client.get(f"{API}/quizzes/{quiz['id']}", headers=sv)).json()
    listing = (await client.get(f"{API}/quizzes", params={"lesson_id": quiz["lesson_id"]}, headers=sv)).json()
    for body in (detail, listing):
        assert not keys_in(body) & {"correct_option_id", "explanation", "ai_original", "options", "stem"}
    assert detail["question_count"] == 3
    owner = (await client.get(f"{API}/quizzes/{quiz['id']}", headers=gv)).json()
    assert "correct_option_id" in keys_in(owner)
    _, other = await make_student(client, "sv2@x.com")
    r = await client.get(f"{API}/quizzes/{quiz['id']}", headers=other)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")


async def test_publish_rechecks_questions_still_usable(client, db):
    gv, _, lesson, approved, _ = await _setup(client, db)
    quiz = (await _create(client, gv, lesson, [q.id for q in approved])).json()
    victim = await db.get(Question, approved[0].id)
    victim.review_status = ReviewStatus.rejected
    await db.commit()
    r = await client.post(f"{API}/quizzes/{quiz['id']}/publish", headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
    assert (await db.scalar(select(Question.review_status).where(Question.id == approved[1].id))) is not None


async def test_quiz_list_is_paginated_with_stable_order(client, db):
    gv, _, lesson, _, _ = await _setup(client, db)
    ids = [(await _create(client, gv, lesson, title=f"Q{i}")).json()["id"] for i in range(3)]
    params = {"lesson_id": lesson["id"], "size": 2}
    p1 = (await client.get(f"{API}/quizzes", params=params, headers=gv)).json()
    p2 = (await client.get(f"{API}/quizzes", params={**params, "page": 2}, headers=gv)).json()
    assert (p1["total"], len(p1["items"]), len(p2["items"])) == (3, 2, 1)
    assert [q["id"] for q in p1["items"] + p2["items"]] == ids
