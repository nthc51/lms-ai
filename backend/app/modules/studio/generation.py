"""Thân các job AI Studio: hướng dẫn tài liệu (source_guide), báo cáo / flashcard (studio_gen), tổng hợp ghi chú
(notes_synth). Hàm ở đây không kiểm quyền (đã kiểm khi tạo job) và không commit trạng thái job (run_job làm)."""

import hashlib
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import LLMClient, LLMOutputError
from app.ai.prompts import load_prompt
from app.ai.retrieval import RetrievedChunk
from app.core.config import Settings
from app.modules.courses.models import Course, Lesson, Section
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.modules.studio.models import ArtifactKind
from app.modules.tutor.text import clean_citations, source_payload

logger = logging.getLogger(__name__)

MAX_CARDS = 40
NO_CONTENT_ERROR = "Chưa có tài liệu nào được xử lý xong trong phạm vi này"
_CITE_RE = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class ScopeChunk(RetrievedChunk):
    """Một đoạn trong phạm vi (dùng lại RetrievedChunk để citation/source_payload của AI Tutor dùng được)."""

    token_count: int


async def load_scope_chunks(
    db: AsyncSession, course_id: uuid.UUID, lesson_id: uuid.UUID | None, source_id: uuid.UUID | None = None
) -> list[ScopeChunk]:
    """Mọi đoạn của tài liệu đã xử lý xong trong phạm vi (một bài, cả khóa, hoặc một tài liệu), theo thứ tự đọc:
    chương → bài → tài liệu → trang."""
    stmt = (
        select(
            Chunk.id,
            Chunk.lesson_id,
            Lesson.title,
            Chunk.content,
            Chunk.heading_path,
            Chunk.page_no,
            Chunk.start_sec,
            Chunk.token_count,
        )
        .join(Source, Source.id == Chunk.source_id)
        .join(Lesson, Lesson.id == Chunk.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Chunk.course_id == course_id, Source.status == SourceStatus.ready)
        .order_by(
            Section.position,
            Lesson.position,
            Source.created_at,
            Source.id,
            Chunk.page_no.nulls_last(),
            Chunk.start_sec.nulls_last(),
            Chunk.created_at,
            Chunk.id,
        )
    )
    if lesson_id is not None:
        stmt = stmt.where(Chunk.lesson_id == lesson_id)
    if source_id is not None:
        stmt = stmt.where(Chunk.source_id == source_id)
    rows = (await db.execute(stmt)).all()
    return [ScopeChunk(r[0], r[1], r[2], r[3], r[4], r[5], r[6], 1.0, r[7]) for r in rows]


