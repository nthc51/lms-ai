"""Sổ ghi chú của học viên (S4): mỗi người chỉ thấy ghi chú của mình."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.modules.auth.models import User
from app.modules.jobs.queue import JobQueue
from app.modules.jobs.service import create_and_enqueue
from app.modules.studio.models import Note, StudioStatus
from app.modules.studio.schemas import (
    NoteFromMessageIn,
    NoteIn,
    NoteOut,
    NotePage,
    NotesSynthesizeIn,
    NoteSynthOut,
    NoteUpdate,
)
from app.modules.studio.service import ensure_scope
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession

NOTES_JOB = "notes_synth"
TITLE_FROM_QUESTION = 80


def note_out(n: Note) -> NoteOut:
    return NoteOut.model_validate(n, from_attributes=True)


async def list_notes(
    db: AsyncSession, user: User, course_id: uuid.UUID | None, lesson_id: uuid.UUID | None, params: PageParams
) -> NotePage:
    stmt = select(Note).where(Note.user_id == user.id)
    if course_id is not None:
        stmt = stmt.where(Note.course_id == course_id)
    if lesson_id is not None:
        stmt = stmt.where(Note.lesson_id == lesson_id)
    total, paged = await paginate(db, stmt.order_by(Note.updated_at.desc(), Note.id), params)
    rows = (await db.scalars(paged)).all()
    return NotePage(items=[note_out(n) for n in rows], total=total, page=params.page, size=params.size)


async def _own(db: AsyncSession, user: User, note_id: uuid.UUID) -> Note:
    note = await db.get(Note, note_id)
    if note is None or note.user_id != user.id:
        raise not_found("Ghi chú")  # ghi chú của người khác cũng là 404
    return note


async def create_note(db: AsyncSession, user: User, data: NoteIn) -> NoteOut:
    await ensure_scope(db, user, data.course_id, data.lesson_id)
    note = Note(
        user_id=user.id,
        course_id=data.course_id,
        lesson_id=data.lesson_id,
        title=data.title,
        content_md=data.content_md,
        citations=data.citations,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note_out(note)


async def note_from_message(db: AsyncSession, user: User, data: NoteFromMessageIn) -> NoteOut:
    """Lưu một câu trả lời AI Tutor của chính mình thành ghi chú, giữ nguyên trích nguồn; tiêu đề là câu hỏi."""
    row = (
        await db.execute(
            select(ChatMessage, ChatSession)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                ChatMessage.id == data.message_id,
                ChatSession.user_id == user.id,
                ChatMessage.role == ChatRole.assistant,
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("Tin nhắn")
    message, session = row
    if message.refused or not message.content.strip():
        raise AppError("NOTHING_TO_SAVE", "Câu trả lời này không có nội dung để lưu", 409)
    question = await db.scalar(
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == session.id,
            ChatMessage.role == ChatRole.user,
            ChatMessage.created_at <= message.created_at,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )
    title = " ".join((question or "Câu trả lời của AI Tutor").split())
    if len(title) > TITLE_FROM_QUESTION:
        title = title[: TITLE_FROM_QUESTION - 1].rstrip() + "…"
    note = Note(
        user_id=user.id,
        course_id=session.course_id,
        lesson_id=session.lesson_id,
        title=title,
        content_md=message.content,
        citations=message.citations,
        from_message_id=message.id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note_out(note)


_CITE_RE = re.compile(r"\[(\d+)\]")


async def update_note(db: AsyncSession, user: User, note_id: uuid.UUID, data: NoteUpdate) -> NoteOut:
    note = await _own(db, user, note_id)
    if note.status == StudioStatus.generating:
        raise AppError("NOTE_GENERATING", "Ghi chú đang được AI tổng hợp, chờ xong rồi sửa", 409)
    if data.title is not None:
        note.title = data.title
    if data.content_md is not None:
        note.content_md = data.content_md
        used = {int(n) for n in _CITE_RE.findall(data.content_md)}
        note.citations = [c for c in note.citations if c["n"] in used]
    await db.commit()
    await db.refresh(note)
    return note_out(note)


async def delete_note(db: AsyncSession, user: User, note_id: uuid.UUID) -> None:
    note = await _own(db, user, note_id)
    await db.delete(note)
    await db.commit()


async def synthesize(db: AsyncSession, queue: JobQueue, user: User, data: NotesSynthesizeIn) -> NoteSynthOut:
    """Tạo ghi chú mới (đang tổng hợp) từ các ghi chú đã chọn — cùng một khóa — rồi giao job nền."""
    notes = (await db.scalars(select(Note).where(Note.id.in_(data.note_ids), Note.user_id == user.id))).all()
    if len(notes) != len(set(data.note_ids)):
        raise not_found("Ghi chú")
    courses = {n.course_id for n in notes}
    if len(courses) != 1:
        raise AppError("MIXED_COURSES", "Chỉ tổng hợp được các ghi chú của cùng một khóa học", 422)
    course_id = courses.pop()
    await ensure_scope(db, user, course_id, None)
    lessons = {n.lesson_id for n in notes}
    note = Note(
        user_id=user.id,
        course_id=course_id,
        lesson_id=lessons.pop() if len(lessons) == 1 else None,
        title=data.title.strip()
        if data.title and data.title.strip()
        else f"Đề cương từ {len(notes)} ghi chú",
        status=StudioStatus.generating,
    )
    db.add(note)
    await db.flush()
    job = await create_and_enqueue(
        db,
        queue,
        NOTES_JOB,
        note.id,
        created_by=user.id,
        payload={"note_ids": [str(i) for i in data.note_ids]},
    )
    await db.refresh(note)
    return NoteSynthOut(note=note_out(note), job_id=job.id)
