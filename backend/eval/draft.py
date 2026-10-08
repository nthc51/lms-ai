"""Soạn NHÁP bộ câu hỏi benchmark từ tài liệu: AI đề xuất câu hỏi + đáp án + trang, người DUYỆT lại.

    uv run python -m eval.draft --pdf eval/datasets/giai-tich.pdf --out eval/datasets/giai-tich.jsonl --max 60

Sau đó mở file: sửa / xóa câu kém, kiểm tra gold_pages, thêm ~15 câu "multi" (ghép nhiều đoạn) và ~15 câu
"refuse" (ngoài tài liệu) bằng tay. Dòng bắt đầu bằng // được bỏ qua khi chạy benchmark."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.embedder import get_embedder
from app.ai.llm import get_llm_provider
from app.ai.llm_client import LLMClient, LLMOutputError
from app.ai.prompts import load_prompt
from app.ai.vision import get_vision
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.studio.generation import load_scope_chunks
from eval.corpus import prepare_corpus

HEADER = (
    "// NHÁP do AI soạn: DUYỆT từng câu (sửa gold_answer, gold_pages), xóa câu kém, "
    'thêm câu "multi" và câu "refuse" (must_refuse: true, gold_pages: []) bằng tay.'
)


class _Draft(BaseModel):
    type: Literal["single", "paraphrase"] = "single"
    question: str = Field(min_length=3, max_length=1000)
    gold_answer: str = ""


class _Batch(BaseModel):
    questions: list[_Draft]


async def draft(
    pdf: str, out: Path, max_questions: int, per_chunk: int, llm: LLMClient, session_factory=SessionLocal
) -> int:
    s = get_settings()
    corpus = await prepare_corpus(
        pdf,
        chunk_max_tokens=s.chunk_max_tokens,
        embedder=get_embedder(s),
        vision=get_vision(s),
        session_factory=session_factory,
    )
    async with session_factory() as db:
        chunks = [
            c
            for c in await load_scope_chunks(db, corpus.scope.course_id, corpus.scope.lesson_id)
            if c.page_no is not None
        ]
    # rải đều trên cả tài liệu thay vì chỉ lấy các trang đầu
    wanted = max(1, max_questions // per_chunk)
    step = max(1, len(chunks) // wanted)
    picked = chunks[::step][:wanted]
    template = load_prompt("eval_draft")
    lines, n = [HEADER], 0
    for c in picked:
        try:
            batch, _ = await llm.generate_json(
                template.render(count=per_chunk, source=c.content), _Batch, op="eval_draft"
            )
        except LLMOutputError:
            continue
        for q in batch.questions[:per_chunk]:
            n += 1
            item = {
                "id": f"q{n:03d}",
                "type": q.type,
                "question": q.question.strip(),
                "gold_pages": [c.page_no],
                "gold_answer": q.gold_answer.strip(),
                "must_refuse": False,
            }
            lines.append(json.dumps(item, ensure_ascii=False))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n


def main() -> None:
    p = argparse.ArgumentParser(description="Soạn nháp bộ câu hỏi benchmark")
    p.add_argument("--pdf", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max", type=int, default=60)
    p.add_argument("--per-chunk", type=int, default=2)
    a = p.parse_args()
    s = get_settings()
    n = asyncio.run(draft(a.pdf, Path(a.out), a.max, a.per_chunk, LLMClient(get_llm_provider(s), s)))
    print(f"Đã soạn {n} câu nháp vào {a.out}. Nhớ DUYỆT trước khi chạy benchmark.")


if __name__ == "__main__":
    main()
