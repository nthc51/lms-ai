# Khu quản trị và Email: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Mục tiêu:** Plan có hai phần.

- **Phần 1 (Task 1–8):** khu quản trị. Quản trị viên có giao diện riêng thay cho hai script dòng lệnh.
- **Phần 2 (Task 9–14):** email.
  - Đăng ký phải xác nhận email thật.
  - Email thông báo khi duyệt, từ chối, khóa tài khoản, ẩn khóa học.
  - Giảng viên bị từ chối gửi lại được yêu cầu duyệt.
  - Xuất CSV người dùng.
  - Hộp câu trả lời AI Tutor bị học viên chê (👎).
- **Phần 3 (Task 15–16):** sửa các lỗi hai reviewer tìm ra.
- **Task 17:** người dùng tự kiểm tra với backend thật.

Phần 1 gồm:

- Duyệt hoặc từ chối giảng viên mới. Từ chối phải ghi lý do, và giảng viên đọc được lý do đó.
- Xem danh sách giảng viên, học viên; tìm kiếm; khóa và mở khóa tài khoản.
- Xem **mọi** khóa học của mọi giảng viên; ẩn khóa vi phạm kèm lý do và hiện lại khi đã sửa.
- Trang tổng quan: số liệu hệ thống, biểu đồ người dùng mới 14 ngày, nhật ký thao tác quản trị.

**Kiến trúc:**

- **Backend:** module mới `app/modules/admin` (models, schemas, service, router). Mọi route nằm dưới `/api/v1/admin/*` và dùng `require_role(Role.admin)`. Mỗi thao tác ghi một dòng vào bảng `admin_actions` trong cùng transaction.
- **Frontend:** khu `/admin` có menu riêng (Tổng quan, Người dùng, Khóa học), dùng lại design system, `ConfirmDialog`, `Pagination` và cách vẽ bảng cuộn ngang của FE-2.

**Mã trong plan đã được chạy thử:** viết trên `main` sau khi FE-2 xong (Task 1–11). Kết quả phần 1 ở dưới; kết quả phần 2 ở đầu Phần 2.

- Backend: **+17 test mới, toàn bộ pass** (628 test, gồm cả 2 test RetryInfo đang chờ commit trong `test_ai_retry.py`). `ruff check`, `ruff format --check` sạch. `alembic check` báo "No new upgrade operations detected" (migration khớp models).
- Frontend: **100 unit test pass** (92 cũ + 8 mới). **42 test E2E pass** (21 kịch bản × 2 khung hình 375/1280px, có axe WCAG AA), trong đó 7 kịch bản mới. `eslint`, `tsc`, `next build` đều sạch.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit.

---

## 0. Bối cảnh

### 0.1 Điều kiện bắt đầu

- **FE-2 đã xong** (Task 1–11 trên `main`). Plan này sửa `course-editor.tsx` và `e2e/mock-api.ts` ở dạng sau FE-2.
- Backend chạy Docker như mọi khi (`docker compose up -d`). Test backend chỉ chạy **một lượt pytest tại một thời điểm** (chung DB `lms_test`).
- `.env` giữ `*_PROVIDER=fake`.

### 0.2 Hiện trạng và chỗ thiếu

| Có sẵn | Thiếu |
|---|---|
| `users.teacher_status` (pending / approved / rejected), `users.locked_at` (deps đã chặn tài khoản bị khóa ở mọi request) | API và giao diện duyệt / từ chối / khóa. Hiện chỉ có script `approve_teacher` |
| `courses.status` có giá trị `archived` nhưng chưa nơi nào dùng | Cách ẩn khóa vi phạm mà giảng viên không tự xuất bản lại được |
| Script `seed_admin` | Kiểm tra email: `admin@lms.local` tạo được nhưng **không đăng nhập được** (trang đăng nhập dùng `EmailStr`, coi `.local` là tên miền dành riêng) |
| Admin đăng nhập vào trang chủ chung | Chào "Chào viên" (lấy chữ cuối của "Quản trị viên"); không có menu quản trị |

### 0.3 Hợp đồng API mới (tất cả cần quyền admin; người khác nhận 403 `FORBIDDEN`, khách nhận 401)

| Endpoint | Ghi chú |
|---|---|
| `GET /admin/stats` | `students`, `teachers`, `pending_teachers`, `locked_users`, `courses_published`, `courses_draft`, `courses_hidden`, `enrollments`, `tutor_questions_7d`, `quiz_submissions_7d`, `failed_jobs_7d`, `signups_14d[{day, count}]`. Ngày tính theo **giờ Việt Nam**, đủ 14 ngày, ngày trống = 0 |
| `GET /admin/users?role=&status=&q=&page=&size=` | `role`: student / teacher / admin. `status`: pending / approved / rejected / locked. `q` tìm tên (gõ không dấu được) hoặc email. Lọc `pending` thì **ai đăng ký trước lên trước**, còn lại mới nhất lên trước. Mỗi dòng có `course_count`, `enrollment_count`, `review_note` |
| `POST /admin/teachers/{id}/approve` | Duyệt giảng viên đang chờ **hoặc đã bị từ chối** (đổi ý), xóa `review_note`. 409 `ALREADY_APPROVED`. 404 nếu không phải giảng viên |
| `POST /admin/teachers/{id}/reject` `{reason}` | Lý do bắt buộc (cắt khoảng trắng, 1–500 ký tự, toàn khoảng trắng → 422). Chỉ từ chối được người **đang chờ** (409 `NOT_PENDING`) |
| `POST /admin/users/{id}/lock` `{reason?}` | Thu hồi mọi refresh token. Access token còn hạn cũng bị chặn ngay nhờ deps. 409 `CANNOT_LOCK_ADMIN` khi khóa quản trị viên (kể cả chính mình). Khóa lại người đã khóa thì không làm gì |
| `POST /admin/users/{id}/unlock` | Xóa `locked_at`. Xóa lý do khóa, nhưng giữ lý do từ chối giảng viên nếu có |
| `GET /admin/courses?status=&q=` | `status`: published / draft / hidden. `q` tìm theo tên khóa hoặc tên giảng viên. Mỗi dòng có tên, email giảng viên, `lesson_count`, `enrollment_count`, `hidden_at`, `hidden_reason` |
| `POST /admin/courses/{id}/hide` `{reason}` | Chỉ ẩn được khóa đang xuất bản (409 `COURSE_NOT_PUBLISHED`). Chuyển `status = archived`, ghi `hidden_at` và `hidden_reason` |
| `POST /admin/courses/{id}/unhide` | Trả về `published`, xóa lý do. 409 `COURSE_NOT_HIDDEN` |
| `GET /admin/actions` | Nhật ký mới nhất trước: `admin_name`, `action`, `target_type` (user / course), `target_label` (email hoặc tên khóa **lúc thao tác**), `note`, `created_at` |

**Thay đổi ở API cũ (chỉ thêm trường, không phá client cũ):**

- `UserOut` (`/me`) có thêm `review_note`: giảng viên bị từ chối đọc được lý do.
- `CourseOut` / `CourseDetail` có thêm `hidden_reason`: chủ khóa thấy vì sao khóa bị ẩn.
- `POST /courses/{id}/publish` trả 409 `COURSE_HIDDEN` nếu khóa đang bị ẩn. Áp dụng **cả với admin**: muốn hiện lại phải dùng `unhide`, để `hidden_*` và nhật ký luôn khớp.

### 0.4 Các quyết định thiết kế

- **Ẩn khóa dùng lại `status = archived`**: mọi chỗ chặn học viên (danh mục, đăng ký, vào bài, AI Tutor, retrieval) đã kiểm `status == published`, nên **không phải sửa thêm chỗ nào**. Cột `hidden_at` / `hidden_reason` để phân biệt "admin ẩn" với "lưu trữ" sau này, và để chặn giảng viên tự xuất bản lại.
- **Từ chối và khóa là hai việc khác nhau**: từ chối chỉ áp cho giảng viên đang chờ; giảng viên đã duyệt mà vi phạm thì khóa tài khoản.
- **Nhật ký ghi `target_label`** (email / tên khóa lúc thao tác) để vẫn đọc được khi đối tượng bị đổi tên hoặc xóa. `admin_id` dùng `ON DELETE SET NULL`.
- **Giao diện:**
  - Menu admin có 3 mục (thanh dưới điện thoại vẫn tối đa 4 mục). "Chờ duyệt" là **tab đầu tiên** của trang Người dùng, và là ô số liệu nổi bật (viền màu nhấn) ở Tổng quan, bấm vào là tới thẳng danh sách.
  - Mục "Tổng quan" (`/admin`) chỉ sáng khi đứng đúng trang đó, không sáng khi ở `/admin/users`.
  - Nút trong bảng có `aria-label` ghi rõ tên người hoặc khóa (vd. "Duyệt Phạm Văn Cường"), để trình đọc màn hình không đọc năm nút "Duyệt" giống nhau.
  - Lý do nhập trong hộp thoại riêng, ghi rõ "Người dùng sẽ thấy lý do này". Lý do bắt buộc với Từ chối và Ẩn khóa, không bắt buộc với Khóa tài khoản.
  - Bảng cuộn ngang trên điện thoại, nhận focus bằng bàn phím (như FE-2).
  - Biểu đồ đăng ký 14 ngày: một chuỗi số liệu nên không cần chú thích. Cột bo 4px ở đầu, có `title` khi rê chuột, và có **bảng ẩn** cho trình đọc màn hình.
- **Admin vào `/` thì chuyển sang `/admin`.** Đăng nhập xong cũng vào thẳng `/admin`.
- **Giảng viên chưa duyệt hoặc bị từ chối** thấy khung thông báo ở trang chủ: đang chờ, hoặc bị từ chối kèm lý do.
- **Khóa bị ẩn:** trình soạn hiện khung cảnh báo kèm lý do, huy hiệu "Đã bị ẩn", và **ẩn nút Xuất bản**.

### 0.5 File

```
backend/
├── alembic/versions/b81e4c7a2d90_admin.py     # cột mới + bảng admin_actions
├── app/modules/admin/{__init__,models,schemas,service,router}.py
├── app/scripts/seed_admin.py                  # kiểm email như trang đăng nhập
└── tests/test_admin.py                        # 17 test
Sửa: app/modules/auth/{models,schemas}.py, app/modules/courses/{models,schemas,service}.py, app/main.py, app/models_registry.py

frontend/src/
├── lib/admin-queries.ts (+test)
├── components/admin/
│   ├── reason-dialog.tsx (+test)   # hộp thoại nhập lý do
│   ├── user-table.tsx              # bảng người dùng + Duyệt / Từ chối / Khóa / Mở khóa
│   ├── course-table.tsx            # bảng khóa học + Ẩn / Hiện lại
│   ├── overview.tsx                # ô số liệu + biểu đồ 14 ngày
│   ├── action-log.tsx              # nhật ký
│   └── filter-tabs.tsx             # nhóm nút lọc
└── app/(main)/admin/{layout, page, users/page, courses/page, activity/page}.tsx
Sửa: lib/auth/require-auth.tsx (+test), components/app/nav-items.ts (+test), app/(auth)/login/login-form.tsx,
     app/(main)/page.tsx, app/(main)/teach/page.tsx (+test), components/teach/course-editor.tsx, lib/api/schema.d.ts (gen:api)
E2E mới: e2e/admin-data.ts, e2e/admin.spec.ts
Docs: docs/plans/2026-09-30-tier-s-system-plan.md (email admin)
```

### 0.6 Quy ước

- Commit sau mỗi task: backend `feat(api): …`, frontend `feat(web): …`. **Không** thêm trailer `Co-Authored-By` hay `Claude-Session`.
- Backend: lệnh chạy trong `backend/`, kiểm tra cuối task bằng `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`.
- Frontend: lệnh chạy trong `frontend/`, kiểm tra cuối task bằng `npm run lint && npm run typecheck && npm test`.

---

## Task 1: Cột mới và migration

**Files:**
- Modify: `backend/app/modules/auth/models.py`, `backend/app/modules/courses/models.py`, `backend/app/modules/auth/schemas.py`, `backend/app/modules/courses/schemas.py`, `backend/app/modules/courses/service.py`
- Create: `backend/app/modules/admin/__init__.py` (rỗng), `backend/app/modules/admin/models.py`, `backend/alembic/versions/b81e4c7a2d90_admin.py`
- Modify: `backend/app/models_registry.py`

- [x] **Bước 1: `users.review_note`** (`app/modules/auth/models.py`, ngay dưới `locked_at`)

```python
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Lý do quản trị viên ghi khi từ chối giảng viên hoặc khóa tài khoản (hiện cho chính người dùng).
    review_note: Mapped[str | None] = mapped_column(String(500))
```

- [x] **Bước 2: `courses.hidden_at`, `courses.hidden_reason`** (`app/modules/courses/models.py`)

Thêm `from datetime import datetime` và `DateTime` vào import (`from sqlalchemy import DateTime, ForeignKey, Integer, String, Text`), rồi thêm ngay dưới cột `status`:

```python
    # Quản trị viên ẩn khóa vi phạm: status chuyển sang archived và giảng viên không tự xuất bản lại được.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_reason: Mapped[str | None] = mapped_column(String(500))
```

- [x] **Bước 3: Bảng nhật ký** (`app/modules/admin/models.py`)

```python
import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class AdminAction(IdMixin, TimestampMixin, Base):
    """Nhật ký thao tác quản trị (ai, làm gì, với đối tượng nào, lý do). Chỉ thêm, không sửa."""

    __tablename__ = "admin_actions"
    __table_args__ = (Index("ix_admin_actions_created", "created_at"),)

    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40))  # approve_teacher | reject_teacher | lock_user | ...
    target_type: Mapped[str] = mapped_column(String(20))  # user | course
    target_id: Mapped[uuid.UUID] = mapped_column()
    target_label: Mapped[str] = mapped_column(String(255))  # email hoặc tên khóa lúc thao tác
    note: Mapped[str | None] = mapped_column(Text)
```

Thêm vào `app/models_registry.py` (giữ thứ tự chữ cái):

```python
from app.modules.admin import models as admin_models  # noqa: F401
```

- [x] **Bước 4: Migration** (`alembic/versions/b81e4c7a2d90_admin.py`)

```python
"""admin: users.review_note, courses.hidden_*, admin_actions

Revision ID: b81e4c7a2d90
Revises: d2a7f3e81b64
Create Date: 2026-10-07 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b81e4c7a2d90"
down_revision: str | Sequence[str] | None = "d2a7f3e81b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("review_note", sa.String(length=500), nullable=True))
    op.add_column("courses", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("courses", sa.Column("hidden_reason", sa.String(length=500), nullable=True))
    op.create_table(
        "admin_actions",
        sa.Column("admin_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("target_label", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_actions_created", "admin_actions", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_admin_actions_created", table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_column("courses", "hidden_reason")
    op.drop_column("courses", "hidden_at")
    op.drop_column("users", "review_note")
```

Kiểm tra `down_revision` là head hiện tại: chạy `uv run alembic heads`, phải ra `d2a7f3e81b64`. Nếu khác thì sửa `down_revision` theo head thật và ghi vào commit.

- [x] **Bước 5: Thêm trường vào API cũ**

`app/modules/auth/schemas.py`, cuối `UserOut`:

```python
    review_note: str | None = None  # lý do bị từ chối duyệt giảng viên (nếu có)
```

`app/modules/courses/schemas.py`, trong `CourseOut` ngay dưới `created_at`:

```python
    hidden_reason: str | None = None  # quản trị viên đã ẩn khóa (status = archived)
```

`app/modules/courses/service.py`, đầu hàm `publish_course`:

```python
async def publish_course(db: AsyncSession, course: Course) -> Course:
    # Khóa bị quản trị viên ẩn chỉ được hiện lại qua POST /admin/courses/{id}/unhide.
    if course.hidden_at is not None:
        raise AppError("COURSE_HIDDEN", "Khóa học đã bị quản trị viên ẩn, không thể tự xuất bản lại", 409)
    if await count_lessons(db, course.id) == 0:
```

- [x] **Bước 6: Chạy migration và kiểm tra khớp models**

Container `api` không mount code, nên phải build lại. Lệnh khởi động của `api` tự chạy `alembic upgrade head`.

```bash
docker compose up -d --build api worker
docker compose exec api alembic current
docker compose exec api alembic check
```

Expected: `alembic current` ra `b81e4c7a2d90 (head)`; `alembic check` có dòng cuối `No new upgrade operations detected.`

```bash
uv run pytest -q
```

Expected: toàn bộ test cũ vẫn pass (611, chưa có test mới).

- [x] **Bước 7: Commit**

```bash
git add backend && git commit -m "feat(api): admin columns (review_note, hidden_at/reason) and admin_actions table"
```

---

## Task 2: Module admin (API + test)

**Files:**
- Create: `backend/app/modules/admin/schemas.py`, `service.py`, `router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_admin.py`

- [x] **Bước 1: Viết test (sẽ fail)** (`tests/test_admin.py`)

```python
"""Khu quản trị: duyệt giảng viên, khóa tài khoản, ẩn khóa học, số liệu tổng quan, nhật ký."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import User
from tests.helpers import (
    API,
    login,
    make_admin,
    make_published_course,
    make_student,
    make_teacher,
    register_user,
)


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/stats"),
        ("get", "/admin/users"),
        ("get", "/admin/courses"),
        ("get", "/admin/actions"),
        ("post", f"/admin/teachers/{uuid.uuid4()}/approve"),
        ("post", f"/admin/users/{uuid.uuid4()}/unlock"),
        ("post", f"/admin/courses/{uuid.uuid4()}/unhide"),
    ],
)
async def test_admin_routes_are_admin_only(client, method, path):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    for headers in (gv, sv):
        r = await getattr(client, method)(f"{API}{path}", headers=headers)
        assert _code(r) == (403, "FORBIDDEN")
    r = await getattr(client, method)(f"{API}{path}")
    assert r.status_code == 401


async def test_pending_list_is_oldest_first_and_approve_lets_teacher_create(client):
    _, ad = await make_admin(client)
    first = await register_user(client, "gv1@x.com", role="teacher", full_name="Lê Văn Một")
    await register_user(client, "gv2@x.com", role="teacher", full_name="Lê Văn Hai")
    await register_user(client, "sv@x.com")

    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["gv1@x.com", "gv2@x.com"]

    r = await client.post(f"{API}/admin/teachers/{first['id']}/approve", headers=ad)
    assert r.status_code == 200 and r.json()["teacher_status"] == "approved"
    gv = await login(client, "gv1@x.com")
    assert (await client.post(f"{API}/courses", json={"title": "Khóa mới"}, headers=gv)).status_code == 201

    r = await client.post(f"{API}/admin/teachers/{first['id']}/approve", headers=ad)
    assert _code(r) == (409, "ALREADY_APPROVED")


async def test_reject_needs_reason_and_teacher_sees_it(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    r = await client.post(f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "   "}, headers=ad)
    assert r.status_code == 422

    r = await client.post(
        f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": " Thiếu thông tin chuyên môn "}, headers=ad
    )
    assert r.status_code == 200
    assert (r.json()["teacher_status"], r.json()["review_note"]) == ("rejected", "Thiếu thông tin chuyên môn")

    me = await client.get(f"{API}/me", headers=await login(client, "gv@x.com"))
    assert (me.json()["teacher_status"], me.json()["review_note"]) == (
        "rejected",
        "Thiếu thông tin chuyên môn",
    )

    # Từ chối lần nữa: không còn ở trạng thái chờ. Đổi ý thì vẫn duyệt được, lý do bị xóa.
    again = await client.post(f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "x"}, headers=ad)
    assert _code(again) == (409, "NOT_PENDING")
    ok = await client.post(f"{API}/admin/teachers/{gv['id']}/approve", headers=ad)
    assert (ok.json()["teacher_status"], ok.json()["review_note"]) == ("approved", None)


async def test_approve_reject_only_for_teachers(client):
    _, ad = await make_admin(client)
    sv_id, _ = await make_student(client)
    r = await client.post(f"{API}/admin/teachers/{sv_id}/approve", headers=ad)
    assert _code(r) == (404, "NOT_FOUND")
    r = await client.post(f"{API}/admin/teachers/{uuid.uuid4()}/reject", json={"reason": "x"}, headers=ad)
    assert _code(r) == (404, "NOT_FOUND")


async def test_lock_revokes_sessions_and_unlock_restores(client):
    admin_id, ad = await make_admin(client)
    sv_id, sv = await make_student(client)
    login_r = await client.post(f"{API}/auth/login", json={"email": "sv@x.com", "password": "password123"})
    raw = login_r.cookies["refresh_token"]

    r = await client.post(f"{API}/admin/users/{sv_id}/lock", json={"reason": "Spam diễn đàn"}, headers=ad)
    assert r.status_code == 200 and r.json()["locked_at"] is not None
    assert r.json()["review_note"] == "Spam diễn đàn"
    assert _code(await client.get(f"{API}/me", headers=sv)) == (403, "ACCOUNT_LOCKED")
    client.cookies.clear()
    refreshed = await client.post(f"{API}/auth/refresh", headers={"Cookie": f"refresh_token={raw}"})
    assert refreshed.status_code in (401, 403)

    r = await client.post(f"{API}/admin/users/{sv_id}/unlock", headers=ad)
    assert (r.json()["locked_at"], r.json()["review_note"]) == (None, None)
    assert (await client.get(f"{API}/me", headers=await login(client, "sv@x.com"))).status_code == 200

    # không khóa được quản trị viên (kể cả chính mình); khóa không cần lý do
    assert _code(await client.post(f"{API}/admin/users/{admin_id}/lock", json={}, headers=ad)) == (
        409,
        "CANNOT_LOCK_ADMIN",
    )
    r = await client.post(f"{API}/admin/users/{sv_id}/lock", json={}, headers=ad)
    assert r.status_code == 200 and r.json()["review_note"] is None


async def test_users_filter_by_role_status_and_search_without_accents(client):
    _, ad = await make_admin(client)
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await register_user(client, "binh@x.com", full_name="Trần Thị Bình")
    gv_id, gv = await make_teacher(client, "gv@x.com")
    await make_published_course(client, gv)

    r = await client.get(f"{API}/admin/users", params={"role": "student", "q": "nguyen van"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["an@x.com"]
    r = await client.get(f"{API}/admin/users", params={"q": "BINH@"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["binh@x.com"]

    r = await client.get(f"{API}/admin/users", params={"role": "teacher"}, headers=ad)
    (teacher,) = r.json()["items"]
    assert (teacher["id"], teacher["course_count"], teacher["enrollment_count"]) == (gv_id, 1, 0)

    async with SessionLocal() as db:
        await db.execute(update(User).where(User.email == "binh@x.com").values(locked_at=utcnow()))
        await db.commit()
    r = await client.get(f"{API}/admin/users", params={"status": "locked"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["binh@x.com"]
    assert (await client.get(f"{API}/admin/users", params={"status": "bogus"}, headers=ad)).status_code == 422


async def test_hide_course_blocks_students_and_teacher_republish(client):
    _, ad = await make_admin(client)
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    _, sv = await make_student(client)
    assert (await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)).status_code == 201

    r = await client.post(
        f"{API}/admin/courses/{course['id']}/hide", json={"reason": "Vi phạm bản quyền"}, headers=ad
    )
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["hidden_reason"]) == ("archived", "Vi phạm bản quyền")
    assert r.json()["enrollment_count"] == 1

    # biến mất khỏi danh mục, học viên đã đăng ký cũng không vào được bài
    assert (await client.get(f"{API}/courses")).json()["total"] == 0
    assert (await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)).status_code == 404
    # giảng viên vẫn thấy khóa (kèm lý do) nhưng không tự xuất bản lại được
    mine = await client.get(f"{API}/courses/{course['slug']}", headers=gv)
    assert mine.json()["hidden_reason"] == "Vi phạm bản quyền"
    assert _code(await client.post(f"{API}/courses/{course['id']}/publish", headers=gv)) == (
        409,
        "COURSE_HIDDEN",
    )
    again = await client.post(f"{API}/admin/courses/{course['id']}/hide", json={"reason": "x"}, headers=ad)
    assert _code(again) == (409, "COURSE_NOT_PUBLISHED")

    r = await client.post(f"{API}/admin/courses/{course['id']}/unhide", headers=ad)
    assert (r.json()["status"], r.json()["hidden_reason"]) == ("published", None)
    assert (await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)).status_code == 200
    assert _code(await client.post(f"{API}/admin/courses/{course['id']}/unhide", headers=ad)) == (
        409,
        "COURSE_NOT_HIDDEN",
    )


async def test_courses_list_all_teachers_with_filters(client):
    _, ad = await make_admin(client)
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    pub, _, _ = await make_published_course(client, gv1, title="Giải tích một")
    r = await client.post(f"{API}/courses", json={"title": "Đại số tuyến tính"}, headers=gv2)
    draft = r.json()

    r = await client.get(f"{API}/admin/courses", headers=ad)
    assert {c["id"] for c in r.json()["items"]} == {pub["id"], draft["id"]}
    r = await client.get(f"{API}/admin/courses", params={"status": "draft"}, headers=ad)
    assert [c["id"] for c in r.json()["items"]] == [draft["id"]]
    r = await client.get(f"{API}/admin/courses", params={"q": "giai tich"}, headers=ad)
    (item,) = r.json()["items"]
    assert (item["teacher_email"], item["lesson_count"]) == ("gv1@x.com", 1)

    await client.post(f"{API}/admin/courses/{pub['id']}/hide", json={"reason": "x"}, headers=ad)
    r = await client.get(f"{API}/admin/courses", params={"status": "hidden"}, headers=ad)
    assert [c["id"] for c in r.json()["items"]] == [pub["id"]]
    r = await client.get(f"{API}/admin/courses", params={"status": "published"}, headers=ad)
    assert r.json()["total"] == 0


async def test_stats_counts_and_14_day_signups(client):
    _, ad = await make_admin(client)
    _, gv = await make_teacher(client)
    await register_user(client, "gv-cho@x.com", role="teacher")
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses", json={"title": "Bản nháp"}, headers=gv)
    _, sv = await make_student(client)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    async with SessionLocal() as db:  # một người đăng ký từ 20 ngày trước: không nằm trong 14 ngày
        await db.execute(
            update(User).where(User.email == "gv-cho@x.com").values(created_at=utcnow() - timedelta(days=20))
        )
        await db.commit()

    s = (await client.get(f"{API}/admin/stats", headers=ad)).json()
    assert (s["students"], s["teachers"], s["pending_teachers"]) == (1, 2, 1)
    assert (s["courses_published"], s["courses_draft"], s["courses_hidden"], s["enrollments"]) == (1, 1, 0, 1)
    assert len(s["signups_14d"]) == 14
    assert s["signups_14d"][0]["day"] < s["signups_14d"][-1]["day"]
    assert sum(d["count"] for d in s["signups_14d"]) == 3  # admin + gv + sv (gv-cho ngoài khoảng)


async def test_actions_log_records_who_did_what(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    await client.post(f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "Chưa đủ hồ sơ"}, headers=ad)
    await client.post(f"{API}/admin/teachers/{gv['id']}/approve", headers=ad)

    r = await client.get(f"{API}/admin/actions", headers=ad)
    items = r.json()["items"]
    assert {(a["action"], a["note"]) for a in items} == {
        ("reject_teacher", "Chưa đủ hồ sơ"),
        ("approve_teacher", None),
    }
    assert all(a["admin_name"] == "Quản trị viên" and a["target_label"] == "gv@x.com" for a in items)


def test_seed_admin_rejects_emails_login_would_refuse():
    from app.scripts.seed_admin import valid_email

    assert valid_email("Admin@Example.com") == "admin@example.com"
    with pytest.raises(SystemExit):
        valid_email("admin@lms.local")
```

Chạy `uv run pytest tests/test_admin.py -q`. Expected: fail ở bước import hoặc 404 (chưa có route).

> Test cuối (`test_seed_admin_rejects_emails_login_would_refuse`) sẽ pass sau Task 3. Ở task này, chạy kèm `--deselect tests/test_admin.py::test_seed_admin_rejects_emails_login_would_refuse`.

- [x] **Bước 2: Schemas** (`app/modules/admin/schemas.py`)

```python
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.pagination import Page
from app.modules.auth.models import Role, TeacherStatus
from app.modules.courses.models import CourseStatus


def _strip(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _required(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Cần nhập lý do")
    return v


class ReasonIn(BaseModel):
    """Lý do bắt buộc (từ chối giảng viên, ẩn khóa học): người bị ảnh hưởng sẽ đọc được."""

    reason: str = Field(min_length=1, max_length=500)

    strip_reason = field_validator("reason")(_required)


class OptionalReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    strip_reason = field_validator("reason")(_strip)


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    teacher_status: TeacherStatus | None
    locked_at: datetime | None
    review_note: str | None
    created_at: datetime
    course_count: int  # giảng viên: số khóa đang sở hữu
    enrollment_count: int  # học viên: số khóa đã đăng ký


class AdminUserPage(Page[AdminUserOut]):
    pass


class AdminCourseOut(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    status: CourseStatus
    teacher_id: uuid.UUID
    teacher_name: str
    teacher_email: str
    created_at: datetime
    lesson_count: int
    enrollment_count: int
    hidden_at: datetime | None
    hidden_reason: str | None


class AdminCoursePage(Page[AdminCourseOut]):
    pass


class DayCount(BaseModel):
    day: date
    count: int


class AdminStats(BaseModel):
    students: int
    teachers: int
    pending_teachers: int
    locked_users: int
    courses_published: int
    courses_draft: int
    courses_hidden: int
    enrollments: int
    tutor_questions_7d: int
    quiz_submissions_7d: int
    failed_jobs_7d: int
    signups_14d: list[DayCount]  # đủ 14 ngày (giờ Việt Nam), ngày không có ai đăng ký = 0


class AdminActionOut(BaseModel):
    id: uuid.UUID
    admin_name: str | None  # None nếu tài khoản admin đã bị xóa
    action: str
    target_type: Literal["user", "course"]
    target_id: uuid.UUID
    target_label: str
    note: str | None
    created_at: datetime


class AdminActionPage(Page[AdminActionOut]):
    pass
```

- [x] **Bước 3: Service** (`app/modules/admin/service.py`)

