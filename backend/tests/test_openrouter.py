"""Provider OpenRouter: gọi đúng API kiểu OpenAI, đổi lỗi để retry đúng, stream SSE, đọc ảnh, embedding.
Không gọi mạng: httpx.MockTransport đóng vai OpenRouter."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.ai.embedder import get_embedder
from app.ai.llm import get_llm_provider
from app.ai.llm_client import LLMClient
from app.ai.openrouter import (
    OpenRouterEmbedder,
    OpenRouterError,
    OpenRouterLLM,
    OpenRouterVision,
    make_client,
)
from app.ai.prompts import RenderedPrompt
from app.ai.retry import is_retryable, retry_after_s
from app.ai.vision import get_vision
from app.core.config import Settings, get_settings
from scripts.check_openrouter import run_checks
from tests.test_ai_retry import Sleeps

BASE = "https://openrouter.test/api/v1"


def _client(handler) -> httpx.AsyncClient:
    return make_client("sk-or-test", BASE, transport=httpx.MockTransport(handler))


def _chat(text="Hà Nội", finish="stop", usage=(12, 3)) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
    }


def _settings(**kw) -> Settings:
    return get_settings().model_copy(update=kw)


async def test_generate_sends_openai_style_request_and_reads_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["title"] = request.headers["x-title"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_chat())

    llm = OpenRouterLLM("sk-or-test", client=_client(handler))
    result = await llm.generate(
        "Thủ đô?", op="t", model="google/gemini-3.5-flash", timeout_s=5, json_schema={"type": "object"}
    )
    assert (result.text, result.tokens_in, result.tokens_out, result.finish_reason) == (
        "Hà Nội",
        12,
        3,
        "STOP",
    )
    assert seen["url"] == f"{BASE}/chat/completions"
    assert (seen["auth"], seen["title"]) == ("Bearer sk-or-test", "LMS-AI")
    body = seen["body"]
    assert body["model"] == "google/gemini-3.5-flash" and body["temperature"] == 0
    assert body["messages"] == [{"role": "user", "content": "Thủ đô?"}]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}


async def test_length_finish_is_reported_as_truncation():
    llm = OpenRouterLLM("k", client=_client(lambda r: httpx.Response(200, json=_chat(finish="length"))))
    assert (await llm.generate("x", op="t", model="m", timeout_s=5)).finish_reason == "MAX_TOKENS"


async def test_http_errors_map_to_retry_rules():
    def rate_limited(request):
        return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {"message": "slow down"}})

    llm = OpenRouterLLM("k", client=_client(rate_limited))
    with pytest.raises(OpenRouterError) as info:
        await llm.generate("x", op="t", model="m", timeout_s=5)
    assert info.value.status_code == 429 and "slow down" in str(info.value)
    assert is_retryable(info.value) and retry_after_s(info.value) == 7

    bad = OpenRouterLLM(
        "k", client=_client(lambda r: httpx.Response(400, json={"error": {"message": "sai model"}}))
    )
    with pytest.raises(OpenRouterError) as info:
        await bad.generate("x", op="t", model="m", timeout_s=5)
    assert not is_retryable(info.value) and "sai model" in str(info.value)

    # 200 nhưng thân là lỗi của nhà cung cấp phía sau OpenRouter
    upstream = OpenRouterLLM(
        "k", client=_client(lambda r: httpx.Response(200, json={"error": {"code": 502, "message": "x"}}))
    )
    with pytest.raises(OpenRouterError) as info:
        await upstream.generate("x", op="t", model="m", timeout_s=5)
    assert is_retryable(info.value)


class Answer(BaseModel):
    answer: str


async def test_llm_client_retries_429_then_parses_json():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": {"message": "busy"}})
        return httpx.Response(200, json=_chat('{"answer": "Hà Nội"}'))

    sleeps = Sleeps()
    client = LLMClient(OpenRouterLLM("k", client=_client(handler)), _settings(), sleep=sleeps)
    parsed, _ = await client.generate_json(RenderedPrompt("check", "v1", "Thủ đô?"), Answer, op="check")
    assert parsed.answer == "Hà Nội" and len(calls) == 2 and sleeps.delays == [2.0]


def _sse(*events: dict | str) -> bytes:
    lines = [": OPENROUTER PROCESSING", ""]
    for e in events:
        lines += [f"data: {e if isinstance(e, str) else json.dumps(e)}", ""]
    return "\n".join(lines).encode()


async def test_stream_yields_text_and_usage_from_last_event():
    body = _sse(
        {"choices": [{"delta": {"content": "Hà "}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "Nội"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 2}},
        "[DONE]",
    )
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    stream = await OpenRouterLLM("k", client=_client(handler)).open_stream(
        "x", op="t", model="m", timeout_s=5
    )
    pieces = [p async for p in stream]
    await stream.aclose()
    await stream.aclose()  # gọi lại an toàn
    assert pieces == ["Hà ", "Nội"]
    assert (stream.tokens_in, stream.tokens_out, stream.finish_reason) == (9, 2, "STOP")
    assert seen["body"]["stream"] is True and seen["body"]["stream_options"] == {"include_usage": True}


async def test_stream_errors_at_open_and_mid_stream():
    llm = OpenRouterLLM(
        "k", client=_client(lambda r: httpx.Response(503, json={"error": {"message": "down"}}))
    )
    with pytest.raises(OpenRouterError) as info:
        await llm.open_stream("x", op="t", model="m", timeout_s=5)
    assert is_retryable(info.value)

    body = _sse(
        {"choices": [{"delta": {"content": "Hà "}}]}, {"error": {"code": 500, "message": "provider lỗi"}}
    )
    llm = OpenRouterLLM("k", client=_client(lambda r: httpx.Response(200, content=body)))
    stream = await llm.open_stream("x", op="t", model="m", timeout_s=5)
    got = []
    with pytest.raises(OpenRouterError):
        async for p in stream:
            got.append(p)
    assert got == ["Hà "]


async def test_vision_sends_png_as_data_url():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_chat("# Trang 1\nĐạo hàm"))

    vision = OpenRouterVision("k", "google/gemini-3.5-flash", client=_client(handler))
    assert await vision.page_to_markdown(b"\x89PNG-fake") == "# Trang 1\nĐạo hàm"
    content = seen["body"]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_embedder_batches_requests_dimensions_and_normalizes():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        # trả ngược thứ tự và dư chiều: phải xếp lại theo index và cắt về dim
        data = [{"index": i, "embedding": [3.0, 4.0, 99.0]} for i in range(len(body["input"]))][::-1]
        return httpx.Response(200, json={"data": data})

    emb = OpenRouterEmbedder("k", "google/gemini-embedding-001", 2, client=_client(handler), batch_size=2)
    vectors = await emb.embed_documents(["a", "b", "c"])
    assert [len(b["input"]) for b in bodies] == [2, 1] and bodies[0]["dimensions"] == 2
    assert vectors == [[0.6, 0.8]] * 3
    assert await emb.embed_query("a") == [0.6, 0.8]

    short = OpenRouterEmbedder(
        "k",
        "m",
        4,
        client=_client(lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})),
    )
    with pytest.raises(ValueError, match="EMBED_DIM=4"):
        await short.embed_query("a")


async def test_embedder_retries_5xx():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(502, json={"error": {"message": "x"}})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

    sleeps = Sleeps()
    emb = OpenRouterEmbedder("k", "m", 2, client=_client(handler), sleep=sleeps)
    assert await emb.embed_query("a") == [1.0, 0.0] and sleeps.delays == [1.0]


def test_settings_require_key_and_factories_pick_openrouter():
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        Settings(_env_file=None, llm_provider="openrouter", jwt_secret="x" * 40)
    s = _settings(
        llm_provider="openrouter",
        vision_provider="openrouter",
        embed_provider="openrouter",
        openrouter_api_key="sk-or-test",
        embed_model="google/gemini-embedding-001",
    )
    assert isinstance(get_llm_provider(s), OpenRouterLLM)
    assert isinstance(get_vision(s), OpenRouterVision)
    embedder = get_embedder(s)
    assert isinstance(embedder, OpenRouterEmbedder) and embedder.model == "google/gemini-embedding-001"


async def test_check_script_reports_each_step():
    from app.ai.embedder import FakeEmbedder
    from app.ai.llm import FakeLLMProvider
    from app.ai.vision import FakeVision

    llm = FakeLLMProvider(['{"answer": "Hà Nội"}'] * 3)
    assert await run_checks(_settings(), llm, FakeVision(), FakeEmbedder(get_settings().embed_dim))
