"""LLMProvider (spec K6): interface + bản giả tất định + bản Gemini.

Provider chỉ gửi một request. Timeout theo loại lời gọi, retry, cache và log nằm ở lớp dùng chung
LLMClient (app/ai/llm_client.py) — mọi lời gọi LLM đều phải đi qua lớp đó."""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.ingestion.chunker import count_tokens

_PIECE_RE = re.compile(r"\s*\S+")


def split_pieces(text: str) -> list[str]:
    """Cắt văn bản thành các mảnh (mỗi mảnh một từ kèm khoảng trắng phía trước) để giả lập stream."""
    return _PIECE_RE.findall(text)


@dataclass
class ProviderResult:
    text: str
    tokens_in: int
    tokens_out: int


class ProviderStream(Protocol):
    """Stream đã mở: request đã gửi, lỗi kết nối/429/5xx đã ném ra lúc mở. tokens_*: None cho tới khi provider
    báo usage (thường ở mảnh cuối; stream bị dừng giữa chừng thì không có)."""

    tokens_in: int | None
    tokens_out: int | None

    def __aiter__(self) -> AsyncIterator[str]: ...
    async def aclose(self) -> None: ...


class LLMProvider(Protocol):
    name: str

    async def generate(
        self, prompt: str, *, op: str, model: str, timeout_s: float, json_schema: dict | None = None
    ) -> ProviderResult: ...

    async def open_stream(self, prompt: str, *, op: str, model: str, timeout_s: float) -> ProviderStream: ...


# ---------------------------------------------------------------- bản giả


@dataclass
class FakeCall:
    op: str
    prompt: str
    model: str
    timeout_s: float
    json_schema: dict | None
    stream: bool


type FakeReply = str | BaseException | Callable[[FakeCall], str]


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i + len(start) : j].strip() if j >= 0 else ""


def _fake_questions(source: str, count: int) -> dict:
    words = source.split() or ["tài", "liệu"]
    questions = []
    for i in range(count):
        window = " ".join(words[i * 5 : i * 5 + 10]) or " ".join(words[:10])
        questions.append(
            {
                "stem": f"Câu {i + 1}: nội dung nào đúng theo đoạn “{window}”?",
                "options": [{"id": x, "text": f"Phương án {x} của câu {i + 1}"} for x in "ABCD"],
                "correct_option_id": "A",
                "explanation": "Câu hỏi mô phỏng (chế độ giả lập, không gọi AI).",
                "difficulty": "medium",
            }
        )
    return {"questions": questions}


def default_reply(call: FakeCall) -> str:
    """Trả lời mặc định theo loại lời gọi, đủ để dev/smoke test chạy trọn luồng mà không cần API key."""
    if call.op == "tutor_rewrite":
        return _between(call.prompt, "<question>", "</question>") or "câu hỏi"
    if call.op == "tutor_answer":
        return "Theo tài liệu [1], đây là câu trả lời mô phỏng (chế độ giả lập, không gọi AI)."
    if call.op == "quiz_generate":
        m = re.search(r"Số câu cần sinh: (\d+)", call.prompt)
        source = _between(call.prompt, "<source>", "</source>")
        return json.dumps(_fake_questions(source, int(m.group(1)) if m else 2), ensure_ascii=False)
    if call.op == "quiz_self_check":
        return json.dumps({"answer_option_id": "A"})
    return "OK"


class FakeStream:
    def __init__(
        self,
        text: str,
        *,
        tokens_in: int,
        gate: asyncio.Event | None,
        error: tuple[int, BaseException] | None,
    ):
        self._pieces = split_pieces(text)
        self._text = text
        self._tokens_in = tokens_in
        self._gate = gate
        self._error = error
        self.tokens_in: int | None = None
        self.tokens_out: int | None = None
        self.closed = False

    def __aiter__(self) -> AsyncIterator[str]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[str]:
        for i, piece in enumerate(self._pieces):
            if self._error is not None and i == self._error[0]:
                raise self._error[1]
            if i == 1 and self._gate is not None:
                await self._gate.wait()
            await asyncio.sleep(0)
            yield piece
        # như Gemini: usage chỉ có ở mảnh cuối
        self.tokens_in = self._tokens_in
        self.tokens_out = count_tokens(self._text)

    async def aclose(self) -> None:
        self.closed = True


