import asyncio

import pymupdf
import pymupdf4llm
import pytest

from app.ai.vision import FakeVision
from app.core.config import Settings
from app.ingestion import extract
from app.ingestion.extract import extract_pages, needs_vision
from tests.pdfs import LONG_TEXT, make_pdf


def test_needs_vision_rules():
    assert needs_vision("")
    assert needs_vision("# \n\n---\n\n| |")
    assert needs_vision("x" * 60 + "�" * 6)
    assert not needs_vision(LONG_TEXT)


def test_needs_vision_any_formula():
    assert not needs_vision(LONG_TEXT, formula_count=0)
    assert needs_vision(LONG_TEXT, formula_count=1)


async def test_text_page_uses_text_blank_page_falls_back_to_vision():
    vision = FakeVision()
    pages = await extract_pages(make_pdf([LONG_TEXT, ""]), vision)
    assert [(p.page_no, p.method) for p in pages] == [(1, "text"), (2, "vision")]
    assert "Binary search" in pages[0].markdown
    assert pages[1].markdown == vision.text
    assert vision.calls == 1
    assert not any(p.vision_skipped for p in pages)


async def test_vision_receives_png(monkeypatch):
    seen = {}

    class Spy(FakeVision):
        async def page_to_markdown(self, png: bytes) -> str:
            seen["png"] = png
            return await super().page_to_markdown(png)

    await extract_pages(make_pdf([""]), Spy())
    assert seen["png"].startswith(b"\x89PNG")


async def test_corrupt_pdf_raises():
    with pytest.raises(pymupdf.FileDataError):
        await extract_pages(b"not a pdf", FakeVision())


async def test_to_markdown_called_without_ocr_and_formula_page_goes_to_vision(monkeypatch):
    seen = {}

    def fake_to_markdown(doc, **kwargs):
        seen.update(kwargs)
        return [
            {"text": LONG_TEXT, "page_boxes": [{"class": "text"}]},
            {"text": LONG_TEXT, "page_boxes": [{"class": "text"}, {"class": "formula"}]},
        ]

    monkeypatch.setattr(pymupdf4llm, "to_markdown", fake_to_markdown)
    vision = FakeVision()
    pages = await extract_pages(make_pdf([LONG_TEXT, LONG_TEXT]), vision)
    assert seen["use_ocr"] is False and seen["page_chunks"] is True and seen["show_progress"] is False
    assert [(p.page_no, p.method) for p in pages] == [(1, "text"), (2, "vision")]
    assert vision.calls == 1


async def test_vision_cap_falls_back_to_text_and_flags_pages():
    vision = FakeVision()
    pages = await extract_pages(make_pdf(["", "", "", ""]), vision, max_vision_pages=2)
    assert [(p.page_no, p.method, p.vision_skipped) for p in pages] == [
        (1, "vision", False),
        (2, "vision", False),
        (3, "text", True),
        (4, "text", True),
    ]
    assert vision.calls == 2


async def test_vision_cap_zero_never_calls_vision():
    vision = FakeVision()
    pages = await extract_pages(make_pdf(["", LONG_TEXT]), vision, max_vision_pages=0)
    assert [(p.method, p.vision_skipped) for p in pages] == [("text", True), ("text", False)]
    assert vision.calls == 0


async def test_vision_cap_defaults_to_setting(monkeypatch):
    assert Settings.model_fields["vision_max_pages_per_doc"].default == 60
    monkeypatch.setattr(extract, "get_settings", lambda: Settings(vision_max_pages_per_doc=1))
    vision = FakeVision()
    pages = await extract_pages(make_pdf(["", ""]), vision)
    assert [(p.method, p.vision_skipped) for p in pages] == [("vision", False), ("text", True)]
    assert vision.calls == 1


# ---- vision song song (VISION_CONCURRENCY) ----


