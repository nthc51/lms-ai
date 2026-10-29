"""Chỉ số đánh giá AI chấm bài (eval/grading.py): MAE, Spearman, lệch ≤ 1 điểm, độ lệch của cặp injection."""

from pathlib import Path

import pytest

from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.core.config import get_settings
from eval.grading import GradedItem, grade_all, load, spearman, summarize
from tests.test_ai_retry import Sleeps


def test_spearman_handles_ties_and_degenerate_input():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert spearman([1, 2, 2, 3], [1, 2, 2, 3]) == 1.0
    assert spearman([1, 2], [1, 2]) is None and spearman([1, 1, 1], [1, 2, 3]) is None


def test_summarize_metrics_and_injection_gap():
    items = [
        GradedItem("a", [6, 4], human=[6, 4], ai=[5, 4], pair="p1"),
        GradedItem("b", [6, 4], human=[2, 1], ai=[2, 0]),
        GradedItem("c", [6, 4], human=[4, 2], ai=[1, 2]),
        GradedItem("a-inj", [6, 4], human=[6, 4], ai=[6, 4], pair="p1", injected=True),
        GradedItem("d", [6, 4], human=[3, 3], ai=None),
    ]
    s = summarize(items)
    assert (s["items"], s["ai_failed"]) == (5, 1)
    assert s["mae_by_criterion"] == [round(4 / 3, 3), round(1 / 3, 3)] and s["mae"] == round(5 / 6, 3)
    assert s["within_1_point"] == round(2 / 3, 3)
    assert s["spearman_total"] == 1.0
    assert s["injection_gap"] == {"p1": 1.0} and s["injection_gap_mean"] == 1.0


async def test_sample_dataset_runs_with_fake_provider():
    rows = load(Path("eval/datasets/grading-sample.jsonl"))
    llm = LLMClient(FakeLLMProvider(), get_settings(), sleep=Sleeps())
    items = await grade_all(llm, rows, rpm=0)
    assert [it.ai for it in items] == [[3.0, 2.0]] * 3  # bản giả cho nửa điểm mỗi tiêu chí
    assert summarize(items)["injection_gap"] == {"p2": 0.0}


def test_dataset_must_have_one_score_per_criterion(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x", "rubric": [{"criterion": "a", "max_points": 2}], "human_scores": [1, 1]}\n')
    with pytest.raises(ValueError, match="human_scores"):
        load(bad)
