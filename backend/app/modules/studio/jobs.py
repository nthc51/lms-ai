"""Thân các job nền của AI Studio. Worker bọc bằng run_job (đánh dấu processing, ghi done/failed của job);
ở đây ghi kết quả vào bảng của mình, lỗi thì ghi trạng thái failed rồi ném tiếp để job cũng failed."""

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.llm_client import LLMClient
from app.ai.prompts import load_prompt
from app.core.config import Settings
from app.ingestion.pipeline import error_text
from app.modules.courses.models import Lesson, Section
from app.modules.materials.models import Source
from app.modules.studio.generation import (
    fingerprint,
    generate_flashcards,
    generate_report,
    generate_source_guide,
    load_scope_chunks,
    scope_title,
)
from app.modules.studio.models import ArtifactKind, Note, SourceGuide, StudioStatus, StudyArtifact

logger = logging.getLogger(__name__)
_CITE_RE = re.compile(r"\[(\d+)\]")


async def run_source_guide(
    source_id: uuid.UUID, llm: LLMClient, settings: Settings, session_factory: async_sessionmaker
) -> None:
    async with session_factory() as db:
        row = (
            await db.execute(
                select(Source.lesson_id, Section.course_id)
                .join(Lesson, Lesson.id == Source.lesson_id)
                .join(Section, Section.id == Lesson.section_id)
                .where(Source.id == source_id)
            )
        ).one_or_none()
        if row is None:
            return
        chunks = await load_scope_chunks(db, row.course_id, row.lesson_id, source_id)
        await _upsert_guide(db, source_id, status=StudioStatus.generating)
        await db.commit()
    try:
        if not chunks:
            raise ValueError("Tài liệu chưa có nội dung đã xử lý")
        title, summary, topics, questions, version = await generate_source_guide(llm, chunks, settings)
    except Exception as e:
        async with session_factory() as db:
            await _upsert_guide(db, source_id, status=StudioStatus.failed, error_msg=error_text(e))
            await db.commit()
        raise
    async with session_factory() as db:
        await _upsert_guide(
            db,
            source_id,
            status=StudioStatus.ready,
            title=title,
            summary=summary,
            topics=topics,
            questions=questions,
            prompt_version=version,
            error_msg=None,
        )
        await db.commit()


async def _upsert_guide(db, source_id: uuid.UUID, **values) -> None:
    stmt = pg_insert(SourceGuide).values(source_id=source_id, **values)
    await db.execute(stmt.on_conflict_do_update(index_elements=["source_id"], set_=values))


async def run_studio(
    artifact_id: uuid.UUID, llm: LLMClient, settings: Settings, session_factory: async_sessionmaker
) -> None:
    """Sinh nội dung cho một bản đang generating. Dùng tài liệu hiện tại của phạm vi (nếu tài liệu vừa đổi sau lúc
    yêu cầu thì cập nhật luôn fingerprint)."""
    async with session_factory() as db:
        artifact = await db.get(StudyArtifact, artifact_id)
        if artifact is None or artifact.status != StudioStatus.generating:
            return
        chunks = await load_scope_chunks(db, artifact.course_id, artifact.lesson_id)
        title = await scope_title(db, artifact.course_id, artifact.lesson_id)
        kind = artifact.kind
    try:
        if kind == ArtifactKind.flashcards:
            cards = await generate_flashcards(llm, title, chunks, settings)
            values = {
                "cards": cards.cards,
                "citations": cards.citations,
                "prompt_version": cards.prompt_version,
            }
        else:
            report = await generate_report(llm, kind, title, chunks, settings)
            values = {
                "content_md": report.content_md,
                "citations": report.citations,
                "prompt_version": report.prompt_version,
            }
    except Exception as e:
        async with session_factory() as db:
            artifact = await db.get(StudyArtifact, artifact_id)
            artifact.status = StudioStatus.failed
            artifact.error_msg = error_text(e)
            await db.commit()
        raise
    async with session_factory() as db:
        artifact = await db.get(StudyArtifact, artifact_id)
        for k, v in values.items():
            setattr(artifact, k, v)
        artifact.fingerprint = fingerprint(chunks)
        artifact.status = StudioStatus.ready
        artifact.error_msg = None
        await db.commit()


def merge_notes(notes: list[Note]) -> tuple[str, list[dict]]:
    """Ghép ghi chú cho AI, đánh số lại nguồn [n] cho khỏi trùng giữa các ghi chú. Trả (văn bản, nguồn toàn cục)."""
    blocks: list[str] = []
    merged: list[dict] = []
    for note in notes:
        mapping: dict[int, int] = {}
        for c in note.citations:
            merged.append({**c, "n": len(merged) + 1})
            mapping[int(c["n"])] = len(merged)

        def renumber(m: re.Match, mapping=mapping) -> str:
            n = mapping.get(int(m.group(1)))
            return f"[{n}]" if n is not None else ""

        blocks.append(f"### {note.title}\n{_CITE_RE.sub(renumber, note.content_md)}")
    return "\n\n".join(blocks), merged


async def run_notes_synth(
    note_id: uuid.UUID,
    source_ids: list[uuid.UUID],
    llm: LLMClient,
    settings: Settings,
    session_factory: async_sessionmaker,
) -> None:
    async with session_factory() as db:
        target = await db.get(Note, note_id)
        if target is None or target.status != StudioStatus.generating:
            return
        by_id = {
            n.id: n
            for n in (
                await db.scalars(select(Note).where(Note.id.in_(source_ids), Note.user_id == target.user_id))
            ).all()
        }
        notes = [by_id[i] for i in source_ids if i in by_id]
        text, merged = merge_notes(notes)
    try:
        if not notes:
            raise ValueError("Các ghi chú đã chọn không còn nữa")
        result = await llm.generate(load_prompt("notes_synthesize").render(notes=text), op="notes_synthesize")
        content = result.text.strip()
        used = {int(n) for n in _CITE_RE.findall(content)}
    except Exception as e:
        async with session_factory() as db:
            target = await db.get(Note, note_id)
            target.status = StudioStatus.failed
            target.content_md = f"Không tổng hợp được: {error_text(e)}"
            await db.commit()
        raise
    async with session_factory() as db:
        target = await db.get(Note, note_id)
        target.content_md = content
        target.citations = [c for c in merged if c["n"] in used]
        target.status = StudioStatus.ready
        await db.commit()
