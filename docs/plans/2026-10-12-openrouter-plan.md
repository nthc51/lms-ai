# OpenRouter thay cho Gemini API: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** Google AI Studio không nhận thẻ thanh toán của bạn, nên bản trả tiền của Gemini API không dùng được. OpenRouter bán cùng các model Gemini (và nhiều model khác) qua một API kiểu OpenAI, nạp tiền trước rồi trừ theo token. Plan này thêm provider thứ ba `openrouter` bên cạnh `fake` và `gemini`, dùng được cho **cả ba vai**: LLM (AI Tutor, quiz, Studio), vision (đọc trang PDF dạng ảnh) và embedding.

**Mục tiêu:**

- `LLM_PROVIDER` / `VISION_PROVIDER` / `EMBED_PROVIDER` nhận thêm `openrouter`; thiếu `OPENROUTER_API_KEY` thì app và worker **không khởi động** (báo rõ lỗi), như cách đang làm với Gemini.
- Hành vi giữ nguyên với phần còn lại của app: retry (429 / 5xx / mất mạng, đọc `Retry-After`), cache, ghi `ai_calls`, `finish_reason` (`length` → bị cắt, `content_filter` → bị chặn), stream SSE cho AI Tutor, JSON theo schema cho quiz / Studio.
- Embedding: gửi `dimensions = EMBED_DIM`; model trả nhiều chiều hơn thì cắt rồi chuẩn hóa lại (an toàn với `gemini-embedding-001`), trả ít hơn thì báo lỗi nêu rõ `EMBED_DIM`.
- Script `scripts/check_openrouter.py`: thử nhanh 5 việc (văn bản, JSON, stream, đọc ảnh một trang PDF, embedding) với `.env` hiện tại, in OK / LỖI và độ trễ.
- Script `scripts/reembed.py`: đổi model embedding thì **nhúng lại** các đoạn tài liệu cũ (không đọc lại PDF, không gọi vision). Đây cũng là cách sửa lỗi "Tài liệu đang được xử lý" mãi không hết sau khi đổi provider.

**Không đổi:** code gọi AI ở các module (tutor, quiz, studio, ingestion) chỉ dùng các factory `get_llm_provider` / `get_vision` / `get_embedder`, nên không phải sửa. Test luôn dùng `fake`; test của OpenRouter dùng `httpx.MockTransport` (không gọi mạng).

**Thứ tự làm:** sau `2026-10-12-password-reset-plan.md` (diff tạo trên bản đã xong plan đó: `config.py` và `.env.example` có thêm `RESET_TOKEN_MINUTES`). Sau plan này là `2026-10-12-tutor-waiting-plan.md`.

**Mã trong plan đã được chạy thử:** backend **751 test pass** ở cuối chuỗi 3 plan (12 test mới ở plan này), `ruff`, `lint-imports` sạch. Không có thay đổi frontend.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Cách áp diff như plan quên mật khẩu (đường dẫn tính từ gốc repo, `git apply --3way` hoặc sửa tay).

---

## Task 1: Client OpenRouter

**Files:**
- Create: `backend/app/ai/openrouter.py`
- Modify: `backend/app/ai/retry.py`
- Test: `backend/tests/test_openrouter.py` (mới; một test của file này dùng script ở Task 3, chạy hết ở Task 3)

- [x] **Bước 1: Viết test**

```python
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
```

- [x] **Bước 2: `app/ai/openrouter.py`**

Ghi chú thiết kế:

- Một `httpx.AsyncClient` cho mỗi provider (`make_client`), header `Authorization: Bearer …` và `X-Title: LMS-AI` (tên hiện trong trang thống kê của OpenRouter). Tham số `transport` chỉ để test.
- OpenRouter đôi khi trả **HTTP 200 nhưng body có `error`** (lỗi từ nhà cung cấp phía sau): coi như lỗi với mã trong body, để retry đúng luật.
- Stream: bỏ dòng chú thích `: OPENROUTER PROCESSING`, dừng ở `[DONE]`, lấy `usage` ở event cuối (`stream_options.include_usage`). Lỗi giữa stream (event có `error`) thì ném lỗi; lỗi HTTP lúc mở stream thì ném ngay ở `open`, trước token đầu.
- JSON schema gửi `strict: false` (một số model qua OpenRouter không nhận strict); app vẫn kiểm schema bằng Pydantic như trước.

