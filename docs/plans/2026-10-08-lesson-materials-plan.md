# Tài liệu PDF hiện ngay trong bài: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** khi kiểm tay, bài chỉ có file PDF (giảng viên chưa viết nội dung chữ) hiện "Bài này chưa có nội dung đọc", và học viên không thấy file đâu: PDF chỉ được dùng cho AI Tutor. Tài liệu giảng viên tải lên phải **hiện cho học viên như video**, kể cả khi AI chưa đọc xong.

**Mục tiêu:**

- Dưới nội dung bài có mục **"Tài liệu của bài"**: tên file gốc (ví dụ "Kỹ thuật truyền thông"), số trang, nút **Xem** (xem ngay trong trang; điện thoại mở thẻ mới) và **Tải xuống** (giữ đúng tên file tiếng Việt).
- Hiện **ngay khi tải lên**: lúc AI còn đang đọc thì ghi "AI đang đọc tài liệu, bạn vẫn xem được ngay".
- "Bài này chưa có nội dung đọc" chỉ hiện khi bài không có chữ, video lẫn tài liệu.
- Tài liệu xử lý lỗi: chỉ giảng viên / admin thấy (để biết mà tải lại), học viên không thấy.
- Trang soạn bài hiện tên file thay cho "Tài liệu 1"; tiêu đề đổi thành "Tài liệu của bài" và nói rõ học viên xem được ngay.
- Tab **Tài liệu** ở cột "Trợ lý học tập" (AI Studio) cũng hiện tài liệu đang xử lý.

**Làm sau plan AI Studio Task 1–11** (`2026-10-08-ai-studio-plan.md`): plan này sửa các file AI Studio tạo ra (`studio/service.py`, `documents-panel.tsx`…). Các diff dưới đây được tạo trên đúng bản đó. Làm **trước** plan tầng S.

**Mã trong plan đã được chạy thử** trên bản đã xong plan admin + AI Studio:

- Backend: **682 test pass** (681 + 1 mới; `test_storage` có thêm kiểm tra). `ruff` sạch. Migration mới `f4c2a7d91b35` lên / xuống / `alembic check` đều sạch.
- Frontend: `tsc`, `eslint` sạch; **106 unit test pass**; **77 E2E pass + 1 bỏ qua có chủ ý** (2 kịch bản mới, chạy ở 375px và 1280px, có axe).

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit.

### Hợp đồng API (chỉ thêm trường, không phá client cũ)

| Endpoint | Thay đổi |
|---|---|
| `POST /uploads/presign` | Nhận thêm `filename` (không bắt buộc). Server chỉ giữ tên file: bỏ `C:\...` hay `/...`, bỏ ký tự điều khiển, gộp khoảng trắng, tối đa 255 ký tự |
| `GET /lessons/{id}/sources` (giảng viên) | `SourceOut` có thêm `file_name` |
| `GET /lessons/{id}/documents` | Trả **mọi** PDF của bài, kể cả `pending` / `processing`; thêm `file_name`, `status`; `page_count` = 0 khi chưa xử lý xong; `title` = tên AI suy ra → tên file (bỏ `.pdf`) → "Tài liệu N". Học viên không thấy tài liệu `failed` |
| `GET /sources/{id}/file?download=true` | Không cần chờ xử lý xong. `download=true`: tải về với tên gốc, header `Content-Disposition` có tên ASCII dự phòng + `filename*=UTF-8''…` (RFC 6266). Học viên mở tài liệu `failed` → 404 |

---

## Task 1: Backend

**Files:**
- Create: `backend/alembic/versions/f4c2a7d91b35_asset_original_name.py`
- Modify: `backend/app/modules/materials/models.py`, `schemas.py`, `assets.py`, `sources.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/modules/studio/schemas.py`, `service.py`, `router.py`
- Test: `backend/tests/test_studio.py`, `backend/tests/test_storage.py`, `backend/tests/helpers.py`

- [x] **Bước 1: Viết test (sẽ fail)**

`tests/helpers.py`: `upload_file` nhận thêm `filename`.

```diff
--- a/tests/helpers.py
+++ b/tests/helpers.py
@@ -97,11 +97,14 @@
     return r.json(), section, lesson
 
 
-async def upload_file(client, storage, headers, data: bytes, kind="pdf", mime="application/pdf") -> str:
+async def upload_file(
+    client, storage, headers, data: bytes, kind="pdf", mime="application/pdf", filename: str | None = None
+) -> str:
     """Presign → 'upload' vào key tạm của storage giả → complete. Trả về asset_id."""
-    r = await client.post(
-        f"{API}/uploads/presign", json={"kind": kind, "mime": mime, "size": len(data)}, headers=headers
-    )
+    body = {"kind": kind, "mime": mime, "size": len(data)}
+    if filename is not None:
+        body["filename"] = filename
+    r = await client.post(f"{API}/uploads/presign", json=body, headers=headers)
     assert r.status_code == 200, r.text
     storage.client_put(r.json()["put_url"], data, mime)  # vào key tạm; complete sẽ copy sang key chính thức
     done = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=headers)
```

`tests/test_studio.py`: thêm `test_documents_show_while_processing_with_original_file_name` (và 2 import).

