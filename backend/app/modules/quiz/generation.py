"""Sinh câu hỏi trắc nghiệm cho một bài học — thân của job quiz_gen (spec 5.4)."""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.llm_client import LLMClient, LLMOutputError
from app.ai.prompts import load_prompt
from app.core.db import SessionLocal
from app.modules.jobs.models import JobStatus
from app.modules.jobs.service import finish_job
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.modules.quiz.models import Difficulty, Question, QuestionOrigin, ReviewStatus
from app.modules.quiz.selection import ChunkInfo, ChunkPlan, plan_questions
from app.modules.quiz.validation import DraftBatch, QuestionContent, SelfCheckOut, validate_draft

logger = logging.getLogger(__name__)

DEDUP_THRESHOLD = 0.9  # cosine giữa stem mới và stem đã có > ngưỡng này thì coi là trùng (spec 5.4 bước 5)
NO_CHUNKS_ERROR = "Bài học chưa có tài liệu đã xử lý đủ dài để sinh câu hỏi"
NO_QUESTIONS_ERROR = "AI không sinh được câu hỏi hợp lệ nào"


@dataclass
class GenerationStats:
    requested: int
    invalid: int = 0  # bị bỏ sau khi đã sinh lại 1 lần
    duplicates: int = 0
    flagged: int = 0
    saved: int = 0


@dataclass(frozen=True)
class _Candidate:
    question: QuestionContent
    chunk: ChunkInfo
    prompt_version: str


async def load_lesson_chunks(db: AsyncSession, lesson_id: uuid.UUID) -> list[ChunkInfo]:
    rows = (
        await db.execute(
            select(Chunk.id, Chunk.content, Chunk.heading_path, Chunk.page_no, Chunk.token_count)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.lesson_id == lesson_id, Source.status == SourceStatus.ready)
            # Thứ tự tất định (cùng dữ liệu → cùng kế hoạch chọn chunk): theo source, rồi vị trí trong tài liệu.
            .order_by(
                Source.created_at,
                Source.id,
                Chunk.page_no.nulls_last(),
                Chunk.start_sec.nulls_last(),
                Chunk.created_at,
                Chunk.id,
            )
        )
    ).all()
    return [ChunkInfo(id=r[0], content=r[1], heading_path=r[2], page_no=r[3], token_count=r[4]) for r in rows]


async def _generate_for_chunk(llm: LLMClient, plan: ChunkPlan, stats: GenerationStats) -> list[_Candidate]:
    """Sinh câu cho một chunk. Câu sai luật được sinh lại đúng 1 lần kèm lý do sai; vẫn sai thì bỏ câu đó."""
    template = load_prompt("quiz_generate")
    remaining = list(plan.difficulties)
    feedback = ""
    kept: list[_Candidate] = []
    for attempt in (1, 2):
        prompt = template.render(
            count=len(remaining),
            difficulties=", ".join(d.value for d in remaining),
            heading=plan.chunk.heading_path or "(không có)",
            source=plan.chunk.content,
            feedback=feedback,
        )
        problems: list[str] = []
        try:
            # Không dùng cache: sinh lại cùng bài phải ra câu mới, không phải lô cũ mà bước lọc trùng sẽ loại hết.
            result, _ = await llm.generate_json(prompt, DraftBatch, op="quiz_generate", use_cache=False)
            drafts = result.questions[: len(remaining)]
            if len(drafts) < len(remaining):
                problems.append(f"thiếu {len(remaining) - len(drafts)} câu")
        except LLMOutputError as e:
            drafts = []
            problems.append(f"JSON không đúng schema: {e.error[:200]}")
        valid = 0
        for draft in drafts:
            question, error = validate_draft(draft)
            if question is None:
                problems.append(error)
            else:
                kept.append(_Candidate(question, plan.chunk, prompt.prompt_version))
                valid += 1
        remaining = remaining[valid:]
        if not remaining:
            break
        if attempt == 2:
            stats.invalid += len(remaining)
            logger.warning(
                "Bỏ %d câu không hợp lệ của chunk %s sau khi đã sinh lại: %s",
                len(remaining),
                plan.chunk.id,
                "; ".join(problems),
            )
            break
        feedback = (
            f"Lần trước có câu không hợp lệ ({'; '.join(problems)}). "
            f"Hãy sinh {len(remaining)} câu mới, tuân thủ đúng mọi yêu cầu."
        )
    return kept


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # embedder luôn trả vector đã chuẩn hóa


