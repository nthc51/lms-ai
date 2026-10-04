import asyncio
import hashlib
import math
import re
import unicodedata
from functools import lru_cache
from typing import Protocol

from app.ai.retry import Sleep, call_with_retry
from app.core.config import Settings, get_settings


class Embedder(Protocol):
    model: str
    dim: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in values))
    return [x / norm for x in values] if norm else values


def _fold(text: str) -> str:
    text = text.lower().replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


class FakeEmbedder:
    """Embedding giả, tất định: băm từng từ (đã bỏ dấu) vào một ô của vector.
    Dùng cho test và dev không có API key; văn bản nhiều từ chung thì cosine cao."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.model = f"fake-{dim}"

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for token in re.findall(r"\w+", _fold(text)):
            h = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            v[h % self.dim] += 1.0
        if not any(v):
            v[0] = 1.0
        return _normalize(v)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class GeminiEmbedder:
    BATCH = 100

    def __init__(
        self,
        api_key: str,
        model: str,
        dim: int,
        client=None,
        *,
        timeout_s: float = 30.0,
        sleep: Sleep = asyncio.sleep,
    ):
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self._timeout_ms = int(timeout_s * 1000)
        self._sleep = sleep
        self.model = model
        self.dim = dim

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self.dim,
            http_options=types.HttpOptions(timeout=self._timeout_ms),
        )
        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            batch = texts[i : i + self.BATCH]
            resp = await call_with_retry(
                "embed",
                lambda b=batch: self._client.aio.models.embed_content(
                    model=self.model, contents=b, config=config
                ),
                sleep=self._sleep,
            )
            # Khi giảm số chiều, vector trả về không còn chuẩn hóa → tự chuẩn hóa để dùng cosine
            out.extend(_normalize(list(e.values)) for e in resp.embeddings)
        return out

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


def get_embedder(s: Settings) -> Embedder:
    if s.embed_provider == "gemini":
        return GeminiEmbedder(s.gemini_api_key, s.embed_model, s.embed_dim, timeout_s=s.embed_timeout_s)
    if s.embed_provider == "fake":
        return FakeEmbedder(s.embed_dim)
    raise ValueError(f"EMBED_PROVIDER không hợp lệ: {s.embed_provider!r} (chỉ nhận fake | gemini)")


@lru_cache
def get_api_embedder() -> Embedder:
    """Dependency FastAPI: embed câu hỏi của Tutor bằng đúng provider/model đã dùng lúc xử lý tài liệu."""
    return get_embedder(get_settings())
