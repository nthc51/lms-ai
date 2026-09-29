import pymupdf

LONG_TEXT = "Binary search repeatedly halves the search interval of a sorted array. " * 5


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        if body:
            page.insert_textbox(pymupdf.Rect(72, 72, 540, 770), body, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data
