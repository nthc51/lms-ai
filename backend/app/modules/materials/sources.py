import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.modules.auth.models import User
from app.modules.courses.models import Course, Lesson, Section
from app.modules.courses.service import ensure_owner, get_owned_lesson
from app.modules.jobs.models import Job
from app.modules.jobs.queue import JobQueue
from app.modules.jobs.service import create_and_enqueue
from app.modules.materials.assets import require_verified_asset
from app.modules.materials.models import (
    AssetKind,
    Chunk,
    ExtractionMethod,
    Source,
    SourcePage,
    SourceStatus,
    SourceType,
)
from app.modules.materials.schemas import SourceOut

INGEST_PDF = "ingest_pdf"  # job.type = tên hàm trong worker; job.ref_id = sources.id


async def get_owned_source(db: AsyncSession, source_id: uuid.UUID, user: User) -> Source:
    row = (await db.execute(
        select(Source, Course)
        .join(Lesson, Lesson.id == Source.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Source.id == source_id)
    )).one_or_none()
    if row is None:
        raise not_found("Tài liệu")
    ensure_owner(row[1], user)
    return row[0]


async def _counts(db: AsyncSession, source_ids: list[uuid.UUID]) -> tuple[dict, dict]:
    """Đếm trang, trang vision và chunk cho nhiều source bằng các truy vấn GROUP BY (không N+1)."""
    if not source_ids:
        return {}, {}
    page_rows = await db.execute(
        select(SourcePage.source_id, func.count(),
               func.count().filter(SourcePage.extraction_method == ExtractionMethod.vision))
        .where(SourcePage.source_id.in_(source_ids))
        .group_by(SourcePage.source_id)
    )
    chunk_rows = await db.execute(
        select(Chunk.source_id, func.count(Chunk.id))
        .where(Chunk.source_id.in_(source_ids))
        .group_by(Chunk.source_id)
    )
    pages = {sid: (total, vision) for sid, total, vision in page_rows}
    chunks = {sid: n for sid, n in chunk_rows}
    return pages, chunks


async def to_out_many(db: AsyncSession, sources: Sequence[Source]) -> list[SourceOut]:
    pages, chunks = await _counts(db, [s.id for s in sources])
    result = []
    for s in sources:
        page_count, vision_pages = pages.get(s.id, (0, 0))
        result.append(SourceOut(
            id=s.id, lesson_id=s.lesson_id, type=s.type, status=s.status, error_msg=s.error_msg,
            # source ready vẫn có thể mang error_msg (cảnh báo vượt trần vision): tách riêng cho client
            warning=s.error_msg if s.status == SourceStatus.ready else None,
            processed_at=s.processed_at, page_count=page_count, vision_pages=vision_pages,
            chunk_count=chunks.get(s.id, 0)))
    return result


async def to_out(db: AsyncSession, source: Source) -> SourceOut:
    return (await to_out_many(db, [source]))[0]


async def attach_pdf(db: AsyncSession, queue: JobQueue, user: User, lesson_id: uuid.UUID,
                     asset_id: uuid.UUID) -> tuple[Source, Job]:
    lesson, _ = await get_owned_lesson(db, lesson_id, user)
    asset = await require_verified_asset(db, asset_id, user, AssetKind.pdf)
    source = Source(lesson_id=lesson.id, asset_id=asset.id, type=SourceType.pdf, status=SourceStatus.pending)
    db.add(source)
    await db.flush()
    job = await create_and_enqueue(db, queue, INGEST_PDF, source.id)  # commit source + job cùng lúc
    return source, job


async def list_lesson_sources(db: AsyncSession, user: User, lesson_id: uuid.UUID) -> list[SourceOut]:
    await get_owned_lesson(db, lesson_id, user)
    sources = (await db.scalars(select(Source).where(Source.lesson_id == lesson_id)
                                .order_by(Source.created_at, Source.id))).all()
    return await to_out_many(db, sources)


async def list_pages(db: AsyncSession, source: Source) -> list[SourcePage]:
    rows = await db.scalars(select(SourcePage).where(SourcePage.source_id == source.id)
                            .order_by(SourcePage.page_no))
    return list(rows)


async def reprocess(db: AsyncSession, queue: JobQueue, source: Source) -> Job:
    if source.status not in (SourceStatus.ready, SourceStatus.failed):
        raise AppError("INVALID_STATE", "Tài liệu đang được xử lý", 409)
    source.status = SourceStatus.pending
    source.error_msg = None
    return await create_and_enqueue(db, queue, INGEST_PDF, source.id)