def fingerprint(chunks: Sequence[ScopeChunk]) -> str:
    """Băm danh sách đoạn: xử lý lại tài liệu tạo chunk mới (id mới), nên fingerprint đổi theo tài liệu."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(str(c.chunk_id).encode())
    return h.hexdigest()


async def scope_title(db: AsyncSession, course_id: uuid.UUID, lesson_id: uuid.UUID | None) -> str:
    if lesson_id is not None:
        return f"Bài: {await db.scalar(select(Lesson.title).where(Lesson.id == lesson_id))}"
    return f"Khóa học: {await db.scalar(select(Course.title).where(Course.id == course_id))}"


def numbered_context(pairs: Sequence[tuple[int, ScopeChunk]]) -> str:
    """Như tutor.text.format_context nhưng giữ số thứ tự toàn cục [n] (một phần của tài liệu dài vẫn đúng nhãn)."""
    blocks = []
    for n, c in pairs:
        meta = [f"Bài: {c.lesson_title}"]
        if c.page_no is not None:
            meta.append(f"trang {c.page_no}")
        if c.heading_path:
            meta.append(c.heading_path)
        blocks.append(f"[{n}] ({' · '.join(meta)})\n{c.content}")
    return "\n\n".join(blocks)


def batches(chunks: Sequence[ScopeChunk], budget: int) -> list[list[tuple[int, ScopeChunk]]]:
    """Chia đoạn (đánh số từ 1) thành các phần liên tiếp, mỗi phần ≤ budget token (đoạn quá lớn đứng riêng)."""
    out: list[list[tuple[int, ScopeChunk]]] = []
    cur: list[tuple[int, ScopeChunk]] = []
    used = 0
    for n, c in enumerate(chunks, 1):
        if cur and used + c.token_count > budget:
            out.append(cur)
            cur, used = [], 0
        cur.append((n, c))
        used += c.token_count
    if cur:
        out.append(cur)
    return out


def citations_for(numbers: Sequence[int], chunks: Sequence[ScopeChunk]) -> list[dict]:
    """Bản ghi nguồn cho mỗi [n] được dùng: như event `sources` của AI Tutor (có đoạn trích để xem trước)."""
    return [source_payload(n, chunks[n - 1]) for n in sorted(set(numbers)) if 1 <= n <= len(chunks)]


async def _context_for(
    llm: LLMClient, title: str, chunks: Sequence[ScopeChunk], settings: Settings
) -> tuple[str, int, int]:
    """Ngữ cảnh gửi cho lời gọi cuối. Vừa ngân sách thì gửi nguyên văn; dài hơn thì tóm tắt từng phần (map),
    giữ nhãn [n] toàn cục, rồi ghép các bản tóm tắt. Trả (context, tokens_in, tokens_out) của bước map."""
    parts = batches(chunks, settings.studio_max_input_tokens)
    if len(parts) == 1:
        return numbered_context(parts[0]), 0, 0
    notes, t_in, t_out = [], 0, 0
    template = load_prompt("studio_map")
    for part in parts:
        result = await llm.generate(
            template.render(scope=title, context=numbered_context(part)), op="studio_map"
        )
        notes.append(result.text.strip())
        t_in, t_out = t_in + result.tokens_in, t_out + result.tokens_out
    return "\n\n".join(notes), t_in, t_out


class ReportResult(BaseModel):
    content_md: str
    citations: list[dict]
    prompt_version: str


async def generate_report(
    llm: LLMClient, kind: ArtifactKind, title: str, chunks: Sequence[ScopeChunk], settings: Settings
) -> ReportResult:
    if not chunks:
        raise ValueError(NO_CONTENT_ERROR)
    context, _, _ = await _context_for(llm, title, chunks, settings)
    prompt = load_prompt(f"studio_{kind.value}").render(scope=title, context=context)
    result = await llm.generate(prompt, op=f"studio_{kind.value}")
    content, cited = clean_citations(result.text.strip(), len(chunks))
    return ReportResult(
        content_md=content, citations=citations_for(cited, chunks), prompt_version=prompt.prompt_version
    )


class CardDraft(BaseModel):
    front: str = Field(min_length=1, max_length=300)
    back: str = Field(min_length=1, max_length=800)
    sources: list[int] = Field(default_factory=list)


class CardBatch(BaseModel):
    cards: list[CardDraft]


class CardsResult(BaseModel):
    cards: list[dict]
    citations: list[dict]
    prompt_version: str


def _cards_wanted(tokens: int) -> int:
    """Khoảng 1 thẻ cho mỗi 300 token tài liệu, 5–15 thẻ mỗi lời gọi."""
    return max(5, min(15, tokens // 300))


async def generate_flashcards(
    llm: LLMClient, title: str, chunks: Sequence[ScopeChunk], settings: Settings
) -> CardsResult:
    """Mỗi phần tài liệu (theo ngân sách token) một lời gọi; gộp, bỏ thẻ trùng mặt trước, tối đa MAX_CARDS thẻ."""
    if not chunks:
        raise ValueError(NO_CONTENT_ERROR)
    template = load_prompt("studio_flashcards")
    cards: list[dict] = []
    seen: set[str] = set()
    used: list[int] = []
    for part in batches(chunks, settings.studio_max_input_tokens):
        count = _cards_wanted(sum(c.token_count for _, c in part))
        prompt = template.render(scope=title, count=count, context=numbered_context(part))
        try:
            batch, _ = await llm.generate_json(prompt, CardBatch, op="studio_flashcards")
        except LLMOutputError:
            logger.warning("Bỏ một phần flashcard: AI trả JSON sai schema")
            continue
        valid = {n for n, _ in part}
        for d in batch.cards:
            key = " ".join(d.front.lower().split())
            if key in seen or len(cards) >= MAX_CARDS:
                continue
            seen.add(key)
            sources = sorted({n for n in d.sources if n in valid})
            cards.append({"front": d.front.strip(), "back": d.back.strip(), "sources": sources})
            used.extend(sources)
    if not cards:
        raise ValueError("AI không soạn được flashcard hợp lệ nào")
    return CardsResult(
        cards=cards, citations=citations_for(used, chunks), prompt_version=template.prompt_version
    )


class GuideDraft(BaseModel):
    title: str = Field(default="", max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    topics: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


def guide_document(chunks: Sequence[ScopeChunk], budget: int) -> str:
    """Phần đầu của tài liệu cho hướng dẫn: mỗi mục (heading) lấy đoạn đầu tiên, tới hết ngân sách token.
    Tài liệu ngắn thì đủ cả; tài liệu dài thì vẫn phủ được mọi mục thay vì chỉ vài trang đầu."""
    picked: list[ScopeChunk] = []
    seen: set[str] = set()
    used = 0
    for c in chunks:  # lượt 1: đoạn đầu của mỗi mục
        if c.heading_path not in seen and used + c.token_count <= budget:
            seen.add(c.heading_path)
            picked.append(c)
            used += c.token_count
    for c in chunks:  # lượt 2: còn ngân sách thì thêm các đoạn khác theo thứ tự
        if c not in picked and used + c.token_count <= budget:
            picked.append(c)
            used += c.token_count
    order = {c.chunk_id: i for i, c in enumerate(chunks)}
    picked.sort(key=lambda c: order[c.chunk_id])
    return "\n\n".join(f"## {c.heading_path}\n{c.content}" if c.heading_path else c.content for c in picked)


async def generate_source_guide(llm: LLMClient, chunks: Sequence[ScopeChunk], settings: Settings):
    template = load_prompt("source_guide")
    prompt = template.render(document=guide_document(chunks, settings.source_guide_max_input_tokens))
    draft, _ = await llm.generate_json(prompt, GuideDraft, op="source_guide", model=settings.llm_cheap_model)
    clip = lambda items, n, length: [" ".join(x.split())[:length] for x in items if x.strip()][:n]
    return (
        draft.title.strip()[:200],
        draft.summary.strip(),
        clip(draft.topics, 7, 60),
        clip(draft.questions, 5, 150),
        template.prompt_version,
    )


def cited_numbers(text: str) -> set[int]:
    return {int(n) for n in _CITE_RE.findall(text)}