class InFlightVision:
    """Vision giả đếm số lời gọi đang chạy cùng lúc; PNG giả mang số trang (xem _numbered_pngs)."""

    def __init__(self, delay: float = 0.01, fail_on: int | None = None):
        self.delay, self.fail_on = delay, fail_on
        self.in_flight = self.max_in_flight = self.calls = 0
        self.cancelled = 0

    async def page_to_markdown(self, png: bytes) -> str:
        page_no = int(png.removeprefix(b"page-"))
        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if page_no == self.fail_on:
                await asyncio.sleep(0)
                raise VisionBoom(f"trang {page_no} lỗi")
            # trang sau xong trước → kiểm tra kết quả vẫn theo thứ tự trang
            await asyncio.sleep(self.delay * (10 - page_no) if self.fail_on is None else 10)
            return f"  md trang {page_no}  "
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.in_flight -= 1


class VisionBoom(Exception):
    pass


@pytest.fixture
def _numbered_pngs(monkeypatch):
    """Thay PNG thật bằng b"page-<n>" để vision giả biết đang đọc trang nào (trang trắng render giống nhau)."""
    real = extract._plan_pages

    def plan(pdf_bytes, max_vision_pages):
        planned, pngs = real(pdf_bytes, max_vision_pages)
        assert all(png.startswith(b"\x89PNG") for png in pngs.values())
        return planned, {n: f"page-{n}".encode() for n in pngs}

    monkeypatch.setattr(extract, "_plan_pages", plan)


async def test_vision_pages_run_concurrently_bounded_by_default_4(_numbered_pngs):
    assert Settings(_env_file=None).vision_concurrency == 4
    vision = InFlightVision()
    pages = await extract_pages(make_pdf([""] * 8), vision)
    assert vision.calls == 8
    assert 1 < vision.max_in_flight <= 4
    assert [(p.page_no, p.method, p.markdown) for p in pages] == [
        (n, "vision", f"md trang {n}") for n in range(1, 9)
    ]


async def test_vision_concurrency_argument_is_respected(_numbered_pngs):
    vision = InFlightVision()
    await extract_pages(make_pdf([""] * 6), vision, concurrency=2)
    assert vision.max_in_flight == 2


async def test_vision_cap_decided_in_page_order_before_calls(_numbered_pngs):
    vision = InFlightVision()
    pages = await extract_pages(make_pdf(["", LONG_TEXT, "", "", "", ""]), vision, max_vision_pages=3)
    assert [(p.page_no, p.method, p.vision_skipped) for p in pages] == [
        (1, "vision", False),
        (2, "text", False),
        (3, "vision", False),
        (4, "vision", False),
        (5, "text", True),
        (6, "text", True),
    ]
    assert vision.calls == 3
    assert [p.markdown for p in pages if p.method == "vision"] == ["md trang 1", "md trang 3", "md trang 4"]


async def test_vision_failure_cancels_others_and_propagates_original_exception(_numbered_pngs):
    vision = InFlightVision(fail_on=2)
    with pytest.raises(VisionBoom, match="trang 2 lỗi"):
        await extract_pages(make_pdf([""] * 8), vision)
    assert vision.cancelled >= 1 and vision.in_flight == 0
    assert vision.calls < 8  # các trang còn chờ semaphore bị hủy trước khi được gọi


async def test_pymupdf_runs_in_a_single_thread_call(monkeypatch):
    calls = []
    real_to_thread = asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        calls.append(fn.__name__)
        return await real_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(extract.asyncio, "to_thread", spy)
    await extract_pages(make_pdf([LONG_TEXT, "", ""]), FakeVision())
    assert calls == ["_plan_pages"]


class QuotaVision(InFlightVision):
    """Trang `fail_on` hết quota (429) — lỗi tạm thời, đã hết retry bên trong vision."""

    async def page_to_markdown(self, png: bytes) -> str:
        page_no = int(png.removeprefix(b"page-"))
        if page_no == self.fail_on:
            self.calls += 1
            from tests.test_ai_retry import api_error

            raise api_error(429)
        self.calls += 1
        return f"md trang {page_no}"


async def test_transient_vision_error_falls_back_to_text_for_that_page_only(_numbered_pngs):
    vision = QuotaVision(fail_on=2)
    pages = await extract_pages(make_pdf([""] * 4), vision)
    assert vision.calls == 4  # các trang khác vẫn được đọc
    assert [(p.page_no, p.method, p.vision_failed) for p in pages] == [
        (1, "vision", False),
        (2, "text", True),
        (3, "vision", False),
        (4, "vision", False),
    ]
