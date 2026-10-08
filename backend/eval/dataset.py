"""Bộ câu hỏi benchmark: file JSONL, mỗi dòng một câu.

{"id": "q017", "type": "single", "question": "...", "gold_pages": [5], "gold_answer": "...", "must_refuse": false}

type: single (đáp án trong một đoạn), multi (phải ghép 2–3 đoạn), paraphrase (hỏi bằng từ khác tài liệu),
refuse (ngoài tài liệu: AI phải từ chối; gold_pages rỗng, must_refuse = true)."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EvalQuestion(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    type: Literal["single", "multi", "paraphrase", "refuse"]
    question: str = Field(min_length=3, max_length=1000)
    gold_pages: list[int] = Field(default_factory=list)
    gold_answer: str = ""
    must_refuse: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> "EvalQuestion":
        if self.type == "refuse" and not self.must_refuse:
            raise ValueError("type=refuse thì must_refuse phải là true")
        if self.must_refuse and self.gold_pages:
            raise ValueError("câu phải từ chối không có gold_pages")
        if not self.must_refuse and not self.gold_pages:
            raise ValueError("câu thường cần gold_pages (trang chứa đáp án)")
        return self


def load_dataset(path: str | Path) -> list[EvalQuestion]:
    """Đọc JSONL; báo lỗi kèm số dòng. Bỏ dòng trống và dòng bắt đầu bằng //."""
    out: list[EvalQuestion] = []
    seen: set[str] = set()
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            q = EvalQuestion.model_validate(json.loads(line))
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(f"{path}:{i}: {e}") from None
        if q.id in seen:
            raise ValueError(f"{path}:{i}: trùng id {q.id}")
        seen.add(q.id)
        out.append(q)
    if not out:
        raise ValueError(f"{path}: không có câu hỏi nào")
    return out
