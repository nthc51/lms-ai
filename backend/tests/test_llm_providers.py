import asyncio
import json
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.ai.llm import FakeLLMProvider, GeminiLLM, get_llm_provider, split_pieces
from app.core.config import Settings
from app.ingestion.chunker import count_tokens
from tests.test_ai_retry import api_error


async def _gen(llm, op="x", prompt="p"):
    return await llm.generate(prompt, op=op, model="m", timeout_s=1)


def test_split_pieces_keeps_text():
    assert split_pieces("Xin chào  các bạn") == ["Xin", " chào", "  các", " bạn"]
    assert split_pieces("") == []


async def test_fake_replies_in_order_then_default():
    llm = FakeLLMProvider(["một", ValueError("hỏng"), lambda call: call.op.upper()])
    assert (await _gen(llm)).text == "một"
    with pytest.raises(ValueError):
        await _gen(llm)
    assert (await _gen(llm, op="abc")).text == "ABC"
    assert (await _gen(llm, op="tutor_answer")).text.startswith("Theo tài liệu [1]")
    assert [c.op for c in llm.calls] == ["x", "x", "abc", "tutor_answer"]
    assert llm.calls[0].timeout_s == 1 and llm.calls[0].stream is False


async def test_fake_default_replies_for_rewrite_and_quiz():
    llm = FakeLLMProvider()
    rewrite = await _gen(
        llm, op="tutor_rewrite", prompt="<history>\nx\n</history>\n<question>\nNó là gì?\n</question>"
    )
    assert rewrite.text == "Nó là gì?"
    prompt = "Số câu cần sinh: 3\n<source>\n" + "từ khóa quan trọng " * 20 + "\n</source>"
    data = json.loads((await _gen(llm, op="quiz_generate", prompt=prompt)).text)
    assert len(data["questions"]) == 3
    assert all(len(q["options"]) == 4 and q["correct_option_id"] == "A" for q in data["questions"])
    assert len({q["stem"] for q in data["questions"]}) == 3
    assert json.loads((await _gen(llm, op="quiz_self_check")).text) == {"answer_option_id": "A"}


async def test_fake_stream_yields_pieces_and_reports_usage_at_end():
    llm = FakeLLMProvider(["Xin chào các bạn"])
    stream = await llm.open_stream("câu hỏi", op="tutor_answer", model="m", timeout_s=1)
    assert stream.tokens_out is None
    pieces = [p async for p in stream]
    assert pieces == ["Xin", " chào", " các", " bạn"]
    assert stream.tokens_in == count_tokens("câu hỏi") and stream.tokens_out == count_tokens(
        "Xin chào các bạn"
    )
    await stream.aclose()
    assert llm.streams == [stream] and stream.closed and llm.calls[0].stream is True


async def test_fake_stream_gate_blocks_and_error_is_raised_mid_stream():
    gate = asyncio.Event()
    llm = FakeLLMProvider(["a b c"], stream_gate=gate)
    it = aiter(await llm.open_stream("p", op="tutor_answer", model="m", timeout_s=1))
    assert await anext(it) == "a"
    nxt = asyncio.ensure_future(anext(it))
    await asyncio.sleep(0.01)
    assert not nxt.done()
    gate.set()
    assert await nxt == " b"

    broken = FakeLLMProvider(["a b c"], stream_error=(2, TimeoutError()))
    got = []
    with pytest.raises(TimeoutError):
        async for piece in await broken.open_stream("p", op="tutor_answer", model="m", timeout_s=1):
            got.append(piece)
    assert got == ["a", " b"]


class _Models:
    def __init__(self, chunks=(), error=None):
        self.configs = []
        self.chunks = list(chunks)
        self.error = error

    async def generate_content(self, model, contents, config=None):
        self.configs.append(config)
        usage = SimpleNamespace(prompt_token_count=11, candidates_token_count=3)
        return SimpleNamespace(text='  {"a": 1}  ', usage_metadata=usage)

    async def generate_content_stream(self, model, contents, config=None):
        self.configs.append(config)
        chunks, error = self.chunks, self.error

        async def gen():
            if error is not None:
                raise error
            for c in chunks:
                yield c

        return gen()


def _gemini(models) -> GeminiLLM:
    return GeminiLLM("x", client=SimpleNamespace(aio=SimpleNamespace(models=models)))


async def test_gemini_generate_sends_schema_timeout_and_maps_usage():
    models = _Models()
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    res = await _gemini(models).generate(
        "p", op="quiz_generate", model="m", timeout_s=12.5, json_schema=schema
    )
    assert (res.text, res.tokens_in, res.tokens_out) == ('{"a": 1}', 11, 3)
    config = models.configs[0]
    assert config.response_json_schema == schema and config.response_mime_type == "application/json"
    assert config.http_options.timeout == 12500 and config.temperature == 0


async def test_gemini_stream_prefetches_first_chunk_and_reads_usage():
    last = SimpleNamespace(
        text="chào", usage_metadata=SimpleNamespace(prompt_token_count=5, candidates_token_count=2)
    )
    models = _Models([SimpleNamespace(text="Xin ", usage_metadata=None), last])
    stream = await _gemini(models).open_stream("p", op="tutor_answer", model="m", timeout_s=30)
    assert [p async for p in stream] == ["Xin ", "chào"]
    assert (stream.tokens_in, stream.tokens_out) == (5, 2)
    # lỗi 429 ném ra ngay lúc mở, trước token đầu → LLMClient retry được
    with pytest.raises(errors.ClientError):
        await _gemini(_Models(error=api_error(429))).open_stream(
            "p", op="tutor_answer", model="m", timeout_s=30
        )


def test_factory_picks_fake_by_default():
    assert isinstance(get_llm_provider(Settings(llm_provider="fake")), FakeLLMProvider)
    assert isinstance(get_llm_provider(Settings(llm_provider="gemini", gemini_api_key="x")), GeminiLLM)
