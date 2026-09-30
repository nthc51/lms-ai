import asyncio
import logging

import pytest
from sqlalchemy import select

from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.ai.models import LLMCache
from app.ai.prompts import RenderedPrompt
from app.core.config import get_settings
from app.ingestion.chunker import count_tokens
from tests.test_ai_retry import Sleeps, api_error

PROMPT = RenderedPrompt("tutor_answer", "v1", "Ngữ cảnh ... Câu hỏi: tìm kiếm nhị phân?")


def settings(**kw):
    return get_settings().model_copy(update={"llm_cache_enabled": True, **kw})


async def cache_rows(db):
    return (await db.scalars(select(LLMCache))).all()


async def test_stream_yields_pieces_and_reports_usage():
    llm = FakeLLMProvider(["Tìm kiếm nhị phân [1]."])
    client = LLMClient(llm, settings(llm_cache_enabled=False), sleep=Sleeps())
    async with client.stream(PROMPT, op="tutor_answer") as s:
        pieces = [p async for p in s]
    assert "".join(pieces) == "Tìm kiếm nhị phân [1]." == s.text
    assert s.completed and s.cached is False and s.truncated is False
    assert s.tokens_out == count_tokens(s.text) and s.tokens_in == count_tokens(PROMPT.text)
    assert llm.calls[0].stream and llm.calls[0].timeout_s == get_settings().llm_stream_timeout_s
    assert llm.streams[0].closed


async def test_break_early_is_not_completed_estimates_tokens_and_is_not_cached(db):
    llm = FakeLLMProvider(["một hai ba bốn năm"])
    client = LLMClient(llm, settings(), sleep=Sleeps())
    async with client.stream(PROMPT, op="tutor_answer") as s:
        async for _ in s:
            break
    assert not s.completed and s.truncated and s.text == "một" and s.tokens_out == count_tokens("một")
    assert llm.streams[0].closed
    assert await cache_rows(db) == []


async def test_completed_stream_is_cached_and_replayed(db):
    llm = FakeLLMProvider(["câu trả lời đầy đủ"])
    client = LLMClient(llm, settings(), sleep=Sleeps())
    async with client.stream(PROMPT, op="tutor_answer") as first:
        _ = [p async for p in first]
    async with client.stream(PROMPT, op="tutor_answer") as second:
        replay = [p async for p in second]
    assert "".join(replay) == "câu trả lời đầy đủ" and second.cached and second.completed
    assert second.truncated is False
    assert len(replay) > 1  # phát lại dạng stream, không phải một cục
    assert (second.tokens_in, second.tokens_out) == (0, 0)
    assert len(llm.calls) == 1


async def test_open_is_retried_but_mid_stream_error_is_not():
    sleeps = Sleeps()
    llm = FakeLLMProvider([api_error(503), "a b c"], stream_error=(1, TimeoutError()))
    client = LLMClient(llm, settings(llm_cache_enabled=False), sleep=sleeps)
    with pytest.raises(TimeoutError):
        async with client.stream(PROMPT, op="tutor_answer") as s:
            async for _ in s:
                pass
    assert sleeps.delays == [1.0] and len(llm.calls) == 2
    assert s.text == "a" and not s.completed and llm.streams[0].closed


async def test_consumer_error_closes_upstream_and_is_not_cached(db):
    llm = FakeLLMProvider(["x y z"])
    client = LLMClient(llm, settings(), sleep=Sleeps())
    with pytest.raises(RuntimeError):
        async with client.stream(PROMPT, op="tutor_answer") as s:
            _ = [p async for p in s]  # đọc hết rồi mới lỗi: vẫn không cache
            raise RuntimeError("ghi SSE hỏng")
    assert s.completed and llm.streams[0].closed
    assert await cache_rows(db) == []


