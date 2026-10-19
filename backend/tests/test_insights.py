"""B7: phân tích lớp học (câu hay sai, bài yếu, học viên cần để ý)."""

import uuid
from datetime import timedelta

from sqlalchemy import update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.enrollment.models import Enrollment
from tests.helpers import API, make_published_quiz, make_student


async def test_insights_rank_hard_questions_weak_lessons_and_students(client, db):
    gv, sv1, course, quiz, qs = await make_published_quiz(client, db, n_questions=2)
    students = [sv1]
    for i in range(2):
        _, sv = await make_student(client, f"sv{i}@x.com")
        await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
        students.append(sv)
    # câu 1 (theo thứ tự tạo) cả 3 người sai, 2 người chọn C; câu 0 chỉ 1 người sai
    order = {q.id: i for i, q in enumerate(qs)}
    for sv, (p0, p1) in zip(students, [("A", "C"), ("A", "C"), ("B", "D")], strict=True):
        attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
        by_index = {order[uuid.UUID(q["id"])]: q["id"] for q in attempt["questions"]}
        final = [
            {"question_id": by_index[0], "selected_option_id": p0},
            {"question_id": by_index[1], "selected_option_id": p1},
        ]
        r = await client.post(
            f"{API}/attempts/{attempt['id']}/submit", json={"final_answers": final}, headers=sv
        )
        assert r.status_code == 200, r.text

    r = await client.get(f"{API}/courses/{course['id']}/insights", headers=gv)
    assert r.status_code == 200, r.text
    data = r.json()
    hard = data["hard_questions"]
    assert [h["question_id"] for h in hard] == [str(qs[1].id), str(qs[0].id)]
    assert hard[0]["wrong"] == 3 and hard[0]["answers"] == 3 and hard[0]["wrong_rate"] == 1.0
    assert hard[0]["top_wrong"] == {"id": "C", "text": "Danh sách liên kết", "count": 2}
    assert hard[0]["correct_option"] == "A" and hard[0]["lesson_title"] == "Bài 1"

    (weak,) = data["weak_lessons"]
    assert weak["attempts"] == 3 and weak["avg_score"] == round((50 + 50 + 0) / 3, 2)

    # điểm trung bình 0% → cần để ý; hai người 50% thì không (ngưỡng < 50)
    (risk,) = data["students_at_risk"]
    assert risk["avg_score"] == 0 and risk["reasons"] == ["Điểm quiz trung bình 0%"]


async def test_inactive_student_listed_and_access(client, db):
    gv, sv, course, _, _ = await make_published_quiz(client, db)
    async with SessionLocal() as s:
        await s.execute(
            update(Enrollment)
            .where(Enrollment.course_id == course["id"])
            .values(enrolled_at=utcnow() - timedelta(days=10))
        )
        await s.commit()
    data = (await client.get(f"{API}/courses/{course['id']}/insights", headers=gv)).json()
    (risk,) = data["students_at_risk"]
    assert risk["reasons"] == ["Không học 10 ngày"] and risk["progress_pct"] == 0
    assert data["hard_questions"] == []  # chưa có ai nộp bài

    # học viên và giảng viên khác không xem được
    assert (await client.get(f"{API}/courses/{course['id']}/insights", headers=sv)).status_code == 403