```python
"""Provider OpenRouter (API kiểu OpenAI, trả tiền theo token): sinh văn bản (kể cả stream), đọc ảnh trang PDF,
embedding. Dùng thay Gemini bằng cách đặt *_PROVIDER=openrouter và tên model kiểu OpenRouter
(vd. LLM_MODEL=google/gemini-3.5-flash, EMBED_MODEL=google/gemini-embedding-001).

Giống bản Gemini, provider chỉ gửi một request; retry (429 / 5xx / timeout), cache và ghi ai_calls nằm ở
LLMClient và call_with_retry. Lỗi HTTP được đổi thành OpenRouterError (có status_code và response) để
call_with_retry biết lỗi nào thử lại được và đọc header Retry-After."""

import base64
import json
import math
from collections.abc import AsyncIterator

import httpx

from app.ai.llm import ProviderResult
from app.ai.retry import Sleep, call_with_retry
from app.ingestion.chunker import count_tokens

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# finish_reason của OpenRouter (chuẩn OpenAI) → tên LLMClient hiểu (STOP thì được cache, khác thì là bị cắt)
_FINISH = {"stop": "STOP", "length": "MAX_TOKENS", "content_filter": "SAFETY", "tool_calls": "TOOL_CALLS"}


class OpenRouterError(Exception):
    """Lỗi từ OpenRouter. status_code: mã HTTP (hoặc mã trong event lỗi giữa stream); response: để đọc
    Retry-After (None với lỗi giữa stream)."""

    def __init__(self, status_code: int, message: str, response: httpx.Response | None = None):
        super().__init__(f"OpenRouter {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.response = response


def _finish(reason: str | None) -> str | None:
    return None if reason is None else _FINISH.get(reason, reason.upper())


def _error_from(response: httpx.Response, body: bytes) -> OpenRouterError:
    message = body.decode("utf-8", "replace")[:500]
    try:
        err = json.loads(body).get("error") or {}
        message = str(err.get("message") or message)
    except (ValueError, AttributeError):
        pass
    return OpenRouterError(response.status_code, message, response)


def make_client(
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    app_title: str = "LMS-AI",
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Client dùng chung cho mọi lời gọi OpenRouter. transport: chỉ để test (httpx.MockTransport)."""
    headers = {"Authorization": f"Bearer {api_key}", "X-Title": app_title}
    return httpx.AsyncClient(base_url=base_url, headers=headers, timeout=60.0, transport=transport)


async def _post_json(client: httpx.AsyncClient, path: str, body: dict, timeout_s: float) -> dict:
    resp = await client.post(path, json=body, timeout=timeout_s)
    if resp.status_code != 200:
        raise _error_from(resp, resp.content)
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):  # OpenRouter đôi khi trả 200 kèm lỗi của nhà cung cấp
        err = data["error"]
        raise OpenRouterError(int(err.get("code") or 502), str(err.get("message") or err))
    return data


def _message_text(data: dict) -> tuple[str, str | None]:
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    if isinstance(content, list):  # một số model trả danh sách phần
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content.strip(), _finish(choice.get("finish_reason"))


# ---------------------------------------------------------------- sinh văn bản


class OpenRouterStream:
    """Stream SSE của /chat/completions. Mở bằng `await OpenRouterStream.open(...)`: mã HTTP lỗi (429/5xx...)
    ném ra ngay lúc mở nên LLMClient retry được. Lỗi giữa chừng (event có trường "error") ném ra khi đọc."""

    def __init__(self, response: httpx.Response):
        self._response = response
        self.tokens_in: int | None = None
        self.tokens_out: int | None = None
        self.finish_reason: str | None = None

    @classmethod
    async def open(cls, client: httpx.AsyncClient, body: dict, timeout_s: float) -> "OpenRouterStream":
        request = client.build_request("POST", "/chat/completions", json=body, timeout=timeout_s)
        response = await client.send(request, stream=True)
        if response.status_code != 200:
            content = await response.aread()
            await response.aclose()
            raise _error_from(response, content)
        return cls(response)

    def __aiter__(self) -> AsyncIterator[str]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[str]:
        async for line in self._response.aiter_lines():
            if not line.startswith("data:"):
                continue  # dòng trống, chú thích ": OPENROUTER PROCESSING"
            data = line[5:].strip()
            if data == "[DONE]":
                return
            event = json.loads(data)
            if event.get("error"):
                err = event["error"]
                raise OpenRouterError(int(err.get("code") or 502), str(err.get("message") or err))
            if usage := event.get("usage"):
                self.tokens_in = usage.get("prompt_tokens") or self.tokens_in
                self.tokens_out = usage.get("completion_tokens") or self.tokens_out
            for choice in event.get("choices") or []:
                self.finish_reason = _finish(choice.get("finish_reason")) or self.finish_reason
                if text := (choice.get("delta") or {}).get("content"):
                    yield text

    async def aclose(self) -> None:
        """Đóng response HTTP (dừng sinh tiếp). Gọi lại nhiều lần an toàn."""
        await self._response.aclose()


class OpenRouterLLM:
    name = "openrouter"

    def __init__(
        self, api_key: str, base_url: str = DEFAULT_BASE_URL, client: httpx.AsyncClient | None = None
    ):
        self._client = client or make_client(api_key, base_url)

    @staticmethod
    def _body(prompt: str, model: str, json_schema: dict | None = None, *, stream: bool = False) -> dict:
        body: dict = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": False, "schema": json_schema},
            }
        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}  # usage nằm ở event cuối
        return body

    async def generate(
        self, prompt: str, *, op: str, model: str, timeout_s: float, json_schema: dict | None = None
    ) -> ProviderResult:
        data = await _post_json(
            self._client, "/chat/completions", self._body(prompt, model, json_schema), timeout_s
        )
        text, finish = _message_text(data)
        usage = data.get("usage") or {}
        return ProviderResult(
            text=text,
            tokens_in=usage.get("prompt_tokens") or count_tokens(prompt),
            tokens_out=usage.get("completion_tokens") or count_tokens(text),
            finish_reason=finish,
        )

    async def open_stream(self, prompt: str, *, op: str, model: str, timeout_s: float) -> OpenRouterStream:
        return await OpenRouterStream.open(self._client, self._body(prompt, model, stream=True), timeout_s)


# ---------------------------------------------------------------- đọc ảnh trang PDF


class OpenRouterVision:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_s: float = 120.0,
        sleep: Sleep | None = None,
    ):
        self._client = client or make_client(api_key, base_url)
        self._model = model
        self._timeout_s = timeout_s
        self._sleep = sleep

    async def page_to_markdown(self, png: bytes) -> str:
        from app.ai.vision import VISION_PROMPT

        image = "data:image/png;base64," + base64.b64encode(png).decode()
        body = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": image}},
                    ],
                }
            ],
        }
        kw = {"sleep": self._sleep} if self._sleep else {}
        data = await call_with_retry(
            "vision", lambda: _post_json(self._client, "/chat/completions", body, self._timeout_s), **kw
        )
        return _message_text(data)[0]


# ---------------------------------------------------------------- embedding


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class OpenRouterEmbedder:
    """Embedding qua /embeddings, gửi theo lô `batch_size` đoạn, xin đúng `dim` chiều (tham số `dimensions`).
    Model trả nhiều chiều hơn (không hỗ trợ `dimensions`) thì cắt lấy `dim` chiều đầu rồi chuẩn hóa lại — các
    model embedding phổ biến (gemini-embedding, text-embedding-3, qwen3-embedding) được huấn luyện để cắt như
    vậy. Ít chiều hơn thì báo lỗi rõ: phải đổi EMBED_DIM và migration cột vector."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dim: int,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_s: float = 30.0,
        batch_size: int = 100,
        sleep: Sleep | None = None,
    ):
        self._client = client or make_client(api_key, base_url)
        self.model = model
        self.dim = dim
        self._timeout_s = timeout_s
        self._batch_size = max(1, batch_size)
        self._sleep = sleep

    def _vector(self, values: list[float]) -> list[float]:
        if len(values) < self.dim:
            raise ValueError(
                f"Model {self.model} trả vector {len(values)} chiều, ít hơn EMBED_DIM={self.dim}. "
                "Chọn model khác hoặc đổi EMBED_DIM (kèm migration cột chunks.embedding)."
            )
        return _normalize(values[: self.dim])

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        kw = {"sleep": self._sleep} if self._sleep else {}
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            body = {"model": self.model, "input": batch, "dimensions": self.dim, "encoding_format": "float"}
            data = await call_with_retry(
                "embed", lambda b=body: _post_json(self._client, "/embeddings", b, self._timeout_s), **kw
            )
            items = sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
            if len(items) != len(batch):
                raise OpenRouterError(502, f"Embedding trả {len(items)} vector cho {len(batch)} đoạn")
            out.extend(self._vector(item["embedding"]) for item in items)
        return out

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]
```

