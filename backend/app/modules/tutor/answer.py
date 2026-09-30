"""Luồng trả lời của AI Tutor (spec 5.3): viết lại câu hỏi → tìm tài liệu → chốt chặn → stream SSE → lưu.

Caller (endpoint SSE, Task 11 `prepare_question`) phải làm TRƯỚC khi gọi answer_stream, trong session DB của
request: kiểm quyền lại bằng resolve_scope (quyền có thể đã đổi từ lúc tạo phiên), rate limit, lấy lịch sử, rồi
lưu câu hỏi của học viên và COMMIT riêng. answer_stream chỉ ghi tin nhắn assistant, trong transaction riêng mở
sau cùng, nên created_at của câu trả lời luôn sau câu hỏi. answer_stream không giữ session DB nào trong lúc gọi
LLM: tìm tài liệu và lưu câu trả lời đều dùng session ngắn từ session_factory."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import anyio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.llm_client import LLMClient, LLMStream
from app.ai.prompts import load_prompt
from app.ai.retrieval import RetrievedChunk, SearchScope, retrieve, should_refuse
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.modules.tutor.models import ChatMessage, ChatRole
from app.modules.tutor.text import (
    REFUSAL_MESSAGE,
    RefuseFilter,
    citation_record,
    clean_citations,
    format_context,
    format_history,
    source_payload,
    sse,
)

logger = logging.getLogger(__name__)

DISCONNECT_CHECK_EVERY = 10  # số mảnh token giữa hai lần hỏi client còn kết nối không (spec 5.3 bước 6)
AI_ERROR = {"code": "AI_UNAVAILABLE", "message": "AI Tutor tạm thời không trả lời được, vui lòng thử lại"}


@dataclass(frozen=True)
class AskContext:
    session_id: uuid.UUID
    scope: SearchScope
    course_title: str
    question: str
    history: list[tuple[ChatRole, str]] = field(default_factory=list)  # ≤ 4 tin gần nhất, cũ → mới


class _Answer:
    """Trạng thái của một câu trả lời đang sinh; save() ghi tin nhắn assistant đúng một lần."""

    def __init__(self, ctx: AskContext, session_factory: async_sessionmaker):
        self.ctx = ctx
        self._session_factory = session_factory
        self.started = time.perf_counter()
        self.sources: list[RetrievedChunk] = []
        self.stream: LLMStream | None = None
        self.refuse_filter = RefuseFilter()
        self.refused = False
        self.ttft_ms: int | None = None
        self.prompt_version: str | None = None
        self.extra_tokens_in = 0  # lời gọi viết lại câu hỏi
        self.extra_tokens_out = 0
        self.saved = False

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def mark_first_token(self) -> None:
        if self.ttft_ms is None:
            self.ttft_ms = self.elapsed_ms()

    def finish_filter(self) -> str:
        """Kết thúc RefuseFilter (gọi lại nhiều lần an toàn): trả phần đang bị giữ nếu không phải REFUSE."""
        tail = self.refuse_filter.finish()
        if self.refuse_filter.refused:
            self.refused = True
        return tail

    async def save(self, *, truncated: bool | None = None) -> tuple[uuid.UUID, str, list[dict]]:
        """truncated=None: lấy theo stream (chưa nhận hết, hoặc provider cắt: MAX_TOKENS, SAFETY...)."""
        self.saved = True
        self.finish_filter()  # nhả phần còn giữ (hoặc chốt REFUSE) trước khi lưu, kể cả khi lỗi/bị hủy
        if truncated is None:
            truncated = self.stream.truncated if self.stream is not None else False
        if self.refused:
            content, cited = REFUSAL_MESSAGE, []
        else:
            content, cited = clean_citations(self.stream.text if self.stream else "", len(self.sources))
        citations = [citation_record(n, self.sources[n - 1]) for n in cited]
        message = ChatMessage(
            id=uuid.uuid4(),
            session_id=self.ctx.session_id,
            role=ChatRole.assistant,
            content=content,
            citations=citations,
            refused=self.refused,
            truncated=truncated,
            latency_ms=self.elapsed_ms(),
            ttft_ms=self.ttft_ms,
            tokens_in=self.extra_tokens_in + (self.stream.tokens_in if self.stream else 0),
            tokens_out=self.extra_tokens_out + (self.stream.tokens_out if self.stream else 0),
            prompt_version=self.prompt_version,
        )
        async with self._session_factory() as db:
            db.add(message)
            await db.commit()
        return message.id, content, citations


async def _rewrite(llm: LLMClient, ctx: AskContext, s: Settings, answer: _Answer) -> str:
    """Biến câu hỏi nối tiếp thành câu độc lập (spec 5.3 bước 1), dùng model rẻ. Lỗi hoặc quá hạn chót tổng
    (tutor_rewrite_deadline_s, gồm cả retry) thì dùng câu hỏi gốc."""
    prompt = load_prompt("tutor_rewrite").render(history=format_history(ctx.history), question=ctx.question)
    try:
        async with asyncio.timeout(s.tutor_rewrite_deadline_s):
            result = await llm.generate(prompt, op="tutor_rewrite", model=s.llm_cheap_model)
    except Exception:
        logger.warning(
            "Không viết lại được câu hỏi (session %s), dùng câu hỏi gốc", ctx.session_id, exc_info=True
        )
        return ctx.question
    answer.extra_tokens_in += result.tokens_in
    answer.extra_tokens_out += result.tokens_out
    return result.text.strip() or ctx.question


async def answer_stream(
    ctx: AskContext,
    *,
    llm: LLMClient,
    embedder: Embedder,
    is_disconnected: Callable[[], Awaitable[bool]],
    session_factory: async_sessionmaker = SessionLocal,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    """Sinh các event SSE: sources → token… → done (hoặc error khi lỗi).

    Phần trước token đầu (viết lại + tìm tài liệu + mở stream, gồm retry) chịu chung hạn chót
    tutor_prestream_deadline_s; quá hạn → event error. Khối finally luôn lưu câu trả lời — kể cả phần dở khi
    client ngắt kết nối, khi lỗi, hoặc khi task stream bị hủy — với truncated=true và số token đã tiêu. Việc lưu
    lúc bị hủy chạy trong CancelScope(shield=True)."""
    s = settings or get_settings()
    answer = _Answer(ctx, session_factory)
    deadline = asyncio.get_running_loop().time() + s.tutor_prestream_deadline_s
    try:
        async with asyncio.timeout_at(deadline):
            query = await _rewrite(llm, ctx, s, answer) if ctx.history else ctx.question
            async with session_factory() as db:
                result = await retrieve(db, embedder, ctx.scope, query, top_k=s.tutor_top_k)
        answer.sources = result.chunks
        yield sse("sources", {"sources": [source_payload(n, c) for n, c in enumerate(result.chunks, 1)]})

        if should_refuse(result, s.tutor_refuse_threshold):
            answer.refused = True  # chốt chặn trước LLM: không gọi LLM
            answer.mark_first_token()
            yield sse("token", {"text": REFUSAL_MESSAGE})
        else:
            prompt = load_prompt("tutor_answer").render(
                course_title=ctx.course_title, context=format_context(result.chunks), question=query
            )
            answer.prompt_version = prompt.prompt_version
            async with AsyncExitStack() as stack:
                # Chỉ việc mở stream nằm trong hạn chót; khối timeout đóng lại trước lần yield đầu tiên
                async with asyncio.timeout_at(deadline):
                    stream = await stack.enter_async_context(llm.stream(prompt, op="tutor_answer"))
                answer.stream = stream
                count = 0
                async for piece in stream:
                    if out := answer.refuse_filter.feed(piece):
                        answer.mark_first_token()
                        yield sse("token", {"text": out})
                    count += 1
                    if count % DISCONNECT_CHECK_EVERY == 0 and await is_disconnected():
                        logger.info("Client ngắt kết nối giữa chừng (session %s)", ctx.session_id)
                        return  # thoát stack (đóng stream upstream), finally lưu phần đã sinh
            tail = answer.finish_filter()
            if answer.refused:
                answer.mark_first_token()
                yield sse("token", {"text": REFUSAL_MESSAGE})
            elif tail:
                answer.mark_first_token()
                yield sse("token", {"text": tail})
        message_id, content, citations = await answer.save()
        yield sse(
            "done",
            {
                "message_id": str(message_id),
                "citations": citations,
                "content": content,
                "refused": answer.refused,
            },
        )
    except Exception:
        logger.exception("AI Tutor lỗi khi trả lời (session %s)", ctx.session_id)
        if not answer.saved and (tail := answer.finish_filter()):
            yield sse("token", {"text": tail})  # phần đang giữ sẽ được lưu, gửi luôn cho khớp
        yield sse("error", AI_ERROR)
    finally:
        if not answer.saved:
            with anyio.CancelScope(shield=True):
                try:
                    await answer.save(truncated=True)
                except Exception:
                    logger.exception("Không lưu được câu trả lời (session %s)", ctx.session_id)
