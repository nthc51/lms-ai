"""Nhúng lại (embedding) các đoạn tài liệu đã xử lý bằng EMBED_PROVIDER / EMBED_MODEL hiện tại.

Khi nào cần: sau khi đổi provider hoặc model embedding (vd. Gemini → OpenRouter, tên model đổi thành
google/gemini-embedding-001). AI Tutor chỉ tìm các đoạn có embedding_model trùng model đang dùng, nên đoạn cũ
không được tìm thấy cho tới khi nhúng lại. Script chỉ tính lại vector từ nội dung đã trích (không đọc lại PDF,
không gọi vision), chạy lại nhiều lần an toàn (chỉ xử lý đoạn còn khác model).

Chạy từ thư mục backend/ (đã đặt .env):  uv run python -m scripts.reembed
"""

import asyncio

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models_registry  # noqa: F401 — nạp mọi model (FK của chunks)
from app.ai.embedder import Embedder, get_embedder
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.materials.models import Chunk

BATCH = 100


async def count_stale(session_factory: async_sessionmaker, model: str) -> int:
    async with session_factory() as db:
        return await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding_model != model))


async def reembed(
    session_factory: async_sessionmaker, embedder: Embedder, *, batch: int = BATCH, log=print
) -> int:
    """Nhúng lại mọi đoạn có embedding_model khác embedder.model. Trả số đoạn đã cập nhật."""
    total = 0
    while True:
        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(Chunk.id, Chunk.content)
                    .where(Chunk.embedding_model != embedder.model)
                    .order_by(Chunk.id)
                    .limit(batch)
                )
            ).all()
            if not rows:
                return total
            vectors = await embedder.embed_documents([content for _, content in rows])
            for (chunk_id, _), vector in zip(rows, vectors, strict=True):
                await db.execute(
                    update(Chunk)
                    .where(Chunk.id == chunk_id)
                    .values(embedding=vector, embedding_model=embedder.model)
                )
            await db.commit()
        total += len(rows)
        log(f"Đã nhúng lại {total} đoạn")


async def main() -> None:
    s = get_settings()
    embedder = get_embedder(s)
    stale = await count_stale(SessionLocal, embedder.model)
    print(f"Model embedding hiện tại: {embedder.model} ({s.embed_provider}). Cần nhúng lại: {stale} đoạn.")
    done = await reembed(SessionLocal, embedder)
    print(f"Xong: {done} đoạn.")


if __name__ == "__main__":
    asyncio.run(main())
