"""Hàm thuần cho AI Tutor: chặn token REFUSE, lọc trích dẫn [n], dựng context/lịch sử, định dạng SSE."""

import json
import re
from collections.abc import Sequence

from app.ai.retrieval import RetrievedChunk
from app.modules.tutor.models import ChatRole

REFUSE_TOKEN = "REFUSE"
REFUSAL_MESSAGE = (
    "Xin lỗi, tài liệu của khóa học không có thông tin để trả lời câu hỏi này. "
    "Bạn thử hỏi cách khác hoặc hỏi về nội dung trong bài học nhé."
)
SNIPPET_CHARS = 300
_CITATION_RE = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")
_SPEAKERS = {ChatRole.user: "Học viên", ChatRole.assistant: "Trợ giảng"}


def _is_refusal(text: str) -> bool:
    return text.strip().rstrip(".!").strip() == REFUSE_TOKEN


class RefuseFilter:
    """LLM trả đúng token REFUSE khi thiếu ngữ cảnh (spec 5.3 bước 4). Giữ lại phần đầu câu trả lời chừng nào
    nó còn có thể là "REFUSE", để học viên không bao giờ thấy token này; câu trả lời thường được đẩy ra ngay."""

    def __init__(self) -> None:
        self._buffer = ""
        self._decided = False
        self.refused = False

    def feed(self, piece: str) -> str:
        if self._decided:
            return piece
        self._buffer += piece
        head = self._buffer.lstrip()
        if REFUSE_TOKEN.startswith(head) or _is_refusal(head):
            return ""
        return self._flush()

    def finish(self) -> str:
        """Gọi khi stream kết thúc: trả phần còn giữ lại (nếu không phải REFUSE)."""
        if self._decided:
            return ""
        if _is_refusal(self._buffer):
            self.refused = True
            self._decided = True
            return ""
        return self._flush()

    def _flush(self) -> str:
        self._decided = True
        out, self._buffer = self._buffer, ""
        return out


def clean_citations(text: str, n_sources: int) -> tuple[str, list[int]]:
    """Bỏ các [n] không nằm trong danh sách nguồn (spec 5.3 bước 5). Trả về (văn bản đã lọc, các n được trích)."""
    cited: set[int] = set()

    def repl(m: re.Match) -> str:
        valid = [n for n in (int(x) for x in m.group(1).split(",")) if 1 <= n <= n_sources]
        cited.update(valid)
        return "".join(f"[{n}]" for n in valid)

    return _CITATION_RE.sub(repl, text), sorted(cited)


def format_context(chunks: Sequence[RetrievedChunk]) -> str:
    blocks = []
    for n, c in enumerate(chunks, 1):
        meta = [f"Bài: {c.lesson_title}"]
        if c.page_no is not None:
            meta.append(f"trang {c.page_no}")
        if c.start_sec is not None:
            minutes, seconds = divmod(int(c.start_sec), 60)
            meta.append(f"phút {minutes}:{seconds:02d}")
        if c.heading_path:
            meta.append(c.heading_path)
        blocks.append(f"[{n}] ({' · '.join(meta)})\n{c.content}")
    return "\n\n".join(blocks)


def format_history(history: Sequence[tuple[ChatRole, str]]) -> str:
    return "\n".join(f"{_SPEAKERS[role]}: {content}" for role, content in history)


def citation_record(n: int, c: RetrievedChunk) -> dict:
    """Một trích dẫn lưu trong chat_messages.citations."""
    return {
        "n": n,
        "chunk_id": str(c.chunk_id),
        "lesson_id": str(c.lesson_id),
        "page_no": c.page_no,
        "start_sec": c.start_sec,
    }


def source_payload(n: int, c: RetrievedChunk) -> dict:
    """Một nguồn trong event `sources`: đủ để frontend hiển thị và mở đúng bài/trang/timestamp."""
    return {
        **citation_record(n, c),
        "lesson_title": c.lesson_title,
        "heading_path": c.heading_path,
        "snippet": c.content[:SNIPPET_CHARS],
    }


def sse(event: str, data: dict) -> str:
    """Một event SSE. data là JSON một dòng (xuống dòng trong text đã được escape)."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