- [x] **Bước 3: Retry nhận `OpenRouterError`**

```diff
--- a/backend/app/ai/retry.py
+++ b/backend/app/ai/retry.py
@@ -1,4 +1,4 @@
-"""Retry dùng chung cho các lời gọi Gemini: chỉ thử lại khi 429, 5xx hoặc timeout."""
+"""Retry dùng chung cho các lời gọi AI (Gemini, OpenRouter): chỉ thử lại khi 429, 5xx hoặc timeout."""
 
 import asyncio
 import logging
@@ -21,7 +21,13 @@
 def _status_code(exc: BaseException) -> int | None:
     from google.genai import errors
 
-    return exc.code if isinstance(exc, errors.APIError) else None
+    from app.ai.openrouter import OpenRouterError
+
+    if isinstance(exc, errors.APIError):
+        return exc.code
+    if isinstance(exc, OpenRouterError):
+        return exc.status_code
+    return None
 
 
 def is_retryable(exc: BaseException) -> bool:
```

---

## Task 2: Cấu hình và factory

**Files:**
- Modify: `backend/app/core/config.py`, `backend/.env.example`
- Modify: `backend/app/ai/llm.py`, `vision.py`, `embedder.py`

- [ ] **Bước 1: Cấu hình** (validator đổi tên thành `_require_provider_keys`, kiểm cả hai loại key)

