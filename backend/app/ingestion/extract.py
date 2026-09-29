import asyncio
import re

import pymupdf
import pymupdf4llm

from app.ai.vision import VisionExtractor
from app.core.config import get_settings
from app.ingestion.chunker import PageText

MIN_TEXT_CHARS = 50
MIN_FORMULAS_FOR_VISION = 1  # layout mode bỏ mất nội dung công thức khỏi markdown → trang có công thức phải nhờ vision
MAX_PAGES = 300
_MARKUP_RE = re.compile(r"[#*_`>\-|\s]")


def needs_vision(markdown: str, formula_count: int = 0) -> bool:
    """Trang gần như không có chữ (scan/ảnh), chữ bị vỡ font hoặc có công thức → nhờ vision đọc lại."""
    visible = _MARKUP_RE.sub("", markdown)
    return len(visible) < MIN_TEXT_CHARS or markdown.count("�") > 5 or formula_count >= MIN_FORMULAS_FOR_VISION


def _extract_text_pages(pdf_bytes: bytes) -> list[tuple[int, str, int]]:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count > MAX_PAGES:
            raise ValueError(f"PDF quá dài (tối đa {MAX_PAGES} trang)")
        # use_ocr=False: không dùng OCR của pymupdf4llm (Tesseract/RapidOCR); trang scan đi qua vision
        parts = pymupdf4llm.to_markdown(doc, page_chunks=True, use_ocr=False, show_progress=False)
        return [
            (i + 1, part["text"], sum(1 for b in part.get("page_boxes") or [] if b.get("class") == "formula"))
            for i, part in enumerate(parts)
        ]
    finally:
        doc.close()


def _render_png(pdf_bytes: bytes, page_no: int, dpi: int = 150) -> bytes:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return doc[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()


async def extract_pages(pdf_bytes: bytes, vision: VisionExtractor,
                        max_vision_pages: int | None = None) -> list[PageText]:
    """Trích từng trang. Tối đa max_vision_pages trang gửi vision (mặc định VISION_MAX_PAGES_PER_DOC),
    xét theo thứ tự trang; vượt trần thì dùng text và đánh dấu vision_skipped=True."""
    if max_vision_pages is None:
        max_vision_pages = get_settings().vision_max_pages_per_doc
    # PyMuPDF là code đồng bộ, nặng CPU → chạy trong thread để không chặn event loop của worker
    raw = await asyncio.to_thread(_extract_text_pages, pdf_bytes)
    pages: list[PageText] = []
    vision_used = 0
    for page_no, markdown, formula_count in raw:
        if not needs_vision(markdown, formula_count):
            pages.append(PageText(page_no, markdown.strip(), "text"))
        elif vision_used >= max_vision_pages:
            pages.append(PageText(page_no, markdown.strip(), "text", vision_skipped=True))
        else:
            vision_used += 1
            png = await asyncio.to_thread(_render_png, pdf_bytes, page_no)
            pages.append(PageText(page_no, (await vision.page_to_markdown(png)).strip(), "vision"))
    return pages
