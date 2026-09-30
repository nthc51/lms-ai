import uuid

from app.ai.retrieval import RetrievedChunk
from app.modules.tutor.models import ChatRole
from app.modules.tutor.text import (
    RefuseFilter,
    citation_record,
    clean_citations,
    format_context,
    format_history,
    source_payload,
    sse,
)


def _run(pieces):
    f = RefuseFilter()
    out = "".join(f.feed(p) for p in pieces) + f.finish()
    return out, f.refused


def _chunk(title="Bài 1", content="Nội dung A", heading="", page=3, start=None):
    return RetrievedChunk(uuid.uuid4(), uuid.uuid4(), title, content, heading, page, start, 0.9)


def test_refuse_token_is_never_emitted():
    for pieces in (["REFUSE"], ["RE", "FU", "SE"], [" REF", "USE", ".\n"]):
        assert _run(pieces) == ("", True)


def test_normal_answer_passes_through_immediately():
    f = RefuseFilter()
    assert f.feed("Tìm") == "Tìm" and f.feed(" kiếm") == " kiếm"
    assert f.finish() == "" and not f.refused


def test_answer_that_only_starts_like_refuse_is_released():
    assert _run(["RE", "D là màu đỏ"]) == ("RED là màu đỏ", False)
    assert _run(["REFUSE", " nhưng vẫn trả lời"]) == ("REFUSE nhưng vẫn trả lời", False)
    assert _run([]) == ("", False)


def test_clean_citations_drops_unknown_numbers():
    text, cited = clean_citations("A [1]. B [7]. C [2, 9]. D [ 3 ]", 3)
    assert text == "A [1]. B . C [2]. D [3]" and cited == [1, 2, 3]
    assert clean_citations("không trích", 2) == ("không trích", [])
    assert clean_citations("[0] [1]", 0) == (" ", [])


def test_format_context_labels_sources_in_order():
    a = _chunk(heading="Chương 1 > Mục 2")
    b = _chunk(title="Bài 2", content="Nội dung B", page=None, start=125.0)
    assert format_context([a, b]) == (
        "[1] (Bài: Bài 1 · trang 3 · Chương 1 > Mục 2)\nNội dung A\n\n[2] (Bài: Bài 2 · phút 2:05)\nNội dung B"
    )


def test_history_citation_and_sse_format():
    assert (
        format_history([(ChatRole.user, "Hỏi"), (ChatRole.assistant, "Đáp")])
        == "Học viên: Hỏi\nTrợ giảng: Đáp"
    )
    c = _chunk()
    record = citation_record(2, c)
    assert record == {
        "n": 2,
        "chunk_id": str(c.chunk_id),
        "lesson_id": str(c.lesson_id),
        "page_no": 3,
        "start_sec": None,
    }
    payload = source_payload(2, c)
    assert payload["lesson_title"] == "Bài 1" and payload["snippet"] == "Nội dung A" and payload["n"] == 2
    assert sse("token", {"text": "xin\nchào"}) == 'event: token\ndata: {"text": "xin\\nchào"}\n\n'
