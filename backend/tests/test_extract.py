import pymupdf4llm
import pytest

from app.ai.vision import FakeVision
from app.ingestion.extract import extract_pages, needs_vision
from tests.pdfs import LONG_TEXT, make_pdf


def test_needs_vision_rules():
    assert needs_vision("")
    assert needs_vision("# \n\n---\n\n| |")
    assert needs_vision("x" * 60 + "�" * 6)
    assert not needs_vision(LONG_TEXT)


def test_needs_vision_many_formulas():
    assert not needs_vision(LONG_TEXT, formula_count=2)
    assert needs_vision(LONG_TEXT, formula_count=3)


async def test_text_page_uses_text_blank_page_falls_back_to_vision():
    vision = FakeVision()
    pages = await extract_pages(make_pdf([LONG_TEXT, ""]), vision)
    assert [(p.page_no, p.method) for p in pages] == [(1, "text"), (2, "vision")]
    assert "Binary search" in pages[0].markdown
    assert pages[1].markdown == vision.text
    assert vision.calls == 1


async def test_vision_receives_png(monkeypatch):
    seen = {}

    class Spy(FakeVision):
        async def page_to_markdown(self, png: bytes) -> str:
            seen["png"] = png
            return await super().page_to_markdown(png)

    await extract_pages(make_pdf([""]), Spy())
    assert seen["png"].startswith(b"\x89PNG")


async def test_corrupt_pdf_raises():
    with pytest.raises(Exception):
        await extract_pages(b"not a pdf", FakeVision())


async def test_to_markdown_called_without_ocr_and_formula_page_goes_to_vision(monkeypatch):
    seen = {}

    def fake_to_markdown(doc, **kwargs):
        seen.update(kwargs)
        formulas = [{"class": "formula"}] * 3
        return [
            {"text": LONG_TEXT, "page_boxes": [{"class": "text"}]},
            {"text": LONG_TEXT, "page_boxes": [{"class": "text"}, *formulas]},
        ]

    monkeypatch.setattr(pymupdf4llm, "to_markdown", fake_to_markdown)
    vision = FakeVision()
    pages = await extract_pages(make_pdf([LONG_TEXT, LONG_TEXT]), vision)
    assert seen["use_ocr"] is False and seen["page_chunks"] is True and seen["show_progress"] is False
    assert [(p.page_no, p.method) for p in pages] == [(1, "text"), (2, "vision")]
    assert vision.calls == 1