```diff
--- a/tests/test_studio.py
+++ b/tests/test_studio.py
@@ -12,7 +12,7 @@
 from app.core.db import SessionLocal
 from app.modules.jobs.models import Job, JobStatus
 from app.modules.jobs.service import create_job
-from app.modules.materials.models import Source
+from app.modules.materials.models import Source, SourceStatus
 from app.modules.studio.generation import (
     batches,
     fingerprint,
@@ -26,7 +26,8 @@
 from app.worker.tasks import ingest_pdf, source_guide, studio_gen
 from tests.factories import LONG_LESSON_TEXT, seed_chunks
 from tests.fakes import RecordingQueue
-from tests.helpers import API, make_published_course, make_student, make_teacher
+from tests.helpers import API, make_published_course, make_student, make_teacher, upload_file
+from tests.pdfs import make_pdf
 from tests.test_ai_retry import Sleeps
 
 
@@ -284,6 +285,45 @@
         assert (await client.get(f"{API}{path}", headers=outsider)).status_code == 403, path
 
 
+async def test_documents_show_while_processing_with_original_file_name(client, db, storage):
+    gv, sv, _course, lesson = await _course_with_chunks(client, db)
+    asset_id = await upload_file(
+        client, storage, gv, make_pdf(["Noi dung"]), filename="C:\\Bai giang\\Kỹ thuật  truyền thông.pdf"
+    )
+    r = await client.post(f"{API}/lessons/{lesson['id']}/sources", json={"asset_id": asset_id}, headers=gv)
+    assert r.status_code == 202 and r.json()["source"]["file_name"] == "Kỹ thuật truyền thông.pdf"
+    new_id = r.json()["source"]["id"]
+
+    # Học viên thấy ngay tài liệu đang chờ xử lý, kèm tên file gốc (bỏ đường dẫn, gộp khoảng trắng)
+    docs = (await client.get(f"{API}/lessons/{lesson['id']}/documents", headers=sv)).json()
+    # (seed_chunks không tạo source_pages nên tài liệu 1 cũng có page_count = 0)
+    assert [(d["title"], d["status"], d["page_count"]) for d in docs] == [
+        ("Tài liệu 1", "ready", 0),
+        ("Kỹ thuật truyền thông", "pending", 0),
+    ]
+    assert docs[1]["file_name"] == "Kỹ thuật truyền thông.pdf"
+
+    # Mở / tải được ngay, không chờ AI. Tải về giữ tên tiếng Việt (filename* theo RFC 6266)
+    assert (await client.get(f"{API}/sources/{new_id}/file", headers=sv)).status_code == 200
+    r = await client.get(f"{API}/sources/{new_id}/file", params={"download": "true"}, headers=sv)
+    assert r.status_code == 200
+    disposition = [h for h in storage.signed_gets.values() if "response-content-disposition" in h][-1]
+    assert disposition["response-content-disposition"] == (
+        'attachment; filename="Ky thuat truyen thong.pdf"; '
+        "filename*=UTF-8''K%E1%BB%B9%20thu%E1%BA%ADt%20truy%E1%BB%81n%20th%C3%B4ng.pdf"
+    )
+
+    # Xử lý lỗi: chỉ giảng viên còn thấy (để tải lại), học viên không thấy và không mở được
+    source = await db.get(Source, uuid.UUID(new_id))
+    source.status = SourceStatus.failed
+    await db.commit()
+    assert len((await client.get(f"{API}/lessons/{lesson['id']}/documents", headers=sv)).json()) == 1
+    assert (await client.get(f"{API}/sources/{new_id}/file", headers=sv)).status_code == 404
+    teacher_docs = (await client.get(f"{API}/lessons/{lesson['id']}/documents", headers=gv)).json()
+    assert [d["status"] for d in teacher_docs] == ["ready", "failed"]
+    assert (await client.get(f"{API}/sources/{new_id}/file", headers=gv)).status_code == 200
+
+
 async def test_source_guide_job_fills_guide(client, db):
     _, sv, _course, lesson = await _course_with_chunks(client, db)
     source_id = (await db.scalars(select(Source.id).where(Source.lesson_id == uuid.UUID(lesson["id"])))).one()
```

`tests/test_storage.py`: tên tiếng Việt khi tải xuống.

```diff
--- a/tests/test_storage.py
+++ b/tests/test_storage.py
@@ -16,6 +16,10 @@
         "response-content-type": "text/plain",
         "response-content-disposition": 'attachment; filename="bai.txt"',
     }
+    # Tên tiếng Việt: tên ASCII dự phòng (đ → d) + filename* UTF-8 cho trình duyệt hiện đại
+    assert download_headers("application/pdf", "Đề cương.pdf")["response-content-disposition"] == (
+        "attachment; filename=\"De cuong.pdf\"; filename*=UTF-8''%C4%90%E1%BB%81%20c%C6%B0%C6%A1ng.pdf"
+    )
 
 
 async def test_presign_get_signs_public_host_with_content_type():
```

Chạy `uv run pytest tests/test_studio.py tests/test_storage.py -q`. Expected: fail (`filename` bị bỏ qua, chưa có `file_name`, header hỏng với tên có dấu).

- [x] **Bước 2: Cột `assets.original_name` + migration**

```diff
--- a/app/modules/materials/models.py
+++ b/app/modules/materials/models.py
@@ -43,6 +43,8 @@
     mime: Mapped[str] = mapped_column(String(100))
     size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
     verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
+    # Tên file gốc trên máy người tải (đã bỏ đường dẫn): hiện cho học viên và dùng làm tên khi tải xuống
+    original_name: Mapped[str | None] = mapped_column(String(255))
 
 
 class SourceType(str, enum.Enum):
```

`alembic/versions/f4c2a7d91b35_asset_original_name.py` (chạy `uv run alembic heads` trước: phải ra `e3b8c1f4a902`; khác thì sửa `down_revision` theo head thật):

```python
"""assets.original_name: tên file gốc để hiện tài liệu trong bài và tải về đúng tên

Revision ID: f4c2a7d91b35
Revises: e3b8c1f4a902
Create Date: 2026-10-08 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4c2a7d91b35"
down_revision: str | Sequence[str] | None = "e3b8c1f4a902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Chỉ thêm cột nullable: file tải lên trước đây vẫn hiện được (tên "Tài liệu N")
    op.add_column("assets", sa.Column("original_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("assets", "original_name")
```

- [x] **Bước 3: Presign giữ tên file; danh sách tài liệu của giảng viên trả `file_name`**

