import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.vision import VisionExtractor
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.storage import Storage
from app.core.time import utcnow
from app.ingestion.chunker import PageText, chunk_pages
from app.ingestion.extract import extract_pages
from app.modules.courses.models import Lesson, Section
from app.modules.jobs.models import JobStatus
from app.modules.jobs.service import finish_job
from app.modules.materials.models import Asset, Chunk, ExtractionMethod, Source, SourcePage, SourceStatus

logger = logging.getLogger(__name__)


def vision_cap_warning(pages: list[PageText], cap: int) -> str | None:
    """Cảnh báo ghi vào sources.error_msg (source vẫn ready) khi có trang cần vision nhưng phải dùng text:
    vượt trần VISION_MAX_PAGES_PER_DOC, hoặc gọi vision lỗi tạm thời (hết quota, quá tải)."""
    skipped = sum(1 for p in pages if p.vision_skipped)
    failed = sum(1 for p in pages if p.vision_failed)
    parts = []
    if skipped:
        parts.append(
            f"vượt giới hạn {cap} trang vision (VISION_MAX_PAGES_PER_DOC); "
            f"{skipped} trang cần vision đã dùng text thường"
        )
    if failed:
        parts.append(
            f"{failed} trang gọi vision bị lỗi tạm thời (hết quota hoặc dịch vụ AI quá tải) nên đã dùng "
            "text thường; bấm Xử lý lại khi dịch vụ ổn định để đọc lại các trang này"
        )
    return f"Cảnh báo: {'; '.join(parts)}." if parts else None


def error_text(error: BaseException) -> str:
    return (str(error) or type(error).__name__)[:500]


async def _mark_failed(
    session_factory: async_sessionmaker,
    source_id: uuid.UUID,
    error: Exception,
    job_id: uuid.UUID | None = None,
) -> None:
    """Đánh dấu source failed; có job_id thì ghi job failed trong cùng transaction.
    Job không còn processing (đã bị sweeper xử lý) thì không đụng tới source."""
    msg = error_text(error)
    async with session_factory() as db:
        if job_id is not None and not await finish_job(db, job_id, JobStatus.failed, msg):
            logger.warning("Job %s không còn processing, bỏ qua kết quả lỗi của source %s", job_id, source_id)
            return
        source = await db.get(Source, source_id)
        if source is not None:
            source.status = SourceStatus.failed
            source.error_msg = msg
        await db.commit()


async def ingest_pdf_source(
    source_id: uuid.UUID,
    *,
    storage: Storage,
    embedder: Embedder,
    vision: VisionExtractor,
    max_vision_pages: int | None = None,
    session_factory: async_sessionmaker = SessionLocal,
    job_id: uuid.UUID | None = None,
) -> int:
    """Xử lý một source PDF. Trả về số chunk đã ghi.

    job_id (worker truyền vào): job đang processing; trạng thái cuối của job (done/failed) được ghi trong
    cùng transaction với trạng thái cuối của source (ready/failed). Nếu lúc ghi kết quả job đã không còn
    processing (sweeper đã đánh dấu failed) thì bỏ kết quả, trả về 0.

    Dùng các DB session ngắn: không giữ connection trong lúc tải file, gọi vision và embedding (có thể mất vài phút).
    max_vision_pages mặc định lấy từ VISION_MAX_PAGES_PER_DOC.
    """
    if max_vision_pages is None:
        max_vision_pages = get_settings().vision_max_pages_per_doc

    async with session_factory() as db:
        row = (
            await db.execute(
                select(Source, Asset.storage_key, Lesson.id, Section.course_id)
                .join(Asset, Asset.id == Source.asset_id)
                .join(Lesson, Lesson.id == Source.lesson_id)
                .join(Section, Section.id == Lesson.section_id)
                .where(Source.id == source_id)
            )
        ).one_or_none()
        if row is None:
            raise ValueError(f"Source {source_id} không tồn tại")
        source, storage_key, lesson_id, course_id = row
        source.status = SourceStatus.processing
        source.error_msg = None
        await db.commit()

    try:
        pdf_bytes = await storage.read_all(storage_key)
        pages = await extract_pages(pdf_bytes, vision, max_vision_pages=max_vision_pages)
        drafts = chunk_pages(pages)
        if not drafts:
            raise ValueError("Tài liệu không có nội dung đọc được")
        vectors = await embedder.embed_documents([d.content for d in drafts])
    except Exception as e:
        await _mark_failed(session_factory, source_id, e, job_id)
        raise

    try:
        async with session_factory() as db:
            if job_id is not None and not await finish_job(db, job_id, JobStatus.done):
                logger.warning("Job %s không còn processing, bỏ kết quả của source %s", job_id, source_id)
                return 0
            await db.execute(delete(Chunk).where(Chunk.source_id == source_id))
            await db.execute(delete(SourcePage).where(SourcePage.source_id == source_id))
            db.add_all(
                [
                    SourcePage(
                        source_id=source_id,
                        page_no=p.page_no,
                        extraction_method=ExtractionMethod(p.method),
                        markdown=p.markdown,
                    )
                    for p in pages
                ]
            )
            db.add_all(
                [
                    Chunk(
                        source_id=source_id,
                        course_id=course_id,
                        lesson_id=lesson_id,
                        content=d.content,
                        heading_path=d.heading_path[:500],
                        page_no=d.page_no,
                        token_count=d.token_count,
                        embedding_model=embedder.model,
                        embedding=v,
                    )
                    for d, v in zip(drafts, vectors, strict=True)
                ]
            )
            source = await db.get(Source, source_id)
            source.status = SourceStatus.ready
            source.error_msg = vision_cap_warning(pages, max_vision_pages)
            source.processed_at = utcnow()
            await db.commit()
    except Exception as e:  # lỗi khi ghi DB: không để source kẹt ở trạng thái processing
        await _mark_failed(session_factory, source_id, e, job_id)
        raise
    return len(drafts)