```diff
--- a/backend/app/core/config.py
+++ b/backend/app/core/config.py
@@ -6,7 +6,7 @@
 from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
 
 # Provider AI hợp lệ. Gõ sai (vd "gemni") thì app/worker không khởi động thay vì âm thầm chạy bản giả.
-AIProvider = Literal["fake", "gemini"]
+AIProvider = Literal["fake", "gemini", "openrouter"]
 
 
 class Settings(BaseSettings):
@@ -37,6 +37,10 @@
     vision_provider: AIProvider = "fake"
     vision_model: str = "gemini-3.5-flash"
     gemini_api_key: str = ""
+    # OpenRouter (provider = openrouter): trả tiền theo token, dùng thay Gemini. Tên model kiểu OpenRouter,
+    # vd. LLM_MODEL=google/gemini-3.6-flash, EMBED_MODEL=google/gemini-embedding-001.
+    openrouter_api_key: str = ""
+    openrouter_base_url: str = "https://openrouter.ai/api/v1"
     embed_timeout_s: float = 30.0
     # Số đoạn tối đa mỗi request embedding.
     embed_batch_size: int = 100
@@ -106,19 +110,20 @@
         return v
 
     @model_validator(mode="after")
-    def _require_gemini_key(self) -> "Settings":
-        """Provider nào là gemini thì phải có GEMINI_API_KEY ngay lúc khởi động (không đợi tới lời gọi đầu tiên)."""
-        using = [
-            name
-            for name, value in (
-                ("LLM_PROVIDER", self.llm_provider),
-                ("EMBED_PROVIDER", self.embed_provider),
-                ("VISION_PROVIDER", self.vision_provider),
-            )
-            if value == "gemini"
-        ]
-        if using and not self.gemini_api_key.strip():
-            raise ValueError(f"GEMINI_API_KEY trống trong khi {', '.join(using)}=gemini")
+    def _require_provider_keys(self) -> "Settings":
+        """Provider nào được dùng thì phải có API key của nó ngay lúc khởi động (không đợi tới lời gọi đầu tiên)."""
+        providers = (
+            ("LLM_PROVIDER", self.llm_provider),
+            ("EMBED_PROVIDER", self.embed_provider),
+            ("VISION_PROVIDER", self.vision_provider),
+        )
+        for provider, key_name, key in (
+            ("gemini", "GEMINI_API_KEY", self.gemini_api_key),
+            ("openrouter", "OPENROUTER_API_KEY", self.openrouter_api_key),
+        ):
+            using = [name for name, value in providers if value == provider]
+            if using and not key.strip():
+                raise ValueError(f"{key_name} trống trong khi {', '.join(using)}={provider}")
         return self
 
 
```