async def _dedup(
    embedder: Embedder, existing_stems: list[str], candidates: list[_Candidate], stats: GenerationStats
) -> list[_Candidate]:
    """Bỏ câu có stem gần trùng (cosine > 0.9) với câu đã có trong bài hoặc với câu mới được giữ trước nó."""
    if not candidates:
        return []
    vectors = await embedder.embed_documents(existing_stems + [c.question.stem for c in candidates])
    accepted = vectors[: len(existing_stems)]
    kept = []
    for cand, vec in zip(candidates, vectors[len(existing_stems) :], strict=True):
        if any(_cosine(vec, other) > DEDUP_THRESHOLD for other in accepted):
            stats.duplicates += 1
            continue
        accepted.append(vec)
        kept.append(cand)
    return kept


async def _self_check(llm: LLMClient, cand: _Candidate) -> bool:
    """LLM làm lại câu hỏi chỉ dựa vào đoạn nguồn (spec 5.4 bước 6); khác đáp án thì gắn cờ. Không kiểm tra được
    (lỗi sau khi đã retry, output sai định dạng) cũng gắn cờ để giảng viên xem kỹ."""
    q = cand.question
    prompt = load_prompt("quiz_self_check").render(
        source=cand.chunk.content, stem=q.stem, options="\n".join(f"{o.id}. {o.text}" for o in q.options)
    )
    try:
        answer, _ = await llm.generate_json(prompt, SelfCheckOut, op="quiz_self_check", use_cache=True)
    except Exception:
        logger.warning("Tự kiểm tra câu hỏi thất bại, gắn cờ để giảng viên xem kỹ", exc_info=True)
        return True
    return answer.answer_option_id.strip().upper() != q.correct_option_id


async def generate_questions_for_lesson(
    lesson_id: uuid.UUID,
    *,
    count: int,
    mix: Mapping[Difficulty, float],
    llm: LLMClient,
    embedder: Embedder,
    job_id: uuid.UUID | None = None,
    session_factory: async_sessionmaker = SessionLocal,
) -> GenerationStats:
    """Chọn chunk → sinh (retry 1 lần câu sai) → lọc trùng → tự kiểm tra → lưu review_status=pending.

    job_id (worker truyền vào): câu hỏi được ghi cùng transaction với trạng thái done của job; job không còn
    processing (đã bị sweeper chốt) thì bỏ kết quả. Không có chunk đủ dài / không sinh được câu hợp lệ nào /
    LLM lỗi sau khi retry thì ném lỗi để run_job ghi job failed. Dùng session DB ngắn: không giữ connection
    trong lúc gọi LLM."""
    async with session_factory() as db:
        chunks = await load_lesson_chunks(db, lesson_id)
        existing = list(
            (await db.scalars(select(Question.stem).where(Question.lesson_id == lesson_id))).all()
        )
    plans = plan_questions(chunks, count, mix)
    if not plans:
        raise ValueError(NO_CHUNKS_ERROR)
    stats = GenerationStats(requested=count)
    candidates: list[_Candidate] = []
    for plan in plans:
        candidates += await _generate_for_chunk(llm, plan, stats)
    kept = (await _dedup(embedder, existing, candidates, stats))[:count]
    if not kept:
        raise ValueError(NO_QUESTIONS_ERROR)
    rows = []
    for cand in kept:
        flagged = await _self_check(llm, cand)
        stats.flagged += flagged
        q = cand.question
        rows.append(
            Question(
                lesson_id=lesson_id,
                stem=q.stem,
                options=[o.model_dump() for o in q.options],
                correct_option_id=q.correct_option_id,
                explanation=q.explanation,
                difficulty=q.difficulty,
                origin=QuestionOrigin.ai,
                source_chunk_id=cand.chunk.id,
                review_status=ReviewStatus.pending,
                self_check_flag=flagged,
                ai_original=q.model_dump(mode="json"),
                prompt_version=cand.prompt_version,
            )
        )
    async with session_factory() as db:
        if job_id is not None and not await finish_job(db, job_id, JobStatus.done):
            logger.warning(
                "Job %s không còn processing, bỏ %d câu hỏi của bài %s", job_id, len(rows), lesson_id
            )
            return stats
        db.add_all(rows)
        await db.commit()
    stats.saved = len(rows)
    # Thông báo cho giảng viên (spec 5.4 bước 7) làm cùng B6 ở tuần 3; tạm thời chỉ ghi log.
    logger.info("quiz_gen bài %s: %s", lesson_id, stats)
    return stats
