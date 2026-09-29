from sqlalchemy import func, select, text

from app.modules.materials.models import Chunk, ExtractionMethod, Source, SourcePage
from tests.factories import add_chunk, make_lesson, make_pdf_source, make_user, unit_vector
from tests.fakes import InMemoryStorage

FTS = text("SELECT count(*) FROM chunks "
           "WHERE tsv @@ websearch_to_tsquery('simple', immutable_unaccent(:q))")


async def _setup(db):
    teacher = await make_user(db)
    course, lesson = await make_lesson(db, teacher)
    source = await make_pdf_source(db, InMemoryStorage(), teacher, lesson, b"%PDF-1.7")
    return course, lesson, source


async def test_full_text_matches_without_diacritics(db):
    course, lesson, source = await _setup(db)
    await add_chunk(db, source, course, lesson, "Tìm kiếm nhị phân chia đôi khoảng tìm", unit_vector(0))
    assert await db.scalar(FTS, {"q": "tim kiem nhi phan"}) == 1
    assert await db.scalar(FTS, {"q": "Tìm Kiếm"}) == 1
    assert await db.scalar(FTS, {"q": "đồ thị"}) == 0


async def test_hnsw_index_can_serve_nearest_neighbour_query(db):
    course, lesson, source = await _setup(db)
    for i in range(3):
        await add_chunk(db, source, course, lesson, f"đoạn {i}", unit_vector(i))
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = (await db.execute(
        text("EXPLAIN SELECT id FROM chunks ORDER BY embedding <=> CAST(:v AS vector) LIMIT 3"),
        {"v": str(unit_vector(1))},
    )).scalars().all()
    await db.rollback()
    assert any("ix_chunks_embedding_hnsw" in line for line in plan), plan


async def test_deleting_source_cascades_pages_and_chunks(db):
    course, lesson, source = await _setup(db)
    db.add(SourcePage(source_id=source.id, page_no=1, extraction_method=ExtractionMethod.text, markdown="x"))
    await db.commit()
    await add_chunk(db, source, course, lesson, "nội dung", unit_vector(0))
    await db.execute(Source.__table__.delete().where(Source.id == source.id))
    await db.commit()
    assert await db.scalar(select(func.count(Chunk.id))) == 0
    assert await db.scalar(select(func.count()).select_from(SourcePage)) == 0
