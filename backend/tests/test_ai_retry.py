"""Timeout + retry của GeminiEmbedder / GeminiVision (không gọi mạng, không ngủ thật)."""
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from app.ai.embedder import GeminiEmbedder
from app.ai.vision import GeminiVision


def api_error(code: int, headers: dict | None = None) -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    body = {"error": {"code": code, "message": "boom", "status": "X"}}
    return cls(code, body, httpx.Response(code, headers=headers or {}))


class Sleeps:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class ScriptedModels:
    """Mỗi lần gọi lấy phần tử kế tiếp trong script: exception thì raise, còn lại coi là thành công."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.configs = []

    def _next(self, config):
        self.calls += 1
        self.configs.append(config)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item

    async def embed_content(self, model, contents, config):
        self._next(config)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0]) for _ in contents])

    async def generate_content(self, model, contents, config=None):
        self._next(config)
        return SimpleNamespace(text="  # Trang 1  ")


def embedder(script, sleep, **kw):
    models = ScriptedModels(script)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiEmbedder("x", "gemini-embedding-001", 2, client=client, sleep=sleep, **kw), models


def vision(script, sleep, **kw):
    models = ScriptedModels(script)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiVision("x", "gemini-2.5-flash", client=client, sleep=sleep, **kw), models


async def test_429_twice_then_success_backs_off_exponentially():
    sleep = Sleeps()
    e, models = embedder([api_error(429), api_error(429), None], sleep)
    assert await e.embed_query("q") == [0.6, 0.8]
    assert models.calls == 3
    assert len(sleep.delays) == 2 and sleep.delays[1] > sleep.delays[0] > 0
    assert sleep.delays == [1.0, 2.0]


async def test_503_then_success():
    sleep = Sleeps()
    v, models = vision([api_error(503), None], sleep)
    assert await v.page_to_markdown(b"png") == "# Trang 1"
    assert models.calls == 2 and sleep.delays == [1.0]


async def test_timeout_then_success():
    sleep = Sleeps()
    e, models = embedder([httpx.ReadTimeout("slow"), None], sleep)
    assert await e.embed_query("q") == [0.6, 0.8]
    assert models.calls == 2 and sleep.delays == [1.0]


async def test_asyncio_timeout_is_retried_too():
    sleep = Sleeps()
    v, models = vision([TimeoutError(), None], sleep)
    assert await v.page_to_markdown(b"png") == "# Trang 1"
    assert models.calls == 2


@pytest.mark.parametrize("code", [400, 401, 403, 404])
async def test_other_4xx_fails_immediately(code):
    sleep = Sleeps()
    e, models = embedder([api_error(code), None], sleep)
    with pytest.raises(errors.ClientError) as exc:
        await e.embed_query("q")
    assert exc.value.code == code
    assert models.calls == 1 and sleep.delays == []


async def test_vision_401_fails_immediately():
    sleep = Sleeps()
    v, models = vision([api_error(401), None], sleep)
    with pytest.raises(errors.ClientError):
        await v.page_to_markdown(b"png")
    assert models.calls == 1 and sleep.delays == []


async def test_retry_after_header_overrides_backoff():
    sleep = Sleeps()
    e, _ = embedder([api_error(429, {"Retry-After": "7"}), None], sleep)
    await e.embed_query("q")
    assert sleep.delays == [7.0]


async def test_unparseable_retry_after_falls_back_to_backoff():
    sleep = Sleeps()
    e, _ = embedder([api_error(429, {"Retry-After": "soon"}), None], sleep)
    await e.embed_query("q")
    assert sleep.delays == [1.0]


async def test_gives_up_after_three_retries():
    sleep = Sleeps()
    e, models = embedder([api_error(429)] * 4 + [None], sleep)
    with pytest.raises(errors.ClientError) as exc:
        await e.embed_query("q")
    assert exc.value.code == 429
    assert models.calls == 4 and sleep.delays == [1.0, 2.0, 4.0]


async def test_timeout_is_passed_to_each_request():
    e, em = embedder([None], Sleeps(), timeout_s=12.5)
    await e.embed_query("q")
    assert em.configs[0].http_options.timeout == 12500
    v, vm = vision([None], Sleeps(), timeout_s=30)
    await v.page_to_markdown(b"png")
    assert vm.configs[0].http_options.timeout == 30000


async def test_real_sdk_client_over_mock_transport():
    """Đi qua google-genai thật (không mạng): 429 + Retry-After → ClientError có header; ReadTimeout
    thô được thử lại; timeout truyền xuống từng request; SDK không tự retry thêm."""
    from google import genai
    from google.genai import types

    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.extensions.get("timeout"))
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"},
                                  json={"error": {"code": 429, "message": "q", "status": "RESOURCE_EXHAUSTED"}})
        if len(seen) == 2:
            raise httpx.ReadTimeout("slow", request=req)
        return httpx.Response(200, json={"embeddings": [{"values": [3.0, 4.0]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = genai.Client(api_key="x", http_options=types.HttpOptions(httpx_async_client=http))
        sleep = Sleeps()
        e = GeminiEmbedder("x", "gemini-embedding-001", 2, client=client, timeout_s=12.5, sleep=sleep)
        assert await e.embed_query("q") == [0.6, 0.8]
    assert sleep.delays == [7.0, 2.0]
    assert len(seen) == 3 and all(t["read"] == 12.5 for t in seen)
