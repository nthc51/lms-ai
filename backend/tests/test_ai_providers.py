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


class _Clock:
    """Đồng hồ giả: sleep() tua thời gian thay vì ngủ thật."""

    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.slept.append(delay)
        self.now += delay


def _paced(models, clock, **kw):
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiEmbedder(
        api_key="x", model="gemini-embedding-001", dim=2, client=client, sleep=clock.sleep, clock=clock, **kw
    )


async def test_embedder_batch_size_setting_is_respected():
    models, clock = _Models(), _Clock()
    await _paced(models, clock, batch_size=20).embed_documents([f"t{i}" for i in range(45)])
    assert models.batch_sizes == [20, 20, 5]
    assert clock.slept == []  # không đặt tpm_limit → không bao giờ chờ


async def test_embedder_tpm_limit_splits_batches_and_waits_for_the_window():
    # mỗi đoạn 100 từ ≈ count_tokens > 100 token; giới hạn 300 token/phút → mỗi lô chỉ chứa được vài đoạn
    from app.ingestion.chunker import count_tokens

    text = " ".join(["điều chế"] * 50)
    per = count_tokens(text)
    limit = per * 2
    models, clock = _Models(), _Clock()
    e = _paced(models, clock, tpm_limit=limit)
    await e.embed_documents([text] * 5)
    assert models.batch_sizes == [2, 2, 1]  # không lô nào vượt giới hạn
    # lô 2 phải đợi lô 1 ra khỏi cửa sổ 60 giây, lô 3 đợi lô 2
    assert clock.slept == [60.0, 60.0]


async def test_embedder_tpm_window_persists_across_calls():
    from app.ingestion.chunker import count_tokens

    text = " ".join(["tín hiệu"] * 50)
    models, clock = _Models(), _Clock()
    e = _paced(models, clock, tpm_limit=count_tokens(text) * 2)
    await e.embed_documents([text, text])  # dùng hết hạn mức của phút này
    clock.now += 10
    await e.embed_documents([text])  # tài liệu kế tiếp: phải chờ phần còn lại của cửa sổ
    assert clock.slept == [50.0]


async def test_embedder_oversized_single_text_is_sent_alone():
    models, clock = _Models(), _Clock()
    big = " ".join(["từ"] * 400)
    await _paced(models, clock, tpm_limit=50).embed_documents(["ngắn", big, "ngắn"])
    assert models.batch_sizes == [1, 1, 1]


def test_get_embedder_passes_batch_and_tpm_settings():
    s = Settings(
        _env_file=None,
        embed_provider="gemini",
        gemini_api_key="k",
        embed_batch_size=20,
        embed_tpm_limit=20000,
    )
    e = get_embedder(s)
    assert isinstance(e, GeminiEmbedder)
    assert (e._batch_size, e._tpm_limit) == (20, 20000)
