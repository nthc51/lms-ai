import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
TOKENS_PER_WORD = 1.4  # ước lượng cho tiếng Việt (mỗi âm tiết là một "từ"), đủ dùng để chia chunk


def count_tokens(text: str) -> int:
    n = len(text.split())
    return round(n * TOKENS_PER_WORD) if n else 0


@dataclass(frozen=True)
class PageText:
    page_no: int
    markdown: str
    method: str  # "text" | "vision"


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
    tokens: int
    is_heading: bool = False


def _hard_split(text: str, max_tokens: int) -> list[str]:
    words = text.split()
    step = max(1, int(max_tokens / TOKENS_PER_WORD))
    return [" ".join(words[i:i + step]) for i in range(0, len(words), step)]


def chunk_pages(pages: list[PageText], max_tokens: int = 700, overlap_tokens: int = 100,
                flush_min_tokens: int = 150) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    buf: list[_Para] = []
    headings: list[tuple[int, str]] = []
    buf_heading = ""

    def buf_tokens() -> int:
        return sum(p.tokens for p in buf)

    def current_path() -> str:
        return " > ".join(title for _, title in headings)

    def flush(keep_overlap: bool) -> None:
        nonlocal buf
        if not buf:
            return
        content = "\n\n".join(p.text for p in buf)
        chunks.append(ChunkDraft(content, buf_heading, buf[0].page_no, count_tokens(content)))
        kept: list[_Para] = []
        if keep_overlap:
            total = 0
            for p in reversed(buf):
                if total + p.tokens > overlap_tokens:
                    break
                kept.insert(0, p)
                total += p.tokens
        buf = kept

    for page in pages:
        for raw in PARAGRAPH_SPLIT_RE.split(page.markdown):
            text = raw.strip()
            if not text:
                continue
            match = HEADING_RE.match(text.splitlines()[0])
            if match:
                if buf_tokens() >= flush_min_tokens:
                    flush(keep_overlap=False)
                level = len(match.group(1))
                headings = [h for h in headings if h[0] < level] + [(level, match.group(2).strip())]
            pieces = _hard_split(text, max_tokens) if count_tokens(text) > max_tokens else [text]
            for piece in pieces:
                tokens = count_tokens(piece)
                if buf and buf_tokens() + tokens > max_tokens:
                    flush(keep_overlap=True)
                    buf_heading = current_path()
                buf.append(_Para(piece, page.page_no, tokens, is_heading=bool(match)))
                # Chunk mới bắt đầu, hoặc chunk mới chỉ gồm các heading: gán theo heading hiện tại
                if len(buf) == 1 or all(p.is_heading for p in buf):
                    buf_heading = current_path()
    flush(keep_overlap=False)
    return chunks
