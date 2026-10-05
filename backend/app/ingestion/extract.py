import asyncio
import logging
import re

import pymupdf
import pymupdf4llm

from app.ai.retry import is_retryable
from app.ai.vision import VisionExtractor
from app.core.config import get_settings
from app.ingestion.chunker import PageText

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS = 50
MIN_FORMULAS_FOR_VISION = (
    1  # layout mode bỏ mất nội dung công thức khỏi markdown → trang có công thức phải nhờ vision
)
MAX_PAGES = 300
_MARKUP_RE = re.compile(r"[#*_`>\-|\s]")


def needs_vision(markdown: str, formula_count: int = 0) -> bool:
    """Trang gần như không có chữ (scan/ảnh), chữ bị vỡ font hoặc có công thức → nhờ vision đọc lại."""
    visible = _MARKUP_RE.sub("", markdown)
    return (
        len(visible) < MIN_TEXT_CHARS or markdown.count("�") > 5 or formula_count >= MIN_FORMULAS_FOR_VISION
    )


def _extract_text_pages(doc: pymupdf.Document) -> list[tuple[int, str, int]]:
    if doc.page_count > MAX_PAGES:
        raise ValueError(f"PDF quá dài (tối đa {MAX_PAGES} trang)")
    # use_ocr=False: không dùng OCR của pymupdf4llm (Tesseract/RapidOCR); trang scan đi qua vision
    parts = pymupdf4llm.to_markdown(doc, page_chunks=True, use_ocr=False, show_progress=False)
    return [
        (i + 1, part["text"], sum(1 for b in part.get("page_boxes") or [] if b.get("class") == "formula"))
        for i, part in enumerate(parts)
    ]


def _plan_pages(
    pdf_bytes: bytes, max_vision_pages: int, dpi: int = 150
) -> tuple[list[tuple[int, str, str]], dict[int, bytes]]:
    """Toàn bộ phần PyMuPDF trong một lời gọi đồng bộ (chạy trong một thread; PyMuPDF không an toàn khi
    dùng song song nhiều thread): trích text từng trang, chọn trang gửi vision theo thứ tự trang (trần
    max_vision_pages quyết định TRƯỚC khi gọi vision, không phụ thuộc thứ tự hoàn thành) và render PNG
    cho các trang đó. Trả về [(page_no, markdown, method)] với method ∈ text|skipped|vision và {page_no: png}."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        planned: list[tuple[int, str, str]] = []
        vision_used = 0
        for page_no, markdown, formula_count in _extract_text_pages(doc):
            if not needs_vision(markdown, formula_count):
                method = "text"
            elif vision_used >= max_vision_pages:
                method = "skipped"
            else:
                vision_used += 1
                method = "vision"
            planned.append((page_no, markdown, method))
        pngs = {n: doc[n - 1].get_pixmap(dpi=dpi).tobytes("png") for n, _, m in planned if m == "vision"}
        return planned, pngs
    finally:
        doc.close()


async def _vision_all(
    vision: VisionExtractor, pngs: dict[int, bytes], concurrency: int
) -> dict[int, str | None]:
    """Gọi vision song song, tối đa `concurrency` lời gọi cùng lúc.

    Lỗi tạm thời của dịch vụ AI (429 hết quota, 5xx, timeout — đã hết lượt retry bên trong vision) chỉ làm
    hỏng TRANG đó: trả None để trang dùng text thường, tài liệu vẫn xử lý tiếp (xuống cấp nhẹ nhàng).
    Lỗi khác (sai cấu hình, lỗi lập trình…) → hủy các lời gọi còn lại (TaskGroup) và ném lại chính exception
    đó (không bọc ExceptionGroup, để retry/error_text dùng được)."""
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(page_no: int, png: bytes) -> str | None:
        async with sem:
            try:
                return (await vision.page_to_markdown(png)).strip()
            except Exception as exc:
                if not is_retryable(exc):
                    raise
                logger.warning("Vision lỗi tạm thời ở trang %d, dùng text thường: %r", page_no, exc)
                return None

    try:
        async with asyncio.TaskGroup() as tg:
            tasks = {n: tg.create_task(one(n, png)) for n, png in pngs.items()}
    except ExceptionGroup as eg:
        raise eg.exceptions[0] from None
    return {n: t.result() for n, t in tasks.items()}


async def extract_pages(
    pdf_bytes: bytes,
    vision: VisionExtractor,
    max_vision_pages: int | None = None,
    concurrency: int | None = None,
) -> list[PageText]:
    """Trích từng trang. Tối đa max_vision_pages trang gửi vision (mặc định VISION_MAX_PAGES_PER_DOC),
    xét theo thứ tự trang; vượt trần thì dùng text và đánh dấu vision_skipped=True.
    Các trang vision được gọi song song, tối đa `concurrency` (mặc định VISION_CONCURRENCY) lời gọi cùng lúc;
    kết quả vẫn theo đúng thứ tự trang. Trang gọi vision lỗi tạm thời dùng text và đánh dấu vision_failed=True."""
    settings = get_settings()
    if max_vision_pages is None:
        max_vision_pages = settings.vision_max_pages_per_doc
    if concurrency is None:
        concurrency = settings.vision_concurrency
    # PyMuPDF là code đồng bộ, nặng CPU → chạy trong (một) thread để không chặn event loop của worker
    planned, pngs = await asyncio.to_thread(_plan_pages, pdf_bytes, max_vision_pages)
    vision_md = await _vision_all(vision, pngs, concurrency)
    pages: list[PageText] = []
    for page_no, markdown, method in planned:
        md = vision_md.get(page_no) if method == "vision" else None
        if md is not None:
            pages.append(PageText(page_no, md, "vision"))
        else:
            pages.append(
                PageText(
                    page_no,
                    markdown.strip(),
                    "text",
                    vision_skipped=method == "skipped",
                    vision_failed=method == "vision",
                )
            )
    return pages
