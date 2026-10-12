"""Chèn lại dấu cách bị mất khi trích chữ PDF.

PDF xuất từ slide (PowerPoint, Canva...) thường đặt từng từ hoặc từng khối chữ ở một vị trí riêng mà không có ký tự
dấu cách giữa chúng. MuPDF tự đoán dấu cách theo khoảng trống, nhưng hay đoán sai ở chỗ đổi font (chữ thường sang
chữ đậm) hoặc khi khoảng trống hơi hẹp, nên chữ bị dính: "hiệu quảsử dụng", "phổvà".

Cách sửa: đọc vị trí từng ký tự của trang (rawdict). Hai ký tự liền nhau trên cùng dòng mà cách nhau hơn
GAP_RATIO × cỡ chữ (chữ trong một từ gần như sát nhau) là ranh giới từ bị thiếu dấu cách. Mỗi chuỗi từ dính liền
(giữa hai dấu cách thật) được tìm nguyên văn trong Markdown, đứng riêng, có thể có dấu ** / _ / ` xen giữa, rồi
chèn dấu cách. Chỗ đã có dấu cách thì không khớp nên không đổi gì."""

import re
import unicodedata
from dataclasses import dataclass

import pymupdf

GAP_RATIO = 0.1  # khoảng trống giữa hai ký tự > 10% cỡ chữ = ranh giới từ
# Giữa hai từ trong Markdown có thể có dấu định dạng, hoặc dấu cách (chỗ MuPDF đã tự đoán đúng)
_SEPARATOR = r"((?:[ \t]|\*\*|\*|__|_|`)*)"


@dataclass(frozen=True)
class GluedRun:
    """Các từ liên tiếp trên một dòng, nằm tách nhau theo vị trí nhưng không có ký tự dấu cách ở giữa."""

    words: tuple[str, ...]


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _line_chars(line: dict) -> list[tuple[str, float, float, float]]:
    return [
        (ch["c"], ch["bbox"][0], ch["bbox"][2], span["size"])
        for span in line.get("spans", [])
        for ch in span.get("chars", [])
    ]


def _flush(run: list[str], found: set[GluedRun]) -> None:
    if len(run) > 1:
        found.add(GluedRun(tuple(_nfc(w) for w in run)))
    run.clear()


def glue_points(page: pymupdf.Page) -> set[GluedRun]:
    """Các chuỗi từ bị thiếu dấu cách trên trang (mỗi chuỗi có ít nhất 2 từ)."""
    found: set[GluedRun] = set()
    for block in page.get_text("rawdict").get("blocks", []):
        for line in block.get("lines", []):
            dx, dy = line.get("dir", (1, 0))
            if abs(dy) > 0.01 or dx <= 0:  # chỉ xét dòng nằm ngang, trái sang phải
                continue
            run: list[str] = []
            current = ""
            prev_x1 = None
            for c, x0, x1, size in _line_chars(line):
                if c.isspace():
                    if current:
                        run.append(current)
                        current = ""
                    _flush(run, found)
                    prev_x1 = None
                    continue
                if current and prev_x1 is not None and x0 - prev_x1 > GAP_RATIO * size:
                    run.append(current)  # khoảng trống không có dấu cách: từ mới, cùng chuỗi dính
                    current = ""
                current += c
                prev_x1 = x1
            if current:
                run.append(current)
            _flush(run, found)
    return found


def add_missing_spaces(markdown: str, runs: set[GluedRun]) -> str:
    """Tìm từng chuỗi dính trong Markdown (đứng riêng; giữa các từ có thể có dấu định dạng hoặc dấu cách đã có)
    và chèn dấu cách vào những chỗ còn dính."""
    if not runs:
        return markdown
    text = _nfc(markdown)
    for r in sorted(runs, key=lambda r: (-sum(map(len, r.words)), r.words)):
        body = _SEPARATOR.join(re.escape(w) for w in r.words)
        pattern = re.compile(r"(?<!\w)" + body + r"(?!\w)")
        text = pattern.sub(lambda m, r=r, t=text: _join(m, r, t), text)
    return text


def _join(m: re.Match, r: GluedRun, text: str) -> str:
    """Ghép lại các từ với dấu cách; dấu định dạng ĐÓNG (đã mở một số lẻ lần trên dòng) đứng trước dấu cách,
    dấu MỞ đứng sau."""
    line_start = text.rfind("\n", 0, m.start()) + 1
    out = r.words[0]
    for i, markers in enumerate(m.groups()):
        if " " in markers or "\t" in markers:
            out += markers  # đã có dấu cách ở đây
        elif not markers:
            out += " "
        else:
            token = "**" if markers.startswith("**") else markers[0]
            prefix = text[line_start : m.start(i + 1)]
            closing = prefix.count(token) % 2 == 1
            out += f"{markers} " if closing else f" {markers}"
        out += r.words[i + 1]
    return out
