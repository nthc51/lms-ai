"""AI giải thích câu học viên làm sai (B3, spec 5.5).

Sau khi nộp bài, học viên bấm "AI giải thích" ở câu sai / bỏ trống: AI viết 2–4 câu vì sao phương án đã chọn chưa
đúng và vì sao đáp án đúng là đúng, dựa trên đoạn tài liệu sinh ra câu hỏi (trích `[1]`). Prompt chỉ phụ thuộc
(câu hỏi, phương án đã chọn, đoạn nguồn), nên bảng llm_cache dùng chung kết quả cho mọi học viên chọn cùng phương án;
mỗi bài làm còn lưu lại ở attempt_answers.ai_explanation để mở lại không gọi AI."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import LLMClient
from app.ai.prompts import load_prompt
from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.ratelimit import RateLimiter, rate_limited
from app.modules.auth.models import Role, User
from app.modules.materials.models import Chunk
from app.modules.quiz.models import AttemptAnswer, AttemptStatus, Question, QuizAttempt
from app.modules.quiz.schemas import ExplainOut

logger = logging.getLogger(__name__)

RATE_WINDOW_S = 3600
FINISHED = (AttemptStatus.completed, AttemptStatus.timed_out)


def _options_text(question: Question) -> str:
    return "\n".join(f"{o['id']}. {o['text']}" for o in question.options)


def _option_label(question: Question, option_id: str | None) -> str:
    if option_id is None:
        return "(học viên bỏ trống)"
    text = next((o["text"] for o in question.options if o["id"] == option_id), "")
    return f"{option_id}. {text}"


async def explain_answer(
    db: AsyncSession,
    llm: LLMClient,
    limiter: RateLimiter,
    user: User,
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
) -> ExplainOut:
    attempt = await db.scalar(
        select(QuizAttempt).where(QuizAttempt.id == attempt_id, QuizAttempt.user_id == user.id)
    )
    if attempt is None:
        raise not_found("Bài làm")
    if attempt.status not in FINISHED:
        raise AppError("INVALID_STATE", "Nộp bài xong mới xem được giải thích", 409)
    if str(question_id) not in attempt.question_order:
        raise not_found("Câu hỏi")
    question = await db.get(Question, question_id)
    if question is None:
        raise not_found("Câu hỏi")
    answer = await db.scalar(
        select(AttemptAnswer).where(
            AttemptAnswer.attempt_id == attempt.id, AttemptAnswer.question_id == question_id
        )
    )
    selected = answer.selected_option_id if answer else None
    if selected == question.correct_option_id:
        raise AppError("INVALID_STATE", "Câu này bạn đã làm đúng", 409)

    chunk = await db.get(Chunk, question.source_chunk_id) if question.source_chunk_id else None
    page_no = chunk.page_no if chunk else None
    if answer is not None and answer.ai_explanation:
        return ExplainOut(text=answer.ai_explanation, source_page_no=page_no)

    if user.role == Role.student:
        retry_after = await limiter.hit(
            f"quiz-explain:{user.id}", get_settings().quiz_explain_rate_limit_per_hour, RATE_WINDOW_S
        )
        if retry_after is not None:
            raise rate_limited(retry_after)

    prompt = load_prompt("quiz_explain").render(
        stem=question.stem,
        options=_options_text(question),
        chosen=_option_label(question, selected),
        correct=_option_label(question, question.correct_option_id),
        explanation=question.explanation or "(không có)",
        source=chunk.content if chunk else "(không có đoạn tài liệu nguồn)",
    )
    try:
        result = await llm.generate(prompt, op="quiz_explain")
    except Exception as e:
        logger.warning("Không sinh được giải thích cho câu %s", question_id, exc_info=True)
        raise AppError(
            "AI_UNAVAILABLE", "AI tạm thời không giải thích được, vui lòng thử lại sau", 503
        ) from e
    text = result.text.strip()
    if not text:
        raise AppError("AI_UNAVAILABLE", "AI tạm thời không giải thích được, vui lòng thử lại sau", 503)
    if answer is not None:
        answer.ai_explanation = text
        await db.commit()
    return ExplainOut(text=text, source_page_no=page_no)