```diff
--- a/app/modules/materials/schemas.py
+++ b/app/modules/materials/schemas.py
@@ -12,6 +12,7 @@
     kind: Literal["pdf", "video", "submission", "image"]
     mime: str = Field(max_length=100)
     size: int = Field(gt=0)
+    filename: str | None = Field(default=None, max_length=255)  # tên file gốc, chỉ để hiển thị / tải xuống
 
 
 class PresignOut(BaseModel):
@@ -48,6 +49,7 @@
     page_count: int
     vision_pages: int  # số trang trích bằng vision (source_pages.extraction_method = 'vision')
     chunk_count: int
+    file_name: str | None  # tên file gốc (file tải lên trước khi có cột này thì None)
 
 
 class SourceCreated(BaseModel):
```

```diff
--- a/app/modules/materials/assets.py
+++ b/app/modules/materials/assets.py
@@ -43,6 +43,16 @@
     return AppError("INVALID_FILE_TYPE", "Định dạng file không hợp lệ", 400)
 
 
+def clean_filename(name: str | None) -> str | None:
+    """Chỉ giữ tên file (bỏ đường dẫn C:\\... hay /...), bỏ ký tự điều khiển, gộp khoảng trắng. Rỗng → None."""
+    if not name:
+        return None
+    base = name.replace("\\", "/").rsplit("/", 1)[-1]
+    base = "".join(ch for ch in base if ch.isprintable())
+    base = " ".join(base.split())[:255]
+    return base or None
+
+
 def mime_matches(declared: str, head: bytes) -> bool:
     """So magic bytes của 2KB đầu với mime đã khai báo. Text thuần thì không có magic bytes."""
     guessed = filetype.guess(head)
@@ -62,7 +72,14 @@
     if data.size > SIZE_LIMITS[kind]:
         raise _too_large()
     key = f"{kind.value}/{user.id}/{uuid.uuid4().hex}.{EXTENSIONS[data.mime]}"
-    asset = Asset(owner_id=user.id, kind=kind, storage_key=key, mime=data.mime, size_bytes=0)
+    asset = Asset(
+        owner_id=user.id,
+        kind=kind,
+        storage_key=key,
+        mime=data.mime,
+        size_bytes=0,
+        original_name=clean_filename(data.filename),
+    )
     db.add(asset)
     await db.commit()
     # Trình duyệt chỉ nhận URL ghi vào key tạm; key chính thức chỉ có server ghi sau khi kiểm tra xong.
```

```diff
--- a/app/modules/materials/sources.py
+++ b/app/modules/materials/sources.py
@@ -15,6 +15,7 @@
 from app.modules.jobs.service import create_and_enqueue, create_job
 from app.modules.materials.assets import require_verified_asset
 from app.modules.materials.models import (
+    Asset,
     AssetKind,
     Chunk,
     ExtractionMethod,
@@ -44,10 +45,10 @@
     return row[0]
 
 
-async def _counts(db: AsyncSession, source_ids: list[uuid.UUID]) -> tuple[dict, dict]:
-    """Đếm trang, trang vision và chunk cho nhiều source bằng các truy vấn GROUP BY (không N+1)."""
+async def _counts(db: AsyncSession, source_ids: list[uuid.UUID]) -> tuple[dict, dict, dict]:
+    """Đếm trang, trang vision và chunk cho nhiều source bằng các truy vấn GROUP BY (không N+1), kèm tên file gốc."""
     if not source_ids:
-        return {}, {}
+        return {}, {}, {}
     page_rows = await db.execute(
         select(
             SourcePage.source_id,
@@ -62,13 +63,19 @@
         .where(Chunk.source_id.in_(source_ids))
         .group_by(Chunk.source_id)
     )
+    name_rows = await db.execute(
+        select(Source.id, Asset.original_name)
+        .join(Asset, Asset.id == Source.asset_id)
+        .where(Source.id.in_(source_ids))
+    )
     pages = {sid: (total, vision) for sid, total, vision in page_rows}
     chunks = {sid: n for sid, n in chunk_rows}
-    return pages, chunks
+    names = {sid: name for sid, name in name_rows}
+    return pages, chunks, names
 
 
 async def to_out_many(db: AsyncSession, sources: Sequence[Source]) -> list[SourceOut]:
-    pages, chunks = await _counts(db, [s.id for s in sources])
+    pages, chunks, names = await _counts(db, [s.id for s in sources])
     result = []
     for s in sources:
         page_count, vision_pages = pages.get(s.id, (0, 0))
@@ -85,6 +92,7 @@
                 page_count=page_count,
                 vision_pages=vision_pages,
                 chunk_count=chunks.get(s.id, 0),
+                file_name=names.get(s.id),
             )
         )
     return result
```

- [x] **Bước 4: Tải xuống an toàn với tên tiếng Việt** (`app/core/storage.py`)

```diff
--- a/app/core/storage.py
+++ b/app/core/storage.py
@@ -1,8 +1,10 @@
 import asyncio
 import io
+import unicodedata
 from datetime import timedelta
 from functools import lru_cache
 from typing import Protocol
+from urllib.parse import quote
 
 from minio import Minio
 from minio.commonconfig import CopySource
@@ -18,11 +20,24 @@
     return STAGING_PREFIX + key
 
 
+def content_disposition(download_name: str) -> str:
+    """attachment; filename=... an toàn với tên tiếng Việt (RFC 6266): tên ASCII dự phòng + filename* UTF-8."""
+    if download_name.isascii() and '"' not in download_name and "\\" not in download_name:
+        return f'attachment; filename="{download_name}"'
+    fallback = (
+        unicodedata.normalize("NFKD", download_name.replace("đ", "d").replace("Đ", "D"))
+        .encode("ascii", "ignore")
+        .decode()
+    )
+    fallback = "".join(ch for ch in fallback if ch.isprintable() and ch not in '"\\') or "download"
+    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(download_name, safe='')}"
+
+
 def download_headers(mime: str, download_name: str | None = None) -> dict[str, str]:
     """Header response ký kèm presigned GET: luôn trả đúng Content-Type, thêm attachment nếu có tên file."""
     headers = {"response-content-type": mime}
     if download_name:
-        headers["response-content-disposition"] = f'attachment; filename="{download_name}"'
+        headers["response-content-disposition"] = content_disposition(download_name)
     return headers
 
 
```

