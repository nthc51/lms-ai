import asyncio
import json
from contextlib import asynccontextmanager

import anyio
from sqlalchemy import select

from app.ai.embedder import FakeEmbedder
from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.ai.retrieval import SearchScope
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.ingestion.chunker import count_tokens
from app.modules.auth.models import Role
from app.modules.tutor.answer import AskContext, answer_stream
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from app.modules.tutor.text import REFUSAL_MESSAGE
from tests.factories import BINARY_SEARCH, make_lesson, make_user, seed_chunks
from tests.test_ai_retry import Sleeps

HISTORY = [(ChatRole.user, "Tìm kiếm nhị phân là gì?"), (ChatRole.assistant, "Là thuật toán [1].")]
TEST_TIMEOUT_S = 15  # mọi test chờ stream đều có giới hạn: hồi quy thì hỏng chứ không treo


def parse(event: str) -> tuple[str, dict]:
    head, data = event.strip().split("\n")
    return head.removeprefix("event: "), json.loads(data.removeprefix("data: "))


async def never_disconnected() -> bool:
    return False


async def _setup(db):
    teacher = await make_user(db)
    student = await make_user(db, Role.student)
    course, lesson = await make_lesson(db, teacher)
    await seed_chunks(db, lesson.id, [BINARY_SEARCH])
    session = ChatSession(user_id=student.id, course_id=course.id, lesson_id=lesson.id)
    db.add(session)
    await db.commit()
    return course, lesson, session


def _ctx(course, lesson, session, question="Tìm kiếm nhị phân là gì?", history=()):
    return AskContext(
        session_id=session.id,
        scope=SearchScope(course.id, lesson.id),
        course_title=course.title,
        question=question,
        history=list(history),
    )


async def _run(
    ctx, provider, *, is_disconnected=never_disconnected, session_factory=SessionLocal, **settings_kw
):
    s = get_settings().model_copy(update=settings_kw)
    llm = LLMClient(provider, s, sleep=Sleeps())
    stream = answer_stream(
        ctx,
        llm=llm,
        embedder=FakeEmbedder(768),
        is_disconnected=is_disconnected,
        session_factory=session_factory,
        settings=s,
    )
    async with asyncio.timeout(TEST_TIMEOUT_S):
        return [parse(e) async for e in stream]


async def _assistant(db, session) -> ChatMessage:
    return await db.scalar(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id, ChatMessage.role == ChatRole.assistant)
        .execution_options(populate_existing=True)
    )


def _tokens(events) -> str:
    return "".join(d["text"] for e, d in events if e == "token")


async def test_streams_sources_tokens_done_and_saves_answer(db):
    course, lesson, session = await _setup(db)
    provider = FakeLLMProvider(["Tìm kiếm nhị phân chia đôi mảng đã sắp xếp [1] và [7]."])
    events = await _run(_ctx(course, lesson, session), provider)
    names = [e for e, _ in events]
    assert names[0] == "sources" and names[-1] == "done" and set(names[1:-1]) == {"token"}
    [src] = events[0][1]["sources"]
    assert src["n"] == 1 and src["lesson_id"] == str(lesson.id) and src["page_no"] == 1
    assert _tokens(events) == "Tìm kiếm nhị phân chia đôi mảng đã sắp xếp [1] và [7]."
    done = events[-1][1]
    assert (
        done["content"] == "Tìm kiếm nhị phân chia đôi mảng đã sắp xếp [1] và ." and done["refused"] is False
    )
    assert [c["n"] for c in done["citations"]] == [1]
    msg = await _assistant(db, session)
    assert str(msg.id) == done["message_id"] and msg.content == done["content"]
    assert msg.citations == done["citations"] and msg.truncated is False and msg.refused is False
    assert msg.prompt_version == "tutor_answer@v1" and msg.tokens_in > 0 and msg.tokens_out > 0
    assert msg.ttft_ms is not None and msg.latency_ms >= msg.ttft_ms
    assert [c.op for c in provider.calls] == ["tutor_answer"]  # không có lịch sử → không viết lại câu hỏi
    assert "[1] (Bài: Bài 1 · trang 1)" in provider.calls[0].prompt


