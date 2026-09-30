"""Lớp gọi LLM dùng chung (spec 5.0). Mọi lời gọi LLM trong dự án đều đi qua LLMClient:

- timeout riêng theo loại lời gọi (op), là giới hạn TỔNG cho mỗi lần thử (asyncio.timeout), vì timeout của
  SDK Gemini (HttpOptions.timeout) chỉ tính cho từng thao tác mạng;
- retry khi 429/5xx/timeout qua call_with_retry (tối đa 3 lần, Retry-After tối đa 60 giây);
- cache trong bảng llm_cache theo hash(provider + model + prompt [+ JSON schema]); chỉ cache output hợp lệ;
- log token, độ trễ, prompt_version;
- output có cấu trúc: gửi JSON schema cho provider rồi validate lại bằng Pydantic."""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.llm import LLMProvider, ProviderResult, get_llm_provider
from app.ai.models import LLMCache
from app.ai.prompts import RenderedPrompt
from app.ai.retry import Sleep, call_with_retry
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal

logger = logging.getLogger("app.ai")

_FENCE_RE = re.compile(r"\A\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*\Z", re.DOTALL)


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cached: bool


class LLMOutputError(Exception):
    """Output có cấu trúc không khớp schema. Không được ghi cache; caller quyết định retry hay bỏ."""

    def __init__(self, op: str, raw: str, error: str, result: LLMResult):
        super().__init__(f"{op}: output không hợp lệ: {error}")
        self.op = op
        self.raw = raw
        self.error = error
        self.result = result


def cache_key(provider: str, model: str, prompt: str, json_schema: dict | None = None) -> str:
    h = hashlib.sha256()
    schema = json.dumps(json_schema, sort_keys=True, ensure_ascii=False) if json_schema is not None else ""
    for part in (provider, model, prompt, schema):
        h.update(part.encode())
        h.update(b"\0")
    return h.hexdigest()


def strip_json_fence(text: str) -> str:
    """Một số model vẫn bọc JSON trong ```json ... ``` dù đã bật JSON mode."""
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        settings: Settings,
        *,
        session_factory: async_sessionmaker = SessionLocal,
        sleep: Sleep = asyncio.sleep,
    ):
        self.provider = provider
        self._settings = settings
        self._session_factory = session_factory
        self._sleep = sleep

    def timeout_for(self, op: str) -> float:
        s = self._settings
        return {"tutor_rewrite": s.llm_rewrite_timeout_s, "tutor_answer": s.llm_stream_timeout_s}.get(
            op, s.llm_timeout_s
        )

    def _caching(self, use_cache: bool) -> bool:
        return use_cache and self._settings.llm_cache_enabled

    async def _cache_get(self, key: str) -> str | None:
        async with self._session_factory() as db:
            text = await db.scalar(
                update(LLMCache)
                .where(LLMCache.key_hash == key)
                .values(hit_count=LLMCache.hit_count + 1)
                .returning(LLMCache.response)
            )
            await db.commit()
        return text

    async def _cache_put(self, key: str, model: str, text: str) -> None:
        async with self._session_factory() as db:
            await db.execute(
                pg_insert(LLMCache)
                .values(key_hash=key, provider=self.provider.name, model=model, response=text)
                .on_conflict_do_nothing(index_elements=["key_hash"])
            )
            await db.commit()

    @staticmethod
    def _log(
        op: str,
        prompt: RenderedPrompt,
        model: str,
        status: str,
        *,
        cached: bool,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
    ) -> None:
        logger.info(
            "llm_call op=%s model=%s prompt_version=%s status=%s cached=%s tokens_in=%d tokens_out=%d "
            "latency_ms=%d",
            op,
            model,
            prompt.prompt_version,
            status,
            cached,
            tokens_in,
            tokens_out,
            latency_ms,
        )

    async def _attempt(
        self, prompt: RenderedPrompt, *, op: str, model: str, timeout_s: float, json_schema: dict | None
    ) -> ProviderResult:
        # Giới hạn tổng cho một lần thử; TimeoutError được call_with_retry coi là lỗi retry được.
        async with asyncio.timeout(timeout_s):
            return await self.provider.generate(
                prompt.text, op=op, model=model, timeout_s=timeout_s, json_schema=json_schema
            )

    async def _complete[T](
        self,
        prompt: RenderedPrompt,
        *,
        op: str,
        model: str | None,
        timeout_s: float | None,
        json_schema: dict | None,
        parse: Callable[[str], T],
        use_cache: bool,
    ) -> tuple[T, LLMResult]:
        model = model or self._settings.llm_model
        timeout_s = timeout_s or self.timeout_for(op)
        caching = self._caching(use_cache)
        key = cache_key(self.provider.name, model, prompt.text, json_schema)
        start = time.perf_counter()
        if caching and (hit := await self._cache_get(key)) is not None:
            try:
                parsed = parse(hit)
            except ValueError:  # bản cache không còn khớp schema hiện tại: gọi lại provider
                pass
            else:
                result = LLMResult(hit, model, prompt.prompt_version, 0, 0, _ms(start), cached=True)
                self._log(
                    op,
                    prompt,
                    model,
                    "ok",
                    cached=True,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=result.latency_ms,
                )
                return parsed, result
        res = await call_with_retry(
            op,
            lambda: self._attempt(prompt, op=op, model=model, timeout_s=timeout_s, json_schema=json_schema),
            sleep=self._sleep,
        )
        result = LLMResult(
            res.text, model, prompt.prompt_version, res.tokens_in, res.tokens_out, _ms(start), cached=False
        )
        try:
            parsed = parse(res.text)
        except ValueError as e:  # pydantic.ValidationError là ValueError
            self._log(
                op,
                prompt,
                model,
                "invalid_output",
                cached=False,
                tokens_in=res.tokens_in,
                tokens_out=res.tokens_out,
                latency_ms=result.latency_ms,
            )
            raise LLMOutputError(op, res.text, str(e)[:1000], result) from None
        self._log(
            op,
            prompt,
            model,
            "ok",
            cached=False,
            tokens_in=res.tokens_in,
            tokens_out=res.tokens_out,
            latency_ms=result.latency_ms,
        )
        if caching:
            await self._cache_put(key, model, res.text)
        return parsed, result

    async def generate(
        self,
        prompt: RenderedPrompt,
        *,
        op: str,
        model: str | None = None,
        timeout_s: float | None = None,
        use_cache: bool = True,
    ) -> LLMResult:
        _, result = await self._complete(
            prompt, op=op, model=model, timeout_s=timeout_s, json_schema=None, parse=str, use_cache=use_cache
        )
        return result

    async def generate_json[M: BaseModel](
        self,
        prompt: RenderedPrompt,
        schema: type[M],
        *,
        op: str,
        model: str | None = None,
        timeout_s: float | None = None,
        use_cache: bool = True,
    ) -> tuple[M, LLMResult]:
        return await self._complete(
            prompt,
            op=op,
            model=model,
            timeout_s=timeout_s,
            json_schema=schema.model_json_schema(),
            parse=lambda text: schema.model_validate_json(strip_json_fence(text)),
            use_cache=use_cache,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    """Dependency FastAPI. Test override bằng LLMClient bọc FakeLLMProvider (tests/conftest.py)."""
    s = get_settings()
    return LLMClient(get_llm_provider(s), s)
