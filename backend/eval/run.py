"""Chạy benchmark AI Tutor.

    cd backend
    uv run python -m eval.run --pdf eval/datasets/giai-tich.pdf --dataset eval/datasets/giai-tich.jsonl \\
        --grid "top_k=4,6,8;chunk=500,700" --rpm 12

Dùng DB, provider AI và model trong .env (LLM_PROVIDER=gemini để chạy thật). Kết quả: eval/results/<thời điểm>/
report.md, report.html, results.json. Kết quả từng câu được cache ở eval/results/cache.jsonl: chạy lại chỉ tốn
quota cho câu / cấu hình mới."""

import argparse
import asyncio
from pathlib import Path

from app.ai.embedder import get_embedder
from app.ai.llm import get_llm_provider
from app.ai.llm_client import LLMClient
from app.ai.vision import get_vision
from app.core.config import get_settings
from app.core.db import SessionLocal
from eval.dataset import load_dataset
from eval.report import now_label, write_report
from eval.runner import ResultCache, parse_grid, run_grid

RESULTS = Path(__file__).parent / "results"


async def main(args: argparse.Namespace) -> Path:
    s = get_settings()
    questions = load_dataset(args.dataset)
    configs = parse_grid(args.grid, s.tutor_top_k, s.chunk_max_tokens)
    judge_model = args.judge_model or s.llm_model
    runs = await run_grid(
        pdf=args.pdf,
        questions=questions,
        configs=configs,
        llm=LLMClient(get_llm_provider(s), s),
        embedder=get_embedder(s),
        vision=get_vision(s),
        session_factory=SessionLocal,
        cache=ResultCache(Path(args.cache)),
        llm_model=s.llm_model,
        judge_model=judge_model,
        rpm=args.rpm,
    )
    meta = {
        "date": now_label(),
        "pdf": Path(args.pdf).name,
        "dataset": Path(args.dataset).name,
        "questions": len(questions),
        "llm_model": s.llm_model,
        "judge_model": judge_model,
    }
    threshold = s.tutor_refuse_threshold if args.threshold is None else args.threshold
    report = write_report(runs, threshold, meta, Path(args.out or RESULTS / meta["date"]))
    print(report.read_text(encoding="utf-8"))
    print(f"Đã ghi {report.parent}")
    return report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Benchmark AI Tutor")
    p.add_argument("--pdf", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument(
        "--grid", default="", help='vd. "top_k=4,6,8;chunk=500,700" (bỏ trống = cấu hình hiện tại)'
    )
    p.add_argument(
        "--threshold", type=float, default=None, help="ngưỡng từ chối τ (mặc định TUTOR_REFUSE_THRESHOLD)"
    )
    p.add_argument("--judge-model", default=None, help="model giám khảo (mặc định LLM_MODEL)")
    p.add_argument("--rpm", type=int, default=0, help="giới hạn request/phút của gói AI (0 = không giãn)")
    p.add_argument("--cache", default=str(RESULTS / "cache.jsonl"))
    p.add_argument("--out", default=None)
    return p


if __name__ == "__main__":
    asyncio.run(main(parser().parse_args()))