```diff
--- a/backend/.env.example
+++ b/backend/.env.example
@@ -32,6 +32,12 @@
 # Khi dùng Gemini thật: EMBED_PROVIDER=gemini, VISION_PROVIDER=gemini, LLM_PROVIDER=gemini, GEMINI_API_KEY=...
 # (kiểm tra lại tên model hiện hành trên trang Google AI; GEMINI_API_KEY dùng chung cho embedder/vision/LLM)
 GEMINI_API_KEY=
+# Khi dùng OpenRouter (trả tiền theo token, thay cho Gemini): *_PROVIDER=openrouter, OPENROUTER_API_KEY=sk-or-...
+# và tên model kiểu OpenRouter: LLM_MODEL=google/gemini-3.6-flash, LLM_CHEAP_MODEL=google/gemini-3.5-flash-lite,
+# VISION_MODEL=google/gemini-3.6-flash, EMBED_MODEL=google/gemini-embedding-001 (kiểm tra tên trên openrouter.ai/models).
+# Đổi EMBED_PROVIDER/EMBED_MODEL thì chạy: uv run python -m scripts.reembed (nhúng lại tài liệu cũ, không gọi lại vision).
+OPENROUTER_API_KEY=
+OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
 LLM_PROVIDER=fake
 LLM_MODEL=gemini-3.5-flash
 LLM_CHEAP_MODEL=gemini-3.5-flash-lite
```

- [ ] **Bước 2: Factory**

```diff
--- a/backend/app/ai/llm.py
+++ b/backend/app/ai/llm.py
@@ -411,6 +411,10 @@
 def get_llm_provider(s: Settings) -> LLMProvider:
     if s.llm_provider == "gemini":
         return GeminiLLM(s.gemini_api_key)
+    if s.llm_provider == "openrouter":
+        from app.ai.openrouter import OpenRouterLLM
+
+        return OpenRouterLLM(s.openrouter_api_key, s.openrouter_base_url)
     if s.llm_provider == "fake":
         return FakeLLMProvider()
-    raise ValueError(f"LLM_PROVIDER không hợp lệ: {s.llm_provider!r} (chỉ nhận fake | gemini)")
+    raise ValueError(f"LLM_PROVIDER không hợp lệ: {s.llm_provider!r} (chỉ nhận fake | gemini | openrouter)")
```

```diff
--- a/backend/app/ai/vision.py
+++ b/backend/app/ai/vision.py
@@ -58,6 +58,14 @@
 def get_vision(s: Settings) -> VisionExtractor:
     if s.vision_provider == "gemini":
         return GeminiVision(s.gemini_api_key, s.vision_model, timeout_s=s.vision_timeout_s)
+    if s.vision_provider == "openrouter":
+        from app.ai.openrouter import OpenRouterVision
+
+        return OpenRouterVision(
+            s.openrouter_api_key, s.vision_model, s.openrouter_base_url, timeout_s=s.vision_timeout_s
+        )
     if s.vision_provider == "fake":
         return FakeVision()
-    raise ValueError(f"VISION_PROVIDER không hợp lệ: {s.vision_provider!r} (chỉ nhận fake | gemini)")
+    raise ValueError(
+        f"VISION_PROVIDER không hợp lệ: {s.vision_provider!r} (chỉ nhận fake | gemini | openrouter)"
+    )
```