class FakeLLMProvider:
    """LLM giả, tất định. Test luôn dùng bản này (spec 8); dev/smoke dùng khi LLM_PROVIDER=fake.

    replies: trả lời theo thứ tự gọi — chuỗi, exception (bị ném ra) hoặc hàm nhận FakeCall. Hết danh sách
    thì dùng reply_for (mặc định default_reply). stream_gate: stream dừng trước mảnh thứ hai cho tới khi
    event được set. stream_error=(i, exc): stream ném exc ngay trước mảnh thứ i."""

    name = "fake"

    def __init__(
        self,
        replies: list[FakeReply] | None = None,
        *,
        reply_for: Callable[[FakeCall], str] | None = None,
        stream_gate: asyncio.Event | None = None,
        stream_error: tuple[int, BaseException] | None = None,
    ):
        self.replies: list[FakeReply] = list(replies or [])
        self.reply_for = reply_for or default_reply
        self.stream_gate = stream_gate
        self.stream_error = stream_error
        self.calls: list[FakeCall] = []
        self.streams: list[FakeStream] = []

    def _reply(self, call: FakeCall) -> str:
        self.calls.append(call)
        item = self.replies.pop(0) if self.replies else self.reply_for
        if isinstance(item, BaseException):
            raise item
        return item(call) if callable(item) else item

    async def generate(
        self, prompt: str, *, op: str, model: str, timeout_s: float, json_schema: dict | None = None
    ) -> ProviderResult:
        text = self._reply(FakeCall(op, prompt, model, timeout_s, json_schema, stream=False))
        return ProviderResult(text=text, tokens_in=count_tokens(prompt), tokens_out=count_tokens(text))

    async def open_stream(self, prompt: str, *, op: str, model: str, timeout_s: float) -> FakeStream:
        text = self._reply(FakeCall(op, prompt, model, timeout_s, None, stream=True))
        stream = FakeStream(
            text, tokens_in=count_tokens(prompt), gate=self.stream_gate, error=self.stream_error
        )
        self.streams.append(stream)
        return stream


# ---------------------------------------------------------------- Gemini


class _GeminiStream:
    def __init__(self, first, rest):
        self._first = first
        self._rest = rest
        self.tokens_in: int | None = None
        self.tokens_out: int | None = None

    def _usage(self, chunk) -> None:
        usage = getattr(chunk, "usage_metadata", None)
        if usage is not None:
            self.tokens_in = usage.prompt_token_count or self.tokens_in
            self.tokens_out = usage.candidates_token_count or self.tokens_out

    def __aiter__(self) -> AsyncIterator[str]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[str]:
        if self._first is not None:
            first, self._first = self._first, None
            self._usage(first)
            if first.text:
                yield first.text
        async for chunk in self._rest:
            self._usage(chunk)
            if chunk.text:
                yield chunk.text

    async def aclose(self) -> None:
        aclose = getattr(self._rest, "aclose", None)
        if aclose is not None:
            await aclose()


class GeminiLLM:
    name = "gemini"

    def __init__(self, api_key: str, client=None):
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client

    @staticmethod
    def _config(timeout_s: float, json_schema: dict | None = None):
        from google.genai import types

        extra = (
            {"response_mime_type": "application/json", "response_json_schema": json_schema}
            if json_schema is not None
            else {}
        )
        return types.GenerateContentConfig(
            temperature=0, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)), **extra
        )

    async def generate(
        self, prompt: str, *, op: str, model: str, timeout_s: float, json_schema: dict | None = None
    ) -> ProviderResult:
        resp = await self._client.aio.models.generate_content(
            model=model, contents=prompt, config=self._config(timeout_s, json_schema)
        )
        text = (resp.text or "").strip()
        usage = resp.usage_metadata
        return ProviderResult(
            text=text,
            tokens_in=(usage.prompt_token_count if usage else None) or count_tokens(prompt),
            tokens_out=(usage.candidates_token_count if usage else None) or count_tokens(text),
        )

    async def open_stream(self, prompt: str, *, op: str, model: str, timeout_s: float) -> _GeminiStream:
        rest = await self._client.aio.models.generate_content_stream(
            model=model, contents=prompt, config=self._config(timeout_s)
        )
        # Lấy trước mảnh đầu: lỗi 429/5xx/timeout ném ra ngay lúc mở (trước khi có token nào),
        # nên LLMClient retry được việc mở stream.
        try:
            first = await anext(rest)
        except StopAsyncIteration:
            first = None
        return _GeminiStream(first, rest)


def get_llm_provider(s: Settings) -> LLMProvider:
    if s.llm_provider == "gemini":
        return GeminiLLM(s.gemini_api_key)
    return FakeLLMProvider()
