import asyncio
import hashlib
import math
import re
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

from app.ai.retry import Sleep, call_with_retry
from app.core.config import Settings, get_settings
from app.ingestion.chunker import count_tokens

TPM_WINDOW_S = 60.0


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
    """Embedding qua Gemini. Gửi theo lô (tối đa `batch_size` đoạn). Khi `tpm_limit` > 0 thì tự giãn nhịp:
    ước lượng token mỗi lô (count_tokens), cắt lô sao cho không lô nào vượt giới hạn, và chờ trước khi gửi
    nếu tổng token đã gửi trong 60 giây gần nhất cộng lô mới sẽ vượt giới hạn (gói miễn phí: 30K TPM).
    Cửa sổ 60 giây gắn với instance, nên worker xử lý nhiều tài liệu liên tiếp vẫn giữ đúng nhịp."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dim: int,
        client=None,
        *,
        timeout_s: float = 30.0,
        batch_size: int = 100,
        tpm_limit: int = 0,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self._timeout_ms = int(timeout_s * 1000)
        self._sleep = sleep
        self._clock = clock
        self._batch_size = max(1, batch_size)
        self._tpm_limit = max(0, tpm_limit)
        self._sent: deque[tuple[float, int]] = deque()  # (thời điểm gửi, số token ước lượng)
        self.model = model
        self.dim = dim

    def _batches(self, texts: list[str]) -> list[list[str]]:
        batches: list[list[str]] = []
        cur: list[str] = []
        cur_tokens = 0
        for text in texts:
            t = count_tokens(text)
            too_many = len(cur) >= self._batch_size
            too_big = self._tpm_limit and cur and cur_tokens + t > self._tpm_limit
            if too_many or too_big:
                batches.append(cur)
                cur, cur_tokens = [], 0
            cur.append(text)  # một đoạn lớn hơn cả giới hạn vẫn được gửi riêng (không cắt được)
            cur_tokens += t
        if cur:
            batches.append(cur)
        return batches

    async def _wait_for_budget(self, tokens: int) -> None:
        if not self._tpm_limit:
            return
        while True:
            now = self._clock()
            while self._sent and now - self._sent[0][0] >= TPM_WINDOW_S:
                self._sent.popleft()
            used = sum(n for _, n in self._sent)
            if not self._sent or used + tokens <= self._tpm_limit:
                self._sent.append((now, tokens))
                return
            await self._sleep(self._sent[0][0] + TPM_WINDOW_S - now)

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self.dim,
            http_options=types.HttpOptions(timeout=self._timeout_ms),
        )
        out: list[list[float]] = []
        for batch in self._batches(texts):
            await self._wait_for_budget(sum(count_tokens(t) for t in batch))
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
        return GeminiEmbedder(
            s.gemini_api_key,
            s.embed_model,
            s.embed_dim,
            timeout_s=s.embed_timeout_s,
            batch_size=s.embed_batch_size,
            tpm_limit=s.embed_tpm_limit,
        )
    if s.embed_provider == "fake":
        return FakeEmbedder(s.embed_dim)
    raise ValueError(f"EMBED_PROVIDER không hợp lệ: {s.embed_provider!r} (chỉ nhận fake | gemini)")


@lru_cache
def get_api_embedder() -> Embedder:
    """Dependency FastAPI: embed câu hỏi của Tutor bằng đúng provider/model đã dùng lúc xử lý tài liệu."""
    return get_embedder(get_settings())