```diff
--- a/backend/app/ai/embedder.py
+++ b/backend/app/ai/embedder.py
@@ -160,9 +160,22 @@
             batch_size=s.embed_batch_size,
             tpm_limit=s.embed_tpm_limit,
         )
+    if s.embed_provider == "openrouter":
+        from app.ai.openrouter import OpenRouterEmbedder
+
+        return OpenRouterEmbedder(
+            s.openrouter_api_key,
+            s.embed_model,
+            s.embed_dim,
+            s.openrouter_base_url,
+            timeout_s=s.embed_timeout_s,
+            batch_size=s.embed_batch_size,
+        )
     if s.embed_provider == "fake":
         return FakeEmbedder(s.embed_dim)
-    raise ValueError(f"EMBED_PROVIDER không hợp lệ: {s.embed_provider!r} (chỉ nhận fake | gemini)")
+    raise ValueError(
+        f"EMBED_PROVIDER không hợp lệ: {s.embed_provider!r} (chỉ nhận fake | gemini | openrouter)"
+    )
 
 
 @lru_cache
```

---

## Task 3: Script kiểm tra và nhúng lại

**Files:**
- Create: `backend/scripts/check_openrouter.py`, `backend/scripts/reembed.py`
- Test: `backend/tests/test_reembed.py`

```python
"""Kiểm tra nhanh provider trong .env (OpenRouter hoặc Gemini) có gọi được không, đúng như app gọi.

Chạy từ thư mục backend/ (PowerShell):  $env:PYTHONUTF8=1; uv run python -m scripts.check_openrouter
Thử lần lượt: sinh văn bản, sinh JSON theo schema, stream, đọc ảnh một trang PDF có chữ, embedding (kiểm số
chiều = EMBED_DIM). In OK/LỖI + độ trễ cho từng mục. Tốn vài lượt gọi rất nhỏ.
"""

import asyncio
import json
import sys
import time

from app.ai.embedder import Embedder, get_embedder
from app.ai.llm import LLMProvider, get_llm_provider
from app.ai.vision import VisionExtractor, get_vision
from app.core.config import Settings, get_settings

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
QUESTION = "Thủ đô của Việt Nam là gì? Trả lời ngắn."


def sample_page_png() -> bytes:
    """Ảnh một trang PDF có chữ tiếng Việt (dựng bằng PyMuPDF, thư viện app đã dùng để đọc PDF)."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=420, height=200)
    page.insert_text((30, 90), "Dao ham cua ham hang bang 0.", fontsize=18)
    return page.get_pixmap(dpi=100).tobytes("png")


async def _step(label: str, fn) -> bool:
    start = time.perf_counter()
    try:
        detail = await fn()
    except Exception as e:  # noqa: BLE001 — in lỗi gọn để người dùng đọc
        print(f"LỖI  {label:<22} → {str(e)[:200]}")
        return False
    print(f"OK   {label:<22} {time.perf_counter() - start:5.1f}s  → {str(detail)[:80]}")
    return True


async def run_checks(s: Settings, llm: LLMProvider, vision: VisionExtractor, embedder: Embedder) -> bool:
    async def text():
        return (await llm.generate(QUESTION, op="check", model=s.llm_model, timeout_s=s.llm_timeout_s)).text

    async def as_json():
        r = await llm.generate(
            QUESTION, op="check", model=s.llm_model, timeout_s=s.llm_timeout_s, json_schema=SCHEMA
        )
        return json.loads(r.text)["answer"]

    async def stream():
        st = await llm.open_stream(QUESTION, op="check", model=s.llm_model, timeout_s=s.llm_timeout_s)
        try:
            pieces = [p async for p in st]
        finally:
            await st.aclose()
        return f"{len(pieces)} mảnh, token {st.tokens_in}/{st.tokens_out}: {''.join(pieces)}"

    async def read_image():
        return await vision.page_to_markdown(sample_page_png())

    async def embed():
        vectors = await embedder.embed_documents(["Đạo hàm của hàm hằng", "Tích phân"])
        if any(len(v) != s.embed_dim for v in vectors):
            raise ValueError(f"vector {len(vectors[0])} chiều, EMBED_DIM={s.embed_dim}")
        return f"{len(vectors)} vector × {s.embed_dim} chiều (model {embedder.model})"

    results = [
        await _step(f"LLM {s.llm_model}", text),
        await _step("LLM JSON schema", as_json),
        await _step("LLM stream", stream),
        await _step(f"Vision {s.vision_model}", read_image),
        await _step(f"Embedding {s.embed_model}", embed),
    ]
    return all(results)


def main() -> None:
    s = get_settings()
    print(f"Provider: LLM={s.llm_provider} VISION={s.vision_provider} EMBED={s.embed_provider}")
    ok = asyncio.run(run_checks(s, get_llm_provider(s), get_vision(s), get_embedder(s)))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

```python
"""Nhúng lại (embedding) các đoạn tài liệu đã xử lý bằng EMBED_PROVIDER / EMBED_MODEL hiện tại.

Khi nào cần: sau khi đổi provider hoặc model embedding (vd. Gemini → OpenRouter, tên model đổi thành
google/gemini-embedding-001). AI Tutor chỉ tìm các đoạn có embedding_model trùng model đang dùng, nên đoạn cũ
không được tìm thấy cho tới khi nhúng lại. Script chỉ tính lại vector từ nội dung đã trích (không đọc lại PDF,
không gọi vision), chạy lại nhiều lần an toàn (chỉ xử lý đoạn còn khác model).

Chạy từ thư mục backend/ (đã đặt .env):  uv run python -m scripts.reembed
"""

