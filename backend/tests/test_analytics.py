import uuid

from tests.factories import BINARY_SEARCH, seed_chunks
from tests.helpers import (
    API,
    make_admin,
    make_published_course,
    make_published_quiz,
    make_student,
    make_teacher,
    parse_sse,
)


async def test_course_analytics_basic_numbers(client, db):
    gv, sv, course, quiz, qs = await make_published_quiz(client, db, max_attempts=2)
    _, sv2 = await make_student(client, "sv2@x.com")
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv2)
    lesson_id = quiz["lesson_id"]
    progress = {"status": "done", "video_position_sec": 0}
    await client.put(f"{API}/lessons/{lesson_id}/progress", json=progress, headers=sv)
    # sv đúng 3/3, sv2 bỏ trống cả bài (0 điểm); một bài làm dở không được tính
    a1 = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    answers = [{"question_id": str(q.id), "selected_option_id": "A"} for q in qs]
    await client.post(f"{API}/attempts/{a1['id']}/submit", json={"final_answers": answers}, headers=sv)
    a2 = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv2)).json()
    await client.post(f"{API}/attempts/{a2['id']}/submit", headers=sv2)
    await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)
    # Tutor: một câu được trả lời, một câu bị từ chối
    await seed_chunks(db, uuid.UUID(lesson_id), [BINARY_SEARCH])
    body = {"course_id": course["id"], "lesson_id": lesson_id}
    session = (await client.post(f"{API}/tutor/sessions", json=body, headers=sv)).json()
    url = f"{API}/tutor/sessions/{session['id']}/messages"
    await client.post(url, json={"content": "Tìm kiếm nhị phân là gì?"}, headers=sv)
    refused = parse_sse(
        (await client.post(url, json={"content": "Thời tiết Hà Nội hôm nay"}, headers=sv)).text
    )
    assert refused[-1][1]["refused"] is True

    data = (await client.get(f"{API}/courses/{course['id']}/analytics", headers=gv)).json()
    assert (data["enrollments"], data["completed_enrollments"]) == (2, 1)
    [lesson] = data["lessons"]
    assert (lesson["lesson_id"], lesson["done_count"], lesson["completion_rate"]) == (lesson_id, 1, 0.5)
    [q] = data["quizzes"]
    assert (q["attempts"], q["students"], q["avg_score"], q["pass_rate"]) == (2, 2, 50.0, 0.5)
    assert data["tutor"] == {"sessions": 1, "questions": 2, "refused_answers": 1}


async def test_analytics_is_for_owner_or_admin_only(client, db):
    _, gv = await make_teacher(client)
    course, _, _ = await make_published_course(client, gv)
    url = f"{API}/courses/{course['id']}/analytics"
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, sv = await make_student(client)
    _, admin = await make_admin(client)
    assert (await client.get(url, headers=gv2)).status_code == 404
    r = await client.get(url, headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
    empty = (await client.get(url, headers=admin)).json()
    assert (
        empty["enrollments"] == 0 and empty["quizzes"] == [] and empty["lessons"][0]["completion_rate"] == 0.0
    )
    assert empty["tutor"] == {"sessions": 0, "questions": 0, "refused_answers": 0}


async def test_analytics_multi_student_partial_progress_and_attempts(client, db):
    gv, sv, course, quiz, qs = await make_published_quiz(client, db, max_attempts=3)
    lesson_id = quiz["lesson_id"]
    students = [sv]
    for i in range(2, 5):
        _, h = await make_student(client, f"sv{i}@x.com")
        await client.post(f"{API}/courses/{course['id']}/enroll", headers=h)
        students.append(h)
    # 3 trong 4 học viên xong bài; sv4 chỉ đang học (không tính)
    done = {"status": "done", "video_position_sec": 0}
    for h in students[:3]:
        await client.put(f"{API}/lessons/{lesson_id}/progress", json=done, headers=h)
    await client.put(
        f"{API}/lessons/{lesson_id}/progress",
        json={"status": "in_progress", "video_position_sec": 5},
        headers=students[3],
    )

    async def attempt(h, n_correct):
        a = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=h)).json()
        answers = [
            {"question_id": str(q.id), "selected_option_id": "A" if i < n_correct else "B"}
            for i, q in enumerate(qs)
        ]
        r = await client.post(f"{API}/attempts/{a['id']}/submit", json={"final_answers": answers}, headers=h)
        assert r.status_code == 200, r.text

    # sv: 3/3 rồi 1/3; sv2: 2/3; sv3: 3/3; sv4: chưa làm. Điểm: 100, 33.33, 66.67, 100
    await attempt(students[0], 3)
    await attempt(students[0], 1)
    await attempt(students[1], 2)
    await attempt(students[2], 3)

    data = (await client.get(f"{API}/courses/{course['id']}/analytics", headers=gv)).json()
    assert data["enrollments"] == 4
    [lesson] = data["lessons"]
    assert (lesson["done_count"], lesson["completion_rate"]) == (3, 0.75)
    [q] = data["quizzes"]
    # pass_score mặc định 50: 100 và 66.67 và 100 đạt, 33.33 trượt → 3/4
    assert (q["attempts"], q["students"], q["avg_score"], q["pass_rate"]) == (4, 3, 75.0, 0.75)