```python
import uuid
from datetime import date, timedelta

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.core.time import utcnow
from app.modules.admin.models import AdminAction
from app.modules.admin.schemas import (
    AdminActionOut,
    AdminActionPage,
    AdminCourseOut,
    AdminCoursePage,
    AdminStats,
    AdminUserOut,
    AdminUserPage,
    DayCount,
)
from app.modules.auth.models import RefreshToken, Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.enrollment.models import Enrollment
from app.modules.jobs.models import Job, JobStatus
from app.modules.quiz.models import AttemptStatus, QuizAttempt
from app.modules.tutor.models import ChatMessage, ChatRole

VN_TZ = "Asia/Ho_Chi_Minh"


def _log(
    db: AsyncSession,
    admin: User,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    label: str,
    note: str | None,
) -> None:
    db.add(
        AdminAction(
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=label,
            note=note,
        )
    )


def _like(q: str) -> str:
    return f"%{q.strip().lower()}%"


# ---------- người dùng ----------

_course_count = (
    select(func.count())
    .select_from(Course)
    .where(Course.teacher_id == User.id)
    .correlate(User)
    .scalar_subquery()
)
_enroll_count = (
    select(func.count())
    .select_from(Enrollment)
    .where(Enrollment.user_id == User.id)
    .correlate(User)
    .scalar_subquery()
)


def _user_out(user: User, course_count: int, enrollment_count: int) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        teacher_status=user.teacher_status,
        locked_at=user.locked_at,
        review_note=user.review_note,
        created_at=user.created_at,
        course_count=course_count,
        enrollment_count=enrollment_count,
    )


async def list_users(
    db: AsyncSession, role: Role | None, status: str | None, q: str | None, params: PageParams
) -> AdminUserPage:
    stmt: Select = select(User, _course_count, _enroll_count)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if status in ("pending", "approved", "rejected"):
        stmt = stmt.where(User.role == Role.teacher, User.teacher_status == TeacherStatus(status))
    elif status == "locked":
        stmt = stmt.where(User.locked_at.is_not(None))
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
                User.email.like(pattern),
            )
        )
    # Chờ duyệt: ai đăng ký trước được xử lý trước. Còn lại: mới nhất lên đầu.
    order = User.created_at.asc() if status == "pending" else User.created_at.desc()
    total, paged = await paginate(db, stmt.order_by(order, User.id), params)
    rows = (await db.execute(paged)).all()
    return AdminUserPage(
        items=[_user_out(u, cc, ec) for u, cc, ec in rows], total=total, page=params.page, size=params.size
    )


async def _get_user_row(db: AsyncSession, user_id: uuid.UUID) -> AdminUserOut:
    row = (await db.execute(select(User, _course_count, _enroll_count).where(User.id == user_id))).one()
    return _user_out(*row)


async def _get_teacher(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.role != Role.teacher:
        raise not_found("Giảng viên")
    return user


async def approve_teacher(db: AsyncSession, admin: User, user_id: uuid.UUID) -> AdminUserOut:
    """Duyệt giảng viên đang chờ hoặc đã bị từ chối trước đó (đổi ý)."""
    user = await _get_teacher(db, user_id)
    if user.teacher_status == TeacherStatus.approved:
        raise AppError("ALREADY_APPROVED", "Giảng viên này đã được duyệt", 409)
    user.teacher_status = TeacherStatus.approved
    user.review_note = None
    _log(db, admin, "approve_teacher", "user", user.id, user.email, None)
    await db.commit()
    return await _get_user_row(db, user.id)


async def reject_teacher(db: AsyncSession, admin: User, user_id: uuid.UUID, reason: str) -> AdminUserOut:
    """Chỉ từ chối được yêu cầu đang chờ. Giảng viên đã duyệt mà vi phạm thì khóa tài khoản."""
    user = await _get_teacher(db, user_id)
    if user.teacher_status != TeacherStatus.pending:
        raise AppError("NOT_PENDING", "Chỉ từ chối được giảng viên đang chờ duyệt", 409)
    user.teacher_status = TeacherStatus.rejected
    user.review_note = reason
    _log(db, admin, "reject_teacher", "user", user.id, user.email, reason)
    await db.commit()
    return await _get_user_row(db, user.id)


async def lock_user(db: AsyncSession, admin: User, user_id: uuid.UUID, reason: str | None) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Người dùng")
    if user.role == Role.admin:
        raise AppError("CANNOT_LOCK_ADMIN", "Không thể khóa tài khoản quản trị viên", 409)
    if user.locked_at is None:
        user.locked_at = utcnow()
        user.review_note = reason
        # Thu hồi mọi phiên: refresh bị chặn ngay; access token còn hạn cũng bị deps chặn vì locked_at.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        _log(db, admin, "lock_user", "user", user.id, user.email, reason)
        await db.commit()
    return await _get_user_row(db, user.id)


async def unlock_user(db: AsyncSession, admin: User, user_id: uuid.UUID) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Người dùng")
    if user.locked_at is not None:
        user.locked_at = None
        # Lý do khóa không còn đúng nữa; lý do từ chối giảng viên (nếu có) thì giữ.
        if user.teacher_status != TeacherStatus.rejected:
            user.review_note = None
        _log(db, admin, "unlock_user", "user", user.id, user.email, None)
        await db.commit()
    return await _get_user_row(db, user.id)


# ---------- khóa học ----------

_lesson_count = (
    select(func.count())
    .select_from(Lesson)
    .join(Section, Section.id == Lesson.section_id)
    .where(Section.course_id == Course.id)
    .correlate(Course)
    .scalar_subquery()
)
_course_enroll_count = (
    select(func.count())
    .select_from(Enrollment)
    .where(Enrollment.course_id == Course.id)
    .correlate(Course)
    .scalar_subquery()
)


def _course_stmt() -> Select:
    return select(Course, User.full_name, User.email, _lesson_count, _course_enroll_count).join(
        User, User.id == Course.teacher_id
    )


def _course_out(row) -> AdminCourseOut:
    c, name, email, lessons, enrolls = row
    return AdminCourseOut(
        id=c.id,
        title=c.title,
        slug=c.slug,
        status=c.status,
        teacher_id=c.teacher_id,
        teacher_name=name,
        teacher_email=email,
        created_at=c.created_at,
        lesson_count=lessons,
        enrollment_count=enrolls,
        hidden_at=c.hidden_at,
        hidden_reason=c.hidden_reason,
    )


async def list_courses(
    db: AsyncSession, status: str | None, q: str | None, params: PageParams
) -> AdminCoursePage:
    """status: published | draft | hidden (đã bị admin ẩn). Không truyền = tất cả."""
    stmt = _course_stmt()
    if status == "hidden":
        stmt = stmt.where(Course.hidden_at.is_not(None))
    elif status in ("published", "draft"):
        stmt = stmt.where(Course.status == CourseStatus(status), Course.hidden_at.is_(None))
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                func.immutable_unaccent(func.lower(Course.title)).like(func.immutable_unaccent(pattern)),
                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
            )
        )
    total, paged = await paginate(db, stmt.order_by(Course.created_at.desc(), Course.id), params)
    rows = (await db.execute(paged)).all()
    return AdminCoursePage(
        items=[_course_out(r) for r in rows], total=total, page=params.page, size=params.size
    )


async def _course_row(db: AsyncSession, course_id: uuid.UUID) -> AdminCourseOut:
    return _course_out((await db.execute(_course_stmt().where(Course.id == course_id))).one())


async def hide_course(db: AsyncSession, admin: User, course_id: uuid.UUID, reason: str) -> AdminCourseOut:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    if course.status != CourseStatus.published:
        raise AppError("COURSE_NOT_PUBLISHED", "Chỉ ẩn được khóa học đang xuất bản", 409)
    course.status = CourseStatus.archived
    course.hidden_at = utcnow()
    course.hidden_reason = reason
    _log(db, admin, "hide_course", "course", course.id, course.title, reason)
    await db.commit()
    return await _course_row(db, course.id)


async def unhide_course(db: AsyncSession, admin: User, course_id: uuid.UUID) -> AdminCourseOut:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    if course.hidden_at is None:
        raise AppError("COURSE_NOT_HIDDEN", "Khóa học này không bị ẩn", 409)
    course.status = CourseStatus.published
    course.hidden_at = None
    course.hidden_reason = None
    _log(db, admin, "unhide_course", "course", course.id, course.title, None)
    await db.commit()
    return await _course_row(db, course.id)


# ---------- tổng quan & nhật ký ----------


async def stats(db: AsyncSession) -> AdminStats:
    now = utcnow()
    week_ago = now - timedelta(days=7)

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    by_role = dict((await db.execute(select(User.role, func.count()).group_by(User.role))).all())
    by_status = dict(
        (
            await db.execute(
                select(Course.status, func.count()).where(Course.hidden_at.is_(None)).group_by(Course.status)
            )
        ).all()
    )
    vn_day = func.date(func.timezone(VN_TZ, User.created_at))
    today = await db.scalar(select(func.date(func.timezone(VN_TZ, func.now()))))
    first = today - timedelta(days=13)
    per_day = dict(
        (await db.execute(select(vn_day, func.count()).where(vn_day >= first).group_by(vn_day))).all()
    )
    days: list[date] = [first + timedelta(days=i) for i in range(14)]

    return AdminStats(
        students=by_role.get(Role.student, 0),
        teachers=by_role.get(Role.teacher, 0),
        pending_teachers=await count(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.teacher, User.teacher_status == TeacherStatus.pending)
        ),
        locked_users=await count(select(func.count()).select_from(User).where(User.locked_at.is_not(None))),
        courses_published=by_status.get(CourseStatus.published, 0),
        courses_draft=by_status.get(CourseStatus.draft, 0),
        courses_hidden=await count(
            select(func.count()).select_from(Course).where(Course.hidden_at.is_not(None))
        ),
        enrollments=await count(select(func.count()).select_from(Enrollment)),
        tutor_questions_7d=await count(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.role == ChatRole.user, ChatMessage.created_at >= week_ago)
        ),
        quiz_submissions_7d=await count(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.status != AttemptStatus.in_progress, QuizAttempt.submitted_at >= week_ago)
        ),
        failed_jobs_7d=await count(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.failed, Job.created_at >= week_ago)
        ),
        signups_14d=[DayCount(day=d, count=per_day.get(d, 0)) for d in days],
    )


async def list_actions(db: AsyncSession, params: PageParams) -> AdminActionPage:
    stmt = select(AdminAction, User.full_name).outerjoin(User, User.id == AdminAction.admin_id)
    total, paged = await paginate(db, stmt.order_by(AdminAction.created_at.desc(), AdminAction.id), params)
    rows = (await db.execute(paged)).all()
    items = [
        AdminActionOut(
            id=a.id,
            admin_name=name,
            action=a.action,
            target_type=a.target_type,
            target_id=a.target_id,
            target_label=a.target_label,
            note=a.note,
            created_at=a.created_at,
        )
        for a, name in rows
    ]
    return AdminActionPage(items=items, total=total, page=params.page, size=params.size)
```

Ghi chú:

- `func.immutable_unaccent` là hàm SQL đã có từ migration tìm kiếm danh mục: tìm "nguyen van" ra "Nguyễn Văn".
- Số liệu 14 ngày dùng `timezone('Asia/Ho_Chi_Minh', created_at)`, để người đăng ký lúc 6h sáng giờ Việt Nam không bị tính sang ngày hôm trước theo giờ UTC.

- [x] **Bước 4: Router** (`app/modules/admin/router.py`)

```python
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_role
from app.core.pagination import PageParams, page_params
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminActionPage,
    AdminCourseOut,
    AdminCoursePage,
    AdminStats,
    AdminUserOut,
    AdminUserPage,
    OptionalReasonIn,
    ReasonIn,
)
from app.modules.auth.models import Role, User

# Mọi route ở đây chỉ dành cho quản trị viên (người khác nhận 403 FORBIDDEN).
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin_only = require_role(Role.admin)


@router.get("/stats", response_model=AdminStats)
async def get_stats(_: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    return await service.stats(db)


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    role: Literal["student", "teacher", "admin"] | None = None,
    status: Literal["pending", "approved", "rejected", "locked"] | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_users(db, Role(role) if role else None, status, q, params)


@router.post("/teachers/{user_id}/approve", response_model=AdminUserOut)
async def approve_teacher(
    user_id: uuid.UUID, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.approve_teacher(db, admin, user_id)


@router.post("/teachers/{user_id}/reject", response_model=AdminUserOut)
async def reject_teacher(
    user_id: uuid.UUID, data: ReasonIn, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.reject_teacher(db, admin, user_id, data.reason)


@router.post("/users/{user_id}/lock", response_model=AdminUserOut)
async def lock_user(
    user_id: uuid.UUID,
    data: OptionalReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.lock_user(db, admin, user_id, data.reason)


@router.post("/users/{user_id}/unlock", response_model=AdminUserOut)
async def unlock_user(
    user_id: uuid.UUID, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.unlock_user(db, admin, user_id)


@router.get("/courses", response_model=AdminCoursePage)
async def list_courses(
    status: Literal["published", "draft", "hidden"] | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_courses(db, status, q, params)


@router.post("/courses/{course_id}/hide", response_model=AdminCourseOut)
async def hide_course(
    course_id: uuid.UUID,
    data: ReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.hide_course(db, admin, course_id, data.reason)


@router.post("/courses/{course_id}/unhide", response_model=AdminCourseOut)
async def unhide_course(
    course_id: uuid.UUID, admin: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await service.unhide_course(db, admin, course_id)


@router.get("/actions", response_model=AdminActionPage)
async def list_actions(
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_actions(db, params)
```

Đăng ký trong `app/main.py`:

```python
from app.modules.admin.router import router as admin_router
...
    app.include_router(analytics_router)
    app.include_router(admin_router)
```

- [x] **Bước 5: Chạy test**

```bash
uv run pytest tests/test_admin.py -q --deselect tests/test_admin.py::test_seed_admin_rejects_emails_login_would_refuse
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Expected: 16 passed; toàn bộ 627 passed (thiếu 1 test seed, thêm ở Task 3); ruff sạch.

- [x] **Bước 6: Commit**

```bash
git add backend && git commit -m "feat(api): admin endpoints for teacher review, account lock, course moderation, stats and audit log"
```

---

## Task 3: `seed_admin` kiểm tra email, sửa plan tầng S

**Files:**
- Modify: `backend/app/scripts/seed_admin.py`, `docs/plans/2026-09-30-tier-s-system-plan.md`

- [x] **Bước 1: `app/scripts/seed_admin.py`** (thay toàn bộ)

```python
import argparse
import asyncio
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.db import SessionLocal
from app.modules.auth.service import create_admin


def valid_email(email: str) -> str:
    """Cùng kiểu kiểm tra với trang đăng nhập (EmailStr): email như admin@lms.local sẽ không đăng nhập được."""
    try:
        return TypeAdapter(EmailStr).validate_python(email).lower()
    except ValidationError:
        sys.exit(
            f"Email không hợp lệ để đăng nhập: {email} (dùng đuôi tên miền thật, ví dụ admin@example.com)"
        )


