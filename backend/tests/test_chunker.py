from app.ingestion.chunker import PageText, chunk_pages, count_tokens


def words(n: int, w: str = "tu") -> str:
    return " ".join([w] * n)


def test_count_tokens_estimate():
    assert count_tokens("") == 0
    assert count_tokens(words(10)) == 14


def test_short_document_is_one_chunk_with_heading_path():
    md = "# Chương 1\n\n## Tìm kiếm nhị phân\n\n" + words(50)
    [chunk] = chunk_pages([PageText(1, md, "text")])
    assert chunk.heading_path == "Chương 1 > Tìm kiếm nhị phân"
    assert chunk.page_no == 1
    assert words(50) in chunk.content


def test_new_heading_starts_new_chunk_when_buffer_is_big_enough():
    md = "# A\n\n" + words(120) + "\n\n# B\n\n" + words(120)
    chunks = chunk_pages([PageText(1, md, "text")])
    assert [c.heading_path for c in chunks] == ["A", "B"]


def test_long_text_splits_with_overlap():
    paragraphs = [words(20, f"p{i}") for i in range(10)]  # mỗi đoạn 28 token
    chunks = chunk_pages([PageText(1, "\n\n".join(paragraphs), "text")], max_tokens=100, overlap_tokens=30)
    assert len(chunks) > 1
    for prev, nxt in zip(chunks, chunks[1:]):
        assert prev.content.split("\n\n")[-1] == nxt.content.split("\n\n")[0]  # có đoạn gối đầu
    for c in chunks:
        assert c.token_count <= 100 + 30


def test_chunk_page_is_page_of_first_paragraph():
    chunks = chunk_pages([PageText(1, words(60, "a"), "text"), PageText(2, words(60, "b"), "text")],
                         max_tokens=100, overlap_tokens=0)
    assert [c.page_no for c in chunks] == [1, 2]


def test_oversized_paragraph_is_hard_split():
    chunks = chunk_pages([PageText(1, words(300), "text")], max_tokens=100, overlap_tokens=0)
    assert len(chunks) >= 4
    assert all(c.token_count <= 100 for c in chunks)


def test_empty_pages_give_no_chunks():
    assert chunk_pages([PageText(1, "   \n\n  ", "text")]) == []
