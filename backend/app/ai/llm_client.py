"""Lớp gọi LLM dùng chung (spec 5.0). Mọi lời gọi LLM trong dự án đều đi qua LLMClient:

- timeout riêng theo loại lời gọi (op), là giới hạn TỔNG cho mỗi lần thử (asyncio.timeout), vì timeout của
  SDK Gemini (HttpOptions.timeout) chỉ tính cho từng thao tác mạng;
- retry khi 429/5xx/timeout qua call_with_retry (tối đa 3 lần, Retry-After tối đa 60 giây);
- cache trong bảng llm_cache theo hash(provider + model + prompt [+ JSON schema]); chỉ cache output hợp lệ;
- log token, độ trễ, prompt_version;
- stream (LLMClient.stream): retry chỉ lúc mở, luôn đóng upstream khi thoát khối, cache khi nhận hết;
- output có cấu trúc: gửi JSON schema cho provider rồi validate lại bằng Pydantic."""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterable, AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache

import anyio
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.llm import LLMProvider, ProviderResult, ProviderStream, get_llm_provider, split_pieces
from app.ai.models import LLMCache
from app.ai.prompts import RenderedPrompt
from app.ai.retry import Sleep, call_with_retry
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.ingestion.chunker import count_tokens

logger = logging.getLogger("app.ai")

_FENCE_RE = re.compile(r"\A\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*\Z", re.DOTALL | re.IGNORECASE)


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


class LLMStream:
    """Câu trả lời đang stream (dùng qua `async with LLMClient.stream(...)`).

    text/parts: phần đã nhận; completed: upstream đã chạy hết bình thường; cached: phát lại từ llm_cache.
    tokens_*: số provider báo (thường chỉ có khi stream chạy hết); không có thì ước lượng 1.4 × số từ, để lúc
    bị ngắt giữa chừng vẫn lưu được số token đã tiêu (spec 5.3 bước 6). Câu trả lời lấy từ cache: 0 token.
    Mỗi lần đọc upstream chịu chung một hạn chót (deadline, giờ của event loop) nên stream bị treo giữa chừng
    ném TimeoutError; lỗi giữa chừng không được retry."""

    def __init__(
        self,
        pieces: AsyncIterable[str],
        prompt: RenderedPrompt,
        upstream: ProviderStream | None,
        *,
        deadline: float | None = None,
    ):
        self._it = aiter(pieces)
        self._prompt = prompt
        self._upstream = upstream
        self._deadline = deadline
        self._done = False
        self.cached = upstream is None
        self.parts: list[str] = []
        self.completed = False

    @property
    def text(self) -> str:
        return "".join(self.parts)

    @property
    def finish_reason(self) -> str | None:
        return None if self._upstream is None else self._upstream.finish_reason

    @property
    def tokens_in(self) -> int:
        if self._upstream is None:
            return 0
        reported = self._upstream.tokens_in
        return reported if reported is not None else count_tokens(self._prompt.text)

    @property
    def tokens_out(self) -> int:
        if self._upstream is None:
            return 0
        reported = self._upstream.tokens_out
        return reported if reported is not None else count_tokens(self.text)

    def __aiter__(self) -> "LLMStream":
        return self

    async def __anext__(self) -> str:
        if self._done:
            raise StopAsyncIteration
        try:
            if self._deadline is None:
                piece = await anext(self._it)
            else:
                async with asyncio.timeout_at(self._deadline):
                    piece = await anext(self._it)
        except StopAsyncIteration:
            self._done = True
            self.completed = True
            raise
        except BaseException:
            self._done = True
            raise
        self.parts.append(piece)
        return piece

    async def aclose(self) -> None:
        """Đóng iterator và stream upstream. Gọi lại nhiều lần an toàn."""
        self._done = True
        close = getattr(self._it, "aclose", None)
        if close is not None:
            await close()
        if self._upstream is not None:
            await self._upstream.aclose()

    @property
    def truncated(self) -> bool:
        """Câu trả lời chưa sinh xong: chưa nhận hết (ngắt, lỗi, bị hủy) hoặc provider dừng vì lý do khác STOP
        (MAX_TOKENS, SAFETY...). Dùng cho chat_messages.truncated."""
        return not self.completed or self.finish_reason not in (None, "STOP")

    @property
    def cacheable(self) -> bool:
        """Chỉ cache câu trả lời đã nhận hết, không rỗng, kết thúc bình thường (STOP hoặc provider không báo)."""
        return self.completed and bool(self.text.strip()) and self.finish_reason in (None, "STOP")