- [x] **Bước 5: API tài liệu của bài** (`app/modules/studio/schemas.py`, `service.py`, `router.py`)

```diff
--- a/app/modules/studio/schemas.py
+++ b/app/modules/studio/schemas.py
@@ -5,6 +5,7 @@
 from pydantic import BaseModel, Field, field_validator
 
 from app.core.pagination import Page
+from app.modules.materials.models import SourceStatus
 from app.modules.studio.models import ArtifactKind, StudioStatus
 
 
@@ -17,11 +18,16 @@
 
 
 class DocumentOut(BaseModel):
-    """Một tài liệu PDF đã xử lý xong của bài, kèm hướng dẫn (S1). guide=None: chưa có (đang chờ sinh)."""
+    """Một tài liệu PDF của bài, kèm hướng dẫn (S1). Hiện ngay khi tải lên, không chờ AI xử lý xong:
+    học viên mở / tải được file trong lúc AI còn đọc. guide=None: chưa có hướng dẫn."""
 
     source_id: uuid.UUID
-    title: str  # tên AI suy ra; chưa có thì "Tài liệu N"
-    page_count: int
+    title: str  # tên AI suy ra; chưa có thì tên file gốc (bỏ .pdf); không có nữa thì "Tài liệu N"
+    file_name: str | None  # tên file gốc
+    status: (
+        SourceStatus  # pending / processing: AI đang đọc; ready: AI dùng được; failed: chỉ giảng viên thấy
+    )
+    page_count: int  # 0 khi chưa xử lý xong
     guide: GuideOut | None
 
 
```

```diff
--- a/app/modules/studio/service.py
+++ b/app/modules/studio/service.py
@@ -62,30 +62,37 @@
 # ---------- tài liệu (S1) và xem trước nguồn (S5) ----------
 
 
+def _doc_title(guide_title: str | None, file_name: str | None, index: int) -> str:
+    if guide_title:
+        return guide_title
+    if file_name:
+        return file_name[:-4] if file_name.lower().endswith(".pdf") else file_name
+    return f"Tài liệu {index}"
+
+
 async def lesson_documents(db: AsyncSession, user: User, lesson_id: uuid.UUID) -> list[DocumentOut]:
-    await ensure_lesson_access(db, lesson_id, user)
+    """Mọi PDF của bài, kể cả đang xử lý. Tài liệu xử lý lỗi chỉ giảng viên / admin thấy (để biết mà tải lại)."""
+    _, course = await ensure_lesson_access(db, lesson_id, user)
     pages = select(SourcePage.source_id, func.count().label("n")).group_by(SourcePage.source_id).subquery()
-    rows = (
-        await db.execute(
-            select(Source.id, func.coalesce(pages.c.n, 0), SourceGuide)
-            .outerjoin(pages, pages.c.source_id == Source.id)
-            .outerjoin(SourceGuide, SourceGuide.source_id == Source.id)
-            .where(
-                Source.lesson_id == lesson_id,
-                Source.status == SourceStatus.ready,
-                Source.type == SourceType.pdf,
-            )
-            .order_by(Source.created_at, Source.id)
-        )
-    ).all()
+    stmt = (
+        select(Source.id, Source.status, Asset.original_name, func.coalesce(pages.c.n, 0), SourceGuide)
+        .join(Asset, Asset.id == Source.asset_id)
+        .outerjoin(pages, pages.c.source_id == Source.id)
+        .outerjoin(SourceGuide, SourceGuide.source_id == Source.id)
+        .where(Source.lesson_id == lesson_id, Source.type == SourceType.pdf)
+        .order_by(Source.created_at, Source.id)
+    )
+    if not is_course_staff(course, user):
+        stmt = stmt.where(Source.status != SourceStatus.failed)
     out = []
-    for i, (source_id, page_count, guide) in enumerate(rows, 1):
-        title = guide.title if guide is not None and guide.title else f"Tài liệu {i}"
+    for i, (source_id, status, file_name, page_count, guide) in enumerate((await db.execute(stmt)).all(), 1):
         out.append(
             DocumentOut(
                 source_id=source_id,
-                title=title,
-                page_count=page_count,
+                title=_doc_title(guide.title if guide is not None else None, file_name, i),
+                file_name=file_name,
+                status=status,
+                page_count=page_count if status == SourceStatus.ready else 0,
                 guide=None
                 if guide is None
                 else GuideOut(
@@ -100,19 +107,30 @@
     return out
 
 
-async def source_file_url(db: AsyncSession, storage: Storage, user: User, source_id: uuid.UUID) -> str:
-    """URL ký sẵn (1 giờ) để mở PDF trong trình duyệt; frontend thêm #page=N để nhảy tới trang."""
+async def source_file_url(
+    db: AsyncSession, storage: Storage, user: User, source_id: uuid.UUID, *, download: bool = False
+) -> str:
+    """URL ký sẵn (1 giờ) để xem PDF trong trình duyệt (frontend thêm #page=N để nhảy tới trang), hoặc tải về
+    với tên file gốc. Không cần chờ AI xử lý xong: file đã được kiểm tra lúc tải lên."""
     row = (
         await db.execute(
-            select(Source, Asset.storage_key, Asset.mime)
+            select(Source, Asset.storage_key, Asset.mime, Asset.original_name)
             .join(Asset, Asset.id == Source.asset_id)
             .where(Source.id == source_id)
         )
     ).one_or_none()
-    if row is None or row[0].status != SourceStatus.ready:
+    if row is None:
+        raise not_found("Tài liệu")
+    source, key, mime, file_name = row
+    _, course = await ensure_lesson_access(db, source.lesson_id, user)
+    if source.status == SourceStatus.failed and not is_course_staff(course, user):
         raise not_found("Tài liệu")
-    await ensure_lesson_access(db, row[0].lesson_id, user)
-    return await storage.presign_get(row[1], row[2])
+    name = None
+    if download:
+        name = file_name or "tai-lieu.pdf"
+        if not name.lower().endswith(".pdf"):
+            name += ".pdf"
+    return await storage.presign_get(key, mime, download_name=name)
 
 
 async def chunk_detail(db: AsyncSession, user: User, chunk_id: uuid.UUID) -> ChunkOut:
```

