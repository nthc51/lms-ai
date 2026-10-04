import json

import pytest
from sqlalchemy import select

from app.ai.embedder import FakeEmbedder
from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.core.config import get_settings
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_job
from app.modules.materials.models import SourceStatus
from app.modules.quiz.generation import (
    ALL_DUPLICATES_ERROR,
    NO_CHUNKS_ERROR,
    NO_QUESTIONS_ERROR,
    generate_questions_for_lesson,
    load_lesson_chunks,
)
from app.modules.quiz.models import Difficulty, Question, QuestionOrigin, ReviewStatus
from tests.factories import LONG_LESSON_TEXT, make_lesson, make_question, make_user, seed_chunks
from tests.test_ai_retry import Sleeps

MIX = {Difficulty.easy: 0.3, Difficulty.medium: 0.5, Difficulty.hard: 0.2}
S1 = "Tìm kiếm nhị phân yêu cầu mảng như thế nào?"
S2 = "Mỗi bước thuật toán loại bỏ bao nhiêu phần của khoảng?"
S3 = "Độ phức tạp thời gian của phương pháp này là gì?"
S4 = "Khi nào thuật toán dừng lại và trả về kết quả?"
CHECK_A = '{"answer_option_id": "A"}'


def q(stem, correct="A", texts=("Một", "Hai", "Ba", "Bốn")) -> dict:
    return {
        "stem": stem,
        "options": [{"id": i, "text": t} for i, t in zip("ABCD", texts, strict=True)],
        "correct_option_id": correct,
        "explanation": "Giải thích dựa trên tài liệu.",
        "difficulty": "easy",
    }


def batch(*questions) -> str:
    return json.dumps({"questions": list(questions)}, ensure_ascii=False)


async def _lesson(db, contents=(LONG_LESSON_TEXT,)):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    chunks = await seed_chunks(db, lesson.id, list(contents))
    return lesson, chunks


async def _generate(lesson, provider, count=2, **kw):
    llm = LLMClient(provider, get_settings(), sleep=Sleeps())
    return await generate_questions_for_lesson(
        lesson.id, count=count, mix=MIX, llm=llm, embedder=FakeEmbedder(768), **kw
    )


async def _questions(db, lesson) -> list[Question]:
    return list((await db.scalars(select(Question).where(Question.lesson_id == lesson.id))).all())


async def test_saves_pending_questions_with_ai_original_and_prompt_version(db):
    lesson, [chunk] = await _lesson(db)
    provider = FakeLLMProvider([batch(q(S1), q(S2)), CHECK_A, CHECK_A])
    stats = await _generate(lesson, provider)
    assert (stats.saved, stats.flagged, stats.invalid, stats.duplicates) == (2, 0, 0, 0)
    gen = provider.calls[0]
    assert gen.op == "quiz_generate" and "Số câu cần sinh: 2" in gen.prompt
    assert "Độ khó lần lượt: easy, medium" in gen.prompt and LONG_LESSON_TEXT.strip() in gen.prompt
    rows = await _questions(db, lesson)
    assert {r.stem for r in rows} == {S1, S2}
    for r in rows:
        assert r.review_status == ReviewStatus.pending and r.origin == QuestionOrigin.ai
        assert r.source_chunk_id == chunk.id and r.prompt_version == "quiz_generate@v2"
        assert r.ai_original["stem"] == r.stem and r.ai_original["correct_option_id"] == "A"
        assert [o["id"] for o in r.options] == ["A", "B", "C", "D"] and r.self_check_flag is False


async def test_short_chunks_are_skipped_and_no_chunk_is_an_error(db):
    lesson, _ = await _lesson(db, ["Đoạn ngắn không đủ dài.", LONG_LESSON_TEXT])
    provider = FakeLLMProvider([batch(q(S1), q(S2)), CHECK_A, CHECK_A])
    await _generate(lesson, provider)
    assert "Đoạn ngắn" not in provider.calls[0].prompt
    only_short, _ = await _lesson(db, ["Đoạn ngắn không đủ dài."])
    with pytest.raises(ValueError, match=NO_CHUNKS_ERROR):
        await _generate(only_short, FakeLLMProvider())


async def test_invalid_question_is_regenerated_once(db):
    lesson, _ = await _lesson(db)
    three_options = {**q(S2), "options": q(S2)["options"][:3]}
    provider = FakeLLMProvider([batch(q(S1), three_options), batch(q(S3)), CHECK_A, CHECK_A])
    stats = await _generate(lesson, provider)
    assert (stats.saved, stats.invalid) == (2, 0)
    retry_prompt = provider.calls[1].prompt
    assert "không hợp lệ" in retry_prompt and "Số câu cần sinh: 1" in retry_prompt
    assert {r.stem for r in await _questions(db, lesson)} == {S1, S3}


async def test_question_still_invalid_after_retry_is_dropped(db):
    lesson, _ = await _lesson(db)
    bad = q(S2, correct="E")
    stats = await _generate(lesson, FakeLLMProvider([batch(q(S1), bad), batch(bad), CHECK_A]))
    assert (stats.saved, stats.invalid) == (1, 1)


