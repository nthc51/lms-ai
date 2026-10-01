import uuid

import pytest
from pydantic import ValidationError

from app.modules.quiz.models import Difficulty
from app.modules.quiz.selection import (
    MIN_CHUNK_TOKENS,
    ChunkInfo,
    difficulty_sequence,
    plan_questions,
    select_chunks,
)
from app.modules.quiz.validation import DraftQuestion, QuestionContent, validate_draft

MIX = {Difficulty.easy: 0.3, Difficulty.medium: 0.5, Difficulty.hard: 0.2}
OPTIONS = [
    {"id": i, "text": t}
    for i, t in zip("ABCD", ["Mảng đã sắp xếp", "Mảng rỗng", "Có số âm", "Có số lặp"], strict=True)
]


def _q(**changes) -> dict:
    base = {
        "stem": "Tìm kiếm nhị phân cần điều kiện gì?",
        "options": OPTIONS,
        "correct_option_id": "A",
        "explanation": "Vì so sánh với phần tử giữa.",
        "difficulty": "easy",
    }
    return {**base, **changes}


def test_valid_question_is_normalized_to_a_d():
    opts = [
        {"id": x, "text": t} for x, t in zip(["1", "2", "3", "4"], ["Một", "Hai", "Ba", "Bốn"], strict=True)
    ]
    q = QuestionContent.model_validate(_q(options=opts, correct_option_id="3")).normalized()
    assert [o.id for o in q.options] == ["A", "B", "C", "D"]
    assert q.correct_option_id == "C" and q.options[2].text == "Ba" and q.difficulty == Difficulty.easy


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"options": OPTIONS[:3]}, "đúng 4 lựa chọn"),
        ({"options": [*OPTIONS[:3], {"id": "D", "text": " mảng  ĐÃ sắp xếp "}]}, "trùng nhau"),
        ({"options": [*OPTIONS[:3], {"id": "A", "text": "Khác hẳn"}]}, "Mã lựa chọn bị trùng"),
        ({"correct_option_id": "E"}, "một trong 4"),
        ({"stem": "Ngắn?"}, "at least 10"),
        ({"difficulty": "siêu khó"}, "easy"),
        ({"options": [*OPTIONS[:3], {"id": "D", "text": "x" * 301}]}, "at most 300"),
    ],
)
def test_invalid_questions_are_rejected(changes, message):
    with pytest.raises(ValidationError, match=message):
        QuestionContent.model_validate(_q(**changes))


def test_validate_draft_returns_error_text_instead_of_raising():
    ok, err = validate_draft(DraftQuestion.model_validate(_q()))
    assert ok is not None and err is None
    bad, err = validate_draft(DraftQuestion.model_validate(_q(correct_option_id="Z")))
    assert bad is None and "một trong 4" in err


def _chunk(heading: str, i: int = 0, tokens: int = 200) -> ChunkInfo:
    return ChunkInfo(
        id=uuid.uuid4(), content=f"{heading} {i}", heading_path=heading, page_no=1, token_count=tokens
    )


def test_select_skips_short_chunks_and_spreads_over_headings():
    chunks = [_chunk(h, i) for h in "ABCD" for i in range(3)] + [_chunk("E", tokens=MIN_CHUNK_TOKENS - 1)]
    assert [c.heading_path for c in select_chunks(chunks, 4)] == ["A", "C"]  # cần 2 chunk, cách đều nhau
    everything = select_chunks(chunks, 100)
    assert len(everything) == 12 and all(c.token_count >= MIN_CHUNK_TOKENS for c in everything)


def test_select_round_robins_when_more_chunks_than_headings():
    chunks = [_chunk("A", i) for i in range(3)] + [_chunk("B", i) for i in range(3)]
    picked = select_chunks(chunks, 8)  # cần 4 chunk, chỉ có 2 heading
    assert [c.content for c in picked] == ["A 0", "B 0", "A 1", "B 1"]