```diff
--- a/app/modules/studio/router.py
+++ b/app/modules/studio/router.py
@@ -43,19 +43,20 @@
 async def lesson_documents(
     lesson_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
 ):
-    """Tài liệu PDF đã xử lý xong của bài + hướng dẫn (tóm tắt, chủ đề, câu hỏi gợi ý). Quyền như xem bài học."""
+    """Tài liệu PDF của bài (kể cả đang xử lý) + hướng dẫn (tóm tắt, chủ đề, câu hỏi gợi ý). Quyền như xem bài học."""
     return await service.lesson_documents(db, user, lesson_id)
 
 
 @router.get("/sources/{source_id}/file", response_model=FileUrlOut)
 async def source_file(
     source_id: uuid.UUID,
+    download: bool = False,
     user: User = Depends(get_current_user),
     db: AsyncSession = Depends(get_db),
     storage: Storage = Depends(get_storage),
 ):
-    """URL ký sẵn (1 giờ) để mở file PDF; thêm #page=N để nhảy tới trang."""
-    return FileUrlOut(url=await service.source_file_url(db, storage, user, source_id))
+    """URL ký sẵn (1 giờ) để mở file PDF (thêm #page=N để nhảy tới trang). download=true: tải về với tên file gốc."""
+    return FileUrlOut(url=await service.source_file_url(db, storage, user, source_id, download=download))
 
 
 @router.get("/chunks/{chunk_id}", response_model=ChunkOut)
```

- [x] **Bước 6: Chạy**

```bash
uv run alembic upgrade head && uv run alembic check      # No new upgrade operations detected.
uv run pytest tests/test_studio.py tests/test_storage.py tests/test_uploads.py tests/test_sources_api.py -q
uv run pytest -q                                           # Expected: 682 passed
uv run ruff check . && uv run ruff format --check .
docker compose up -d --build api worker
```

- [x] **Bước 7: Commit**

```bash
git add backend && git commit -m "feat(api): lesson PDFs visible right after upload, original file names, Vietnamese-safe downloads"
```

---

## Task 2: Frontend

**Files:**
- Create: `frontend/src/components/lesson/lesson-materials.tsx`
- Modify: `frontend/src/lib/api/upload.ts`, `frontend/src/lib/studio/queries.ts`, `frontend/src/components/lesson/lesson-view.tsx`, `frontend/src/components/studio/documents-panel.tsx`, `frontend/src/components/teach/source-list.tsx`
- Modify: `frontend/src/lib/api/schema.d.ts`, `frontend/openapi.json` (sinh lại)

- [ ] **Bước 1: Sinh lại kiểu API** (backend đã chạy bản Task 1): `cd frontend`, rồi `npm run gen:api`. Kiểm tra `schema.d.ts` có `file_name` và `filename`.

- [ ] **Bước 2: Gửi tên file khi tải lên** (`src/lib/api/upload.ts`)

```diff
--- a/src/lib/api/upload.ts
+++ b/src/lib/api/upload.ts
@@ -23,7 +23,7 @@
 /** presign → PUT (có tiến trình) → complete. Trả về asset_id đã được server xác minh. */
 export async function uploadAsset(kind: UploadKind, file: File, onProgress: UploadProgress, signal?: AbortSignal) {
   const { asset_id, put_url } = await unwrap(
-    api.POST("/api/v1/uploads/presign", { body: { kind, mime: file.type, size: file.size } }),
+    api.POST("/api/v1/uploads/presign", { body: { kind, mime: file.type, size: file.size, filename: file.name } }),
   );
   await putWithProgress(put_url, file, onProgress, signal);
   await unwrap(api.POST("/api/v1/uploads/{asset_id}/complete", { params: { path: { asset_id } } }));
```

- [ ] **Bước 3: Truy vấn** (`src/lib/studio/queries.ts`): hỏi lại khi còn tài liệu đang xử lý; thêm `sourceFileUrl` và `downloadSourcePdf`.

