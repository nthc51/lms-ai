import math
from types import SimpleNamespace

from app.ai.embedder import FakeEmbedder, GeminiEmbedder, get_embedder
from app.ai.vision import FakeVision, get_vision
from app.core.config import Settings


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


async def test_fake_embedder_shape_norm_and_determinism():
    e = FakeEmbedder(768)
    [v1] = await e.embed_documents(["Tìm kiếm nhị phân"])
    v2 = await e.embed_query("Tìm kiếm nhị phân")
    assert len(v1) == 768 and e.model == "fake-768"
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-6)
    assert v1 == v2


async def test_fake_embedder_ignores_diacritics_and_ranks_related_higher():
    e = FakeEmbedder(768)
    a = await e.embed_query("Tìm kiếm nhị phân trên mảng đã sắp xếp")
    b = await e.embed_query("tim kiem nhi phan tren mang")
    c = await e.embed_query("mạng máy tính và giao thức TCP")
    assert cosine(a, b) > cosine(a, c)


async def test_fake_embedder_never_returns_zero_vector():
    [v] = await FakeEmbedder(8).embed_documents([""])
    assert any(v)


class _Models:
    def __init__(self):
        self.batch_sizes = []

    async def embed_content(self, model, contents, config):
        self.batch_sizes.append(len(contents))
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0]) for _ in contents])


async def test_gemini_embedder_batches_and_normalizes():
    models = _Models()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    e = GeminiEmbedder(api_key="x", model="gemini-embedding-001", dim=2, client=client)
    vectors = await e.embed_documents([f"t{i}" for i in range(250)])
    assert models.batch_sizes == [100, 100, 50]
    assert vectors[0] == [0.6, 0.8]


def test_factories_pick_fake_by_default():
    s = Settings(embed_provider="fake", vision_provider="fake", embed_dim=768)
    assert isinstance(get_embedder(s), FakeEmbedder)
    assert isinstance(get_vision(s), FakeVision)


async def test_fake_vision_records_calls():
    v = FakeVision()
    md = await v.page_to_markdown(b"\x89PNG...")
    assert v.calls == 1 and len(md) > 50