import asyncio

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models_registry  # noqa: F401 — nạp mọi model (FK của chunks)
from app.ai.embedder import Embedder, get_embedder
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.materials.models import Chunk

BATCH = 100


async def count_stale(session_factory: async_sessionmaker, model: str) -> int:
    async with session_factory() as db:
        return await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding_model != model))


async def reembed(
    session_factory: async_sessionmaker, embedder: Embedder, *, batch: int = BATCH, log=print
) -> int:
    """Nhúng lại mọi đoạn có embedding_model khác embedder.model. Trả số đoạn đã cập nhật."""
    total = 0
    while True:
        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(Chunk.id, Chunk.content)
                    .where(Chunk.embedding_model != embedder.model)
                    .order_by(Chunk.id)
                    .limit(batch)
                )
            ).all()
            if not rows:
                return total
            vectors = await embedder.embed_documents([content for _, content in rows])
            for (chunk_id, _), vector in zip(rows, vectors, strict=True):
                await db.execute(
                    update(Chunk)
                    .where(Chunk.id == chunk_id)
                    .values(embedding=vector, embedding_model=embedder.model)
                )
            await db.commit()
        total += len(rows)
        log(f"Đã nhúng lại {total} đoạn")


async def main() -> None:
    s = get_settings()
    embedder = get_embedder(s)
    stale = await count_stale(SessionLocal, embedder.model)
    print(f"Model embedding hiện tại: {embedder.model} ({s.embed_provider}). Cần nhúng lại: {stale} đoạn.")
    done = await reembed(SessionLocal, embedder)
    print(f"Xong: {done} đoạn.")


if __name__ == "__main__":
    asyncio.run(main())
```

```python
"""scripts.reembed: đổi model embedding (vd. Gemini → OpenRouter) thì nhúng lại đoạn cũ, không đọc lại PDF."""

import uuid

import pytest
from sqlalchemy import select, update

from app.ai.embedder import FakeEmbedder
from app.ai.retrieval import SearchScope, count_ready_chunks
from app.core.db import SessionLocal
from app.modules.materials.models import Chunk
from scripts.reembed import count_stale, reembed
from tests.factories import seed_chunks
from tests.helpers import make_published_course, make_teacher


