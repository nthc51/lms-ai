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
