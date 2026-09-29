import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.modules.auth.models import User
from app.modules.courses.models import Course, Lesson, Section
from app.modules.courses.service import ensure_owner, get_owned_lesson
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.queue import JobQueue
from app.modules.jobs.service import create_and_enqueue, create_job
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
from app.modules.materials.schemas import PageOut, SourceOut, SourcePagesPage

INGEST_PDF = "ingest_pdf"  # job.type = tên hàm trong worker; job.ref_id = sources.id


async def get_owned_source(db: AsyncSession, source_id: uuid.UUID, user: User) -> Source:
    row = (
        await db.execute(
            select(Source, Course)
            .join(Lesson, Lesson.id == Source.lesson_id)
            .join(Section, Section.id == Lesson.section_id)
            .join(Course, Course.id == Section.course_id)
            .where(Source.id == source_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Tài liệu")
    ensure_owner(row[1], user)
    return row[0]


async def _counts(db: AsyncSession, source_ids: list[uuid.UUID]) -> tuple[dict, dict]:
    """Đếm trang, trang vision và chunk cho nhiều source bằng các truy vấn GROUP BY (không N+1)."""
    if not source_ids:
        return {}, {}
    page_rows = await db.execute(
        select(
            SourcePage.source_id,
            func.count(),
            func.count().filter(SourcePage.extraction_method == ExtractionMethod.vision),
        )
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
        result.append(
            SourceOut(
                id=s.id,
                lesson_id=s.lesson_id,
                type=s.type,
                status=s.status,
                error_msg=s.error_msg,
                # source ready vẫn có thể mang error_msg (cảnh báo vượt trần vision): tách riêng cho client
                warning=s.error_msg if s.status == SourceStatus.ready else None,
                processed_at=s.processed_at,
                page_count=page_count,
                vision_pages=vision_pages,
                chunk_count=chunks.get(s.id, 0),
            )
        )
    return result


async def to_out(db: AsyncSession, source: Source) -> SourceOut:
    return (await to_out_many(db, [source]))[0]


async def attach_pdf(
    db: AsyncSession, queue: JobQueue, user: User, lesson_id: uuid.UUID, asset_id: uuid.UUID
) -> tuple[Source, Job]:
    lesson, _ = await get_owned_lesson(db, lesson_id, user)
    asset = await require_verified_asset(db, asset_id, user, AssetKind.pdf)
    # ON CONFLICT theo uq_sources_lesson_asset: hai request gắn cùng file đồng thời thì chỉ một cái thành công
    source_id = await db.scalar(
        pg_insert(Source)
        .values(
            id=uuid.uuid4(),
            lesson_id=lesson.id,
            asset_id=asset.id,
            type=SourceType.pdf,
            status=SourceStatus.pending,
        )
        .on_conflict_do_nothing(constraint="uq_sources_lesson_asset")
        .returning(Source.id)
    )
    if source_id is None:
        await db.rollback()
        raise AppError("ALREADY_ATTACHED", "File này đã được gắn vào bài học", 409)
    source = await db.get(Source, source_id)
    # commit source + job cùng lúc
    job = await create_and_enqueue(db, queue, INGEST_PDF, source.id, created_by=user.id)
    return source, job


async def list_lesson_sources(db: AsyncSession, user: User, lesson_id: uuid.UUID) -> list[SourceOut]:
    await get_owned_lesson(db, lesson_id, user)
    sources = (
        await db.scalars(
            select(Source).where(Source.lesson_id == lesson_id).order_by(Source.created_at, Source.id)
        )
    ).all()
    return await to_out_many(db, sources)


async def list_pages(db: AsyncSession, source: Source, params: PageParams) -> SourcePagesPage:
    # (source_id, page_no) là duy nhất nên page_no đủ làm thứ tự ổn định
    stmt = select(SourcePage).where(SourcePage.source_id == source.id).order_by(SourcePage.page_no)
    total, paged = await paginate(db, stmt, params)
    rows = await db.scalars(paged)
    return SourcePagesPage(
        items=[PageOut.model_validate(p) for p in rows], total=total, page=params.page, size=params.size
    )


def _busy(message: str) -> AppError:
    return AppError("INVALID_STATE", message, 409)


async def reprocess(db: AsyncSession, queue: JobQueue, source: Source, user: User) -> Job:
    if source.status == SourceStatus.pending:
        raise _busy("Tài liệu đang chờ xử lý")
    if source.status == SourceStatus.processing:
        raise _busy("Tài liệu đang được xử lý")
    # Tạo job trước: nếu vẫn còn job đang chạy (chưa được worker đánh dấu xong) thì không đụng tới source,
    # tránh để source kẹt 'pending' mà không có job nào mới được enqueue.
    job, created = await create_job(db, INGEST_PDF, source.id, created_by=user.id)
    if not created:
        waiting = job.status == JobStatus.pending  # đọc trước rollback (rollback làm hết hạn các object)
        await db.rollback()
        raise _busy("Tài liệu đang chờ xử lý" if waiting else "Tài liệu đang được xử lý")
    source.status = SourceStatus.pending
    source.error_msg = None
    await db.commit()
    await queue.enqueue(job)  # chỉ enqueue sau khi job đã commit
    return job
