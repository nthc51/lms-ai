"""Xuất kết quả benchmark: report.md (dán vào báo cáo) và report.html (bảng + biểu đồ chất lượng – token)."""

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from eval.metrics import QuestionResult, Summary, summarize, threshold_sweep
from eval.runner import Config

THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 13)]  # 0.05 … 0.60


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _rows(
    runs: Sequence[tuple[Config, list[QuestionResult]]], threshold: float
) -> list[tuple[Config, Summary]]:
    return [(cfg, summarize(results, cfg.top_k, threshold)) for cfg, results in runs]


def best_config(rows: Sequence[tuple[Config, Summary]]) -> tuple[Config, Summary]:
    """Cấu hình tốt nhất: điểm Đúng × Bám tài liệu cao nhất; bằng nhau thì ít token hơn."""
    return max(rows, key=lambda r: ((r[1].correct or 0) * (r[1].faithful or 0), -r[1].tokens_per_question))


def to_markdown(runs, threshold: float, meta: dict) -> str:
    rows = _rows(runs, threshold)
    best_cfg, _ = best_config(rows)
    lines = [
        f"# Kết quả benchmark AI Tutor ({meta['date']})",
        "",
        f"- Tài liệu: `{meta['pdf']}` · Bộ câu hỏi: `{meta['dataset']}` ({meta['questions']} câu)",
        f"- Model trả lời: `{meta['llm_model']}` · Giám khảo: `{meta['judge_model']}` · Ngưỡng từ chối τ = {threshold}",
        "",
        "| Cấu hình | Recall@k | Đúng | Bám tài liệu | Trích nguồn đúng | Từ chối đúng | Từ chối nhầm | Token/câu | p50 / p95 (ms) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cfg, s in rows:
        mark = " **(tốt nhất)**" if cfg == best_cfg else ""
        lines.append(
            f"| {cfg.label}{mark} | {_pct(s.recall_at_k)} | {_pct(s.correct)} | {_pct(s.faithful)} | "
            f"{_pct(s.citation_precision)} | {_pct(s.refusal_recall)} | {_pct(s.false_refusal)} | "
            f"{s.tokens_per_question:.0f} | {s.latency_p50_ms:.0f} / {s.latency_p95_ms:.0f} |"
        )
    sweep = threshold_sweep(next(r for c, r in runs if c == best_cfg), THRESHOLDS)
    best_t = max(sweep, key=lambda r: (r["score"], -r["threshold"]))
    lines += [
        "",
        f"## Quét ngưỡng từ chối (cấu hình {best_cfg.label})",
        "",
        "| τ | Từ chối đúng | Từ chối nhầm | Điểm |",
        "|---|---|---|---|",
        *[
            f"| {r['threshold']:.2f}{' **(đề xuất)**' if r is best_t else ''} | {_pct(r['refusal_recall'])} | "
            f"{_pct(r['false_refusal'])} | {r['score']:.2f} |"
            for r in sweep
        ],
        "",
        (
            "Đúng / Bám tài liệu / Trích nguồn đúng do AI giám khảo chấm (0 / 0.5 / 1) trên các câu được trả lời. "
            "Recall@k: trang chứa đáp án nằm trong k đoạn tìm được. Điểm ngưỡng = từ chối đúng − từ chối nhầm."
        ),
    ]
    return "\n".join(lines) + "\n"


def _scatter(rows: Sequence[tuple[Config, Summary]]) -> str:
    """Một chuỗi điểm: mỗi cấu hình một chấm (trục x token/câu, trục y điểm Đúng), nhãn trực tiếp, hover có số."""
    w, h, pad_l, pad_b, pad_t, pad_r = 640, 320, 56, 40, 16, 24
    xs = [s.tokens_per_question for _, s in rows] or [0]
    x_max = max(xs) * 1.15 or 1
    sx = lambda x: pad_l + x / x_max * (w - pad_l - pad_r)
    sy = lambda y: h - pad_b - y * (h - pad_b - pad_t)
    grid = "".join(
        f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" class="grid"/>'
        f'<text x="{pad_l - 8}" y="{sy(v) + 4:.1f}" class="tick" text-anchor="end">{int(v * 100)}%</text>'
        for v in (0, 0.25, 0.5, 0.75, 1)
    )
    dots = "".join(
        f'<g><circle cx="{sx(s.tokens_per_question):.1f}" cy="{sy(s.correct or 0):.1f}" r="5" class="dot"/>'
        f'<circle cx="{sx(s.tokens_per_question):.1f}" cy="{sy(s.correct or 0):.1f}" r="14" class="hit">'
        f"<title>{escape(cfg.label)}: đúng {_pct(s.correct)}, {s.tokens_per_question:.0f} token/câu</title></circle>"
        f'<text x="{sx(s.tokens_per_question) + 9:.1f}" y="{sy(s.correct or 0) - 8:.1f}" class="label">'
        f"{escape(cfg.label)}</text></g>"
        for cfg, s in rows
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Điểm đúng theo số token mỗi câu của từng cấu hình">'
        f"{grid}"
        f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{sy(0):.1f}" y2="{sy(0):.1f}" class="axis"/>'
        f'<text x="{(w + pad_l) / 2:.0f}" y="{h - 6}" class="tick" text-anchor="middle">Token mỗi câu (càng ít càng rẻ)</text>'
        f"{dots}</svg>"
    )


def to_html(markdown_table_rows: Sequence[tuple[Config, Summary]], md: str) -> str:
    table_rows = "".join(
        f"<tr><td>{escape(c.label)}</td><td>{_pct(s.recall_at_k)}</td><td>{_pct(s.correct)}</td>"
        f"<td>{_pct(s.faithful)}</td><td>{_pct(s.citation_precision)}</td><td>{_pct(s.refusal_recall)}</td>"
        f"<td>{_pct(s.false_refusal)}</td><td>{s.tokens_per_question:.0f}</td></tr>"
        for c, s in markdown_table_rows
    )
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Benchmark AI Tutor</title><style>
:root{{--bg:#ffffff;--fg:#1a1a19;--muted:#5f5e5a;--grid:#e8e6df;--mark:#2a6fdb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1a1a19;--fg:#f1efe8;--muted:#b4b2a9;--grid:#3a3936;--mark:#6ea0f0}}}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:960px;margin:24px auto;padding:0 16px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border-bottom:1px solid var(--grid);padding:6px 8px;text-align:right}}
th:first-child,td:first-child{{text-align:left}}.grid{{stroke:var(--grid)}}.axis{{stroke:var(--muted)}}
.tick,.label{{fill:var(--muted);font-size:12px}}.dot{{fill:var(--mark);stroke:var(--bg);stroke-width:2}}.hit{{fill:transparent}}
.wrap{{overflow-x:auto}}pre{{white-space:pre-wrap;color:var(--muted)}}
</style></head><body>
<h1>Benchmark AI Tutor</h1>
<h2>Chất lượng và chi phí</h2>{_scatter(markdown_table_rows)}
<div class="wrap"><table><thead><tr><th>Cấu hình</th><th>Recall@k</th><th>Đúng</th><th>Bám tài liệu</th><th>Trích nguồn đúng</th>
<th>Từ chối đúng</th><th>Từ chối nhầm</th><th>Token/câu</th></tr></thead><tbody>{table_rows}</tbody></table></div>
<h2>Báo cáo đầy đủ (Markdown)</h2><pre>{escape(md)}</pre></body></html>"""


def write_report(runs, threshold: float, meta: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = to_markdown(runs, threshold, meta)
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    (out_dir / "report.html").write_text(to_html(_rows(runs, threshold), md), encoding="utf-8")
    raw = {
        "meta": meta,
        "threshold": threshold,
        "runs": [{"config": asdict(c), "results": [asdict(r) for r in rs]} for c, rs in runs],
    }
    (out_dir / "results.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    return out_dir / "report.md"


def now_label() -> str:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y%m%d-%H%M")
