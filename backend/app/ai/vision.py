import asyncio
from typing import Protocol

from app.ai.retry import Sleep, call_with_retry
from app.core.config import Settings

VISION_PROMPT = (
    "Chuyển nội dung trang tài liệu trong ảnh thành Markdown. Giữ nguyên tiếng Việt có dấu, "
    "heading, danh sách và bảng. Công thức toán viết dạng LaTeX trong $...$. "
    "Chỉ trả về Markdown, không giải thích thêm."
)


class VisionExtractor(Protocol):
    async def page_to_markdown(self, png: bytes) -> str: ...


class FakeVision:
    def __init__(
        self, text: str = "Nội dung được trích từ ảnh của trang tài liệu (chế độ giả lập, không gọi AI)."
    ):
        self.text = text
        self.calls = 0

    async def page_to_markdown(self, png: bytes) -> str:
        self.calls += 1
        return self.text


class GeminiVision:
    def __init__(
        self, api_key: str, model: str, client=None, *, timeout_s: float = 120.0, sleep: Sleep = asyncio.sleep
    ):
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self._model = model
        self._timeout_ms = int(timeout_s * 1000)
        self._sleep = sleep

    async def page_to_markdown(self, png: bytes) -> str:
        from google.genai import types

        contents = [types.Part.from_bytes(data=png, mime_type="image/png"), VISION_PROMPT]
        config = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=self._timeout_ms))
        resp = await call_with_retry(
            "vision",
            lambda: self._client.aio.models.generate_content(
                model=self._model, contents=contents, config=config
            ),
            sleep=self._sleep,
        )
        return (resp.text or "").strip()


def get_vision(s: Settings) -> VisionExtractor:
    if s.vision_provider == "gemini":
        return GeminiVision(s.gemini_api_key, s.vision_model, timeout_s=s.vision_timeout_s)
    return FakeVision()
