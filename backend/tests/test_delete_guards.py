"""Xóa khóa/chương/bài bị chặn (409) chỉ khi cascade sẽ xóa dữ liệu của học viên."""

import uuid

from sqlalchemy import select

from app.modules.courses.models import Lesson
from app.modules.enrollment.models import Enrollment, LessonProgress, ProgressStatus
from app.modules.quiz.models import Quiz, QuizAttempt, QuizStatus
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from tests.helpers import (
    API,
    make_admin,
    make_published_course,
    make_published_quiz,
    make_student,
    make_teacher,
)


def _blocked(r, text: str) -> None:
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE" and text in r.json()["error"]["message"]


async def _chat(db, user_id, course_id, lesson_id=None, with_message=True) -> ChatSession:
    s = ChatSession(user_id=uuid.UUID(user_id), course_id=uuid.UUID(course_id), lesson_id=lesson_id)
    db.add(s)
    await db.flush()
    if with_message:
        db.add(ChatMessage(session_id=s.id, role=ChatRole.user, content="Câu hỏi"))
    await db.commit()
    return s


async def test_published_quiz_without_attempts_is_deleted_with_the_lesson(client, db):
    gv, _, _, quiz, _ = await make_published_quiz(client, db)
    quiz_id = uuid.UUID(quiz["id"])
    lesson_id = (await db.get(Quiz, quiz_id)).lesson_id
    section_id = (await db.get(Lesson, lesson_id)).section_id
    assert (await client.delete(f"{API}/lessons/{lesson_id}", headers=gv)).status_code == 204
    assert (await db.scalars(select(Quiz).where(Quiz.id == quiz_id))).first() is None
    assert (await client.delete(f"{API}/sections/{section_id}", headers=gv)).status_code == 204


async def test_quiz_attempt_blocks_lesson_section_and_course_delete(client, db):
    gv, sv, course, quiz, _ = await make_published_quiz(client, db)
    assert (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).status_code == 201
    lesson_id = (await db.get(Quiz, uuid.UUID(quiz["id"]))).lesson_id
    section_id = (await db.get(Lesson, lesson_id)).section_id
    for url in (
        f"{API}/lessons/{lesson_id}",
        f"{API}/sections/{section_id}",
        f"{API}/courses/{course['id']}",
    ):
        _blocked(await client.delete(url, headers=gv), "bài làm quiz")
    assert await db.scalar(select(QuizAttempt.id).where(QuizAttempt.quiz_id == uuid.UUID(quiz["id"])))


async def test_student_chat_blocks_but_owner_and_admin_previews_do_not(client, db):
    gv_id, gv = await make_teacher(client)
    admin_id, _ = await make_admin(client)
    sv_id, _ = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    lesson_id = uuid.UUID(lesson["id"])
    await _chat(db, gv_id, course["id"], lesson_id)  # xem thử của chủ khóa
    await _chat(db, admin_id, course["id"], lesson_id)  # xem thử của admin
    await _chat(db, sv_id, course["id"], lesson_id, with_message=False)  # phiên rỗng: không có lịch sử
    assert (await client.delete(f"{API}/lessons/{lesson['id']}", headers=gv)).status_code == 204

    course2, section2, lesson2 = await make_published_course(client, gv, title="Khóa hai")
    await _chat(db, sv_id, course2["id"], uuid.UUID(lesson2["id"]))
    _blocked(await client.delete(f"{API}/lessons/{lesson2['id']}", headers=gv), "lịch sử hỏi Tutor")
    _blocked(await client.delete(f"{API}/sections/{section2['id']}", headers=gv), "lịch sử hỏi Tutor")

    course3, _, lesson3 = await make_published_course(client, gv, title="Khóa ba")
    await _chat(db, sv_id, course3["id"])  # hỏi cả khóa: chỉ chặn xóa khóa
    assert (await client.delete(f"{API}/lessons/{lesson3['id']}", headers=gv)).status_code == 204
    _blocked(await client.delete(f"{API}/courses/{course3['id']}", headers=gv), "lịch sử hỏi Tutor")
    assert (await client.delete(f"{API}/courses/{course['id']}", headers=gv)).status_code == 204


async def test_enrollment_blocks_course_delete(client, db):
    _, gv = await make_teacher(client)
    sv_id, _ = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    db.add(Enrollment(user_id=uuid.UUID(sv_id), course_id=uuid.UUID(course["id"])))
    await db.commit()
    _blocked(await client.delete(f"{API}/courses/{course['id']}", headers=gv), "đăng ký")


async def test_student_progress_blocks_lesson_and_section_delete(client, db):
    _, gv = await make_teacher(client)
    sv_id, _ = await make_student(client)
    course, section, lesson = await make_published_course(client, gv)
    other_id, _ = await make_student(client, "sv2@x.com")
    db.add(Enrollment(user_id=uuid.UUID(sv_id), course_id=uuid.UUID(course["id"])))
    # tiến độ của người không (còn) đăng ký khóa không chặn
    db.add(
        LessonProgress(
            user_id=uuid.UUID(other_id), lesson_id=uuid.UUID(lesson["id"]), status=ProgressStatus.done
        )
    )
    await db.commit()
    db.add(
        LessonProgress(
            user_id=uuid.UUID(sv_id), lesson_id=uuid.UUID(lesson["id"]), status=ProgressStatus.done
        )
    )
    await db.commit()
    _blocked(await client.delete(f"{API}/lessons/{lesson['id']}", headers=gv), "tiến độ học")
    _blocked(await client.delete(f"{API}/sections/{section['id']}", headers=gv), "tiến độ học")


async def test_unenrolled_progress_alone_does_not_block_lesson_delete(client, db):
    _, gv = await make_teacher(client)
    other_id, _ = await make_student(client)
    _, _, lesson = await make_published_course(client, gv)
    db.add(
        LessonProgress(
            user_id=uuid.UUID(other_id), lesson_id=uuid.UUID(lesson["id"]), status=ProgressStatus.done
        )
    )
    await db.commit()
    assert (await client.delete(f"{API}/lessons/{lesson['id']}", headers=gv)).status_code == 204


async def test_teacher_only_content_is_still_deleted_with_cascade(client, db):
    _, gv = await make_teacher(client)
    course, section, lesson = await make_published_course(client, gv)
    draft = Quiz(lesson_id=uuid.UUID(lesson["id"]), title="Quiz nháp", status=QuizStatus.draft)
    db.add(draft)
    await db.commit()
    assert (await client.delete(f"{API}/sections/{section['id']}", headers=gv)).status_code == 204
    assert (await db.scalars(select(Quiz).where(Quiz.id == draft.id))).first() is None
    assert (await client.delete(f"{API}/courses/{course['id']}", headers=gv)).status_code == 204
