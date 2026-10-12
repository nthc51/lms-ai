# Sửa chữ dính PDF, lệnh vận hành, báo cáo: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** khi kiểm tay sinh câu hỏi trên bộ slide "Kỹ thuật truyền thông", đoạn trích bị dính chữ: "hiệu quảsử dụng", "phổvà", "lỗi** Xem". PDF xuất từ slide đặt từng từ / khối chữ ở vị trí riêng mà không có ký tự dấu cách; MuPDF tự đoán dấu cách nhưng hay sai ở chỗ đổi font (thường → đậm) hoặc khi khoảng trống hẹp. Chữ dính làm AI Tutor tìm kém và câu hỏi AI sinh ra khó đọc. Kèm theo là vài việc dọn dẹp còn sót và bản nháp báo cáo đồ án.

**Mục tiêu:**

- **Chèn lại dấu cách khi trích chữ PDF** (`app/ingestion/spacing.py`): đọc vị trí từng ký tự của trang; hai ký tự liền nhau trên một dòng cách nhau hơn 10% cỡ chữ mà không có dấu cách là ranh giới từ bị mất. Mỗi chuỗi từ dính được tìm nguyên văn trong Markdown (đứng riêng, có thể có `**` / `_` / `` ` `` hoặc dấu cách sẵn xen giữa) rồi chèn dấu cách; dấu đậm đóng/mở được đặt đúng phía. Không tốn tiền AI, không đổi gì ở chữ bình thường.
- **`scripts/reprocess_pdfs.py`**: xử lý lại hàng loạt các PDF đã tải lên (mặc định chỉ liệt kê, `--yes` mới làm, lọc theo `--course <slug>`), chống tạo job trùng, chỉ đụng tài liệu `ready` / `failed`.
- **`app/scripts/lock_user.py`**: khóa / mở khóa tài khoản bằng lệnh, kể cả admin (trang quản trị không cho khóa admin), thu hồi mọi phiên, **không cho khóa admin cuối cùng còn hoạt động**. Dùng để khóa `admin@lms.local` cũ.
- **Spec**: cập nhật bảng tiến độ báo cáo, mục 5.7, bảng endpoint Tutor và nhật ký quyết định cho 4 thay đổi ngày 2026-10-12.
- **Báo cáo đồ án** (`docs/report/`): đã viết sẵn 6 file Markdown (mở đầu, chương 1–4, kết luận), 6 sơ đồ, script dựng file Word và file `bao-cao-do-an.docx` (42 trang). Claude Code chỉ cần commit.

**Thứ tự làm:** sau `2026-10-12-tutor-waiting-plan.md`. Diff tạo trên HEAD `c77a37b`.

**Mã trong plan đã được chạy thử** trên HEAD `c77a37b`: backend **761 test pass** (752 cũ + 9 mới), `ruff check`, `ruff format --check` sạch, `lint-imports` 5 hợp đồng KEPT. Không có thay đổi frontend, không có migration.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6 nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn dùng pgvector 0.8, **không cần làm gì**. Test mới chỉ dùng font có sẵn của PDF (Helvetica), chạy được trên Windows.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Cách áp diff như các plan trước (đường dẫn tính từ gốc repo, `git apply --3way` hoặc sửa tay; file mới tạo đúng nội dung).

---

## Task 1: Chèn lại dấu cách khi trích chữ PDF

**Files:**
- Create: `backend/app/ingestion/spacing.py`
- Modify: `backend/app/ingestion/extract.py`
- Test: `backend/tests/test_spacing.py`

- [x] **Bước 1: Viết test (sẽ fail)**

PDF thử dựng như slide: mỗi từ đặt ở một vị trí, cách nhau 2pt ở cỡ chữ 14 (MuPDF không tự chèn dấu cách ở khoảng này), xen chữ đậm. Test cuối chạy qua `extract_pages` để chắc chắn đường xử lý thật dùng bản đã sửa.

```python
"""Chèn lại dấu cách bị mất khi trích chữ PDF xuất từ slide ("hiệu quảsử dụng")."""

import pymupdf

from app.ai.vision import FakeVision
from app.ingestion.extract import extract_pages
from app.ingestion.spacing import GluedRun, add_missing_spaces, glue_points
from tests.pdfs import LONG_TEXT

# Mỗi từ đặt ở một vị trí riêng, không có ký tự dấu cách, xen chữ đậm (như PowerPoint xuất PDF)
SLIDE_WORDS = [
    ("Channel", "helv"),
    ("coding", "helv"),
    ("improves", "hebo"),
    ("spectral", "hebo"),
    ("efficiency", "helv"),
    ("and", "helv"),
    ("error", "helv"),
    ("rate", "hebo"),
]


def slide_pdf(gap: float = 2.0) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    x = 72.0
    for word, font in SLIDE_WORDS:
        page.insert_text((x, 100), word, fontname=font, fontsize=14)
        x += pymupdf.get_text_length(word, fontname=font, fontsize=14) + gap
    page.insert_textbox(pymupdf.Rect(72, 150, 540, 770), LONG_TEXT, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _page(data: bytes) -> pymupdf.Page:
    return pymupdf.open(stream=data, filetype="pdf")[0]


def test_detects_words_placed_apart_without_space_characters():
    runs = glue_points(_page(slide_pdf()))
    assert runs == {GluedRun(tuple(w for w, _ in SLIDE_WORDS))}


def test_normal_text_with_real_spaces_has_no_glue():
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(72, 72, 540, 770), LONG_TEXT, fontsize=11)
    assert glue_points(_page(doc.tobytes())) == set()


def test_inserts_spaces_inside_and_around_bold_markers():
    md = "# Channelcoding **improvesspectral** efficiencyanderror **rate**\n"
    run = GluedRun(tuple(w for w, _ in SLIDE_WORDS))
    assert add_missing_spaces(md, {run}) == (
        "# Channel coding **improves spectral** efficiency and error **rate**\n"
    )


def test_opening_and_closing_markers_go_on_the_right_side_of_the_space():
    assert add_missing_spaces("quả**sử**dụng", {GluedRun(("quả", "sử", "dụng"))}) == "quả **sử** dụng"


def test_only_standalone_runs_are_changed():
    # "an" + "h" dính trên trang, nhưng chữ "anh" ở chỗ khác (từ thật) và "thanh" không bị tách
    assert add_missing_spaces("anh, thanh và anh", {GluedRun(("an", "h"))}) == "an h, thanh và an h"
    assert add_missing_spaces("thanh hoa", {GluedRun(("an", "h"))}) == "thanh hoa"


async def test_extract_pages_returns_spaced_text():
    [page] = await extract_pages(slide_pdf(), FakeVision())
    assert page.method == "text"
    assert "Channel coding" in page.markdown and "efficiency and error" in page.markdown
    assert "improves spectral" in page.markdown
```

Chạy: `cd backend; uv run pytest tests/test_spacing.py -q` → fail (ImportError).

- [x] **Bước 2: `app/ingestion/spacing.py`**

```python
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
```

Ghi chú:

- Vị trí ký tự (`bbox` trong `rawdict`) tính theo bề rộng ký tự, nên các chữ trong một từ gần như sát nhau (khoảng trống ≈ 0, kerning hơi âm); dấu cách thật giữa hai từ rộng khoảng 25–30% cỡ chữ. Ngưỡng 10% nằm giữa hai mức này.
- Chỉ thay **cả chuỗi dính** đứng riêng (`(?<!\w)` … `(?!\w)`): chữ "anh" thật ở chỗ khác không bị tách thành "an h" dù trang có cặp "an" + "h" dính (có test).
- Chuẩn hóa Unicode NFC trước khi so khớp (có PDF lưu chữ có dấu dạng tổ hợp).

- [x] **Bước 3: Dùng trong `extract.py`**

```diff
--- a/backend/app/ingestion/extract.py
+++ b/backend/app/ingestion/extract.py
@@ -9,6 +9,7 @@
 from app.ai.vision import VisionExtractor
 from app.core.config import get_settings
 from app.ingestion.chunker import PageText
+from app.ingestion.spacing import add_missing_spaces, glue_points
 
 logger = logging.getLogger(__name__)
 
@@ -33,8 +34,13 @@
         raise ValueError(f"PDF quá dài (tối đa {MAX_PAGES} trang)")
     # use_ocr=False: không dùng OCR của pymupdf4llm (Tesseract/RapidOCR); trang scan đi qua vision
     parts = pymupdf4llm.to_markdown(doc, page_chunks=True, use_ocr=False, show_progress=False)
+    # PDF xuất từ slide hay mất dấu cách giữa các khối chữ ("hiệu quảsử dụng"): chèn lại theo vị trí ký tự
     return [
-        (i + 1, part["text"], sum(1 for b in part.get("page_boxes") or [] if b.get("class") == "formula"))
+        (
+            i + 1,
+            add_missing_spaces(part["text"], glue_points(doc[i])),
+            sum(1 for b in part.get("page_boxes") or [] if b.get("class") == "formula"),
+        )
         for i, part in enumerate(parts)
     ]
 
```

- [x] **Bước 4: Chạy test**

```powershell
uv run pytest tests/test_spacing.py tests/test_extract.py tests/test_pipeline.py -q
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
```

Kỳ vọng: pass hết; sạch.

- [x] **Bước 5: Commit**

```powershell
git add backend
git commit -m "fix(ingestion): chèn lại dấu cách bị mất khi trích chữ PDF xuất từ slide"
```

---

## Task 2: Lệnh vận hành

**Files:**
- Create: `backend/app/scripts/lock_user.py`, `backend/scripts/reprocess_pdfs.py`
- Test: `backend/tests/test_ops_scripts.py`

`lock_user` nằm trong `app/scripts/` (chạy được trong container `api` như `seed_admin`, `approve_teacher`); `reprocess_pdfs` nằm trong `backend/scripts/` (chạy từ máy bằng `uv run`, như `reembed`).

- [x] **Bước 1: Test**

```python
"""Lệnh vận hành: khóa tài khoản bằng lệnh, xử lý lại PDF hàng loạt."""

import pytest
from sqlalchemy import select

from app.modules.auth.models import RefreshToken, Role
from app.modules.jobs.models import Job
from app.modules.materials.models import SourceStatus
from app.scripts.lock_user import LockError, set_locked
from scripts.reprocess_pdfs import reprocess
from tests.factories import make_lesson, make_pdf_source, make_user
from tests.fakes import InMemoryStorage, RecordingQueue
from tests.helpers import API, make_student


async def test_lock_admin_by_command_revokes_sessions_but_keeps_last_admin(client, db):
    old = await make_user(db, Role.admin)
    main = await make_user(db, Role.admin)
    db.add(RefreshToken(user_id=old.id, token_hash="x" * 64, expires_at=old.created_at))
    await db.commit()

    user = await set_locked(db, old.email.upper(), True, "Tài khoản cũ")
    assert user.locked_at is not None and user.lock_reason == "Tài khoản cũ"
    token = await db.scalar(select(RefreshToken).where(RefreshToken.user_id == old.id))
    assert token.revoked_at is not None
    with pytest.raises(LockError, match="cuối cùng"):
        await set_locked(db, main.email, True)

    user = await set_locked(db, old.email, False)
    assert user.locked_at is None and user.lock_reason is None
    with pytest.raises(LockError, match="Không có tài khoản"):
        await set_locked(db, "khongco@x.com", True)


async def test_locked_student_cannot_log_in(client, db):
    await make_student(client, "sv@x.com")
    await set_locked(db, "sv@x.com", True)
    r = await client.post(f"{API}/auth/login", json={"email": "sv@x.com", "password": "password123"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"


async def test_reprocess_queues_ready_and_failed_pdfs_only(db):
    from app.core.db import SessionLocal

    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    storage = InMemoryStorage()
    ready = await make_pdf_source(db, storage, teacher, lesson, b"%PDF-1.7", status=SourceStatus.ready)
    failed = await make_pdf_source(db, storage, teacher, lesson, b"%PDF-1.7", status=SourceStatus.failed)
    busy = await make_pdf_source(db, storage, teacher, lesson, b"%PDF-1.7", status=SourceStatus.processing)
    queue = RecordingQueue()

    assert await reprocess(SessionLocal, queue) == (2, 1)
    assert sorted(ref for _, ref in queue.jobs) == sorted([ready.id, failed.id])
    for s in (ready, failed):
        await db.refresh(s)
        assert s.status == SourceStatus.pending and s.error_msg is None
    await db.refresh(busy)
    assert busy.status == SourceStatus.processing
    # Chạy lại khi job cũ còn chờ: không tạo job trùng
    assert await reprocess(SessionLocal, RecordingQueue()) == (0, 3)
    assert len(list(await db.scalars(select(Job)))) == 2
```

- [x] **Bước 2: `app/scripts/lock_user.py`**

```python
"""Khóa / mở khóa một tài khoản bằng lệnh (kể cả quản trị viên, việc trang quản trị không cho làm).

Dùng cho tài khoản admin cũ hoặc tạo nhầm, ví dụ admin@lms.local (email đuôi .local không đăng nhập được):

    docker compose exec api python -m app.scripts.lock_user admin@lms.local --reason "Tài khoản cũ"
    docker compose exec api python -m app.scripts.lock_user admin@lms.local --unlock

Khóa thì thu hồi mọi phiên đăng nhập. Không cho khóa quản trị viên cuối cùng còn hoạt động."""

import argparse
import asyncio

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import RefreshToken, Role, User


class LockError(Exception):
    pass


async def set_locked(db: AsyncSession, email: str, locked: bool, reason: str | None = None) -> User:
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise LockError(f"Không có tài khoản {email}")
    if locked and user.locked_at is None:
        if user.role == Role.admin:
            active_admins = await db.scalar(
                select(func.count(User.id)).where(User.role == Role.admin, User.locked_at.is_(None))
            )
            if active_admins <= 1:
                raise LockError("Không thể khóa quản trị viên cuối cùng còn hoạt động")
        user.locked_at = utcnow()
        user.lock_reason = reason
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    elif not locked and user.locked_at is not None:
        user.locked_at = None
        user.lock_reason = None
    await db.commit()
    return user


async def main(email: str, unlock: bool, reason: str | None) -> None:
    async with SessionLocal() as db:
        try:
            user = await set_locked(db, email, not unlock, reason)
        except LockError as e:
            raise SystemExit(str(e)) from None
    print(f"{'Đã mở khóa' if unlock else 'Đã khóa'}: {user.email} ({user.role.value})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("email")
    p.add_argument("--unlock", action="store_true")
    p.add_argument("--reason")
    a = p.parse_args()
    asyncio.run(main(a.email, a.unlock, a.reason))
```

- [x] **Bước 3: `scripts/reprocess_pdfs.py`**

```python
"""Xử lý lại các tài liệu PDF đã tải lên (như bấm "Xử lý lại" cho từng tài liệu).

Khi nào cần: sau khi sửa cách trích chữ (ví dụ chèn lại dấu cách bị mất ở PDF xuất từ slide), tài liệu cũ vẫn giữ
đoạn trích theo cách cũ cho tới khi được xử lý lại. Chỉ xử lý tài liệu đang "ready" hoặc "failed"; tài liệu đang chờ
/ đang xử lý thì bỏ qua.

Lưu ý chi phí: khi dùng AI thật, mỗi tài liệu gọi lại vision (tối đa VISION_MAX_PAGES_PER_DOC trang) và embedding.

Chạy từ thư mục backend/ (Docker đang chạy, worker đang chạy):
    uv run python -m scripts.reprocess_pdfs                    # chỉ liệt kê, không làm gì
    uv run python -m scripts.reprocess_pdfs --yes              # xử lý lại tất cả
    uv run python -m scripts.reprocess_pdfs --course kttt-8feb7f --yes   # chỉ một khóa (slug trên URL)
"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models_registry  # noqa: F401 — nạp mọi model (khóa ngoại)
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.courses.models import Course, Lesson, Section
from app.modules.jobs.queue import ArqQueue, JobQueue
from app.modules.jobs.service import create_job
from app.modules.materials.models import Source, SourceStatus, SourceType
from app.modules.materials.sources import INGEST_PDF


async def find_sources(session_factory: async_sessionmaker, course_slug: str | None) -> list[tuple]:
    stmt = (
        select(Source.id, Source.status, Course.slug, Lesson.title)
        .join(Lesson, Lesson.id == Source.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Source.type == SourceType.pdf)
        .order_by(Course.slug, Lesson.title, Source.id)
    )
    if course_slug:
        stmt = stmt.where(Course.slug == course_slug)
    async with session_factory() as db:
        return list((await db.execute(stmt)).all())


async def reprocess(
    session_factory: async_sessionmaker, queue: JobQueue, course_slug: str | None = None
) -> tuple[int, int]:
    """Trả về (số tài liệu đã xếp hàng xử lý lại, số bỏ qua vì đang chờ / đang xử lý)."""
    queued = skipped = 0
    for source_id, status, _, _ in await find_sources(session_factory, course_slug):
        if status not in (SourceStatus.ready, SourceStatus.failed):
            skipped += 1
            continue
        async with session_factory() as db:
            job, created = await create_job(db, INGEST_PDF, source_id, created_by=None)
            if not created:
                await db.rollback()
                skipped += 1
                continue
            source = await db.get(Source, source_id)
            source.status = SourceStatus.pending
            source.error_msg = None
            await db.commit()
        await queue.enqueue(job)  # chỉ sau khi job đã commit
        queued += 1
    return queued, skipped


async def main(course: str | None, yes: bool) -> None:
    rows = await find_sources(SessionLocal, course)
    for _, status, slug, title in rows:
        print(f"  [{status.value:10}] {slug} / {title}")
    if not yes:
        print(f"{len(rows)} tài liệu. Thêm --yes để xử lý lại.")
        return
    queued, skipped = await reprocess(SessionLocal, ArqQueue(get_settings().redis_url), course)
    print(f"Đã xếp hàng xử lý lại {queued} tài liệu, bỏ qua {skipped} (đang chờ / đang xử lý).")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--course", help="slug của khóa học (phần sau /teach/ trên URL)")
    p.add_argument("--yes", action="store_true", help="thực hiện (mặc định chỉ liệt kê)")
    a = p.parse_args()
    asyncio.run(main(a.course, a.yes))
```

- [x] **Bước 4: Chạy test + commit**

```powershell
uv run pytest tests/test_ops_scripts.py -q
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
uv run pytest -q          # cả bộ: 761 pass
git add backend
git commit -m "feat(ops): lệnh khóa tài khoản và xử lý lại PDF hàng loạt"
```

---

## Task 3: Spec và báo cáo

**Files:**
- Modify: `docs/specs/2026-09-29-lms-ai-design.md`
- Add (đã có sẵn trong repo, chưa commit): `docs/report/**`

- [x] **Bước 1: Spec**

```diff
--- a/docs/specs/2026-09-29-lms-ai-design.md
+++ b/docs/specs/2026-09-29-lms-ai-design.md
@@ -80,10 +80,10 @@
 
 ### Báo cáo
 
-- [ ] R1. Chương 1–2: tổng quan, cơ sở lý thuyết
-- [ ] R2. Chương 3: phân tích thiết kế (use case, ERD, sơ đồ luồng)
-- [ ] R3. Chương 4: kết quả và đánh giá
-- [ ] R4. Chương 5: kết luận, hướng phát triển
+- [~] R1. Chương 1–2: tổng quan, cơ sở lý thuyết (bản nháp trong `docs/report/`)
+- [~] R2. Chương 3: phân tích thiết kế (use case, ERD, sơ đồ luồng) (bản nháp)
+- [~] R3. Chương 4: kết quả và đánh giá (bản nháp, chờ số liệu benchmark và đo tải)
+- [~] R4. Chương 5: kết luận, hướng phát triển (bản nháp)
 - [ ] R5. Slide bảo vệ + tập demo
 
 ### Mốc
@@ -450,7 +450,7 @@
 | Job xử lý tài liệu thất bại | `sources.status = failed` kèm `error_msg`, giáo viên thấy nút "Xử lý lại" |
 | Worker chết hoặc bị kill giữa chừng | Cron arq 5 phút một lần: job `processing` quá `job_timeout + 5 phút` → `failed` với `error_msg = "Worker bị gián đoạn"`; source tương ứng, nếu vẫn còn `pending`/`processing`, cũng chuyển `failed` (cùng transaction) để giáo viên bấm "Xử lý lại" |
 | Job kẹt `pending` (Redis down lúc enqueue, mất job trong Redis) | Cùng cron: job `pending` quá `PENDING_JOB_REQUEUE_AFTER_MIN` (mặc định 10) phút và chưa `requeued_at` → enqueue lại **một lần** với cùng `_job_id` (arq tự bỏ qua nếu job còn), ghi `requeued_at` chỉ khi enqueue không lỗi (lỗi thì để lần sweep sau). Vẫn `pending` quá N phút sau `requeued_at` → `failed` với `error_msg = "Không đưa được job vào hàng đợi"`; source còn `pending`/`processing` cũng `failed`, cùng transaction |
-| Khóa học chưa có chunk nào ở trạng thái ready | Ẩn AI Tutor, hiện "Tài liệu đang được xử lý" |
+| Khóa học chưa có chunk nào ở trạng thái ready | Báo đúng lý do theo `availability.state`; còn tài liệu đang xử lý thì vẫn nhận câu hỏi chờ, AI trả lời khi xử lý xong (2026-10-12) |
 | Đang demo | Bật cache cho các câu demo và có sẵn video demo dự phòng |
 
 **Worker (đã làm ở tuần 1):**
@@ -498,7 +498,7 @@
 | Khóa học | `GET /courses` · `GET /courses/{slug}` · `POST/PATCH/DELETE /courses` · `POST /courses/{id}/publish` · CRUD sections/lessons · `PATCH /courses/{id}/reorder` · `GET /teacher/courses?page=&size=` (khóa của giảng viên đang đăng nhập, phân trang) |
 | Học | `POST /courses/{id}/enroll` · `GET /me/courses?page=&size=` (phân trang) · `GET /lessons/{id}` (nội dung bài học) · `GET /lessons/{id}/video` (presigned GET) · `PUT /lessons/{id}/progress` |
 | Tài liệu | `POST /uploads/presign` · `POST /uploads/{id}/complete` · `POST /lessons/{id}/sources` → 202 · `GET /lessons/{id}/sources` · `GET /sources/{id}` · `POST /sources/{id}/reprocess` → 202 · `GET /sources/{id}/pages?page=&size=` (`size ≤ 100`, trả `{items, total, page, size}`) |
-| Tutor | `POST /tutor/sessions` · `GET /tutor/sessions?course_id=` (phiên của chính mình, phân trang) · `GET /tutor/availability?course_id=&lesson_id=` (`{available, ready_chunks, message}`) · `GET /tutor/sessions/{id}/messages` · `POST /tutor/sessions/{id}/messages` (SSE, frontend đọc bằng `fetch` + `ReadableStream`) · `POST /tutor/messages/{id}/feedback` |
+| Tutor | `POST /tutor/sessions` · `GET /tutor/sessions?course_id=` (phiên của chính mình, phân trang) · `GET /tutor/availability?course_id=&lesson_id=` (`{available, ready_chunks, message, state, processing_docs, can_queue}`) · `POST /tutor/sessions/{id}/questions` → 202 (câu hỏi chờ khi tài liệu đang xử lý) · `GET /tutor/sessions/{id}/messages` · `POST /tutor/sessions/{id}/messages` (SSE, frontend đọc bằng `fetch` + `ReadableStream`) · `POST /tutor/messages/{id}/feedback` |
 | Câu hỏi | `POST /lessons/{id}/questions/generate` → 202 · `GET /lessons/{id}/questions?review_status=` · `PATCH /questions/{id}` |
 | Quiz | `POST /quizzes` · `GET /quizzes?lesson_id=` (phân trang) · `GET/PATCH/DELETE /quizzes/{id}` · `POST /quizzes/{id}/publish` · `POST /quizzes/{id}/attempts` (**không trả đáp án**) · `PUT /attempts/{id}/answers/{qid}` · `POST /attempts/{id}/submit {final_answers?}` · `GET /attempts/{id}/result` (chỉ khi `completed` hoặc `timed_out`) · `POST /attempts/{id}/answers/{qid}/explain` |
 | Assignment | CRUD `/assignments` · `PUT /assignments/{id}/submission` · `GET /assignments/{id}/submissions` · `POST /submissions/{id}/grade` |
@@ -764,3 +764,7 @@
 | 2026-10-07 | Khu quản trị: ẩn khóa dùng lại status=archived + hidden_at/hidden_reason; từ chối chỉ áp cho giảng viên đang chờ, vi phạm sau khi duyệt thì khóa; mọi thao tác ghi admin_actions; seed_admin từ chối email `.local`. |
 | 2026-10-07 | Email: xác nhận khi đăng ký (chặn đăng nhập tới khi xác nhận, gửi lại tối đa 3 lần/giờ, luôn 202); outbox ghi cùng transaction, worker gửi (kick + cron mỗi phút, SKIP LOCKED, thử lại 5 lần); dev dùng Mailpit, chạy thật dùng Brevo SMTP. Giảng viên chỉ vào hàng chờ khi đã xác nhận email. 👎 của AI Tutor: admin thấy tên học viên, giảng viên thì không. |
 | 2026-10-12 | Tầng S: cache có phiên bản (fail-open), rate limit đăng nhập 20/phút/IP (vì NAT ở trường), Caddy + sslip.io (web và API cùng tên miền, /api đi thẳng tới FastAPI), email qua Brevo, deploy bằng build trên VPS + rollback tự động theo /ready, backup pg_dump + tar MinIO giữ 7 ngày |
+| 2026-10-12 | Quên mật khẩu qua email: link 60 phút dùng một lần (token SHA-256 trong `email_tokens`, purpose `reset_password`), xin link mới thì link cũ vô hiệu, đặt mật khẩu mới thu hồi mọi phiên và xác nhận luôn email; luôn 202; 3 lần/giờ/email, 10 lần/giờ/IP; nội dung email bị xóa khỏi outbox sau khi gửi |
+| 2026-10-12 | Thêm provider `openrouter` cho LLM, vision, embedding (API kiểu OpenAI); embedding gửi `dimensions`, cắt về `EMBED_DIM` rồi chuẩn hóa; script `reembed` (đổi model nhúng) và `check_openrouter` |
+| 2026-10-12 | AI Tutor: `availability` có `state` (ready/processing/model_mismatch/failed/empty/draft); lúc tài liệu đang xử lý vẫn gửi được câu hỏi (`waiting_for_docs`, tối đa 5 câu/phiên), job `tutor_waiting` sau `ingest_pdf` + cron 5 phút trả lời bằng đúng luồng Tutor, nhận câu bằng UPDATE có điều kiện, câu trả lời ghi `created_at` của câu hỏi |
+| 2026-10-12 | Trích PDF: chèn lại dấu cách bị mất ở PDF xuất từ slide (hai ký tự cách nhau > 10% cỡ chữ mà không có dấu cách); script `reprocess_pdfs` xử lý lại hàng loạt; `app.scripts.lock_user` khóa/mở khóa tài khoản bằng lệnh (kể cả admin, không khóa admin cuối cùng) |
```

- [x] **Bước 2: Báo cáo.** Thư mục `docs/report/` đã được chép sẵn vào repo (chưa commit): `README.md`, `00-mo-dau.md` … `05-ket-luan.md`, `build/` (`build.py`, `numbering.lua`, `mermaid.json`), `figures/so-do-01.png` … `so-do-06.png`, `bao-cao-do-an.docx`. Không sửa nội dung; chỉ kiểm tra `git status` thấy đúng các file này rồi commit.

```powershell
git add docs
git commit -m "docs: bản nháp báo cáo đồ án (Markdown + Word), cập nhật spec 2026-10-12"
```

---

## Task 4: Kiểm tay (bạn làm)

Sau khi pull: `docker compose up -d --build api worker`.

- [ ] **Khóa admin cũ:**

```powershell
docker compose exec api python -m app.scripts.lock_user admin@lms.local --reason "Tài khoản cũ"
```

Kỳ vọng: `Đã khóa: admin@lms.local (admin)`. Trang quản trị → Người dùng: tài khoản này hiện "Đã khóa". Thử khóa admin đang dùng (khi nó là admin cuối cùng còn hoạt động): báo "Không thể khóa quản trị viên cuối cùng còn hoạt động".

- [ ] **Xử lý lại slide cũ** (khóa "kttt", `.env` vẫn `fake` nên không tốn tiền):

```powershell
cd backend
uv run python -m scripts.reprocess_pdfs --course kttt-8feb7f
uv run python -m scripts.reprocess_pdfs --course kttt-8feb7f --yes
```

Lần đầu chỉ liệt kê; lần hai in "Đã xếp hàng xử lý lại N tài liệu". Đợi worker xong (`docker compose logs -f worker`).

- [ ] **Kiểm tra chữ:** giảng viên mở tài liệu → "Xem các trang", hoặc:

```powershell
docker compose exec db psql -U lms -d lms -P pager=off -c "select page_no, left(markdown, 200) from source_pages where markdown like '%hiệu quả%' limit 5;"
```

Kỳ vọng: "hiệu quả sử dụng", "phổ và" đã có dấu cách. Sinh câu hỏi lại: đoạn trích trong câu hỏi không còn chữ dính. Nếu vẫn còn chỗ dính, chép lại đúng đoạn đó gửi Claude.

- [ ] **Báo cáo:** mở `docs/report/bao-cao-do-an.docx` bằng Word, chọn **Yes** khi hỏi cập nhật trường (mục lục). Điền các chỗ `[CẦN ĐIỀN: ...]` vào file `.md` tương ứng (không sửa trực tiếp file Word, vì dựng lại sẽ mất), rồi dựng lại theo `docs/report/README.md`.