async def _replay(text: str) -> AsyncIterator[str]:
    for piece in split_pieces(text):
        await asyncio.sleep(0)
        yield piece


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
        """Best-effort: DB lỗi thì coi như cache miss (ghi cảnh báo), lời gọi vẫn tiếp tục."""
        try:
            async with self._session_factory() as db:
                text = await db.scalar(
                    update(LLMCache)
                    .where(LLMCache.key_hash == key)
                    .values(hit_count=LLMCache.hit_count + 1)
                    .returning(LLMCache.response)
                )
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — cache không được làm hỏng lời gọi LLM
            logger.warning("llm_cache read failed key=%s error=%r", key, exc)
            return None
        return text

    async def _cache_put(self, key: str, model: str, text: str) -> None:
        """Best-effort: DB lỗi thì chỉ ghi cảnh báo, không bỏ kết quả LLM đã trả tiền.
        Trùng key (bản cũ không còn parse được) thì ghi đè response/model, giữ hit_count."""
        stmt = pg_insert(LLMCache).values(
            key_hash=key, provider=self.provider.name, model=model, response=text
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key_hash"],
            set_={"response": stmt.excluded.response, "model": stmt.excluded.model},
        )
        try:
            async with self._session_factory() as db:
                await db.execute(stmt)
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — cache không được làm hỏng lời gọi LLM
            logger.warning("llm_cache write failed key=%s error=%r", key, exc)

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
        finish_reason: str | None = None,
    ) -> None:
        logger.info(
            "llm_call op=%s model=%s prompt_version=%s status=%s cached=%s tokens_in=%d tokens_out=%d "
            "latency_ms=%d finish_reason=%s",
            op,
            model,
            prompt.prompt_version,
            status,
            cached,
            tokens_in,
            tokens_out,
            latency_ms,
            finish_reason,
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
        finish_reason = res.finish_reason

        def log(status: str) -> None:
            self._log(
                op,
                prompt,
                model,
                status,
                cached=False,
                tokens_in=res.tokens_in,
                tokens_out=res.tokens_out,
                latency_ms=result.latency_ms,
                finish_reason=finish_reason,
            )

        # Output rỗng (bị chặn an toàn, hết token trước khi có chữ...) không bao giờ là câu trả lời hợp lệ.
        # Ném sau call_with_retry nên không bị retry; caller quyết định.
        if not res.text.strip():
            log("empty_output")
            raise LLMOutputError(op, res.text, f"output rỗng (finish_reason={finish_reason})", result)
        try:
            parsed = parse(res.text)
        except ValueError as e:  # pydantic.ValidationError là ValueError
            log("invalid_output")
            raise LLMOutputError(op, res.text, str(e)[:1000], result) from None
        # Chỉ cache output kết thúc bình thường; bị cắt (MAX_TOKENS, SAFETY...) vẫn trả về nhưng không cache.
        complete = finish_reason in (None, "STOP")
        log("ok" if complete else "incomplete")
        if caching and complete:
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

    async def _open_stream(
        self, prompt: RenderedPrompt, *, op: str, model: str, timeout_s: float
    ) -> tuple[ProviderStream, float]:
        """Một lần thử mở stream (gồm mảnh đầu). timeout_s là giới hạn tổng cho cả lần thử: phần đọc tiếp theo
        dùng chung hạn chót đó."""
        deadline = asyncio.get_running_loop().time() + timeout_s
        async with asyncio.timeout_at(deadline):
            upstream = await self.provider.open_stream(prompt.text, op=op, model=model, timeout_s=timeout_s)
        return upstream, deadline

    @asynccontextmanager
    async def stream(
        self,
        prompt: RenderedPrompt,
        *,
        op: str,
        model: str | None = None,
        timeout_s: float | None = None,
        use_cache: bool = True,
    ) -> AsyncIterator[LLMStream]:
        """Stream câu trả lời trong `async with` (spec 5.3 bước 6): thoát khỏi khối theo bất kỳ cách nào
        (xong, break khi client ngắt, lỗi, bị hủy) đều đóng stream upstream. Retry chỉ áp dụng lúc mở
        stream (trước token đầu); lỗi giữa chừng ném ra cho caller. Chỉ ghi cache khi đã nhận hết, không rỗng,
        finish_reason là STOP/None và khối `async with` kết thúc không lỗi. Cache hit được phát lại dạng stream."""
        model = model or self._settings.llm_model
        timeout_s = timeout_s or self.timeout_for(op)
        caching = self._caching(use_cache)
        key = cache_key(self.provider.name, model, prompt.text)
        start = time.perf_counter()
        hit = await self._cache_get(key) if caching else None
        if hit is not None:
            self._log(op, prompt, model, "ok", cached=True, tokens_in=0, tokens_out=0, latency_ms=_ms(start))
            replay = LLMStream(_replay(hit), prompt, None)
            try:
                yield replay
            finally:
                await replay.aclose()
            return
        upstream, deadline = await call_with_retry(
            op,
            lambda: self._open_stream(prompt, op=op, model=model, timeout_s=timeout_s),
            sleep=self._sleep,
        )
        stream = LLMStream(upstream, prompt, upstream, deadline=deadline)
        status = "error"
        try:
            yield stream
            if not stream.completed:
                status = "truncated"
            elif stream.finish_reason in (None, "STOP"):
                status = "ok"
            else:
                status = "incomplete"
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        finally:
            with anyio.CancelScope(shield=True):  # bị hủy (client ngắt) vẫn đóng được upstream
                await stream.aclose()
            self._log(
                op,
                prompt,
                model,
                status,
                cached=False,
                tokens_in=stream.tokens_in,
                tokens_out=stream.tokens_out,
                latency_ms=_ms(start),
                finish_reason=stream.finish_reason,
            )
        if caching and stream.cacheable:
            await self._cache_put(key, model, stream.text)


@lru_cache
def get_llm_client() -> LLMClient:
    """Dependency FastAPI. Test override bằng LLMClient bọc FakeLLMProvider (tests/conftest.py)."""
    s = get_settings()
    return LLMClient(get_llm_provider(s), s)
