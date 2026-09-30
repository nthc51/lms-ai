"""Tìm đoạn tài liệu cho AI Tutor.

A5 (tuần 2): chỉ vector (cosine top-k). B2 (tuần 3) thay phần thân retrieve() bằng hybrid (vector top-20 +
full-text top-20, gộp RRF, giữ top-6) mà không đổi chữ ký: caller chỉ dùng SearchScope, RetrievalResult
và should_refuse; B2 điền thêm has_fulltext_match."""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedder import Embedder
from app.modules.courses.models import Course, CourseStatus, Lesson
from app.modules.materials.models import Chunk, Source, SourceStatus


@dataclass(frozen=True)
class SearchScope:
    """Phạm vi tìm (spec 4.3): theo bài học (lesson_id), hoặc cả khóa khi lesson_id là None."""

    course_id: uuid.UUID
    lesson_id: uuid.UUID | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    lesson_id: uuid.UUID
    lesson_title: str
    content: str
    heading_path: str
    page_no: int | None
    start_sec: float | None
    similarity: float


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]  # đã xếp hạng, tốt nhất trước
    top_similarity: float | None  # cosine cao nhất; None khi không có chunk nào
    has_fulltext_match: bool = False  # A5 chỉ tìm vector nên luôn False; B2 điền giá trị thật


def scope_filter(scope: SearchScope, embedding_model: str) -> list[ColumnElement[bool]]:
    """Điều kiện chung của retrieve và count_ready_chunks (câu lệnh phải join Source; theo khóa thì join
    thêm Course).

    Luôn lọc đúng model embedding hiện tại và chỉ lấy chunk của source đang ready (source đang xử lý lại
    hoặc xử lý lại bị lỗi vẫn còn chunk cũ). Luôn lọc course_id (kể cả theo bài học: lesson không thuộc
    khóa thì không ra gì, và dùng được ix_chunks_scope). Theo khóa thì chỉ khi khóa đã publish."""
    conds = [
        Chunk.course_id == scope.course_id,
        Chunk.embedding_model == embedding_model,
        Source.status == SourceStatus.ready,
    ]
    if scope.lesson_id is not None:
        conds.append(Chunk.lesson_id == scope.lesson_id)
    else:
        conds.append(Course.status == CourseStatus.published)
    return conds


async def retrieve(
    db: AsyncSession, embedder: Embedder, scope: SearchScope, query: str, *, top_k: int = 6
) -> RetrievalResult:
    vector = await embedder.embed_query(query)
    distance = Chunk.embedding.cosine_distance(vector)
    # pgvector ≥ 0.8: HNSW có lọc WHERE quét tiếp cho đủ top_k thay vì trả thiếu (ef_search mặc định 40)
    await db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    rows = (
        await db.execute(
            select(
                Chunk.id,
                Chunk.lesson_id,
                Lesson.title,
                Chunk.content,
                Chunk.heading_path,
                Chunk.page_no,
                Chunk.start_sec,
                (1 - distance).label("similarity"),
            )
            .join(Source, Source.id == Chunk.source_id)
            .join(Course, Course.id == Chunk.course_id)
            .join(Lesson, Lesson.id == Chunk.lesson_id)
            .where(*scope_filter(scope, embedder.model))
            .order_by(distance)
            .limit(top_k)
        )
    ).all()
    chunks = [
        RetrievedChunk(
            chunk_id=r[0],
            lesson_id=r[1],
            lesson_title=r[2],
            content=r[3],
            heading_path=r[4],
            page_no=r[5],
            start_sec=r[6],
            similarity=float(r[7]),
        )
        for r in rows
    ]
    return RetrievalResult(chunks=chunks, top_similarity=chunks[0].similarity if chunks else None)


async def count_ready_chunks(db: AsyncSession, scope: SearchScope, embedding_model: str) -> int:
    """Số chunk Tutor tìm được trong phạm vi; 0 thì ẩn Tutor ("Tài liệu đang được xử lý", spec 5.7)."""
    stmt = select(func.count(Chunk.id)).join(Source, Source.id == Chunk.source_id)
    if scope.lesson_id is None:
        stmt = stmt.join(Course, Course.id == Chunk.course_id)
    n = await db.scalar(stmt.where(*scope_filter(scope, embedding_model)))
    return n or 0


def should_refuse(result: RetrievalResult, threshold: float) -> bool:
    """Chốt chặn trước LLM (spec 5.3 bước 3): không có chunk nào, hoặc similarity cao nhất < τ và không có
    kết quả full-text. A5: has_fulltext_match luôn False nên chỉ còn điều kiện similarity.
    Viết dạng `not (x >= τ)` để similarity None hoặc NaN cũng bị từ chối."""
    if not result.chunks:
        return True
    if result.has_fulltext_match:
        return False
    top = result.top_similarity
    return top is None or not (top >= threshold)
