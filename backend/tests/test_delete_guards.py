"""Xóa khóa/chương/bài bị chặn (409) khi cascade sẽ xóa dữ liệu của học viên."""

import uuid

from sqlalchemy import select

from app.modules.courses.models import Lesson
from app.modules.quiz.models import Quiz, QuizAttempt, QuizStatus
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from tests.helpers import API, make_published_course, make_published_quiz, make_student, make_teacher


def _urls(course, section, lesson) -> dict[str, str]:
    return {
        "course": f"{API}/courses/{course['id']}",
        "section": f"{API}/sections/{section['id']}",
        "lesson": f"{API}/lessons/{lesson['id']}",
    }


def _blocked(r, text: str) -> None:
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE" and text in r.json()["error"]["message"]


async def _chat(db, user_id, course_id, lesson_id=None, with_message=True) -> ChatSession:
    s = ChatSession(user_id=uuid.UUID(user_id), course_id=uuid.UUID(course_id), lesson_id=lesson_id)
    db.add(s)
    await db.flush()
    if with_message:
        db.add(ChatMessage(session_id=s.id, role=ChatRole.user, content="Câu hỏi của học viên"))
    await db.commit()
    return s


async def test_published_quiz_blocks_delete_of_lesson_section_and_course(client, db):
    gv, _, course, quiz, _ = await make_published_quiz(client, db)
    lesson_id = (await db.get(Quiz, uuid.UUID(quiz["id"]))).lesson_id
    section_id = (await db.get(Lesson, lesson_id)).section_id
    urls = _urls(course, {"id": str(section_id)}, {"id": str(lesson_id)})
    for url in (urls["lesson"], urls["section"], urls["course"]):
        _blocked(await client.delete(url, headers=gv), "quiz đã xuất bản")
    assert await db.get(Quiz, uuid.UUID(quiz["id"]), populate_existing=True) is not None


async def test_quiz_attempts_block_delete(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    sv_id, _ = await make_student(client)
    quiz = Quiz(lesson_id=uuid.UUID(lesson["id"]), title="Quiz", status=QuizStatus.draft)
    db.add(quiz)
    await db.flush()
    db.add(QuizAttempt(quiz_id=quiz.id, user_id=uuid.UUID(sv_id), attempt_no=1, question_order=[]))
    await db.commit()
    _blocked(await client.delete(f"{API}/lessons/{lesson['id']}", headers=gv), "bài làm quiz")
    _blocked(await client.delete(f"{API}/courses/{course['id']}", headers=gv), "bài làm quiz")


async def test_student_tutor_history_blocks_delete_but_teacher_previews_do_not(client, db):
    gv_id, gv = await make_teacher(client)
    course, section, lesson = await make_published_course(client, gv)
    urls = _urls(course, section, lesson)
    lesson_id = uuid.UUID(lesson["id"])
    sv_id, _ = await make_student(client)

    await _chat(db, gv_id, course["id"], lesson_id)  # phiên thử của chính giảng viên: không chặn
    await _chat(db, sv_id, course["id"], lesson_id, with_message=False)  # phiên rỗng: không có lịch sử
    await _chat(db, sv_id, course["id"])  # hỏi cả khóa: chỉ chặn xóa khóa
    _blocked(await client.delete(urls["course"], headers=gv), "lịch sử hỏi Tutor")
    assert (await client.delete(urls["lesson"], headers=gv)).status_code == 204

    course2, _, lesson2 = await make_published_course(client, gv, title="Khóa hai")
    await _chat(db, sv_id, course2["id"], uuid.UUID(lesson2["id"]))
    _blocked(await client.delete(f"{API}/lessons/{lesson2['id']}", headers=gv), "lịch sử hỏi Tutor")


async def test_teacher_only_content_is_still_deleted_with_cascade(client, db):
    _, gv = await make_teacher(client)
    course, section, lesson = await make_published_course(client, gv)
    draft = Quiz(lesson_id=uuid.UUID(lesson["id"]), title="Quiz nháp", status=QuizStatus.draft)
    db.add(draft)
    await db.commit()
    assert (await client.delete(f"{API}/sections/{section['id']}", headers=gv)).status_code == 204
    assert (await db.scalars(select(Quiz).where(Quiz.id == draft.id))).first() is None
    assert (await client.delete(f"{API}/courses/{course['id']}", headers=gv)).status_code == 204