def test_no_eligible_chunk_gives_empty_plan():
    short = [_chunk("A", tokens=10)]
    assert select_chunks(short, 5) == [] and plan_questions(short, 5, MIX) == []


def test_plan_asks_two_or_three_questions_per_chunk():
    two = [_chunk("A"), _chunk("B")]
    assert [len(p.difficulties) for p in plan_questions(two, 4, MIX)] == [2, 2]
    assert [len(p.difficulties) for p in plan_questions(two, 6, MIX)] == [
        3,
        3,
    ]  # thiếu chunk → 3 câu mỗi chunk


def test_difficulty_sequence_follows_mix():
    seq = difficulty_sequence(10, MIX)
    counts = [seq.count(d) for d in (Difficulty.easy, Difficulty.medium, Difficulty.hard)]
    assert counts == [3, 5, 2] and seq[:3] == [Difficulty.easy, Difficulty.medium, Difficulty.hard]
    assert difficulty_sequence(3, {Difficulty.hard: 1.0}) == [Difficulty.hard] * 3
    assert difficulty_sequence(2, {}) == [Difficulty.medium] * 2


def test_draft_difficulty_is_tolerant_and_schema_is_steered():
    for raw in ("Easy", " HARD "):
        ok, err = validate_draft(DraftQuestion.model_validate(_q(difficulty=raw)))
        assert err is None and ok.difficulty == Difficulty(raw.strip().lower())
    missing = _q()
    del missing["difficulty"], missing["explanation"]
    ok, _ = validate_draft(DraftQuestion.model_validate(missing))
    assert ok.difficulty == Difficulty.medium
    schema = DraftQuestion.model_json_schema()
    assert schema["properties"]["difficulty"]["$ref"] == "#/$defs/Difficulty"
    assert schema["$defs"]["Difficulty"]["enum"] == ["easy", "medium", "hard"]
    assert (
        schema["properties"]["options"]["minItems"] == 4 and schema["properties"]["options"]["maxItems"] == 4
    )
    assert schema["properties"]["stem"]["maxLength"] == 1000
    assert schema["$defs"]["DraftOption"]["properties"]["text"]["maxLength"] == 300
    assert (
        "default" not in schema["properties"]["difficulty"]
        and "default" not in schema["properties"]["explanation"]
    )


def test_nfc_and_nfd_options_are_duplicates():
    import unicodedata

    nfd = unicodedata.normalize("NFD", "Đúng rồi")
    opts = [*OPTIONS[:3], {"id": "D", "text": "Đúng rồi"}]
    opts[0] = {"id": "A", "text": nfd}
    with pytest.raises(ValidationError, match="trùng nhau"):
        QuestionContent.model_validate(_q(options=opts))


def test_validate_draft_error_names_the_field():
    _, err = validate_draft(DraftQuestion.model_validate(_q(stem="Ngắn?")))
    assert err.startswith("stem:")


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 10, 13, 30])
@pytest.mark.parametrize("n_chunks", [1, 2, 3, 5, 20])
@pytest.mark.parametrize("mix", [MIX, {Difficulty.hard: 1.0}, {}])
def test_plan_totals_exactly_n(n, n_chunks, mix):
    chunks = [_chunk(f"H{i}") for i in range(n_chunks)]
    plans = plan_questions(chunks, n, mix)
    flat = [d for p in plans for d in p.difficulties]
    assert len(flat) == n and all(p.difficulties for p in plans)
    expected = difficulty_sequence(n, mix)
    assert sorted(flat, key=str) == sorted(expected, key=str)
    if n_chunks >= n // 2 and n >= 2:
        assert all(2 <= len(p.difficulties) <= 3 for p in plans)


def test_plan_single_question_uses_one_chunk():
    plans = plan_questions([_chunk("A"), _chunk("B")], 1, MIX)
    assert [len(p.difficulties) for p in plans] == [1]


def test_plan_more_questions_than_three_per_chunk_still_totals_n():
    plans = plan_questions([_chunk("A"), _chunk("B")], 10, MIX)
    assert [len(p.difficulties) for p in plans] == [5, 5]
