import uuid

from sqlalchemy import select

from app.ai.retrieval import (
    RetrievalResult,
    RetrievedChunk,
    SearchScope,
    count_ready_chunks,
    retrieve,
    should_refuse,
)
from app.modules.courses.models import CourseStatus, Lesson, Section
from app.modules.materials.models import SourceStatus
from tests.factories import add_chunk, make_lesson, make_pdf_source, make_user, unit_vector
from tests.fakes import InMemoryStorage


class VectorEmbedder:
    """Embedder giả trả đúng vector cho trước, để điều khiển similarity."""

    model = "fake-768"
    dim = 768

    def __init__(self, vector: list[float]):
        self.vector = vector

    async def embed_query(self, text: str) -> list[float]:
        return self.vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.vector for _ in texts]


def between(i: int, j: int, w: float) -> list[float]:
    """Vector đơn vị nằm giữa trục i và j: cosine với unit_vector(i) đúng bằng w."""
    v = [0.0] * 768
    v[i] = w
    v[j] = (1 - w * w) ** 0.5
    return v


async def _ready_lesson(db, teacher, course=None):
    if course is None:
        course, lesson = await make_lesson(db, teacher)
    else:
        section = await db.scalar(select(Section).where(Section.course_id == course.id))
        lesson = Lesson(section_id=section.id, title="Bài 2", position=2)
        db.add(lesson)
        await db.commit()
    source = await make_pdf_source(
        db, InMemoryStorage(), teacher, lesson, b"%PDF-1.7", status=SourceStatus.ready
    )
    return course, lesson, source


async def test_lesson_scope_ranks_by_cosine_and_limits_top_k(db):
    teacher = await make_user(db)
    course, lesson, source = await _ready_lesson(db, teacher)
    for i, w in enumerate([0.2, 0.9, 0.5]):
        await add_chunk(db, source, course, lesson, f"đoạn {i}", between(0, i + 1, w))
    result = await retrieve(
        db, VectorEmbedder(unit_vector(0)), SearchScope(course.id, lesson.id), "q", top_k=2
    )
    assert [c.content for c in result.chunks] == ["đoạn 1", "đoạn 2"]
    assert abs(result.top_similarity - 0.9) < 1e-5 and result.has_fulltext_match is False
    assert result.chunks[0].lesson_title == "Bài 1" and result.chunks[0].page_no == 1


async def test_retrieved_chunk_passes_through_citation_fields(db):
    teacher = await make_user(db)
    course, lesson, source = await _ready_lesson(db, teacher)
    chunk = await add_chunk(
        db,
        source,
        course,
        lesson,
        "có mốc",
        unit_vector(0),
        page_no=None,
        heading_path="Chương 1 > Mục 2",
        start_sec=12.5,
    )
    result = await retrieve(db, VectorEmbedder(unit_vector(0)), SearchScope(course.id, lesson.id), "q")
    [got] = result.chunks
    assert got.chunk_id == chunk.id and got.lesson_id == lesson.id
    assert got.heading_path == "Chương 1 > Mục 2" and got.page_no is None and got.start_sec == 12.5
    assert abs(got.similarity - 1.0) < 1e-5


async def test_lesson_scope_requires_lesson_to_belong_to_course(db):
    teacher = await make_user(db)
    course, lesson, source = await _ready_lesson(db, teacher)
    other_course, _, _ = await _ready_lesson(db, teacher)
    await add_chunk(db, source, course, lesson, "bài 1", unit_vector(0))
    emb = VectorEmbedder(unit_vector(0))
    mismatched = SearchScope(other_course.id, lesson.id)
    assert (await retrieve(db, emb, mismatched, "q")).chunks == []
    assert await count_ready_chunks(db, mismatched, emb.model) == 0
    assert await count_ready_chunks(db, SearchScope(course.id, lesson.id), emb.model) == 1


async def test_course_scope_covers_lessons_of_published_course_only(db):
    teacher = await make_user(db)
    course, l1, s1 = await _ready_lesson(db, teacher)
    _, l2, s2 = await _ready_lesson(db, teacher, course)
    other_course, l3, s3 = await _ready_lesson(db, teacher)
    await add_chunk(db, s1, course, l1, "bài 1", unit_vector(0))
    await add_chunk(db, s2, course, l2, "bài 2", unit_vector(0))
    await add_chunk(db, s3, other_course, l3, "khóa khác", unit_vector(0))
    emb = VectorEmbedder(unit_vector(0))
    result = await retrieve(db, emb, SearchScope(course.id), "q")
    assert sorted(c.content for c in result.chunks) == ["bài 1", "bài 2"]
    assert await count_ready_chunks(db, SearchScope(course.id), emb.model) == 2

    course.status = CourseStatus.draft
    await db.commit()
    assert (await retrieve(db, emb, SearchScope(course.id), "q")).chunks == []
    # theo bài học thì vẫn tìm được (giảng viên xem trước khóa nháp)
    lesson_result = await retrieve(db, emb, SearchScope(course.id, l1.id), "q")
    assert [c.content for c in lesson_result.chunks] == ["bài 1"]


async def test_other_embedding_model_and_unready_sources_are_ignored(db):
    teacher = await make_user(db)
    course, lesson, ready = await _ready_lesson(db, teacher)
    processing = await make_pdf_source(
        db, InMemoryStorage(), teacher, lesson, b"%PDF-1.7", status=SourceStatus.processing
    )
    failed = await make_pdf_source(
        db, InMemoryStorage(), teacher, lesson, b"%PDF-1.7", status=SourceStatus.failed
    )
    await add_chunk(db, ready, course, lesson, "đúng model", unit_vector(0))
    await add_chunk(db, ready, course, lesson, "model cũ", unit_vector(0), embedding_model="old-768")
    await add_chunk(db, processing, course, lesson, "đang xử lý lại", unit_vector(0))
    await add_chunk(db, failed, course, lesson, "xử lý lại bị lỗi", unit_vector(0))
    emb = VectorEmbedder(unit_vector(0))
    scope = SearchScope(course.id, lesson.id)
    assert [c.content for c in (await retrieve(db, emb, scope, "q")).chunks] == ["đúng model"]
    assert await count_ready_chunks(db, scope, emb.model) == 1


def test_should_refuse():
    assert should_refuse(RetrievalResult(chunks=[], top_similarity=None), 0.3)
    chunk = RetrievedChunk(uuid.uuid4(), uuid.uuid4(), "Bài", "x", "", 1, None, 0.25)
    assert should_refuse(RetrievalResult([chunk], 0.25), 0.3)
    assert not should_refuse(RetrievalResult([chunk], 0.25), 0.2)
    # B2: có kết quả full-text thì không từ chối dù similarity thấp
    assert not should_refuse(RetrievalResult([chunk], 0.25, has_fulltext_match=True), 0.3)
    # NaN/None không bao giờ lọt qua chốt chặn
    assert should_refuse(RetrievalResult([chunk], float("nan")), 0.3)
    assert should_refuse(RetrievalResult([chunk], None), 0.3)
    assert not should_refuse(RetrievalResult([chunk], 0.3), 0.3)