async def test_reembed_moves_old_chunks_to_current_model(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    await seed_chunks(db, uuid.UUID(lesson["id"]), ["Đạo hàm của hàm hằng", "Tích phân", "Giới hạn"])
    await db.execute(
        update(Chunk).values(embedding_model="google/gemini-embedding-001", embedding=[0.0] * 768)
    )
    await db.commit()
    embedder = FakeEmbedder(768)
    scope = SearchScope(uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    assert await count_ready_chunks(db, scope, embedder.model) == 0  # AI Tutor không thấy đoạn của model cũ
    assert await count_stale(SessionLocal, embedder.model) == 3

    logs: list[str] = []
    assert await reembed(SessionLocal, embedder, batch=2, log=logs.append) == 3
    assert logs == ["Đã nhúng lại 2 đoạn", "Đã nhúng lại 3 đoạn"]
    db.expire_all()
    rows = (await db.execute(select(Chunk.content, Chunk.embedding_model, Chunk.embedding))).all()
    assert {m for _, m, _ in rows} == {embedder.model}
    for content, _, vector in rows:
        assert list(vector) == pytest.approx((await embedder.embed_documents([content]))[0], abs=1e-6)
    assert await count_ready_chunks(db, scope, embedder.model) == 3
    assert await reembed(SessionLocal, embedder) == 0  # chạy lại an toàn
```

- [ ] **Chạy test**

```powershell
cd backend
uv run pytest tests/test_openrouter.py tests/test_reembed.py tests/test_config.py tests/test_ai_retry.py -q
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
```

Kỳ vọng: pass (12 test mới), sạch.

- [ ] **Commit**

```powershell
git add backend
git commit -m "feat(ai): provider OpenRouter cho LLM, vision, embedding + script kiểm tra / nhúng lại"
```

---

## Task 4: Chuyển sang OpenRouter (bạn làm, khi muốn dùng AI thật)

Làm khi **đã code xong cả 3 plan** và đã test xong với `fake`. Tốn tiền thật nhưng rất ít (vài nghìn đồng cho một lượt kiểm tra).

- [ ] **Nạp tiền và tạo key:** đăng nhập openrouter.ai → Credits → nạp (thẻ quốc tế hoặc crypto) → Keys → Create key, đặt giới hạn chi tiêu cho key (ví dụ 5 USD) để không bị trừ quá tay.
- [ ] **Kiểm tên model** trên openrouter.ai/models (gõ "gemini"). Tháng 10/2026 có `google/gemini-3.6-flash`, `google/gemini-3.5-flash-lite`; embedding `google/gemini-embedding-001`. Tên đổi theo thời gian, lấy đúng tên đang có.
- [ ] **Sửa `backend/.env`** (không commit file này):

```env
OPENROUTER_API_KEY=sk-or-v1-...
LLM_PROVIDER=openrouter
LLM_MODEL=google/gemini-3.6-flash
LLM_CHEAP_MODEL=google/gemini-3.5-flash-lite
VISION_PROVIDER=openrouter
VISION_MODEL=google/gemini-3.6-flash
EMBED_PROVIDER=openrouter
EMBED_MODEL=google/gemini-embedding-001
EMBED_DIM=768
```

`EMBED_DIM` **giữ 768** (cột vector trong DB là 768 chiều; script tự cắt và chuẩn hóa).

- [ ] **Kiểm tra nhanh:**

```powershell
cd backend
$env:PYTHONUTF8=1; uv run python -m scripts.check_openrouter
```

Kỳ vọng: 5 dòng OK. Có dòng LỖI thì đọc thông báo (thường là sai tên model, hết tiền, hoặc key sai).

- [ ] **Nhúng lại tài liệu cũ** (đã xử lý bằng `fake` hoặc Gemini):

```powershell
uv run python -m scripts.reembed
```

Kỳ vọng: in số đoạn đã nhúng lại; chạy lần hai báo 0. Sau bước này AI Tutor của các bài cũ hỏi được (không còn báo "model AI khác" sau plan hỏi chờ).

- [ ] **Khởi động lại:** `docker compose up -d --build api worker`. Tải một PDF mới, xem log worker: `docker compose logs -f worker` thấy `ingest_pdf` xong; hỏi AI Tutor có trích nguồn.
- [ ] **Theo dõi chi phí:** trang admin "Token AI 7 ngày" và openrouter.ai → Activity.

Quay về chế độ giả: đặt lại `*_PROVIDER=fake`, rồi chạy `reembed` một lần nữa (embedding giả có tên model khác).
