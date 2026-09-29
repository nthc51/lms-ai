import math
import re
from collections.abc import Callable
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
TOKENS_PER_WORD = 1.4  # ước lượng cho tiếng Việt (mỗi âm tiết là một "từ"), đủ dùng để chia chunk
CHARS_PER_TOKEN = 4  # sàn theo ký tự: chuỗi dài không có khoảng trắng không bị tính là 1 token


def count_tokens(text: str) -> int:
    n = len(text.split())
    if not n:
        return 0
    return max(round(n * TOKENS_PER_WORD), math.ceil(len(text) / CHARS_PER_TOKEN))


@dataclass(frozen=True)
class PageText:
    page_no: int
    markdown: str
    method: str  # "text" | "vision"
    vision_skipped: bool = False  # cần vision nhưng đã chạm trần VISION_MAX_PAGES_PER_DOC → dùng text


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    heading_path: str
    page_no: int
    token_count: int


@dataclass(frozen=True)
class _Para:
    text: str
    page_no: int
    is_heading: bool = False


def _is_fence_close(line: str, fence: str) -> bool:
    m = FENCE_RE.match(line)
    return (m is not None and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence)
            and line.strip() == m.group(1))


def _paragraphs(markdown: str) -> list[tuple[str, bool]]:
    """Tách theo dòng trống. Mỗi code fence (``` hoặc ~~~) là đúng một đoạn riêng, dòng trống
    bên trong không tách. Trả về danh sách (text, is_fence)."""
    out: list[tuple[str, bool]] = []
    cur: list[str] = []
    fence: str | None = None

    def end(is_fence: bool) -> None:
        text = "\n".join(cur).strip()
        if text:
            out.append((text, is_fence))
        cur.clear()

    for line in markdown.splitlines():
        if fence is not None:
            cur.append(line)
            if _is_fence_close(line, fence):
                fence = None
                end(is_fence=True)
            continue
        m = FENCE_RE.match(line)
        if m:
            end(is_fence=False)
            fence = m.group(1)
            cur.append(line)
        elif not line.strip():
            end(is_fence=False)
        else:
            cur.append(line)
    end(is_fence=fence is not None)  # fence chưa đóng đến cuối trang vẫn là một đoạn
    return out


def _pack(units: list[str], sep: str, max_tokens: int,
          fallback: Callable[[str], list[str]]) -> list[str]:
    """Gom các unit liên tiếp (nối bằng sep) sao cho mỗi phần <= max_tokens; unit quá lớn -> fallback."""
    out: list[str] = []
    cur: list[str] = []
    for unit in units:
        if count_tokens(unit) > max_tokens:
            if cur:
                out.append(sep.join(cur))
                cur = []
            out.extend(fallback(unit))
            continue
        if cur and count_tokens(sep.join([*cur, unit])) > max_tokens:
            out.append(sep.join(cur))
            cur = []
        cur.append(unit)
    if cur:
        out.append(sep.join(cur))
    return [p for p in out if p.strip()]


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Chia đoạn quá dài: theo dòng trước (giữ nguyên dòng bảng/code), rồi theo từ, rồi theo ký tự."""
    step = max_tokens * CHARS_PER_TOKEN

    def by_chars(word: str) -> list[str]:
        return [word[i:i + step] for i in range(0, len(word), step)]

    def by_words(line: str) -> list[str]:
        return _pack(line.split(), " ", max_tokens, by_chars)

    return _pack(text.split("\n"), "\n", max_tokens, by_words)


def _join(paras: list[_Para]) -> str:
    return "\n\n".join(p.text for p in paras)


def chunk_pages(pages: list[PageText], max_tokens: int = 700, overlap_tokens: int = 100,
                flush_min_tokens: int = 150) -> list[ChunkDraft]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be >= 0 and < max_tokens")

    chunks: list[ChunkDraft] = []
    buf: list[_Para] = []
    headings: list[tuple[int, str]] = []
    buf_heading = ""

    def current_path() -> str:
        return " > ".join(title for _, title in headings)

    def fits(para: _Para) -> bool:
        return count_tokens(_join([*buf, para])) <= max_tokens

    def flush(keep_overlap: bool) -> None:
        nonlocal buf
        if not buf:
            return
        content = _join(buf)
        chunks.append(ChunkDraft(content, buf_heading, buf[0].page_no, count_tokens(content)))
        kept: list[_Para] = []
        if keep_overlap:
            for p in reversed(buf):
                if count_tokens(_join([p, *kept])) > overlap_tokens:
                    break
                kept.insert(0, p)
        buf = kept

    for page in pages:
        for text, is_fence in _paragraphs(page.markdown):
            match = None if is_fence else HEADING_RE.match(text.splitlines()[0])
            if match:
                if count_tokens(_join(buf)) >= flush_min_tokens:
                    flush(keep_overlap=False)
                level = len(match.group(1))
                headings = [h for h in headings if h[0] < level] + [(level, match.group(2).strip())]
            pieces = _hard_split(text, max_tokens) if count_tokens(text) > max_tokens else [text]
            for piece in pieces:
                para = _Para(piece, page.page_no, is_heading=bool(match))
                if buf and not fits(para):
                    flush(keep_overlap=True)
                    if not fits(para):
                        buf = []  # overlap + đoạn mới vượt max: bỏ overlap để giữ giới hạn size
                    buf_heading = current_path()
                buf.append(para)
                # Chunk mới bắt đầu, hoặc chunk mới chỉ gồm các heading: gán theo heading hiện tại
                if len(buf) == 1 or all(p.is_heading for p in buf):
                    buf_heading = current_path()
    flush(keep_overlap=False)
    return chunks
