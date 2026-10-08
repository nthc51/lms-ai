"""Benchmark AI Tutor (eval/): chỉ số, bộ câu hỏi, lưới cấu hình, cache, báo cáo, và chạy trọn với AI giả."""

import json
from pathlib import Path

import pytest

from app.ai.embedder import FakeEmbedder
from app.ai.llm import FakeLLMProvider
from app.ai.vision import FakeVision
from app.core.db import SessionLocal
from eval.dataset import EvalQuestion, load_dataset
from eval.draft import draft
from eval.metrics import QuestionResult, percentile, recall_at_k, summarize, threshold_sweep
from eval.report import best_config, to_markdown, write_report
from eval.runner import Config, ResultCache, parse_grid, run_grid
from tests.pdfs import make_pdf
from tests.test_studio import _llm

# Không dấu: PDF sinh trong test (tests/pdfs.py) không nhúng font tiếng Việt. Embedder giả bỏ dấu khi so khớp,
# nên câu hỏi có dấu vẫn tìm đúng trang. Mỗi trang ~180 token: với chunk=200 mỗi trang là một đoạn riêng.
SAMPLE_PAGES = [
    "Tim kiem nhi phan tim mot gia tri trong mang da sap xep bang cach chia doi khoang tim. " * 7,
    "Do phuc tap thoi gian cua tim kiem nhi phan la O(log n) vi moi buoc loai bo mot nua so phan tu. " * 7,
    "Sap xep noi bot lap lai viec hoan doi hai phan tu ke nhau neu chung dung sai thu tu. " * 7,
]
DATASET = Path(__file__).parents[1] / "eval" / "datasets" / "sample.jsonl"


def _r(**kw) -> QuestionResult:
    base = {
        "id": "q",
        "type": "single",
        "must_refuse": False,
        "gold_pages": [1],
        "retrieved_pages": [1, 2],
        "top_similarity": 0.8,
        "llm_refused": False,
        "answer": "a [1]",
        "cited_pages": [1],
        "tokens_in": 100,
        "tokens_out": 20,
        "latency_ms": 1000,
    }
    return QuestionResult(**{**base, **kw})


# ---------- hàm thuần ----------


def test_recall_and_percentile():
    assert recall_at_k([3, 1, 2], [1], k=2) == 1.0
    assert recall_at_k([3, 1, 2], [2], k=2) == 0.0
    assert recall_at_k([1, 2], [1, 5], k=6) == 0.5  # câu multi: thiếu một trang
    assert recall_at_k([], [], k=3) == 1.0
    assert (
        percentile([10, 20, 30, 40], 50) == 20
        and percentile([10, 20, 30, 40], 95) == 40
        and percentile([], 50) == 0
    )


def test_refusal_threshold_applies_after_the_fact():
    weak = _r(top_similarity=0.2)
    assert weak.refused_at(0.3) and not weak.refused_at(0.1)
    assert _r(llm_refused=True).refused_at(0.0) and _r(top_similarity=None).refused_at(0.0)


def test_summary_and_threshold_sweep():
    results = [
        _r(id="a", correct=1, faithful=1, citation_checks=[True, True]),
        _r(
            id="b", correct=0.5, faithful=1, citation_checks=[False], retrieved_pages=[4], top_similarity=0.25
        ),
        _r(id="c", type="refuse", must_refuse=True, gold_pages=[], top_similarity=0.2, answer="bịa"),
        _r(
            id="d",
            type="refuse",
            must_refuse=True,
            gold_pages=[],
            top_similarity=0.5,
            llm_refused=True,
            answer="",
        ),
    ]
    s = summarize(results, k=6, threshold=0.3)
    # b bị chốt chặn ở τ=0.3 (0.25 < 0.3): không tính vào Đúng / Bám tài liệu
    assert (s.correct, s.faithful, s.citation_precision) == (1.0, 1.0, 1.0)
    assert (s.recall_at_k, s.refusal_recall, s.false_refusal) == (0.5, 1.0, 0.5)
    assert s.tokens_per_question == 120 and s.by_type["refuse"]["n"] == 2
    sweep = {row["threshold"]: row for row in threshold_sweep(results, [0.1, 0.22, 0.3])}
    assert sweep[0.1] == {"threshold": 0.1, "refusal_recall": 0.5, "false_refusal": 0.0, "score": 0.5}
    assert sweep[0.22]["score"] == 1.0  # chặn c (0.2) mà không chặn b (0.25)
    assert sweep[0.3]["false_refusal"] == 0.5


