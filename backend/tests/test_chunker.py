import itertools

import pytest

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
    for prev, nxt in itertools.pairwise(chunks):
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


CODE_BLOCK = "```python\ndef tong(a):\n    s = 0\n\n# tinh tong\n    for x in a:\n        s += x\n    return s\n```"


def test_code_fence_lines_are_not_headings_and_block_is_not_split():
    md = "# Thuat toan\n\n" + words(30) + "\n\n" + CODE_BLOCK + "\n\n" + words(30, "sau")
    chunks = chunk_pages([PageText(1, md, "text")], max_tokens=60, overlap_tokens=0)
    assert len(chunks) > 1
    assert all(c.heading_path == "Thuat toan" for c in chunks)
    assert any(CODE_BLOCK in c.content for c in chunks)


def test_tilde_fence_is_one_piece_even_without_blank_line_around_it():
    block = "~~~\n# khong phai heading\n\n\nx = 1\n~~~"
    md = "# Chuong\n\n" + words(10) + "\n" + block + "\n" + words(10, "sau")
    [chunk] = chunk_pages([PageText(1, md, "text")])
    assert chunk.heading_path == "Chuong"
    assert "\n\n" + block + "\n\n" in chunk.content  # khối fence nguyên vẹn, là một đoạn riêng


def test_size_bound_uses_joined_buffer_tokens():
    md = "\n\n".join(["tu"] * 200)
    chunks = chunk_pages([PageText(1, md, "text")], max_tokens=100, overlap_tokens=0)
    assert len(chunks) > 1
    assert all(c.token_count <= 100 for c in chunks)


def test_count_tokens_has_char_floor():
    assert count_tokens("a" * 400) == 100


def test_long_string_without_spaces_is_split_by_chars():
    chunks = chunk_pages([PageText(1, "a" * 50_000, "text")])
    assert len(chunks) > 1
    assert all(c.token_count <= 700 for c in chunks)
    assert "".join(c.content for c in chunks) == "a" * 50_000


@pytest.mark.parametrize(("max_tokens", "overlap_tokens"), [(100, 100), (100, 150), (0, 0)])
def test_invalid_sizes_raise(max_tokens, overlap_tokens):
    with pytest.raises(ValueError):
        chunk_pages([PageText(1, "x", "text")], max_tokens=max_tokens, overlap_tokens=overlap_tokens)


def test_oversized_table_is_split_on_row_boundaries():
    rows = ["| cot a | cot b | cot c |", "|---|---|---|"]
    rows += [f"| r{i} | gia tri {i} | ghi chu {i} |" for i in range(80)]
    chunks = chunk_pages([PageText(1, "\n".join(rows), "text")], max_tokens=100, overlap_tokens=0)
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= 100
        assert all(line in rows for line in c.content.split("\n") if line)
