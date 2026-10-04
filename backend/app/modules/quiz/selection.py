"""Chọn chunk để sinh câu hỏi (spec 5.4 bước 2) và chia độ khó theo tỉ lệ (bước 1). Hàm thuần, không đụng DB."""

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.modules.quiz.models import Difficulty

MIN_CHUNK_TOKENS = 150
DIFFICULTY_ORDER = (Difficulty.easy, Difficulty.medium, Difficulty.hard)


@dataclass(frozen=True)
class ChunkInfo:
    id: uuid.UUID
    content: str
    heading_path: str
    page_no: int | None
    token_count: int


@dataclass(frozen=True)
class ChunkPlan:
    chunk: ChunkInfo
    difficulties: tuple[Difficulty, ...]  # số phần tử = số câu cần sinh từ chunk (2 hoặc 3)


def _spread(eligible: Sequence[ChunkInfo], want: int) -> list[ChunkInfo]:
    """Rải đều `want` chunk theo heading: k ≤ số heading thì lấy chunk đầu của k heading cách đều nhau; nhiều hơn
    thì lấy vòng tròn qua các heading (chunk thứ nhất của mọi heading, rồi chunk thứ hai...)."""
    groups: dict[str, list[ChunkInfo]] = {}
    for c in eligible:
        groups.setdefault(c.heading_path, []).append(c)
    queues = list(groups.values())
    want = min(want, len(eligible))
    if want <= 0:
        return []
    if want <= len(queues):
        return [queues[i * len(queues) // want][0] for i in range(want)]
    picked: list[ChunkInfo] = []
    depth = 0
    while len(picked) < want:
        for q in queues:
            if depth < len(q) and len(picked) < want:
                picked.append(q[depth])
        depth += 1
    return picked


def select_chunks(
    chunks: Sequence[ChunkInfo], count: int, usage: Mapping[uuid.UUID, int] | None = None
) -> list[ChunkInfo]:
    """Bỏ chunk dưới MIN_CHUNK_TOKENS, ưu tiên chunk ít được dùng nhất rồi rải đều theo heading để phủ toàn bài.

    Cần k = ⌈count/2⌉ chunk (không quá số chunk đủ dài). usage: số câu hỏi đã có của bài lấy từ mỗi chunk
    (questions.source_chunk_id). Chunk được xét theo từng mức usage tăng dần (giữ thứ tự gốc trong cùng mức):
    lấy hết mức thấp nhất trước (rải đều theo heading trong mức đó), thiếu mới sang mức kế tiếp. Nhờ vậy sinh
    lại câu hỏi cho cùng bài sẽ dùng phần tài liệu chưa có câu hỏi thay vì lặp lại đúng các chunk cũ."""
    usage = usage or {}
    eligible = [c for c in chunks if c.token_count >= MIN_CHUNK_TOKENS]
    want = min(len(eligible), math.ceil(count / 2))
    picked: list[ChunkInfo] = []
    for level in sorted({usage.get(c.id, 0) for c in eligible}):
        if len(picked) >= want:
            break
        tier = [c for c in eligible if usage.get(c.id, 0) == level]
        picked += _spread(tier, want - len(picked))
    return picked


def difficulty_sequence(n: int, mix: Mapping[Difficulty, float]) -> list[Difficulty]:
    """n độ khó theo tỉ lệ mix (làm tròn kiểu phần dư lớn nhất), xếp xen kẽ dễ → trung bình → khó."""
    total = sum(mix.get(d, 0.0) for d in DIFFICULTY_ORDER)
    if total <= 0:
        return [Difficulty.medium] * n
    exact = {d: n * mix.get(d, 0.0) / total for d in DIFFICULTY_ORDER}
    counts = {d: math.floor(v) for d, v in exact.items()}
    by_remainder = sorted(DIFFICULTY_ORDER, key=lambda d: exact[d] - counts[d], reverse=True)
    for d in by_remainder[: n - sum(counts.values())]:
        counts[d] += 1
    seq: list[Difficulty] = []
    while len(seq) < n:
        for d in DIFFICULTY_ORDER:
            if counts[d] > 0:
                seq.append(d)
                counts[d] -= 1
    return seq


def plan_questions(
    chunks: Sequence[ChunkInfo],
    count: int,
    mix: Mapping[Difficulty, float],
    usage: Mapping[uuid.UUID, int] | None = None,
) -> list[ChunkPlan]:
    """Kế hoạch sinh đúng `count` câu: tổng số độ khó trong kế hoạch == count và khớp chia tỉ lệ cho count.

    Số chunk k = max(1, count // 2) (mỗi chunk 2-3 câu), bị chặn bởi số chunk đủ dài; count nhỏ (1) thì 1 chunk 1 câu.
    Nếu k bị chặn bởi số chunk thì mỗi chunk nhận nhiều câu hơn (có thể > 3) - vẫn đủ count câu.
    Chỉ khi không có chunk đủ dài mới trả [] (caller xử lý 409/failed). Các độ khó xen kẽ dễ -> vừa -> khó được
    chia lần lượt cho từng chunk nên mỗi chunk có độ khó trộn. usage: xem select_chunks."""
    if count <= 0:
        return []
    picked = select_chunks(chunks, 2 * max(1, count // 2), usage)
    if not picked:
        return []
    seq = difficulty_sequence(count, mix)
    base, extra = divmod(count, len(picked))
    plans: list[ChunkPlan] = []
    pos = 0
    for i, c in enumerate(picked):
        n = base + (1 if i < extra else 0)
        plans.append(ChunkPlan(c, tuple(seq[pos : pos + n])))
        pos += n
    return plans
