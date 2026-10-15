"""Trang chủ học viên: quiz chưa làm trong các khóa đã đăng ký (GET /me/pending-quizzes)."""

from tests.helpers import API, make_admin, make_published_quiz, make_student


async def _pending(client, headers):
    r = await client.get(f"{API}/me/pending-quizzes", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_pending_quiz_listed_until_submitted(client, db):
    _, sv, course, quiz, _ = await make_published_quiz(client, db, n_questions=2, time_limit_sec=600)

    (item,) = await _pending(client, sv)
    assert item["quiz_id"] == quiz["id"]
    assert item["title"] == "Quiz tìm kiếm nhị phân"
    assert item["course_title"] == course["title"] and item["course_slug"] == course["slug"]
    assert item["lesson_title"] == "Bài 1" and item["lesson_id"] == quiz["lesson_id"]
    assert item["question_count"] == 2 and item["time_limit_sec"] == 600
    assert item["in_progress"] is False

    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    (item,) = await _pending(client, sv)
    assert item["in_progress"] is True  # đang làm dở vẫn là việc cần làm

    r = await client.post(f"{API}/attempts/{attempt['id']}/submit", json={}, headers=sv)
    assert r.status_code == 200, r.text
    assert await _pending(client, sv) == []


async def test_not_enrolled_not_listed(client, db):
    gv, _, _, _, _ = await make_published_quiz(client, db)
    _, other = await make_student(client, "khac@x.com")  # chưa đăng ký khóa
    assert await _pending(client, other) == []
    assert await _pending(client, gv) == []  # giảng viên không đăng ký khóa của mình


async def test_hidden_course_hides_its_quizzes(client, db):
    _, sv, course, _, _ = await make_published_quiz(client, db)
    _, admin = await make_admin(client)
    r = await client.post(
        f"{API}/admin/courses/{course['id']}/hide", json={"reason": "Nội dung chưa phù hợp"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert await _pending(client, sv) == []


async def test_pending_quizzes_need_login(client):
    assert (await client.get(f"{API}/me/pending-quizzes")).status_code == 401