async def test_cancelled_consumer_closes_upstream_and_is_not_cached(db, caplog):
    gate = asyncio.Event()
    llm = FakeLLMProvider(["một hai ba"], stream_gate=gate)
    client = LLMClient(llm, settings(), sleep=Sleeps())
    got: list[str] = []

    streams = []

    async def consume():
        async with client.stream(PROMPT, op="tutor_answer") as s:
            streams.append(s)
            async for p in s:
                got.append(p)

    with caplog.at_level(logging.INFO, logger="app.ai"):
        task = asyncio.create_task(consume())
        async with asyncio.timeout(5):
            while not got and not task.done():
                await asyncio.sleep(0)
        assert not task.done(), task.exception()
        task.cancel()  # client ngắt kết nối
        with pytest.raises(asyncio.CancelledError):
            await task
    assert got == ["một"] and llm.streams[0].closed and streams[0].truncated
    assert await cache_rows(db) == []
    line = next(m for m in caplog.messages if m.startswith("llm_call"))
    assert "status=cancelled" in line and "cached=False" in line


@pytest.mark.parametrize("reply", ["", "   "])
async def test_empty_stream_is_not_cached(db, reply):
    llm = FakeLLMProvider([reply])
    client = LLMClient(llm, settings(), sleep=Sleeps())
    async with client.stream(PROMPT, op="tutor_answer") as s:
        _ = [p async for p in s]
    assert s.completed and llm.streams[0].closed
    assert await cache_rows(db) == []


async def test_stream_cut_by_provider_is_not_cached(db, caplog):
    llm = FakeLLMProvider(["câu trả lời bị cắt"], finish_reason="MAX_TOKENS")
    client = LLMClient(llm, settings(), sleep=Sleeps())
    with caplog.at_level(logging.INFO, logger="app.ai"):
        async with client.stream(PROMPT, op="tutor_answer") as s:
            _ = [p async for p in s]
    assert s.completed and s.finish_reason == "MAX_TOKENS" and s.truncated  # chưa sinh xong
    assert await cache_rows(db) == []
    line = next(m for m in caplog.messages if m.startswith("llm_call"))
    assert "status=incomplete" in line and "finish_reason=MAX_TOKENS" in line


async def test_stream_without_finish_reason_is_cached_when_it_ends_normally(db):
    llm = FakeLLMProvider(["đầy đủ"], finish_reason=None)
    client = LLMClient(llm, settings(), sleep=Sleeps())
    async with client.stream(PROMPT, op="tutor_answer") as s:
        _ = [p async for p in s]
    assert [r.response for r in await cache_rows(db)] == ["đầy đủ"]


async def test_stalled_stream_hits_total_timeout_and_is_not_retried(db):
    llm = FakeLLMProvider(["một hai ba"], stream_gate=asyncio.Event())  # treo trước mảnh thứ hai
    client = LLMClient(llm, settings(), sleep=Sleeps())
    # gate không bao giờ được set: chặn ngoài 5 giây để lỗi ở logic deadline làm test HỎNG thay vì treo
    # (timeout ngoài ném CancelledError qua pytest.raises nên không bị nhầm là TimeoutError mong đợi)
    async with asyncio.timeout(5):
        with pytest.raises(TimeoutError):
            async with client.stream(PROMPT, op="tutor_answer", timeout_s=0.05) as s:
                async for _ in s:
                    pass
    assert s.text == "một" and not s.completed and s.truncated
    assert len(llm.calls) == 1 and llm.streams[0].closed
    assert await cache_rows(db) == []


class HangOnceOpen(FakeLLMProvider):
    """Lần mở đầu treo lâu hơn timeout (SDK chỉ có timeout theo từng thao tác mạng)."""

    def __init__(self):
        super().__init__(["xin chào"])
        self.opens = 0

    async def open_stream(self, prompt, *, op, model, timeout_s):
        self.opens += 1
        if self.opens == 1:
            await asyncio.sleep(10)
        return await super().open_stream(prompt, op=op, model=model, timeout_s=timeout_s)


async def test_hanging_open_times_out_and_is_retried():
    sleeps = Sleeps()
    llm = HangOnceOpen()
    client = LLMClient(llm, settings(llm_cache_enabled=False), sleep=sleeps)
    async with asyncio.timeout(5):  # không treo nếu timeout lúc mở hỏng
        async with client.stream(PROMPT, op="tutor_answer", timeout_s=0.05) as s:
            pieces = [p async for p in s]
    assert "".join(pieces) == "xin chào" and s.completed
    assert llm.opens == 2 and sleeps.delays == [1.0]