async def test_low_similarity_is_refused_before_calling_llm(db):
    course, lesson, session = await _setup(db)
    provider = FakeLLMProvider()
    ctx = _ctx(course, lesson, session, question="Thời tiết Hà Nội hôm nay")
    events = await _run(ctx, provider, tutor_refuse_threshold=0.3)
    assert provider.calls == []
    assert events[1] == ("token", {"text": REFUSAL_MESSAGE})
    assert events[-1][1]["refused"] is True and events[-1][1]["citations"] == []
    msg = await _assistant(db, session)
    assert msg.refused is True and msg.content == REFUSAL_MESSAGE and msg.prompt_version is None
    assert msg.truncated is False


async def test_llm_refuse_token_is_hidden_and_marked_refused(db):
    course, lesson, session = await _setup(db)
    events = await _run(_ctx(course, lesson, session), FakeLLMProvider(["REFUSE"]))
    assert _tokens(events) == REFUSAL_MESSAGE and events[-1][1]["refused"] is True
    assert (await _assistant(db, session)).refused is True


async def test_follow_up_question_is_rewritten_with_cheap_model(db):
    course, lesson, session = await _setup(db)
    provider = FakeLLMProvider(["Tìm kiếm nhị phân hoạt động thế nào?", "Nó chia đôi mảng [1]."])
    ctx = _ctx(course, lesson, session, question="Nó hoạt động thế nào?", history=HISTORY)
    events = await _run(ctx, provider, llm_cheap_model="re-model")
    assert events[-1][0] == "done"
    rewrite, answer_call = provider.calls
    assert rewrite.op == "tutor_rewrite" and rewrite.model == "re-model"
    assert (
        "Học viên: Tìm kiếm nhị phân là gì?" in rewrite.prompt and "Nó hoạt động thế nào?" in rewrite.prompt
    )
    assert "Tìm kiếm nhị phân hoạt động thế nào?" in answer_call.prompt
    msg = await _assistant(db, session)
    assert msg.tokens_in > count_tokens(answer_call.prompt)  # cộng cả token của lời gọi viết lại


async def test_rewrite_failure_falls_back_to_original_question(db):
    course, lesson, session = await _setup(db)
    provider = FakeLLMProvider([ValueError("hỏng"), "Trả lời [1]."])
    ctx = _ctx(course, lesson, session, question="Nó hoạt động thế nào?", history=HISTORY)
    events = await _run(ctx, provider, tutor_refuse_threshold=0.0)
    assert events[-1][0] == "done"
    assert "Nó hoạt động thế nào?" in provider.calls[1].prompt


class HangingRewrite(FakeLLMProvider):
    """Lời gọi viết lại treo mãi (mỗi lần thử vẫn trong timeout riêng của nó): chỉ hạn chót tổng cứu được."""

    async def generate(self, prompt, *, op, model, timeout_s, json_schema=None):
        if op == "tutor_rewrite":
            await asyncio.Event().wait()
        return await super().generate(
            prompt, op=op, model=model, timeout_s=timeout_s, json_schema=json_schema
        )


async def test_slow_rewrite_hits_deadline_and_falls_back_to_original_question(db):
    course, lesson, session = await _setup(db)
    provider = HangingRewrite(["Trả lời [1]."])
    ctx = _ctx(course, lesson, session, question="Nó hoạt động thế nào?", history=HISTORY)
    events = await _run(ctx, provider, tutor_refuse_threshold=0.0, tutor_rewrite_deadline_s=0.05)
    assert events[-1][0] == "done"
    [answer_call] = provider.calls  # lời gọi viết lại bị hủy trước khi FakeLLMProvider ghi nhận
    assert answer_call.op == "tutor_answer" and "Nó hoạt động thế nào?" in answer_call.prompt


