import pytest
from sqlalchemy import func, select

from app.ai.embedder import FakeEmbedder
from app.ai.vision import FakeVision
from app.ingestion.pipeline import ingest_pdf_source
from app.modules.materials.models import Chunk, Source, SourcePage, SourceStatus
from tests.factories import make_lesson, make_pdf_source, make_user
from tests.fakes import InMemoryStorage
from tests.pdfs import LONG_TEXT, make_pdf


async def _source(db, storage, pdf: bytes):
    teacher = await make_user(db)
    course, lesson = await make_lesson(db, teacher)
    source = await make_pdf_source(db, storage, teacher, lesson, pdf)
    return course, lesson, source


async def test_ingest_success_writes_pages_and_chunks(db):
    storage = InMemoryStorage()
    course, lesson, source = await _source(db, storage, make_pdf([LONG_TEXT, ""]))
    n = await ingest_pdf_source(source.id, storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())
    assert n >= 1

    await db.refresh(source)
    assert source.status == SourceStatus.ready and source.processed_at is not None
    assert source.error_msg is None
    methods = (
        await db.scalars(
            select(SourcePage.extraction_method)
            .where(SourcePage.source_id == source.id)
            .order_by(SourcePage.page_no)
        )
    ).all()
    assert [m.value for m in methods] == ["text", "vision"]
    chunk = await db.scalar(select(Chunk).where(Chunk.source_id == source.id).limit(1))
    assert (chunk.course_id, chunk.lesson_id) == (course.id, lesson.id)
    assert chunk.embedding_model == "fake-768" and len(chunk.embedding) == 768


async def test_reingest_replaces_instead_of_duplicating(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, make_pdf([LONG_TEXT]))
    kw = {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision()}
    first = await ingest_pdf_source(source.id, **kw)
    second = await ingest_pdf_source(source.id, **kw)
    total = await db.scalar(select(func.count(Chunk.id)).where(Chunk.source_id == source.id))
    assert first == second == total


async def test_corrupt_pdf_marks_source_failed(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, b"not a pdf")
    with pytest.raises(RuntimeError):  # pymupdf.FileDataError
        await ingest_pdf_source(source.id, storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())
    fresh = await db.get(Source, source.id, populate_existing=True)
    assert fresh.status == SourceStatus.failed and fresh.error_msg


async def test_document_without_any_text_fails(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, make_pdf([""]))
    with pytest.raises(ValueError):
        await ingest_pdf_source(
            source.id, storage=storage, embedder=FakeEmbedder(768), vision=FakeVision(text="")
        )
    fresh = await db.get(Source, source.id, populate_existing=True)
    assert fresh.status == SourceStatus.failed


async def test_vision_cap_reached_still_ready_with_warning(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, make_pdf([LONG_TEXT, "", "", ""]))
    vision = FakeVision()
    await ingest_pdf_source(
        source.id, storage=storage, embedder=FakeEmbedder(768), vision=vision, max_vision_pages=1
    )
    assert vision.calls == 1
    fresh = await db.get(Source, source.id, populate_existing=True)
    assert fresh.status == SourceStatus.ready and fresh.processed_at is not None
    assert fresh.error_msg == (
        "Cảnh báo: vượt giới hạn 1 trang vision (VISION_MAX_PAGES_PER_DOC); "
        "2 trang cần vision đã dùng text thường."
    )


async def test_reingest_after_failure_clears_old_error(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, make_pdf([LONG_TEXT]))
    source.status = SourceStatus.failed
    source.error_msg = "Lỗi cũ"
    await db.commit()
    await ingest_pdf_source(source.id, storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())
    fresh = await db.get(Source, source.id, populate_existing=True)
    assert fresh.status == SourceStatus.ready and fresh.error_msg is None


def test_vision_warning_mentions_transient_failures():
    from app.ingestion.chunker import PageText
    from app.ingestion.pipeline import vision_cap_warning

    pages = [PageText(1, "a", "text", vision_failed=True), PageText(2, "b", "vision")]
    msg = vision_cap_warning(pages, 10)
    assert msg.startswith("Cảnh báo: 1 trang gọi vision bị lỗi tạm thời")
    assert "Xử lý lại" in msg
    assert vision_cap_warning([PageText(1, "a", "vision")], 10) is None


async def test_vision_quota_error_keeps_source_ready_with_warning(db):
    from tests.test_ai_retry import api_error

    class QuotaVision(FakeVision):
        async def page_to_markdown(self, png: bytes) -> str:
            raise api_error(429)

    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, make_pdf([LONG_TEXT, ""]))
    n = await ingest_pdf_source(source.id, storage=storage, embedder=FakeEmbedder(768), vision=QuotaVision())
    assert n >= 1
    fresh = await db.get(Source, source.id, populate_existing=True)
    assert fresh.status == SourceStatus.ready
    assert "1 trang gọi vision bị lỗi tạm thời" in fresh.error_msg
    methods = (
        await db.scalars(
            select(SourcePage.extraction_method)
            .where(SourcePage.source_id == source.id)
            .order_by(SourcePage.page_no)
        )
    ).all()
    assert [m.value for m in methods] == ["text", "text"]
