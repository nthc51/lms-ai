"""Chèn lại dấu cách bị mất khi trích chữ PDF xuất từ slide ("hiệu quảsử dụng")."""

import pymupdf

from app.ai.vision import FakeVision
from app.ingestion.extract import extract_pages
from app.ingestion.spacing import GluedRun, add_missing_spaces, glue_points
from tests.pdfs import LONG_TEXT

# Mỗi từ đặt ở một vị trí riêng, không có ký tự dấu cách, xen chữ đậm (như PowerPoint xuất PDF)
SLIDE_WORDS = [
    ("Channel", "helv"),
    ("coding", "helv"),
    ("improves", "hebo"),
    ("spectral", "hebo"),
    ("efficiency", "helv"),
    ("and", "helv"),
    ("error", "helv"),
    ("rate", "hebo"),
]


def slide_pdf(gap: float = 2.0) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    x = 72.0
    for word, font in SLIDE_WORDS:
        page.insert_text((x, 100), word, fontname=font, fontsize=14)
        x += pymupdf.get_text_length(word, fontname=font, fontsize=14) + gap
    page.insert_textbox(pymupdf.Rect(72, 150, 540, 770), LONG_TEXT, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _page(data: bytes) -> pymupdf.Page:
    return pymupdf.open(stream=data, filetype="pdf")[0]


def test_detects_words_placed_apart_without_space_characters():
    runs = glue_points(_page(slide_pdf()))
    assert runs == {GluedRun(tuple(w for w, _ in SLIDE_WORDS))}


def test_normal_text_with_real_spaces_has_no_glue():
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(72, 72, 540, 770), LONG_TEXT, fontsize=11)
    assert glue_points(_page(doc.tobytes())) == set()


def test_inserts_spaces_inside_and_around_bold_markers():
    md = "# Channelcoding **improvesspectral** efficiencyanderror **rate**\n"
    run = GluedRun(tuple(w for w, _ in SLIDE_WORDS))
    assert add_missing_spaces(md, {run}) == (
        "# Channel coding **improves spectral** efficiency and error **rate**\n"
    )


def test_opening_and_closing_markers_go_on_the_right_side_of_the_space():
    assert add_missing_spaces("quả**sử**dụng", {GluedRun(("quả", "sử", "dụng"))}) == "quả **sử** dụng"


def test_only_standalone_runs_are_changed():
    # "an" + "h" dính trên trang, nhưng chữ "anh" ở chỗ khác (từ thật) và "thanh" không bị tách
    assert add_missing_spaces("anh, thanh và anh", {GluedRun(("an", "h"))}) == "an h, thanh và an h"
    assert add_missing_spaces("thanh hoa", {GluedRun(("an", "h"))}) == "thanh hoa"


async def test_extract_pages_returns_spaced_text():
    [page] = await extract_pages(slide_pdf(), FakeVision())
    assert page.method == "text"
    assert "Channel coding" in page.markdown and "efficiency and error" in page.markdown
    assert "improves spectral" in page.markdown
