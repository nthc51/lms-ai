"""Kiểm tra nhanh các model Gemini trong .env có gọi được không (không cần Docker).

Chạy từ thư mục backend/:  $env:PYTHONUTF8=1; uv run python -m scripts.check_models
Gọi đúng cấu hình app dùng (temperature 0, JSON schema cho LLM_MODEL), in OK/LỖI + độ trễ cho từng model.
"""

import asyncio
import sys
import time

from google import genai
from google.genai import types

from app.core.config import get_settings

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


async def check(client: genai.Client, label: str, model: str, *, json_mode: bool = False) -> bool:
    cfg = types.GenerateContentConfig(
        temperature=0,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),  # như app: tắt cảnh báo AFC
        **({"response_mime_type": "application/json", "response_json_schema": SCHEMA} if json_mode else {}),
    )
    start = time.perf_counter()
    try:
        resp = await client.aio.models.generate_content(
            model=model, contents="Thủ đô của Việt Nam là gì? Trả lời ngắn.", config=cfg
        )
        text = (resp.text or "").strip().replace("\n", " ")[:80]
        print(f"OK   {label:<16} {model:<28} {time.perf_counter() - start:5.1f}s  → {text}")
        return True
    except Exception as e:  # noqa: BLE001 — in lỗi gọn để người dùng đọc
        print(f"LỖI  {label:<16} {model:<28} → {str(e)[:200]}")
        return False


async def main() -> int:
    s = get_settings()
    if not s.gemini_api_key.strip():
        print("Thiếu GEMINI_API_KEY trong backend/.env")
        return 1
    client = genai.Client(api_key=s.gemini_api_key)
    ok = [
        await check(client, "LLM_MODEL", s.llm_model),
        await check(client, "LLM_MODEL (JSON)", s.llm_model, json_mode=True),
        await check(client, "LLM_CHEAP_MODEL", s.llm_cheap_model),
        await check(client, "VISION_MODEL", s.vision_model),
    ]
    start = time.perf_counter()
    try:
        r = await client.aio.models.embed_content(
            model=s.embed_model,
            contents=["tìm kiếm nhị phân"],
            config=types.EmbedContentConfig(output_dimensionality=s.embed_dim),
        )
        dim = len(r.embeddings[0].values)
        good = dim == s.embed_dim
        print(
            f"{'OK ' if good else 'LỖI'}  {'EMBED_MODEL':<16} {s.embed_model:<28} {time.perf_counter() - start:5.1f}s  → {dim} chiều"
        )
        ok.append(good)
    except Exception as e:  # noqa: BLE001
        print(f"LỖI  {'EMBED_MODEL':<16} {s.embed_model:<28} → {str(e)[:200]}")
        ok.append(False)
    print("TẤT CẢ OK" if all(ok) else "CÓ MODEL LỖI: sửa tên model trong backend/.env rồi chạy lại")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