async def test_malformed_json_twice_means_no_questions(db):
    lesson, _ = await _lesson(db)
    with pytest.raises(ValueError, match=NO_QUESTIONS_ERROR):
        await _generate(lesson, FakeLLMProvider(["không phải JSON", '{"questions": "sai"}']))


async def test_near_duplicates_are_dropped(db):
    lesson, _ = await _lesson(db)
    await make_question(db, lesson.id, stem=S1)
    near_s1 = "Tìm kiếm nhị phân yêu cầu mảng như thế nào vậy?"
    stats = await _generate(lesson, FakeLLMProvider([batch(q(near_s1), q(S2)), CHECK_A]))
    assert (stats.saved, stats.duplicates) == (1, 1)
    assert {r.stem for r in await _questions(db, lesson)} == {S1, S2}


async def test_self_check_disagreement_or_failure_sets_flag(db):
    lesson, _ = await _lesson(db)
    provider = FakeLLMProvider(
        [batch(q(S1), q(S2), q(S3)), '{"answer_option_id": "B"}', CHECK_A, ValueError("hỏng")]
    )
    stats = await _generate(lesson, provider, count=3)  # 1 chunk, count 3 > 2 → 3 câu cho chunk đó
    flags = {r.stem: r.self_check_flag for r in await _questions(db, lesson)}
    assert flags == {S1: True, S2: False, S3: True} and stats.flagged == 2
    assert [c.op for c in provider.calls[1:]] == ["quiz_self_check"] * 3


async def test_questions_are_saved_with_job_done_or_dropped_if_job_was_swept(db):
    lesson, _ = await _lesson(db)
    job, _ = await create_job(db, "quiz_gen", lesson.id, created_by=None)
    job.status = JobStatus.processing
    await db.commit()
    await _generate(lesson, FakeLLMProvider([batch(q(S1), q(S2)), CHECK_A, CHECK_A]), job_id=job.id)
    assert (await db.get(Job, job.id, populate_existing=True)).status == JobStatus.done
    assert len(await _questions(db, lesson)) == 2

    swept, _ = await create_job(db, "quiz_gen", lesson.id, created_by=None)
    swept.status = JobStatus.failed  # sweeper đã chốt job này
    await db.commit()
    provider = FakeLLMProvider([batch(q(S3), q(S4)), CHECK_A, CHECK_A])
    stats = await _generate(lesson, provider, job_id=swept.id)
    assert stats.saved == 0 and len(await _questions(db, lesson)) == 2


