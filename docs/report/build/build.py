"""Dựng báo cáo Word từ các chương Markdown.

Chạy:  python docs/report/build/build.py
Cần: pandoc (>= 3), python-docx; mermaid-cli (mmdc) để vẽ lại sơ đồ (không có thì dùng ảnh đã có trong figures/).
Kết quả: docs/report/bao-cao-do-an.docx. Mở bằng Word: chọn "Yes" khi được hỏi cập nhật trường để có mục lục.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
FIG = REPORT / "figures"
OUT = REPORT / "bao-cao-do-an.docx"
FONT = "Times New Roman"

TOC_XML = (
    '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    "<w:r><w:t>Mở bằng Word và chọn cập nhật trường (F9) để hiện mục lục.</w:t></w:r>"
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
)


def render_mermaid(source: str, name: str) -> Path:
    png = FIG / f"{name}.png"
    mmdc = shutil.which("mmdc")
    if mmdc:
        FIG.mkdir(exist_ok=True)
        src = FIG / f"{name}.mmd"
        src.write_text(source, encoding="utf-8")
        cmd = [mmdc, "-i", str(src), "-o", str(png), "-s", "2", "-b", "white", "-c", str(HERE / "mermaid.json")]
        if os.environ.get("PUPPETEER_CONFIG"):
            cmd += ["-p", os.environ["PUPPETEER_CONFIG"]]
        subprocess.run(cmd, check=True, capture_output=True)
        src.unlink()
    if not png.exists():
        sys.exit(f"Thiếu {png} và không có mmdc để vẽ")
    return png


def combined_markdown() -> str:
    parts = [p.read_text(encoding="utf-8") for p in sorted(REPORT.glob("[0-9][0-9]-*.md"))]
    text = "\n\n".join(parts)
    counter = 0

    def repl(m: re.Match) -> str:
        nonlocal counter
        counter += 1
        body = m.group(1)
        cap = re.search(r"^%% caption: (.+)$", body, re.M)
        caption = cap.group(1).strip() if cap else f"Sơ đồ {counter}"
        size = re.search(r"^%% size: (.+)$", body, re.M)
        attr = size.group(1).strip() if size else "width=15.5cm"
        png = render_mermaid(body, f"so-do-{counter:02d}")
        return f"![{caption}](figures/{png.name}){{{attr}}}"

    text = re.sub(r"```mermaid\n(.*?)```", repl, text, flags=re.S)
    pagebreak = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```\n\n'
    toc = pagebreak + '::: {custom-style="TOC Heading"}\nMỤC LỤC\n:::\n\n```{=openxml}\n' + TOC_XML + "\n```\n"
    return text.replace("<!-- MUCLUC -->", toc)


def _font(style, size, bold=None, italic=None, color=True):
    style.font.name = FONT
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic
    if color:
        style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), FONT)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        rfonts.attrib.pop(qn(attr), None)


def _para(style, *, align=None, before=0, after=6, spacing=1.5, indent=None, keep=False):
    pf = style.paragraph_format
    if align is not None:
        pf.alignment = align
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = spacing
    if indent is not None:
        pf.first_line_indent = indent
    if keep:
        pf.keep_with_next = True


def _style(doc, name, base=None):
    """Tìm style theo tên hiển thị (python-docx đổi "Heading 1" thành "heading 1" khi tra theo khóa)."""
    for st in doc.styles:
        if st.name == name:
            return st
    st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    if base:
        st.base_style = _style(doc, base)
    return st


def reference_doc(path: Path) -> None:
    data = subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"], capture_output=True, check=True
    ).stdout
    path.write_bytes(data)
    doc = Document(path)
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21)
    sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)
    sec.left_margin, sec.right_margin = Cm(3), Cm(2)
    # số trang ở giữa chân trang
    p = sec.footer.paragraphs[0] if sec.footer.paragraphs else sec.footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)

    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        st = _style(doc, name)
        _font(st, 13)
    _para(_style(doc, "Normal"), align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=6, spacing=1.5)
    for name in ("Body Text", "First Paragraph"):
        _para(_style(doc, name), align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=6, spacing=1.5, indent=Cm(1))
    _para(_style(doc, "Compact"), align=WD_ALIGN_PARAGRAPH.LEFT, after=2, spacing=1.3)
    for level, size, before, after, align in (
        (1, 16, 0, 18, WD_ALIGN_PARAGRAPH.CENTER),
        (2, 14, 12, 6, WD_ALIGN_PARAGRAPH.LEFT),
        (3, 13, 10, 4, WD_ALIGN_PARAGRAPH.LEFT),
        (4, 13, 8, 4, WD_ALIGN_PARAGRAPH.LEFT),
    ):
        st = _style(doc, f"Heading {level}")
        _font(st, size, bold=True, italic=(level == 4))
        _para(st, align=align, before=before, after=after, spacing=1.3, keep=True)
    for name in ("Title", "Subtitle", "Author", "Date"):
        _font(_style(doc, name), 13)
    cap = _style(doc, "Image Caption", "Normal")
    _font(cap, 12, bold=False, italic=True)
    _para(cap, align=WD_ALIGN_PARAGRAPH.CENTER, before=2, after=12, spacing=1.2)
    for name in ("Captioned Figure", "Figure"):
        st = _style(doc, name, "Normal")
        _para(st, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=0, spacing=1.0, keep=True)
    src = _style(doc, "Source Code", "Normal")
    _para(src, align=WD_ALIGN_PARAGRAPH.LEFT, after=6, spacing=1.0)
    cover = _style(doc, "Cover", "Normal")
    _font(cover, 14, bold=True)
    _para(cover, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=6, spacing=1.5)
    title = _style(doc, "Cover Title", "Normal")
    _font(title, 20, bold=True)
    _para(title, align=WD_ALIGN_PARAGRAPH.CENTER, before=60, after=24, spacing=1.3)
    formula = _style(doc, "Formula", "Normal")
    _font(formula, 13)
    _para(formula, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=6, spacing=1.5)
    toc_h = _style(doc, "TOC Heading", "Normal")
    _font(toc_h, 16, bold=True)
    _para(toc_h, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=18, spacing=1.3)
    for level in (1, 2, 3):
        st = _style(doc, f"toc {level}", "Normal")
        _font(st, 13, bold=(level == 1))
        _para(st, align=WD_ALIGN_PARAGRAPH.LEFT, after=2, spacing=1.3)
        st.paragraph_format.left_indent = Cm(0.6 * (level - 1))
    doc.save(path)


def _borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    old = tbl_pr.find(qn("w:tblBorders"))
    if old is not None:
        tbl_pr.remove(old)
    tbl_pr.append(borders)


def postprocess(path: Path) -> None:
    doc = Document(path)
    for table in doc.tables:
        _borders(table)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for r, row in enumerate(table.rows):
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent = Cm(0)
                    p.paragraph_format.line_spacing = 1.15
                    p.paragraph_format.space_after = Pt(2)
                    for run in p.runs:
                        run.font.size = Pt(11.5)
                        if r == 0:
                            run.font.bold = True
    # Word tự cập nhật mục lục khi mở file
    settings = doc.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)
    doc.save(path)


def main() -> None:
    os.chdir(REPORT)
    tmp = Path(tempfile.mkdtemp())
    md = tmp / "combined.md"
    md.write_text(combined_markdown(), encoding="utf-8")
    ref = tmp / "reference.docx"
    reference_doc(ref)
    subprocess.run(
        [
            "pandoc", str(md), "-f", "markdown", "-o", str(OUT),
            "--reference-doc", str(ref), "--lua-filter", str(HERE / "numbering.lua"),
            "--resource-path", str(REPORT),
        ],
        check=True,
    )
    postprocess(OUT)
    shutil.rmtree(tmp)
    print(f"Đã ghi {OUT}")


if __name__ == "__main__":
    main()