def test_dataset_validation(tmp_path):
    assert [q.id for q in load_dataset(DATASET)] == ["s1", "s2", "s3", "s4"]
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"id": "x", "type": "refuse", "question": "Hỏi gì?", "must_refuse": false}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="bad.jsonl:1"):
        load_dataset(bad)
    dup = tmp_path / "dup.jsonl"
    line = json.dumps({"id": "x", "type": "single", "question": "Hỏi gì?", "gold_pages": [1]})
    dup.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="trùng id x"):
        load_dataset(dup)
    with pytest.raises(ValueError):
        EvalQuestion(id="y", type="single", question="Không có trang?")


def test_parse_grid():
    assert parse_grid("", 6, 700) == [Config(6, 700)]
    assert parse_grid("top_k=4,8;chunk=500", 6, 700) == [Config(4, 500), Config(8, 500)]
    with pytest.raises(ValueError, match="Lưới cấu hình sai"):
        parse_grid("topk=4", 6, 700)


def test_report_marks_best_config_and_threshold(tmp_path):
    good = [_r(correct=1, faithful=1), _r(type="refuse", must_refuse=True, gold_pages=[], top_similarity=0.1)]
    cheap_bad = [
        _r(correct=0, faithful=0.5, tokens_in=10),
        _r(type="refuse", must_refuse=True, gold_pages=[]),
    ]
    runs = [(Config(4, 500), cheap_bad), (Config(6, 700), good)]
    meta = {
        "date": "x",
        "pdf": "a.pdf",
        "dataset": "a.jsonl",
        "questions": 2,
        "llm_model": "m",
        "judge_model": "j",
    }
    md = to_markdown(runs, 0.3, meta)
    assert "| top_k=6, chunk=700 **(tốt nhất)** |" in md and "**(đề xuất)**" in md
    out = write_report(runs, 0.3, meta, tmp_path / "r")
    html = (tmp_path / "r" / "report.html").read_text(encoding="utf-8")
    assert out.name == "report.md" and "<svg" in html and "top_k=6, chunk=700" in html
    assert (
        json.loads((tmp_path / "r" / "results.json").read_text(encoding="utf-8"))["runs"][0]["config"][
            "top_k"
        ]
        == 4
    )
    assert best_config([(c, __import__("eval.metrics").metrics.summarize(r, c.top_k, 0.3)) for c, r in runs])[
        0
    ] == Config(6, 700)


# ---------- chạy trọn với AI giả ----------


async def test_run_grid_end_to_end_with_cache(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(make_pdf(SAMPLE_PAGES))
    questions = load_dataset(DATASET)
    provider = FakeLLMProvider(reply_for=lambda c: _fake(c))
    kwargs = {
        "pdf": pdf,
        "questions": questions,
        "configs": [Config(2, 200)],
        "llm": _llm(provider),
        "embedder": FakeEmbedder(768),
        "vision": FakeVision(),
        "session_factory": SessionLocal,
        "llm_model": "fake",
        "judge_model": "fake-judge",
        "progress": lambda _m: None,
    }
    runs = await run_grid(cache=ResultCache(tmp_path / "cache.jsonl"), **kwargs)
    ((cfg, results),) = runs
    by_id = {r.id: r for r in results}
    assert by_id["s1"].retrieved_pages[0] == 1 and by_id["s2"].retrieved_pages[0] == 2
    assert (
        by_id["s4"].llm_refused is True and by_id["s4"].correct is None
    )  # câu ngoài tài liệu: AI từ chối, không chấm
    assert by_id["s1"].correct == 1 and by_id["s1"].citation_checks == [True]
    judge_calls = [c for c in provider.calls if c.op == "eval_judge"]
    assert len(judge_calls) == 3 and {c.model for c in judge_calls} == {"fake-judge"}
    s = summarize(results, cfg.top_k, threshold=0.0)
    assert s.recall_at_k == 1.0 and s.refusal_recall == 1.0
    # chạy lại: lấy từ cache, không gọi AI nữa; và không xử lý lại tài liệu
    before = len(provider.calls)
    again = await run_grid(cache=ResultCache(tmp_path / "cache.jsonl"), **kwargs)
    assert len(provider.calls) == before and [r.id for r in again[0][1]] == ["s1", "s2", "s3", "s4"]


def _fake(call) -> str:
    """AI giả cho benchmark: trả lời trích [1], từ chối câu về nước Pháp."""
    from app.ai.llm import default_reply

    if call.op == "eval_answer":
        return "REFUSE" if "Pháp" in call.prompt.split("<question>")[-1] else "Theo tài liệu [1]."
    return default_reply(call)


async def test_draft_writes_reviewable_jsonl(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(make_pdf(SAMPLE_PAGES))
    out = tmp_path / "draft.jsonl"
    n = await draft(str(pdf), out, max_questions=4, per_chunk=2, llm=_llm())
    lines = out.read_text(encoding="utf-8").splitlines()
    assert n >= 2 and lines[0].startswith("// NHÁP")
    assert load_dataset(out)[0].gold_pages == [1]
