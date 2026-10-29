"""Đánh giá AI gợi ý chấm bài (B5, spec 9.4): so điểm AI với điểm người chấm trên một bộ bài có sẵn điểm.

    cd backend
    uv run python -m eval.grading --dataset eval/datasets/grading-sample.jsonl --rpm 12

Mỗi dòng của dataset (JSONL) là một bài:
    {"id": "b01", "title": "...", "instructions": "...",
     "rubric": [{"criterion": "...", "max_points": 6, "description": "..."}, ...],
     "submission": "bài làm", "human_scores": [5, 3],
     "pair": "p1", "injected": false}            # tùy chọn: cặp bài sạch / có câu "lừa" AI
Chỉ số:
- MAE từng tiêu chí và MAE trung bình (điểm AI so với người chấm).
- Tương quan Spearman của tổng điểm.
- Tỉ lệ bài có tổng điểm lệch không quá 1 điểm.
- Injection: với mỗi cặp (cùng `pair`, một bài injected=true), độ lệch tổng điểm giữa hai bản; kỳ vọng gần 0.
Dùng provider AI và model trong .env (LLM_PROVIDER=gemini / openrouter để chạy thật). Kết quả ghi ở
eval/results/grading-<thời điểm>.md và .json."""

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from app.ai.llm import get_llm_provider
from app.ai.llm_client import LLMClient
from app.core.config import get_settings
from app.modules.assignment.grading import ai_grade
from eval.report import now_label

RESULTS = Path(__file__).parent / "results"


@dataclass
class GradedItem:
    id: str
    max_points: list[int]
    human: list[float]
    ai: list[float] | None  # None: AI lỗi
    pair: str | None = None
    injected: bool = False

    @property
    def human_total(self) -> float:
        return sum(self.human)

    @property
    def ai_total(self) -> float | None:
        return None if self.ai is None else sum(self.ai)


def _ranks(values: Sequence[float]) -> list[float]:
    """Hạng (bắt đầu từ 1), giá trị bằng nhau nhận hạng trung bình."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Tương quan Spearman (Pearson trên hạng). Ít hơn 3 cặp hoặc một bên không đổi → None."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return round(cov / (vx * vy) ** 0.5, 4)


def summarize(items: Sequence[GradedItem]) -> dict:
    ok = [it for it in items if it.ai is not None and not it.injected]
    n_crit = max((len(it.human) for it in ok), default=0)
    mae_by_criterion = []
    for c in range(n_crit):
        diffs = [abs(it.ai[c] - it.human[c]) for it in ok if c < len(it.human)]
        mae_by_criterion.append(round(sum(diffs) / len(diffs), 3) if diffs else None)
    all_diffs = [abs(a - h) for it in ok for a, h in zip(it.ai, it.human, strict=True)]
    totals = [(it.ai_total, it.human_total) for it in ok]
    pairs: dict[str, dict[bool, GradedItem]] = {}
    for it in items:
        if it.pair and it.ai is not None:
            pairs.setdefault(it.pair, {})[it.injected] = it
    injection = {
        p: round(abs(v[True].ai_total - v[False].ai_total), 2)
        for p, v in sorted(pairs.items())
        if len(v) == 2
    }
    return {
        "items": len(items),
        "ai_failed": sum(1 for it in items if it.ai is None),
        "mae_by_criterion": mae_by_criterion,
        "mae": round(sum(all_diffs) / len(all_diffs), 3) if all_diffs else None,
        "spearman_total": spearman([a for a, _ in totals], [h for _, h in totals]),
        "within_1_point": round(sum(1 for a, h in totals if abs(a - h) <= 1) / len(totals), 3)
        if totals
        else None,
        "injection_gap": injection,
        "injection_gap_mean": round(sum(injection.values()) / len(injection), 2) if injection else None,
    }


def load(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if len(row["human_scores"]) != len(row["rubric"]):
            raise ValueError(f"{row['id']}: human_scores phải có đúng {len(row['rubric'])} điểm")
    return rows


async def grade_all(llm: LLMClient, rows: list[dict], rpm: int) -> list[GradedItem]:
    out = []
    for row in rows:
        rubric = [{"key": f"c{i}", **r} for i, r in enumerate(row["rubric"], start=1)]
        try:
            result, _, _ = await ai_grade(llm, row["title"], row["instructions"], rubric, row["submission"])
            ai = [result["scores"][r["key"]]["score"] for r in rubric]
        except Exception as e:  # noqa: BLE001 — một bài lỗi không làm hỏng cả lượt đánh giá
            print(f"{row['id']}: AI lỗi ({e})")
            ai = None
        out.append(
            GradedItem(
                id=row["id"],
                max_points=[r["max_points"] for r in rubric],
                human=[float(x) for x in row["human_scores"]],
                ai=ai,
                pair=row.get("pair"),
                injected=bool(row.get("injected")),
            )
        )
        if rpm > 0:
            await asyncio.sleep(60 / rpm)  # gói miễn phí giới hạn số lời gọi mỗi phút
    return out


def report(summary: dict, items: list[GradedItem], model: str) -> str:
    lines = [
        "# Đánh giá AI gợi ý chấm bài",
        "",
        f"- Model: `{model}`; số bài: {summary['items']}; AI lỗi: {summary['ai_failed']}",
        f"- MAE trung bình mỗi tiêu chí: {summary['mae']}; theo tiêu chí: {summary['mae_by_criterion']}",
        f"- Spearman tổng điểm: {summary['spearman_total']}",
        f"- Tỉ lệ bài lệch tổng ≤ 1 điểm: {summary['within_1_point']}",
        f"- Injection: lệch trung bình {summary['injection_gap_mean']} điểm; từng cặp {summary['injection_gap']}",
        "",
        "| Bài | Người chấm | AI | Lệch |",
        "|---|---|---|---|",
    ]
    for it in items:
        ai = "lỗi" if it.ai_total is None else f"{it.ai_total:g}"
        gap = "" if it.ai_total is None else f"{abs(it.ai_total - it.human_total):g}"
        lines.append(
            f"| {it.id}{' (injection)' if it.injected else ''} | {it.human_total:g} | {ai} | {gap} |"
        )
    return "\n".join(lines) + "\n"


async def main(args: argparse.Namespace) -> Path:
    s = get_settings()
    rows = load(Path(args.dataset))
    items = await grade_all(LLMClient(get_llm_provider(s), s), rows, args.rpm)
    summary = summarize(items)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"grading-{now_label()}"
    out.with_suffix(".md").write_text(report(summary, items, s.llm_model), encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "items": [asdict(it) for it in items]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return out.with_suffix(".md")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", required=True)
    p.add_argument("--rpm", type=int, default=0, help="số lời gọi AI tối đa mỗi phút (0 = không giới hạn)")
    return p


if __name__ == "__main__":
    print(asyncio.run(main(parser().parse_args())))
