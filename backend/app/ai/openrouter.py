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
