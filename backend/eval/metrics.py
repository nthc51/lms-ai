"""Chỉ số benchmark: hàm thuần, không gọi DB hay AI (để test kỹ và tính lại từ cache)."""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class QuestionResult:
    """Kết quả của một câu hỏi dưới một cấu hình (lưu vào cache dạng JSON)."""

    id: str
    type: str
    must_refuse: bool
    gold_pages: list[int]
    retrieved_pages: list[int]  # trang của các đoạn tìm được, theo thứ hạng
    top_similarity: float | None
    llm_refused: bool  # AI trả REFUSE (benchmark luôn gọi AI, chốt chặn ngưỡng τ tính sau bằng refused_at)
    answer: str
    cited_pages: list[int]
    tokens_in: int
    tokens_out: int
    latency_ms: int
    correct: float | None = None  # giám khảo (None: không chấm, vd. câu từ chối)
    faithful: float | None = None
    citation_checks: list[bool] = field(default_factory=list)  # mỗi [n]: đoạn có thật sự chứa ý đó không
    unsupported: list[str] = field(default_factory=list)

    def refused_at(self, threshold: float) -> bool:
        """Có bị từ chối với ngưỡng τ không: chốt chặn trước AI (similarity cao nhất < τ) hoặc AI tự từ chối.
        Viết `not (x >= τ)` giống should_refuse để None cũng bị từ chối."""
        gate = self.top_similarity is None or not (self.top_similarity >= threshold)
        return gate or self.llm_refused


def recall_at_k(retrieved_pages: Sequence[int], gold_pages: Sequence[int], k: int) -> float:
    """Tỉ lệ trang đáp án nằm trong k đoạn đầu (câu multi cần đủ nhiều trang)."""
    if not gold_pages:
        return 1.0
    top = set(retrieved_pages[:k])
    return sum(1 for p in set(gold_pages) if p in top) / len(set(gold_pages))


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, math.ceil(p / 100 * len(s)) - 1)
    return float(s[idx])


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


@dataclass
class Summary:
    n: int
    recall_at_k: float | None  # trung bình trên câu không phải refuse
    correct: float | None  # trung bình điểm giám khảo trên câu được trả lời (không từ chối)
    faithful: float | None
    citation_precision: float | None  # tỉ lệ [n] trỏ đúng đoạn
    refusal_recall: float | None  # câu phải từ chối: tỉ lệ đã từ chối
    false_refusal: float | None  # câu thường: tỉ lệ bị từ chối nhầm
    tokens_per_question: float
    latency_p50_ms: float
    latency_p95_ms: float
    by_type: dict[str, dict[str, float | None]]


def summarize(results: Sequence[QuestionResult], k: int, threshold: float) -> Summary:
    normal = [r for r in results if not r.must_refuse]
    refuse = [r for r in results if r.must_refuse]
    answered = [r for r in normal if not r.refused_at(threshold)]
    checks = [c for r in answered for c in r.citation_checks]
    by_type: dict[str, dict[str, float | None]] = {}
    for t in sorted({r.type for r in results}):
        rs = [r for r in results if r.type == t]
        ans = [r for r in rs if not r.refused_at(threshold) and not r.must_refuse]
        by_type[t] = {
            "n": len(rs),
            "recall_at_k": _mean(
                [recall_at_k(r.retrieved_pages, r.gold_pages, k) for r in rs if not r.must_refuse]
            ),
            "correct": _mean([r.correct for r in ans if r.correct is not None]),
            "refused": _mean([1.0 if r.refused_at(threshold) else 0.0 for r in rs]),
        }
    return Summary(
        n=len(results),
        recall_at_k=_mean([recall_at_k(r.retrieved_pages, r.gold_pages, k) for r in normal]),
        correct=_mean([r.correct for r in answered if r.correct is not None]),
        faithful=_mean([r.faithful for r in answered if r.faithful is not None]),
        citation_precision=_mean([1.0 if c else 0.0 for c in checks]),
        refusal_recall=_mean([1.0 if r.refused_at(threshold) else 0.0 for r in refuse]),
        false_refusal=_mean([1.0 if r.refused_at(threshold) else 0.0 for r in normal]),
        tokens_per_question=round(sum(r.tokens_in + r.tokens_out for r in results) / len(results), 1)
        if results
        else 0.0,
        latency_p50_ms=percentile([r.latency_ms for r in results], 50),
        latency_p95_ms=percentile([r.latency_ms for r in results], 95),
        by_type=by_type,
    )


def threshold_sweep(results: Sequence[QuestionResult], thresholds: Sequence[float]) -> list[dict[str, float]]:
    """Tỉ lệ từ chối đúng / từ chối nhầm theo từng ngưỡng τ, tính lại từ similarity đã đo (không gọi AI).
    score = từ chối đúng − từ chối nhầm: chọn τ có score cao nhất."""
    refuse = [r for r in results if r.must_refuse]
    normal = [r for r in results if not r.must_refuse]
    rows = []
    for t in thresholds:
        rr = sum(r.refused_at(t) for r in refuse) / len(refuse) if refuse else 1.0
        fr = sum(r.refused_at(t) for r in normal) / len(normal) if normal else 0.0
        rows.append(
            {
                "threshold": t,
                "refusal_recall": round(rr, 4),
                "false_refusal": round(fr, 4),
                "score": round(rr - fr, 4),
            }
        )
    return rows
