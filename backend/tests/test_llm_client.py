import asyncio
import logging

import pytest
from google.genai import errors
from pydantic import BaseModel
from sqlalchemy import select

from app.ai.llm import FakeLLMProvider, ProviderResult
from app.ai.llm_client import LLMClient, LLMOutputError, cache_key
from app.ai.models import LLMCache
from app.ai.prompts import RenderedPrompt
from app.core.config import get_settings
from tests.test_ai_retry import Sleeps, api_error

PROMPT = RenderedPrompt("tutor_rewrite", "v1", "Viết lại: nó là gì?")


def settings(**kw):
    return get_settings().model_copy(update={"llm_cache_enabled": True, **kw})


class Answer(BaseModel):
    answer_option_id: str


async def test_generate_logs_tokens_latency_and_prompt_version(caplog):
    llm = FakeLLMProvider(["Tìm kiếm nhị phân là gì?"])
    client = LLMClient(llm, settings(llm_cache_enabled=False), sleep=Sleeps())
    with caplog.at_level(logging.INFO, logger="app.ai"):
        r = await client.generate(PROMPT, op="tutor_rewrite", model="cheap")
    assert r.text == "Tìm kiếm nhị phân là gì?" and r.cached is False
    assert r.tokens_in > 0 and r.tokens_out > 0 and r.prompt_version == "tutor_rewrite@v1"
    assert llm.calls[0].model == "cheap"
    line = next(m for m in caplog.messages if m.startswith("llm_call"))
    assert "op=tutor_rewrite" in line and "prompt_version=tutor_rewrite@v1" in line
    assert "tokens_in=" in line and "tokens_out=" in line and "latency_ms=" in line


async def test_timeout_depends_on_call_type():
    s = settings(llm_cache_enabled=False, llm_rewrite_timeout_s=7, llm_timeout_s=33)
    llm = FakeLLMProvider()
    client = LLMClient(llm, s, sleep=Sleeps())
    await client.generate(PROMPT, op="tutor_rewrite")
    await client.generate(PROMPT, op="quiz_generate")
    await client.generate(PROMPT, op="quiz_generate", timeout_s=3)
    assert [c.timeout_s for c in llm.calls] == [7, 33, 3]
    assert llm.calls[1].model == s.llm_model
    assert client.timeout_for("tutor_answer") == s.llm_stream_timeout_s


class SlowOnceProvider:
    """Lần gọi đầu treo lâu hơn timeout (SDK chỉ có timeout theo từng thao tác, không phải tổng)."""

    name = "slow"

    def __init__(self):
        self.calls = 0

    async def generate(self, prompt, *, op, model, timeout_s, json_schema=None):
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(10)
        return ProviderResult(text="ok", tokens_in=1, tokens_out=1)


async def test_timeout_is_a_total_bound_and_retried():
    sleeps = Sleeps()
    llm = SlowOnceProvider()
    client = LLMClient(llm, settings(llm_cache_enabled=False), sleep=sleeps)
    r = await client.generate(PROMPT, op="x", timeout_s=0.05)
    assert r.text == "ok" and llm.calls == 2 and sleeps.delays == [1.0]


async def test_second_identical_call_hits_cache(db):
    llm = FakeLLMProvider(["một"])
    client = LLMClient(llm, settings(), sleep=Sleeps())
    first = await client.generate(PROMPT, op="tutor_rewrite", model="m")
    second = await client.generate(PROMPT, op="tutor_rewrite", model="m")
    assert (first.text, first.cached) == ("một", False)
    assert (second.text, second.cached, second.tokens_in, second.tokens_out) == ("một", True, 0, 0)
    assert len(llm.calls) == 1
    row = await db.get(LLMCache, cache_key("fake", "m", PROMPT.text))
    assert (row.hit_count, row.provider, row.model, row.response) == (1, "fake", "m", "một")


def test_cache_key_depends_on_provider_model_prompt_and_schema():
    base = cache_key("fake", "a", "p")
    assert base != cache_key("gemini", "a", "p")
    assert base != cache_key("fake", "b", "p")
    assert base != cache_key("fake", "a", "q")
    assert base != cache_key("fake", "a", "p", {"type": "object"})
    assert base == cache_key("fake", "a", "p") and len(base) == 64


async def test_cache_disabled_or_bypassed_calls_provider_every_time():
    llm = FakeLLMProvider()
    off = LLMClient(llm, settings(llm_cache_enabled=False), sleep=Sleeps())
    await off.generate(PROMPT, op="x")
    await off.generate(PROMPT, op="x")
    on = LLMClient(llm, settings(), sleep=Sleeps())
    await on.generate(PROMPT, op="x", use_cache=False)
    await on.generate(PROMPT, op="x", use_cache=False)
    assert len(llm.calls) == 4


async def test_retries_429_and_503_then_succeeds():
    sleeps = Sleeps()
    llm = FakeLLMProvider([api_error(429), api_error(503), "ok"])
    r = await LLMClient(llm, settings(llm_cache_enabled=False), sleep=sleeps).generate(PROMPT, op="x")
    assert r.text == "ok" and sleeps.delays == [1.0, 2.0] and len(llm.calls) == 3


async def test_retry_after_is_respected():
    sleeps = Sleeps()
    llm = FakeLLMProvider([api_error(429, {"Retry-After": "7"}), "ok"])
    await LLMClient(llm, settings(llm_cache_enabled=False), sleep=sleeps).generate(PROMPT, op="x")
    assert sleeps.delays == [7.0]


async def test_other_4xx_is_not_retried():
    sleeps = Sleeps()
    llm = FakeLLMProvider([api_error(400), "ok"])
    with pytest.raises(errors.ClientError) as exc:
        await LLMClient(llm, settings(llm_cache_enabled=False), sleep=sleeps).generate(PROMPT, op="x")
    assert exc.value.code == 400 and sleeps.delays == [] and len(llm.calls) == 1


async def test_generate_json_validates_with_pydantic_and_sends_schema(db):
    llm = FakeLLMProvider(['```json\n{"answer_option_id": "B"}\n```'])
    parsed, result = await LLMClient(llm, settings(), sleep=Sleeps()).generate_json(
        PROMPT, Answer, op="quiz_self_check"
    )
    assert parsed == Answer(answer_option_id="B") and result.cached is False
    assert llm.calls[0].json_schema == Answer.model_json_schema()


async def test_invalid_json_raises_and_is_not_cached(db):
    llm = FakeLLMProvider(['{"sai": 1}', '{"answer_option_id": "C"}'])
    client = LLMClient(llm, settings(), sleep=Sleeps())
    with pytest.raises(LLMOutputError) as exc:
        await client.generate_json(PROMPT, Answer, op="quiz_self_check")
    assert exc.value.raw == '{"sai": 1}' and exc.value.result.tokens_out > 0
    parsed, _ = await client.generate_json(PROMPT, Answer, op="quiz_self_check")
    assert parsed.answer_option_id == "C" and len(llm.calls) == 2
    [row] = (await db.scalars(select(LLMCache))).all()
    assert row.response == '{"answer_option_id": "C"}'