class RecordingLLM(LLMClient):
    """Ghi lại use_cache của từng lời gọi generate_json theo op."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.use_cache: list[tuple[str, bool]] = []

    async def generate_json(self, prompt, schema, *, op, use_cache=True, **kw):
        self.use_cache.append((op, use_cache))
        return await super().generate_json(prompt, schema, op=op, use_cache=use_cache, **kw)


async def test_generation_bypasses_cache_but_self_check_may_use_it(db):
    lesson, _ = await _lesson(db)
    llm = RecordingLLM(
        FakeLLMProvider([batch(q(S1), q(S2)), CHECK_A, CHECK_A]), get_settings(), sleep=Sleeps()
    )
    await generate_questions_for_lesson(lesson.id, count=2, mix=MIX, llm=llm, embedder=FakeEmbedder(768))
    assert llm.use_cache == [("quiz_generate", False), ("quiz_self_check", True), ("quiz_self_check", True)]


async def test_malformed_batch_skips_only_that_chunk(db):
    other = LONG_LESSON_TEXT.replace("Tìm kiếm nhị phân", "Sắp xếp nổi bọt")
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    await seed_chunks(db, lesson.id, [LONG_LESSON_TEXT, other], heading_paths=["Mục 1", "Mục 2"])
    provider = FakeLLMProvider(
        ["không phải JSON", '{"questions": "sai"}', batch(q(S3), q(S4)), CHECK_A, CHECK_A]
    )
    stats = await _generate(lesson, provider, count=4)
    assert (stats.saved, stats.invalid) == (2, 2)
    assert "Sắp xếp nổi bọt" in provider.calls[2].prompt
    assert {r.stem for r in await _questions(db, lesson)} == {S3, S4}


async def test_never_keeps_more_than_requested(db):
    lesson, _ = await _lesson(db)
    stats = await _generate(lesson, FakeLLMProvider([batch(q(S1), q(S2), q(S3)), CHECK_A, CHECK_A]))
    assert stats.saved == 2 and {r.stem for r in await _questions(db, lesson)} == {S1, S2}


async def test_dedup_includes_rejected_questions_and_new_ones(db):
    lesson, _ = await _lesson(db)
    await make_question(db, lesson.id, stem=S1, review_status=ReviewStatus.rejected)
    stats = await _generate(lesson, FakeLLMProvider([batch(q(S1), q(S2), q(S2)), CHECK_A]), count=3)
    assert (stats.saved, stats.duplicates) == (1, 2)


async def test_load_lesson_chunks_is_ordered_and_ready_only(db):
    lesson, chunks = await _lesson(db, [LONG_LESSON_TEXT, "Trang hai " * 200, "Trang ba " * 200])
    await seed_chunks(db, lesson.id, ["Nguồn lỗi " * 200], status=SourceStatus.failed)
    loaded = await load_lesson_chunks(db, lesson.id)
    assert [c.id for c in loaded] == [c.id for c in chunks]
    assert [c.page_no for c in loaded] == [1, 2, 3]


async def test_retry_requests_the_failed_slots_difficulty_and_saved_keeps_plan(db):
    lesson, _ = await _lesson(db)  # kế hoạch 2 câu: slot 1 easy, slot 2 medium
    bad_first = q(S1, correct="E")
    provider = FakeLLMProvider([batch(bad_first, q(S2)), batch(q(S3)), CHECK_A, CHECK_A])
    stats = await _generate(lesson, provider)
    retry_prompt = provider.calls[1].prompt
    assert "Số câu cần sinh: 1" in retry_prompt and "Độ khó lần lượt: easy\n" in retry_prompt
    rows = {r.stem: r for r in await _questions(db, lesson)}
    assert rows[S2].difficulty == Difficulty.medium and rows[S3].difficulty == Difficulty.easy
    assert rows[S2].ai_original["difficulty"] == "easy"  # ai_original giữ đúng output của model
    assert stats.difficulty_mismatches == 1


async def test_saved_difficulties_follow_plan_when_model_ignores_it(db):
    lesson, _ = await _lesson(db)
    stems = [f"Khái niệm từ{i}a từ{i}b từ{i}c từ{i}d có nghĩa là gì?" for i in range(10)]
    drafts = [{**q(s), "difficulty": "medium"} for s in stems]
    provider = FakeLLMProvider([batch(*drafts)] + [CHECK_A] * 10)
    stats = await _generate(lesson, provider, count=10)
    counts = {d: 0 for d in Difficulty}
    for r in await _questions(db, lesson):
        counts[r.difficulty] += 1
    assert counts == {Difficulty.easy: 3, Difficulty.medium: 5, Difficulty.hard: 2}
    assert (stats.saved, stats.difficulty_mismatches) == (10, 5)


async def test_all_duplicates_has_a_distinct_error(db):
    lesson, _ = await _lesson(db)
    await make_question(db, lesson.id, stem=S1)
    await make_question(db, lesson.id, stem=S2)
    with pytest.raises(ValueError, match=ALL_DUPLICATES_ERROR):
        await _generate(lesson, FakeLLMProvider([batch(q(S1), q(S2))]))


async def test_regenerating_same_lesson_uses_unused_chunks_and_avoid_list(db):
    other = (
        "Sắp xếp nổi bọt duyệt danh sách nhiều lượt. Ở mỗi lượt, hai phần tử kề nhau bị đổi chỗ khi đứng sai "
        "thứ tự, nên phần tử lớn nhất dần nổi lên cuối dãy. Độ phức tạp trung bình bằng bình phương kích thước. "
    ) * 4
    lesson, chunks = await _lesson(db, [LONG_LESSON_TEXT, other])
    first = FakeLLMProvider()  # trả lời mặc định: câu hỏi phụ thuộc đoạn nguồn trong prompt
    assert (await _generate(lesson, first)).saved == 2
    assert "Không lặp lại" not in first.calls[0].prompt
    saved_stems = {r.stem for r in await _questions(db, lesson)}
    assert {r.source_chunk_id for r in await _questions(db, lesson)} == {chunks[0].id}

    second = FakeLLMProvider()
    stats = await _generate(lesson, second)  # temperature vẫn 0, nhưng chunk và prompt khác
    assert stats.saved == 2 and stats.duplicates == 0
    gen = next(c for c in second.calls if c.op == "quiz_generate")
    assert "Sắp xếp nổi bọt" in gen.prompt and "Không lặp lại các câu sau" in gen.prompt
    assert all(f"- {s}" in gen.prompt for s in saved_stems)
    rows = await _questions(db, lesson)
    assert len(rows) == 4 and {r.source_chunk_id for r in rows} == {chunks[0].id, chunks[1].id}


async def test_avoid_list_is_capped_and_prefers_the_chunk_own_questions(db):
    lesson, [chunk] = await _lesson(db)
    # câu của chính chunk được tạo trước (cũ nhất) nhưng vẫn đứng đầu danh sách
    await make_question(db, lesson.id, stem="Câu của chính chunk này là gì vậy?", source_chunk_id=chunk.id)
    for i in range(25):
        await make_question(db, lesson.id, stem=f"Câu đã có số {i} về chủ đề riêng {i}?")
    provider = FakeLLMProvider([batch(q(S1), q(S2)), CHECK_A, CHECK_A])
    await _generate(lesson, provider)
    prompt = provider.calls[0].prompt
    listed = [line for line in prompt.splitlines() if line.startswith("- Câu")]
    assert len(listed) == 20 and listed[0] == "- Câu của chính chunk này là gì vậy?"
