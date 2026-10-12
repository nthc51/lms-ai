"""Tìm đoạn tài liệu cho AI Tutor.

Hybrid (B2, spec 5.3 bước 2): vector top-20 (cosine) + full-text top-20 (`websearch_to_tsquery` trên cột `tsv`
đã bỏ dấu), gộp bằng Reciprocal Rank Fusion: điểm = Σ 1/(60 + hạng), giữ top_k. Full-text bắt được thuật ngữ,
mã số, tên riêng mà vector dễ bỏ sót; gõ không dấu vẫn khớp nhờ `immutable_unaccent`.
RETRIEVAL_MODE=vector quay về chỉ vector (benchmark dùng để so sánh)."""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedder import Embedder
from app.core.config import get_settings
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
    has_fulltext_match: bool = False  # có đoạn khớp full-text (chế độ vector: luôn False)


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


CANDIDATES = 20  # số ứng viên lấy từ mỗi nhánh trước khi gộp
RRF_K = 60
RetrievalMode = Literal["hybrid", "vector"]


def _scoped(stmt, scope: SearchScope, embedding_model: str):
    return (
        stmt.join(Source, Source.id == Chunk.source_id)
        .join(Course, Course.id == Chunk.course_id)
        .where(*scope_filter(scope, embedding_model))
    )


def _tsquery(query: str):
    return func.websearch_to_tsquery(text("'simple'::regconfig"), func.immutable_unaccent(query))


async def retrieve(
    db: AsyncSession,
    embedder: Embedder,
    scope: SearchScope,
    query: str,
    *,
    top_k: int = 6,
    mode: RetrievalMode | None = None,
) -> RetrievalResult:
    mode = mode or get_settings().retrieval_mode
    vector = await embedder.embed_query(query)
    distance = Chunk.embedding.cosine_distance(vector)
    # pgvector ≥ 0.8: HNSW có lọc WHERE quét tiếp cho đủ số ứng viên thay vì trả thiếu (ef_search mặc định 40)
    await db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    vector_ids = list(
        await db.scalars(
            _scoped(select(Chunk.id), scope, embedder.model)
            .order_by(distance, Chunk.id)
            .limit(CANDIDATES if mode == "hybrid" else top_k)
        )
    )
    text_ids: list = []
    if mode == "hybrid":
        tsq = _tsquery(query)
        text_ids = list(
            await db.scalars(
                _scoped(select(Chunk.id), scope, embedder.model)
                .where(Chunk.tsv.op("@@")(tsq))
                .order_by(func.ts_rank_cd(Chunk.tsv, tsq).desc(), Chunk.id)
                .limit(CANDIDATES)
            )
        )
    scores: dict = {}
    for ranked in (vector_ids, text_ids):
        for rank, cid in enumerate(ranked, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    if not scores:
        return RetrievalResult(chunks=[], top_similarity=None, has_fulltext_match=False)
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
            .join(Lesson, Lesson.id == Chunk.lesson_id)
            .where(Chunk.id.in_(list(scores)))
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
    # RRF cao trước; bằng điểm thì gần nghĩa hơn trước
    chunks.sort(key=lambda c: (-scores[c.chunk_id], -c.similarity))
    chunks = chunks[:top_k]
    return RetrievalResult(
        chunks=chunks,
        top_similarity=max((c.similarity for c in chunks), default=None),
        has_fulltext_match=bool(text_ids),
    )


async def count_ready_chunks(db: AsyncSession, scope: SearchScope, embedding_model: str) -> int:
    """Số chunk Tutor tìm được trong phạm vi; 0 thì ẩn Tutor ("Tài liệu đang được xử lý", spec 5.7)."""
    stmt = select(func.count(Chunk.id)).join(Source, Source.id == Chunk.source_id)
    if scope.lesson_id is None:
        stmt = stmt.join(Course, Course.id == Chunk.course_id)
    n = await db.scalar(stmt.where(*scope_filter(scope, embedding_model)))
    return n or 0


def should_refuse(result: RetrievalResult, threshold: float) -> bool:
    """Chốt chặn trước LLM (spec 5.3 bước 3): không có chunk nào, hoặc similarity cao nhất < τ và không có
    kết quả full-text (full-text khớp nghĩa là mọi từ của câu hỏi đều có trong tài liệu).
    Viết dạng `not (x >= τ)` để similarity None hoặc NaN cũng bị từ chối."""
    if not result.chunks:
        return True
    if result.has_fulltext_match:
        return False
    top = result.top_similarity
    return top is None or not (top >= threshold)
