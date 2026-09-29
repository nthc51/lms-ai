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
from app.modules.materials.models import Asset, Chunk, ExtractionMethod, Source, SourcePage, SourceStatus


def vision_cap_warning(pages: list[PageText], cap: int) -> str | None:
    """Cảnh báo ghi vào sources.error_msg khi có trang cần vision nhưng đã vượt trần (source vẫn ready)."""
    skipped = sum(1 for p in pages if p.vision_skipped)
    if not skipped:
        return None
    return (f"Cảnh báo: vượt giới hạn {cap} trang vision (VISION_MAX_PAGES_PER_DOC); "
            f"{skipped} trang cần vision đã dùng text thường.")


async def _mark_failed(session_factory: async_sessionmaker, source_id: uuid.UUID, error: Exception) -> None:
    async with session_factory() as db:
        source = await db.get(Source, source_id)
        if source is not None:
            source.status = SourceStatus.failed
            source.error_msg = (str(error) or type(error).__name__)[:500]
            await db.commit()


async def ingest_pdf_source(source_id: uuid.UUID, *, storage: Storage, embedder: Embedder,
                            vision: VisionExtractor, max_vision_pages: int | None = None,
                            session_factory: async_sessionmaker = SessionLocal) -> int:
    """Xử lý một source PDF. Trả về số chunk đã ghi.

    Dùng các DB session ngắn: không giữ connection trong lúc tải file, gọi vision và embedding (có thể mất vài phút).
    max_vision_pages mặc định lấy từ VISION_MAX_PAGES_PER_DOC.
    """
    if max_vision_pages is None:
        max_vision_pages = get_settings().vision_max_pages_per_doc

    async with session_factory() as db:
        row = (await db.execute(
            select(Source, Asset.storage_key, Lesson.id, Section.course_id)
            .join(Asset, Asset.id == Source.asset_id)
            .join(Lesson, Lesson.id == Source.lesson_id)
            .join(Section, Section.id == Lesson.section_id)
            .where(Source.id == source_id)
        )).one_or_none()
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
        await _mark_failed(session_factory, source_id, e)
        raise

    try:
        async with session_factory() as db:
            await db.execute(delete(Chunk).where(Chunk.source_id == source_id))
            await db.execute(delete(SourcePage).where(SourcePage.source_id == source_id))
            db.add_all([SourcePage(source_id=source_id, page_no=p.page_no,
                                   extraction_method=ExtractionMethod(p.method), markdown=p.markdown)
                        for p in pages])
            db.add_all([Chunk(source_id=source_id, course_id=course_id, lesson_id=lesson_id, content=d.content,
                              heading_path=d.heading_path[:500], page_no=d.page_no, token_count=d.token_count,
                              embedding_model=embedder.model, embedding=v)
                        for d, v in zip(drafts, vectors, strict=True)])
            source = await db.get(Source, source_id)
            source.status = SourceStatus.ready
            source.error_msg = vision_cap_warning(pages, max_vision_pages)
            source.processed_at = utcnow()
            await db.commit()
    except Exception as e:  # lỗi khi ghi DB: không để source kẹt ở trạng thái processing
        await _mark_failed(session_factory, source_id, e)
        raise
    return len(drafts)
