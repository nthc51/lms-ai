"""Chạy benchmark: mỗi cấu hình × mỗi câu hỏi → tìm tài liệu, AI trả lời, giám khảo chấm. Có cache trên đĩa.

Cách trả lời giống AI Tutor (tutor/answer.py) nhưng không qua SSE / phiên chat, và LUÔN gọi AI kể cả khi
similarity thấp: chốt chặn theo ngưỡng τ được tính sau (metrics.QuestionResult.refused_at), nhờ vậy một lần
chạy quét được mọi ngưỡng."""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.llm_client import LLMClient, LLMOutputError
from app.ai.prompts import load_prompt
from app.ai.retrieval import RetrievedChunk, retrieve
from app.ai.vision import VisionExtractor
from app.modules.tutor.text import REFUSE_TOKEN, clean_citations, format_context
from eval.corpus import Corpus, prepare_corpus
from eval.dataset import EvalQuestion
from eval.metrics import QuestionResult

logger = logging.getLogger(__name__)
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Config:
    top_k: int
    chunk_max_tokens: int

    @property
    def label(self) -> str:
        return f"top_k={self.top_k}, chunk={self.chunk_max_tokens}"


def parse_grid(spec: str, default_top_k: int, default_chunk: int) -> list[Config]:
    """ "top_k=4,6,8;chunk=500,700" → mọi tổ hợp. Thiếu khóa nào thì dùng giá trị hiện tại trong .env."""
    values = {"top_k": [default_top_k], "chunk": [default_chunk]}
    for part in filter(None, (p.strip() for p in spec.split(";"))):
        key, _, raw = part.partition("=")
        key = key.strip()
        if key not in values or not raw.strip():
            raise ValueError(f"Lưới cấu hình sai ở '{part}' (chỉ nhận top_k=..., chunk=...)")
        values[key] = [int(x) for x in raw.split(",") if x.strip()]
    return [Config(k, c) for c in values["chunk"] for k in values["top_k"]]


class Verdict(BaseModel):
    correct: float = Field(ge=0, le=1)
    faithful: float = Field(ge=0, le=1)
    unsupported: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)


def _is_refusal(text: str) -> bool:
    return text.strip().rstrip(".!").strip() == REFUSE_TOKEN


async def answer_once(
    llm: LLMClient,
    embedder: Embedder,
    session_factory: async_sessionmaker,
    corpus: Corpus,
    q: EvalQuestion,
    cfg: Config,
) -> tuple[QuestionResult, list[RetrievedChunk], str]:
    start = time.perf_counter()
    async with session_factory() as db:
        found = await retrieve(db, embedder, corpus.scope, q.question, top_k=cfg.top_k)
    prompt = load_prompt("tutor_answer").render(
        course_title=corpus.course_title, context=format_context(found.chunks), question=q.question
    )
    res = await llm.generate(prompt, op="eval_answer")
    refused = _is_refusal(res.text)
    content, cited = ("", []) if refused else clean_citations(res.text.strip(), len(found.chunks))
    result = QuestionResult(
        id=q.id,
        type=q.type,
        must_refuse=q.must_refuse,
        gold_pages=q.gold_pages,
        retrieved_pages=[c.page_no for c in found.chunks if c.page_no is not None],
        top_similarity=found.top_similarity,
        llm_refused=refused,
        answer=content,
        cited_pages=[found.chunks[n - 1].page_no for n in cited if found.chunks[n - 1].page_no is not None],
        tokens_in=res.tokens_in,
        tokens_out=res.tokens_out,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )
    return result, found.chunks, content


async def judge(
    llm: LLMClient,
    q: EvalQuestion,
    result: QuestionResult,
    chunks: Sequence[RetrievedChunk],
    judge_model: str,
) -> None:
    """Chấm câu đã trả lời (bỏ qua câu AI từ chối và câu phải từ chối). Lỗi JSON của giám khảo: để trống điểm."""
    if result.llm_refused or q.must_refuse or not result.answer:
        return
    prompt = load_prompt("eval_judge").render(
        question=q.question, gold=q.gold_answer, context=format_context(chunks), answer=result.answer
    )
    try:
        verdict, res = await llm.generate_json(prompt, Verdict, op="eval_judge", model=judge_model)
    except LLMOutputError:
        logger.warning("Giám khảo trả JSON sai cho câu %s", q.id)
        return
    result.correct = verdict.correct
    result.faithful = verdict.faithful
    result.unsupported = verdict.unsupported
    result.citation_checks = [bool(c.get("supports")) for c in verdict.citations]
    result.tokens_in += res.tokens_in
    result.tokens_out += res.tokens_out


def cache_key(corpus: Corpus, q: EvalQuestion, cfg: Config, llm_model: str, judge_model: str) -> str:
    parts = [
        corpus.pdf_sha,
        q.model_dump_json(),
        str(cfg.top_k),
        str(cfg.chunk_max_tokens),
        llm_model,
        judge_model,
        load_prompt("tutor_answer").prompt_version,
        load_prompt("eval_judge").prompt_version,
    ]
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


class ResultCache:
    """Kết quả từng câu (JSONL, chỉ thêm). Đổi prompt / model / câu hỏi thì khóa đổi và câu đó chạy lại."""

    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.items[row["key"]] = row["result"]

    def get(self, key: str) -> QuestionResult | None:
        row = self.items.get(key)
        return QuestionResult(**row) if row is not None else None

    def put(self, key: str, result: QuestionResult) -> None:
        self.items[key] = asdict(result)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "result": asdict(result)}, ensure_ascii=False) + "\n")


async def run_grid(
    *,
    pdf: str | Path,
    questions: Sequence[EvalQuestion],
    configs: Sequence[Config],
    llm: LLMClient,
    embedder: Embedder,
    vision: VisionExtractor,
    session_factory: async_sessionmaker,
    cache: ResultCache,
    llm_model: str,
    judge_model: str,
    rpm: int = 0,
    sleep: Sleep = asyncio.sleep,
    progress: Callable[[str], None] = print,
) -> list[tuple[Config, list[QuestionResult]]]:
    """rpm > 0: giãn các lời gọi AI cho vừa giới hạn request/phút của gói miễn phí (mỗi câu tốn 2 lời gọi)."""
    out = []
    corpora: dict[int, Corpus] = {}
    gap = 120.0 / rpm if rpm > 0 else 0.0
    for cfg in configs:
        if cfg.chunk_max_tokens not in corpora:
            corpora[cfg.chunk_max_tokens] = await prepare_corpus(
                pdf,
                chunk_max_tokens=cfg.chunk_max_tokens,
                embedder=embedder,
                vision=vision,
                session_factory=session_factory,
            )
            progress(
                f"Tài liệu (chunk={cfg.chunk_max_tokens}): {corpora[cfg.chunk_max_tokens].chunk_count} đoạn"
            )
        corpus = corpora[cfg.chunk_max_tokens]
        results = []
        for i, q in enumerate(questions, 1):
            key = cache_key(corpus, q, cfg, llm_model, judge_model)
            cached = cache.get(key)
            if cached is not None:
                results.append(cached)
                continue
            result, chunks, _ = await answer_once(llm, embedder, session_factory, corpus, q, cfg)
            await judge(llm, q, result, chunks, judge_model)
            cache.put(key, result)
            results.append(result)
            progress(f"[{cfg.label}] {i}/{len(questions)} {q.id}")
            if gap:
                await sleep(gap)
        out.append((cfg, results))
    return out