```diff
--- a/src/lib/studio/queries.ts
+++ b/src/lib/studio/queries.ts
@@ -119,16 +119,32 @@
     queryKey: studioKeys.documents(lessonId),
     enabled,
     queryFn: () => unwrap(api.GET("/api/v1/lessons/{lesson_id}/documents", { params: { path: { lesson_id: lessonId } } })),
-    // hướng dẫn tài liệu được sinh nền sau khi xử lý PDF: còn tài liệu chưa có hướng dẫn thì hỏi lại
-    refetchInterval: (q) => (q.state.data?.some((d) => !d.guide || d.guide.status === "generating") ? POLL_MS * 2 : false),
+    // PDF còn đang xử lý, hoặc hướng dẫn tài liệu (sinh nền sau khi xử lý xong) chưa có: hỏi lại
+    refetchInterval: (q) =>
+      q.state.data?.some((d) => d.status === "pending" || d.status === "processing" || (d.status === "ready" && (!d.guide || d.guide.status === "generating")))
+        ? POLL_MS * 2
+        : false,
   });
 }
 
+/** URL ký sẵn để xem PDF (download=true: tải về với tên file gốc). Chỉ sống 1 giờ nên lấy lúc bấm. */
+export async function sourceFileUrl(sourceId: string, download = false) {
+  const { url } = await unwrap(
+    api.GET("/api/v1/sources/{source_id}/file", { params: { path: { source_id: sourceId }, query: { download } } }),
+  );
+  return url;
+}
+
+/** Tải PDF về máy: server ký URL kèm Content-Disposition attachment nên trình duyệt tải, không rời trang. */
+export async function downloadSourcePdf(sourceId: string) {
+  window.location.assign(await sourceFileUrl(sourceId, true));
+}
+
 /** Mở PDF ở trang N trong thẻ mới (URL ký sẵn chỉ sống 1 giờ nên lấy lúc bấm). */
 export async function openSourcePdf(sourceId: string, page?: number | null) {
   const win = window.open("", "_blank"); // mở trước khi await để trình duyệt không chặn popup
   try {
-    const { url } = await unwrap(api.GET("/api/v1/sources/{source_id}/file", { params: { path: { source_id: sourceId } } }));
+    const url = await sourceFileUrl(sourceId);
     const target = page ? `${url}#page=${page}` : url;
     if (win) win.location.href = target;
     else window.location.href = target;
```

- [ ] **Bước 4: Mục "Tài liệu của bài"** (`src/components/lesson/lesson-materials.tsx`)
  - **Xem**: màn hình rộng nhúng PDF ngay trong trang (cao 75% màn hình, kèm link "Mở trong thẻ mới" phòng khi trình duyệt không hiện); điện thoại mở thẻ mới (trình duyệt di động hiện PDF trong khung rất kém).
  - **Tải xuống**: server ký URL kèm `Content-Disposition: attachment`, trình duyệt tải mà không rời trang.

```tsx
"use client";