class HangingOpen(FakeLLMProvider):
    async def open_stream(self, prompt, *, op, model, timeout_s):
        await asyncio.Event().wait()


async def test_hanging_stream_open_hits_prestream_deadline_and_sends_error(db):
    course, lesson, session = await _setup(db)
    events = await _run(_ctx(course, lesson, session), HangingOpen(), tutor_prestream_deadline_s=0.2)
    assert [e for e, _ in events] == ["sources", "error"] and events[-1][1]["code"] == "AI_UNAVAILABLE"
    msg = await _assistant(db, session)
    assert msg.truncated is True and msg.content == ""


async def test_provider_cut_off_is_saved_as_truncated(db):
    course, lesson, session = await _setup(db)
    provider = FakeLLMProvider(["Tìm kiếm nhị phân chia [1]"], finish_reason="MAX_TOKENS")
    events = await _run(_ctx(course, lesson, session), provider)
    assert events[-1][0] == "done"
    msg = await _assistant(db, session)
    assert msg.truncated is True and msg.content == "Tìm kiếm nhị phân chia [1]"


async def test_client_disconnect_stops_stream_and_saves_partial_answer(db):
    course, lesson, session = await _setup(db)
    checks = []

    async def disconnected() -> bool:
        checks.append(1)
        return True

    provider = FakeLLMProvider([" ".join(f"từ{i}" for i in range(30))])
    events = await _run(_ctx(course, lesson, session), provider, is_disconnected=disconnected)
    assert "done" not in [e for e, _ in events] and len(checks) == 1
    msg = await _assistant(db, session)
    assert msg.truncated is True and msg.content == " ".join(f"từ{i}" for i in range(10))
    assert msg.tokens_out == count_tokens(msg.content)
    assert provider.streams[0].closed


async def test_cancelled_stream_still_saves_partial_answer(db):
    course, lesson, session = await _setup(db)
    provider = FakeLLMProvider(
        ["Mảnh đầu rồi treo mãi"], stream_gate=asyncio.Event()
    )  # gate không bao giờ set
    s = get_settings().model_copy()
    llm = LLMClient(provider, s, sleep=Sleeps())
    got_token = anyio.Event()

    async def consume():
        stream = answer_stream(
            _ctx(course, lesson, session),
            llm=llm,
            embedder=FakeEmbedder(768),
            is_disconnected=never_disconnected,
            settings=s,
        )
        async for e in stream:
            if parse(e)[0] == "token":
                got_token.set()

    with anyio.fail_after(TEST_TIMEOUT_S):
        async with anyio.create_task_group() as tg:  # giống Starlette hủy task stream khi client ngắt
            tg.start_soon(consume)
            await got_token.wait()
            tg.cancel_scope.cancel()
    msg = await _assistant(db, session)
    assert msg.truncated is True and msg.content == "Mảnh"
    assert provider.streams[0].closed


async def test_llm_errors_send_error_event_and_keep_partial_answer(db):
    course, lesson, session = await _setup(db)
    events = await _run(_ctx(course, lesson, session), FakeLLMProvider([ValueError("hết quota")]))
    assert [e for e, _ in events] == ["sources", "error"]
    assert events[-1][1]["code"] == "AI_UNAVAILABLE"
    msg = await _assistant(db, session)
    assert msg.truncated is True and msg.content == ""

    course2, lesson2, session2 = await _setup(db)
    broken = FakeLLMProvider(["một hai ba"], stream_error=(2, TimeoutError()))  # lỗi giữa chừng: không retry
    events = await _run(_ctx(course2, lesson2, session2), broken)
    assert [e for e, _ in events] == ["sources", "token", "token", "error"]
    msg = await _assistant(db, session2)
    assert msg.truncated is True and msg.content == "một hai"


