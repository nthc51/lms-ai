import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models import Role
from app.modules.courses.models import Course
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from tests.factories import make_lesson, make_user


async def _session(db):
    student = await make_user(db, Role.student)
    teacher = await make_user(db)
    course, lesson = await make_lesson(db, teacher)
    s = ChatSession(user_id=student.id, course_id=course.id, lesson_id=lesson.id)
    db.add(s)
    await db.commit()
    return course, s


async def test_message_defaults(db):
    _, s = await _session(db)
    m = ChatMessage(session_id=s.id, role=ChatRole.user, content="Tìm kiếm nhị phân là gì?")
    db.add(m)
    await db.commit()
    m = await db.get(ChatMessage, m.id, populate_existing=True)
    assert m.citations == [] and m.refused is False and m.truncated is False and m.feedback is None


async def test_feedback_only_accepts_plus_or_minus_one(db):
    _, s = await _session(db)
    db.add(ChatMessage(session_id=s.id, role=ChatRole.assistant, content="x", feedback=2))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_deleting_course_removes_sessions_and_messages(db):
    course, s = await _session(db)
    db.add(ChatMessage(session_id=s.id, role=ChatRole.user, content="x"))
    await db.commit()
    await db.execute(delete(Course).where(Course.id == course.id))
    await db.commit()
    assert (await db.scalars(select(ChatMessage))).all() == []
    assert (await db.scalars(select(ChatSession))).all() == []
