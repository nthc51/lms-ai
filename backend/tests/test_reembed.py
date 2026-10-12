"""scripts.reembed: đổi model embedding (vd. Gemini → OpenRouter) thì nhúng lại đoạn cũ, không đọc lại PDF."""

import uuid

import pytest
from sqlalchemy import select, update

from app.ai.embedder import FakeEmbedder
from app.ai.retrieval import SearchScope, count_ready_chunks
from app.core.db import SessionLocal
from app.modules.materials.models import Chunk
from scripts.reembed import count_stale, reembed
from tests.factories import seed_chunks
from tests.helpers import make_published_course, make_teacher


async def test_reembed_moves_old_chunks_to_current_model(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    await seed_chunks(db, uuid.UUID(lesson["id"]), ["Đạo hàm của hàm hằng", "Tích phân", "Giới hạn"])
    await db.execute(
        update(Chunk).values(embedding_model="google/gemini-embedding-001", embedding=[0.0] * 768)
    )
    await db.commit()
    embedder = FakeEmbedder(768)
    scope = SearchScope(uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
    assert await count_ready_chunks(db, scope, embedder.model) == 0  # AI Tutor không thấy đoạn của model cũ
    assert await count_stale(SessionLocal, embedder.model) == 3

    logs: list[str] = []
    assert await reembed(SessionLocal, embedder, batch=2, log=logs.append) == 3
    assert logs == ["Đã nhúng lại 2 đoạn", "Đã nhúng lại 3 đoạn"]
    db.expire_all()
    rows = (await db.execute(select(Chunk.content, Chunk.embedding_model, Chunk.embedding))).all()
    assert {m for _, m, _ in rows} == {embedder.model}
    for content, _, vector in rows:
        assert list(vector) == pytest.approx((await embedder.embed_documents([content]))[0], abs=1e-6)
    assert await count_ready_chunks(db, scope, embedder.model) == 3
    assert await reembed(SessionLocal, embedder) == 0  # chạy lại an toàn