async def test_refuse_filter_is_finished_when_stream_breaks(db):
    # Stream hỏng khi RefuseFilter còn giữ "REFUSE": lưu là câu từ chối, học viên không thấy token REFUSE
    course, lesson, session = await _setup(db)
    events = await _run(
        _ctx(course, lesson, session), FakeLLMProvider(["REFUSE nữa"], stream_error=(1, TimeoutError()))
    )
    assert [e for e, _ in events] == ["sources", "error"]
    msg = await _assistant(db, session)
    assert msg.refused is True and msg.content == REFUSAL_MESSAGE and msg.truncated is True

    # Phần đầu đang bị giữ ("REF" có thể là REFUSE) được nhả ra rồi mới lưu
    course2, lesson2, session2 = await _setup(db)
    events = await _run(
        _ctx(course2, lesson2, session2), FakeLLMProvider(["REF nữa"], stream_error=(1, TimeoutError()))
    )
    assert [e for e, _ in events] == ["sources", "token", "error"] and _tokens(events) == "REF"
    msg = await _assistant(db, session2)
    assert msg.refused is False and msg.content == "REF" and msg.truncated is True


class TrackingFactory:
    """session_factory đếm số session DB đang mở, để kiểm tra không giữ connection trong lúc gọi LLM."""

    def __init__(self):
        self.open = 0

    @asynccontextmanager
    async def _session(self):
        self.open += 1
        try:
            async with SessionLocal() as db:
                yield db
        finally:
            self.open -= 1

    def __call__(self):
        return self._session()


async def test_no_db_session_is_held_during_llm_calls(db):
    course, lesson, session = await _setup(db)
    factory = TrackingFactory()
    open_at_call = []

    def reply(text):
        def f(call):
            open_at_call.append((call.op, factory.open))
            return text

        return f

    provider = FakeLLMProvider([reply("Tìm kiếm nhị phân là gì?"), reply("Nó chia đôi [1].")])
    ctx = _ctx(course, lesson, session, question="Nó là gì?", history=HISTORY)
    events = await _run(ctx, provider, session_factory=factory)
    assert events[-1][0] == "done"
    assert open_at_call == [("tutor_rewrite", 0), ("tutor_answer", 0)]
    assert factory.open == 0


async def test_answer_is_saved_after_the_already_committed_question(db):
    # Caller (Task 11 prepare_question) commit câu hỏi trước; câu trả lời ghi trong transaction riêng sau đó
    course, lesson, session = await _setup(db)
    question = ChatMessage(session_id=session.id, role=ChatRole.user, content="Tìm kiếm nhị phân là gì?")
    db.add(question)
    await db.commit()
    await _run(_ctx(course, lesson, session), FakeLLMProvider())
    msg = await _assistant(db, session)
    assert msg.created_at > question.created_at


async def test_cancel_while_refuse_is_held_saves_refusal(db):
    # Bị hủy lúc RefuseFilter đang giữ "REFUSE" (chưa có token nào ra client): save() vẫn chốt filter
    course, lesson, session = await _setup(db)
    provider = FakeLLMProvider(["REFUSE rồi treo"], stream_gate=asyncio.Event())  # treo trước mảnh thứ hai
    s = get_settings().model_copy()
    llm = LLMClient(provider, s, sleep=Sleeps())
    got_sources = anyio.Event()

    async def consume():
        stream = answer_stream(
            _ctx(course, lesson, session),
            llm=llm,
            embedder=FakeEmbedder(768),
            is_disconnected=never_disconnected,
            settings=s,
        )
        async for e in stream:
            assert parse(e)[0] == "sources"
            got_sources.set()

    with anyio.fail_after(TEST_TIMEOUT_S):
        async with anyio.create_task_group() as tg:
            tg.start_soon(consume)
            await got_sources.wait()
            while not provider.streams:
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.1)  # mảnh "REFUSE" được đọc, stream dừng ở gate
            tg.cancel_scope.cancel()
    msg = await _assistant(db, session)
    assert msg.refused is True and msg.content == REFUSAL_MESSAGE and msg.truncated is True