async def main(email: str, password: str) -> None:
    async with SessionLocal() as db:
        user = await create_admin(db, email, password)
    print(f"Admin sẵn sàng: {user.email}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    a = p.parse_args()
    if len(a.password) < 8:
        sys.exit("Mật khẩu cần ít nhất 8 ký tự")
    asyncio.run(main(valid_email(a.email), a.password))
```

- [x] **Bước 2: Chạy test**

```bash
uv run pytest tests/test_admin.py -q
uv run pytest -q
```

Expected: 17 passed; toàn bộ **628 passed**.

- [x] **Bước 3: Thử bằng tay**

```bash
docker compose exec api python -m app.scripts.seed_admin --email admin@lms.local --password Admin12345
```

Expected: báo `Email không hợp lệ để đăng nhập: admin@lms.local …`, mã thoát khác 0.

- [x] **Bước 4: Sửa plan tầng S**

Trong `docs/plans/2026-09-30-tier-s-system-plan.md`, tìm dòng gọi `seed_admin --email admin@lms.local` và đổi email thành `admin@<tên miền của bạn>`. Thêm ngay dưới dòng đó:

```markdown
> Email phải có đuôi tên miền thật: `.local`, `.test`, `.localhost` không đăng nhập được (trang đăng nhập dùng `EmailStr`). Script sẽ từ chối các email này.
```

- [x] **Bước 5: Commit**

```bash
git add backend docs && git commit -m "fix(api): seed_admin rejects emails the login form would refuse"
```

---

## Task 4: Truy vấn admin, phân quyền và menu

**Files:**
- Modify: `frontend/src/lib/api/schema.d.ts` (sinh lại), `frontend/src/lib/auth/require-auth.tsx` (+test), `frontend/src/components/app/nav-items.ts` (+test), `frontend/src/app/(auth)/login/login-form.tsx`
- Create: `frontend/src/lib/admin-queries.ts`
- Test: `frontend/src/lib/admin-queries.test.ts`

- [x] **Bước 1: Sinh lại kiểu API**

```bash
npm run gen:api
git diff --stat src/lib/api/schema.d.ts
```

Expected: chỉ **thêm** dòng (các route `/api/v1/admin/*`, schema `Admin*`, `DayCount`, `ReasonIn`, `OptionalReasonIn`, trường `review_note` và `hidden_reason`), không có dòng nào bị xóa.

- [x] **Bước 2: Viết test (sẽ fail)** (`src/lib/admin-queries.test.ts`)

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { actionLabel, useAdminActionsMutations, useAdminUsers } from "./admin-queries";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
  const invalidatedAdmin = () => spy.mock.calls.some(([f]) => JSON.stringify(f?.queryKey) === JSON.stringify(["admin"]));
  return { wrapper, invalidatedAdmin };
}

describe("admin-queries", () => {
  it("danh sách người dùng gửi đúng bộ lọc, bỏ q rỗng", async () => {
    let query = "";
    server.use(
      http.get(url("/admin/users"), ({ request }) => {
        query = new URL(request.url).search;
        return HttpResponse.json({ items: [], total: 0, page: 1, size: 20 });
      }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useAdminUsers({ role: "teacher", status: "pending", q: "", page: 2 }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const params = new URLSearchParams(query);
    expect(Object.fromEntries(params)).toEqual({ role: "teacher", status: "pending", page: "2", size: "20" });
  });

  it("thao tác xong thì làm mới cả khu quản trị; khóa không lý do gửi reason = null", async () => {
    let body: unknown;
    server.use(
      http.post(url("/admin/users/u1/lock"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: "u1" });
      }),
    );
    const { wrapper, invalidatedAdmin } = setup();
    const { result } = renderHook(() => useAdminActionsMutations(), { wrapper });
    await result.current.lock.mutateAsync({ id: "u1", reason: "" });
    expect(body).toEqual({ reason: null });
    await waitFor(() => expect(invalidatedAdmin()).toBe(true));
  });

  it("nhãn thao tác tiếng Việt, mã lạ thì giữ nguyên", () => {
    expect(actionLabel("hide_course")).toBe("Ẩn khóa học");
    expect(actionLabel("something_new")).toBe("something_new");
  });
});
```

- [x] **Bước 3: `src/lib/admin-queries.ts`**

```ts
"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type AdminStats = components["schemas"]["AdminStats"];
export type AdminUser = components["schemas"]["AdminUserOut"];
export type AdminCourse = components["schemas"]["AdminCourseOut"];
export type AdminAction = components["schemas"]["AdminActionOut"];

export type UserFilter = { role?: "student" | "teacher" | "admin"; status?: "pending" | "approved" | "rejected" | "locked"; q?: string; page: number };
export type CourseFilter = { status?: "published" | "draft" | "hidden"; q?: string; page: number };

/** Mọi khóa của khu quản trị bắt đầu bằng "admin": một thao tác xong thì làm mới cả khu (số liệu, danh sách, nhật ký). */
const ADMIN = ["admin"] as const;
export const adminKeys = {
  all: ADMIN,
  stats: [...ADMIN, "stats"] as const,
  users: (f: UserFilter) => [...ADMIN, "users", f] as const,
  courses: (f: CourseFilter) => [...ADMIN, "courses", f] as const,
  actions: (page: number) => [...ADMIN, "actions", page] as const,
};

export const PAGE_SIZE = 20;

export function useAdminStats() {
  return useQuery({ queryKey: adminKeys.stats, queryFn: () => unwrap(api.GET("/api/v1/admin/stats")) });
}

export function useAdminUsers(f: UserFilter) {
  return useQuery({
    queryKey: adminKeys.users(f),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/users", {
          params: { query: { role: f.role, status: f.status, q: f.q || undefined, page: f.page, size: PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useAdminCourses(f: CourseFilter) {
  return useQuery({
    queryKey: adminKeys.courses(f),
    queryFn: () =>
      unwrap(api.GET("/api/v1/admin/courses", { params: { query: { status: f.status, q: f.q || undefined, page: f.page, size: PAGE_SIZE } } })),
    placeholderData: keepPreviousData,
  });
}

export function useAdminActions(page: number, size = PAGE_SIZE) {
  return useQuery({
    queryKey: [...adminKeys.actions(page), size],
    queryFn: () => unwrap(api.GET("/api/v1/admin/actions", { params: { query: { page, size } } })),
    placeholderData: keepPreviousData,
  });
}

function useAdminMutation<A>(fn: (a: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ADMIN }) });
}

const uid = (id: string) => ({ params: { path: { user_id: id } } });
const cid = (id: string) => ({ params: { path: { course_id: id } } });

export function useAdminActionsMutations() {
  return {
    approve: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/teachers/{user_id}/approve", uid(id)))),
    reject: useAdminMutation(({ id, reason }: { id: string; reason: string }) =>
      unwrap(api.POST("/api/v1/admin/teachers/{user_id}/reject", { ...uid(id), body: { reason } })),
    ),
    lock: useAdminMutation(({ id, reason }: { id: string; reason?: string }) =>
      unwrap(api.POST("/api/v1/admin/users/{user_id}/lock", { ...uid(id), body: { reason: reason || null } })),
    ),
    unlock: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/users/{user_id}/unlock", uid(id)))),
    hide: useAdminMutation(({ id, reason }: { id: string; reason: string }) =>
      unwrap(api.POST("/api/v1/admin/courses/{course_id}/hide", { ...cid(id), body: { reason } })),
    ),
    unhide: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/courses/{course_id}/unhide", cid(id)))),
  };
}

const ACTION_LABEL: Record<string, string> = {
  approve_teacher: "Duyệt giảng viên",
  reject_teacher: "Từ chối giảng viên",
  lock_user: "Khóa tài khoản",
  unlock_user: "Mở khóa tài khoản",
  hide_course: "Ẩn khóa học",
  unhide_course: "Hiện lại khóa học",
};
export const actionLabel = (a: string) => ACTION_LABEL[a] ?? a;

const dateFmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Ho_Chi_Minh" });
const timeFmt = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
export const fmtDate = (iso: string) => dateFmt.format(new Date(iso));
export const fmtDateTime = (iso: string) => timeFmt.format(new Date(iso));
```

- [x] **Bước 4: `RequireAuth admin`** (`src/lib/auth/require-auth.tsx`)

Đổi chữ ký và chú thích:

```tsx
/** Chặn trang cần đăng nhập. Chưa đăng nhập → /login?next=<trang hiện tại>. `admin`: chỉ quản trị viên. */
export function RequireAuth({ staff = false, admin = false, children }: { staff?: boolean; admin?: boolean; children: React.ReactNode }) {
```

Thêm ngay **trước** khối `if (staff && !isStaff(user)) {`:

```tsx
  if (admin && user?.role !== "admin") {
    return (
      <div className="mx-auto max-w-md p-6 text-center">
        <h1 className="text-xl font-semibold">Không có quyền truy cập</h1>
        <p className="mt-2 text-muted-foreground">Trang này chỉ dành cho quản trị viên.</p>
      </div>
    );
  }
```

Thêm test cuối `describe` trong `src/lib/auth/require-auth.test.tsx`:

```tsx
  it("trang quản trị: giảng viên đã duyệt cũng bị chặn, admin thì vào được", () => {
    auth.status = "authenticated";
    auth.user = { role: "teacher", teacher_status: "approved" };
    const { unmount } = render(<RequireAuth admin>khu quản trị</RequireAuth>);
    expect(screen.getByText(/chỉ dành cho quản trị viên/)).toBeInTheDocument();
    expect(screen.queryByText("khu quản trị")).not.toBeInTheDocument();
    unmount();
    auth.user = { role: "admin", teacher_status: null };
    render(<RequireAuth admin>khu quản trị</RequireAuth>);
    expect(screen.getByText("khu quản trị")).toBeInTheDocument();
  });
```

- [x] **Bước 5: Menu admin** (`src/components/app/nav-items.ts`, thay toàn bộ)

```ts
import { BookMarked, Compass, GraduationCap, Home, LayoutDashboard, Library, type LucideIcon, Users } from "lucide-react";
import type { User } from "@/lib/auth/auth-context";

export type NavItem = { href: string; label: string; icon: LucideIcon };

/** Mục điều hướng theo vai trò (design-system §7.1). Điện thoại hiển thị tối đa 4 mục. */
export function navItems(user: User | null): NavItem[] {
  const base: NavItem[] = [
    { href: "/", label: "Trang chủ", icon: Home },
    { href: "/explore", label: "Khám phá", icon: Compass },
  ];
  if (!user) return base;
  if (user.role === "admin")
    return [
      { href: "/admin", label: "Tổng quan", icon: LayoutDashboard },
      { href: "/admin/users", label: "Người dùng", icon: Users },
      { href: "/admin/courses", label: "Khóa học", icon: Library },
    ];
  if (user.role === "student") return [...base, { href: "/my", label: "Khóa của tôi", icon: BookMarked }];
  // Chỉ giảng viên đã duyệt: GET /teacher/courses dùng require_teacher_approved (admin nhận 403).
  if (user.role === "teacher" && user.teacher_status === "approved")
    return [{ href: "/teach", label: "Khóa đang dạy", icon: GraduationCap }, ...base.slice(1)];
  return base.slice(1); // giảng viên chờ duyệt / bị từ chối
}

/** Mục chỉ sáng khi khớp đúng đường dẫn (không khớp tiền tố): "/" và "/admin" là cha của các mục khác. */
const EXACT = new Set(["/", "/admin"]);

export function isActive(pathname: string, href: string) {
  return EXACT.has(href) ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}
```

Trong `src/components/app/nav-items.test.ts`, thay test `"quản trị viên không có Khóa đang dạy …"` bằng:

```ts
  it("quản trị viên có khu quản trị, không có Khóa đang dạy (API /teacher/courses chỉ cho giảng viên)", () => {
    expect(navItems(user("admin")).map((i) => i.href)).toEqual(["/admin", "/admin/users", "/admin/courses"]);
  });
  it("/admin chỉ sáng ở chính trang tổng quan, không sáng khi ở /admin/users", () => {
    expect(isActive("/admin", "/admin")).toBe(true);
    expect(isActive("/admin/users", "/admin")).toBe(false);
    expect(isActive("/admin/users", "/admin/users")).toBe(true);
  });
```

- [x] **Bước 6: Đăng nhập xong admin vào `/admin`** (`src/app/(auth)/login/login-form.tsx`)

```tsx
      const fallback = user.role === "student" ? "/" : user.role === "admin" ? "/admin" : "/teach";
```

- [x] **Bước 7: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend && git commit -m "feat(web): admin queries, admin-only guard and admin navigation"
```

Expected: test mới pass, không test cũ nào fail.

---

## Task 5: Component khu quản trị

**Files:**
- Create: `frontend/src/components/admin/{reason-dialog, user-table, course-table, overview, action-log, filter-tabs}.tsx`
- Test: `frontend/src/components/admin/reason-dialog.test.tsx`

- [x] **Bước 1: Viết test (sẽ fail)** (`src/components/admin/reason-dialog.test.tsx`)

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReasonDialog } from "./reason-dialog";

function setup(required = true, onSubmit = vi.fn(async () => {})) {
  const onOpenChange = vi.fn();
  render(
    <ReasonDialog open onOpenChange={onOpenChange} title="Từ chối An?" description="Mô tả" confirmLabel="Từ chối" required={required} onSubmit={onSubmit} />,
  );
  return { onSubmit, onOpenChange, user: userEvent.setup() };
}

describe("ReasonDialog", () => {
  it("bắt buộc lý do: để trống thì báo lỗi, không gửi", async () => {
    const { onSubmit, user } = setup();
    await user.type(screen.getByLabelText("Lý do"), "   ");
    await user.click(screen.getByRole("button", { name: "Từ chối" }));
    expect(await screen.findByText("Cần nhập lý do")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("gửi lý do đã cắt khoảng trắng rồi đóng", async () => {
    const { onSubmit, onOpenChange, user } = setup();
    await user.type(screen.getByLabelText("Lý do"), "  Thiếu hồ sơ  ");
    await user.click(screen.getByRole("button", { name: "Từ chối" }));
    expect(onSubmit).toHaveBeenCalledWith("Thiếu hồ sơ");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("lý do không bắt buộc: gửi được khi để trống; lỗi thì giữ hộp thoại mở", async () => {
    const failing = vi.fn(async () => {
      throw new Error("x");
    });
    const { onOpenChange, user } = setup(false, failing);
    await user.click(screen.getByRole("button", { name: "Từ chối" }));
    expect(failing).toHaveBeenCalledWith("");
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
```

- [x] **Bước 2: `reason-dialog.tsx`**

```tsx
"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/input";

/**
 * Hộp thoại nhập lý do cho thao tác quản trị. Lý do sẽ hiện cho chính người bị ảnh hưởng
 * (giảng viên bị từ chối, chủ khóa bị ẩn), nên viết rõ ràng, lịch sự.
 * `onSubmit` ném lỗi thì hộp thoại giữ nguyên để sửa (nơi gọi tự báo toast).
 */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  required = true,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  required?: boolean;
  onSubmit: (reason: string) => Promise<unknown>;
}) {
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string>();
  const [pending, setPending] = React.useState(false);

  function change(o: boolean) {
    if (!o) {
      setReason("");
      setError(undefined);
    }
    onOpenChange(o);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (required && !reason.trim()) return setError("Cần nhập lý do");
    setPending(true);
    try {
      await onSubmit(reason.trim());
      change(false);
    } catch {
      // giữ hộp thoại mở
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent title={title} description={description}>
        <form onSubmit={submit} className="space-y-4" noValidate>
          <Field id="admin-reason" label={required ? "Lý do" : "Lý do (không bắt buộc)"} error={error} hint="Người dùng sẽ thấy lý do này.">
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={500} autoFocus />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => change(false)}>
              Hủy
            </Button>
            <Button type="submit" variant="destructive" loading={pending} loadingText="Đang xử lý…">
              {confirmLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [x] **Bước 3: `filter-tabs.tsx`**

```tsx
"use client";

import { cn } from "@/lib/utils";

/** Nhóm nút lọc (một nút được chọn). Dùng aria-pressed để trình đọc màn hình biết nút nào đang bật. */
export function FilterTabs<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-9 rounded-full border px-4 text-sm transition-colors",
            value === o.value ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
```

- [x] **Bước 4: `user-table.tsx`**

```tsx
"use client";

import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type AdminUser, fmtDate, useAdminActionsMutations } from "@/lib/admin-queries";
import { ReasonDialog } from "./reason-dialog";

const ROLE = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

export function UserStatus({ user }: { user: AdminUser }) {
  if (user.locked_at) return <Badge tone="destructive">Đã khóa</Badge>;
  if (user.role !== "teacher") return <Badge>Hoạt động</Badge>;
  if (user.teacher_status === "pending") return <Badge tone="accent">Chờ duyệt</Badge>;
  if (user.teacher_status === "rejected") return <Badge tone="destructive">Bị từ chối</Badge>;
  return <Badge tone="success">Đã duyệt</Badge>;
}


/** Bảng người dùng + thao tác theo trạng thái. Điện thoại cuộn ngang trong khung (bàn phím cũng cuộn được). */
export function UserTable({ users, caption }: { users: AdminUser[]; caption: string }) {
  const mut = useAdminActionsMutations();
  // Giữ người dùng đang thao tác cả khi hộp thoại đang đóng (tiêu đề không bị trống lúc chạy hiệu ứng đóng).
  const [target, setTarget] = React.useState<AdminUser | null>(null);
  const [dialog, setDialog] = React.useState<"reject" | "lock" | null>(null);
  const open = (kind: "reject" | "lock", u: AdminUser) => {
    setTarget(u);
    setDialog(kind);
  };

  async function run(p: Promise<unknown>, ok: string) {
    try {
      await p;
      toast.success(ok);
    } catch (err) {
      toast.error(errorMessage(err));
      throw err;
    }
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label={caption}>
        <table className="w-full min-w-[720px] text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="border-b text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Người dùng</th>
              <th className="px-4 py-2 font-medium">Vai trò</th>
              <th className="px-4 py-2 font-medium">Trạng thái</th>
              <th className="px-4 py-2 font-medium">Ngày tạo</th>
              <th className="px-4 py-2 font-medium">Khóa / Đăng ký</th>
              <th className="px-4 py-2 text-right font-medium">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.map((u) => (
              <tr key={u.id} className="align-top">
                <td className="px-4 py-3">
                  <p className="font-medium">{u.full_name}</p>
                  <p className="text-muted-foreground">{u.email}</p>
                  {u.review_note ? <p className="mt-1 text-xs text-muted-foreground">Lý do: {u.review_note}</p> : null}
                </td>
                <td className="px-4 py-3">{ROLE[u.role]}</td>
                <td className="px-4 py-3">
                  <UserStatus user={u} />
                </td>
                <td className="px-4 py-3 tabular-nums">{fmtDate(u.created_at)}</td>
                <td className="px-4 py-3 tabular-nums">
                  {u.role === "teacher" ? `${u.course_count} khóa` : u.role === "student" ? `${u.enrollment_count} đăng ký` : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    {u.role === "teacher" && u.teacher_status !== "approved" && !u.locked_at ? (
                      <Button size="sm" aria-label={`Duyệt ${u.full_name}`} onClick={() => run(mut.approve.mutateAsync(u.id), `Đã duyệt ${u.full_name}`).catch(() => {})}>
                        Duyệt
                      </Button>
                    ) : null}
                    {u.role === "teacher" && u.teacher_status === "pending" && !u.locked_at ? (
                      <Button size="sm" variant="destructive-outline" aria-label={`Từ chối ${u.full_name}`} onClick={() => open("reject", u)}>
                        Từ chối
                      </Button>
                    ) : null}
                    {u.role === "admin" ? null : u.locked_at ? (
                      <Button size="sm" variant="outline" aria-label={`Mở khóa ${u.full_name}`} onClick={() => run(mut.unlock.mutateAsync(u.id), `Đã mở khóa ${u.full_name}`).catch(() => {})}>
                        Mở khóa
                      </Button>
                    ) : (
                      <Button size="sm" variant="ghost" aria-label={`Khóa tài khoản ${u.full_name}`} onClick={() => open("lock", u)}>
                        Khóa
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ReasonDialog
        open={dialog === "reject"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Từ chối ${target?.full_name ?? ""}?`}
        description="Giảng viên sẽ không tạo được khóa học. Bạn vẫn có thể duyệt lại sau."
        confirmLabel="Từ chối"
        onSubmit={(reason) => run(mut.reject.mutateAsync({ id: target!.id, reason }), "Đã từ chối")}
      />
      <ReasonDialog
        open={dialog === "lock"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Khóa tài khoản ${target?.full_name ?? ""}?`}
        description="Người dùng bị đăng xuất khỏi mọi thiết bị và không đăng nhập được cho tới khi mở khóa."
        confirmLabel="Khóa tài khoản"
        required={false}
        onSubmit={(reason) => run(mut.lock.mutateAsync({ id: target!.id, reason }), "Đã khóa tài khoản")}
      />
    </>
  );
}
```

> `target` được giữ lại cả khi hộp thoại đã đóng: nếu xóa ngay thì tiêu đề "Từ chối …?" bị trống trong lúc hộp thoại chạy hiệu ứng đóng.

- [x] **Bước 5: `course-table.tsx`**

```tsx
"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type AdminCourse, fmtDate, useAdminActionsMutations } from "@/lib/admin-queries";
import { ReasonDialog } from "./reason-dialog";

export function CourseStatusBadge({ course }: { course: Pick<AdminCourse, "status" | "hidden_at"> }) {
  if (course.hidden_at) return <Badge tone="destructive">Đã ẩn</Badge>;
  if (course.status === "published") return <Badge tone="success">Đã xuất bản</Badge>;
  if (course.status === "archived") return <Badge>Lưu trữ</Badge>;
  return <Badge>Nháp</Badge>;
}

export function CourseTable({ courses }: { courses: AdminCourse[] }) {
  const mut = useAdminActionsMutations();
  const [target, setTarget] = React.useState<AdminCourse | null>(null);
  const [dialog, setDialog] = React.useState<"hide" | "unhide" | null>(null);
  const open = (kind: "hide" | "unhide", c: AdminCourse) => {
    setTarget(c);
    setDialog(kind);
  };

  async function run(p: Promise<unknown>, ok: string) {
    try {
      await p;
      toast.success(ok);
    } catch (err) {
      toast.error(errorMessage(err));
      throw err;
    }
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng khóa học">
        <table className="w-full min-w-[760px] text-sm">
          <caption className="sr-only">Bảng khóa học</caption>
          <thead className="border-b text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Khóa học</th>
              <th className="px-4 py-2 font-medium">Giảng viên</th>
              <th className="px-4 py-2 font-medium">Trạng thái</th>
              <th className="px-4 py-2 font-medium">Bài / Học viên</th>
              <th className="px-4 py-2 font-medium">Ngày tạo</th>
              <th className="px-4 py-2 text-right font-medium">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {courses.map((c) => (
              <tr key={c.id} className="align-top">
                <td className="px-4 py-3">
                  {/* Admin được xem cả khóa nháp/đã ẩn (backend coi admin như chủ khóa) */}
                  <Link href={`/courses/${c.slug}`} className="font-medium text-primary hover:underline">
                    {c.title}
                  </Link>
                  {c.hidden_reason ? <p className="mt-1 text-xs text-muted-foreground">Lý do ẩn: {c.hidden_reason}</p> : null}
                </td>
                <td className="px-4 py-3">
                  <p>{c.teacher_name}</p>
                  <p className="text-muted-foreground">{c.teacher_email}</p>
                </td>
                <td className="px-4 py-3">
                  <CourseStatusBadge course={c} />
                </td>
                <td className="px-4 py-3 tabular-nums">
                  {c.lesson_count} / {c.enrollment_count}
                </td>
                <td className="px-4 py-3 tabular-nums">{fmtDate(c.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    {c.hidden_at ? (
                      <Button size="sm" variant="outline" aria-label={`Hiện lại ${c.title}`} onClick={() => open("unhide", c)}>
                        Hiện lại
                      </Button>
                    ) : c.status === "published" ? (
                      <Button size="sm" variant="destructive-outline" aria-label={`Ẩn ${c.title}`} onClick={() => open("hide", c)}>
                        Ẩn
                      </Button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ReasonDialog
        open={dialog === "hide"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Ẩn khóa “${target?.title ?? ""}”?`}
        description={`Khóa biến mất khỏi trang Khám phá và ${target?.enrollment_count ?? 0} học viên đã đăng ký tạm thời không vào học được. Giảng viên không tự xuất bản lại được.`}
        confirmLabel="Ẩn khóa học"
        onSubmit={(reason) => run(mut.hide.mutateAsync({ id: target!.id, reason }), "Đã ẩn khóa học")}
      />
      <ConfirmDialog
        open={dialog === "unhide"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Hiện lại khóa “${target?.title ?? ""}”?`}
        description="Khóa xuất hiện lại trên trang Khám phá và học viên đã đăng ký học tiếp được."
        confirmLabel="Hiện lại"
        pendingLabel="Đang xử lý…"
        onConfirm={() => run(mut.unhide.mutateAsync(target!.id), "Đã hiện lại khóa học")}
      />
    </>
  );
}
```

- [x] **Bước 6: `overview.tsx`**

```tsx
"use client";

import { AlertTriangle, BookOpen, ClipboardCheck, GraduationCap, type LucideIcon, MessageCircleQuestion, UserCheck, Users } from "lucide-react";
import Link from "next/link";
import { type AdminStats } from "@/lib/admin-queries";
import { cn } from "@/lib/utils";

function Tile({ icon: Icon, label, value, sub, href, highlight }: { icon: LucideIcon; label: string; value: number; sub?: string; href?: string; highlight?: boolean }) {
  const body = (
    <>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className={cn("size-4", highlight && "text-accent")} aria-hidden />
        {label}
      </div>
      <p className="mt-2 text-3xl font-semibold tabular-nums">{value.toLocaleString("vi-VN")}</p>
      {sub ? <p className="mt-1 text-xs text-muted-foreground">{sub}</p> : null}
    </>
  );
  const cls = cn("block rounded-lg border bg-surface p-4", highlight && "border-accent/60", href && "transition-colors hover:bg-muted");
  return href ? (
    <Link href={href} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/** Ô số liệu tổng quan. Ô "Chờ duyệt" nổi bật khi có người đang chờ và dẫn thẳng tới danh sách. */
export function StatTiles({ s }: { s: AdminStats }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile icon={UserCheck} label="Giảng viên chờ duyệt" value={s.pending_teachers} href="/admin/users?tab=pending" highlight={s.pending_teachers > 0} sub={s.pending_teachers > 0 ? "Bấm để xử lý" : "Không có ai đang chờ"} />
      <Tile icon={Users} label="Học viên" value={s.students} sub={`${s.enrollments.toLocaleString("vi-VN")} lượt đăng ký khóa`} href="/admin/users?tab=student" />
      <Tile icon={GraduationCap} label="Giảng viên" value={s.teachers} sub={s.locked_users ? `${s.locked_users} tài khoản đang bị khóa` : undefined} href="/admin/users?tab=teacher" />
      <Tile icon={BookOpen} label="Khóa đã xuất bản" value={s.courses_published} sub={`${s.courses_draft} nháp · ${s.courses_hidden} đã ẩn`} href="/admin/courses" />
      <Tile icon={MessageCircleQuestion} label="Câu hỏi AI Tutor (7 ngày)" value={s.tutor_questions_7d} />
      <Tile icon={ClipboardCheck} label="Bài quiz đã nộp (7 ngày)" value={s.quiz_submissions_7d} />
      <Tile icon={AlertTriangle} label="Tác vụ AI lỗi (7 ngày)" value={s.failed_jobs_7d} highlight={s.failed_jobs_7d > 0} sub="Xử lý tài liệu, sinh câu hỏi" />
    </div>
  );
}

const dayFmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "UTC" });

/** Cột đăng ký mới 14 ngày. Một chuỗi số liệu nên không cần chú thích; có bảng ẩn cho trình đọc màn hình. */
export function SignupChart({ days }: { days: AdminStats["signups_14d"] }) {
  const max = Math.max(1, ...days.map((d) => d.count));
  const total = days.reduce((a, d) => a + d.count, 0);
  const label = (d: { day: string }) => dayFmt.format(new Date(`${d.day}T00:00:00Z`));
  return (
    <figure className="rounded-lg border bg-surface p-4">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="font-semibold">Người dùng mới 14 ngày qua</span>
        <span className="text-sm text-muted-foreground tabular-nums">Tổng {total}</span>
      </figcaption>
      <div className="mt-4 flex h-32 items-end gap-1" aria-hidden>
        {days.map((d) => (
          <div key={d.day} className="group relative flex h-full flex-1 flex-col justify-end" title={`${label(d)}: ${d.count} người`}>
            <div className="rounded-t-[4px] bg-primary transition-opacity group-hover:opacity-80" style={{ height: `${(d.count / max) * 100}%`, minHeight: d.count ? 4 : 0 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted-foreground" aria-hidden>
        <span>{label(days[0])}</span>
        <span>{label(days[days.length - 1])}</span>
      </div>
      <table className="sr-only">
        <caption>Số người dùng mới theo ngày</caption>
        <tbody>
          {days.map((d) => (
            <tr key={d.day}>
              <th scope="row">{label(d)}</th>
              <td>{d.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
```

- [x] **Bước 7: `action-log.tsx`**

```tsx
"use client";

import { BookOpen, User } from "lucide-react";
import { type AdminAction, actionLabel, fmtDateTime } from "@/lib/admin-queries";

export function ActionLog({ items }: { items: AdminAction[] }) {
  if (items.length === 0) return <p className="rounded-lg border border-dashed p-6 text-center text-muted-foreground">Chưa có thao tác quản trị nào.</p>;
  return (
    <ol className="divide-y rounded-lg border bg-surface">
      {items.map((a) => {
        const Icon = a.target_type === "course" ? BookOpen : User;
        return (
          <li key={a.id} className="flex gap-3 px-4 py-3 text-sm">
            <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <p>
                <span className="font-medium">{actionLabel(a.action)}</span> · <span className="break-all">{a.target_label}</span>
              </p>
              {a.note ? <p className="text-muted-foreground">Lý do: {a.note}</p> : null}
              <p className="text-xs text-muted-foreground">
                {a.admin_name ?? "Quản trị viên đã xóa"} · <time dateTime={a.created_at}>{fmtDateTime(a.created_at)}</time>
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
```

- [x] **Bước 8: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend && git commit -m "feat(web): admin tables, reason dialog, overview tiles and activity log"
```

---

## Task 6: Các trang `/admin`

**Files:**
- Create: `frontend/src/app/(main)/admin/layout.tsx`, `page.tsx`, `users/page.tsx`, `courses/page.tsx`, `activity/page.tsx`

- [x] **Bước 1: `admin/layout.tsx`** (một chỗ chặn quyền cho cả khu)

```tsx
import { RequireAuth } from "@/lib/auth/require-auth";

export const metadata = { title: "Quản trị" };

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <RequireAuth admin>{children}</RequireAuth>;
}
```

- [x] **Bước 2: `admin/page.tsx`** (Tổng quan)

```tsx
"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { ErrorState, PageHeader } from "@/components/app/states";
import { ActionLog } from "@/components/admin/action-log";
import { SignupChart, StatTiles } from "@/components/admin/overview";
import { UserTable } from "@/components/admin/user-table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { useAdminActions, useAdminStats, useAdminUsers } from "@/lib/admin-queries";

export default function AdminHome() {
  const stats = useAdminStats();
  const pending = useAdminUsers({ role: "teacher", status: "pending", page: 1 });
  const actions = useAdminActions(1, 8);

  return (
    <>
      <PageHeader title="Tổng quan hệ thống">Tình hình người dùng, khóa học và các việc cần xử lý.</PageHeader>
      {stats.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : stats.isError ? (
        <ErrorState error={stats.error} onRetry={() => stats.refetch()} />
      ) : (
        <div className="space-y-6">
          <StatTiles s={stats.data} />
          <SignupChart days={stats.data.signups_14d} />
        </div>
      )}

      <section className="mt-10" aria-labelledby="pending-title">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id="pending-title" className="text-lg font-semibold">
            Giảng viên chờ duyệt
          </h2>
          <Button asChild variant="link">
            <Link href="/admin/users?tab=pending">
              Xem tất cả <ArrowRight />
            </Link>
          </Button>
        </div>
        {pending.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : pending.isError ? (
          <ErrorState error={pending.error} onRetry={() => pending.refetch()} />
        ) : pending.data.items.length === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-muted-foreground">Không có giảng viên nào đang chờ duyệt.</p>
        ) : (
          <UserTable users={pending.data.items.slice(0, 5)} caption="Giảng viên chờ duyệt" />
        )}
      </section>

      <section className="mt-10" aria-labelledby="log-title">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 id="log-title" className="text-lg font-semibold">
            Hoạt động quản trị gần đây
          </h2>
          <Button asChild variant="link">
            <Link href="/admin/activity">
              Nhật ký đầy đủ <ArrowRight />
            </Link>
          </Button>
        </div>
        {actions.isPending ? <Skeleton className="h-24 w-full" /> : actions.isError ? <ErrorState error={actions.error} onRetry={() => actions.refetch()} /> : <ActionLog items={actions.data.items} />}
      </section>
    </>
  );
}
```

- [x] **Bước 3: `admin/users/page.tsx`**

Tab nằm trên URL (`?tab=pending`), để link "Chờ duyệt" ở Tổng quan mở đúng tab và F5 không mất tab. `useSearchParams` phải nằm trong `Suspense`, nếu không `next build` báo lỗi.

```tsx
"use client";

import { Search, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { FilterTabs } from "@/components/admin/filter-tabs";
import { UserTable } from "@/components/admin/user-table";
import { Pagination } from "@/components/course/course-card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { type UserFilter, useAdminUsers } from "@/lib/admin-queries";
import { useDebounced } from "@/lib/use-debounced";

const TABS = [
  { value: "pending", label: "Chờ duyệt", filter: { role: "teacher", status: "pending" } },
  { value: "teacher", label: "Giảng viên", filter: { role: "teacher" } },
  { value: "student", label: "Học viên", filter: { role: "student" } },
  { value: "locked", label: "Đã khóa", filter: { status: "locked" } },
  { value: "all", label: "Tất cả", filter: {} },
] as const satisfies readonly { value: string; label: string; filter: Omit<UserFilter, "page"> }[];
type Tab = (typeof TABS)[number]["value"];
const isTab = (v: string | null): v is Tab => TABS.some((t) => t.value === v);

export default function AdminUsersPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <UsersView />
    </React.Suspense>
  );
}

function UsersView() {
  const router = useRouter();
  const params = useSearchParams();
  const tabParam = params.get("tab");
  const tab: Tab = isTab(tabParam) ? tabParam : "pending";
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  // đổi tab hoặc từ khóa thì về trang 1
  const [paging, setPaging] = React.useState({ key: "", page: 1 });
  const key = `${tab}|${query}`;
  const page = paging.key === key ? paging.page : 1;
  const filter = TABS.find((t) => t.value === tab)!.filter;
  const users = useAdminUsers({ ...filter, q: query, page });

  return (
    <>
      <PageHeader title="Người dùng">Duyệt giảng viên mới, tìm kiếm và khóa tài khoản vi phạm.</PageHeader>
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterTabs label="Lọc người dùng" value={tab} options={TABS.map(({ value, label }) => ({ value, label }))} onChange={(v) => router.replace(`/admin/users?tab=${v}`)} />
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="user-search" className="sr-only">
            Tìm người dùng
          </label>
          <Input id="user-search" type="search" placeholder="Tìm theo tên hoặc email…" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {users.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => users.refetch()} />
      ) : users.data.items.length === 0 ? (
        <EmptyState icon={Users} title={query ? `Không tìm thấy ai cho “${query}”.` : tab === "pending" ? "Không có giảng viên nào đang chờ duyệt." : "Chưa có người dùng nào."} />
      ) : (
        <div aria-busy={users.isFetching}>
          <UserTable users={users.data.items} caption={`Danh sách người dùng: ${TABS.find((t) => t.value === tab)!.label}`} />
          <Pagination page={page} total={users.data.total} size={users.data.size} onPage={(p) => setPaging({ key, page: p })} />
        </div>
      )}
    </>
  );
}
```

- [x] **Bước 4: `admin/courses/page.tsx`**

```tsx
"use client";

import { Library, Search } from "lucide-react";
import * as React from "react";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { CourseTable } from "@/components/admin/course-table";
import { FilterTabs } from "@/components/admin/filter-tabs";
import { Pagination } from "@/components/course/course-card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { type CourseFilter, useAdminCourses } from "@/lib/admin-queries";
import { useDebounced } from "@/lib/use-debounced";

type Status = NonNullable<CourseFilter["status"]> | "all";
const OPTIONS: { value: Status; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "published", label: "Đã xuất bản" },
  { value: "draft", label: "Nháp" },
  { value: "hidden", label: "Đã ẩn" },
];

export default function AdminCoursesPage() {
  const [status, setStatus] = React.useState<Status>("all");
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  const [paging, setPaging] = React.useState({ key: "", page: 1 });
  const key = `${status}|${query}`;
  const page = paging.key === key ? paging.page : 1;
  const courses = useAdminCourses({ status: status === "all" ? undefined : status, q: query, page });

  return (
    <>
      <PageHeader title="Khóa học">Toàn bộ khóa của mọi giảng viên. Ẩn khóa vi phạm kèm lý do cho giảng viên.</PageHeader>
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterTabs label="Lọc theo trạng thái" value={status} options={OPTIONS} onChange={setStatus} />
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="course-search" className="sr-only">
            Tìm khóa học
          </label>
          <Input id="course-search" type="search" placeholder="Tìm theo tên khóa hoặc giảng viên…" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {courses.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : courses.isError ? (
        <ErrorState error={courses.error} onRetry={() => courses.refetch()} />
      ) : courses.data.items.length === 0 ? (
        <EmptyState icon={Library} title={query ? `Không tìm thấy khóa nào cho “${query}”.` : "Không có khóa học nào."} />
      ) : (
        <div aria-busy={courses.isFetching}>
          <CourseTable courses={courses.data.items} />
          <Pagination page={page} total={courses.data.total} size={courses.data.size} onPage={(p) => setPaging({ key, page: p })} />
        </div>
      )}
    </>
  );
}
```

- [x] **Bước 5: `admin/activity/page.tsx`**

```tsx
"use client";

import * as React from "react";
import { ErrorState, PageHeader } from "@/components/app/states";
import { ActionLog } from "@/components/admin/action-log";
import { Pagination } from "@/components/course/course-card";
import { Skeleton } from "@/components/ui/misc";
import { useAdminActions } from "@/lib/admin-queries";

export default function AdminActivityPage() {
  const [page, setPage] = React.useState(1);
  const actions = useAdminActions(page);
  return (
    <>
      <PageHeader title="Nhật ký quản trị">Mọi thao tác duyệt, từ chối, khóa tài khoản và ẩn khóa học.</PageHeader>
      {actions.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : actions.isError ? (
        <ErrorState error={actions.error} onRetry={() => actions.refetch()} />
      ) : (
        <>
          <ActionLog items={actions.data.items} />
          <Pagination page={page} total={actions.data.total} size={actions.data.size} onPage={setPage} />
        </>
      )}
    </>
  );
}
```

- [x] **Bước 6: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test && npm run build
git add frontend && git commit -m "feat(web): admin overview, users, courses and activity pages"
```

Expected: phần cuối của `next build` có `○ /admin`, `○ /admin/activity`, `○ /admin/courses`, `○ /admin/users`.

---

## Task 7: Trang chủ admin, thông báo cho giảng viên, khóa bị ẩn

**Files:**
- Modify: `frontend/src/app/(main)/page.tsx`, `frontend/src/app/(main)/teach/page.tsx` (+test), `frontend/src/components/teach/course-editor.tsx`

- [x] **Bước 1: Trang chủ** (`src/app/(main)/page.tsx`, thay toàn bộ)

Admin được chuyển sang `/admin`. Giảng viên chưa duyệt thấy khung "đang chờ" hoặc "bị từ chối" kèm lý do. Tên gọi tách theo khoảng trắng bất kỳ.

```tsx
"use client";

import { ArrowRight, Clock, Compass, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { PageHeader } from "@/components/app/states";
import { MyCourseList } from "@/components/course/my-course-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { type User, useAuth } from "@/lib/auth/auth-context";

/** Tên gọi: chữ cuối của họ tên Việt ("Nguyễn Văn An" → "An"). */
const givenName = (fullName: string) => fullName.trim().split(/\s+/).slice(-1)[0] ?? fullName;

/** Giảng viên chưa được duyệt: nói rõ đang chờ hay đã bị từ chối (kèm lý do quản trị viên ghi). */
function TeacherReviewNotice({ user }: { user: User }) {
  if (user.role !== "teacher" || user.teacher_status === "approved") return null;
  const rejected = user.teacher_status === "rejected";
  const Icon = rejected ? XCircle : Clock;
  return (
    <div role="status" className="mb-6 flex gap-3 rounded-lg border p-4">
      <Icon className={rejected ? "mt-0.5 size-5 shrink-0 text-destructive" : "mt-0.5 size-5 shrink-0 text-accent"} aria-hidden />
      <div>
        <p className="font-medium">{rejected ? "Yêu cầu giảng dạy chưa được chấp nhận" : "Tài khoản giảng viên đang chờ duyệt"}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {rejected
            ? `Lý do: ${user.review_note ?? "không ghi"}. Liên hệ quản trị viên nếu bạn cần xem xét lại.`
            : "Quản trị viên sẽ duyệt sớm. Trong lúc chờ, bạn vẫn xem được các khóa học đã xuất bản."}
        </p>
      </div>
    </div>
  );
}

export default function HomePage() {
  const { user, status } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";
  // Quản trị viên không học cũng không dạy: trang chủ của họ là khu quản trị.
  React.useEffect(() => {
    if (isAdmin) router.replace("/admin");
  }, [isAdmin, router]);
  if (status === "loading" || isAdmin) return <Skeleton className="h-40 w-full" />;

  if (!user)
    return (
      <section className="mx-auto max-w-2xl py-10 text-center md:py-20">
        <h1 className="text-3xl font-semibold md:text-4xl">Học theo nhịp của bạn, có AI giải đáp ngay trong bài</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          AI Tutor trả lời dựa trên đúng tài liệu của khóa học và luôn ghi nguồn, để bạn kiểm chứng được.
        </p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/explore">
              <Compass /> Khám phá khóa học
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/register">Tạo tài khoản</Link>
          </Button>
        </div>
      </section>
    );

  // Chỉ giảng viên đã duyệt mới vào được /teach.
  const canTeach = user.role === "teacher" && user.teacher_status === "approved";

  return (
    <>
      <PageHeader title={`Chào ${givenName(user.full_name)}`}>
        {user.role === "student" ? "Tiếp tục từ chỗ bạn đã dừng." : canTeach ? "Quản lý các khóa bạn đang dạy." : "Chào mừng bạn đến với LMS-AI."}
      </PageHeader>
      <TeacherReviewNotice user={user} />
      {user.role === "student" ? (
        <>
          <MyCourseList limit={3} />
          <Button asChild variant="link" className="mt-4">
            <Link href="/my">
              Xem tất cả khóa của tôi <ArrowRight />
            </Link>
          </Button>
        </>
      ) : (
        <Button asChild>
          <Link href={canTeach ? "/teach" : "/explore"}>{canTeach ? "Tới khóa đang dạy" : "Khám phá khóa học"}</Link>
        </Button>
      )}
    </>
  );
}
```

- [x] **Bước 2: `/teach` khi admin mở** (`src/app/(main)/teach/page.tsx`)

Trong `TeachGate`, đổi đoạn chữ và nút:

```tsx
          <p className="text-muted-foreground">Trang này dành cho giảng viên. Quản trị viên xem mọi khóa học ở khu quản trị.</p>
          <Button asChild variant="outline" className="mt-4">
            <Link href="/admin/courses">Đến danh sách khóa học</Link>
          </Button>
```

Trong danh sách khóa, thay dòng huy hiệu:

```tsx
                {c.hidden_reason ? (
                  <Badge tone="destructive">Đã bị ẩn</Badge>
                ) : c.status === "published" ? (
                  <Badge tone="success">Đã xuất bản</Badge>
                ) : (
                  <Badge>Nháp</Badge>
                )}
```

Trong `src/app/(main)/teach/page.test.tsx`, test "admin thấy thông báo…" đổi dòng kiểm link:

```tsx
    expect(screen.getByRole("link", { name: /danh sách khóa học/ })).toHaveAttribute("href", "/admin/courses");
```

- [x] **Bước 3: Trình soạn khóa bị ẩn** (`src/components/teach/course-editor.tsx`)

Import thêm `EyeOff`:

```tsx
import { BarChart3, Eye, EyeOff, Globe, Trash2 } from "lucide-react";
```

Thay dòng huy hiệu trạng thái:

```tsx
        {course.hidden_reason ? (
          <Badge tone="destructive">Đã bị ẩn</Badge>
        ) : course.status === "published" ? (
          <Badge tone="success">Đã xuất bản</Badge>
        ) : (
          <Badge>Nháp</Badge>
        )}
```

Điều kiện hiện nút Xuất bản:

```tsx
        {course.status !== "published" && !course.hidden_reason ? (
```

Chèn ngay **trước** đoạn `<p className="mb-6 rounded-md border border-dashed p-3 text-sm text-muted-foreground md:hidden">`:

```tsx
      {course.hidden_reason ? (
        <div role="alert" className="mb-6 flex gap-3 rounded-lg border border-destructive/50 p-4">
          <EyeOff className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
          <div>
            <p className="font-medium">Quản trị viên đã ẩn khóa học này</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Lý do: {course.hidden_reason}. Học viên tạm thời không vào học được. Hãy chỉnh sửa nội dung rồi liên hệ quản trị viên để được hiện lại.
            </p>
          </div>
        </div>
      ) : null}

```

- [x] **Bước 4: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend && git commit -m "feat(web): admin lands on /admin, teacher review notice, hidden course banner"
```

Expected: **100 passed**.

---

## Task 8: E2E khu quản trị

**Files:**
- Create: `frontend/e2e/admin-data.ts`, `frontend/e2e/admin.spec.ts`

- [x] **Bước 1: `e2e/admin-data.ts`**

```ts
/** Dữ liệu giả cho khu quản trị (E2E). */
export const admin = { id: "u-9", email: "admin@example.com", full_name: "Quản trị viên", role: "admin", teacher_status: null };

export const pendingTeacher = {
  id: "u-3",
  email: "cuong@gv.vn",
  full_name: "Phạm Văn Cường",
  role: "teacher",
  teacher_status: "pending",
  locked_at: null,
  review_note: null,
  created_at: "2026-10-05T02:00:00Z",
  course_count: 0,
  enrollment_count: 0,
};

export const studentRow = {
  ...pendingTeacher,
  id: "u-1",
  email: "an@sv.vn",
  full_name: "Nguyễn Văn An",
  role: "student",
  teacher_status: null,
  enrollment_count: 2,
};

export const stats = (over: Record<string, unknown> = {}) => ({
  students: 120,
  teachers: 8,
  pending_teachers: 1,
  locked_users: 0,
  courses_published: 12,
  courses_draft: 3,
  courses_hidden: 0,
  enrollments: 340,
  tutor_questions_7d: 85,
  quiz_submissions_7d: 41,
  failed_jobs_7d: 2,
  signups_14d: Array.from({ length: 14 }, (_, i) => ({ day: new Date(Date.UTC(2026, 8, 23 + i)).toISOString().slice(0, 10), count: i % 4 })),
  ...over,
});

export const adminCourse = (over: Record<string, unknown> = {}) => ({
  id: "11111111-1111-1111-1111-111111111111",
  title: "Giải tích 1",
  slug: "giai-tich-1",
  status: "published",
  teacher_id: "u-2",
  teacher_name: "Trần Thị Bình",
  teacher_email: "gv@lms.vn",
  created_at: "2026-09-01T00:00:00Z",
  lesson_count: 2,
  enrollment_count: 35,
  hidden_at: null,
  hidden_reason: null,
  ...over,
});

export const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, size: 20 });
```

- [x] **Bước 2: `e2e/admin.spec.ts`**

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { admin, adminCourse, page as pageOf, pendingTeacher, stats, studentRow } from "./admin-data";
import { courseDetail, mockApi, teacher } from "./mock-api";

test.describe("quản trị viên", () => {
  test("đăng nhập xong vào thẳng Tổng quan: số liệu, giảng viên chờ duyệt, nhật ký", async ({ page }) => {
    let loggedIn = false;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/login": (r) => {
          loggedIn = true;
          return r.fulfill({ json: { access_token: "tok", token_type: "bearer" } });
        },
        "GET /me": (r) => (loggedIn ? r.fulfill({ json: admin }) : r.fulfill({ status: 401, json: { error: { code: "NOT_AUTHENTICATED", message: "x" } } })),
        "GET /admin/stats": (r) => r.fulfill({ json: stats() }),
        "GET /admin/users": (r) => r.fulfill({ json: pageOf([pendingTeacher]) }),
        "GET /admin/actions": (r) =>
          r.fulfill({
            json: pageOf([
              { id: "a1", admin_name: "Quản trị viên", action: "hide_course", target_type: "course", target_id: "c", target_label: "Khóa X", note: "Vi phạm bản quyền", created_at: "2026-10-06T03:00:00Z" },
            ]),
          }),
      },
    });
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Mật khẩu").fill("Admin12345");
    await page.getByRole("button", { name: "Đăng nhập" }).click();

    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole("heading", { name: "Tổng quan hệ thống" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Giảng viên chờ duyệt\s*1/ })).toHaveAttribute("href", "/admin/users?tab=pending");
    await expect(page.getByRole("cell", { name: /cuong@gv\.vn/ })).toBeVisible();
    await expect(page.getByText("Lý do: Vi phạm bản quyền")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("duyệt và từ chối giảng viên (từ chối bắt buộc ghi lý do)", async ({ page }) => {
    const calls: { path: string; body: unknown }[] = [];
    let pending = [pendingTeacher, { ...pendingTeacher, id: "u-4", email: "dung@gv.vn", full_name: "Lê Thị Dung" }];
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/users": (r) => r.fulfill({ json: pageOf(pending) }),
        "POST /admin/teachers/*/approve": (r, url) => {
          calls.push({ path: url.pathname, body: null });
          pending = pending.filter((u) => !url.pathname.includes(u.id));
          return r.fulfill({ json: { ...pendingTeacher, teacher_status: "approved" } });
        },
        "POST /admin/teachers/*/reject": (r, url) => {
          calls.push({ path: url.pathname, body: r.request().postDataJSON() });
          pending = pending.filter((u) => !url.pathname.includes(u.id));
          return r.fulfill({ json: { ...pendingTeacher, teacher_status: "rejected" } });
        },
      },
    });
    await page.goto("/admin/users?tab=pending");
    await expect(page.getByRole("button", { name: "Chờ duyệt" })).toHaveAttribute("aria-pressed", "true");
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByRole("button", { name: "Duyệt Phạm Văn Cường" }).click();
    await expect(page.getByRole("cell", { name: /cuong@gv\.vn/ })).toBeHidden();

    await page.getByRole("button", { name: "Từ chối Lê Thị Dung" }).click();
    const dialog = page.getByRole("dialog", { name: "Từ chối Lê Thị Dung?" });
    await dialog.getByRole("button", { name: "Từ chối" }).click();
    await expect(dialog.getByText("Cần nhập lý do")).toBeVisible();
    await dialog.getByLabel("Lý do").fill("Chưa có minh chứng chuyên môn");
    await dialog.getByRole("button", { name: "Từ chối" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText("Không có giảng viên nào đang chờ duyệt.")).toBeVisible();
    expect(calls).toEqual([
      { path: "/api/v1/admin/teachers/u-3/approve", body: null },
      { path: "/api/v1/admin/teachers/u-4/reject", body: { reason: "Chưa có minh chứng chuyên môn" } },
    ]);
  });

  test("tab Học viên lọc đúng và khóa tài khoản", async ({ page }) => {
    const queries: string[] = [];
    let locked = false;
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/users": (r, url) => {
          queries.push(url.search);
          return r.fulfill({ json: pageOf([{ ...studentRow, locked_at: locked ? "2026-10-06T03:00:00Z" : null }]) });
        },
        "POST /admin/users/*/lock": (r) => {
          locked = true;
          return r.fulfill({ json: { ...studentRow, locked_at: "2026-10-06T03:00:00Z" } });
        },
      },
    });
    await page.goto("/admin/users");
    await page.getByRole("button", { name: "Học viên" }).click();
    await expect(page).toHaveURL(/tab=student/);
    await expect.poll(() => queries.at(-1)).toContain("role=student");
    await page.getByRole("button", { name: "Khóa tài khoản Nguyễn Văn An" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Khóa tài khoản" }).click(); // lý do không bắt buộc
    await expect(page.getByRole("cell", { name: "Đã khóa", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Mở khóa Nguyễn Văn An" })).toBeVisible();
  });

  test("ẩn khóa học vi phạm kèm lý do", async ({ page }) => {
    let hidden: Record<string, unknown> | null = null;
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/courses": (r) => r.fulfill({ json: pageOf([adminCourse(hidden ? { status: "archived", hidden_at: "2026-10-06T03:00:00Z", hidden_reason: "Sao chép giáo trình" } : {})]) }),
        "POST /admin/courses/*/hide": (r) => {
          hidden = r.request().postDataJSON();
          return r.fulfill({ json: adminCourse({ status: "archived" }) });
        },
      },
    });
    await page.goto("/admin/courses");
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByRole("button", { name: "Ẩn Giải tích 1" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/35 học viên/)).toBeVisible();
    await dialog.getByLabel("Lý do").fill("Sao chép giáo trình");
    await dialog.getByRole("button", { name: "Ẩn khóa học" }).click();
    await expect(page.getByText("Lý do ẩn: Sao chép giáo trình")).toBeVisible();
    await expect(page.getByRole("button", { name: "Hiện lại Giải tích 1" })).toBeVisible();
    expect(hidden).toEqual({ reason: "Sao chép giáo trình" });
  });
});

test.describe("phân quyền và thông báo cho giảng viên", () => {
  test("giảng viên mở /admin thấy thông báo không có quyền", async ({ page }) => {
    await mockApi(page, { user: teacher });
    await page.goto("/admin");
    await expect(page.getByText("Trang này chỉ dành cho quản trị viên.")).toBeVisible();
  });

  test("giảng viên bị từ chối thấy lý do ở trang chủ", async ({ page }) => {
    const rejected = { ...teacher, teacher_status: "rejected", review_note: "Chưa có minh chứng chuyên môn" };
    await mockApi(page, { user: rejected });
    await page.goto("/");
    await expect(page.getByText("Yêu cầu giảng dạy chưa được chấp nhận")).toBeVisible();
    await expect(page.getByText(/Lý do: Chưa có minh chứng chuyên môn/)).toBeVisible();
    await expectAccessible(page);
  });

  test("khóa bị ẩn: trình soạn hiện lý do và không còn nút Xuất bản", async ({ page }) => {
    const hiddenCourse = courseDetail({ status: "archived", is_owner: true, hidden_reason: "Sao chép giáo trình" });
    await mockApi(page, { user: teacher, extra: { "GET /courses/giai-tich-1": (r) => r.fulfill({ json: hiddenCourse }) } });
    await page.goto("/teach/giai-tich-1");
    await expect(page.getByRole("alert").filter({ hasText: "Quản trị viên đã ẩn khóa học này" })).toContainText("Sao chép giáo trình");
    await expect(page.getByText("Đã bị ẩn")).toBeVisible();
    await expect(page.getByRole("button", { name: "Xuất bản" })).toHaveCount(0);
    await expectAccessible(page);
  });
});
```

Ghi chú:

- Dùng `getByRole("cell", { name: /cuong@gv\.vn/ })` thay vì tìm theo tên: tên người còn nằm trong `aria-label` của nút ở ô Thao tác, nên tìm theo tên sẽ ra 2 ô.
- "Đã khóa" vừa là huy hiệu vừa là nút lọc, nên tìm theo `cell`.

- [x] **Bước 3: Chạy**

```bash
npx playwright test e2e/admin.spec.ts
npx playwright test
```

Expected: 14 passed; toàn bộ **42 passed**.

- [x] **Bước 4: Commit và push**

```bash
git add frontend/e2e && git commit -m "test(web): E2E for admin area"
git push
```

Expected: CI xanh cả job `backend` lẫn `frontend`.

---

# Phần 2: Email (xác nhận khi đăng ký, thông báo), gửi lại yêu cầu duyệt, xuất CSV, phản hồi 👎 của AI Tutor

### P2.0 Mục tiêu và quyết định

- **Đăng ký phải dùng email thật.** Đăng ký xong, hệ thống gửi link xác nhận (hiệu lực 24 giờ). Chưa bấm link thì **không đăng nhập được** (403 `EMAIL_NOT_VERIFIED`). Lỗi này chỉ báo khi mật khẩu đúng, để người ngoài không dò được email nào chưa xác nhận.
- **Gửi lại link:** `POST /auth/resend-verification` luôn trả 202, kể cả với email không tồn tại (không lộ ai đã đăng ký). Tối đa 3 lần mỗi giờ cho một email (429 kèm `Retry-After`). Mỗi lần gửi lại, link cũ hết dùng được.
- **Giảng viên chỉ vào hàng chờ duyệt khi đã xác nhận email.** Lúc xác nhận xong, hệ thống gửi email báo cho mọi admin. Admin có thêm tab "Chưa xác nhận email".
- **Email thông báo:**
  - Duyệt giảng viên, từ chối (kèm lý do).
  - Khóa tài khoản (kèm lý do nếu có).
  - Ẩn khóa học (kèm lý do) và hiện lại khóa học: gửi cho chủ khóa.
  - Giảng viên mới chờ duyệt: gửi cho admin.
- **Outbox pattern:** email được ghi vào bảng `email_outbox` **trong cùng transaction** với thay đổi sinh ra nó. Worker gửi sau. Nhờ vậy:
  - API không bao giờ phải chờ SMTP.
  - SMTP lỗi thì không mất mail: worker thử lại tối đa 5 lần.
  - Không có chuyện "đã duyệt mà không gửi mail" hay "đã gửi mail mà duyệt bị rollback".

  Sau khi commit, API báo worker gửi ngay (`kick`). Ngoài ra có cron mỗi phút để vét phần còn sót. Hai lần chạy song song không gửi trùng nhờ `FOR UPDATE SKIP LOCKED`.
- **SMTP chuẩn, không thêm thư viện** (`smtplib` chạy trong thread).
  - Dev: **Mailpit**, một container bắt mọi mail, xem ở `http://localhost:8025`, không gửi ra ngoài.
  - Chạy thật: **Brevo**, gói miễn phí 300 mail/ngày. Chỉ cần đổi `.env`.
- **Tài khoản cũ** được coi là đã xác nhận (migration gán `email_verified_at = created_at`). Admin tạo bằng `seed_admin` cũng vậy.
- **Giảng viên bị từ chối gửi lại yêu cầu duyệt** (`POST /me/teacher-request`): quay về hàng chờ, xóa lý do cũ, báo admin.
- **Xuất CSV** (`GET /admin/users/export`): theo đúng tab và từ khóa đang xem, tối đa 10.000 dòng, có BOM UTF-8 để Excel hiện đúng tiếng Việt.
- **Câu trả lời AI bị chê (👎):**
  - Admin xem mọi khóa, có tên học viên (`/admin/feedback`, thêm ô số liệu ở Tổng quan).
  - Giảng viên xem trong trang Thống kê của khóa, **không có tên học viên**, để học viên dám bấm 👎.
  - Mỗi mục có câu hỏi ngay trước câu trả lời, bài học, thời gian, và nhãn nếu AI đã từ chối trả lời.

**Mã phần 2 đã chạy thử** (nối tiếp phần 1):

- Backend: **638 test pass** (628 + 10 mới trong `tests/test_email.py`). `ruff` sạch. `alembic check` sạch. Migration chạy `downgrade` / `upgrade` hai chiều đều được.
- Frontend: **102 unit test** pass. **56 test E2E** pass (28 kịch bản × 2 khung hình), có axe. `eslint`, `tsc`, `next build` sạch.

### P2.1 API mới / thay đổi

| Endpoint | Ghi chú |
|---|---|
| `POST /auth/register` | Như cũ, nhưng gửi email xác nhận. **Frontend không tự đăng nhập nữa** |
| `POST /auth/login` | Thêm 403 `EMAIL_NOT_VERIFIED` (chỉ khi mật khẩu đúng) |
| `POST /auth/verify-email` `{token}` | 200 `UserOut`. 400 `INVALID_TOKEN` (sai, hoặc đã bị link mới thay) / `TOKEN_EXPIRED`. Bấm lại link đã dùng thì vẫn 200 |
| `POST /auth/resend-verification` `{email}` | Luôn 202. 429 `RATE_LIMITED` khi quá 3 lần/giờ |
| `POST /me/teacher-request` | Giảng viên bị từ chối gửi lại yêu cầu. 409 `NOT_REJECTED` |
| `GET /me` | `UserOut` thêm `email_verified` |
| `GET /admin/users?status=unverified` | Tab mới. `status=pending` chỉ còn giảng viên **đã xác nhận email**. Mỗi dòng thêm `email_verified` |
| `GET /admin/users/export` | CSV, cùng tham số lọc với `/admin/users` |
| `GET /admin/stats` | Thêm `tutor_downvotes_7d`. `pending_teachers` chỉ đếm người đã xác nhận email |
| `GET /admin/tutor-feedback` | Câu trả lời bị 👎 trên mọi khóa, có `student_name` |
| `GET /courses/{id}/tutor-feedback` | Chủ khóa / admin. `student_name` luôn `null` |

### P2.2 File

```
backend/
├── alembic/versions/c5d2e8f1a734_email.py
├── app/modules/notify/{__init__,models,templates,mailer,outbox}.py
└── tests/test_email.py
Sửa: app/core/config.py, app/modules/auth/{models,schemas,service,router}.py, app/modules/admin/{schemas,service,router}.py,
     app/modules/analytics/{schemas,service,router}.py, app/worker/{tasks,settings}.py, app/models_registry.py,
     .env.example, tests/{conftest,helpers,fakes}.py
docker-compose.yml (Mailpit)

frontend/src/
├── lib/auth/email-verification.ts (+test)
├── components/auth/{resend-verification, check-email}.tsx
├── components/admin/feedback-list.tsx
└── app/(auth)/verify-email/{page, verify-email}.tsx, app/(main)/admin/feedback/page.tsx
Sửa: lib/auth/auth-context.tsx, app/(auth)/register/register-form.tsx, app/(auth)/login/login-form.tsx, app/(main)/page.tsx,
     lib/admin-queries.ts, components/admin/{user-table, overview}.tsx, app/(main)/admin/users/page.tsx,
     lib/quiz/queries.ts, components/teach/course-analytics.tsx, lib/api/schema.d.ts
E2E: e2e/auth-email.spec.ts (mới), e2e/admin.spec.ts (thêm 2 kịch bản), e2e/admin-data.ts, e2e/mock-api.ts
```

---

## Task 9: Hạ tầng email (outbox, SMTP, worker, Mailpit)

**Files:**
- Modify: `backend/app/core/config.py`, `backend/app/modules/auth/models.py`, `backend/app/models_registry.py`, `backend/app/worker/tasks.py`, `backend/app/worker/settings.py`, `backend/.env.example`, `docker-compose.yml`
- Create: `backend/app/modules/notify/__init__.py` (rỗng), `models.py`, `templates.py`, `mailer.py`, `outbox.py`, `backend/alembic/versions/c5d2e8f1a734_email.py`

- [x] **Bước 1: Cấu hình** (`app/core/config.py`, thêm ngay sau `tutor_prestream_deadline_s`)

```python
    # Địa chỉ frontend, dùng để tạo link trong email (xác nhận email...). Không có dấu / ở cuối.
    app_base_url: str = "http://localhost:3000"
    # Bắt buộc bấm link xác nhận email trước khi đăng nhập được.
    email_verification_required: bool = True
    verify_token_hours: int = 24
    # SMTP. Mặc định trỏ vào Mailpit (docker compose) để dev không gửi mail thật; chạy thật thì dùng Brevo.
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False  # Brevo cổng 587: true
    smtp_timeout_s: float = 20.0
    mail_from: str = "LMS-AI <no-reply@example.com>"
    mail_max_attempts: int = 5  # gửi lỗi quá số lần này thì bỏ (status failed)
```

Thêm vào cuối `backend/.env.example` (test `test_env_example_lists_every_setting_with_a_valid_value` bắt buộc mọi setting phải có ở đây):

```bash
# Email. Link trong email trỏ về APP_BASE_URL (địa chỉ frontend, không có dấu / ở cuối).
APP_BASE_URL=http://localhost:3000
EMAIL_VERIFICATION_REQUIRED=true
VERIFY_TOKEN_HOURS=24
# Dev: Mailpit trong docker compose (SMTP_HOST=mailpit khi chạy trong Docker, localhost khi chạy uvicorn ngoài),
# xem thư ở http://localhost:8025. Chạy thật với Brevo: SMTP_HOST=smtp-relay.brevo.com, SMTP_PORT=587,
# SMTP_STARTTLS=true, SMTP_USER/SMTP_PASSWORD lấy ở Brevo › SMTP & API, MAIL_FROM là email đã xác minh trong Brevo.
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_STARTTLS=false
SMTP_TIMEOUT_S=20
MAIL_FROM="LMS-AI <no-reply@example.com>"
MAIL_MAX_ATTEMPTS=5
```

- [x] **Bước 2: Model** (`app/modules/notify/models.py`)

```python
import enum
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class EmailStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class EmailOutbox(IdMixin, TimestampMixin, Base):
    """Hộp thư đi (outbox pattern): email được ghi CÙNG transaction với thay đổi sinh ra nó (đăng ký,
    duyệt giảng viên...), worker gửi sau. API không bao giờ chờ SMTP, và không mất mail khi SMTP lỗi."""

    __tablename__ = "email_outbox"
    __table_args__ = (
        Index("ix_email_outbox_pending", "created_at", postgresql_where=text("status = 'pending'")),
    )

    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(40))  # verify_email | teacher_approved | ...
    status: Mapped[EmailStatus] = mapped_column(
        SAEnum(EmailStatus, name="email_status"), default=EmailStatus.pending, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Trong `app/modules/auth/models.py`, thêm vào `User` ngay dưới `review_note`:

```python
    # NULL = chưa bấm link xác nhận email (không đăng nhập được khi EMAIL_VERIFICATION_REQUIRED=true).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None
```

và thêm class mới ở cuối file:

```python
class EmailToken(IdMixin, TimestampMixin, Base):
    """Token một lần gửi qua email (hiện chỉ dùng để xác nhận email). Chỉ lưu hash, giống refresh token."""

    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))  # verify_email
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`app/models_registry.py` thêm (giữ thứ tự chữ cái):

```python
from app.modules.notify import models as notify_models  # noqa: F401
```

- [x] **Bước 3: Nội dung email** (`app/modules/notify/templates.py`)

```python
"""Nội dung email. Mỗi hàm trả (subject, text, html). HTML tối giản, inline style để hiện ổn trong Gmail."""

from html import escape

Mail = tuple[str, str, str]


def _html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    body = "".join(f'<p style="margin:0 0 12px">{p}</p>' for p in paragraphs)
    if button:
        label, url = button
        body += (
            f'<p style="margin:20px 0"><a href="{escape(url)}" style="background:#0f766e;color:#fff;'
            f'padding:10px 18px;border-radius:6px;text-decoration:none;display:inline-block">{escape(label)}</a></p>'
            f'<p style="margin:0 0 12px;font-size:13px;color:#555">Nếu nút không bấm được, mở link: {escape(url)}</p>'
        )
    return (
        '<div style="font-family:Arial,sans-serif;font-size:15px;color:#111;max-width:560px;margin:auto">'
        f'<h2 style="font-size:20px">{escape(title)}</h2>{body}'
        '<p style="margin-top:24px;font-size:12px;color:#777">LMS-AI · Email tự động, vui lòng không trả lời.</p></div>'
    )


def verify_email(name: str, url: str, hours: int) -> Mail:
    subject = "Xác nhận email đăng ký LMS-AI"
    text = (
        f"Chào {name},\n\nBấm link sau để xác nhận email và kích hoạt tài khoản (hiệu lực {hours} giờ):\n{url}\n\n"
        "Nếu bạn không đăng ký, hãy bỏ qua email này."
    )
    html = _html(
        "Xác nhận email",
        [
            f"Chào {escape(name)},",
            f"Bấm nút dưới đây để kích hoạt tài khoản. Link có hiệu lực {hours} giờ.",
            "Nếu bạn không đăng ký, hãy bỏ qua email này.",
        ],
        ("Xác nhận email", url),
    )
    return subject, text, html


def teacher_approved(name: str, url: str) -> Mail:
    subject = "Tài khoản giảng viên đã được duyệt"
    text = f"Chào {name},\n\nTài khoản giảng viên của bạn đã được duyệt. Bạn có thể tạo khóa học ngay:\n{url}"
    html = _html(
        "Tài khoản đã được duyệt",
        [
            f"Chào {escape(name)},",
            "Tài khoản giảng viên của bạn đã được duyệt. Bạn có thể tạo khóa học ngay.",
        ],
        ("Tạo khóa học", url),
    )
    return subject, text, html


def teacher_rejected(name: str, reason: str, url: str) -> Mail:
    subject = "Yêu cầu giảng dạy chưa được chấp nhận"
    text = (
        f"Chào {name},\n\nYêu cầu giảng dạy của bạn chưa được chấp nhận.\nLý do: {reason}\n\n"
        f"Bạn có thể bổ sung thông tin và gửi lại yêu cầu tại:\n{url}"
    )
    html = _html(
        "Yêu cầu chưa được chấp nhận",
        [
            f"Chào {escape(name)},",
            "Yêu cầu giảng dạy của bạn chưa được chấp nhận.",
            f"<b>Lý do:</b> {escape(reason)}",
            "Bạn có thể bổ sung thông tin và gửi lại yêu cầu.",
        ],
        ("Gửi lại yêu cầu", url),
    )
    return subject, text, html


def account_locked(name: str, reason: str | None) -> Mail:
    subject = "Tài khoản LMS-AI đã bị khóa"
    why = f"Lý do: {reason}" if reason else "Liên hệ quản trị viên để biết thêm chi tiết."
    text = f"Chào {name},\n\nTài khoản của bạn đã bị quản trị viên khóa.\n{why}"
    html = _html(
        "Tài khoản đã bị khóa",
        [f"Chào {escape(name)},", "Tài khoản của bạn đã bị quản trị viên khóa.", escape(why)],
    )
    return subject, text, html


def course_hidden(name: str, title: str, reason: str, url: str) -> Mail:
    subject = f"Khóa học “{title}” đã bị ẩn"
    text = (
        f"Chào {name},\n\nQuản trị viên đã ẩn khóa học “{title}”.\nLý do: {reason}\n\n"
        f"Hãy chỉnh sửa nội dung rồi liên hệ quản trị viên để được hiện lại:\n{url}"
    )
    html = _html(
        "Khóa học đã bị ẩn",
        [
            f"Chào {escape(name)},",
            f"Quản trị viên đã ẩn khóa học <b>{escape(title)}</b>.",
            f"<b>Lý do:</b> {escape(reason)}",
            "Hãy chỉnh sửa nội dung rồi liên hệ quản trị viên để được hiện lại.",
        ],
        ("Mở trình soạn khóa", url),
    )
    return subject, text, html


def course_unhidden(name: str, title: str, url: str) -> Mail:
    subject = f"Khóa học “{title}” đã được hiện lại"
    text = f"Chào {name},\n\nKhóa học “{title}” đã được hiện lại, học viên học tiếp được.\n{url}"
    html = _html(
        "Khóa học đã được hiện lại",
        [
            f"Chào {escape(name)},",
            f"Khóa học <b>{escape(title)}</b> đã được hiện lại, học viên học tiếp được.",
        ],
        ("Mở khóa học", url),
    )
    return subject, text, html


def new_pending_teacher(teacher_name: str, teacher_email: str, url: str) -> Mail:
    subject = f"Giảng viên mới chờ duyệt: {teacher_name}"
    text = f"{teacher_name} ({teacher_email}) đang chờ duyệt tài khoản giảng viên.\n{url}"
    html = _html(
        "Giảng viên mới chờ duyệt",
        [f"<b>{escape(teacher_name)}</b> ({escape(teacher_email)}) đang chờ duyệt tài khoản giảng viên."],
        ("Mở danh sách chờ duyệt", url),
    )
    return subject, text, html
```

- [x] **Bước 4: Gửi SMTP** (`app/modules/notify/mailer.py`)

```python
import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.core.config import Settings


class Mailer(Protocol):
    async def send(self, to: str, subject: str, text: str, html: str) -> None: ...


class SmtpMailer:
    """SMTP chuẩn (Mailpit khi dev, Brevo khi chạy thật). smtplib chạy trong thread để không chặn event loop."""

    def __init__(self, s: Settings):
        self.s = s

    def _send_sync(self, msg: EmailMessage) -> None:
        s = self.s
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_s) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)

    async def send(self, to: str, subject: str, text: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.s.mail_from
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="lms-ai")
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        await asyncio.to_thread(self._send_sync, msg)
```

- [x] **Bước 5: Outbox** (`app/modules/notify/outbox.py`)

```python
import logging
from functools import lru_cache
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.time import utcnow
from app.modules.notify.mailer import Mailer
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.templates import Mail

logger = logging.getLogger(__name__)
SEND_BATCH = 20


def queue_email(db: AsyncSession, to: str, template: str, mail: Mail) -> None:
    """Thêm email vào outbox trong transaction đang mở. Nơi gọi tự commit (cùng thay đổi nghiệp vụ)."""
    subject, text, html = mail
    db.add(EmailOutbox(to_email=to, subject=subject, body_text=text, body_html=html, template=template))


class MailKicker(Protocol):
    async def kick(self) -> None: ...


class ArqMailKicker:
    """Báo worker gửi ngay sau khi commit (không đợi cron mỗi phút). Lỗi Redis thì bỏ qua: cron vẫn gửi."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def kick(self) -> None:
        try:
            if self._pool is None:
                self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
            await self._pool.enqueue_job("send_pending_emails")
        except Exception:
            logger.warning("Không báo được worker gửi email, cron sẽ gửi sau", exc_info=True)


@lru_cache
def get_mail_kicker() -> MailKicker:
    return ArqMailKicker(get_settings().redis_url)


async def send_pending(session_factory: async_sessionmaker, mailer: Mailer, limit: int = SEND_BATCH) -> int:
    """Gửi các email đang chờ. Trả số email gửi thành công.

    FOR UPDATE SKIP LOCKED: hai lần chạy song song (kick + cron) không gửi trùng một email.
    Gửi lỗi thì tăng attempts, quá MAIL_MAX_ATTEMPTS thì chuyển failed."""
    max_attempts = get_settings().mail_max_attempts
    sent = 0
    async with session_factory() as db:
        rows = (
            await db.scalars(
                select(EmailOutbox)
                .where(EmailOutbox.status == EmailStatus.pending)
                .order_by(EmailOutbox.created_at, EmailOutbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for mail in rows:
            mail.attempts += 1
            try:
                await mailer.send(mail.to_email, mail.subject, mail.body_text, mail.body_html)
            except Exception as exc:  # noqa: BLE001 — SMTP lỗi kiểu gì cũng thử lại ở lượt sau
                mail.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                if mail.attempts >= max_attempts:
                    mail.status = EmailStatus.failed
                logger.warning("Gửi email %s tới %s lỗi: %s", mail.id, mail.to_email, mail.last_error)
            else:
                mail.status = EmailStatus.sent
                mail.sent_at = utcnow()
                mail.last_error = None
                sent += 1
        await db.commit()
    return sent
```

- [x] **Bước 6: Worker**

Cuối `app/worker/tasks.py`:

```python
async def send_pending_emails(ctx: dict) -> int:
    """Gửi email trong outbox. API gọi ngay sau khi commit (kick), cron chạy mỗi phút để vét phần còn sót."""
    from app.modules.notify.outbox import send_pending

    return await send_pending(ctx.get("session_factory", SessionLocal), ctx["mailer"])
```

`app/worker/settings.py`:

- Import `SmtpMailer` từ `app.modules.notify.mailer` và `send_pending_emails` từ `app.worker.tasks`.
- Trong `startup` thêm `ctx["mailer"] = SmtpMailer(s)`.
- Thêm vào `functions`:

  ```python
          func(send_pending_emails, name="send_pending_emails", timeout=120),
  ```

- Thêm vào `cron_jobs` (sau `sweep_stale_jobs`):

  ```python
          # Vét email còn trong outbox (kick từ API bị lỡ, SMTP lỗi cần thử lại)
          cron(
              send_pending_emails,
              name="send_pending_emails_cron",
              minute=set(range(60)),
              run_at_startup=True,
              timeout=120,
          ),
  ```

- [x] **Bước 7: Migration** (`alembic/versions/c5d2e8f1a734_email.py`)

```python
"""email: users.email_verified_at, email_tokens, email_outbox

Revision ID: c5d2e8f1a734
Revises: b81e4c7a2d90
Create Date: 2026-10-07 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d2e8f1a734"
down_revision: str | Sequence[str] | None = "b81e4c7a2d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Tài khoản tạo trước khi có xác nhận email: coi như đã xác nhận, để không ai bị khóa ngoài.
    op.execute("UPDATE users SET email_verified_at = created_at")
    op.create_table(
        "email_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_email_tokens_user_id"), "email_tokens", ["user_id"], unique=False)
    op.create_table(
        "email_outbox",
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("template", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "failed", name="email_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_outbox_pending",
        "email_outbox",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_email_outbox_pending", table_name="email_outbox", postgresql_where=sa.text("status = 'pending'")
    )
    op.drop_table("email_outbox")
    sa.Enum(name="email_status").drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f("ix_email_tokens_user_id"), table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_column("users", "email_verified_at")
```

- [x] **Bước 8: Mailpit** (`docker-compose.yml`)

Thêm service (đặt sau `minio`). Tag ghim theo bản mới nhất ở <https://github.com/axllent/mailpit/releases> lúc làm, **không dùng `latest`**:

```yaml
  mailpit:
    # Bắt mọi email khi dev (không gửi ra ngoài). Xem thư: http://localhost:8025
    image: axllent/mailpit:<tag mới nhất, vd. v1.xx.y>
    ports: ["127.0.0.1:8025:8025", "[::1]:8025:8025"]
```

Thêm `mailpit: { condition: service_started }` vào `depends_on` của `api` và `worker`.

Trong `backend/.env` (file local, **không commit**), thêm:

```bash
SMTP_HOST=mailpit
SMTP_PORT=1025
APP_BASE_URL=http://localhost:3000
```

- [x] **Bước 9: Kiểm tra và commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Expected: 628 passed (chưa có test mới; luồng đăng ký chưa đổi).

```bash
git add backend docker-compose.yml && git commit -m "feat(api): email outbox, SMTP mailer, worker sender and Mailpit for dev"
```

---

## Task 10: Xác nhận email khi đăng ký (backend)

**Files:**
- Modify: `backend/app/modules/auth/schemas.py`, `service.py`, `router.py`, `backend/tests/{conftest,helpers,fakes}.py`
- Test: `backend/tests/test_email.py`

- [x] **Bước 1: Hạ tầng test**

`tests/fakes.py`, thêm ở cuối:

```python
class RecordingKicker:
    """MailKicker giả: chỉ đếm số lần API báo worker gửi email."""

    def __init__(self) -> None:
        self.kicks = 0

    async def kick(self) -> None:
        self.kicks += 1


class RecordingMailer:
    """Mailer giả cho send_pending: ghi lại email đã gửi; fail_times > 0 thì ném lỗi N lần đầu."""

    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[dict] = []
        self.fail_times = fail_times

    async def send(self, to: str, subject: str, text: str, html: str) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("SMTP down")
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})
```

`tests/conftest.py`:

- Import `get_mail_kicker` và `RecordingKicker`.
- Thêm fixture:

  ```python
  @pytest.fixture
  def kicker():
      return RecordingKicker()
  ```

- Fixture `client` nhận thêm `kicker` và đặt `app.dependency_overrides[get_mail_kicker] = lambda: kicker`.

`tests/helpers.py`: `register_user` có thêm tham số `verify=True`. Mặc định đánh dấu đã xác nhận ngay trong DB, nên **600+ test cũ không phải sửa**:

```python
async def register_user(
    client, email, password="password123", role="student", full_name="Người dùng", verify=True
):
    """Đăng ký qua API. verify=True (mặc định): đánh dấu luôn đã xác nhận email trong DB, để test khác
    không phải đi qua email. Test về xác nhận email truyền verify=False."""
    r = await client.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "role": role, "full_name": full_name},
    )
    assert r.status_code == 201, r.text
    if verify:
        await verify_email_in_db(r.json()["id"])
    return r.json()


async def verify_email_in_db(user_id: str) -> None:
    from app.core.time import utcnow

    async with SessionLocal() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.email_verified_at = utcnow()
        await db.commit()
```

- [x] **Bước 2: Viết test (sẽ fail)** (`tests/test_email.py`, cả file; phần admin / CSV / 👎 sẽ pass ở Task 11)

```python
"""Xác nhận email khi đăng ký, email thông báo (outbox), gửi lại yêu cầu duyệt, xuất CSV, phản hồi 👎 của AI Tutor."""

import re
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import EmailToken
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.outbox import send_pending
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from tests.fakes import RecordingMailer
from tests.helpers import (
    API,
    login,
    make_admin,
    make_published_course,
    make_student,
    make_teacher,
    register_user,
)


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def _outbox(to: str | None = None, *, verify: bool = False) -> list[EmailOutbox]:
    """Email trong outbox. Mặc định bỏ qua mail xác nhận (mọi tài khoản đăng ký qua API đều có một)."""
    async with SessionLocal() as db:
        stmt = select(EmailOutbox).order_by(EmailOutbox.created_at, EmailOutbox.id)
        if to:
            stmt = stmt.where(EmailOutbox.to_email == to)
        stmt = stmt.where((EmailOutbox.template == "verify_email") == verify)
        return list((await db.scalars(stmt)).all())


def _token(mail: EmailOutbox) -> str:
    return re.search(r"verify-email\?token=([\w-]+)", mail.body_text).group(1)


async def _login_raw(client, email):
    return await client.post(f"{API}/auth/login", json={"email": email, "password": "password123"})


# ---------- xác nhận email ----------


async def test_register_sends_verification_and_login_waits_for_it(client, kicker):
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An", verify=False)
    (mail,) = await _outbox("an@x.com", verify=True)
    assert (mail.template, mail.status) == ("verify_email", EmailStatus.pending)
    assert "http://localhost:3000/verify-email?token=" in mail.body_text and "Nguyễn Văn An" in mail.body_html
    assert kicker.kicks == 1

    assert _code(await _login_raw(client, "an@x.com")) == (403, "EMAIL_NOT_VERIFIED")
    wrong = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": "sai-mat-khau"})
    assert _code(wrong) == (401, "INVALID_CREDENTIALS")  # sai mật khẩu không lộ trạng thái xác nhận

    r = await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert (await _login_raw(client, "an@x.com")).status_code == 200
    # bấm lại link đã dùng: vẫn thành công
    assert (await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})).status_code == 200


async def test_verify_rejects_bad_and_expired_links(client):
    user = await register_user(client, "b@x.com", verify=False)
    (mail,) = await _outbox("b@x.com", verify=True)
    r = await client.post(f"{API}/auth/verify-email", json={"token": "khong-phai-token-that"})
    assert _code(r) == (400, "INVALID_TOKEN")
    async with SessionLocal() as db:
        await db.execute(
            update(EmailToken)
            .where(EmailToken.user_id == uuid.UUID(user["id"]))
            .values(expires_at=utcnow() - timedelta(minutes=1))
        )
        await db.commit()
    r = await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})
    assert _code(r) == (400, "TOKEN_EXPIRED")


async def test_resend_replaces_old_link_hides_unknown_emails_and_is_rate_limited(client):
    await register_user(client, "c@x.com", verify=False)
    r = await client.post(f"{API}/auth/resend-verification", json={"email": "ai-do@x.com"})
    assert r.status_code == 202
    assert await _outbox("ai-do@x.com", verify=True) == []

    assert (
        await client.post(f"{API}/auth/resend-verification", json={"email": "C@x.com"})
    ).status_code == 202
    old, new = await _outbox("c@x.com", verify=True)
    r = await client.post(f"{API}/auth/verify-email", json={"token": _token(old)})
    assert _code(r) == (400, "INVALID_TOKEN")  # link cũ bị thay
    assert (await client.post(f"{API}/auth/verify-email", json={"token": _token(new)})).status_code == 200

    # đã xác nhận thì không gửi nữa; quá 3 lần/giờ cho một email thì 429
    await client.post(f"{API}/auth/resend-verification", json={"email": "c@x.com"})
    assert len(await _outbox("c@x.com", verify=True)) == 2
    await client.post(f"{API}/auth/resend-verification", json={"email": "c@x.com"})  # lần thứ 3 trong giờ
    r = await client.post(f"{API}/auth/resend-verification", json={"email": "c@x.com"})
    assert _code(r) == (429, "RATE_LIMITED") and r.headers["retry-after"]


async def test_me_reports_email_verified(client):
    await register_user(client, "d@x.com")
    me = await client.get(f"{API}/me", headers=await login(client, "d@x.com"))
    assert me.json()["email_verified"] is True


# ---------- giảng viên chờ duyệt ----------


async def test_unverified_teacher_is_not_in_pending_queue_and_admins_are_told_after_verify(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher", full_name="Phạm Văn Cường", verify=False)
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert r.json()["total"] == 0
    assert (await client.get(f"{API}/admin/stats", headers=ad)).json()["pending_teachers"] == 0
    r = await client.get(f"{API}/admin/users", params={"status": "unverified"}, headers=ad)
    assert [u["id"] for u in r.json()["items"]] == [gv["id"]]

    (mail,) = await _outbox("gv@x.com", verify=True)
    await client.post(f"{API}/auth/verify-email", json={"token": _token(mail)})
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["email"] for u in r.json()["items"]] == ["gv@x.com"]
    (notice,) = await _outbox("admin@x.com")
    assert notice.template == "new_pending_teacher" and "Phạm Văn Cường" in notice.subject


async def test_rejected_teacher_can_ask_again(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    headers = await login(client, "gv@x.com")
    assert _code(await client.post(f"{API}/me/teacher-request", headers=headers)) == (409, "NOT_REJECTED")

    await client.post(
        f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "Thiếu minh chứng"}, headers=ad
    )
    r = await client.post(f"{API}/me/teacher-request", headers=headers)
    assert (r.json()["teacher_status"], r.json()["review_note"]) == ("pending", None)
    assert [m.template for m in await _outbox("admin@x.com")] == ["new_pending_teacher"]
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["id"] for u in r.json()["items"]] == [gv["id"]]


# ---------- email từ thao tác quản trị ----------


async def test_admin_actions_email_the_affected_person(client, kicker):
    _, ad = await make_admin(client)
    gv1 = await register_user(client, "gv1@x.com", role="teacher", full_name="Lê Một")
    gv2 = await register_user(client, "gv2@x.com", role="teacher", full_name="Lê Hai")
    sv_id, _ = await make_student(client)
    before = kicker.kicks

    await client.post(f"{API}/admin/teachers/{gv1['id']}/approve", headers=ad)
    await client.post(
        f"{API}/admin/teachers/{gv2['id']}/reject", json={"reason": "Thiếu minh chứng"}, headers=ad
    )
    await client.post(f"{API}/admin/users/{sv_id}/lock", json={"reason": "Spam"}, headers=ad)
    gv1_headers = await login(client, "gv1@x.com")
    course, _, _ = await make_published_course(client, gv1_headers, title="Giải tích")
    await client.post(f"{API}/admin/courses/{course['id']}/hide", json={"reason": "Sao chép"}, headers=ad)
    await client.post(f"{API}/admin/courses/{course['id']}/unhide", headers=ad)

    assert [m.template for m in await _outbox("gv1@x.com")] == [
        "teacher_approved",
        "course_hidden",
        "course_unhidden",
    ]
    (rejected,) = await _outbox("gv2@x.com")
    assert rejected.template == "teacher_rejected" and "Thiếu minh chứng" in rejected.body_text
    (locked,) = await _outbox("sv@x.com")
    assert locked.template == "account_locked" and "Spam" in locked.body_text
    hidden = (await _outbox("gv1@x.com"))[1]
    assert f"/teach/{course['slug']}" in hidden.body_text and "Sao chép" in hidden.body_html
    assert kicker.kicks - before == 5


async def test_send_pending_marks_sent_and_retries_then_gives_up():
    async with SessionLocal() as db:
        db.add(
            EmailOutbox(to_email="a@x.com", subject="S", body_text="T", body_html="<p>T</p>", template="t")
        )
        await db.commit()

    flaky = RecordingMailer(fail_times=1)
    assert await send_pending(SessionLocal, flaky) == 0
    (mail,) = await _outbox()
    assert (mail.status, mail.attempts, mail.last_error) == (
        EmailStatus.pending,
        1,
        "ConnectionError: SMTP down",
    )
    assert await send_pending(SessionLocal, flaky) == 1
    (mail,) = await _outbox()
    assert (mail.status, mail.attempts, mail.last_error) == (EmailStatus.sent, 2, None)
    assert flaky.sent == [{"to": "a@x.com", "subject": "S", "text": "T", "html": "<p>T</p>"}]

    async with SessionLocal() as db:
        db.add(
            EmailOutbox(
                to_email="b@x.com", subject="S", body_text="T", body_html="T", template="t", attempts=4
            )
        )
        await db.commit()
    assert await send_pending(SessionLocal, RecordingMailer(fail_times=9)) == 0
    assert (await _outbox("b@x.com"))[0].status == EmailStatus.failed  # lần thứ 5 vẫn lỗi → bỏ


# ---------- CSV ----------


async def test_export_users_csv_follows_filters(client):
    _, ad = await make_admin(client)
    _, sv = await make_student(client)
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await make_teacher(client)
    r = await client.get(f"{API}/admin/users/export", params={"role": "student"}, headers=ad)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "nguoi-dung.csv" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿Họ tên,Email,Vai trò")
    lines = text.strip().splitlines()
    assert len(lines) == 3 and "Nguyễn Văn An,an@x.com,Học viên" in text and "gv@x.com" not in text
    assert (await client.get(f"{API}/admin/users/export", headers=sv)).status_code == 403


# ---------- phản hồi 👎 của AI Tutor ----------


async def _downvoted_answer(course_id: str, user_id: str, lesson_id: str | None = None) -> None:
    async with SessionLocal() as db:
        session = ChatSession(
            user_id=uuid.UUID(user_id),
            course_id=uuid.UUID(course_id),
            lesson_id=lesson_id and uuid.UUID(lesson_id),
        )
        db.add(session)
        await db.flush()
        db.add(ChatMessage(session_id=session.id, role=ChatRole.user, content="Đạo hàm là gì?"))
        await db.flush()
        db.add(
            ChatMessage(
                session_id=session.id, role=ChatRole.assistant, content="Câu trả lời sai [1].", feedback=-1
            )
        )
        db.add(ChatMessage(session_id=session.id, role=ChatRole.assistant, content="Câu tốt", feedback=1))
        await db.commit()


async def test_tutor_feedback_lists_downvoted_answers(client):
    _, ad = await make_admin(client)
    _, gv = await make_teacher(client)
    _, other = await make_teacher(client, "gv2@x.com")
    course, _, lesson = await make_published_course(client, gv)
    sv_id, _ = await make_student(client)
    await _downvoted_answer(course["id"], sv_id, lesson["id"])

    r = await client.get(f"{API}/admin/tutor-feedback", headers=ad)
    (item,) = r.json()["items"]
    assert (item["question"], item["answer"], item["student_name"]) == (
        "Đạo hàm là gì?",
        "Câu trả lời sai [1].",
        "Người dùng",
    )
    assert (item["course_slug"], item["lesson_title"]) == (course["slug"], lesson["title"])
    assert (await client.get(f"{API}/admin/stats", headers=ad)).json()["tutor_downvotes_7d"] == 1

    mine = await client.get(f"{API}/courses/{course['id']}/tutor-feedback", headers=gv)
    assert mine.json()["total"] == 1 and mine.json()["items"][0]["student_name"] is None
    assert (
        await client.get(f"{API}/courses/{course['id']}/tutor-feedback", headers=other)
    ).status_code == 404
```

- [x] **Bước 3: Schemas** (`app/modules/auth/schemas.py`)

Thêm trước `TokenOut`:

```python
class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResendVerificationIn(BaseModel):
    email: EmailStr

    normalize_email = field_validator("email")(_lower)
```

Cuối `UserOut`:

```python
    email_verified: bool = False  # đọc từ property User.email_verified
```

- [x] **Bước 4: Service** (`app/modules/auth/service.py`, thay toàn bộ)

```python
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.core.time import utcnow
from app.modules.auth.models import EmailToken, RefreshToken, Role, TeacherStatus, User
from app.modules.auth.schemas import LoginIn, RegisterIn
from app.modules.notify import templates
from app.modules.notify.outbox import queue_email

VERIFY = "verify_email"


def _email_taken() -> AppError:
    return AppError("EMAIL_TAKEN", "Email đã được sử dụng", 409)


async def register(db: AsyncSession, data: RegisterIn) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise _email_taken()
    role = Role(data.role)
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=role,
        teacher_status=TeacherStatus.pending if role == Role.teacher else None,
    )
    db.add(user)
    try:
        await db.flush()  # cần user.id cho link xác nhận
        await _issue_verify_token(db, user)
        await db.commit()
    except IntegrityError:
        # Hai request đăng ký cùng email chạy song song: cả hai qua được bước kiểm tra ở trên,
        # request thua vấp unique constraint (ở flush) → vẫn trả 409 thay vì 500.
        await db.rollback()
        if await db.scalar(select(User.id).where(User.email == email)):
            raise _email_taken() from None
        raise
    return user


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    """Trả về (access_token, refresh_token_raw). Commit luôn cả các thay đổi đang chờ trong session."""
    raw, hashed = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days),
        )
    )
    await db.commit()
    return create_access_token(user.id, user.role.value), raw


async def login(db: AsyncSession, data: LoginIn) -> tuple[str, str]:
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng", 401)
    if user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    # Kiểm sau mật khẩu: người không biết mật khẩu không dò được email nào chưa xác nhận.
    if get_settings().email_verification_required and user.email_verified_at is None:
        raise AppError("EMAIL_NOT_VERIFIED", "Bạn cần xác nhận email trước khi đăng nhập", 403)
    return await issue_tokens(db, user)


async def refresh(db: AsyncSession, raw: str) -> tuple[str, str]:
    token = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)).with_for_update()
    )
    if token is None:
        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
    if token.revoked_at is not None:
        # Token đã bị xoay mà vẫn có người dùng lại, coi như bị đánh cắp: thu hồi toàn bộ phiên của user.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await db.commit()
        raise AppError("TOKEN_REUSED", "Phiên đăng nhập đã bị thu hồi, vui lòng đăng nhập lại", 401)
    if token.expires_at <= utcnow():
        raise AppError("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn", 401)
    user = await db.get(User, token.user_id)
    if user is None or user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    token.revoked_at = utcnow()
    return await issue_tokens(db, user)


async def logout(db: AsyncSession, raw: str) -> None:
    token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
    if token is not None and token.revoked_at is None:
        token.revoked_at = utcnow()
        await db.commit()


async def create_admin(db: AsyncSession, email: str, password: str, full_name: str = "Quản trị viên") -> User:
    email = email.lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=Role.admin,
            email_verified_at=utcnow(),  # admin tạo bằng script: coi như đã xác nhận
        )
        db.add(user)
    else:
        user.role = Role.admin
        user.password_hash = hash_password(password)
        user.email_verified_at = user.email_verified_at or utcnow()
    await db.commit()
    return user


async def approve_teacher(db: AsyncSession, email: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower(), User.role == Role.teacher))
    if user is None:
        raise AppError("NOT_FOUND", "Không tìm thấy giảng viên", 404)
    user.teacher_status = TeacherStatus.approved
    await db.commit()
    return user


# ---------- xác nhận email ----------


async def _issue_verify_token(db: AsyncSession, user: User) -> None:
    """Hủy các link cũ chưa dùng, tạo link mới và đưa email vào outbox (cùng transaction với nơi gọi)."""
    s = get_settings()
    await db.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.purpose == VERIFY, EmailToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    raw, hashed = new_refresh_token()
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=VERIFY,
            token_hash=hashed,
            expires_at=utcnow() + timedelta(hours=s.verify_token_hours),
        )
    )
    url = f"{s.app_base_url}/verify-email?token={raw}"
    queue_email(db, user.email, VERIFY, templates.verify_email(user.full_name, url, s.verify_token_hours))


async def notify_admins_pending_teacher(db: AsyncSession, teacher: User) -> None:
    url = f"{get_settings().app_base_url}/admin/users?tab=pending"
    admins = (await db.scalars(select(User).where(User.role == Role.admin, User.locked_at.is_(None)))).all()
    for admin in admins:
        queue_email(
            db,
            admin.email,
            "new_pending_teacher",
            templates.new_pending_teacher(teacher.full_name, teacher.email, url),
        )


async def verify_email(db: AsyncSession, raw: str) -> User:
    token = await db.scalar(
        select(EmailToken)
        .where(EmailToken.token_hash == hash_refresh_token(raw), EmailToken.purpose == VERIFY)
        .with_for_update()
    )
    invalid = AppError("INVALID_TOKEN", "Link xác nhận không hợp lệ hoặc đã được thay bằng link mới", 400)
    if token is None:
        raise invalid
    user = await db.get(User, token.user_id)
    if token.used_at is not None:
        # Bấm lại link đã dùng (vd. mở mail lần 2): đã xác nhận rồi thì coi như thành công.
        if user is not None and user.email_verified_at is not None:
            return user
        raise invalid
    if token.expires_at <= utcnow():
        raise AppError("TOKEN_EXPIRED", "Link xác nhận đã hết hạn, hãy gửi lại email xác nhận", 400)
    token.used_at = utcnow()
    user.email_verified_at = utcnow()
    if user.role == Role.teacher and user.teacher_status == TeacherStatus.pending:
        await notify_admins_pending_teacher(db, user)  # chỉ báo admin khi email đã thật
    await db.commit()
    return user


async def resend_verification(db: AsyncSession, email: str) -> bool:
    """Trả True nếu có gửi. API luôn trả 202 để không lộ email nào đã đăng ký."""
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if user is None or user.email_verified_at is not None or user.locked_at is not None:
        return False
    await _issue_verify_token(db, user)
    await db.commit()
    return True


async def request_teacher_review(db: AsyncSession, user: User) -> User:
    """Giảng viên bị từ chối gửi lại yêu cầu duyệt: quay về hàng chờ, xóa lý do cũ, báo admin."""
    if user.role != Role.teacher or user.teacher_status != TeacherStatus.rejected:
        raise AppError("NOT_REJECTED", "Chỉ gửi lại được khi yêu cầu giảng dạy đã bị từ chối", 409)
    user.teacher_status = TeacherStatus.pending
    user.review_note = None
    await notify_admins_pending_teacher(db, user)
    await db.commit()
    return user
```

> `flush` nằm **trong** khối `try`: nếu hai request đăng ký cùng email chạy song song, request thua sẽ vấp unique constraint ngay ở `flush` (chứ không phải ở `commit` như trước), và vẫn phải trả 409. Test `test_register_race…` trong `test_auth.py` kiểm tra đúng chỗ này.

- [x] **Bước 5: Router** (`app/modules/auth/router.py`, thay toàn bộ)

```python
from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginIn,
    RegisterIn,
    ResendVerificationIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)
from app.modules.notify.outbox import MailKicker, get_mail_kicker

router = APIRouter(prefix="/api/v1", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
        path=REFRESH_PATH,
        max_age=s.refresh_token_days * 86400,
    )


@router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(
    data: RegisterIn, db: AsyncSession = Depends(get_db), kicker: MailKicker = Depends(get_mail_kicker)
):
    """Tạo tài khoản và gửi email xác nhận. Chưa xác nhận thì đăng nhập nhận 403 EMAIL_NOT_VERIFIED."""
    user = await service.register(db, data)
    await kicker.kick()
    return user


@router.post("/auth/verify-email", response_model=UserOut)
async def verify_email(
    data: VerifyEmailIn, db: AsyncSession = Depends(get_db), kicker: MailKicker = Depends(get_mail_kicker)
):
    """400 INVALID_TOKEN (sai / đã thay bằng link mới) hoặc TOKEN_EXPIRED. Bấm lại link đã dùng thì vẫn 200."""
    user = await service.verify_email(db, data.token)
    await kicker.kick()  # giảng viên vừa xác nhận: báo admin
    return user


RESEND_LIMIT = 3  # mỗi email tối đa 3 lần / giờ


@router.post("/auth/resend-verification", status_code=202)
async def resend_verification(
    data: ResendVerificationIn,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
    kicker: MailKicker = Depends(get_mail_kicker),
) -> dict:
    """Luôn 202 (không lộ email nào đã đăng ký). 429 RATE_LIMITED khi gửi quá 3 lần mỗi giờ cho một email."""
    wait = await limiter.hit(f"verify-resend:{data.email}", RESEND_LIMIT, 3600)
    if wait is not None:
        raise AppError(
            "RATE_LIMITED",
            "Bạn đã yêu cầu gửi lại quá nhiều lần, vui lòng thử lại sau",
            429,
            {"retry_after": wait},
            headers={"Retry-After": str(wait)},
        )
    if await service.resend_verification(db, data.email):
        await kicker.kick()
    return {"status": "accepted"}


@router.post("/me/teacher-request", response_model=UserOut)
async def request_teacher_review(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    """Giảng viên bị từ chối gửi lại yêu cầu duyệt. 409 NOT_REJECTED nếu không ở trạng thái bị từ chối."""
    user = await service.request_teacher_review(db, user)
    await kicker.kick()
    return user


@router.post("/auth/login", response_model=TokenOut)
async def login(data: LoginIn, response: Response, db: AsyncSession = Depends(get_db)):
    access, raw = await service.login(db, data)
    set_refresh_cookie(response, raw)
    return TokenOut(access_token=access)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/refresh", response_model=TokenOut)
async def refresh(
    response: Response, refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)
):
    if not refresh_token:
        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
    access, raw = await service.refresh(db, refresh_token)
    set_refresh_cookie(response, raw)
    return TokenOut(access_token=access)


@router.post("/auth/logout", status_code=204)
async def logout(refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    if refresh_token:
        await service.logout(db, refresh_token)
    resp = Response(status_code=204)
    resp.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    return resp
```

- [x] **Bước 6: Chạy test**

```bash
uv run pytest tests/test_email.py -q -k "register_sends or verify_rejects or resend or me_reports or send_pending"
uv run pytest -q --ignore=tests/test_email.py
```

Expected: 5 passed; phần còn lại vẫn 628 passed.

- [x] **Bước 7: Commit**

```bash
git add backend && git commit -m "feat(api): email verification on sign-up with resend and rate limit"
```

---

## Task 11: Email từ thao tác admin, gửi lại yêu cầu duyệt, CSV, phản hồi 👎

**Files:**
- Modify: `backend/app/modules/admin/{schemas,service,router}.py`, `backend/app/modules/analytics/{schemas,service,router}.py`

- [x] **Bước 1: `app/modules/admin/schemas.py`**

`AdminUserOut` thêm ngay dưới `review_note`:

```python
    email_verified: bool
```

`AdminStats` thêm ngay dưới `failed_jobs_7d`:

```python
    tutor_downvotes_7d: int  # câu trả lời AI bị học viên bấm 👎 trong 7 ngày
```

- [x] **Bước 2: `app/modules/admin/service.py`** (thay toàn bộ)

```python
import csv
import io
import uuid
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.core.time import utcnow
from app.modules.admin.models import AdminAction
from app.modules.admin.schemas import (
    AdminActionOut,
    AdminActionPage,
    AdminCourseOut,
    AdminCoursePage,
    AdminStats,
    AdminUserOut,
    AdminUserPage,
    DayCount,
)
from app.modules.auth.models import RefreshToken, Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.enrollment.models import Enrollment
from app.modules.jobs.models import Job, JobStatus
from app.modules.notify import templates
from app.modules.notify.outbox import queue_email
from app.modules.quiz.models import AttemptStatus, QuizAttempt
from app.modules.tutor.models import ChatMessage, ChatRole

VN_TZ = "Asia/Ho_Chi_Minh"
VN = ZoneInfo(VN_TZ)


def _log(
    db: AsyncSession,
    admin: User,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    label: str,
    note: str | None,
) -> None:
    db.add(
        AdminAction(
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=label,
            note=note,
        )
    )


def _like(q: str) -> str:
    return f"%{q.strip().lower()}%"


def _url(path: str) -> str:
    return f"{get_settings().app_base_url}{path}"


# Giảng viên chỉ vào hàng chờ duyệt khi đã xác nhận email (tránh hàng chờ đầy email giả).
_PENDING = (
    User.role == Role.teacher,
    User.teacher_status == TeacherStatus.pending,
    User.email_verified_at.is_not(None),
)


# ---------- người dùng ----------

_course_count = (
    select(func.count())
    .select_from(Course)
    .where(Course.teacher_id == User.id)
    .correlate(User)
    .scalar_subquery()
)
_enroll_count = (
    select(func.count())
    .select_from(Enrollment)
    .where(Enrollment.user_id == User.id)
    .correlate(User)
    .scalar_subquery()
)


def _user_out(user: User, course_count: int, enrollment_count: int) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        teacher_status=user.teacher_status,
        locked_at=user.locked_at,
        review_note=user.review_note,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
        course_count=course_count,
        enrollment_count=enrollment_count,
    )


def _users_stmt(role: Role | None, status: str | None, q: str | None) -> Select:
    stmt: Select = select(User, _course_count, _enroll_count)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if status == "pending":
        stmt = stmt.where(*_PENDING)
    elif status == "unverified":
        stmt = stmt.where(User.email_verified_at.is_(None))
    elif status in ("approved", "rejected"):
        stmt = stmt.where(User.role == Role.teacher, User.teacher_status == TeacherStatus(status))
    elif status == "locked":
        stmt = stmt.where(User.locked_at.is_not(None))
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
                User.email.like(pattern),
            )
        )
    # Chờ duyệt: ai đăng ký trước được xử lý trước. Còn lại: mới nhất lên đầu.
    order = User.created_at.asc() if status == "pending" else User.created_at.desc()
    return stmt.order_by(order, User.id)


async def list_users(
    db: AsyncSession, role: Role | None, status: str | None, q: str | None, params: PageParams
) -> AdminUserPage:
    total, paged = await paginate(db, _users_stmt(role, status, q), params)
    rows = (await db.execute(paged)).all()
    return AdminUserPage(
        items=[_user_out(u, cc, ec) for u, cc, ec in rows], total=total, page=params.page, size=params.size
    )


CSV_MAX_ROWS = 10_000
_ROLE_VI = {Role.student: "Học viên", Role.teacher: "Giảng viên", Role.admin: "Quản trị"}
_STATUS_VI = {
    TeacherStatus.pending: "Chờ duyệt",
    TeacherStatus.approved: "Đã duyệt",
    TeacherStatus.rejected: "Bị từ chối",
}


async def export_users_csv(db: AsyncSession, role: Role | None, status: str | None, q: str | None) -> str:
    """CSV theo đúng bộ lọc đang xem. Có BOM UTF-8 để Excel hiện đúng tiếng Việt."""
    rows = (await db.execute(_users_stmt(role, status, q).limit(CSV_MAX_ROWS))).all()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(
        [
            "Họ tên",
            "Email",
            "Vai trò",
            "Trạng thái giảng viên",
            "Đã xác nhận email",
            "Bị khóa",
            "Ngày tạo",
            "Số khóa",
            "Số đăng ký",
        ]
    )
    for u, cc, ec in rows:
        w.writerow(
            [
                u.full_name,
                u.email,
                _ROLE_VI[u.role],
                _STATUS_VI.get(u.teacher_status, "") if u.teacher_status else "",
                "Có" if u.email_verified_at else "Chưa",
                "Có" if u.locked_at else "",
                u.created_at.astimezone(VN).strftime("%d/%m/%Y %H:%M"),
                cc if u.role == Role.teacher else "",
                ec if u.role == Role.student else "",
            ]
        )
    return buf.getvalue()


async def _get_user_row(db: AsyncSession, user_id: uuid.UUID) -> AdminUserOut:
    row = (await db.execute(select(User, _course_count, _enroll_count).where(User.id == user_id))).one()
    return _user_out(*row)


async def _get_teacher(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.role != Role.teacher:
        raise not_found("Giảng viên")
    return user


async def approve_teacher(db: AsyncSession, admin: User, user_id: uuid.UUID) -> AdminUserOut:
    """Duyệt giảng viên đang chờ hoặc đã bị từ chối trước đó (đổi ý)."""
    user = await _get_teacher(db, user_id)
    if user.teacher_status == TeacherStatus.approved:
        raise AppError("ALREADY_APPROVED", "Giảng viên này đã được duyệt", 409)
    user.teacher_status = TeacherStatus.approved
    user.review_note = None
    _log(db, admin, "approve_teacher", "user", user.id, user.email, None)
    queue_email(
        db, user.email, "teacher_approved", templates.teacher_approved(user.full_name, _url("/teach"))
    )
    await db.commit()
    return await _get_user_row(db, user.id)


async def reject_teacher(db: AsyncSession, admin: User, user_id: uuid.UUID, reason: str) -> AdminUserOut:
    """Chỉ từ chối được yêu cầu đang chờ. Giảng viên đã duyệt mà vi phạm thì khóa tài khoản."""
    user = await _get_teacher(db, user_id)
    if user.teacher_status != TeacherStatus.pending:
        raise AppError("NOT_PENDING", "Chỉ từ chối được giảng viên đang chờ duyệt", 409)
    user.teacher_status = TeacherStatus.rejected
    user.review_note = reason
    _log(db, admin, "reject_teacher", "user", user.id, user.email, reason)
    queue_email(
        db, user.email, "teacher_rejected", templates.teacher_rejected(user.full_name, reason, _url("/"))
    )
    await db.commit()
    return await _get_user_row(db, user.id)


async def lock_user(db: AsyncSession, admin: User, user_id: uuid.UUID, reason: str | None) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Người dùng")
    if user.role == Role.admin:
        raise AppError("CANNOT_LOCK_ADMIN", "Không thể khóa tài khoản quản trị viên", 409)
    if user.locked_at is None:
        user.locked_at = utcnow()
        user.review_note = reason
        # Thu hồi mọi phiên: refresh bị chặn ngay; access token còn hạn cũng bị deps chặn vì locked_at.
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        _log(db, admin, "lock_user", "user", user.id, user.email, reason)
        queue_email(db, user.email, "account_locked", templates.account_locked(user.full_name, reason))
        await db.commit()
    return await _get_user_row(db, user.id)


async def unlock_user(db: AsyncSession, admin: User, user_id: uuid.UUID) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise not_found("Người dùng")
    if user.locked_at is not None:
        user.locked_at = None
        # Lý do khóa không còn đúng nữa; lý do từ chối giảng viên (nếu có) thì giữ.
        if user.teacher_status != TeacherStatus.rejected:
            user.review_note = None
        _log(db, admin, "unlock_user", "user", user.id, user.email, None)
        await db.commit()
    return await _get_user_row(db, user.id)


# ---------- khóa học ----------

_lesson_count = (
    select(func.count())
    .select_from(Lesson)
    .join(Section, Section.id == Lesson.section_id)
    .where(Section.course_id == Course.id)
    .correlate(Course)
    .scalar_subquery()
)
_course_enroll_count = (
    select(func.count())
    .select_from(Enrollment)
    .where(Enrollment.course_id == Course.id)
    .correlate(Course)
    .scalar_subquery()
)


def _course_stmt() -> Select:
    return select(Course, User.full_name, User.email, _lesson_count, _course_enroll_count).join(
        User, User.id == Course.teacher_id
    )


def _course_out(row) -> AdminCourseOut:
    c, name, email, lessons, enrolls = row
    return AdminCourseOut(
        id=c.id,
        title=c.title,
        slug=c.slug,
        status=c.status,
        teacher_id=c.teacher_id,
        teacher_name=name,
        teacher_email=email,
        created_at=c.created_at,
        lesson_count=lessons,
        enrollment_count=enrolls,
        hidden_at=c.hidden_at,
        hidden_reason=c.hidden_reason,
    )


async def list_courses(
    db: AsyncSession, status: str | None, q: str | None, params: PageParams
) -> AdminCoursePage:
    """status: published | draft | hidden (đã bị admin ẩn). Không truyền = tất cả."""
    stmt = _course_stmt()
    if status == "hidden":
        stmt = stmt.where(Course.hidden_at.is_not(None))
    elif status in ("published", "draft"):
        stmt = stmt.where(Course.status == CourseStatus(status), Course.hidden_at.is_(None))
    if q and q.strip():
        pattern = _like(q)
        stmt = stmt.where(
            or_(
                func.immutable_unaccent(func.lower(Course.title)).like(func.immutable_unaccent(pattern)),
                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
            )
        )
    total, paged = await paginate(db, stmt.order_by(Course.created_at.desc(), Course.id), params)
    rows = (await db.execute(paged)).all()
    return AdminCoursePage(
        items=[_course_out(r) for r in rows], total=total, page=params.page, size=params.size
    )


async def _course_row(db: AsyncSession, course_id: uuid.UUID) -> AdminCourseOut:
    return _course_out((await db.execute(_course_stmt().where(Course.id == course_id))).one())


async def _mail_owner(db: AsyncSession, course: Course, template: str, build) -> None:
    teacher = await db.get(User, course.teacher_id)
    if teacher is not None:
        queue_email(db, teacher.email, template, build(teacher))


async def hide_course(db: AsyncSession, admin: User, course_id: uuid.UUID, reason: str) -> AdminCourseOut:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    if course.status != CourseStatus.published:
        raise AppError("COURSE_NOT_PUBLISHED", "Chỉ ẩn được khóa học đang xuất bản", 409)
    course.status = CourseStatus.archived
    course.hidden_at = utcnow()
    course.hidden_reason = reason
    _log(db, admin, "hide_course", "course", course.id, course.title, reason)
    await _mail_owner(
        db,
        course,
        "course_hidden",
        lambda t: templates.course_hidden(t.full_name, course.title, reason, _url(f"/teach/{course.slug}")),
    )
    await db.commit()
    return await _course_row(db, course.id)


async def unhide_course(db: AsyncSession, admin: User, course_id: uuid.UUID) -> AdminCourseOut:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    if course.hidden_at is None:
        raise AppError("COURSE_NOT_HIDDEN", "Khóa học này không bị ẩn", 409)
    course.status = CourseStatus.published
    course.hidden_at = None
    course.hidden_reason = None
    _log(db, admin, "unhide_course", "course", course.id, course.title, None)
    await _mail_owner(
        db,
        course,
        "course_unhidden",
        lambda t: templates.course_unhidden(t.full_name, course.title, _url(f"/courses/{course.slug}")),
    )
    await db.commit()
    return await _course_row(db, course.id)


# ---------- tổng quan & nhật ký ----------


async def stats(db: AsyncSession) -> AdminStats:
    now = utcnow()
    week_ago = now - timedelta(days=7)

    async def count(stmt) -> int:
        return int(await db.scalar(stmt) or 0)

    by_role = dict((await db.execute(select(User.role, func.count()).group_by(User.role))).all())
    by_status = dict(
        (
            await db.execute(
                select(Course.status, func.count()).where(Course.hidden_at.is_(None)).group_by(Course.status)
            )
        ).all()
    )
    vn_day = func.date(func.timezone(VN_TZ, User.created_at))
    today = await db.scalar(select(func.date(func.timezone(VN_TZ, func.now()))))
    first = today - timedelta(days=13)
    per_day = dict(
        (await db.execute(select(vn_day, func.count()).where(vn_day >= first).group_by(vn_day))).all()
    )
    days: list[date] = [first + timedelta(days=i) for i in range(14)]

    return AdminStats(
        students=by_role.get(Role.student, 0),
        teachers=by_role.get(Role.teacher, 0),
        pending_teachers=await count(select(func.count()).select_from(User).where(*_PENDING)),
        locked_users=await count(select(func.count()).select_from(User).where(User.locked_at.is_not(None))),
        courses_published=by_status.get(CourseStatus.published, 0),
        courses_draft=by_status.get(CourseStatus.draft, 0),
        courses_hidden=await count(
            select(func.count()).select_from(Course).where(Course.hidden_at.is_not(None))
        ),
        enrollments=await count(select(func.count()).select_from(Enrollment)),
        tutor_questions_7d=await count(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.role == ChatRole.user, ChatMessage.created_at >= week_ago)
        ),
        quiz_submissions_7d=await count(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.status != AttemptStatus.in_progress, QuizAttempt.submitted_at >= week_ago)
        ),
        failed_jobs_7d=await count(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.failed, Job.created_at >= week_ago)
        ),
        tutor_downvotes_7d=await count(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.role == ChatRole.assistant,
                ChatMessage.feedback == -1,
                ChatMessage.created_at >= week_ago,
            )
        ),
        signups_14d=[DayCount(day=d, count=per_day.get(d, 0)) for d in days],
    )


async def list_actions(db: AsyncSession, params: PageParams) -> AdminActionPage:
    stmt = select(AdminAction, User.full_name).outerjoin(User, User.id == AdminAction.admin_id)
    total, paged = await paginate(db, stmt.order_by(AdminAction.created_at.desc(), AdminAction.id), params)
    rows = (await db.execute(paged)).all()
    items = [
        AdminActionOut(
            id=a.id,
            admin_name=name,
            action=a.action,
            target_type=a.target_type,
            target_id=a.target_id,
            target_label=a.target_label,
            note=a.note,
            created_at=a.created_at,
        )
        for a, name in rows
    ]
    return AdminActionPage(items=items, total=total, page=params.page, size=params.size)
```

- [x] **Bước 3: `app/modules/admin/router.py`** (thay toàn bộ)

`/users/export` phải khai báo **trước** mọi route `/users/{user_id}/…`. Thực ra hiện chưa có `GET /users/{user_id}`, nhưng đặt trước cho an toàn.

```python
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_role
from app.core.pagination import PageParams, page_params
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminActionPage,
    AdminCourseOut,
    AdminCoursePage,
    AdminStats,
    AdminUserOut,
    AdminUserPage,
    OptionalReasonIn,
    ReasonIn,
)
from app.modules.analytics.schemas import TutorFeedbackPage
from app.modules.analytics.service import downvoted_answers
from app.modules.auth.models import Role, User
from app.modules.notify.outbox import MailKicker, get_mail_kicker

# Mọi route ở đây chỉ dành cho quản trị viên (người khác nhận 403 FORBIDDEN).
# Thao tác có gửi email (duyệt, từ chối, khóa, ẩn/hiện khóa) gọi kicker sau khi commit.
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
admin_only = require_role(Role.admin)
UserRole = Literal["student", "teacher", "admin"]
UserStatus = Literal["pending", "approved", "rejected", "locked", "unverified"]


@router.get("/stats", response_model=AdminStats)
async def get_stats(_: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    return await service.stats(db)


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    role: UserRole | None = None,
    status: UserStatus | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_users(db, Role(role) if role else None, status, q, params)


@router.get("/users/export", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
async def export_users(
    role: UserRole | None = None,
    status: UserStatus | None = None,
    q: str | None = Query(None, max_length=100),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    """CSV theo bộ lọc đang xem (tối đa 10.000 dòng)."""
    body = await service.export_users_csv(db, Role(role) if role else None, status, q)
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nguoi-dung.csv"'},
    )


@router.post("/teachers/{user_id}/approve", response_model=AdminUserOut)
async def approve_teacher(
    user_id: uuid.UUID,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.approve_teacher(db, admin, user_id)
    await kicker.kick()
    return out


@router.post("/teachers/{user_id}/reject", response_model=AdminUserOut)
async def reject_teacher(
    user_id: uuid.UUID,
    data: ReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.reject_teacher(db, admin, user_id, data.reason)
    await kicker.kick()
    return out


@router.post("/users/{user_id}/lock", response_model=AdminUserOut)
async def lock_user(
    user_id: uuid.UUID,
    data: OptionalReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.lock_user(db, admin, user_id, data.reason)
    await kicker.kick()
    return out


@router.post("/users/{user_id}/unlock", response_model=AdminUserOut)
async def unlock_user(
    user_id: uuid.UUID,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.unlock_user(db, admin, user_id)


@router.get("/courses", response_model=AdminCoursePage)
async def list_courses(
    status: Literal["published", "draft", "hidden"] | None = None,
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_courses(db, status, q, params)


@router.post("/courses/{course_id}/hide", response_model=AdminCourseOut)
async def hide_course(
    course_id: uuid.UUID,
    data: ReasonIn,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.hide_course(db, admin, course_id, data.reason)
    await kicker.kick()
    return out


@router.post("/courses/{course_id}/unhide", response_model=AdminCourseOut)
async def unhide_course(
    course_id: uuid.UUID,
    admin: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
    kicker: MailKicker = Depends(get_mail_kicker),
):
    out = await service.unhide_course(db, admin, course_id)
    await kicker.kick()
    return out


@router.get("/actions", response_model=AdminActionPage)
async def list_actions(
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_actions(db, params)


@router.get("/tutor-feedback", response_model=TutorFeedbackPage)
async def tutor_feedback(
    params: PageParams = Depends(page_params),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    """Câu trả lời AI Tutor bị học viên bấm 👎 trên mọi khóa, mới nhất trước (kèm tên học viên)."""
    return await downvoted_answers(db, params, with_student=True)
```

- [x] **Bước 4: Phản hồi 👎** (`app/modules/analytics`)

`schemas.py`:

- Thêm `from datetime import datetime` và `from app.core.pagination import Page`.
- Thêm ở cuối:

```python
class TutorFeedbackItem(BaseModel):
    """Một câu trả lời AI Tutor bị học viên bấm 👎 (D1), kèm câu hỏi ngay trước nó."""

    message_id: uuid.UUID
    question: str | None
    answer: str
    refused: bool
    created_at: datetime
    course_id: uuid.UUID
    course_title: str
    course_slug: str
    lesson_id: uuid.UUID | None
    lesson_title: str | None
    student_name: str | None  # chỉ trả cho admin; giảng viên không thấy ai chê (để học viên dám bấm)


class TutorFeedbackPage(Page[TutorFeedbackItem]):
    pass
```

`service.py`:

- Import thêm: `uuid`, `aliased` (`sqlalchemy.orm`), `PageParams` và `paginate` (`app.core.pagination`), `TutorFeedbackItem` và `TutorFeedbackPage`, `User`.
- Thêm ở cuối:

```python
async def downvoted_answers(
    db: AsyncSession, params: PageParams, course_id: uuid.UUID | None = None, with_student: bool = False
) -> TutorFeedbackPage:
    """Câu trả lời bị bấm 👎, mới nhất trước. course_id=None: mọi khóa (admin)."""
    question_msg = aliased(ChatMessage)
    question = (
        select(question_msg.content)
        .where(
            question_msg.session_id == ChatMessage.session_id,
            question_msg.role == ChatRole.user,
            question_msg.created_at <= ChatMessage.created_at,
        )
        .order_by(question_msg.created_at.desc(), question_msg.id.desc())
        .limit(1)
        .correlate(ChatMessage)
        .scalar_subquery()
    )
    stmt = (
        select(
            ChatMessage,
            question,
            Course.id,
            Course.title,
            Course.slug,
            Lesson.id,
            Lesson.title,
            User.full_name,
        )
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .join(Course, Course.id == ChatSession.course_id)
        .join(User, User.id == ChatSession.user_id)
        .outerjoin(Lesson, Lesson.id == ChatSession.lesson_id)
        .where(ChatMessage.role == ChatRole.assistant, ChatMessage.feedback == -1)
    )
    if course_id is not None:
        stmt = stmt.where(ChatSession.course_id == course_id)
    total, paged = await paginate(db, stmt.order_by(ChatMessage.created_at.desc(), ChatMessage.id), params)
    rows = (await db.execute(paged)).all()
    items = [
        TutorFeedbackItem(
            message_id=m.id,
            question=q,
            answer=m.content,
            refused=m.refused,
            created_at=m.created_at,
            course_id=cid,
            course_title=ctitle,
            course_slug=slug,
            lesson_id=lid,
            lesson_title=ltitle,
            student_name=student if with_student else None,
        )
        for m, q, cid, ctitle, slug, lid, ltitle, student in rows
    ]
    return TutorFeedbackPage(items=items, total=total, page=params.page, size=params.size)
```

`router.py`:

- Import `PageParams`, `page_params`, `TutorFeedbackPage`.
- Thêm ở cuối:

```python
@router.get("/courses/{course_id}/tutor-feedback", response_model=TutorFeedbackPage)
async def course_tutor_feedback(
    course_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Câu trả lời AI Tutor bị học viên chê trong khóa (không kèm tên học viên)."""
    course = await get_owned_course(db, course_id, user)
    return await service.downvoted_answers(db, params, course.id)
```

- [x] **Bước 5: Chạy test**

```bash
uv run pytest tests/test_email.py tests/test_admin.py -q
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Expected: 27 passed (10 + 17); toàn bộ **638 passed**; ruff sạch.

- [x] **Bước 6: Thử với Mailpit**

```bash
docker compose up -d --build api worker mailpit
```

Đăng ký một tài khoản ở `http://localhost:3000/register` (frontend cũ vẫn gọi được API; nó sẽ báo lỗi ở bước tự đăng nhập, đúng như mong đợi). Mở `http://localhost:8025`: thấy email "Xác nhận email đăng ký LMS-AI" trong vòng vài giây.

- [x] **Bước 7: Commit**

```bash
git add backend && git commit -m "feat(api): admin notification emails, teacher re-request, users CSV export, tutor downvote inbox"
```

---

## Task 12: Frontend: đăng ký, đăng nhập, trang xác nhận email

**Files:**
- Modify: `frontend/src/lib/api/schema.d.ts` (sinh lại), `frontend/src/lib/auth/auth-context.tsx`, `frontend/src/app/(auth)/register/register-form.tsx`, `frontend/src/app/(auth)/login/login-form.tsx`
- Create: `frontend/src/lib/auth/email-verification.ts` (+test), `frontend/src/components/auth/resend-verification.tsx`, `frontend/src/components/auth/check-email.tsx`, `frontend/src/app/(auth)/verify-email/page.tsx`, `verify-email.tsx`

- [x] **Bước 1: Sinh lại kiểu API**

```bash
npm run gen:api
```

Expected: chỉ thêm dòng (các route `verify-email`, `resend-verification`, `teacher-request`, `users/export`, `tutor-feedback`; trường `email_verified`, `tutor_downvotes_7d`).

- [x] **Bước 2: `reloadUser` trong auth context** (`src/lib/auth/auth-context.tsx`)

Thêm vào kiểu `AuthValue`:

```tsx
  /** Tải lại /me sau khi trạng thái tài khoản đổi (vd. gửi lại yêu cầu duyệt giảng viên). */
  reloadUser: () => Promise<User>;
```

và trong `useMemo`:

```tsx
    () => ({ user, userId, status, login, register, logout, reloadUser: loadMe }),
    [user, userId, status, login, register, logout, loadMe],
```

- [x] **Bước 3: Viết test (sẽ fail)** (`src/lib/auth/email-verification.test.ts`)

```ts
import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { resendErrorMessage } from "./email-verification";

describe("resendErrorMessage", () => {
  it("429: báo số phút phải chờ (làm tròn lên, ít nhất 1 phút)", () => {
    const err = (s: number | null) => new ApiError(429, "RATE_LIMITED", "x", null, {}, s);
    expect(resendErrorMessage(err(1500))).toContain("khoảng 25 phút");
    expect(resendErrorMessage(err(10))).toContain("khoảng 1 phút");
    expect(resendErrorMessage(err(null))).toContain("khoảng 1 phút");
  });
  it("lỗi khác: giữ thông báo của lỗi", () => {
    expect(resendErrorMessage(new Error("Mất mạng"))).toBe("Mất mạng");
  });
});
```

- [x] **Bước 4: `src/lib/auth/email-verification.ts`**

```ts
"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

/** Gửi lại email xác nhận. API luôn trả 202 (không lộ email nào đã đăng ký); 429 khi gửi quá 3 lần/giờ. */
export function useResendVerification() {
  return useMutation({
    mutationFn: (email: string) => unwrap(api.POST("/api/v1/auth/resend-verification", { body: { email } })),
  });
}

/** Xác nhận email bằng token trong link. Chỉ gửi một lần cho mỗi token (không thử lại, không tải lại). */
export function useVerifyEmail(token: string | null) {
  return useQuery({
    queryKey: ["verify-email", token],
    queryFn: () => unwrap(api.POST("/api/v1/auth/verify-email", { body: { token: token! } })),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function resendErrorMessage(err: unknown) {
  if (err instanceof ApiError && err.status === 429) {
    const minutes = Math.max(1, Math.ceil((err.retryAfter ?? 60) / 60));
    return `Bạn đã yêu cầu gửi lại quá nhiều lần. Thử lại sau khoảng ${minutes} phút.`;
  }
  return err instanceof Error ? err.message : "Không gửi lại được email";
}
```

> `useVerifyEmail` dùng `useQuery` (không gọi API trong `useEffect`): mỗi token chỉ gửi đúng một lần kể cả khi React Strict Mode chạy effect hai lần, và tránh luật eslint `set-state-in-effect`.

- [x] **Bước 5: Component**

`src/components/auth/resend-verification.tsx`:

```tsx
"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { resendErrorMessage, useResendVerification } from "@/lib/auth/email-verification";

/** Nút "Gửi lại email xác nhận" có thông báo kết quả ngay bên dưới (role=status để trình đọc màn hình đọc). */
export function ResendVerification({ email, variant = "outline" }: { email: string; variant?: "outline" | "link" }) {
  const resend = useResendVerification();
  const [message, setMessage] = React.useState<{ ok: boolean; text: string } | null>(null);

  async function send() {
    setMessage(null);
    try {
      await resend.mutateAsync(email);
      setMessage({ ok: true, text: `Đã gửi lại. Kiểm tra hộp thư ${email} (cả mục Spam).` });
    } catch (err) {
      setMessage({ ok: false, text: resendErrorMessage(err) });
    }
  }

  return (
    <div className="space-y-2">
      <Button type="button" variant={variant} className={variant === "outline" ? "w-full" : undefined} onClick={send} loading={resend.isPending} loadingText="Đang gửi…">
        Gửi lại email xác nhận
      </Button>
      <p role="status" className={message ? (message.ok ? "text-sm text-muted-foreground" : "text-sm text-destructive") : "sr-only"}>
        {message?.text ?? ""}
      </p>
    </div>
  );
}
```

`src/components/auth/check-email.tsx`:

```tsx
"use client";

import { MailCheck } from "lucide-react";
import Link from "next/link";
import { ResendVerification } from "./resend-verification";

/** Màn sau khi đăng ký: chưa đăng nhập được cho tới khi bấm link trong email. */
export function CheckEmail({ email, teacher }: { email: string; teacher: boolean }) {
  return (
    <div className="text-center">
      <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
      <h1 className="mt-3 text-2xl font-semibold">Kiểm tra hộp thư của bạn</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Chúng tôi đã gửi link xác nhận tới <span className="font-medium text-foreground">{email}</span>. Bấm link trong
        email để kích hoạt tài khoản (link có hiệu lực 24 giờ).
      </p>
      {teacher ? (
        <p className="mt-2 text-sm text-muted-foreground">Sau khi xác nhận email, tài khoản giảng viên sẽ chờ quản trị viên duyệt.</p>
      ) : null}
      <div className="mt-6 text-left">
        <p className="mb-2 text-sm text-muted-foreground">Không thấy email? Xem trong mục Spam, hoặc:</p>
        <ResendVerification email={email} />
      </div>
      <p className="mt-6 text-sm text-muted-foreground">
        Đã xác nhận?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">
          Đăng nhập
        </Link>
      </p>
    </div>
  );
}
```

- [x] **Bước 6: Đăng ký** (`src/app/(auth)/register/register-form.tsx`, thay toàn bộ)

Đăng ký xong **không tự đăng nhập** nữa, mà hiện màn "Kiểm tra hộp thư".

```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import * as React from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { CheckEmail } from "@/components/auth/check-email";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";

const schema = z.object({
  full_name: z.string().trim().min(1, "Nhập họ tên").max(120),
  email: z.email("Email không hợp lệ"),
  password: z.string().min(8, "Mật khẩu ít nhất 8 ký tự").max(128),
  role: z.enum(["student", "teacher"]),
});
type Values = z.infer<typeof schema>;

export function RegisterForm() {
  const { register: signup } = useAuth();
  // Đăng ký xong chưa đăng nhập được: phải bấm link xác nhận trong email trước.
  const [sent, setSent] = React.useState<{ email: string; teacher: boolean } | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", password: "", role: "student" },
  });
  const { errors, isSubmitting } = form.formState;
  const role = useWatch({ control: form.control, name: "role" });

  async function onSubmit(values: Values) {
    try {
      await signup(values);
      setSent({ email: values.email.trim().toLowerCase(), teacher: values.role === "teacher" });
    } catch (err) {
      if (err instanceof ApiError && err.code === "EMAIL_TAKEN") {
        form.setError("email", { message: err.message }, { shouldFocus: true });
      } else {
        form.setError("root", { message: errorMessage(err) });
      }
    }
  }

  if (sent) return <CheckEmail email={sent.email} teacher={sent.teacher} />;

  return (
    <>
      <h1 className="text-2xl font-semibold">Tạo tài khoản</h1>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Bạn là</legend>
          <div role="radiogroup" className="grid grid-cols-2 gap-2">
            {(["student", "teacher"] as const).map((r) => (
              <label
                key={r}
                className={cn(
                  "flex h-11 cursor-pointer items-center justify-center rounded-md border text-sm",
                  role === r && "border-primary bg-primary/10 font-medium text-primary",
                )}
              >
                <input type="radio" value={r} className="sr-only" {...form.register("role")} />
                {r === "student" ? "Học viên" : "Giảng viên"}
              </label>
            ))}
          </div>
        </fieldset>
        <Field id="full_name" label="Họ và tên" error={errors.full_name?.message}>
          <Input autoComplete="name" {...form.register("full_name")} />
        </Field>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Field id="password" label="Mật khẩu" error={errors.password?.message} hint="Ít nhất 8 ký tự">
          <Input type="password" autoComplete="new-password" {...form.register("password")} />
        </Field>
        {errors.root ? (
          <p role="alert" className="text-sm text-destructive">
            {errors.root.message}
          </p>
        ) : null}
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting} loadingText="Đang tạo tài khoản…">
          Tạo tài khoản
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Đã có tài khoản?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">
          Đăng nhập
        </Link>
      </p>
    </>
  );
}
```

- [x] **Bước 7: Đăng nhập** (`src/app/(auth)/login/login-form.tsx`, thay toàn bộ)

```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ResendVerification } from "@/components/auth/resend-verification";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNext } from "@/lib/auth/safe-next";

const schema = z.object({
  email: z.email("Email không hợp lệ"),
  password: z.string().min(1, "Nhập mật khẩu"),
});
type Values = z.infer<typeof schema>;

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });
  const { errors, isSubmitting } = form.formState;
  // Email đúng mật khẩu nhưng chưa xác nhận: hiện nút gửi lại link cho đúng email đó.
  const [unverified, setUnverified] = React.useState<string | null>(null);

  async function onSubmit(values: Values) {
    setUnverified(null);
    try {
      const user = await login(values.email, values.password);
      const fallback = user.role === "student" ? "/" : user.role === "admin" ? "/admin" : "/teach";
      router.replace(safeNext(params.get("next"), fallback));
    } catch (err) {
      if (err instanceof ApiError && err.code === "EMAIL_NOT_VERIFIED") {
        setUnverified(values.email.trim().toLowerCase());
        return;
      }
      // sai mật khẩu: báo ngay dưới ô mật khẩu và đưa con trỏ về đó (design-system §5.3)
      const msg = err instanceof ApiError && err.status === 401 ? "Email hoặc mật khẩu không đúng" : errorMessage(err);
      form.setError("password", { message: msg }, { shouldFocus: true });
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Đăng nhập</h1>
      <p className="mt-1 text-sm text-muted-foreground">Tiếp tục buổi học của bạn.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Field id="password" label="Mật khẩu" error={errors.password?.message}>
          <Input type="password" autoComplete="current-password" {...form.register("password")} />
        </Field>
        {unverified ? (
          <div role="alert" className="space-y-3 rounded-md border border-accent/60 p-3 text-sm">
            <p>Bạn cần xác nhận email trước khi đăng nhập. Mở email chúng tôi đã gửi tới {unverified} và bấm link xác nhận.</p>
            <ResendVerification email={unverified} />
          </div>
        ) : null}
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting} loadingText="Đang đăng nhập…">
          Đăng nhập
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Chưa có tài khoản?{" "}
        <Link href={`/register${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`} className="font-medium text-primary underline underline-offset-4">
          Đăng ký
        </Link>
      </p>
    </>
  );
}
```

- [x] **Bước 8: Trang `/verify-email`**

`src/app/(auth)/verify-email/page.tsx`:

```tsx
import { Suspense } from "react";
import { VerifyEmail } from "./verify-email";

export const metadata = { title: "Xác nhận email" };

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmail />
    </Suspense>
  );
}
```

`src/app/(auth)/verify-email/verify-email.tsx`:

```tsx
"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { resendErrorMessage, useResendVerification, useVerifyEmail } from "@/lib/auth/email-verification";

export function VerifyEmail() {
  const token = useSearchParams().get("token");
  const verify = useVerifyEmail(token);

  if (token && verify.isPending)
    return (
      <div aria-busy="true" aria-label="Đang xác nhận email" className="space-y-3">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-16 w-full" />
      </div>
    );

  if (verify.isSuccess) {
    const teacherWaiting = verify.data.role === "teacher" && verify.data.teacher_status === "pending";
    return (
      <div className="text-center">
        <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
        <h1 className="mt-3 text-2xl font-semibold">Email đã được xác nhận</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {teacherWaiting
            ? "Bạn đã đăng nhập được. Tài khoản giảng viên đang chờ quản trị viên duyệt, bạn sẽ nhận email khi có kết quả."
            : "Tài khoản đã được kích hoạt. Bạn có thể đăng nhập ngay."}
        </p>
        <Button asChild size="lg" className="mt-6 w-full">
          <Link href="/login">Đăng nhập</Link>
        </Button>
      </div>
    );
  }

  const expired = verify.error instanceof ApiError && verify.error.code === "TOKEN_EXPIRED";
  return (
    <div>
      <XCircle className="mx-auto size-10 text-destructive" aria-hidden />
      <h1 className="mt-3 text-center text-2xl font-semibold">{expired ? "Link đã hết hạn" : "Link không dùng được"}</h1>
      <p className="mt-2 text-center text-sm text-muted-foreground">
        {token ? errorMessage(verify.error) : "Thiếu mã xác nhận trong link."} Nhập email để nhận link mới.
      </p>
      <ResendForm />
    </div>
  );
}

function ResendForm() {
  const resend = useResendVerification();
  const [email, setEmail] = React.useState("");
  const [message, setMessage] = React.useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = email.trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(value)) return setMessage({ ok: false, text: "Email không hợp lệ" });
    try {
      await resend.mutateAsync(value);
      setMessage({ ok: true, text: `Nếu ${value} đã đăng ký và chưa xác nhận, link mới đã được gửi tới hộp thư.` });
    } catch (err) {
      setMessage({ ok: false, text: resendErrorMessage(err) });
    }
  }

  return (
    <form className="mt-6 space-y-3" onSubmit={submit} noValidate>
      <Field id="resend-email" label="Email đã đăng ký">
        <Input type="email" autoComplete="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Button type="submit" variant="outline" className="w-full" loading={resend.isPending} loadingText="Đang gửi…">
        Gửi link xác nhận mới
      </Button>
      <p role="status" className={message ? (message.ok ? "text-sm text-muted-foreground" : "text-sm text-destructive") : "sr-only"}>
        {message?.text ?? ""}
      </p>
    </form>
  );
}
```

- [x] **Bước 9: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test
git add frontend && git commit -m "feat(web): sign-up email verification flow (check inbox, resend, verify page)"
```

---

## Task 13: Frontend: admin (CSV, chưa xác nhận, 👎), gửi lại yêu cầu duyệt

**Files:**
- Modify: `frontend/src/lib/admin-queries.ts`, `frontend/src/components/admin/{user-table,overview}.tsx`, `frontend/src/app/(main)/admin/users/page.tsx`, `frontend/src/app/(main)/page.tsx`, `frontend/src/lib/quiz/queries.ts`, `frontend/src/components/teach/course-analytics.tsx`
- Create: `frontend/src/components/admin/feedback-list.tsx`, `frontend/src/app/(main)/admin/feedback/page.tsx`

- [x] **Bước 1: `src/lib/admin-queries.ts`** (thay toàn bộ)

```ts
"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type AdminStats = components["schemas"]["AdminStats"];
export type AdminUser = components["schemas"]["AdminUserOut"];
export type AdminCourse = components["schemas"]["AdminCourseOut"];
export type AdminAction = components["schemas"]["AdminActionOut"];
export type TutorFeedback = components["schemas"]["TutorFeedbackItem"];

export type UserFilter = {
  role?: "student" | "teacher" | "admin";
  status?: "pending" | "approved" | "rejected" | "locked" | "unverified";
  q?: string;
  page: number;
};
export type CourseFilter = { status?: "published" | "draft" | "hidden"; q?: string; page: number };

/** Mọi khóa của khu quản trị bắt đầu bằng "admin": một thao tác xong thì làm mới cả khu (số liệu, danh sách, nhật ký). */
const ADMIN = ["admin"] as const;
export const adminKeys = {
  all: ADMIN,
  stats: [...ADMIN, "stats"] as const,
  users: (f: UserFilter) => [...ADMIN, "users", f] as const,
  courses: (f: CourseFilter) => [...ADMIN, "courses", f] as const,
  actions: (page: number) => [...ADMIN, "actions", page] as const,
  feedback: (page: number) => [...ADMIN, "feedback", page] as const,
};

export const PAGE_SIZE = 20;

export function useAdminStats() {
  return useQuery({ queryKey: adminKeys.stats, queryFn: () => unwrap(api.GET("/api/v1/admin/stats")) });
}

export function useAdminUsers(f: UserFilter) {
  return useQuery({
    queryKey: adminKeys.users(f),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/users", {
          params: { query: { role: f.role, status: f.status, q: f.q || undefined, page: f.page, size: PAGE_SIZE } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useAdminCourses(f: CourseFilter) {
  return useQuery({
    queryKey: adminKeys.courses(f),
    queryFn: () =>
      unwrap(api.GET("/api/v1/admin/courses", { params: { query: { status: f.status, q: f.q || undefined, page: f.page, size: PAGE_SIZE } } })),
    placeholderData: keepPreviousData,
  });
}

export function useAdminActions(page: number, size = PAGE_SIZE) {
  return useQuery({
    queryKey: [...adminKeys.actions(page), size],
    queryFn: () => unwrap(api.GET("/api/v1/admin/actions", { params: { query: { page, size } } })),
    placeholderData: keepPreviousData,
  });
}

export function useAdminTutorFeedback(page: number, size = PAGE_SIZE) {
  return useQuery({
    queryKey: [...adminKeys.feedback(page), size],
    queryFn: () => unwrap(api.GET("/api/v1/admin/tutor-feedback", { params: { query: { page, size } } })),
    placeholderData: keepPreviousData,
  });
}

/** Tải CSV theo đúng bộ lọc đang xem (qua API client để có token và tự refresh). */
export async function downloadUsersCsv(f: Omit<UserFilter, "page">) {
  const blob = await unwrap(
    api.GET("/api/v1/admin/users/export", { params: { query: { role: f.role, status: f.status, q: f.q || undefined } }, parseAs: "blob" }),
  );
  const url = URL.createObjectURL(blob as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nguoi-dung-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function useAdminMutation<A>(fn: (a: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ADMIN }) });
}

const uid = (id: string) => ({ params: { path: { user_id: id } } });
const cid = (id: string) => ({ params: { path: { course_id: id } } });

export function useAdminActionsMutations() {
  return {
    approve: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/teachers/{user_id}/approve", uid(id)))),
    reject: useAdminMutation(({ id, reason }: { id: string; reason: string }) =>
      unwrap(api.POST("/api/v1/admin/teachers/{user_id}/reject", { ...uid(id), body: { reason } })),
    ),
    lock: useAdminMutation(({ id, reason }: { id: string; reason?: string }) =>
      unwrap(api.POST("/api/v1/admin/users/{user_id}/lock", { ...uid(id), body: { reason: reason || null } })),
    ),
    unlock: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/users/{user_id}/unlock", uid(id)))),
    hide: useAdminMutation(({ id, reason }: { id: string; reason: string }) =>
      unwrap(api.POST("/api/v1/admin/courses/{course_id}/hide", { ...cid(id), body: { reason } })),
    ),
    unhide: useAdminMutation((id: string) => unwrap(api.POST("/api/v1/admin/courses/{course_id}/unhide", cid(id)))),
  };
}

const ACTION_LABEL: Record<string, string> = {
  approve_teacher: "Duyệt giảng viên",
  reject_teacher: "Từ chối giảng viên",
  lock_user: "Khóa tài khoản",
  unlock_user: "Mở khóa tài khoản",
  hide_course: "Ẩn khóa học",
  unhide_course: "Hiện lại khóa học",
};
export const actionLabel = (a: string) => ACTION_LABEL[a] ?? a;

const dateFmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Ho_Chi_Minh" });
const timeFmt = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
export const fmtDate = (iso: string) => dateFmt.format(new Date(iso));
export const fmtDateTime = (iso: string) => timeFmt.format(new Date(iso));
```

> `downloadUsersCsv` đi qua API client (`parseAs: "blob"`), nên vẫn có token và tự refresh khi gặp 401. Nếu dùng `<a href>` thẳng tới API thì không gửi được header `Authorization`.

- [x] **Bước 2: Huy hiệu "Chưa xác nhận email"** (`src/components/admin/user-table.tsx`, trong `UserStatus`, ngay sau dòng `locked_at`)

```tsx
  if (!user.email_verified) return <Badge>Chưa xác nhận email</Badge>;
```

- [x] **Bước 3: Trang Người dùng** (`src/app/(main)/admin/users/page.tsx`, thay toàn bộ)

Thêm tab "Chưa xác nhận email" và nút **Xuất CSV** (xuất đúng tab và từ khóa đang xem).

```tsx
"use client";

import { Download, Search, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { FilterTabs } from "@/components/admin/filter-tabs";
import { UserTable } from "@/components/admin/user-table";
import { Pagination } from "@/components/course/course-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { downloadUsersCsv, type UserFilter, useAdminUsers } from "@/lib/admin-queries";
import { errorMessage } from "@/lib/api/errors";
import { useDebounced } from "@/lib/use-debounced";

const TABS = [
  { value: "pending", label: "Chờ duyệt", filter: { role: "teacher", status: "pending" } },
  { value: "teacher", label: "Giảng viên", filter: { role: "teacher" } },
  { value: "student", label: "Học viên", filter: { role: "student" } },
  { value: "locked", label: "Đã khóa", filter: { status: "locked" } },
  { value: "unverified", label: "Chưa xác nhận email", filter: { status: "unverified" } },
  { value: "all", label: "Tất cả", filter: {} },
] as const satisfies readonly { value: string; label: string; filter: Omit<UserFilter, "page"> }[];
type Tab = (typeof TABS)[number]["value"];
const isTab = (v: string | null): v is Tab => TABS.some((t) => t.value === v);

export default function AdminUsersPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <UsersView />
    </React.Suspense>
  );
}

function UsersView() {
  const router = useRouter();
  const params = useSearchParams();
  const tabParam = params.get("tab");
  const tab: Tab = isTab(tabParam) ? tabParam : "pending";
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  // đổi tab hoặc từ khóa thì về trang 1
  const [paging, setPaging] = React.useState({ key: "", page: 1 });
  const key = `${tab}|${query}`;
  const page = paging.key === key ? paging.page : 1;
  const filter = TABS.find((t) => t.value === tab)!.filter;
  const users = useAdminUsers({ ...filter, q: query, page });
  const [exporting, setExporting] = React.useState(false);

  async function exportCsv() {
    setExporting(true);
    try {
      await downloadUsersCsv({ ...filter, q: query });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Người dùng"
        actions={
          <Button variant="outline" onClick={exportCsv} loading={exporting} loadingText="Đang xuất…">
            <Download /> Xuất CSV
          </Button>
        }
      >
        Duyệt giảng viên mới, tìm kiếm và khóa tài khoản vi phạm.
      </PageHeader>
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterTabs label="Lọc người dùng" value={tab} options={TABS.map(({ value, label }) => ({ value, label }))} onChange={(v) => router.replace(`/admin/users?tab=${v}`)} />
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="user-search" className="sr-only">
            Tìm người dùng
          </label>
          <Input id="user-search" type="search" placeholder="Tìm theo tên hoặc email…" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {users.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => users.refetch()} />
      ) : users.data.items.length === 0 ? (
        <EmptyState icon={Users} title={query ? `Không tìm thấy ai cho “${query}”.` : tab === "pending" ? "Không có giảng viên nào đang chờ duyệt." : "Chưa có người dùng nào."} />
      ) : (
        <div aria-busy={users.isFetching}>
          <UserTable users={users.data.items} caption={`Danh sách người dùng: ${TABS.find((t) => t.value === tab)!.label}`} />
          <Pagination page={page} total={users.data.total} size={users.data.size} onPage={(p) => setPaging({ key, page: p })} />
        </div>
      )}
    </>
  );
}
```

- [x] **Bước 4: Ô số liệu 👎** (`src/components/admin/overview.tsx`)

Import thêm `ThumbsDown`. Chèn ngay trước ô "Tác vụ AI lỗi":

```tsx
      <Tile icon={ThumbsDown} label="Trả lời AI bị chê (7 ngày)" value={s.tutor_downvotes_7d} href="/admin/feedback" sub="Xem câu hỏi và câu trả lời" />
```

- [x] **Bước 5: Danh sách 👎** (`src/components/admin/feedback-list.tsx`)

```tsx
"use client";

import { ThumbsDown } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/app/states";
import { Badge } from "@/components/ui/misc";
import { fmtDateTime, type TutorFeedback } from "@/lib/admin-queries";

/**
 * Câu trả lời AI Tutor bị học viên bấm 👎: câu hỏi, câu trả lời, nơi hỏi. Dùng chung cho admin (mọi khóa,
 * có tên học viên) và giảng viên (một khóa, không có tên để học viên dám bấm).
 */
export function FeedbackList({ items, showCourse }: { items: TutorFeedback[]; showCourse: boolean }) {
  if (items.length === 0) return <EmptyState icon={ThumbsDown} title="Chưa có câu trả lời nào bị chê." />;
  return (
    <ol className="space-y-3">
      {items.map((f) => (
        <li key={f.message_id} className="rounded-lg border bg-surface p-4">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            {showCourse ? (
              <Link href={`/courses/${f.course_slug}`} className="font-medium text-primary hover:underline">
                {f.course_title}
              </Link>
            ) : null}
            {f.lesson_title ? <span>· {f.lesson_title}</span> : <span>· Hỏi trên toàn khóa</span>}
            {f.student_name ? <span>· {f.student_name}</span> : null}
            <time dateTime={f.created_at}>· {fmtDateTime(f.created_at)}</time>
            {f.refused ? <Badge>AI đã từ chối trả lời</Badge> : null}
          </div>
          <p className="mt-2 text-sm">
            <span className="font-medium">Hỏi:</span> {f.question ?? "(không còn câu hỏi)"}
          </p>
          <details className="mt-1 text-sm">
            <summary className="cursor-pointer text-muted-foreground">Câu trả lời của AI</summary>
            <p className="mt-1 whitespace-pre-wrap">{f.answer}</p>
          </details>
        </li>
      ))}
    </ol>
  );
}
```

`src/app/(main)/admin/feedback/page.tsx`:

```tsx
"use client";

import * as React from "react";
import { ErrorState, PageHeader } from "@/components/app/states";
import { FeedbackList } from "@/components/admin/feedback-list";
import { Pagination } from "@/components/course/course-card";
import { Skeleton } from "@/components/ui/misc";
import { useAdminTutorFeedback } from "@/lib/admin-queries";

export default function AdminFeedbackPage() {
  const [page, setPage] = React.useState(1);
  const feedback = useAdminTutorFeedback(page);
  return (
    <>
      <PageHeader title="Câu trả lời AI bị chê">
        Học viên bấm 👎 ở AI Tutor. Dùng để tìm tài liệu thiếu, câu trả lời sai hoặc AI từ chối nhầm.
      </PageHeader>
      {feedback.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : feedback.isError ? (
        <ErrorState error={feedback.error} onRetry={() => feedback.refetch()} />
      ) : (
        <>
          <FeedbackList items={feedback.data.items} showCourse />
          <Pagination page={page} total={feedback.data.total} size={feedback.data.size} onPage={setPage} />
        </>
      )}
    </>
  );
}
```

- [x] **Bước 6: 👎 trong Thống kê của giảng viên**

`src/lib/quiz/queries.ts`, thêm ngay trước `useCourseAnalytics`:

```ts
/** Câu trả lời AI Tutor bị chê trong khóa (giảng viên; không có tên học viên). */
export function useCourseTutorFeedback(courseId: string | undefined) {
  return useQuery({
    queryKey: [...quizKeys.analytics(courseId ?? "none"), "tutor-feedback"],
    enabled: !!courseId,
    queryFn: () =>
      unwrap(api.GET("/api/v1/courses/{course_id}/tutor-feedback", { params: { path: { course_id: courseId! }, query: { size: 20 } } })),
  });
}
```

`src/components/teach/course-analytics.tsx`:

- Import `FeedbackList` từ `@/components/admin/feedback-list` và `useCourseTutorFeedback`.
- Ngay trước `</>` cuối của `CourseAnalyticsView` thêm `{course.data ? <TutorFeedbackSection courseId={course.data.id} /> : null}`.
- Thêm component:

```tsx
/** Câu trả lời AI bị học viên chê: gợi ý chỗ tài liệu còn thiếu hoặc khó hiểu. */
function TutorFeedbackSection({ courseId }: { courseId: string }) {
  const feedback = useCourseTutorFeedback(courseId);
  if (!feedback.data) return null;
  return (
    <section className="mt-10" aria-labelledby="feedback-title">
      <h2 id="feedback-title" className="mb-1 text-lg font-semibold">
        Câu trả lời AI bị học viên chê ({feedback.data.total})
      </h2>
      <p className="mb-3 text-sm text-muted-foreground">Gợi ý chỗ tài liệu còn thiếu hoặc khó hiểu. Tên học viên được ẩn.</p>
      <FeedbackList items={feedback.data.items} showCourse={false} />
    </section>
  );
}
```

- [x] **Bước 7: Gửi lại yêu cầu duyệt** (`src/app/(main)/page.tsx`, thay toàn bộ)

```tsx
"use client";

import { ArrowRight, Clock, Compass, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/app/states";
import { MyCourseList } from "@/components/course/my-course-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { api, unwrap } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { type User, useAuth } from "@/lib/auth/auth-context";

/** Tên gọi: chữ cuối của họ tên Việt ("Nguyễn Văn An" → "An"). */
const givenName = (fullName: string) => fullName.trim().split(/\s+/).slice(-1)[0] ?? fullName;

/** Giảng viên chưa được duyệt: nói rõ đang chờ hay đã bị từ chối (kèm lý do quản trị viên ghi). */
function TeacherReviewNotice({ user }: { user: User }) {
  const { reloadUser } = useAuth();
  const [sending, setSending] = React.useState(false);
  if (user.role !== "teacher" || user.teacher_status === "approved") return null;

  async function askAgain() {
    setSending(true);
    try {
      await unwrap(api.POST("/api/v1/me/teacher-request"));
      await reloadUser();
      toast.success("Đã gửi lại yêu cầu duyệt");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  const rejected = user.teacher_status === "rejected";
  const Icon = rejected ? XCircle : Clock;
  return (
    <div role="status" className="mb-6 flex gap-3 rounded-lg border p-4">
      <Icon className={rejected ? "mt-0.5 size-5 shrink-0 text-destructive" : "mt-0.5 size-5 shrink-0 text-accent"} aria-hidden />
      <div>
        <p className="font-medium">{rejected ? "Yêu cầu giảng dạy chưa được chấp nhận" : "Tài khoản giảng viên đang chờ duyệt"}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {rejected
            ? `Lý do: ${user.review_note ?? "không ghi"}. Bổ sung thông tin rồi gửi lại yêu cầu để được xem xét lại.`
            : "Quản trị viên sẽ duyệt sớm và báo kết quả qua email. Trong lúc chờ, bạn vẫn xem được các khóa học đã xuất bản."}
        </p>
        {rejected ? (
          <Button variant="outline" size="sm" className="mt-3" onClick={askAgain} loading={sending} loadingText="Đang gửi…">
            Gửi lại yêu cầu duyệt
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export default function HomePage() {
  const { user, status } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";
  // Quản trị viên không học cũng không dạy: trang chủ của họ là khu quản trị.
  React.useEffect(() => {
    if (isAdmin) router.replace("/admin");
  }, [isAdmin, router]);
  if (status === "loading" || isAdmin) return <Skeleton className="h-40 w-full" />;

  if (!user)
    return (
      <section className="mx-auto max-w-2xl py-10 text-center md:py-20">
        <h1 className="text-3xl font-semibold md:text-4xl">Học theo nhịp của bạn, có AI giải đáp ngay trong bài</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          AI Tutor trả lời dựa trên đúng tài liệu của khóa học và luôn ghi nguồn, để bạn kiểm chứng được.
        </p>
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/explore">
              <Compass /> Khám phá khóa học
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/register">Tạo tài khoản</Link>
          </Button>
        </div>
      </section>
    );

  // Chỉ giảng viên đã duyệt mới vào được /teach.
  const canTeach = user.role === "teacher" && user.teacher_status === "approved";

  return (
    <>
      <PageHeader title={`Chào ${givenName(user.full_name)}`}>
        {user.role === "student" ? "Tiếp tục từ chỗ bạn đã dừng." : canTeach ? "Quản lý các khóa bạn đang dạy." : "Chào mừng bạn đến với LMS-AI."}
      </PageHeader>
      <TeacherReviewNotice user={user} />
      {user.role === "student" ? (
        <>
          <MyCourseList limit={3} />
          <Button asChild variant="link" className="mt-4">
            <Link href="/my">
              Xem tất cả khóa của tôi <ArrowRight />
            </Link>
          </Button>
        </>
      ) : (
        <Button asChild>
          <Link href={canTeach ? "/teach" : "/explore"}>{canTeach ? "Tới khóa đang dạy" : "Khám phá khóa học"}</Link>
        </Button>
      )}
    </>
  );
}
```

- [x] **Bước 8: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test && npm run build
git add frontend && git commit -m "feat(web): users CSV export, unverified tab, tutor downvote inbox, teacher re-request"
```

Expected: **102 passed**. `next build` có thêm `○ /admin/feedback` và `○ /verify-email`.

---

## Task 14: E2E cho email, CSV, 👎

**Files:**
- Modify: `frontend/e2e/mock-api.ts`, `frontend/e2e/admin-data.ts`, `frontend/e2e/admin.spec.ts`
- Create: `frontend/e2e/auth-email.spec.ts`

- [x] **Bước 1: Mock mặc định**

`e2e/mock-api.ts`, thêm ngay dưới `"GET /quizzes"`, để trang Thống kê ở các test cũ không gọi vào route chưa mock:

```ts
    "GET /courses/*/tutor-feedback": (r) => json(r, { items: [], total: 0, page: 1, size: 20 }),
```

`e2e/admin-data.ts`, trong `stats()` thêm ngay dưới `failed_jobs_7d: 2,`:

```ts
  tutor_downvotes_7d: 3,
```

> Thiếu trường này thì trang Tổng quan **sập** (`undefined.toLocaleString`). E2E đã bắt được lỗi này.

- [x] **Bước 2: `e2e/auth-email.spec.ts`**

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { mockApi, teacher } from "./mock-api";

const err = (code: string, message: string) => ({ error: { code, message, details: {}, request_id: "rq-e2e" } });

test.describe("xác nhận email", () => {
  test("đăng ký xong thì phải kiểm tra hộp thư, gửi lại được link", async ({ page }) => {
    let resendBody: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/register": (r) => r.fulfill({ status: 201, json: { ...teacher, id: "u-5", email: "moi@sv.vn", role: "student", teacher_status: null, email_verified: false } }),
        "POST /auth/resend-verification": (r) => {
          resendBody = r.request().postDataJSON();
          return r.fulfill({ status: 202, json: { status: "accepted" } });
        },
      },
    });
    await page.goto("/register");
    await page.getByLabel("Họ và tên").fill("Nguyễn Văn Mới");
    await page.getByLabel("Email").fill("Moi@SV.vn");
    await page.getByLabel("Mật khẩu").fill("password123");
    await page.getByRole("button", { name: "Tạo tài khoản" }).click();

    await expect(page.getByRole("heading", { name: "Kiểm tra hộp thư của bạn" })).toBeVisible();
    await expect(page.getByText("moi@sv.vn")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByRole("button", { name: "Gửi lại email xác nhận" }).click();
    await expect(page.getByText(/Đã gửi lại/)).toBeVisible();
    expect(resendBody).toEqual({ email: "moi@sv.vn" });
  });

  test("đăng nhập khi chưa xác nhận: báo rõ và cho gửi lại; gửi quá nhiều thì báo thời gian chờ", async ({ page }) => {
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/login": (r) => r.fulfill({ status: 403, json: err("EMAIL_NOT_VERIFIED", "Bạn cần xác nhận email trước khi đăng nhập") }),
        "POST /auth/resend-verification": (r) =>
          r.fulfill({ status: 429, headers: { "Retry-After": "1500" }, json: err("RATE_LIMITED", "Bạn đã yêu cầu gửi lại quá nhiều lần") }),
      },
    });
    await page.goto("/login");
    await page.getByLabel("Email").fill("an@sv.vn");
    await page.getByLabel("Mật khẩu").fill("password123");
    await page.getByRole("button", { name: "Đăng nhập" }).click();
    const alert = page.getByRole("alert").filter({ hasText: "Bạn cần xác nhận email" });
    await expect(alert).toContainText("an@sv.vn");
    await alert.getByRole("button", { name: "Gửi lại email xác nhận" }).click();
    await expect(page.getByText(/Thử lại sau khoảng 25 phút/)).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("bấm link trong email: xác nhận thành công", async ({ page }) => {
    let body: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/verify-email": (r) => {
          body = r.request().postDataJSON();
          return r.fulfill({ json: { ...teacher, teacher_status: "pending", email_verified: true } });
        },
      },
    });
    await page.goto("/verify-email?token=abc123xyz789");
    await expect(page.getByRole("heading", { name: "Email đã được xác nhận" })).toBeVisible();
    await expect(page.getByText(/đang chờ quản trị viên duyệt/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Đăng nhập" }).last()).toHaveAttribute("href", "/login");
    expect(body).toEqual({ token: "abc123xyz789" });
    await expectAccessible(page);
  });

  test("link hết hạn: nhập email để nhận link mới", async ({ page }) => {
    let resendBody: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/verify-email": (r) => r.fulfill({ status: 400, json: err("TOKEN_EXPIRED", "Link xác nhận đã hết hạn, hãy gửi lại email xác nhận") }),
        "POST /auth/resend-verification": (r) => {
          resendBody = r.request().postDataJSON();
          return r.fulfill({ status: 202, json: { status: "accepted" } });
        },
      },
    });
    await page.goto("/verify-email?token=het-han-roi-123");
    await expect(page.getByRole("heading", { name: "Link đã hết hạn" })).toBeVisible();
    await page.getByLabel("Email đã đăng ký").fill("an@sv.vn");
    await page.getByRole("button", { name: "Gửi link xác nhận mới" }).click();
    await expect(page.getByText(/link mới đã được gửi/)).toBeVisible();
    expect(resendBody).toEqual({ email: "an@sv.vn" });
    await expectAccessible(page);
  });
});

test("giảng viên bị từ chối gửi lại yêu cầu duyệt", async ({ page }) => {
  let status = "rejected";
  await mockApi(page, {
    user: { ...teacher, teacher_status: "rejected" },
    extra: {
      "GET /me": (r) => r.fulfill({ json: { ...teacher, teacher_status: status, review_note: status === "rejected" ? "Thiếu minh chứng" : null } }),
      "POST /me/teacher-request": (r) => {
        status = "pending";
        return r.fulfill({ json: { ...teacher, teacher_status: "pending", review_note: null } });
      },
    },
  });
  await page.goto("/");
  await expect(page.getByText(/Lý do: Thiếu minh chứng/)).toBeVisible();
  await page.getByRole("button", { name: "Gửi lại yêu cầu duyệt" }).click();
  await expect(page.getByText("Tài khoản giảng viên đang chờ duyệt")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gửi lại yêu cầu duyệt" })).toHaveCount(0);
});
```

- [x] **Bước 3: Thêm cuối `e2e/admin.spec.ts`**

```ts
test.describe("quản trị viên: phản hồi AI và xuất CSV", () => {
  test("trang câu trả lời AI bị chê", async ({ page }) => {
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/tutor-feedback": (r) =>
          r.fulfill({
            json: pageOf([
              { message_id: "m1", question: "Đạo hàm của x² là gì?", answer: "Là x [1].", refused: false, created_at: "2026-10-06T03:00:00Z", course_id: "c", course_title: "Giải tích 1", course_slug: "giai-tich-1", lesson_id: "l", lesson_title: "Định nghĩa đạo hàm", student_name: "Nguyễn Văn An" },
            ]),
          }),
      },
    });
    await page.goto("/admin/feedback");
    await expect(page.getByText("Đạo hàm của x² là gì?")).toBeVisible();
    await expect(page.getByText("· Nguyễn Văn An")).toBeVisible();
    await page.getByText("Câu trả lời của AI").click();
    await expect(page.getByText("Là x [1].")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("xuất CSV theo tab đang xem", async ({ page }) => {
    let query = "";
    await mockApi(page, {
      user: admin,
      extra: {
        "GET /admin/users": (r) => r.fulfill({ json: pageOf([studentRow]) }),
        "GET /admin/users/export": (r, url) => {
          query = url.search;
          return r.fulfill({ status: 200, contentType: "text/csv; charset=utf-8", body: "﻿Họ tên,Email\nNguyễn Văn An,an@sv.vn\n" });
        },
      },
    });
    await page.goto("/admin/users?tab=student");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Xuất CSV" }).click();
    expect((await download).suggestedFilename()).toMatch(/^nguoi-dung-\d{4}-\d{2}-\d{2}\.csv$/);
    expect(query).toContain("role=student");
  });
});
```

- [x] **Bước 4: Chạy và commit**

```bash
npx playwright test
git add frontend/e2e && git commit -m "test(web): E2E for email verification, CSV export and tutor downvotes"
git push
```

Expected: **56 passed**; CI xanh.

---

# Phần 3: Sửa sau code review

Hai reviewer độc lập đã đọc code phần 1 và phần 2 (backend và frontend). Kết luận chung là "Ready to merge: With fixes", **không có lỗi Critical**. Hai task dưới đây sửa toàn bộ lỗi Important và một số lỗi Minor dễ sửa. Các lỗi còn lại được ghi ở cuối phần này.

**Đã chạy thử sau khi sửa:**

- Backend: **647 test pass** (638 + 9 mới trong `tests/test_review_fixes.py`). `alembic check` sạch; migration mới chạy lên / lùi được.
- Frontend: **102 unit test** pass. **62 test E2E** pass (31 kịch bản × 2 khung hình). `eslint`, `tsc`, `next build` sạch.

| # | Lỗi (reviewer tìm ra) | Mức | Cách sửa |
|---|---|---|---|
| B1 | `send_pending` gửi tới 20 mail trong **một** transaction. Job bị arq hủy giữa chừng (timeout 120s) thì rollback: mail đã gửi vẫn `pending` nên bị **gửi lại**, và `attempts` không tăng nên **gửi mãi** | Important | Nhận từng email rồi commit ngay (attempts + 1, hạn thuê 5 phút), gửi xong commit kết quả. Lỗi thì lùi dần (n phút). Mỗi lượt tối đa 5 mail (5 × 20s < 120s) |
| B2 | `review_note` dùng chung cho lý do từ chối và lý do khóa. Khóa giảng viên bị từ chối thì **đè** lý do từ chối; mở khóa thì "Spam" hiện thành lý do từ chối | Important | Cột riêng `users.lock_reason` (migration chuyển dữ liệu cũ sang) |
| B3 | Xuất CSV bị **chèn công thức**: họ tên `=HYPERLINK(...)` chạy được khi mở bằng Excel | Important | Ô bắt đầu bằng `= + - @ tab CR` được thêm `'` ở đầu |
| B4 | Tắt `EMAIL_VERIFICATION_REQUIRED` thì giảng viên **không bao giờ vào hàng chờ** và admin không được báo | Important | Điều kiện "đã xác nhận" chỉ áp khi cờ bật; cờ tắt thì báo admin ngay lúc đăng ký |
| B5 | Tiêu đề email có xuống dòng (tên khóa) → lỗi header, mail fail sau 5 lần | Minor | Gộp khoảng trắng trong subject |
| B6 | Token xác nhận nằm dạng rõ trong `email_outbox` mãi mãi | Minor | Xóa nội dung mail xác nhận sau khi gửi |
| B7 | Tìm kiếm `%` hoặc `_` khớp mọi thứ | Minor | Escape ký tự LIKE |
| B8 | Kicker chờ vài giây mỗi request khi Redis chết (arq thử kết nối lại 5 lần) | Minor | `conn_retries=0`, `conn_timeout=1` |
| B9 | Đăng ký không giới hạn (mỗi lần gửi 1 email ra ngoài); gửi lại chỉ giới hạn theo email | Minor | 20 lần đăng ký / giờ / IP; gửi lại 10 lần / giờ / IP |
| F1 | Mở link xác nhận trên trình duyệt **đang có phiên**: khôi phục phiên gọi `resetQueries` → POST xác nhận chạy **lần hai** → trang đổi từ "thành công" sang "Link không dùng được" | Important | Bỏ truy vấn `verify-email` khỏi `resetQueries` |
| F2 | Duyệt người cuối ở trang 2 → trang trống, không có phân trang để quay lại | Important | Trang > 1 mà trống thì có nút "Về trang đầu" (cả trang Khóa học) |
| F3 | Bấm đúp **Duyệt / Mở khóa** gửi 2 request (lỗi 409 ngay sau toast thành công) | Important | Chặn bằng ref (đổi ngay, không đợi render) + trạng thái đang xử lý |
| F4 | Sau khi đăng ký / xác nhận, focus rơi về `<body>`, trình đọc màn hình không đọc tiêu đề mới | Important | Focus vào tiêu đề mới |
| F5 | Tên file CSV lấy ngày UTC; thu hồi object URL ngay sau click (hỏng trên Safari) | Minor | Ngày theo giờ Việt Nam; thu hồi sau 1 giây |
| F6 | Biểu đồ sập nếu chuỗi rỗng; số "tài khoản bị khóa" nằm dưới ô Giảng viên dù tính mọi vai trò | Minor | Bảo vệ chuỗi rỗng; ô "Tài khoản bị khóa" riêng, dẫn tới tab Đã khóa |
| F7 | Khung thông báo tĩnh dùng `role=status` / `role=alert` (trình đọc màn hình đọc như thông báo mới) | Minor | Đổi thành `<section aria-label>` |
| F8 | Ẩn khóa xong, danh mục và trang khóa còn cache cũ | Minor | Thao tác admin làm mới thêm `catalog` và `course` |

---

## Task 15: Sửa backend sau review

**Files:**
- Create: `backend/alembic/versions/d7a4b9c2e615_review_fixes.py`, `backend/tests/test_review_fixes.py`
- Modify: `backend/app/modules/notify/{models,outbox}.py`, `backend/app/modules/auth/{models,service,router}.py`, `backend/app/modules/admin/{schemas,service}.py`, `backend/tests/{test_admin,test_email,test_tutor_api}.py`

- [ ] **Bước 1: Viết test (sẽ fail)** (`tests/test_review_fixes.py`)

```python
"""Các sửa sau code review: gửi email từng cái một có hạn thuê, tách lý do khóa, chặn CSV injection,
escape LIKE, tắt bắt buộc xác nhận email, chống spam đăng ký, xóa token khỏi outbox sau khi gửi."""

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.outbox import REDACTED, _claim, queue_email, send_pending
from app.modules.notify.templates import course_hidden
from tests.fakes import RecordingMailer
from tests.helpers import API, login, make_admin, make_student, register_user


async def _outbox(template: str | None = None) -> list[EmailOutbox]:
    async with SessionLocal() as db:
        stmt = select(EmailOutbox).order_by(EmailOutbox.created_at, EmailOutbox.id)
        if template:
            stmt = stmt.where(EmailOutbox.template == template)
        return list((await db.scalars(stmt)).all())


async def test_claimed_email_is_not_sent_twice_while_leased_and_retried_after_lease():
    async with SessionLocal() as db:
        db.add(EmailOutbox(to_email="a@x.com", subject="S", body_text="T", body_html="T", template="t"))
        await db.commit()
    claimed = await _claim(SessionLocal)  # worker nhận email rồi "chết" trước khi gửi xong
    assert claimed is not None and claimed[1] == 1
    mailer = RecordingMailer()
    assert await send_pending(SessionLocal, mailer) == 0  # còn trong hạn thuê: không gửi trùng
    async with SessionLocal() as db:
        await db.execute(update(EmailOutbox).values(next_attempt_at=None))
        await db.commit()
    assert await send_pending(SessionLocal, mailer) == 1  # hết hạn thuê: gửi lại
    (mail,) = await _outbox()
    assert (mail.status, mail.attempts) == (EmailStatus.sent, 2)


async def test_verification_email_body_is_redacted_after_sending(client):
    await register_user(client, "an@x.com", verify=False)
    assert await send_pending(SessionLocal, RecordingMailer()) == 1
    (mail,) = await _outbox("verify_email")
    assert mail.status == EmailStatus.sent and mail.body_text == mail.body_html == REDACTED


async def test_subject_newlines_are_flattened():
    async with SessionLocal() as db:
        queue_email(db, "gv@x.com", "course_hidden", course_hidden("Bình", "Giải tích\r\n1", "x", "http://u"))
        await db.commit()
    (mail,) = await _outbox()
    assert mail.subject == "Khóa học “Giải tích 1” đã bị ẩn"
    mailer = RecordingMailer()
    assert await send_pending(SessionLocal, mailer) == 1


async def test_lock_reason_is_separate_from_rejection_reason(client):
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher")
    await client.post(
        f"{API}/admin/teachers/{gv['id']}/reject", json={"reason": "Thiếu minh chứng"}, headers=ad
    )
    r = await client.post(f"{API}/admin/users/{gv['id']}/lock", json={"reason": "Spam"}, headers=ad)
    assert (r.json()["review_note"], r.json()["lock_reason"]) == ("Thiếu minh chứng", "Spam")
    r = await client.post(f"{API}/admin/users/{gv['id']}/unlock", headers=ad)
    assert (r.json()["review_note"], r.json()["lock_reason"]) == ("Thiếu minh chứng", None)
    me = await client.get(f"{API}/me", headers=await login(client, "gv@x.com"))
    assert me.json()["review_note"] == "Thiếu minh chứng"


async def test_csv_neutralises_formulas(client):
    _, ad = await make_admin(client)
    await register_user(client, "x@x.com", full_name='=HYPERLINK("http://evil","x")')
    r = await client.get(f"{API}/admin/users/export", params={"role": "student"}, headers=ad)
    assert "'=HYPERLINK" in r.content.decode("utf-8")


async def test_search_treats_percent_and_underscore_literally(client):
    _, ad = await make_admin(client)
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await register_user(client, "giam_50@x.com", full_name="Giảm 50% học phí")
    for q, expected in (("%", ["giam_50@x.com"]), ("_", ["giam_50@x.com"]), ("an", ["an@x.com"])):
        r = await client.get(f"{API}/admin/users", params={"role": "student", "q": q}, headers=ad)
        assert [u["email"] for u in r.json()["items"]] == expected, q


async def test_without_required_verification_teachers_queue_immediately(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_verification_required", False)
    _, ad = await make_admin(client)
    gv = await register_user(client, "gv@x.com", role="teacher", verify=False)
    r = await client.get(f"{API}/admin/users", params={"status": "pending"}, headers=ad)
    assert [u["id"] for u in r.json()["items"]] == [gv["id"]]
    assert [m.to_email for m in await _outbox("new_pending_teacher")] == ["admin@x.com"]
    assert (
        await client.post(f"{API}/auth/login", json={"email": "gv@x.com", "password": "password123"})
    ).status_code == 200


async def test_register_and_resend_are_rate_limited_per_ip(client, limiter):
    limiter.counts["register-ip:127.0.0.1"] = 20
    r = await client.post(
        f"{API}/auth/register", json={"email": "z@x.com", "password": "password123", "full_name": "Z"}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (429, "RATE_LIMITED")
    limiter.counts["verify-resend-ip:127.0.0.1"] = 10
    r = await client.post(f"{API}/auth/resend-verification", json={"email": "z@x.com"})
    assert r.status_code == 429


async def test_unlock_does_not_touch_other_users(client):
    _, ad = await make_admin(client)
    sv_id, _ = await make_student(client)
    await client.post(f"{API}/admin/users/{sv_id}/lock", json={}, headers=ad)
    r = await client.post(f"{API}/admin/users/{sv_id}/unlock", headers=ad)
    assert r.json()["lock_reason"] is None and r.json()["locked_at"] is None
```

- [ ] **Bước 2: Migration** (`alembic/versions/d7a4b9c2e615_review_fixes.py`)

```python
"""review fixes: users.lock_reason, email_outbox.next_attempt_at

Revision ID: d7a4b9c2e615
Revises: c5d2e8f1a734
Create Date: 2026-10-07 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a4b9c2e615"
down_revision: str | Sequence[str] | None = "c5d2e8f1a734"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("lock_reason", sa.String(length=500), nullable=True))
    # Trước đây lý do khóa nằm chung review_note: chuyển sang cột mới (giữ lý do từ chối giảng viên).
    op.execute(
        "UPDATE users SET lock_reason = review_note, review_note = NULL "
        "WHERE locked_at IS NOT NULL AND teacher_status IS DISTINCT FROM 'rejected'"
    )
    op.add_column("email_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("email_outbox", "next_attempt_at")
    op.execute(
        "UPDATE users SET review_note = lock_reason WHERE lock_reason IS NOT NULL AND review_note IS NULL"
    )
    op.drop_column("users", "lock_reason")
```

- [ ] **Bước 3: Model**

```diff
--- a/backend/app/modules/auth/models.py
+++ b/backend/app/modules/auth/models.py
@@ -35,8 +35,10 @@
     role: Mapped[Role] = mapped_column(SAEnum(Role, name="user_role"))
     teacher_status: Mapped[TeacherStatus | None] = mapped_column(SAEnum(TeacherStatus, name="teacher_status"))
     locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
-    # Lý do quản trị viên ghi khi từ chối giảng viên hoặc khóa tài khoản (hiện cho chính người dùng).
+    # Lý do quản trị viên ghi khi từ chối giảng viên (hiện cho chính người dùng).
     review_note: Mapped[str | None] = mapped_column(String(500))
+    # Lý do khóa tài khoản. Tách khỏi review_note để khóa / mở khóa không đè lý do từ chối.
+    lock_reason: Mapped[str | None] = mapped_column(String(500))
     # NULL = chưa bấm link xác nhận email (không đăng nhập được khi EMAIL_VERIFICATION_REQUIRED=true).
     email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
 
```

```diff
--- a/backend/app/modules/notify/models.py
+++ b/backend/app/modules/notify/models.py
@@ -34,3 +34,6 @@
     attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
     last_error: Mapped[str | None] = mapped_column(Text)
     sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
+    # Lần gửi kế tiếp được phép (NULL = ngay). Khi nhận email để gửi, đặt lùi ra sau CLAIM_LEASE: nếu worker
+    # chết giữa chừng thì hết hạn thuê, lượt sau gửi lại (ít nhất một lần, không kẹt mãi).
+    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Bước 4: Outbox gửi từng email** (`app/modules/notify/outbox.py`, thay toàn bộ)

```python
import logging
from datetime import timedelta
from functools import lru_cache
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.time import utcnow
from app.modules.notify.mailer import Mailer
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.templates import Mail

logger = logging.getLogger(__name__)
SEND_BATCH = 5  # 5 × SMTP_TIMEOUT_S (20 giây) < timeout job 120 giây


def queue_email(db: AsyncSession, to: str, template: str, mail: Mail) -> None:
    """Thêm email vào outbox trong transaction đang mở. Nơi gọi tự commit (cùng thay đổi nghiệp vụ)."""
    subject, text, html = mail
    subject = " ".join(subject.split())  # tên khóa / tên người có xuống dòng thì header Subject sẽ lỗi
    db.add(EmailOutbox(to_email=to, subject=subject, body_text=text, body_html=html, template=template))


class MailKicker(Protocol):
    async def kick(self) -> None: ...


class ArqMailKicker:
    """Báo worker gửi ngay sau khi commit (không đợi cron mỗi phút). Lỗi Redis thì bỏ qua: cron vẫn gửi."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def kick(self) -> None:
        try:
            if self._pool is None:
                settings = RedisSettings.from_dsn(self._redis_url)
            # Redis chết thì bỏ qua nhanh (cron vẫn gửi), không để request chờ arq thử kết nối lại nhiều lần.
            settings.conn_retries = 0
            settings.conn_timeout = 1
            self._pool = await create_pool(settings)
            await self._pool.enqueue_job("send_pending_emails")
        except Exception:
            logger.warning("Không báo được worker gửi email, cron sẽ gửi sau", exc_info=True)


@lru_cache
def get_mail_kicker() -> MailKicker:
    return ArqMailKicker(get_settings().redis_url)


CLAIM_LEASE = timedelta(minutes=5)
RETRY_BACKOFF = timedelta(minutes=1)  # lỗi lần n thì chờ n phút rồi thử lại
REDACTED = "[Nội dung đã xóa sau khi gửi]"
# Email chứa link một lần (token thật): xóa nội dung sau khi gửi để DB không giữ token dạng rõ.
SECRET_TEMPLATES = frozenset({"verify_email"})


async def _claim(session_factory: async_sessionmaker) -> tuple[EmailOutbox, int] | None:
    """Nhận một email đến hạn gửi và commit ngay (attempts + 1, đặt hạn thuê), để khóa dòng không bị giữ
    trong lúc chờ SMTP và lần thử được tính kể cả khi worker chết giữa chừng."""
    now = utcnow()
    async with session_factory() as db:
        mail = await db.scalar(
            select(EmailOutbox)
            .where(
                EmailOutbox.status == EmailStatus.pending,
                or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now),
            )
            .order_by(EmailOutbox.created_at, EmailOutbox.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if mail is None:
            return None
        mail.attempts += 1
        mail.next_attempt_at = now + CLAIM_LEASE
        await db.commit()
        db.expunge(mail)
        return mail, mail.attempts


async def _finish(session_factory: async_sessionmaker, mail_id, error: str | None, attempts: int) -> None:
    async with session_factory() as db:
        mail = await db.get(EmailOutbox, mail_id)
        if error is None:
            mail.status = EmailStatus.sent
            mail.sent_at = utcnow()
            mail.last_error = None
            mail.next_attempt_at = None
            if mail.template in SECRET_TEMPLATES:
                mail.body_text = mail.body_html = REDACTED
        else:
            mail.last_error = error[:2000]
            if attempts >= get_settings().mail_max_attempts:
                mail.status = EmailStatus.failed
            else:
                mail.next_attempt_at = utcnow() + RETRY_BACKOFF * attempts
        await db.commit()


async def send_pending(session_factory: async_sessionmaker, mailer: Mailer, limit: int = SEND_BATCH) -> int:
    """Gửi tối đa `limit` email đến hạn, từng email một. Trả số email gửi thành công.

    Mỗi email: nhận (commit) → gửi SMTP → ghi kết quả (commit). Hai lần chạy song song (kick + cron) không
    nhận trùng nhờ SKIP LOCKED + hạn thuê. Gửi lỗi thì chờ lùi dần rồi thử lại, quá MAIL_MAX_ATTEMPTS thì failed.
    `limit` × SMTP_TIMEOUT_S phải nhỏ hơn timeout của job arq (120 giây)."""
    sent = 0
    for _ in range(limit):
        claimed = await _claim(session_factory)
        if claimed is None:
            break
        mail, attempts = claimed
        try:
            await mailer.send(mail.to_email, mail.subject, mail.body_text, mail.body_html)
        except Exception as exc:  # noqa: BLE001 — SMTP lỗi kiểu gì cũng thử lại ở lượt sau
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("Gửi email %s tới %s lỗi: %s", mail.id, mail.to_email, error)
            await _finish(session_factory, mail.id, error, attempts)
        else:
            await _finish(session_factory, mail.id, None, attempts)
            sent += 1
    return sent
```

- [ ] **Bước 5: Tách lý do khóa, chặn CSV injection, escape LIKE, cờ xác nhận email** (admin)

```diff
--- a/backend/app/modules/admin/schemas.py
+++ b/backend/app/modules/admin/schemas.py
@@ -42,7 +42,8 @@
     role: Role
     teacher_status: TeacherStatus | None
     locked_at: datetime | None
-    review_note: str | None
+    review_note: str | None  # lý do từ chối giảng viên
+    lock_reason: str | None
     email_verified: bool
     created_at: datetime
     course_count: int  # giảng viên: số khóa đang sở hữu
```

```diff
--- a/backend/app/modules/admin/service.py
+++ b/backend/app/modules/admin/service.py
@@ -57,19 +57,26 @@
 
 
 def _like(q: str) -> str:
-    return f"%{q.strip().lower()}%"
+    """Mẫu LIKE từ chuỗi người dùng gõ: % và _ được coi là ký tự thường (dùng kèm escape="\\")."""
+    q = q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
+    return f"%{q}%"
+
+
+def _ilike(column, pattern: str):
+    return func.immutable_unaccent(func.lower(column)).like(func.immutable_unaccent(pattern), escape="\\")
 
 
 def _url(path: str) -> str:
     return f"{get_settings().app_base_url}{path}"
 
 
-# Giảng viên chỉ vào hàng chờ duyệt khi đã xác nhận email (tránh hàng chờ đầy email giả).
-_PENDING = (
-    User.role == Role.teacher,
-    User.teacher_status == TeacherStatus.pending,
-    User.email_verified_at.is_not(None),
-)
+def _pending():
+    """Giảng viên chờ duyệt. Khi bắt buộc xác nhận email thì chỉ tính người đã xác nhận (tránh hàng chờ
+    đầy email giả); tắt EMAIL_VERIFICATION_REQUIRED thì tính mọi người."""
+    conds = [User.role == Role.teacher, User.teacher_status == TeacherStatus.pending]
+    if get_settings().email_verification_required:
+        conds.append(User.email_verified_at.is_not(None))
+    return conds
 
 
 # ---------- người dùng ----------
@@ -99,6 +106,7 @@
         teacher_status=user.teacher_status,
         locked_at=user.locked_at,
         review_note=user.review_note,
+        lock_reason=user.lock_reason,
         email_verified=user.email_verified_at is not None,
         created_at=user.created_at,
         course_count=course_count,
@@ -111,7 +119,7 @@
     if role is not None:
         stmt = stmt.where(User.role == role)
     if status == "pending":
-        stmt = stmt.where(*_PENDING)
+        stmt = stmt.where(*_pending())
     elif status == "unverified":
         stmt = stmt.where(User.email_verified_at.is_(None))
     elif status in ("approved", "rejected"):
@@ -122,8 +130,8 @@
         pattern = _like(q)
         stmt = stmt.where(
             or_(
-                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
-                User.email.like(pattern),
+                _ilike(User.full_name, pattern),
+                User.email.like(pattern, escape="\\"),
             )
         )
     # Chờ duyệt: ai đăng ký trước được xử lý trước. Còn lại: mới nhất lên đầu.
@@ -150,6 +158,14 @@
 }
 
 
+_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
+
+
+def _cell(value: str) -> str:
+    """Chặn CSV injection: ô bắt đầu bằng = + - @ bị Excel coi là công thức (vd. =HYPERLINK(...) trong họ tên)."""
+    return f"'{value}" if value.startswith(_FORMULA_START) else value
+
+
 async def export_users_csv(db: AsyncSession, role: Role | None, status: str | None, q: str | None) -> str:
     """CSV theo đúng bộ lọc đang xem. Có BOM UTF-8 để Excel hiện đúng tiếng Việt."""
     rows = (await db.execute(_users_stmt(role, status, q).limit(CSV_MAX_ROWS))).all()
@@ -172,8 +188,8 @@
     for u, cc, ec in rows:
         w.writerow(
             [
-                u.full_name,
-                u.email,
+                _cell(u.full_name),
+                _cell(u.email),
                 _ROLE_VI[u.role],
                 _STATUS_VI.get(u.teacher_status, "") if u.teacher_status else "",
                 "Có" if u.email_verified_at else "Chưa",
@@ -236,7 +252,7 @@
         raise AppError("CANNOT_LOCK_ADMIN", "Không thể khóa tài khoản quản trị viên", 409)
     if user.locked_at is None:
         user.locked_at = utcnow()
-        user.review_note = reason
+        user.lock_reason = reason
         # Thu hồi mọi phiên: refresh bị chặn ngay; access token còn hạn cũng bị deps chặn vì locked_at.
         await db.execute(
             update(RefreshToken)
@@ -255,9 +271,7 @@
         raise not_found("Người dùng")
     if user.locked_at is not None:
         user.locked_at = None
-        # Lý do khóa không còn đúng nữa; lý do từ chối giảng viên (nếu có) thì giữ.
-        if user.teacher_status != TeacherStatus.rejected:
-            user.review_note = None
+        user.lock_reason = None
         _log(db, admin, "unlock_user", "user", user.id, user.email, None)
         await db.commit()
     return await _get_user_row(db, user.id)
@@ -319,8 +333,8 @@
         pattern = _like(q)
         stmt = stmt.where(
             or_(
-                func.immutable_unaccent(func.lower(Course.title)).like(func.immutable_unaccent(pattern)),
-                func.immutable_unaccent(func.lower(User.full_name)).like(func.immutable_unaccent(pattern)),
+                _ilike(Course.title, pattern),
+                _ilike(User.full_name, pattern),
             )
         )
     total, paged = await paginate(db, stmt.order_by(Course.created_at.desc(), Course.id), params)
@@ -409,7 +423,7 @@
     return AdminStats(
         students=by_role.get(Role.student, 0),
         teachers=by_role.get(Role.teacher, 0),
-        pending_teachers=await count(select(func.count()).select_from(User).where(*_PENDING)),
+        pending_teachers=await count(select(func.count()).select_from(User).where(*_pending())),
         locked_users=await count(select(func.count()).select_from(User).where(User.locked_at.is_not(None))),
         courses_published=by_status.get(CourseStatus.published, 0),
         courses_draft=by_status.get(CourseStatus.draft, 0),
```

- [ ] **Bước 6: Báo admin lúc đăng ký khi tắt xác nhận; giới hạn theo IP** (auth)

```diff
--- a/backend/app/modules/auth/service.py
+++ b/backend/app/modules/auth/service.py
@@ -42,6 +42,9 @@
     try:
         await db.flush()  # cần user.id cho link xác nhận
         await _issue_verify_token(db, user)
+        if role == Role.teacher and not get_settings().email_verification_required:
+            # Không bắt buộc xác nhận email: giảng viên vào hàng chờ ngay, báo admin luôn lúc đăng ký.
+            await notify_admins_pending_teacher(db, user)
         await db.commit()
     except IntegrityError:
         # Hai request đăng ký cùng email chạy song song: cả hai qua được bước kiểm tra ở trên,
```

```diff
--- a/backend/app/modules/auth/router.py
+++ b/backend/app/modules/auth/router.py
@@ -1,4 +1,4 @@
-from fastapi import APIRouter, Cookie, Depends, Response
+from fastapi import APIRouter, Cookie, Depends, Request, Response
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from app.core.config import get_settings
@@ -37,11 +37,43 @@
     )
 
 
+REGISTER_IP_LIMIT = 20  # mỗi IP tối đa 20 lần đăng ký / giờ (mỗi lần đăng ký gửi một email)
+RESEND_LIMIT = 3  # mỗi email tối đa 3 lần / giờ
+RESEND_IP_LIMIT = 10  # mỗi IP tối đa 10 lần / giờ (chặn spam nhiều email khác nhau)
+
+
+def _too_many(wait: int) -> AppError:
+    return AppError(
+        "RATE_LIMITED",
+        "Bạn thao tác quá nhiều lần, vui lòng thử lại sau",
+        429,
+        {"retry_after": wait},
+        headers={"Retry-After": str(wait)},
+    )
+
+
+async def _limit(limiter: RateLimiter, key: str, limit: int) -> None:
+    wait = await limiter.hit(key, limit, 3600)
+    if wait is not None:
+        raise _too_many(wait)
+
+
+def _ip(request: Request) -> str:
+    # Sau reverse proxy (Caddy ở tầng S) cần chạy uvicorn với --proxy-headers để đây là IP thật.
+    return request.client.host if request.client else "unknown"
+
+
 @router.post("/auth/register", response_model=UserOut, status_code=201)
 async def register(
-    data: RegisterIn, db: AsyncSession = Depends(get_db), kicker: MailKicker = Depends(get_mail_kicker)
+    data: RegisterIn,
+    request: Request,
+    db: AsyncSession = Depends(get_db),
+    limiter: RateLimiter = Depends(get_rate_limiter),
+    kicker: MailKicker = Depends(get_mail_kicker),
 ):
-    """Tạo tài khoản và gửi email xác nhận. Chưa xác nhận thì đăng nhập nhận 403 EMAIL_NOT_VERIFIED."""
+    """Tạo tài khoản và gửi email xác nhận. Chưa xác nhận thì đăng nhập nhận 403 EMAIL_NOT_VERIFIED.
+    429 RATE_LIMITED khi một IP đăng ký quá 20 lần / giờ."""
+    await _limit(limiter, f"register-ip:{_ip(request)}", REGISTER_IP_LIMIT)
     user = await service.register(db, data)
     await kicker.kick()
     return user
@@ -57,26 +89,18 @@
     return user
 
 
-RESEND_LIMIT = 3  # mỗi email tối đa 3 lần / giờ
-
-
 @router.post("/auth/resend-verification", status_code=202)
 async def resend_verification(
     data: ResendVerificationIn,
+    request: Request,
     db: AsyncSession = Depends(get_db),
     limiter: RateLimiter = Depends(get_rate_limiter),
     kicker: MailKicker = Depends(get_mail_kicker),
 ) -> dict:
-    """Luôn 202 (không lộ email nào đã đăng ký). 429 RATE_LIMITED khi gửi quá 3 lần mỗi giờ cho một email."""
-    wait = await limiter.hit(f"verify-resend:{data.email}", RESEND_LIMIT, 3600)
-    if wait is not None:
-        raise AppError(
-            "RATE_LIMITED",
-            "Bạn đã yêu cầu gửi lại quá nhiều lần, vui lòng thử lại sau",
-            429,
-            {"retry_after": wait},
-            headers={"Retry-After": str(wait)},
-        )
+    """Luôn 202 (không lộ email nào đã đăng ký). 429 RATE_LIMITED khi quá 3 lần/giờ cho một email
+    hoặc quá 10 lần/giờ từ một IP."""
+    await _limit(limiter, f"verify-resend-ip:{_ip(request)}", RESEND_IP_LIMIT)
+    await _limit(limiter, f"verify-resend:{data.email}", RESEND_LIMIT)
     if await service.resend_verification(db, data.email):
         await kicker.kick()
     return {"status": "accepted"}
```

> Ở tầng S, API chạy sau Caddy: thêm `--proxy-headers --forwarded-allow-ips="*"` vào lệnh `uvicorn`, nếu không mọi request đều mang IP của Caddy và giới hạn theo IP sẽ chặn cả hệ thống. Ghi chú này vào plan tầng S.

- [ ] **Bước 7: Sửa test cũ cho khớp**

- `test_admin.py`: lý do khóa giờ nằm ở `lock_reason`.
- `test_email.py`: gửi lỗi thì chờ lùi, test phải cho email "đến hạn" trước khi gửi lại.
- `test_tutor_api.py`: rate limiter giờ có thêm lượt đếm đăng ký theo IP, nên chỉ so lượt đếm của Tutor.

```diff
--- a/backend/tests/test_admin.py
+++ b/backend/tests/test_admin.py
@@ -106,14 +106,14 @@
 
     r = await client.post(f"{API}/admin/users/{sv_id}/lock", json={"reason": "Spam diễn đàn"}, headers=ad)
     assert r.status_code == 200 and r.json()["locked_at"] is not None
-    assert r.json()["review_note"] == "Spam diễn đàn"
+    assert r.json()["lock_reason"] == "Spam diễn đàn"
     assert _code(await client.get(f"{API}/me", headers=sv)) == (403, "ACCOUNT_LOCKED")
     client.cookies.clear()
     refreshed = await client.post(f"{API}/auth/refresh", headers={"Cookie": f"refresh_token={raw}"})
     assert refreshed.status_code in (401, 403)
 
     r = await client.post(f"{API}/admin/users/{sv_id}/unlock", headers=ad)
-    assert (r.json()["locked_at"], r.json()["review_note"]) == (None, None)
+    assert (r.json()["locked_at"], r.json()["lock_reason"]) == (None, None)
     assert (await client.get(f"{API}/me", headers=await login(client, "sv@x.com"))).status_code == 200
 
     # không khóa được quản trị viên (kể cả chính mình); khóa không cần lý do
@@ -122,7 +122,7 @@
         "CANNOT_LOCK_ADMIN",
     )
     r = await client.post(f"{API}/admin/users/{sv_id}/lock", json={}, headers=ad)
-    assert r.status_code == 200 and r.json()["review_note"] is None
+    assert r.status_code == 200 and r.json()["lock_reason"] is None
 
 
 async def test_users_filter_by_role_status_and_search_without_accents(client):
```

```diff
--- a/backend/tests/test_email.py
+++ b/backend/tests/test_email.py
@@ -181,7 +181,17 @@
     assert kicker.kicks - before == 5
 
 
-async def test_send_pending_marks_sent_and_retries_then_gives_up():
+async def _make_due(to: str | None = None) -> None:
+    """Cho email đang chờ lùi (backoff / hạn thuê) đến hạn gửi ngay."""
+    async with SessionLocal() as db:
+        stmt = update(EmailOutbox).values(next_attempt_at=None)
+        if to:
+            stmt = stmt.where(EmailOutbox.to_email == to)
+        await db.execute(stmt)
+        await db.commit()
+
+
+async def test_send_pending_marks_sent_and_retries_with_backoff_then_gives_up():
     async with SessionLocal() as db:
         db.add(
             EmailOutbox(to_email="a@x.com", subject="S", body_text="T", body_html="<p>T</p>", template="t")
@@ -196,6 +206,9 @@
         1,
         "ConnectionError: SMTP down",
     )
+    assert mail.next_attempt_at > utcnow()  # chờ lùi, không thử lại ngay
+    assert await send_pending(SessionLocal, flaky) == 0
+    await _make_due()
     assert await send_pending(SessionLocal, flaky) == 1
     (mail,) = await _outbox()
     assert (mail.status, mail.attempts, mail.last_error) == (EmailStatus.sent, 2, None)
```

```diff
--- a/backend/tests/test_tutor_api.py
+++ b/backend/tests/test_tutor_api.py
@@ -20,6 +20,11 @@
 TEST_TIMEOUT_S = 15  # mọi request chờ stream đều có giới hạn: hồi quy thì hỏng chứ không treo
 
 
+def _tutor_counts(limiter) -> dict[str, int]:
+    """Chỉ lượt đếm của Tutor (đăng ký tài khoản trong test cũng đi qua rate limiter theo IP)."""
+    return {k: v for k, v in limiter.counts.items() if k.startswith("tutor:")}
+
+
 async def _ready_session(client, db):
     _, gv = await make_teacher(client)
     course, _, lesson = await make_published_course(client, gv)
@@ -96,13 +101,15 @@
     msgs = (await client.get(f"{API}/tutor/sessions/{session['id']}/messages", headers=sv)).json()
     assert msgs["total"] == 4  # câu bị chặn không được lưu
     student = await db.scalar(select(User).where(User.email == "sv@x.com"))
-    assert limiter.counts == {f"tutor:{student.id}": 3}  # RedisRateLimiter thêm tiền tố → rl:tutor:<id>
+    assert _tutor_counts(limiter) == {
+        f"tutor:{student.id}": 3
+    }  # RedisRateLimiter thêm tiền tố → rl:tutor:<id>
     # giảng viên không bị giới hạn (và không bị đếm)
     body = {"course_id": course["id"], "lesson_id": lesson["id"]}
     teacher_session = (await client.post(f"{API}/tutor/sessions", json=body, headers=gv)).json()
     for _ in range(3):
         assert (await _ask(client, gv, teacher_session["id"])).status_code == 200
-    assert list(limiter.counts) == [f"tutor:{student.id}"]
+    assert list(_tutor_counts(limiter)) == [f"tutor:{student.id}"]
 
 
 async def test_other_users_session_and_blank_question(client, db, limiter):
@@ -111,7 +118,7 @@
     assert (await _ask(client, other, session["id"])).status_code == 404
     r = await _ask(client, sv, session["id"], "   ")
     assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
-    assert limiter.counts == {}  # bị từ chối trước rate limit: không tốn lượt
+    assert _tutor_counts(limiter) == {}  # bị từ chối trước rate limit: không tốn lượt
     assert await _messages(db, session["id"]) == []
 
 
@@ -121,7 +128,7 @@
     await db.commit()
     r = await _ask(client, sv, session["id"])
     assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")  # như khi tạo phiên
-    assert await _messages(db, session["id"]) == [] and limiter.counts == {}
+    assert await _messages(db, session["id"]) == [] and _tutor_counts(limiter) == {}
 
 
 async def test_unpublished_after_session_creation_cannot_ask(client, db):
```

- [ ] **Bước 8: Kiểm tra và commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
docker compose up -d --build api worker
docker compose exec api alembic check
```

Expected: **647 passed**; `No new upgrade operations detected.`

```bash
git add backend && git commit -m "fix(api): per-email outbox claims with lease and backoff, separate lock_reason, CSV formula escaping, LIKE escaping, IP rate limits"
```

---

## Task 16: Sửa frontend sau review

**Files:**
- Modify: `frontend/src/lib/api/schema.d.ts` (sinh lại), `src/lib/auth/auth-context.tsx`, `src/components/admin/{user-table,overview}.tsx`, `src/app/(main)/admin/{users,courses}/page.tsx`, `src/lib/admin-queries.ts`, `src/components/auth/check-email.tsx`, `src/app/(auth)/verify-email/verify-email.tsx`, `src/app/(main)/page.tsx`, `src/components/teach/course-editor.tsx`, `e2e/{admin-data,admin.spec}.ts`
- Create: `frontend/e2e/review-fixes.spec.ts`

- [ ] **Bước 1: Sinh lại kiểu API** (`npm run gen:api`). Thêm `lock_reason` vào `AdminUserOut`.

- [ ] **Bước 2: E2E (sẽ fail)** (`e2e/review-fixes.spec.ts`)

```ts
import { expect, test } from "@playwright/test";
import { admin, page as pageOf, pendingTeacher } from "./admin-data";
import { mockApi, student } from "./mock-api";

test("mở link xác nhận khi trình duyệt đang có phiên đăng nhập: chỉ gửi xác nhận một lần", async ({ page }) => {
  let calls = 0;
  await mockApi(page, {
    user: student, // khôi phục phiên làm đổi người dùng → resetQueries; truy vấn xác nhận không được chạy lại
    extra: {
      "POST /auth/verify-email": (r) => {
        calls += 1;
        return calls === 1
          ? r.fulfill({ json: { ...student, email_verified: true } })
          : r.fulfill({ status: 400, json: { error: { code: "INVALID_TOKEN", message: "x", details: {}, request_id: null } } });
      },
    },
  });
  await page.goto("/verify-email?token=abc123xyz789");
  await expect(page.getByRole("heading", { name: "Email đã được xác nhận" })).toBeVisible();
  await page.waitForTimeout(800);
  await expect(page.getByRole("heading", { name: "Email đã được xác nhận" })).toBeVisible();
  expect(calls).toBe(1);
});

test("duyệt người cuối cùng ở trang 2: có nút về trang đầu, bấm Duyệt hai lần chỉ gửi một request", async ({ page }) => {
  let approves = 0;
  let remaining = 21;
  const rows = (p: number) =>
    Array.from({ length: Math.max(0, Math.min(20, remaining - (p - 1) * 20)) }, (_, i) => ({
      ...pendingTeacher,
      id: `u-${p}-${i}`,
      email: `gv${p}${i}@gv.vn`,
      full_name: `Giảng viên ${p}-${i}`,
    }));
  await mockApi(page, {
    user: admin,
    extra: {
      "GET /admin/users": (r, url) => {
        const p = Number(url.searchParams.get("page") ?? 1);
        return r.fulfill({ json: { items: rows(p), total: remaining, page: p, size: 20 } });
      },
      "POST /admin/teachers/*/approve": async (r) => {
        approves += 1;
        await new Promise((res) => setTimeout(res, 300)); // đủ lâu để cú bấm thứ hai rơi vào lúc đang xử lý
        remaining -= 1;
        return r.fulfill({ json: { ...pendingTeacher, teacher_status: "approved" } });
      },
    },
  });
  await page.goto("/admin/users?tab=pending");
  await page.getByRole("button", { name: "Trang sau" }).click();
  const approve = page.getByRole("button", { name: "Duyệt Giảng viên 2-0" });
  await approve.dblclick();
  await expect(page.getByText("Trang này không còn ai.")).toBeVisible();
  expect(approves).toBe(1);
  await page.getByRole("button", { name: "Về trang đầu" }).click();
  await expect(page.getByRole("button", { name: "Duyệt Giảng viên 1-0" })).toBeVisible();
});

test("admin vào trang chủ thì được chuyển sang khu quản trị", async ({ page }) => {
  await mockApi(page, {
    user: admin,
    extra: {
      "GET /admin/stats": (r) => r.fulfill({ status: 500, json: { error: { code: "X", message: "x", details: {}, request_id: null } } }),
      "GET /admin/users": (r) => r.fulfill({ json: pageOf([]) }),
      "GET /admin/actions": (r) => r.fulfill({ json: pageOf([]) }),
    },
  });
  await page.goto("/");
  await expect(page).toHaveURL(/\/admin$/);
});
```

- [ ] **Bước 3: Sửa code**

```diff
--- a/frontend/src/lib/auth/auth-context.tsx
+++ b/frontend/src/lib/auth/auth-context.tsx
@@ -65,7 +65,8 @@
   React.useEffect(() => {
     if (status === "loading" || lastUserId.current === userId) return;
     lastUserId.current = userId;
-    void qc.resetQueries();
+    // Trừ truy vấn xác nhận email: token chỉ dùng một lần, gọi lại sẽ báo lỗi dù vừa xác nhận thành công.
+    void qc.resetQueries({ predicate: (q) => q.queryKey[0] !== "verify-email" });
   }, [status, userId, qc]);
 
   const login = React.useCallback(
```

```diff
--- a/frontend/src/components/admin/user-table.tsx
+++ b/frontend/src/components/admin/user-table.tsx
@@ -41,6 +41,17 @@
     }
   }
 
+  // Chặn bấm đúp: trạng thái "đang xử lý" của mutation chỉ có sau lần render kế tiếp, cú bấm thứ hai
+  // (cùng nhịp) vẫn lọt qua. Ref đổi ngay lập tức.
+  const busy = React.useRef(new Set<string>());
+  function once(key: string, start: () => Promise<unknown>, ok: string) {
+    if (busy.current.has(key)) return;
+    busy.current.add(key);
+    run(start(), ok)
+      .catch(() => {})
+      .finally(() => busy.current.delete(key));
+  }
+
   return (
     <>
       <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label={caption}>
@@ -62,7 +73,8 @@
                 <td className="px-4 py-3">
                   <p className="font-medium">{u.full_name}</p>
                   <p className="text-muted-foreground">{u.email}</p>
-                  {u.review_note ? <p className="mt-1 text-xs text-muted-foreground">Lý do: {u.review_note}</p> : null}
+                  {u.review_note ? <p className="mt-1 text-xs text-muted-foreground">Lý do từ chối: {u.review_note}</p> : null}
+                  {u.lock_reason ? <p className="mt-1 text-xs text-muted-foreground">Lý do khóa: {u.lock_reason}</p> : null}
                 </td>
                 <td className="px-4 py-3">{ROLE[u.role]}</td>
                 <td className="px-4 py-3">
@@ -75,7 +87,13 @@
                 <td className="px-4 py-3">
                   <div className="flex justify-end gap-2">
                     {u.role === "teacher" && u.teacher_status !== "approved" && !u.locked_at ? (
-                      <Button size="sm" aria-label={`Duyệt ${u.full_name}`} onClick={() => run(mut.approve.mutateAsync(u.id), `Đã duyệt ${u.full_name}`).catch(() => {})}>
+                      <Button
+                        size="sm"
+                        aria-label={`Duyệt ${u.full_name}`}
+                        loading={mut.approve.isPending && mut.approve.variables === u.id}
+                        loadingText="Đang duyệt…"
+                        onClick={() => once(`approve:${u.id}`, () => mut.approve.mutateAsync(u.id), `Đã duyệt ${u.full_name}`)}
+                      >
                         Duyệt
                       </Button>
                     ) : null}
@@ -85,7 +103,14 @@
                       </Button>
                     ) : null}
                     {u.role === "admin" ? null : u.locked_at ? (
-                      <Button size="sm" variant="outline" aria-label={`Mở khóa ${u.full_name}`} onClick={() => run(mut.unlock.mutateAsync(u.id), `Đã mở khóa ${u.full_name}`).catch(() => {})}>
+                      <Button
+                        size="sm"
+                        variant="outline"
+                        aria-label={`Mở khóa ${u.full_name}`}
+                        loading={mut.unlock.isPending && mut.unlock.variables === u.id}
+                        loadingText="Đang mở…"
+                        onClick={() => once(`unlock:${u.id}`, () => mut.unlock.mutateAsync(u.id), `Đã mở khóa ${u.full_name}`)}
+                      >
                         Mở khóa
                       </Button>
                     ) : (
```

```diff
--- a/frontend/src/app/(main)/admin/users/page.tsx
+++ b/frontend/src/app/(main)/admin/users/page.tsx
@@ -87,7 +87,20 @@
       ) : users.isError ? (
         <ErrorState error={users.error} onRetry={() => users.refetch()} />
       ) : users.data.items.length === 0 ? (
-        <EmptyState icon={Users} title={query ? `Không tìm thấy ai cho “${query}”.` : tab === "pending" ? "Không có giảng viên nào đang chờ duyệt." : "Chưa có người dùng nào."} />
+        page > 1 ? (
+          // Vừa xử lý hết dòng của trang cuối (vd. duyệt người cuối ở trang 2): đưa về trang đầu.
+          <EmptyState
+            icon={Users}
+            title="Trang này không còn ai."
+            action={
+              <Button variant="outline" onClick={() => setPaging({ key, page: 1 })}>
+                Về trang đầu
+              </Button>
+            }
+          />
+        ) : (
+          <EmptyState icon={Users} title={query ? `Không tìm thấy ai cho “${query}”.` : tab === "pending" ? "Không có giảng viên nào đang chờ duyệt." : "Chưa có người dùng nào."} />
+        )
       ) : (
         <div aria-busy={users.isFetching}>
           <UserTable users={users.data.items} caption={`Danh sách người dùng: ${TABS.find((t) => t.value === tab)!.label}`} />
```

```diff
--- a/frontend/src/app/(main)/admin/courses/page.tsx
+++ b/frontend/src/app/(main)/admin/courses/page.tsx
@@ -6,6 +6,7 @@
 import { CourseTable } from "@/components/admin/course-table";
 import { FilterTabs } from "@/components/admin/filter-tabs";
 import { Pagination } from "@/components/course/course-card";
+import { Button } from "@/components/ui/button";
 import { Input } from "@/components/ui/input";
 import { Skeleton } from "@/components/ui/misc";
 import { type CourseFilter, useAdminCourses } from "@/lib/admin-queries";
@@ -46,7 +47,19 @@
       ) : courses.isError ? (
         <ErrorState error={courses.error} onRetry={() => courses.refetch()} />
       ) : courses.data.items.length === 0 ? (
-        <EmptyState icon={Library} title={query ? `Không tìm thấy khóa nào cho “${query}”.` : "Không có khóa học nào."} />
+        page > 1 ? (
+          <EmptyState
+            icon={Library}
+            title="Trang này không còn khóa nào."
+            action={
+              <Button variant="outline" onClick={() => setPaging({ key, page: 1 })}>
+                Về trang đầu
+              </Button>
+            }
+          />
+        ) : (
+          <EmptyState icon={Library} title={query ? `Không tìm thấy khóa nào cho “${query}”.` : "Không có khóa học nào."} />
+        )
       ) : (
         <div aria-busy={courses.isFetching}>
           <CourseTable courses={courses.data.items} />
```

```diff
--- a/frontend/src/lib/admin-queries.ts
+++ b/frontend/src/lib/admin-queries.ts
@@ -81,16 +81,26 @@
   const url = URL.createObjectURL(blob as Blob);
   const a = document.createElement("a");
   a.href = url;
-  a.download = `nguoi-dung-${new Date().toISOString().slice(0, 10)}.csv`;
+  a.download = `nguoi-dung-${isoDateVN(new Date())}.csv`;
   document.body.appendChild(a);
   a.click();
   a.remove();
-  URL.revokeObjectURL(url);
+  // Thu hồi ngay sau click làm hỏng tải xuống trên Safari / Firefox cũ: đợi một nhịp.
+  setTimeout(() => URL.revokeObjectURL(url), 1000);
 }
 
 function useAdminMutation<A>(fn: (a: A) => Promise<unknown>) {
   const qc = useQueryClient();
-  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ADMIN }) });
+  return useMutation({
+    mutationFn: fn,
+    // Ẩn / hiện khóa cũng đổi danh mục công khai và trang chi tiết khóa đang cache.
+    onSuccess: () =>
+      Promise.all([
+        qc.invalidateQueries({ queryKey: ADMIN }),
+        qc.invalidateQueries({ queryKey: ["catalog"] }),
+        qc.invalidateQueries({ queryKey: ["course"] }),
+      ]),
+  });
 }
 
 const uid = (id: string) => ({ params: { path: { user_id: id } } });
@@ -126,4 +136,6 @@
 const dateFmt = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Ho_Chi_Minh" });
 const timeFmt = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
 export const fmtDate = (iso: string) => dateFmt.format(new Date(iso));
+/** yyyy-mm-dd theo giờ Việt Nam (toISOString là giờ UTC: 0h–7h sáng sẽ ra ngày hôm trước). */
+export const isoDateVN = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(d);
 export const fmtDateTime = (iso: string) => timeFmt.format(new Date(iso));
```

```diff
--- a/frontend/src/components/admin/overview.tsx
+++ b/frontend/src/components/admin/overview.tsx
@@ -1,6 +1,6 @@
 "use client";
 
-import { AlertTriangle, BookOpen, ClipboardCheck, GraduationCap, type LucideIcon, MessageCircleQuestion, ThumbsDown, UserCheck, Users } from "lucide-react";
+import { AlertTriangle, BookOpen, Lock, ClipboardCheck, GraduationCap, type LucideIcon, MessageCircleQuestion, ThumbsDown, UserCheck, Users } from "lucide-react";
 import Link from "next/link";
 import { type AdminStats } from "@/lib/admin-queries";
 import { cn } from "@/lib/utils";
@@ -32,7 +32,8 @@
     <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
       <Tile icon={UserCheck} label="Giảng viên chờ duyệt" value={s.pending_teachers} href="/admin/users?tab=pending" highlight={s.pending_teachers > 0} sub={s.pending_teachers > 0 ? "Bấm để xử lý" : "Không có ai đang chờ"} />
       <Tile icon={Users} label="Học viên" value={s.students} sub={`${s.enrollments.toLocaleString("vi-VN")} lượt đăng ký khóa`} href="/admin/users?tab=student" />
-      <Tile icon={GraduationCap} label="Giảng viên" value={s.teachers} sub={s.locked_users ? `${s.locked_users} tài khoản đang bị khóa` : undefined} href="/admin/users?tab=teacher" />
+      <Tile icon={GraduationCap} label="Giảng viên" value={s.teachers} href="/admin/users?tab=teacher" />
+      <Tile icon={Lock} label="Tài khoản bị khóa" value={s.locked_users} href="/admin/users?tab=locked" />
       <Tile icon={BookOpen} label="Khóa đã xuất bản" value={s.courses_published} sub={`${s.courses_draft} nháp · ${s.courses_hidden} đã ẩn`} href="/admin/courses" />
       <Tile icon={MessageCircleQuestion} label="Câu hỏi AI Tutor (7 ngày)" value={s.tutor_questions_7d} />
       <Tile icon={ClipboardCheck} label="Bài quiz đã nộp (7 ngày)" value={s.quiz_submissions_7d} />
@@ -46,6 +47,7 @@
 
 /** Cột đăng ký mới 14 ngày. Một chuỗi số liệu nên không cần chú thích; có bảng ẩn cho trình đọc màn hình. */
 export function SignupChart({ days }: { days: AdminStats["signups_14d"] }) {
+  if (days.length === 0) return null;
   const max = Math.max(1, ...days.map((d) => d.count));
   const total = days.reduce((a, d) => a + d.count, 0);
   const label = (d: { day: string }) => dayFmt.format(new Date(`${d.day}T00:00:00Z`));
```

```diff
--- a/frontend/src/components/auth/check-email.tsx
+++ b/frontend/src/components/auth/check-email.tsx
@@ -2,14 +2,20 @@
 
 import { MailCheck } from "lucide-react";
 import Link from "next/link";
+import * as React from "react";
 import { ResendVerification } from "./resend-verification";
 
 /** Màn sau khi đăng ký: chưa đăng nhập được cho tới khi bấm link trong email. */
 export function CheckEmail({ email, teacher }: { email: string; teacher: boolean }) {
+  // Form đăng ký vừa biến mất (nút đang focus bị gỡ): đưa focus tới tiêu đề mới để trình đọc màn hình đọc.
+  const heading = React.useRef<HTMLHeadingElement>(null);
+  React.useEffect(() => heading.current?.focus(), []);
   return (
     <div className="text-center">
       <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
-      <h1 className="mt-3 text-2xl font-semibold">Kiểm tra hộp thư của bạn</h1>
+      <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
+        Kiểm tra hộp thư của bạn
+      </h1>
       <p className="mt-2 text-sm text-muted-foreground">
         Chúng tôi đã gửi link xác nhận tới <span className="font-medium text-foreground">{email}</span>. Bấm link trong
         email để kích hoạt tài khoản (link có hiệu lực 24 giờ).
```

```diff
--- a/frontend/src/app/(auth)/verify-email/verify-email.tsx
+++ b/frontend/src/app/(auth)/verify-email/verify-email.tsx
@@ -13,6 +13,9 @@
 export function VerifyEmail() {
   const token = useSearchParams().get("token");
   const verify = useVerifyEmail(token);
+  // Khung chờ đổi sang kết quả: đưa focus tới tiêu đề kết quả.
+  const heading = React.useRef<HTMLHeadingElement>(null);
+  React.useEffect(() => heading.current?.focus(), [verify.status]);
 
   if (token && verify.isPending)
     return (
@@ -27,10 +30,12 @@
     return (
       <div className="text-center">
         <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
-        <h1 className="mt-3 text-2xl font-semibold">Email đã được xác nhận</h1>
+        <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
+          Email đã được xác nhận
+        </h1>
         <p className="mt-2 text-sm text-muted-foreground">
           {teacherWaiting
-            ? "Bạn đã đăng nhập được. Tài khoản giảng viên đang chờ quản trị viên duyệt, bạn sẽ nhận email khi có kết quả."
+            ? "Bạn có thể đăng nhập. Tài khoản giảng viên đang chờ quản trị viên duyệt, bạn sẽ nhận email khi có kết quả."
             : "Tài khoản đã được kích hoạt. Bạn có thể đăng nhập ngay."}
         </p>
         <Button asChild size="lg" className="mt-6 w-full">
@@ -44,7 +49,9 @@
   return (
     <div>
       <XCircle className="mx-auto size-10 text-destructive" aria-hidden />
-      <h1 className="mt-3 text-center text-2xl font-semibold">{expired ? "Link đã hết hạn" : "Link không dùng được"}</h1>
+      <h1 ref={heading} tabIndex={-1} className="mt-3 text-center text-2xl font-semibold outline-none">
+        {expired ? "Link đã hết hạn" : "Link không dùng được"}
+      </h1>
       <p className="mt-2 text-center text-sm text-muted-foreground">
         {token ? errorMessage(verify.error) : "Thiếu mã xác nhận trong link."} Nhập email để nhận link mới.
       </p>
```

```diff
--- a/frontend/src/app/(main)/page.tsx
+++ b/frontend/src/app/(main)/page.tsx
@@ -38,13 +38,13 @@
   const rejected = user.teacher_status === "rejected";
   const Icon = rejected ? XCircle : Clock;
   return (
-    <div role="status" className="mb-6 flex gap-3 rounded-lg border p-4">
+    <section aria-label="Trạng thái tài khoản giảng viên" className="mb-6 flex gap-3 rounded-lg border p-4">
       <Icon className={rejected ? "mt-0.5 size-5 shrink-0 text-destructive" : "mt-0.5 size-5 shrink-0 text-accent"} aria-hidden />
       <div>
         <p className="font-medium">{rejected ? "Yêu cầu giảng dạy chưa được chấp nhận" : "Tài khoản giảng viên đang chờ duyệt"}</p>
         <p className="mt-1 text-sm text-muted-foreground">
           {rejected
-            ? `Lý do: ${user.review_note ?? "không ghi"}. Bổ sung thông tin rồi gửi lại yêu cầu để được xem xét lại.`
+            ? `Lý do: ${user.review_note ?? "không ghi"}. Bạn có thể gửi lại yêu cầu để được xem xét lại.`
             : "Quản trị viên sẽ duyệt sớm và báo kết quả qua email. Trong lúc chờ, bạn vẫn xem được các khóa học đã xuất bản."}
         </p>
         {rejected ? (
@@ -53,7 +53,7 @@
           </Button>
         ) : null}
       </div>
-    </div>
+    </section>
   );
 }
 
```

```diff
--- a/frontend/src/components/teach/course-editor.tsx
+++ b/frontend/src/components/teach/course-editor.tsx
@@ -85,7 +85,7 @@
       </div>
 
       {course.hidden_reason ? (
-        <div role="alert" className="mb-6 flex gap-3 rounded-lg border border-destructive/50 p-4">
+        <section aria-label="Khóa học đã bị ẩn" className="mb-6 flex gap-3 rounded-lg border border-destructive/50 p-4">
           <EyeOff className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
           <div>
             <p className="font-medium">Quản trị viên đã ẩn khóa học này</p>
@@ -93,7 +93,7 @@
               Lý do: {course.hidden_reason}. Học viên tạm thời không vào học được. Hãy chỉnh sửa nội dung rồi liên hệ quản trị viên để được hiện lại.
             </p>
           </div>
-        </div>
+        </section>
       ) : null}
 
       <p className="mb-6 rounded-md border border-dashed p-3 text-sm text-muted-foreground md:hidden">
```

- [ ] **Bước 4: Sửa E2E cũ cho khớp**

```diff
--- a/frontend/e2e/admin-data.ts
+++ b/frontend/e2e/admin-data.ts
@@ -9,6 +9,8 @@
   teacher_status: "pending",
   locked_at: null,
   review_note: null,
+  lock_reason: null,
+  email_verified: true,
   created_at: "2026-10-05T02:00:00Z",
   course_count: 0,
   enrollment_count: 0,
```

```diff
--- a/frontend/e2e/admin.spec.ts
+++ b/frontend/e2e/admin.spec.ts
@@ -152,7 +152,7 @@
     const hiddenCourse = courseDetail({ status: "archived", is_owner: true, hidden_reason: "Sao chép giáo trình" });
     await mockApi(page, { user: teacher, extra: { "GET /courses/giai-tich-1": (r) => r.fulfill({ json: hiddenCourse }) } });
     await page.goto("/teach/giai-tich-1");
-    await expect(page.getByRole("alert").filter({ hasText: "Quản trị viên đã ẩn khóa học này" })).toContainText("Sao chép giáo trình");
+    await expect(page.getByRole("region", { name: "Khóa học đã bị ẩn" })).toContainText("Sao chép giáo trình");
     await expect(page.getByText("Đã bị ẩn")).toBeVisible();
     await expect(page.getByRole("button", { name: "Xuất bản" })).toHaveCount(0);
     await expectAccessible(page);
```

- [ ] **Bước 5: Kiểm tra và commit**

```bash
npm run lint && npm run typecheck && npm test && npx playwright test
git add frontend && git commit -m "fix(web): verify link survives session restore, empty-page recovery, double-submit guard, focus after screen swap, CSV filename date"
git push
```

Expected: **102** unit test, **62** E2E pass; CI xanh.

**Lỗi Minor chưa sửa (ghi lại, làm sau nếu còn thời gian):**

- Câu hỏi đi kèm câu trả lời 👎 được tìm theo thời gian; nên lưu thẳng `question_id` trên tin trả lời.
- Bảng `email_outbox` chưa có dọn dẹp định kỳ (đã xóa nội dung mail xác nhận).
- Mở khóa tài khoản chưa gửi email báo.
- CSV cắt ở 10.000 dòng mà không báo.
- Giảng viên vẫn xóa được khóa bị ẩn khi chưa có học viên.
- Mục 👎 trong Thống kê chỉ hiện 20 mục đầu, và ẩn lỗi khi tải hỏng.
- Có thể làm mờ bảng khi đang tải tab mới (dữ liệu tab cũ hiện tạm).

---

## Task 17: Kiểm tra với backend thật và cập nhật spec

Task này **người dùng tự làm**, kiểm tra cả phần 1 và phần 2.

- [ ] `docker compose up -d --build`. Sau đó mở `http://localhost:8025` (Mailpit) ở một tab riêng.
- [ ] Tạo admin: `docker compose exec api python -m app.scripts.seed_admin --email admin@example.com --password Admin12345`.
- [ ] **Đăng ký học viên ở cửa sổ ẩn danh:**
  - Thấy màn "Kiểm tra hộp thư".
  - Thử đăng nhập ngay: thấy báo "cần xác nhận email", kèm nút gửi lại.
  - Mailpit có 2 mail; bấm link trong mail **cũ**: thấy "Link không dùng được".
  - Bấm link trong mail **mới**: thấy "Email đã được xác nhận". Đăng nhập được.
- [ ] **Đăng ký 2 giảng viên.** Trước khi họ xác nhận email: admin thấy họ ở tab "Chưa xác nhận email", Tổng quan ghi 0 chờ duyệt. Sau khi xác nhận: Mailpit có mail "Giảng viên mới chờ duyệt" gửi admin.
- [ ] **Admin:**
  - Duyệt người thứ nhất; từ chối người thứ hai, có lý do. Mailpit có mail duyệt và mail từ chối kèm lý do.
  - Giảng viên thứ hai bấm **Gửi lại yêu cầu duyệt** ở trang chủ: quay về hàng chờ, admin nhận mail.
- [ ] **Ẩn / hiện khóa học:** chủ khóa nhận 2 mail, link trong mail mở đúng trình soạn.
- [ ] **Khóa một học viên:** học viên nhận mail kèm lý do.
- [ ] **Người dùng › Học viên › Xuất CSV:** mở bằng Excel, tiếng Việt hiển thị đúng.
- [ ] **👎:** học viên bấm 👎 một câu trả lời của AI Tutor.
  - Admin thấy ô "Trả lời AI bị chê" = 1, mở trang danh sách thấy câu hỏi, câu trả lời và tên học viên.
  - Giảng viên mở Thống kê khóa: thấy mục đó nhưng **không có tên** học viên.
- [ ] Ẩn khóa: giảng viên mở trình soạn thấy khung "Quản trị viên đã ẩn khóa học này", không còn nút Xuất bản; khóa biến mất khỏi Khám phá. Admin bấm **Hiện lại**.
- [ ] Khóa một học viên đang đăng nhập ở cửa sổ khác: thao tác tiếp theo ở cửa sổ đó báo tài khoản bị khóa và đưa về trang đăng nhập. Mở khóa lại.
- [ ] **Nhật ký đầy đủ:** thấy đủ các thao tác vừa làm, có tên admin và lý do.
- [ ] Tổng quan: ô "Giảng viên chờ duyệt" có viền màu nhấn khi có người chờ; biểu đồ có cột ở ngày hôm nay.
- [ ] Ở khung 375px: menu dưới có Tổng quan / Người dùng / Khóa học / Tài khoản; bảng cuộn ngang được; trang không bị cuộn ngang.
- [ ] **(Tùy chọn) Brevo thật:**
  - Tạo tài khoản ở brevo.com.
  - **Senders, Domains & Dedicated IPs** → thêm và xác minh email gửi (ví dụ Gmail của bạn).
  - **SMTP & API** → tạo SMTP key.
  - Trong `backend/.env` đổi các dòng SMTP:
    ```bash
    SMTP_HOST=smtp-relay.brevo.com
    SMTP_PORT=587
    SMTP_STARTTLS=true
    SMTP_USER=<login SMTP Brevo>
    SMTP_PASSWORD=<SMTP key>
    MAIL_FROM="LMS-AI <email-đã-xác-minh@gmail.com>"
    ```
  - Chạy `docker compose up -d --force-recreate api worker`, rồi đăng ký bằng email thật của bạn. Nếu mail vào Spam thì bình thường với domain chưa có SPF/DKIM; khi có tên miền riêng (tầng S) thì xác thực domain trong Brevo.
- [ ] Cập nhật spec `docs/specs/2026-09-29-lms-ai-design.md`:
  - Đánh dấu xong **B8**.
  - Thêm nhật ký quyết định:

```markdown
| 2026-10-07 | Khu quản trị: ẩn khóa dùng lại status=archived + hidden_at/hidden_reason; từ chối chỉ áp cho giảng viên đang chờ, vi phạm sau khi duyệt thì khóa; mọi thao tác ghi admin_actions; seed_admin từ chối email `.local`. |
| 2026-10-07 | Email: xác nhận khi đăng ký (chặn đăng nhập tới khi xác nhận, gửi lại tối đa 3 lần/giờ, luôn 202); outbox ghi cùng transaction, worker gửi (kick + cron mỗi phút, SKIP LOCKED, thử lại 5 lần); dev dùng Mailpit, chạy thật dùng Brevo SMTP. Giảng viên chỉ vào hàng chờ khi đã xác nhận email. 👎 của AI Tutor: admin thấy tên học viên, giảng viên thì không. |
```

```bash
git add docs && git commit -m "docs: admin area and email done"
```

- [ ] **Plan tầng S:** thêm vào `.env.prod.example` các dòng `APP_BASE_URL=https://<domain>` và `SMTP_*` của Brevo. Thêm mục "Xác thực domain gửi mail (SPF/DKIM) trong Brevo" vào phần cấu hình DNS.

---

## Phụ lục: Ánh xạ yêu cầu → task

| Yêu cầu | Task |
|---|---|
| Danh sách giảng viên chờ duyệt, Duyệt / Từ chối (có lý do) | 2, 5, 6 |
| Danh sách giảng viên, học viên; tìm kiếm không dấu; khóa / mở khóa | 2, 5, 6 |
| Danh sách mọi khóa học; ẩn / hiện lại khóa vi phạm | 1, 2, 5, 6 |
| Số liệu tổng quan, người dùng mới 14 ngày, nhật ký quản trị | 1, 2, 5, 6 |
| Giảng viên thấy lý do bị từ chối; chủ khóa thấy lý do bị ẩn | 1, 7 |
| Admin vào thẳng `/admin`; sửa "Chào viên"; `seed_admin` chặn email `.local` | 3, 4, 7 |
| **Đăng ký phải xác nhận email thật** | 9, 10, 12 |
| **Email báo duyệt / từ chối / khóa / ẩn khóa; báo admin có giảng viên mới** | 9, 11 |
| **Giảng viên bị từ chối gửi lại yêu cầu** | 10, 13 |
| **Xuất CSV người dùng** | 11, 13 |
| **Hộp câu trả lời AI bị chê (admin + giảng viên)** | 11, 13 |
| Responsive 375/1280, WCAG AA | 8, 14, 16 |
| Sửa lỗi sau code review (outbox, lý do khóa, CSV injection, link xác nhận, phân trang, bấm đúp) | 15, 16 |

**Để sau:** quên mật khẩu (dùng lại bảng `email_tokens` với `purpose = "reset_password"`), đổi email.