import { Download, ExternalLink, Eye, EyeOff, FileText, Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { downloadSourcePdf, type LessonDocument, openSourcePdf, sourceFileUrl, useLessonDocuments } from "@/lib/studio/queries";

/** Màn hình rộng thì xem PDF ngay trong trang; điện thoại (trình duyệt di động hiện PDF trong khung rất kém) mở thẻ mới. */
function canViewInline() {
  return typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches;
}

/**
 * Tài liệu PDF của bài, hiện ngay dưới nội dung bài, kể cả khi bài chưa có nội dung chữ và kể cả khi AI còn đang
 * đọc tài liệu: học viên xem / tải được file ngay. AI Tutor và Studio dùng tài liệu khi đã "sẵn sàng".
 */
export function LessonMaterials({ lessonId }: { lessonId: string }) {
  const docs = useLessonDocuments(lessonId);
  const [viewing, setViewing] = React.useState<{ id: string; url: string } | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  if (!docs.data?.length) return null;

  async function view(doc: LessonDocument) {
    if (viewing?.id === doc.source_id) return setViewing(null);
    if (!canViewInline()) return openSourcePdf(doc.source_id).catch((err) => toast.error(errorMessage(err)));
    setBusy(doc.source_id);
    try {
      setViewing({ id: doc.source_id, url: await sourceFileUrl(doc.source_id) });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="materials-title" className="mt-8">
      <h2 id="materials-title" className="text-lg font-semibold">
        Tài liệu của bài
      </h2>
      <ul className="mt-3 space-y-3">
        {docs.data.map((d) => {
          const open = viewing?.id === d.source_id;
          return (
            <li key={d.source_id} className="rounded-lg border bg-surface p-4">
              <div className="flex flex-wrap items-center gap-3">
                <FileText className="size-5 shrink-0 text-primary" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="font-medium break-words">{d.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {d.status === "ready" ? (
                      `${d.page_count} trang`
                    ) : d.status === "failed" ? (
                      <span className="text-destructive">AI không đọc được tài liệu này (chỉ giảng viên thấy dòng này)</span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <Loader2 className="size-3 animate-spin" aria-hidden /> AI đang đọc tài liệu, bạn vẫn xem được ngay
                      </span>
                    )}
                  </p>
                </div>
                {d.status === "pending" || d.status === "processing" ? <Badge tone="primary">Đang xử lý</Badge> : null}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-pressed={open}
                    aria-label={`${open ? "Ẩn" : "Xem"} ${d.title}`}
                    loading={busy === d.source_id}
                    loadingText="Đang mở…"
                    onClick={() => void view(d)}
                  >
                    {open ? <EyeOff /> : <Eye />} {open ? "Ẩn" : "Xem"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label={`Tải xuống ${d.title}`}
                    onClick={() => downloadSourcePdf(d.source_id).catch((err) => toast.error(errorMessage(err)))}
                  >
                    <Download /> Tải xuống
                  </Button>
                </div>
              </div>
              {open ? (
                <div className="mt-3">
                  <iframe title={`Tài liệu: ${d.title}`} src={viewing.url} className="h-[75vh] w-full rounded-md border bg-white" />
                  <a
                    href={viewing.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-sm text-primary hover:underline"
                  >
                    <ExternalLink className="size-4" aria-hidden /> Không hiện? Mở trong thẻ mới
                  </a>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
```

- [ ] **Bước 5: Gắn vào trang bài học** (`lesson-view.tsx`): đặt dưới nội dung chữ; dòng "Bài này chưa có nội dung đọc" chỉ hiện khi không có chữ, video lẫn tài liệu (đợi danh sách tài liệu tải xong để không nháy).

```diff
--- a/src/components/lesson/lesson-view.tsx
+++ b/src/components/lesson/lesson-view.tsx
@@ -36,9 +36,11 @@
 import { lastLesson, READER_MAX, READER_MIN, readerSize } from "@/lib/study/storage";
 import { useShortcuts } from "@/lib/study/use-shortcuts";
 import { useVideoProgress } from "@/lib/study/use-video-progress";
+import { useLessonDocuments } from "@/lib/studio/queries";
 import { useTutorChat } from "@/lib/tutor/use-tutor-chat";
 import { cn } from "@/lib/utils";
 import { BreakReminder } from "./break-reminder";
+import { LessonMaterials } from "./lesson-materials";
 import { LessonQuizzes } from "./lesson-quizzes";
 import { CourseOutline } from "./course-outline";
 import { ReadingProgress } from "./reading-progress";
@@ -62,6 +64,7 @@
   const course = useCourse(slug);
   const lesson = useLesson(lessonId);
   const video = useLessonVideo(lessonId);
+  const documents = useLessonDocuments(lessonId);
   const desktop = useIsDesktop();
 
   // LessonView chỉ render trên trình duyệt (sau RequireAuth) nên đọc localStorage lúc khởi tạo được
@@ -238,11 +241,13 @@
                   />
                 ) : null}
 
-                {lesson.data.content_md ? (
-                  <Markdown className="mt-6">{lesson.data.content_md}</Markdown>
-                ) : (
+                {lesson.data.content_md ? <Markdown className="mt-6">{lesson.data.content_md}</Markdown> : null}
+                {/* Chỉ báo "trống" khi bài thật sự không có gì: không chữ, không video, không tài liệu */}
+                {!lesson.data.content_md && !video.data && documents.isSuccess && documents.data.length === 0 ? (
                   <p className="mt-6 text-muted-foreground">Bài này chưa có nội dung đọc.</p>
-                )}
+                ) : null}
+
+                <LessonMaterials lessonId={lessonId} />
 
                 <LessonQuizzes slug={slug} lessonId={lessonId} isStudent={isStudent} />
 
```

- [ ] **Bước 6: Tab Tài liệu** (`documents-panel.tsx`) **và trang soạn bài** (`source-list.tsx`)

```diff
--- a/src/components/studio/documents-panel.tsx
+++ b/src/components/studio/documents-panel.tsx
@@ -33,13 +33,19 @@
             <FileText className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
             <div className="min-w-0 flex-1">
               <h3 className="font-semibold">{d.title}</h3>
-              <p className="text-xs text-muted-foreground">{d.page_count} trang</p>
+              <p className="text-xs text-muted-foreground">{d.status === "ready" ? `${d.page_count} trang` : d.file_name}</p>
             </div>
             <Button size="sm" variant="outline" onClick={() => openSourcePdf(d.source_id).catch((err) => toast.error(errorMessage(err)))}>
               Mở PDF
             </Button>
           </div>
-          {!d.guide || d.guide.status === "generating" ? (
+          {d.status === "pending" || d.status === "processing" ? (
+            <p role="status" className="mt-3 flex items-center gap-1.5 text-sm text-muted-foreground">
+              <Loader2 className="size-4 animate-spin" aria-hidden /> AI đang đọc tài liệu. Bạn vẫn mở PDF được ngay.
+            </p>
+          ) : d.status === "failed" ? (
+            <p className="mt-3 text-sm text-destructive">AI không đọc được tài liệu này. Tải lại file ở trang soạn bài.</p>
+          ) : !d.guide || d.guide.status === "generating" ? (
             <p role="status" className="mt-3 flex items-center gap-1.5 text-sm text-muted-foreground">
               <Loader2 className="size-4 animate-spin" aria-hidden /> AI đang đọc tài liệu để viết hướng dẫn…
             </p>
```

```diff
--- a/src/components/teach/source-list.tsx
+++ b/src/components/teach/source-list.tsx
@@ -31,9 +31,11 @@
   return (
     <section aria-labelledby="sources-title" className="space-y-3">
       <h2 id="sources-title" className="font-semibold">
-        Tài liệu cho AI Tutor
+        Tài liệu của bài
       </h2>
-      <p className="text-sm text-muted-foreground">AI Tutor chỉ trả lời dựa trên các tài liệu ở trạng thái Sẵn sàng.</p>
+      <p className="text-sm text-muted-foreground">
+        Học viên xem và tải được ngay sau khi tải lên. AI Tutor và Studio chỉ dùng tài liệu ở trạng thái Sẵn sàng.
+      </p>
 
       {sources.isPending ? (
         <Skeleton className="h-16 w-full" />
@@ -45,7 +47,7 @@
             <li key={s.id} className="rounded-md border p-3 text-sm">
               <div className="flex items-center gap-2">
                 <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
-                <span className="flex-1">Tài liệu {i + 1}</span>
+                <span className="min-w-0 flex-1 break-words">{s.file_name ?? `Tài liệu ${i + 1}`}</span>
                 <Badge tone={STATUS[s.status].tone}>
                   {s.status === "processing" || s.status === "pending" ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
                   {s.status === "ready" ? <CheckCircle2 className="size-3" aria-hidden /> : null}
```

- [ ] **Bước 7:** `npx tsc --noEmit && npx eslint src && npx vitest run` → sạch, 106 pass. Commit:

```bash
git add frontend && git commit -m "feat(web): show lesson PDFs to students with inline view and download"
```

---

## Task 3: E2E

**Files:**
- Modify: `frontend/e2e/studio.spec.ts`

- [ ] **Bước 1:** Sửa mock tab Tài liệu cho đủ trường mới, thêm 2 kịch bản: bài chỉ có PDF (đang xử lý vẫn hiện, xem trong trang ở 1280px / mở thẻ mới ở 375px, tải xuống gửi `download=true`) và bài trống thật sự.

```diff
--- a/e2e/studio.spec.ts
+++ b/e2e/studio.spec.ts
@@ -1,6 +1,6 @@
 import { expect, test } from "@playwright/test";
 import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
-import { COURSE_ID, L1, mockApi, note, studioOverview } from "./mock-api";
+import { COURSE_ID, L1, lesson, mockApi, note, studioOverview } from "./mock-api";
 
 const ART = "a-1";
 const FC = "a-2";
@@ -116,6 +116,8 @@
               {
                 source_id: "src-1",
                 title: "Giáo trình đạo hàm",
+                file_name: "Giáo trình đạo hàm.pdf",
+                status: "ready",
                 page_count: 12,
                 guide: { status: "ready", title: "Giáo trình đạo hàm", summary: "Tài liệu trình bày định nghĩa và quy tắc tính đạo hàm.", topics: ["Định nghĩa", "Quy tắc"], questions: ["Đạo hàm một phía là gì?"] },
               },
@@ -131,6 +133,67 @@
     await expect(page.getByRole("tab", { name: "AI Tutor" })).toHaveAttribute("aria-selected", "true");
   });
 
+  test("bài chỉ có PDF: vẫn hiện tài liệu (kể cả đang xử lý), xem ngay trong trang và tải xuống", async ({ page, isMobile }) => {
+    const fileRequests: string[] = [];
+    await page.route("**/fake-files/**", (r) =>
+      r.fulfill({
+        contentType: "application/pdf",
+        headers: r.request().url().includes("dl=1") ? { "Content-Disposition": 'attachment; filename="slide.pdf"' } : {},
+        body: "%PDF-1.4\n%%EOF\n",
+      }),
+    );
+    await mockApi(page, {
+      extra: {
+        [`GET /lessons/${L1}`]: (r) => r.fulfill({ json: { ...lesson(L1), content_md: "" } }),
+        "GET /lessons/*/documents": (r) =>
+          r.fulfill({
+            json: [
+              { source_id: "src-1", title: "Giáo trình đạo hàm", file_name: "Giáo trình đạo hàm.pdf", status: "ready", page_count: 12, guide: null },
+              { source_id: "src-2", title: "Slide chương 2", file_name: "Slide chương 2.pdf", status: "processing", page_count: 0, guide: null },
+            ],
+          }),
+        "GET /sources/*/file": (r, url) => {
+          fileRequests.push(url.search);
+          const dl = url.searchParams.get("download") === "true";
+          return r.fulfill({ json: { url: `${new URL(r.request().url()).origin}/fake-files/doc.pdf${dl ? "?dl=1" : ""}` } });
+        },
+      },
+    });
+    await page.goto(`/learn/giai-tich-1/${L1}`);
+    const section = page.getByRole("region", { name: "Tài liệu của bài" });
+    await expect(section.getByText("Giáo trình đạo hàm")).toBeVisible();
+    await expect(section.getByText("12 trang")).toBeVisible();
+    await expect(section.getByText(/AI đang đọc tài liệu, bạn vẫn xem được ngay/)).toBeVisible();
+    await expect(page.getByText("Bài này chưa có nội dung đọc.")).toHaveCount(0);
+    await expectAccessible(page);
+    await expectNoHorizontalScroll(page);
+
+    if (isMobile) {
+      // điện thoại: mở thẻ mới thay vì nhúng
+      const popup = page.waitForEvent("popup");
+      await section.getByRole("button", { name: "Xem Slide chương 2" }).click();
+      await popup;
+    } else {
+      await section.getByRole("button", { name: "Xem Slide chương 2" }).click();
+      await expect(section.locator('iframe[title="Tài liệu: Slide chương 2"]')).toBeVisible();
+      await expect(section.getByRole("link", { name: /Mở trong thẻ mới/ })).toBeVisible();
+      await section.getByRole("button", { name: "Ẩn Slide chương 2" }).click();
+      await expect(section.locator("iframe")).toHaveCount(0);
+    }
+
+    const download = page.waitForEvent("download");
+    await section.getByRole("button", { name: "Tải xuống Giáo trình đạo hàm" }).click();
+    await download;
+    expect(fileRequests).toContain("?download=true");
+  });
+
+  test("bài không có chữ, video hay tài liệu: báo bài trống", async ({ page }) => {
+    await mockApi(page, { extra: { [`GET /lessons/${L1}`]: (r) => r.fulfill({ json: { ...lesson(L1), content_md: "" } }) } });
+    await page.goto(`/learn/giai-tich-1/${L1}`);
+    await expect(page.getByText("Bài này chưa có nội dung đọc.")).toBeVisible();
+    await expect(page.getByRole("region", { name: "Tài liệu của bài" })).toHaveCount(0);
+  });
+
   test("AI Tutor: gợi ý hỏi tiếp + lưu câu trả lời vào ghi chú", async ({ page }) => {
     let saved = false;
     await mockApi(page, {
```

- [ ] **Bước 2:** `npx playwright test` → **77 passed, 1 skipped**. Commit:

```bash
git add frontend && git commit -m "test(web): E2E for lesson PDFs"
```

---

## Task 4: Kiểm tay (bạn làm)

- [ ] Giảng viên tạo bài **không viết nội dung chữ**, tải lên một PDF tên có dấu (ví dụ "Kỹ thuật truyền thông.pdf"). Trang soạn bài: mục "Tài liệu của bài" hiện đúng tên file.
- [ ] Học viên mở bài đó **ngay khi PDF còn "Đang xử lý"**:
  - Thấy mục "Tài liệu của bài" với tên file và dòng "AI đang đọc tài liệu…"; không còn "Bài này chưa có nội dung đọc".
  - Bấm **Xem**: PDF hiện ngay trong trang. Nếu khung trắng, bấm "Mở trong thẻ mới" và **ghi lại** (có thể MinIO chặn nhúng khung, cần sửa thêm).
  - Bấm **Tải xuống**: file về máy đúng tên "Kỹ thuật truyền thông.pdf".
- [ ] Đợi xử lý xong: dòng đổi thành "N trang"; AI Tutor hỏi được.
- [ ] F12 chế độ điện thoại 375px: bấm **Xem** mở thẻ mới; trang không cuộn ngang.
- [ ] File tải lên **trước** plan này (không có tên gốc) vẫn hiện, tên "Tài liệu N".
