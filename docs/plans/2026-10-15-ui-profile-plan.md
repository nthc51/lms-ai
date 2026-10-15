# Giao diện mới, trang chủ cho khách, hồ sơ cá nhân và menu tài khoản: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:**

- **Giao diện:** bạn đã duyệt bản demo trang chủ màu dịu (nền xám trắng, xanh lá nhạt, nút teal, vàng bút dạ quang chỉ cho trích dẫn). Plan đưa bản đó vào Next.js và đổi màu, bo góc của cả app cho đồng bộ.
- **Tài khoản:** hiện chỉ có menu tài khoản ở góc trên các trang nằm trong khung app, và chỉ trên máy tính. Trang học bài, trang làm quiz, trang kết quả **không có** chỗ đăng xuất. Menu cũng **không có** lối vào hồ sơ, và **chưa có** chức năng sửa hồ sơ hay đổi mật khẩu. Đăng xuất từ trang có `RequireAuth` còn có thể bị chuyển sang `/login?next=…` thay vì về trang chủ.

**Mục tiêu:**

1. **Backend:**
   - `PATCH /api/v1/me` sửa họ tên (gọn khoảng trắng, 1–120 ký tự).
   - `POST /api/v1/me/password` đổi mật khẩu khi đang đăng nhập: phải đúng mật khẩu hiện tại và khác mật khẩu cũ; tối đa 10 lần thử mỗi giờ cho mỗi tài khoản. Đổi xong thì thu hồi **mọi** phiên cũ (máy khác phải đăng nhập lại), rồi cấp phiên mới cho chính trình duyệt đang dùng để người dùng không bị văng ra.
2. **Menu tài khoản ở mọi trang** (khung app, trang học, quiz, kết quả quiz; máy tính và điện thoại):
   - Đầu menu: tên, email, vai trò.
   - Các mục: **Hồ sơ cá nhân**, Ghi chú của tôi, chế độ màu, **Đăng xuất**.
   - Đăng xuất xong thì tải lại trang chủ.
3. **Trang Hồ sơ cá nhân** (`/account`, làm lại): sửa họ tên, đổi mật khẩu, chế độ màu, đăng xuất.
4. **Giao diện:**
   - Bảng màu sáng trung tính hơn: nền `#F3F4F1`, thẻ `#FCFCFA`.
   - Bo góc 4px.
   - Token mới `--mark` (vàng bút dạ quang) cho số trích dẫn `[n]`, ở cả 3 chế độ màu.
   - Font Be Vietnam Pro 800 cho tiêu đề lớn ở trang chủ.
5. **Trang chủ cho khách:** đúng như bản demo đã duyệt.
   - Trang toàn màn hình, không nằm trong khung app.
   - Phần "Thử hỏi" có 4 câu mẫu cố định, không gọi API. Câu ngoài tài liệu thì AI từ chối.
   - Hiệu ứng nhẹ, tắt khi người dùng bật giảm chuyển động.
   - Người đã đăng nhập vẫn thấy trang chủ cũ ("Chào An", khóa của tôi).

**Không đổi:**

- Không có migration.
- Email không sửa được (là tên đăng nhập đã xác nhận).
- Chế độ Tối dịu và Giấy giữ màu cũ, chỉ thêm `--mark`.
- Thanh dưới trên điện thoại vẫn có mục "Tài khoản".

**Thứ tự làm:** sau `2026-10-12-hybrid-quiz-timer-explain-plan.md`. Diff tạo trên HEAD `cbc735e`.

**Mã trong plan đã được chạy thử** trên HEAD `cbc735e`:

- **Backend:** **782 test pass** (776 cũ + 6 mới). `ruff check`, `ruff format --check` sạch, `lint-imports` 5 hợp đồng KEPT.
- **Frontend:** `tsc`, `eslint` sạch.
  - Unit test: **164 pass** (155 cũ + 9 mới).
  - E2E cả bộ: **95 pass + 1 bỏ qua có chủ ý** (87 cũ + 8 lượt mới; 375px và 1280px, có kiểm axe).
  - Đã chụp màn hình trang chủ, menu và trang Hồ sơ ở 1440px và 390px để soát.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6, nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng như các plan trước. Docker của bạn dùng pgvector 0.8, **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Cách áp diff như các plan trước: đường dẫn tính từ gốc repo, dùng `git apply --3way` hoặc sửa tay; file mới tạo đúng nội dung. Commit **không** thêm dòng `Co-Authored-By` hay `Claude-Session`.

### Hợp đồng API (tiền tố `/api/v1`)

| Endpoint | Hành vi |
|---|---|
| `PATCH /me` (mới) | Body `{full_name}`. Gọn khoảng trắng thừa, rỗng hoặc quá 120 ký tự thì **422**. Trả `UserOut`. Chưa đăng nhập thì **401** |
| `POST /me/password` (mới) | Body `{current_password, new_password}` (mật khẩu mới 8–128 ký tự, sai thì **422**). Sai mật khẩu hiện tại: **400 `WRONG_PASSWORD`**. Trùng mật khẩu cũ: **400 `SAME_PASSWORD`**. Quá 10 lần thử/giờ/tài khoản: **429 `RATE_LIMITED`** kèm `Retry-After`. Thành công: **200** `{access_token}` + cookie refresh mới; mọi refresh token cũ bị thu hồi |

Dùng **400** cho mật khẩu sai, không dùng 401: frontend gặp 401 sẽ tự refresh và gửi lại.

---

## Task 1: Backend: sửa hồ sơ, đổi mật khẩu

**Files:**
- Modify: `backend/app/modules/auth/schemas.py`, `service.py`, `router.py`
- Create: `backend/tests/test_profile.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`

- [x] **Bước 1: Test (sẽ fail)**

```python
"""Hồ sơ cá nhân: sửa họ tên, đổi mật khẩu khi đang đăng nhập."""

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.auth.models import RefreshToken
from tests.helpers import API, login, register_user

NEW_PASSWORD = "mat-khau-moi-123"


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def _active_sessions(user_id: str) -> int:
    async with SessionLocal() as db:
        return await db.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )


async def test_update_full_name_trims_spaces(client):
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    h = await login(client, "an@x.com")

    r = await client.patch(f"{API}/me", json={"full_name": "  Nguyễn   Văn  Bình "}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Nguyễn Văn Bình"
    assert (await client.get(f"{API}/me", headers=h)).json()["full_name"] == "Nguyễn Văn Bình"


async def test_update_full_name_rejects_blank_and_too_long(client):
    await register_user(client, "an@x.com")
    h = await login(client, "an@x.com")
    assert (await client.patch(f"{API}/me", json={"full_name": "   "}, headers=h)).status_code == 422
    assert (await client.patch(f"{API}/me", json={"full_name": "a" * 121}, headers=h)).status_code == 422


async def test_profile_endpoints_need_login(client):
    assert (await client.patch(f"{API}/me", json={"full_name": "X"})).status_code == 401
    r = await client.post(f"{API}/me/password", json={"current_password": "x", "new_password": NEW_PASSWORD})
    assert r.status_code == 401


async def test_change_password_keeps_this_browser_and_revokes_others(client):
    user = await register_user(client, "an@x.com")
    await login(client, "an@x.com")  # phiên trên "máy khác"
    h = await login(client, "an@x.com")  # phiên đang dùng; client giữ cookie refresh của phiên này
    assert await _active_sessions(user["id"]) == 2

    r = await client.post(
        f"{API}/me/password",
        json={"current_password": "password123", "new_password": NEW_PASSWORD},
        headers=h,
    )
    assert r.status_code == 200, r.text
    new_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get(f"{API}/me", headers=new_h)).status_code == 200
    assert "refresh_token=" in r.headers["set-cookie"]
    assert await _active_sessions(user["id"]) == 1  # chỉ còn phiên vừa cấp

    # cookie mới dùng được để refresh
    assert (await client.post(f"{API}/auth/refresh")).status_code == 200
    old = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": "password123"})
    assert _code(old) == (401, "INVALID_CREDENTIALS")
    assert (
        await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": NEW_PASSWORD})
    ).status_code == 200


async def test_change_password_wrong_current_or_same_or_short(client):
    user = await register_user(client, "an@x.com")
    h = await login(client, "an@x.com")

    wrong = await client.post(
        f"{API}/me/password",
        json={"current_password": "sai-mat-khau", "new_password": NEW_PASSWORD},
        headers=h,
    )
    assert _code(wrong) == (400, "WRONG_PASSWORD")
    same = await client.post(
        f"{API}/me/password",
        json={"current_password": "password123", "new_password": "password123"},
        headers=h,
    )
    assert _code(same) == (400, "SAME_PASSWORD")
    short = await client.post(
        f"{API}/me/password", json={"current_password": "password123", "new_password": "ngan"}, headers=h
    )
    assert short.status_code == 422
    assert await _active_sessions(user["id"]) == 1  # không lần nào ở trên thu hồi phiên


async def test_change_password_is_rate_limited_per_account(client):
    await register_user(client, "an@x.com")
    h = await login(client, "an@x.com")
    body = {"current_password": "sai-mat-khau", "new_password": NEW_PASSWORD}
    for _ in range(10):
        assert (await client.post(f"{API}/me/password", json=body, headers=h)).status_code == 400
    r = await client.post(f"{API}/me/password", json=body, headers=h)
    assert _code(r) == (429, "RATE_LIMITED")
    assert r.headers["retry-after"] == "3600"
```

Chạy: `cd backend; uv run pytest tests/test_profile.py -q`. Kỳ vọng fail (405 / 404 vì chưa có endpoint).

- [x] **Bước 2: Schema**

```diff
--- a/backend/app/modules/auth/schemas.py
+++ b/backend/app/modules/auth/schemas.py
@@ -51,6 +51,23 @@
     password: str = Field(min_length=8, max_length=128)
 
 
+class ProfileIn(BaseModel):
+    full_name: str = Field(min_length=1, max_length=120)
+
+    @field_validator("full_name")
+    @classmethod
+    def strip_name(cls, v: str) -> str:
+        v = " ".join(v.split())  # bỏ khoảng trắng thừa ở giữa và hai đầu
+        if not v:
+            raise ValueError("Họ tên không được để trống")
+        return v
+
+
+class ChangePasswordIn(BaseModel):
+    current_password: str = Field(min_length=1, max_length=128)
+    new_password: str = Field(min_length=8, max_length=128)
+
+
 class TokenOut(BaseModel):
     access_token: str
     token_type: str = "bearer"
```

- [x] **Bước 3: Service.** `db.refresh(user, with_for_update=True)` khóa dòng user, để hai lần đổi cùng lúc thì lần sau thấy mật khẩu mới. `issue_tokens` commit luôn mật khẩu mới và việc thu hồi phiên.

```diff
--- a/backend/app/modules/auth/service.py
+++ b/backend/app/modules/auth/service.py
@@ -279,6 +279,29 @@
     return user
 
 
+async def update_profile(db: AsyncSession, user: User, full_name: str) -> User:
+    user.full_name = full_name
+    await db.commit()
+    return user
+
+
+async def change_password(db: AsyncSession, user: User, current: str, new: str) -> tuple[str, str]:
+    """Đổi mật khẩu khi đang đăng nhập. Thu hồi MỌI phiên cũ (máy khác đang đăng nhập bị đăng xuất khi access
+    token hết hạn) rồi cấp phiên mới cho chính trình duyệt này để người dùng không bị văng ra."""
+    await db.refresh(user, with_for_update=True)  # hai lần đổi cùng lúc: lần sau thấy hash mới
+    if not verify_password(current, user.password_hash):
+        raise AppError("WRONG_PASSWORD", "Mật khẩu hiện tại không đúng", 400)
+    if verify_password(new, user.password_hash):
+        raise AppError("SAME_PASSWORD", "Mật khẩu mới phải khác mật khẩu hiện tại", 400)
+    user.password_hash = hash_password(new)
+    await db.execute(
+        update(RefreshToken)
+        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
+        .values(revoked_at=utcnow())
+    )
+    return await issue_tokens(db, user)  # commit luôn mật khẩu mới và việc thu hồi
+
+
 async def request_teacher_review(db: AsyncSession, user: User) -> User:
     """Giảng viên bị từ chối gửi lại yêu cầu duyệt: quay về hàng chờ, xóa lý do cũ, báo admin."""
     if user.role != Role.teacher or user.teacher_status != TeacherStatus.rejected:
```

- [x] **Bước 4: Router**

```diff
--- a/backend/app/modules/auth/router.py
+++ b/backend/app/modules/auth/router.py
@@ -9,8 +9,10 @@
 from app.modules.auth import service
 from app.modules.auth.models import User
 from app.modules.auth.schemas import (
+    ChangePasswordIn,
     ForgotPasswordIn,
     LoginIn,
+    ProfileIn,
     RegisterIn,
     ResendVerificationIn,
     ResetPasswordIn,
@@ -44,6 +46,7 @@
 RESEND_IP_LIMIT = 10  # mỗi IP tối đa 10 lần / giờ (chặn spam nhiều email khác nhau)
 RESET_LIMIT = 3  # quên mật khẩu: mỗi email tối đa 3 lần / giờ
 RESET_IP_LIMIT = 10  # và mỗi IP tối đa 10 lần / giờ
+PASSWORD_CHANGE_LIMIT = 10  # đổi mật khẩu: mỗi tài khoản tối đa 10 lần thử / giờ (chặn dò mật khẩu hiện tại)
 
 
 def _too_many(wait: int) -> AppError:
@@ -170,6 +173,30 @@
     return user
 
 
+@router.patch("/me", response_model=UserOut)
+async def update_me(
+    data: ProfileIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
+):
+    """Sửa hồ sơ (hiện chỉ có họ tên). Email không đổi được ở đây vì là tên đăng nhập đã xác nhận."""
+    return await service.update_profile(db, user, data.full_name)
+
+
+@router.post("/me/password", response_model=TokenOut)
+async def change_my_password(
+    data: ChangePasswordIn,
+    response: Response,
+    user: User = Depends(get_current_user),
+    db: AsyncSession = Depends(get_db),
+    limiter: RateLimiter = Depends(get_rate_limiter),
+):
+    """Đổi mật khẩu. 400 WRONG_PASSWORD / SAME_PASSWORD; 429 khi thử quá PASSWORD_CHANGE_LIMIT lần / giờ.
+    Mọi phiên khác bị thu hồi; trả access token mới và đặt cookie refresh mới cho trình duyệt này."""
+    await _limit(limiter, f"password-change:{user.id}", PASSWORD_CHANGE_LIMIT)
+    access, raw = await service.change_password(db, user, data.current_password, data.new_password)
+    set_refresh_cookie(response, raw)
+    return TokenOut(access_token=access)
+
+
 @router.post("/auth/refresh", response_model=TokenOut)
 async def refresh(
     response: Response, refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)
```

- [x] **Bước 5: Chạy test, kiểu API cho frontend, commit**

```powershell
uv run pytest tests/test_profile.py -q          # 6 pass
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
uv run pytest -q                                 # cả bộ
cd ..\frontend; npm run gen:api                  # schema.d.ts có PATCH /api/v1/me, /api/v1/me/password, ProfileIn, ChangePasswordIn
cd ..
git add backend frontend/openapi.json frontend/src/lib/api/schema.d.ts
git commit -m "feat(auth): sửa họ tên và đổi mật khẩu khi đang đăng nhập"
```

---

## Task 2: Giao diện mới và trang chủ cho khách

**Files:**
- Modify: `frontend/src/app/globals.css`, `frontend/src/app/layout.tsx`, `frontend/src/components/tutor/citation-chip.tsx`
- Create: `frontend/src/components/landing/landing-data.ts`, `landing.tsx`, `landing.css`
- Modify: `frontend/src/app/(main)/page.tsx`, `frontend/src/components/app/app-shell.tsx`
- Create: `frontend/e2e/landing.spec.ts`
- Modify: `docs/design/design-system.md`

- [ ] **Bước 1: Màu, bo góc, `--mark`.**
  - Màu sáng mới đều đạt chuẩn AA. Đã tính lại: chữ/nền 13.27, chữ phụ 5.68, màu chính 5.53, chữ trên nút 6.10, màu nhấn 4.70, đỏ 5.95, xanh lá 4.56.
  - Chữ trên `--mark` đạt 11.8 (sáng), 10.7 (tối), 8.9 (giấy).
  - Các class `rounded-md` / `rounded-lg` sẵn có tự nhỏ lại vì đọc `--radius`.

```diff
--- a/frontend/src/app/globals.css
+++ b/frontend/src/app/globals.css
@@ -3,21 +3,25 @@
 
 @custom-variant dark (&:is(.dark *));
 
-/* ---- Design tokens (docs/design/design-system.md §2) ---- */
+/* ---- Design tokens (docs/design/design-system.md §2) ----
+   2026-10-15: bảng màu sáng trung tính hơn (nền xám trắng thay màu giấy ấm, teal giữ nguyên), góc bo nhỏ 4px,
+   thêm --mark (vàng bút dạ quang) chỉ dùng cho số trích dẫn và dòng tài liệu được tô. */
 :root {
-  --background: #f7f5f0;
-  --surface: #fffdf9;
+  --background: #f3f4f1;
+  --surface: #fcfcfa;
   --foreground: #24292f;
-  --muted-foreground: #5b6470;
-  --border: #e3ded4;
-  --muted: #efebe3;
+  --muted-foreground: #59616b;
+  --border: #dfe2dc;
+  --muted: #e7eae5;
   --primary: #0f6e66;
   --primary-foreground: #ffffff;
   --accent: #a15c07;
   --success: #2f7d4f;
   --destructive: #b42318;
   --ring: #0f6e66;
-  --radius: 10px;
+  --mark: #ffe68f;
+  --mark-foreground: #24292f;
+  --radius: 4px;
   --reader-size: 17px;
 }
 
@@ -34,6 +38,8 @@
   --success: #7cc49a;
   --destructive: #f2867a;
   --ring: #5fbfb3;
+  --mark: #e3c55a;
+  --mark-foreground: #1a1608;
   color-scheme: dark;
 }
 
@@ -50,6 +56,8 @@
   --success: #3b6e45;
   --destructive: #a3321f;
   --ring: #2f6b5e;
+  --mark: #f2d36b;
+  --mark-foreground: #3a2f24;
 }
 
 @theme inline {
@@ -65,8 +73,10 @@
   --color-success: var(--success);
   --color-destructive: var(--destructive);
   --color-ring: var(--ring);
+  --color-mark: var(--mark);
+  --color-mark-foreground: var(--mark-foreground);
   --radius-lg: var(--radius);
-  --radius-md: 8px;
+  --radius-md: var(--radius);
   --font-sans: "Be Vietnam Pro", system-ui, sans-serif;
   --font-reading: "Noto Sans Variable", "Noto Sans", system-ui, sans-serif;
   --font-mono: "JetBrains Mono Variable", ui-monospace, monospace;
```

```diff
--- a/frontend/src/app/layout.tsx
+++ b/frontend/src/app/layout.tsx
@@ -1,6 +1,7 @@
 import "@fontsource/be-vietnam-pro/400.css";
 import "@fontsource/be-vietnam-pro/500.css";
 import "@fontsource/be-vietnam-pro/600.css";
+import "@fontsource/be-vietnam-pro/800.css";
 import "@fontsource-variable/noto-sans";
 import "@fontsource-variable/jetbrains-mono";
 import type { Metadata, Viewport } from "next";
@@ -14,7 +15,7 @@
 
 export const viewport: Viewport = {
   themeColor: [
-    { media: "(prefers-color-scheme: light)", color: "#f7f5f0" },
+    { media: "(prefers-color-scheme: light)", color: "#f3f4f1" },
     { media: "(prefers-color-scheme: dark)", color: "#171a1e" },
   ],
 };
```

- [ ] **Bước 2: Số trích dẫn `[n]` dùng nền `--mark`.** Áp cho cả AI Tutor, Studio và ghi chú (cùng component). Khi hover thì chuyển sang màu chính.

```diff
--- a/frontend/src/components/tutor/citation-chip.tsx
+++ b/frontend/src/components/tutor/citation-chip.tsx
@@ -45,7 +45,7 @@
         <button
           type="button"
           aria-label={`Nguồn ${n}${where ? `, ${where}` : ""}`}
-          className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border border-accent/50 px-1 align-text-top text-xs font-medium text-accent hover:bg-accent/10"
+          className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-sm bg-mark px-1 align-text-top text-xs font-semibold text-mark-foreground transition-colors duration-150 hover:bg-primary hover:text-primary-foreground"
         >
           {n}
         </button>
```

- [ ] **Bước 3: Nội dung mẫu của phần "Thử hỏi".** Bốn câu cố định, không gọi API. Các thẻ `<sub>` / `<span class="hl">` trong chuỗi do code viết sẵn (không phải dữ liệu người dùng), nên dùng `dangerouslySetInnerHTML` được.

```ts
/**
 * Nội dung mẫu cho phần "Thử hỏi" ở trang chủ: 4 câu hỏi về một bài Kỹ thuật truyền thông, trả lời theo
 * đúng cách AI Tutor hiển thị (đoạn văn có [n], danh sách nguồn có số trang, đoạn tài liệu được dùng).
 * Đây là ví dụ cố định để khách xem trước, không gọi API. Thay bằng nội dung khóa học thật nếu muốn.
 * Chuỗi có thẻ <sub>/<span class="hl"> do code này tự viết (không phải dữ liệu người dùng).
 */
export type SampleKey = "am" | "shannon" | "noise" | "ticket";

export type SampleAnswer = {
  label: string;
  question: string;
  paragraphs?: string[];
  sources?: { title: string; page: number }[];
  excerpt?: { page: number; html: string };
  refusal?: string;
  followups: string[];
};

export const SAMPLES: Record<SampleKey, SampleAnswer> = {
  am: {
    label: "Điều chế AM",
    question: "Điều chế AM là gì, băng thông bao nhiêu?",
    paragraphs: [
      "Điều chế biên độ (AM) thay đổi biên độ của sóng mang theo tín hiệu tin tức, còn tần số và pha của sóng mang giữ nguyên [1].",
      "Phổ tín hiệu AM gồm sóng mang và hai dải biên đối xứng quanh tần số sóng mang, nên băng thông bằng hai lần tần số cao nhất của tín hiệu tin tức [2].",
    ],
    sources: [
      { title: "Chương 3 · Điều chế biên độ", page: 47 },
      { title: "Chương 3 · Phổ của tín hiệu AM", page: 49 },
    ],
    excerpt: {
      page: 49,
      html: 'Phổ của tín hiệu AM gồm thành phần sóng mang tại f<sub>c</sub> và hai dải biên. <span class="hl">Băng thông của tín hiệu AM bằng 2·f<sub>max</sub></span>, trong đó f<sub>max</sub> là tần số cao nhất của tín hiệu tin tức.',
    },
    followups: ["So sánh AM với FM?", "Chỉ số điều chế là gì?"],
  },
  shannon: {
    label: "Dung lượng kênh",
    question: "Dung lượng kênh phụ thuộc vào những gì?",
    paragraphs: [
      "Theo định lý Shannon–Hartley, dung lượng kênh C = B·log<sub>2</sub>(1 + S/N): tăng tỉ lệ thuận với băng thông B và tăng theo log của tỉ số tín hiệu trên nhiễu [1].",
      "Ví dụ trong bài: kênh thoại rộng 3,1 kHz với S/N = 30 dB có dung lượng khoảng 30,9 kbit/s [2].",
    ],
    sources: [
      { title: "Chương 2 · Dung lượng kênh", page: 31 },
      { title: "Chương 2 · Ví dụ kênh thoại", page: 32 },
    ],
    excerpt: {
      page: 31,
      html: 'Với kênh có nhiễu Gauss trắng cộng, <span class="hl">dung lượng kênh C = B·log<sub>2</sub>(1 + S/N)</span> (bit/s), trong đó B là băng thông và S/N là tỉ số công suất tín hiệu trên nhiễu.',
    },
    followups: ["30 dB đổi ra S/N là bao nhiêu?", "Giới hạn Shannon là gì?"],
  },
  noise: {
    label: "Nhiễu trắng",
    question: "Nhiễu trắng là gì?",
    paragraphs: [
      "Nhiễu trắng có mật độ phổ công suất như nhau ở mọi tần số, thường viết là N<sub>0</sub>/2 [1].",
      "Nhiễu nhiệt trong máy thu được mô hình hóa là nhiễu Gauss trắng cộng (AWGN) khi phân tích hệ thống [2].",
    ],
    sources: [
      { title: "Chương 2 · Các loại nhiễu", page: 22 },
      { title: "Chương 2 · Mô hình kênh AWGN", page: 24 },
    ],
    excerpt: {
      page: 22,
      html: '<span class="hl">Nhiễu trắng là nhiễu có mật độ phổ công suất không đổi trên toàn bộ dải tần</span>, ký hiệu N<sub>0</sub>/2 (W/Hz) với phổ hai phía.',
    },
    followups: ["Nhiễu nhiệt phụ thuộc nhiệt độ thế nào?", "AWGN là gì?"],
  },
  ticket: {
    label: "Giá vé tàu",
    question: "Giá vé tàu Hà Nội – Sài Gòn bao nhiêu?",
    refusal:
      "Tài liệu của khóa Kỹ thuật truyền thông không nói đến giá vé tàu, nên mình không trả lời được câu này. Bạn có thể hỏi về nội dung trong bài, ví dụ điều chế, nhiễu hay dung lượng kênh.",
    followups: ["Điều chế FM khác AM thế nào?", "Tỉ số S/N là gì?"],
  },
};

export const SAMPLE_KEYS = Object.keys(SAMPLES) as SampleKey[];
```

- [ ] **Bước 4: Trang chủ cho khách.** Đây là bản demo đã duyệt, chuyển sang React:
  - **Ngăn ảnh hưởng tới app:** toàn bộ CSS nằm dưới `.landing` và có màu cố định (trang chủ luôn sáng). Font lấy Be Vietnam Pro đã nạp sẵn.
  - **Chuyển động:** chỉ dùng `transform` / `opacity`, có nhánh `prefers-reduced-motion`.
  - **Khi tắt JavaScript:** nội dung vẫn hiện đủ, vì class `is-js` chỉ được thêm khi script chạy.

```tsx
"use client";

import Link from "next/link";
import * as React from "react";
import { SAMPLE_KEYS, SAMPLES, type SampleKey } from "./landing-data";
import "./landing.css";

/** Độ trễ xuất hiện theo thứ tự trong một mục (CSS: transition-delay = --d × 80ms). */
const d = (n: number) => ({ "--d": n }) as React.CSSProperties;
const lineDelay = (n: number) => ({ "--i": n }) as React.CSSProperties;

const QUIZ_TOTAL = 300;
const QUIZ_START = 252;

/** Đồng hồ quiz minh họa: đếm ngược 04:12 rồi quay lại, dừng khi tab ẩn hoặc người dùng giảm chuyển động. */
function useDemoClock() {
  const [left, setLeft] = React.useState(QUIZ_START);
  React.useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      if (!document.hidden) setLeft((v) => (v > 0 ? v - 1 : QUIZ_START));
    }, 1000);
    return () => window.clearInterval(id);
  }, []);
  const text = `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
  return { text, ratio: left / QUIZ_TOTAL };
}

/** Hiện dần từng phần khi cuộn tới (một lần). Không có JS / IntersectionObserver thì mọi thứ hiện sẵn. */
function useReveal(root: React.RefObject<HTMLDivElement | null>) {
  React.useEffect(() => {
    const el = root.current;
    if (!el) return;
    el.classList.add("is-js");
    const targets = el.querySelectorAll("[data-reveal]");
    if (!("IntersectionObserver" in window)) {
      targets.forEach((t) => t.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries)
          if (e.isIntersecting) {
            e.target.classList.add("is-in");
            io.unobserve(e.target);
          }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.1 },
    );
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, [root]);
}

function Timer({ clock }: { clock: { text: string } }) {
  return <span className="timer">{clock.text}</span>;
}

function TimeBar({ ratio }: { ratio: number }) {
  return (
    <div className="timebar">
      <i style={{ transform: `scaleX(${ratio})`, transition: "transform 1s linear" }} />
    </div>
  );
}

const withCites = (p: string) => p.replace(/\[(\d)\]/g, (_, n) => `<a class="cite" href="#lp-ex">${n}</a>`);

/** Phần "Thử hỏi": chọn một câu, xem câu trả lời kèm số trang và đoạn tài liệu được dùng. */
function TrySheet() {
  const [key, setKey] = React.useState<SampleKey>("am");
  const [shown, setShown] = React.useState<SampleKey>("am");
  const [fading, setFading] = React.useState(false);
  const excerpt = React.useRef<HTMLDivElement>(null);
  const s = SAMPLES[shown];

  function choose(k: SampleKey) {
    setKey(k);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(k);
      return;
    }
    setFading(true);
    window.setTimeout(() => {
      setShown(k);
      setFading(false);
    }, 200);
  }

  function onSheetClick(e: React.MouseEvent) {
    const target = (e.target as HTMLElement).closest(".cite, .source a");
    if (!target || !excerpt.current) return;
    e.preventDefault();
    excerpt.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    excerpt.current.animate([{ transform: "translateY(8px)", opacity: 0.4 }, { transform: "none", opacity: 1 }], {
      duration: 400,
      easing: "cubic-bezier(.16,1,.3,1)",
    });
  }

  return (
    <section className="try" id="thu" aria-labelledby="h-try">
      <div className="try-index">
        <h2 className="sr-only" id="h-try">
          Thử hỏi AI Tutor
        </h2>
        <div className="try-names" role="group" aria-label="Chọn một câu hỏi">
          {SAMPLE_KEYS.map((k) => (
            <button key={k} type="button" aria-pressed={key === k} onClick={() => choose(k)}>
              {SAMPLES[k].label}
            </button>
          ))}
        </div>
        <div className="try-note" data-reveal>
          <p>Bốn câu hỏi về bài Kỹ thuật truyền thông. Bấm số trong ô vàng để xem đoạn tài liệu được dùng.</p>
          <p>Câu cuối nằm ngoài tài liệu, nên AI nói thẳng là không có.</p>
        </div>
      </div>
      <div className="stage">
        {/* onClick chỉ bắt click của các liên kết [n] / "Mở PDF" bên trong (bàn phím: Enter trên liên kết cũng là click) */}
        <article className={fading ? "sheet fading" : "sheet"} data-ui aria-live="polite" onClick={onSheetClick}>
          <div className="sheet-head">
            <span>AI Tutor · Kỹ thuật truyền thông</span>
            <span>Phạm vi: cả khóa</span>
          </div>
          <div className="q-bubble">{s.question}</div>
          <div className="answer">
            {s.refusal ? (
              <p className="refuse">{s.refusal}</p>
            ) : (
              s.paragraphs?.map((p) => <p key={p} dangerouslySetInnerHTML={{ __html: withCites(p) }} />)
            )}
          </div>
          {s.sources ? (
            <div className="sources">
              {s.sources.map((src, i) => (
                <div className="source" key={src.page}>
                  <span className="cite">{i + 1}</span>
                  <span>{src.title}</span>
                  <a href="#lp-ex">Mở PDF trang {src.page}</a>
                </div>
              ))}
            </div>
          ) : null}
          {s.excerpt ? (
            <div className="excerpt" id="lp-ex" ref={excerpt}>
              <div className="ex-top">
                <span>Đoạn được dùng</span>
                <span>trang {s.excerpt.page}</span>
              </div>
              <p dangerouslySetInnerHTML={{ __html: s.excerpt.html }} />
            </div>
          ) : null}
          <div className="followups">
            {s.followups.map((f) => (
              <span key={f}>{f}</span>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}

/** Trang chủ cho khách: giới thiệu AI Tutor trả lời theo tài liệu và ghi số trang. */
export function Landing() {
  const root = React.useRef<HTMLDivElement>(null);
  const clock = useDemoClock();
  useReveal(root);

  return (
    <div className="landing" ref={root}>
      <header className="mast">
        <div className="bar">
          <Link className="wordmark" href="/" aria-label="LMS-AI, trang chủ">
            LMS-AI
          </Link>
          <nav className="tab" aria-label="Trang chủ">
            <a href="#thu">Thử hỏi</a>
            <a href="#cach">Cách hoạt động</a>
            <a href="#giang-vien">Cho giảng viên</a>
          </nav>
          <div className="bar-end">
            <Link className="link hide-s" href="/login">
              Đăng nhập
            </Link>
            <Link className="link" href="/register">
              Tạo tài khoản
            </Link>
          </div>
        </div>

        <div className="mosaic" aria-hidden="true">
          <div className="cell c-a">
            <div className="ui-slide" data-ui>
              <div className="s-top">
                <span>Kỹ thuật truyền thông · Chương 3</span>
                <span>trang 49</span>
              </div>
              <h4>Phổ của tín hiệu AM</h4>
              <ul>
                <li>Gồm sóng mang và hai dải biên đối xứng</li>
                <li>
                  <span className="hl sweep" data-reveal>
                    Băng thông B = 2·f<sub>max</sub>
                  </span>{" "}
                  của tín hiệu tin tức
                </li>
                <li>Hiệu suất công suất thấp khi chỉ số điều chế nhỏ</li>
              </ul>
            </div>
          </div>
          <div className="cell c-b">
            <span className="big-num">trang 49</span>
            <span className="tile-note">là nơi câu trả lời lấy ra</span>
          </div>
          <div className="cell c-c">
            <div className="ui-chat" data-ui>
              <div className="q-bubble">Băng thông của AM bằng bao nhiêu?</div>
              <div className="a-text">
                Bằng hai lần tần số cao nhất của tín hiệu tin tức <span className="cite">2</span>
              </div>
              <div className="src-line">
                <span className="cite">2</span>
                <span>Chương 3 · trang 49 · Mở PDF</span>
              </div>
            </div>
          </div>
          <div className="cell c-d">
            <span className="big-num">174</span>
            <span className="tile-note">trang slide đọc xong trong khoảng 90 giây</span>
          </div>
          <div className="cell c-e">
            <span className="tile-note tile-formula">
              N<sub>0</sub>/2
            </span>
          </div>
          <div className="cell c-f">
            <span className="tile-note">Sáng, tối hoặc giấy</span>
          </div>
          <div className="cell c-h">
            <div className="ui-quiz" data-ui>
              <div className="quiz-top">
                <span>Câu 3/10</span>
                <Timer clock={clock} />
              </div>
              <TimeBar ratio={clock.ratio} />
              <div>Tín hiệu AM có băng thông bằng?</div>
              <div className="opt">
                <b>A</b>
                <span>
                  f<sub>max</sub>
                </span>
              </div>
              <div className="opt on">
                <b>B</b>
                <span>
                  2·f<sub>max</sub>
                </span>
              </div>
              <div className="opt">
                <b>C</b>
                <span>
                  4·f<sub>max</sub>
                </span>
              </div>
            </div>
          </div>
          <div className="cell c-i">
            <span className="tile-note">Giảng viên duyệt từng câu hỏi</span>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="hero" aria-labelledby="h-hero">
          <div className="hero-left after-lines">
            <p className="standfirst">
              AI Tutor chỉ trả lời từ tài liệu giảng viên tải lên, và ghi rõ trang để bạn mở ra kiểm.
            </p>
            <div className="actions">
              <a className="btn" href="#thu">
                Thử hỏi một câu
              </a>
              <a className="link" href="#cach">
                Xem cách hoạt động
              </a>
            </div>
          </div>
          <h1 className="lines" id="h-hero">
            <span className="line">
              <span data-line style={lineDelay(0)}>
                Hỏi bài,
              </span>
            </span>
            <span className="line">
              <span data-line style={lineDelay(1)}>
                có số trang.
              </span>
            </span>
          </h1>
        </section>

        <TrySheet />

        <section className="how" id="cach" aria-labelledby="h-how">
          <h2 id="h-how" data-reveal>
            Tải lên một lần, hỏi cả kỳ
          </h2>
          <div className="stages" data-ui>
            <div className="stage-seg seg-1" data-reveal style={d(1)}>
              Vài giây<small>Trước tiên, giảng viên tải PDF bài giảng lên bài học.</small>
            </div>
            <div className="stage-seg seg-2" data-reveal style={d(2)}>
              Khoảng 90 giây<small>Sau đó hệ thống đọc từng trang, kể cả trang ảnh và công thức.</small>
            </div>
            <div className="stage-seg seg-3" data-reveal style={d(3)}>
              Cả học kỳ<small>Rồi học viên hỏi, làm quiz và ôn thẻ trên đúng tài liệu ấy.</small>
            </div>
          </div>
          <div className="stage-notes">
            <p className="n1" data-reveal style={d(1)}>
              Trước tiên, giảng viên tải PDF bài giảng lên bài học.
            </p>
            <p className="n2" data-reveal style={d(2)}>
              Sau đó hệ thống đọc từng trang, kể cả trang ảnh và công thức, rồi chia thành đoạn để tìm.
            </p>
            <p className="n3" data-reveal style={d(3)}>
              Rồi học viên hỏi, làm quiz và ôn thẻ trên đúng tài liệu ấy. Tìm được cả khi gõ không dấu.
            </p>
          </div>
        </section>

        <section className="feat" aria-labelledby="h-feat">
          <div className="feat-intro">
            <h2 id="h-feat" data-reveal>
              Ôn ngay trong bài học
            </h2>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Giảng viên đặt từ 1 đến 240 phút<span>Hết giờ bài tự nộp, kể cả khi đã đóng tab</span>
            </p>
            <div>
              <h3 data-reveal>Quiz có đồng hồ</h3>
              <p data-reveal style={d(1)}>
                Mỗi người nhận câu hỏi theo một thứ tự riêng, tải lại trang vẫn giữ nguyên. Đồng hồ chạy theo giờ
                máy chủ, nên không ai “dừng giờ” được.
              </p>
            </div>
            <figure data-reveal style={d(2)}>
              <div className="frag f1" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Kiểm tra chương 3</span>
                    <Timer clock={clock} />
                  </div>
                  <TimeBar ratio={clock.ratio} />
                  <div className="frag-q">Câu 3/10 · Tín hiệu AM có băng thông bằng?</div>
                  <div className="opt">
                    <b>A</b>
                    <span>
                      f<sub>max</sub>
                    </span>
                  </div>
                  <div className="opt on">
                    <b>B</b>
                    <span>
                      2·f<sub>max</sub>
                    </span>
                  </div>
                  <div className="opt">
                    <b>C</b>
                    <span>
                      4·f<sub>max</sub>
                    </span>
                  </div>
                  <div className="opt">
                    <b>D</b>
                    <span>Bằng tần số sóng mang</span>
                  </div>
                  <div className="frag-foot">
                    <span>Đã lưu tự động</span>
                    <span>Câu tiếp</span>
                  </div>
                </div>
              </div>
              <figcaption className="sr-only">Màn hình làm quiz có đồng hồ đếm ngược</figcaption>
            </figure>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Dựa trên đoạn tài liệu đã sinh ra câu hỏi<span>Giải thích một lần, lần sau mở lại ngay</span>
            </p>
            <div>
              <h3 data-reveal>Giải thích câu sai</h3>
              <p data-reveal style={d(1)}>
                Nộp bài xong, bấm vào câu làm sai hoặc bỏ trống. AI nói vì sao đáp án kia đúng, kèm trang tài liệu
                để đọc lại.
              </p>
            </div>
            <figure className="r2" data-reveal style={d(2)}>
              <div className="frag f2" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Kết quả · 7/10</span>
                    <span className="frag-meta">Nộp lúc 09:41</span>
                  </div>
                  <div className="res-row">
                    <span>Câu 2 · Hiệu suất AM</span>
                    <em>Đúng</em>
                  </div>
                  <div className="res-row bad">
                    <span>Câu 3 · Băng thông AM</span>
                    <em>Sai</em>
                  </div>
                  <div className="ai-explain">
                    <b>AI giải thích</b>Phổ AM có hai dải biên đối xứng quanh f<sub>c</sub>, mỗi dải rộng f
                    <sub>max</sub>, nên băng thông là 2·f<sub>max</sub> chứ không phải f<sub>max</sub>.{" "}
                    <span className="cite">tr. 49</span>
                  </div>
                </div>
              </div>
              <figcaption className="sr-only">Trang kết quả quiz có phần AI giải thích</figcaption>
            </figure>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Phím cách để lật, N là chưa nhớ, C là đã nhớ<span>Soạn một lần, dùng chung cả lớp</span>
            </p>
            <div>
              <h3 data-reveal>Thẻ ôn và đề cương</h3>
              <p data-reveal style={d(1)}>
                Studio soạn đề cương, bản tóm tắt và bộ thẻ ghi nhớ từ tài liệu của bài. Mỗi ý đều có số trang, bấm
                vào là mở đúng chỗ.
              </p>
            </div>
            <figure data-reveal style={d(2)}>
              <div className="frag f3" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Thẻ 4/18</span>
                    <span className="frag-meta">Đã nhớ 3</span>
                  </div>
                  <div className="fc-card">Mật độ phổ công suất của nhiễu trắng?</div>
                  <div className="fc-keys">
                    <span>
                      <kbd>Space</kbd> lật
                    </span>
                    <span>
                      <kbd>N</kbd> chưa nhớ
                    </span>
                    <span>
                      <kbd>C</kbd> đã nhớ
                    </span>
                  </div>
                </div>
              </div>
              <figcaption className="sr-only">Một thẻ ghi nhớ trong Studio</figcaption>
            </figure>
          </div>

          <div className="row">
            <p className="side" data-reveal>
              Chọn từ hai ghi chú trở lên<span>Ghi chú lưu theo từng bài, xem lại ở trang Ghi chú</span>
            </p>
            <div>
              <h3 data-reveal>Gộp ghi chú</h3>
              <p data-reveal style={d(1)}>
                Lưu câu trả lời hay vào ghi chú ngay trong cuộc hỏi đáp. Trước kỳ thi, chọn vài ghi chú và để AI gộp
                lại thành một đề cương ôn tập.
              </p>
            </div>
            <figure className="r2" data-reveal style={d(2)}>
              <div className="frag f4" data-ui>
                <div className="fpad">
                  <div className="quiz-top">
                    <span>Ghi chú của tôi</span>
                    <span className="frag-meta">Đã chọn 2</span>
                  </div>
                  <div className="note-item">
                    <i />
                    <span>
                      Băng thông AM = 2·f<sub>max</sub>, trang 49
                    </span>
                  </div>
                  <div className="note-item">
                    <i />
                    <span>
                      Shannon: C = B·log<sub>2</sub>(1 + S/N), trang 31
                    </span>
                  </div>
                  <div className="note-item off">
                    <i />
                    <span>AWGN là mô hình của nhiễu nhiệt, trang 24</span>
                  </div>
                  <span className="mini-btn">Tạo đề cương từ 2 ghi chú</span>
                </div>
              </div>
              <figcaption className="sr-only">Trang ghi chú, chọn hai ghi chú để tạo đề cương</figcaption>
            </figure>
          </div>
        </section>

        <section className="teach" id="giang-vien" aria-labelledby="h-teach">
          <h2 id="h-teach" data-reveal>
            Giảng viên duyệt trước
          </h2>
          <p className="lead" data-reveal style={d(1)}>
            Câu hỏi do AI soạn chỉ đến tay học viên sau khi giảng viên đọc, sửa hoặc loại bỏ. Bản đề cương đã sửa
            mang nhãn “Giảng viên đã duyệt” và không bị ghi đè khi tài liệu thay đổi.
          </p>
          <div className="teach-grid">
            <figure className="t-photo" data-reveal>
              <div className="review" data-ui>
                <div className="rv-head">
                  <span>Câu hỏi chờ duyệt · Chương 3</span>
                  <span className="badge-ok">8 câu</span>
                </div>
                <div className="rv-q">
                  <p>Khi chỉ số điều chế bằng 1, công suất hai dải biên chiếm bao nhiêu phần tổng công suất AM?</p>
                  <ol className="rv-opts">
                    <li>A. 1/2</li>
                    <li className="ok">B. 1/3</li>
                    <li>C. 2/3</li>
                    <li>D. 1/4</li>
                  </ol>
                </div>
                <div className="rv-src">Lấy từ trang 50 · Độ khó: trung bình</div>
                <div className="rv-actions">
                  <span>Duyệt</span>
                  <span>Sửa</span>
                  <span>Loại</span>
                </div>
                <div className="rv-q rv-done">
                  <p>
                    Đề cương chương 3 · Điều chế biên độ <span className="badge-ok">Giảng viên đã duyệt</span>
                  </p>
                  <span className="frag-meta">Sửa lúc 14:20 · 6 mục · mỗi mục có số trang</span>
                </div>
              </div>
              <p className="t-over">
                Mỗi câu ghi trang mà AI đã dựa vào. Câu nào AI tự kiểm thấy nghi sai được gắn cờ để giảng viên xem kỹ.
              </p>
            </figure>
            <div className="t-side" data-reveal style={d(2)}>
              <div className="t-tile" aria-hidden="true">
                <svg viewBox="0 0 120 160">
                  <path d="M0 0h86l34 34v126H0z" fill="#fff" />
                  <path d="M86 0v34h34z" fill="#16181b" />
                  <g fill="#16181b" opacity=".18">
                    <rect x="14" y="22" width="56" height="7" />
                    <rect x="14" y="44" width="90" height="5" />
                    <rect x="14" y="56" width="84" height="5" />
                    <rect x="14" y="68" width="90" height="5" />
                    <rect x="14" y="104" width="78" height="5" />
                    <rect x="14" y="116" width="90" height="5" />
                    <rect x="14" y="128" width="60" height="5" />
                  </g>
                  <rect x="12" y="84" width="92" height="9" fill="#ffe68f" />
                  <circle cx="106" cy="88.5" r="6" fill="#16181b" />
                </svg>
              </div>
              <dl className="facts">
                <div>
                  <dt>Trang đọc được</dt>
                  <dd>174 trong khoảng 90 giây</dd>
                </div>
                <div>
                  <dt>Đoạn tìm cho mỗi câu hỏi</dt>
                  <dd>6 đoạn</dd>
                </div>
                <div>
                  <dt>Lượt tạo trong Studio</dt>
                  <dd>10 mỗi giờ</dd>
                </div>
                <div>
                  <dt>Chế độ đọc</dt>
                  <dd>Sáng, tối, giấy</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>

        <section className="close" aria-labelledby="h-close">
          <h2 id="h-close" data-reveal>
            Câu nào cũng
            <br />
            có trang.
          </h2>
          <div className="close-foot">
            <p data-reveal style={d(1)}>
              Tạo tài khoản học viên, vào khóa học và hỏi ngay bên cạnh bài giảng.
            </p>
            <Link className="btn" href="/register" data-reveal style={d(2)}>
              Tạo tài khoản
            </Link>
          </div>
        </section>
      </main>

      <footer className="foot">
        <div className="foot-top">
          <div className="foot-notes">
            <p>
              <b>LMS-AI</b>Đồ án tốt nghiệp, nền tảng học trực tuyến có AI Tutor.
            </p>
            <p>Khóa học, bài giảng PDF và video, quiz, Studio, ghi chú, trang quản trị.</p>
          </div>
          <a className="link" href="#main">
            Về đầu trang
          </a>
        </div>
        <Link className="contact" href="/explore">
          <span>Khám phá</span>
          <span>khóa học</span>
        </Link>
        <div className="meta">
          <nav aria-label="Liên kết cuối trang">
            <Link className="link" href="/login">
              Đăng nhập
            </Link>
            <Link className="link" href="/register">
              Đăng ký
            </Link>
          </nav>
          <p>Chữ: Be Vietnam Pro</p>
          <p>Việt Nam, 2026</p>
        </div>
      </footer>
    </div>
  );
}
```

```css
/* Trang chủ cho khách (components/landing/landing.tsx). Mọi quy tắc nằm dưới .landing để không ảnh hưởng
   phần còn lại của app. Màu cố định (trang chủ luôn sáng), không theo chế độ màu của app. */
.landing{
  --bg:#f3f4f1; --surface:#e7eae5; --ink:#16181b; --muted:#59616b;
  --accent:#0f6e66; --accent-ink:#ffffff;
  --paper:#ffffff; --pink:#e4ece8; --cyan:#dfe6ec; --orange:#cddfd7;
  --mark:#ffe68f;
  --m:clamp(16px,2vw,28px);
  --axis:42vw;
  --step-small:clamp(0.8125rem,0.79rem + 0.1vw,0.875rem);
  --step-body:clamp(1.0625rem,1rem + 0.25vw,1.1875rem);
  --step-lead:clamp(1.25rem,1.1rem + 0.7vw,1.625rem);
  --step-head:clamp(2rem,1.3rem + 3.2vw,4rem);
  --step-display:clamp(3.25rem,8.3vw,8rem);
  --ease-out:cubic-bezier(.16,1,.3,1);
  --font:"Be Vietnam Pro",system-ui,sans-serif;
}
.landing *, .landing *::before, .landing *::after{box-sizing:border-box}
.landing{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);font-size:var(--step-body);line-height:1.45;letter-spacing:-0.01em;overflow-x:hidden}
.landing h1, .landing h2, .landing h3, .landing p, .landing ol, .landing ul, .landing figure, .landing blockquote{margin:0}
.landing ul, .landing ol{padding:0;list-style:none}
.landing a{color:inherit}
.landing button{font:inherit;color:inherit}
.landing img, .landing svg{display:block;max-width:100%}
.landing :focus-visible{outline:3px solid var(--ink);outline-offset:3px}
.landing ::selection{background:var(--mark);color:var(--ink)}
.landing .sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}


.landing .btn{display:inline-flex;align-items:center;justify-content:center;gap:.5em;min-height:52px;padding:0 1.4em;background:var(--accent);color:var(--accent-ink);font-weight:600;text-decoration:none;border:0;cursor:pointer;transition:transform .2s var(--ease-out),background-color .2s}
.landing .btn:hover{background:#0b5a53;transform:translateY(-2px)}
.landing .btn:active{transform:translateY(0) scale(.98)}
.landing .link{font-weight:600;text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:5px;transition:text-underline-offset .2s var(--ease-out)}
.landing .link:hover{text-underline-offset:8px}


.landing .mast{height:52svh;min-height:420px;display:grid;grid-template-rows:auto 1fr}
.landing .bar{display:flex;align-items:stretch;height:56px;background:var(--bg)}
.landing .wordmark{display:flex;align-items:center;padding:0 var(--m);background:var(--ink);color:var(--bg);font-weight:800;font-size:var(--step-lead);letter-spacing:-0.04em;text-decoration:none}
.landing .tab{display:flex;align-items:center;gap:clamp(16px,2.4vw,40px);padding:0 var(--m);background:var(--cyan);width:calc(var(--axis) - 0px);flex:none}
.landing .tab a{position:relative;font-weight:600;text-decoration:none;font-size:var(--step-small);padding:6px 0}
.landing .tab a::after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--ink);transform:scaleX(0);transform-origin:0 50%;transition:transform .25s var(--ease-out)}
.landing .tab a:hover::after{transform:scaleX(1)}
.landing .bar-end{margin-left:auto;display:flex;align-items:center;gap:24px;padding-right:var(--m);font-size:var(--step-small)}
.landing .bar-end a{font-weight:600}
.landing .mosaic{display:grid;grid-template-columns:repeat(6,1fr);grid-template-rows:1fr 1fr;min-height:0;overflow:hidden}
.landing .cell{position:relative;overflow:hidden;min-height:0}
.landing .c-a{grid-column:1/3;grid-row:1;background:var(--paper)}
.landing .c-b{grid-column:3;grid-row:1/3;background:var(--pink);display:flex;flex-direction:column;justify-content:flex-end;padding:var(--m)}
.landing .c-c{grid-column:4/6;grid-row:1;background:#f4f4f2}
.landing .c-d{grid-column:6;grid-row:1;background:var(--orange);padding:var(--m);display:flex;flex-direction:column;justify-content:space-between}
.landing .c-e{grid-column:1;grid-row:2;background:var(--cyan);padding:var(--m);display:flex;align-items:center;justify-content:center}
.landing .c-f{grid-column:2;grid-row:2;background:var(--ink);color:var(--bg);padding:var(--m);display:flex;align-items:flex-end}
.landing .c-h{grid-column:4/6;grid-row:2;background:var(--paper)}
.landing .c-i{grid-column:6;grid-row:2;background:var(--surface);padding:var(--m);display:flex;align-items:flex-end}
.landing .big-num{font-weight:800;font-size:var(--step-head);letter-spacing:-0.05em;line-height:.95}
.landing .tile-note{font-size:var(--step-small);font-weight:600;line-height:1.3;max-width:16ch}


.landing [data-ui]{font-family:var(--font);letter-spacing:0;color:#16181b;line-height:1.5}
.landing .ui-slide{position:absolute;inset:0;padding:clamp(14px,1.6vw,24px) clamp(16px,1.8vw,28px);background:#fff;font-size:13px}
.landing .ui-slide .s-top{display:flex;justify-content:space-between;color:#6a6f76;font-size:11.5px;margin-bottom:10px}
.landing .ui-slide h4{margin:0 0 8px;font-size:clamp(15px,1.35vw,20px);font-weight:800;letter-spacing:-0.02em}
.landing .ui-slide ul{display:grid;gap:5px}
.landing .ui-slide li{padding-left:14px;position:relative}
.landing .ui-slide li::before{content:"";position:absolute;left:0;top:.62em;width:6px;height:6px;background:#16181b}
.landing .hl{background:var(--mark);box-decoration-break:clone;-webkit-box-decoration-break:clone}
.landing .hl.sweep{background:none;position:relative;z-index:0;white-space:nowrap}
.landing .hl.sweep::after{content:"";position:absolute;z-index:-1;left:-3px;right:-3px;top:.1em;bottom:.05em;background:var(--mark);transform-origin:0 50%}
.landing.is-js .hl.sweep::after{transform:scaleX(0)}
.landing.is-js .hl.sweep.is-in::after{animation:lp-sweep 900ms var(--ease-out) 600ms forwards}
@keyframes lp-sweep{to{transform:scaleX(1)}}

.landing .ui-chat{position:absolute;inset:0;padding:clamp(14px,1.4vw,22px);font-size:13px;display:flex;flex-direction:column;gap:10px;background:#f4f4f2}
.landing .q-bubble{align-self:flex-end;background:#16181b;color:#fff;padding:7px 12px;max-width:80%}
.landing .a-text{background:#fff;padding:10px 12px}
.landing .cite{display:inline-block;min-width:1.5em;padding:0 .3em;margin:0 1px;background:var(--mark);font-weight:700;font-size:.82em;line-height:1.5;text-align:center;color:#16181b;text-decoration:none;cursor:pointer;transition:background-color .15s}
.landing .cite:hover{background:var(--accent);color:#fff}
.landing .src-line{font-size:12px;color:#4b5058;display:flex;gap:8px;align-items:baseline}

.landing .ui-quiz{position:absolute;inset:0;padding:clamp(14px,1.4vw,22px);font-size:13px;display:flex;flex-direction:column;gap:10px;background:#fff}
.landing .quiz-top{display:flex;justify-content:space-between;align-items:center;font-weight:600}
.landing .timer{font-variant-numeric:tabular-nums;font-weight:800;font-size:18px;padding:2px 10px;background:#16181b;color:#fff}
.landing .timebar{height:5px;background:#e8e8e5;overflow:hidden}
.landing .timebar i{display:block;height:100%;background:var(--accent);transform-origin:0 50%}
.landing .opt{display:flex;gap:10px;align-items:center;padding:7px 10px;background:#f4f4f2}
.landing .opt b{display:inline-grid;place-items:center;width:22px;height:22px;background:#fff;font-size:12px}
.landing .opt.on{background:#16181b;color:#fff}
.landing .opt.on b{background:var(--mark);color:#16181b}


.landing .hero{display:grid;grid-template-columns:var(--axis) 1fr;align-items:start;padding:clamp(56px,9vh,110px) var(--m) clamp(64px,10vh,120px) var(--m);column-gap:0}
.landing .standfirst{font-size:var(--step-lead);line-height:1.3;max-width:24ch;font-weight:400;padding-right:var(--m)}
.landing .standfirst + .actions{margin-top:28px;display:flex;flex-wrap:wrap;gap:16px 24px;align-items:center}
.landing .lines{font-weight:800;font-size:var(--step-display);letter-spacing:-0.05em;line-height:.98}
.landing .lines .line{display:block;overflow:hidden;padding:.14em 0 .1em;margin:-.14em 0 -.1em}
.landing .lines [data-line]{display:block}
@media (prefers-reduced-motion:no-preference){
  .landing.is-js .lines [data-line]{transform:translateY(110%);animation:lp-line-up 900ms var(--ease-out) forwards;animation-delay:calc(var(--i) * 110ms + 150ms)}
  .landing.is-js .hero .after-lines{opacity:0;transform:translateY(16px);animation:lp-fade-up 700ms var(--ease-out) 650ms forwards}
}
@keyframes lp-line-up{to{transform:none}}
@keyframes lp-fade-up{to{opacity:1;transform:none}}


@media (prefers-reduced-motion:no-preference){
  .landing.is-js [data-reveal]{opacity:0;transform:translateY(24px);transition:opacity .7s var(--ease-out),transform .7s var(--ease-out);transition-delay:calc(var(--d,0) * 80ms)}
  .landing.is-js [data-reveal].is-in{opacity:1;transform:none}
}


.landing .try{display:grid;grid-template-columns:var(--axis) 1fr;background:var(--bg)}
.landing .try-index{padding:clamp(72px,10vh,120px) var(--m) var(--m);display:flex;flex-direction:column;gap:clamp(32px,5vh,56px)}
.landing .try-names{display:flex;flex-direction:column;gap:.1em}
.landing .try-names button{all:unset;cursor:pointer;font-weight:800;font-size:var(--step-head);letter-spacing:-0.045em;line-height:1.1;color:var(--muted);transition:color .2s,transform .3s var(--ease-out);width:max-content;max-width:100%}
.landing .try-names button:hover{color:var(--ink);transform:translateX(8px)}
.landing .try-names button[aria-pressed="true"]{color:var(--ink)}
.landing .try-names button:focus-visible{outline:3px solid var(--ink);outline-offset:4px}
.landing .try-note{max-width:34ch}
.landing .try-note p + p{margin-top:.8em}
.landing .stage{background:var(--surface);min-height:88svh;position:relative;overflow:hidden;padding:72px 0 0 64px}
.landing .sheet{width:560px;max-width:none;background:#fff;padding:28px 32px 40px;font-size:15px;min-height:calc(88svh - 40px);transition:opacity .2s}
.landing .sheet.fading{opacity:0}
.landing .sheet-head{display:flex;justify-content:space-between;gap:16px;font-size:12.5px;color:#4b5058;padding-bottom:14px;margin-bottom:18px}
.landing .sheet .q-bubble{margin-left:auto;width:max-content;max-width:85%;font-size:14px;margin-bottom:16px}
.landing .sheet .answer p{margin-bottom:.8em}
.landing .sheet .answer .refuse{background:#f4f4f2;padding:12px 14px}
.landing .sources{margin-top:18px;display:grid;gap:10px}
.landing .source{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;padding:12px 14px;background:#f4f4f2;font-size:13px}
.landing .source .cite{grid-row:1/3;align-self:start}
.landing .source a{font-weight:600;color:#16181b}
.landing .excerpt{margin-top:18px;background:#fbfbf9;padding:16px 18px;font-size:13.5px}
.landing .excerpt .ex-top{display:flex;justify-content:space-between;color:#6a6f76;font-size:12px;margin-bottom:8px}
.landing .followups{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px;font-size:13px}
.landing .followups span{background:#f4f4f2;padding:5px 10px}


.landing .how{background:var(--paper);padding:clamp(120px,16vh,200px) var(--m)}
.landing .how h2, .landing .feat h2, .landing .teach h2{font-weight:800;letter-spacing:-0.05em;line-height:.98}
.landing .how h2{font-size:var(--step-display);max-width:12ch;margin-bottom:64px}
.landing .stages{display:flex;gap:6px;height:22vh;min-height:150px}
.landing .stage-seg{padding:20px;font-weight:800;font-size:var(--step-lead);letter-spacing:-0.03em;line-height:1.1;min-width:12%}
.landing .seg-1{flex-grow:8;background:var(--cyan)}
.landing .seg-2{flex-grow:18;background:var(--orange)}
.landing .seg-3{flex-grow:74;background:var(--pink)}
.landing .stage-notes{display:flex;gap:6px;margin-top:18px}
.landing .stage-notes p{max-width:24ch;padding-right:12px}
.landing .stage-notes .n1{flex:8 1 0;min-width:12%}
.landing .stage-notes .n2{flex:18 1 0}
.landing .stage-notes .n3{flex:74 1 0}


.landing .feat{background:var(--pink);padding:0 var(--m) clamp(120px,16vh,200px)}
.landing .feat-intro{min-height:40svh;display:flex;align-items:center;padding-left:calc(var(--axis) - var(--m))}
.landing .feat h2{font-size:var(--step-head);max-width:14ch}
.landing .row{display:grid;grid-template-columns:calc(var(--axis) - var(--m)) minmax(0,36ch) 1fr;align-items:start;margin-top:clamp(96px,12vh,120px)}
.landing .row:first-of-type{margin-top:0}
.landing .side{font-size:var(--step-body);font-weight:600;max-width:24ch;padding-top:.5em;line-height:1.35}
.landing .side span{display:block;font-weight:400;margin-top:8px}
.landing .row h3{font-weight:800;font-size:var(--step-head);letter-spacing:-0.045em;line-height:1;margin-bottom:16px}
.landing .row figure{justify-self:end;margin-left:32px}
.landing .frag{position:relative;background:#fff;overflow:hidden;transition:transform .4s var(--ease-out)}
.landing .frag:hover{transform:translateY(-4px)}
.landing .f1{width:380px;aspect-ratio:4/5}
.landing .f2{width:440px;aspect-ratio:3/2}
.landing .f3{width:340px;aspect-ratio:1}
.landing .f4{width:420px;aspect-ratio:3/2}
.landing .fpad{position:absolute;inset:0;padding:22px;font-size:13.5px;display:flex;flex-direction:column;gap:10px}
.landing .fc-card{flex:1;display:grid;place-items:center;text-align:center;background:var(--cyan);padding:18px;font-size:20px;font-weight:800;letter-spacing:-0.02em}
.landing .fc-keys{display:flex;gap:8px;font-size:12px;color:#4b5058;flex-wrap:wrap}
.landing .fc-keys kbd{font-family:var(--font);background:#f4f4f2;padding:2px 7px;font-weight:600;color:#16181b}
.landing .res-row{display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:#f4f4f2}
.landing .res-row.bad{background:#f7e4e1}
.landing .res-row em{font-style:normal;font-weight:700}
.landing .ai-explain{background:#fff8d6;padding:10px 12px;font-size:13px}
.landing .ai-explain b{display:block;margin-bottom:3px}
.landing .note-item{display:flex;gap:10px;align-items:flex-start;padding:9px 10px;background:#f4f4f2}
.landing .note-item i{flex:none;width:16px;height:16px;margin-top:3px}
.landing .note-item i{background:var(--mark);outline:4px solid #16181b;outline-offset:-4px}
.landing .note-item.off i{background:#fff;outline:2px solid #16181b;outline-offset:-2px}
.landing .mini-btn{align-self:flex-start;background:#16181b;color:#fff;padding:7px 12px;font-weight:600;font-size:13px}


.landing .teach{background:var(--cyan);padding:clamp(120px,16vh,200px) var(--m)}
.landing .teach h2{font-size:var(--step-head)}
.landing .teach .lead{font-size:var(--step-lead);line-height:1.35;max-width:44ch;margin-top:24px}
.landing .teach-grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px;margin-top:72px;align-items:start}
.landing .t-photo{grid-column:1/9;position:relative;aspect-ratio:16/10;background:#fff;overflow:hidden}
.landing .t-over{position:absolute;top:0;right:0;width:320px;background:var(--bg);padding:20px;font-size:var(--step-body);line-height:1.45;z-index:2}
.landing .t-side{grid-column:9/13}
.landing .t-tile{background:var(--orange);aspect-ratio:8/10;display:grid;place-items:center;padding:28px}
.landing .t-tile svg{width:62%;height:auto}
.landing .facts{display:grid;grid-template-columns:1fr 1fr;gap:20px 16px;margin-top:22px;font-size:var(--step-small)}
.landing .facts dt{color:var(--ink);font-weight:400}
.landing .facts dd{margin:2px 0 0;font-weight:800;font-size:var(--step-lead);letter-spacing:-0.03em;line-height:1.15}
.landing .review{position:absolute;inset:0;padding:26px 28px;font-size:14px;display:flex;flex-direction:column;gap:12px;padding-right:360px}
.landing .rv-head{display:flex;gap:10px;align-items:center;font-weight:700}
.landing .badge-ok{background:var(--mark);padding:2px 8px;font-size:12px;font-weight:700}
.landing .rv-q{background:#f4f4f2;padding:12px 14px}
.landing .rv-q p{font-weight:600;margin-bottom:8px}
.landing .rv-opts{display:grid;gap:5px;font-size:13px}
.landing .rv-opts li.ok{font-weight:700}
.landing .rv-opts li.ok::after{content:"  · đáp án";font-weight:400;color:#4b5058}
.landing .rv-actions{display:flex;gap:8px;font-size:13px;font-weight:600}
.landing .rv-actions span{padding:7px 12px;background:#f4f4f2}
.landing .rv-actions span:first-child{background:#16181b;color:#fff}
.landing .rv-src{font-size:12.5px;color:#4b5058}


.landing .close{background:var(--ink);color:var(--bg);min-height:92svh;padding:clamp(96px,14vh,160px) var(--m) 40px;display:flex;flex-direction:column;justify-content:space-between}
.landing .close h2{font-weight:800;font-size:clamp(3.5rem,10vw,10rem);letter-spacing:-0.055em;line-height:.95}
.landing .close-foot{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;margin-top:64px}
.landing .close-foot p{font-size:var(--step-lead);max-width:30ch;line-height:1.3}
.landing .close .btn{min-height:56px;padding:0 2em}


.landing .foot{background:var(--orange);min-height:80svh;padding:40px var(--m) 28px;display:flex;flex-direction:column}
.landing .foot-top{display:flex;justify-content:space-between;gap:24px;font-size:var(--step-small)}
.landing .foot-notes{display:flex;gap:clamp(24px,4vw,64px);max-width:60%}
.landing .foot-notes p{max-width:28ch}
.landing .foot-notes b{display:block;font-weight:800}
.landing .contact{margin-top:auto;display:block;font-weight:800;font-size:clamp(2.6rem,8.6vw,9rem);letter-spacing:-0.055em;line-height:.95;text-decoration:none;padding-bottom:.06em}
.landing .contact span{display:block}
.landing .contact:hover span{text-decoration:underline;text-decoration-thickness:.06em;text-underline-offset:.08em}
.landing .meta{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;margin-top:36px;font-size:var(--step-small)}
.landing .meta nav{display:flex;gap:20px;flex-wrap:wrap}
.landing .meta p:last-child{text-align:right}


@media (max-width:900px){
  .landing{--axis:0px}
  .landing .mast{height:auto;min-height:0}
  .landing .bar{height:52px}
  .landing .tab{display:none}
  .landing .bar-end .hide-s{display:none}
  .landing .mosaic{grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,minmax(0,1fr));height:38svh;min-height:260px}
  .landing .c-a{grid-column:1/3;grid-row:1}
  .landing .c-d{grid-column:3;grid-row:1}
  .landing .c-b{grid-column:1;grid-row:2}
  .landing .c-h{grid-column:2/4;grid-row:2}
  .landing .c-c, .landing .c-e, .landing .c-f, .landing .c-i{display:none}
  .landing .ui-slide .s-top{display:none}
  .landing .ui-slide ul li:not(:nth-child(2)){display:none}
  .landing .ui-quiz .opt:nth-of-type(n+3){display:none}
  .landing .hero{grid-template-columns:1fr;padding-top:40px;padding-bottom:56px}
  .landing .hero h1{order:-1;font-size:clamp(2.6rem,13vw,5rem)}
  .landing .standfirst{margin-top:20px;font-size:17px;max-width:32ch}
  .landing .try{grid-template-columns:1fr}
  .landing .try-index{padding-top:72px;gap:24px}
  .landing .try-names{flex-direction:row;overflow-x:auto;scroll-snap-type:x mandatory;gap:20px;padding-bottom:6px;margin-right:calc(var(--m) * -1)}
  .landing .try-names button{font-size:24px;scroll-snap-align:start;white-space:nowrap}
  .landing .stage{min-height:0;height:auto;padding:16px 0 0 16px}
  .landing .sheet{width:min(560px,calc(100vw - 32px));min-height:0;padding:20px 20px 28px;font-size:14px}
  .landing .how h2{font-size:clamp(2.6rem,11vw,4rem)}
  .landing .stages{flex-direction:column;height:auto;min-height:0}
  .landing .stage-seg{font-size:22px;min-height:0}
  .landing .seg-1{min-height:120px}.landing .seg-2{min-height:170px}.landing .seg-3{min-height:300px}
  .landing .stage-notes{display:none}
  .landing .stage-seg small{display:block;font-weight:400;font-size:16px;letter-spacing:-0.01em;margin-top:8px;max-width:30ch;line-height:1.4}
  .landing .feat-intro{min-height:auto;padding:120px 0 64px}
  .landing .feat h2{font-size:clamp(2.2rem,9vw,3.2rem)}
  .landing .row{grid-template-columns:1fr;margin-top:72px}
  .landing .side{order:3;padding-top:12px}
  .landing .row h3{font-size:30px}
  .landing .row figure{justify-self:start;margin:20px 0 0;order:4}
  .landing .f1{width:100%}
  .landing .f2{width:78%;justify-self:end}
  .landing .f3{width:72%}
  .landing .f4{width:100%}
  .landing .row figure.r2{justify-self:end}
  .landing .teach-grid{grid-template-columns:1fr;margin-top:40px}
  .landing .t-photo{grid-column:1;aspect-ratio:auto;height:auto}
  .landing .review{position:static;padding:20px}
  .landing .t-over{position:static;width:auto;background:transparent;padding:16px 0 0}
  .landing .t-side{grid-column:1}
  .landing .t-tile{aspect-ratio:3/2}
  .landing .t-tile svg{width:auto;height:80%}
  .landing .close{min-height:80svh}
  .landing .close h2{font-size:12vw}
  .landing .close-foot{flex-direction:column;align-items:stretch}
  .landing .close-foot p{font-size:17px}
  .landing .close .btn{width:100%}
  .landing .foot-top{flex-direction:column}
  .landing .foot-notes{flex-direction:column;max-width:none;gap:16px}
  .landing .contact{font-size:clamp(2.2rem,11.5vw,5rem);margin-top:96px}
  .landing .meta{grid-template-columns:1fr;gap:6px}
  .landing .meta p:last-child{text-align:left}
}
@media (min-width:901px){ .landing .stage-seg small{display:none} }
@media (max-width:1180px) and (min-width:901px){
  .landing .review{padding-right:28px;padding-bottom:180px}
  .landing .t-over{top:auto;bottom:0}
  .landing .f2, .landing .f4{width:360px}.landing .f1{width:320px}.landing .f3{width:300px}
}
.landing .tile-formula{font-size:var(--step-lead);font-weight:800;text-align:center;max-width:none}
.landing .frag-q{font-weight:600;margin-top:6px}
.landing .frag-foot{margin-top:auto;display:flex;justify-content:space-between;color:#4b5058;font-size:12.5px}
.landing .frag-meta{font-weight:400;color:#4b5058;font-size:12.5px}
.landing .rv-done{background:#fff8d6}
.landing .rv-done p{margin-bottom:4px}
.landing .rv-done .badge-ok{margin-left:6px}
```

- [ ] **Bước 5: Gắn vào trang chủ.** Khách xem `<Landing />`. `AppShell` bỏ khung ở `/` khi chưa đăng nhập, kể cả lúc đang khôi phục phiên, để khách không thấy khung app nháy lên rồi biến mất. Người đã đăng nhập vẫn thấy trang chủ cũ trong khung app.

```diff
--- a/frontend/src/app/(main)/page.tsx
+++ b/frontend/src/app/(main)/page.tsx
@@ -1,12 +1,13 @@
 "use client";
 
-import { ArrowRight, Clock, Compass, XCircle } from "lucide-react";
+import { ArrowRight, Clock, XCircle } from "lucide-react";
 import Link from "next/link";
 import { useRouter } from "next/navigation";
 import * as React from "react";
 import { toast } from "sonner";
 import { PageHeader } from "@/components/app/states";
 import { MyCourseList } from "@/components/course/my-course-list";
+import { Landing } from "@/components/landing/landing";
 import { Button } from "@/components/ui/button";
 import { Skeleton } from "@/components/ui/misc";
 import { api, unwrap } from "@/lib/api/client";
@@ -67,25 +68,8 @@
   }, [isAdmin, router]);
   if (status === "loading" || isAdmin) return <Skeleton className="h-40 w-full" />;
 
-  if (!user)
-    return (
-      <section className="mx-auto max-w-2xl py-10 text-center md:py-20">
-        <h1 className="text-3xl font-semibold md:text-4xl">Học theo nhịp của bạn, có AI giải đáp ngay trong bài</h1>
-        <p className="mt-4 text-lg text-muted-foreground">
-          AI Tutor trả lời dựa trên đúng tài liệu của khóa học và luôn ghi nguồn, để bạn kiểm chứng được.
-        </p>
-        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
-          <Button asChild size="lg">
-            <Link href="/explore">
-              <Compass /> Khám phá khóa học
-            </Link>
-          </Button>
-          <Button asChild size="lg" variant="outline">
-            <Link href="/register">Tạo tài khoản</Link>
-          </Button>
-        </div>
-      </section>
-    );
+  // Khách: trang giới thiệu riêng, không nằm trong khung app (AppShell bỏ khung ở "/" khi chưa đăng nhập).
+  if (!user) return <Landing />;
 
   // Chỉ giảng viên đã duyệt mới vào được /teach.
   const canTeach = user.role === "teacher" && user.teacher_status === "approved";
```

```diff
--- a/frontend/src/components/app/app-shell.tsx
+++ b/frontend/src/components/app/app-shell.tsx
@@ -18,10 +18,14 @@
  * thanh dưới tối đa 4 mục (<768px). Trang bài học không dùng khung này.
  */
 export function AppShell({ children }: { children: React.ReactNode }) {
-  const { user } = useAuth();
+  const { user, status } = useAuth();
   const pathname = usePathname();
   const items = navItems(user);
 
+  // Trang chủ của khách là trang giới thiệu toàn màn hình, có thanh điều hướng riêng.
+  // Lúc đang khôi phục phiên cũng chưa vẽ khung, để khách không thấy khung app nháy lên rồi biến mất.
+  if (pathname === "/" && status !== "authenticated") return <>{children}</>;
+
   return (
     <div className="min-h-dvh md:pl-16 lg:pl-60">
       <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
```

- [ ] **Bước 6: E2E trang chủ**

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { mockApi } from "./mock-api";

test.describe("trang chủ cho khách", () => {
  test("giới thiệu toàn màn hình, thử 4 câu hỏi mẫu, câu ngoài tài liệu thì AI từ chối", async ({ page }) => {
    await mockApi(page, { user: null });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Hỏi bài, có số trang.", level: 1 })).toBeVisible();
    // không có khung app (thanh điều hướng chính) ở trang giới thiệu
    await expect(page.getByRole("navigation", { name: "Điều hướng chính" })).toHaveCount(0);
    await expect(page.getByText("Mở PDF trang 49")).toBeVisible();

    await page.getByRole("button", { name: "Giá vé tàu" }).click();
    await expect(page.getByRole("button", { name: "Giá vé tàu" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(/không nói đến giá vé tàu/)).toBeVisible();
    await expect(page.getByText(/Mở PDF trang/)).toHaveCount(0);

    await page.getByRole("button", { name: "Dung lượng kênh" }).click();
    await expect(page.getByText("Mở PDF trang 31")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("nút Tạo tài khoản ở cuối trang dẫn tới đăng ký", async ({ page }) => {
    await mockApi(page, { user: null });
    await page.goto("/");
    await page.getByRole("link", { name: "Tạo tài khoản" }).last().click();
    await expect(page).toHaveURL(/\/register$/);
  });
});
```

- [ ] **Bước 7: Design system**

```diff
--- a/docs/design/design-system.md
+++ b/docs/design/design-system.md
@@ -8,7 +8,7 @@
 
 ## 1. Nguyên tắc: dịu mắt khi học lâu
 
-1. **Không dùng trắng tuyệt đối (#FFF) và đen tuyệt đối (#000) làm nền hay chữ.** Nền sáng là màu giấy ấm, nền tối là xám than. Chữ không dùng đen hay trắng thuần.
+1. **Không dùng trắng tuyệt đối (#FFF) và đen tuyệt đối (#000) làm nền hay chữ.** Nền sáng là xám trắng trung tính (từ 2026-10-15, trước đó là màu giấy ấm), nền tối là xám than. Chữ không dùng đen hay trắng thuần.
 2. **Tương phản vừa đủ, không gắt.** Chữ nội dung đạt 10.9–14.4:1 (trên chuẩn AAA 7:1), nhưng không chạm mức 21:1 như đen trên trắng. Chữ phụ đạt ≥ 5.4:1.
 3. **Màu nhấn dùng tiết kiệm.** Màu chính (xanh lục lam đậm) chỉ dùng cho **một hành động chính** trên mỗi màn hình và cho trạng thái đang chọn. Phần còn lại là trung tính.
 4. **Chữ đọc lớn, dòng ngắn.** Nội dung bài 17px (chỉnh được 15–21px), giãn dòng 1.75, mỗi dòng tối đa khoảng 68 ký tự.
@@ -23,14 +23,15 @@
 
 | Token | Sáng | Tối dịu | Giấy (sepia) | Dùng cho |
 |---|---|---|---|---|
-| `--background` | `#F7F5F0` | `#171A1E` | `#F3EAD7` | Nền trang |
-| `--surface` (card) | `#FFFDF9` | `#1F2328` | `#F9F2E3` | Thẻ, khung đọc, panel |
+| `--background` | `#F3F4F1` | `#171A1E` | `#F3EAD7` | Nền trang |
+| `--surface` (card) | `#FCFCFA` | `#1F2328` | `#F9F2E3` | Thẻ, khung đọc, panel |
 | `--foreground` | `#24292F` | `#E4E1DA` | `#3A2F24` | Chữ chính |
 | `--muted-foreground` | `#5B6470` | `#A3A8AF` | `#6B5B49` | Chữ phụ, nhãn, thời gian |
-| `--border` | `#E3DED4` | `#33383F` | `#DDCFB4` | Viền, đường phân cách |
+| `--border` | `#DFE2DC` | `#33383F` | `#DDCFB4` | Viền, đường phân cách |
 | `--primary` | `#0F6E66` | `#5FBFB3` | `#2F6B5E` | Nút chính, liên kết, mục đang chọn |
 | `--primary-foreground` | `#FFFFFF` | `#0E1A19` | `#FFFFFF` | Chữ trên nút chính |
-| `--accent` | `#A15C07` | `#E0A458` | `#8A5313` | Tiến độ, điểm nổi bật, trích dẫn nguồn |
+| `--accent` | `#A15C07` | `#E0A458` | `#8A5313` | Tiến độ, điểm nổi bật |
+| `--mark` | `#FFE68F` | `#E3C55A` | `#F2D36B` | Nền số trích dẫn [n] và dòng tài liệu được tô (như bút dạ quang); chữ trên nó là `--mark-foreground` |
 | `--success` | `#2F7D4F` | `#7CC49A` | `#3B6E45` | Đúng, hoàn thành, đã xử lý |
 | `--destructive` | `#B42318` | `#F2867A` | `#A3321F` | Xóa, lỗi, sai |
 
@@ -38,7 +39,7 @@
 
 | | Chữ/nền | Chữ phụ/nền | Màu chính/nền | Chữ trên nút chính | Màu nhấn | Đỏ | Xanh lá |
 |---|---|---|---|---|---|---|---|
-| Sáng | 13.45 | 5.50 | 5.60 | 6.10 | 4.76 | 6.03 | 4.63 |
+| Sáng | 13.27 | 5.68 | 5.53 | 6.10 | 4.70 | 5.95 | 4.56 |
 | Tối dịu | 13.37 | 7.30 | 7.97 | 8.12 | 8.00 | 7.04 | 8.50 |
 | Giấy | 10.89 | 5.46 | 5.19 | 6.20 | 5.28 | 5.79 | 5.01 |
 
@@ -62,14 +63,14 @@
 
 - `xs` 12px: chỉ dùng cho nhãn phụ, không bao giờ dùng cho nội dung.
 - `sm` 14px, `base` 16px, `lg` 18px, `xl` 20px, `2xl` 24px, `3xl` 30px.
-- Tiêu đề trang trên điện thoại 24px, desktop 30px. Độ đậm 600, không dùng 800–900.
+- Tiêu đề trang trên điện thoại 24px, desktop 30px. Độ đậm 600, không dùng 800–900 trong app. Ngoại lệ duy nhất: trang chủ cho khách (`components/landing`) dùng 800 cho tiêu đề lớn.
 
 ---
 
 ## 4. Khoảng cách, bo góc, đổ bóng, chuyển động
 
 - **Khoảng cách:** bội số của 4px. Khoảng cách giữa các khối nội dung trên trang: 24px trên điện thoại, 32px trên desktop.
-- **Bo góc:** `--radius: 10px` cho thẻ và panel, 8px cho nút và ô nhập, tròn hẳn cho huy hiệu (badge).
+- **Bo góc:** `--radius: 4px` cho thẻ, panel, nút và ô nhập (từ 2026-10-15, trước đó 10px/8px); tròn hẳn cho huy hiệu và ảnh đại diện. Trang chủ cho khách dùng góc vuông.
 - **Đổ bóng:** rất nhẹ, chỉ dùng cho lớp nổi (menu, dialog, panel Tutor trên điện thoại). Thẻ thường chỉ dùng viền.
 - **Chuyển động:** 150ms khi hover hoặc nhấn, 200ms khi mở panel. Không có hiệu ứng khi cuộn trang. Khi `prefers-reduced-motion` bật thì tắt hết chuyển động.
 
```

- [ ] **Bước 8: Kiểm tra + commit**

```powershell
cd frontend
npx tsc --noEmit ; npx eslint .
npx vitest run
npx playwright test e2e/landing.spec.ts e2e/student.spec.ts     # student.spec có kiểm tương phản 3 chế độ màu
cd ..
git add frontend docs/design
git commit -m "feat(web): bảng màu sáng trung tính, bo góc 4px, trích dẫn nền vàng, trang chủ mới cho khách"
```

---

## Task 3: Menu tài khoản ở mọi trang, trang Hồ sơ cá nhân

**Files:**
- Create: `frontend/src/lib/auth/profile.ts`
- Create: `frontend/src/components/app/user-menu.tsx`, `user-menu.test.tsx`
- Modify: `frontend/src/components/app/app-shell.tsx`
- Create: `frontend/src/components/account/profile-forms.tsx`, `profile-forms.test.tsx`
- Modify: `frontend/src/app/(main)/account/page.tsx`
- Modify: `frontend/src/components/lesson/lesson-view.tsx`, `frontend/src/components/quiz/quiz-player.tsx`, `quiz-player.test.tsx`, `quiz-result.tsx`
- Create: `frontend/e2e/account.spec.ts`
- Modify: `docs/specs/2026-09-29-lms-ai-design.md`

- [ ] **Bước 1: Hook gọi API.** Đổi mật khẩu xong thì dùng ngay access token mới. Cookie refresh mới do backend đặt và dùng chung cho mọi tab.

```ts
"use client";

import { useMutation } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { setAccessToken } from "@/lib/api/token";

/** Sửa họ tên. Trả UserOut mới. */
export function useUpdateProfile() {
  return useMutation({
    mutationFn: (full_name: string) => unwrap(api.PATCH("/api/v1/me", { body: { full_name } })),
  });
}

/**
 * Đổi mật khẩu khi đang đăng nhập. Backend thu hồi mọi phiên cũ và cấp phiên mới cho trình duyệt này
 * (cookie refresh mới + access token trả về), nên dùng ngay token mới để không bị văng ra.
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: async (body: { current_password: string; new_password: string }) => {
      const { access_token } = await unwrap(api.POST("/api/v1/me/password", { body }));
      setAccessToken(access_token);
    },
  });
}

/** Lỗi đổi mật khẩu thuộc ô nào: "current" (sai mật khẩu hiện tại), "new" (trùng mật khẩu cũ) hay chung. */
export function passwordErrorField(err: unknown): "current" | "new" | null {
  if (!(err instanceof ApiError)) return null;
  if (err.code === "WRONG_PASSWORD") return "current";
  if (err.code === "SAME_PASSWORD") return "new";
  return null;
}

export function passwordErrorMessage(err: unknown) {
  if (err instanceof ApiError && err.status === 429) {
    const minutes = Math.max(1, Math.ceil((err.retryAfter ?? 60) / 60));
    return `Bạn đã thử quá nhiều lần. Thử lại sau khoảng ${minutes} phút.`;
  }
  return err instanceof Error ? err.message : "Không đổi được mật khẩu";
}
```

- [ ] **Bước 2: Menu tài khoản dùng chung.**
  - `compact`: chỉ hiện chữ cái đại diện; tên vẫn có cho trình đọc màn hình, nên e2e cũ tìm nút theo tên vẫn chạy.
  - **Trên điện thoại** luôn ở dạng gọn.
  - **Đăng xuất** dùng `window.location.assign("/")` (tải lại hẳn trang). Nếu dùng `router.push`, trang có `RequireAuth` thấy phiên mất sẽ kịp chuyển sang `/login?next=…`; tải lại hẳn cũng bỏ sạch dữ liệu của phiên cũ trong bộ nhớ.

```tsx
"use client";

import { LogIn, LogOut, NotebookPen, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";
import { ThemeSwitcher } from "./theme-switcher";

export const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;

/** Chữ cái đại diện: chữ đầu của tên gọi (chữ cuối họ tên Việt), "Nguyễn Văn An" → "A". */
export function initialOf(fullName: string) {
  const given = fullName.trim().split(/\s+/).pop() ?? "";
  return (given[0] ?? "?").toLocaleUpperCase("vi");
}

/** Đăng xuất rồi nạp lại trang chủ. Tải lại hẳn (không router.push) để trang đang chặn bằng RequireAuth
 *  không kịp chuyển sang /login?next=…, và mọi dữ liệu của phiên cũ trong bộ nhớ đều bị bỏ. */
export async function logoutAndGoHome(logout: () => Promise<void>) {
  await logout();
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- cố ý tải lại hẳn trang (xem chú thích trên)
  window.location.assign("/");
}

/**
 * Nút tài khoản ở góc trên, dùng ở mọi khung trang (AppShell, trang học, quiz).
 * `compact`: chỉ hiện chữ cái đại diện (tên vẫn có cho trình đọc màn hình).
 * Trên điện thoại luôn ở dạng gọn.
 */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, status, logout } = useAuth();
  const router = useRouter();

  if (status === "loading") return <div className="size-10 shrink-0" aria-hidden />;
  if (!user)
    return (
      <Button asChild variant="outline" size={compact ? "sm" : "default"}>
        <Link href="/login">
          <LogIn /> Đăng nhập
        </Link>
      </Button>
    );

  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" className="shrink-0 gap-2 px-1.5 md:px-2">
          <span
            className="grid size-8 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
            aria-hidden
          >
            {initialOf(user.full_name)}
          </span>
          <span className={cn("max-w-40 truncate", compact ? "sr-only" : "sr-only md:not-sr-only")}>
            {user.full_name}
          </span>
        </Button>
      </MenuTrigger>
      <MenuContent>
        <div className="px-2 py-2">
          <p className="truncate text-sm font-medium">{user.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {user.email} · {ROLE_LABEL[user.role]}
          </p>
        </div>
        <MenuSeparator />
        <MenuItem onSelect={() => router.push("/account")}>
          <UserRound /> Hồ sơ cá nhân
        </MenuItem>
        {user.role !== "admin" ? (
          <MenuItem onSelect={() => router.push("/notes")}>
            <NotebookPen /> Ghi chú của tôi
          </MenuItem>
        ) : null}
        <div className="px-2 py-2">
          <ThemeSwitcher compact />
        </div>
        <MenuSeparator />
        <MenuItem onSelect={() => void logoutAndGoHome(logout)}>
          <LogOut /> Đăng xuất
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}
```

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("next-themes", () => ({ useTheme: () => ({ theme: "light", resolvedTheme: "light", setTheme: vi.fn() }) }));
const logout = vi.fn(async () => {});
const auth = {
  status: "authenticated",
  logout,
  user: { id: "u1", email: "an@sv.vn", full_name: "Nguyễn Văn An", role: "student", teacher_status: null } as unknown,
};
vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => auth }));

import { initialOf, UserMenu } from "./user-menu";

afterEach(() => {
  push.mockClear();
  logout.mockClear();
  vi.unstubAllGlobals();
});

describe("UserMenu", () => {
  it("chữ đại diện là chữ đầu của tên gọi", () => {
    expect(initialOf("Nguyễn Văn An")).toBe("A");
    expect(initialOf("  trần thị  ánh ")).toBe("Á");
    expect(initialOf("")).toBe("?");
  });

  it("mở menu: có Hồ sơ cá nhân, Ghi chú và Đăng xuất; vào hồ sơ thì chuyển tới /account", async () => {
    render(<UserMenu compact />);
    // dạng gọn vẫn có tên cho trình đọc màn hình
    await userEvent.click(screen.getByRole("button", { name: /Nguyễn Văn An/ }));
    expect(screen.getByText("an@sv.vn · Học viên")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Ghi chú của tôi" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Hồ sơ cá nhân" }));
    expect(push).toHaveBeenCalledWith("/account");
  });

  it("đăng xuất rồi nạp lại trang chủ", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    render(<UserMenu />);
    await userEvent.click(screen.getByRole("button", { name: /Nguyễn Văn An/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Đăng xuất" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
    expect(logout).toHaveBeenCalledOnce();
  });

  it("quản trị viên không có mục Ghi chú; khách thấy nút Đăng nhập", async () => {
    auth.user = { id: "a1", email: "ad@x.vn", full_name: "Quản trị viên", role: "admin", teacher_status: null };
    const { unmount } = render(<UserMenu />);
    await userEvent.click(screen.getByRole("button", { name: /Quản trị viên/ }));
    expect(screen.queryByRole("menuitem", { name: "Ghi chú của tôi" })).not.toBeInTheDocument();
    unmount();
    auth.user = null;
    auth.status = "anonymous";
    render(<UserMenu />);
    expect(screen.getByRole("link", { name: "Đăng nhập" })).toHaveAttribute("href", "/login");
  });
});
```

- [ ] **Bước 3: Khung app dùng menu mới.** Menu cũ chỉ có trên máy tính và không có mục Hồ sơ; giờ được bỏ, menu mới hiện ở mọi cỡ màn hình.

```diff
--- a/frontend/src/components/app/app-shell.tsx
+++ b/frontend/src/components/app/app-shell.tsx
@@ -1,21 +1,18 @@
 "use client";
 
-import { LogIn, LogOut, NotebookPen, User as UserIcon } from "lucide-react";
+import { User as UserIcon } from "lucide-react";
 import Link from "next/link";
-import { usePathname, useRouter } from "next/navigation";
+import { usePathname } from "next/navigation";
 import * as React from "react";
-import { Button } from "@/components/ui/button";
-import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
 import { useAuth } from "@/lib/auth/auth-context";
 import { cn } from "@/lib/utils";
 import { isActive, navItems } from "./nav-items";
-import { ThemeSwitcher } from "./theme-switcher";
-
-const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;
+import { UserMenu } from "./user-menu";
 
 /**
  * Khung chung: thanh bên 240px (≥1024px), thu gọn icon 64px (768–1023px),
- * thanh dưới tối đa 4 mục (<768px). Trang bài học không dùng khung này.
+ * thanh dưới tối đa 4 mục (<768px). Góc trên luôn có menu tài khoản (hồ sơ, ghi chú, chế độ màu, đăng xuất).
+ * Trang bài học và quiz không dùng khung này nhưng có cùng menu tài khoản ở thanh trên.
  */
 export function AppShell({ children }: { children: React.ReactNode }) {
   const { user, status } = useAuth();
@@ -60,7 +57,7 @@
           LMS-AI
         </Link>
         <div className="hidden md:block" />
-        <AccountMenu />
+        <UserMenu />
       </header>
 
       <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 md:px-8 md:pb-10 md:pt-8">
@@ -101,53 +98,3 @@
     </div>
   );
 }
-
-function AccountMenu() {
-  const { user, status, logout } = useAuth();
-  const router = useRouter();
-  if (status === "loading") return <div className="h-10 w-24" />;
-  if (!user)
-    return (
-      <Button asChild variant="outline" className="hidden md:inline-flex">
-        <Link href="/login">
-          <LogIn /> Đăng nhập
-        </Link>
-      </Button>
-    );
-  return (
-    <div className="hidden md:block">
-      <Menu>
-        <MenuTrigger asChild>
-          <Button variant="ghost">
-            <span className="grid size-7 place-items-center rounded-full bg-muted text-xs font-semibold">
-              {user.full_name.slice(0, 1).toUpperCase()}
-            </span>
-            {user.full_name}
-          </Button>
-        </MenuTrigger>
-        <MenuContent>
-          <div className="px-2 py-1.5 text-xs text-muted-foreground">
-            {user.email} · {ROLE_LABEL[user.role]}
-          </div>
-          <div className="px-2 py-2">
-            <ThemeSwitcher compact />
-          </div>
-          <MenuSeparator />
-          {user.role !== "admin" ? (
-            <MenuItem onSelect={() => router.push("/notes")}>
-              <NotebookPen /> Ghi chú của tôi
-            </MenuItem>
-          ) : null}
-          <MenuItem
-            onSelect={async () => {
-              await logout();
-              router.push("/");
-            }}
-          >
-            <LogOut /> Đăng xuất
-          </MenuItem>
-        </MenuContent>
-      </Menu>
-    </div>
-  );
-}
```

- [ ] **Bước 4: Trang Hồ sơ cá nhân**
  - **Form họ tên:** nút Lưu chỉ bật khi đã sửa. Lưu xong thì tải lại `/me` để menu ở mọi trang hiện tên mới.
  - **Form mật khẩu:**
    - Kiểm hai ô mật khẩu mới phải khớp.
    - Lỗi `WRONG_PASSWORD` báo ở ô "Mật khẩu hiện tại"; `SAME_PASSWORD` báo ở ô "Mật khẩu mới".
    - Lỗi 429 báo số phút phải chờ.

```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { type User, useAuth } from "@/lib/auth/auth-context";
import { passwordErrorField, passwordErrorMessage, useChangePassword, useUpdateProfile } from "@/lib/auth/profile";

const nameSchema = z.object({
  full_name: z
    .string()
    .transform((v) => v.trim().replace(/\s+/g, " "))
    .pipe(z.string().min(1, "Nhập họ tên").max(120, "Họ tên tối đa 120 ký tự")),
});
type NameIn = z.input<typeof nameSchema>;
type NameOut = z.output<typeof nameSchema>;

/** Sửa họ tên. Email là tên đăng nhập nên chỉ hiển thị. */
export function ProfileForm({ user }: { user: User }) {
  const { reloadUser } = useAuth();
  const update = useUpdateProfile();
  const form = useForm<NameIn, unknown, NameOut>({
    resolver: zodResolver(nameSchema),
    defaultValues: { full_name: user.full_name },
  });
  const { errors, isDirty } = form.formState;

  async function onSubmit({ full_name }: NameOut) {
    try {
      const saved = await update.mutateAsync(full_name);
      await reloadUser(); // menu tài khoản ở mọi trang đọc tên từ đây
      form.reset({ full_name: saved.full_name });
      toast.success("Đã lưu họ tên");
    } catch (err) {
      const msg = err instanceof ApiError ? (err.fieldError("full_name") ?? errorMessage(err)) : errorMessage(err);
      form.setError("full_name", { message: msg }, { shouldFocus: true });
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate aria-labelledby="h-profile">
      <h2 id="h-profile" className="text-lg font-semibold">
        Thông tin cá nhân
      </h2>
      <div className="space-y-1.5">
        <p className="text-sm font-medium">Email</p>
        <p className="text-sm text-muted-foreground">{user.email} (dùng để đăng nhập, không đổi được)</p>
      </div>
      <Field id="full_name" label="Họ tên" error={errors.full_name?.message}>
        <Input autoComplete="name" {...form.register("full_name")} />
      </Field>
      <Button type="submit" disabled={!isDirty} loading={update.isPending} loadingText="Đang lưu…">
        Lưu họ tên
      </Button>
    </form>
  );
}

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Nhập mật khẩu hiện tại"),
    new_password: z.string().min(8, "Mật khẩu mới ít nhất 8 ký tự").max(128, "Mật khẩu tối đa 128 ký tự"),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Hai mật khẩu chưa khớp" });
type PasswordValues = z.infer<typeof passwordSchema>;

const EMPTY: PasswordValues = { current_password: "", new_password: "", confirm: "" };

/** Đổi mật khẩu: phiên trên trình duyệt này được giữ, các thiết bị khác bị đăng xuất. */
export function PasswordForm() {
  const change = useChangePassword();
  const [formError, setFormError] = React.useState<string | null>(null);
  const form = useForm<PasswordValues>({ resolver: zodResolver(passwordSchema), defaultValues: EMPTY });
  const { errors } = form.formState;

  async function onSubmit({ current_password, new_password }: PasswordValues) {
    setFormError(null);
    try {
      await change.mutateAsync({ current_password, new_password });
      form.reset(EMPTY);
      toast.success("Đã đổi mật khẩu. Các thiết bị khác sẽ phải đăng nhập lại.");
    } catch (err) {
      const field = passwordErrorField(err);
      if (field === "current") form.setError("current_password", { message: errorMessage(err) }, { shouldFocus: true });
      else if (field === "new") form.setError("new_password", { message: errorMessage(err) }, { shouldFocus: true });
      else setFormError(passwordErrorMessage(err));
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate aria-labelledby="h-password">
      <h2 id="h-password" className="text-lg font-semibold">
        Đổi mật khẩu
      </h2>
      <Field id="current_password" label="Mật khẩu hiện tại" error={errors.current_password?.message}>
        <Input type="password" autoComplete="current-password" {...form.register("current_password")} />
      </Field>
      <Field id="new_password" label="Mật khẩu mới" error={errors.new_password?.message} hint="Ít nhất 8 ký tự">
        <Input type="password" autoComplete="new-password" {...form.register("new_password")} />
      </Field>
      <Field id="confirm" label="Nhập lại mật khẩu mới" error={errors.confirm?.message}>
        <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
      </Field>
      {formError ? (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      ) : null}
      <Button type="submit" loading={change.isPending} loadingText="Đang đổi…">
        Đổi mật khẩu
      </Button>
    </form>
  );
}
```

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getAccessToken, setAccessToken } from "@/lib/api/token";
import { api as url, server } from "@/test/msw";

const reloadUser = vi.fn(async () => ({}));
vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ reloadUser }) }));
const toast = vi.hoisted(() => ({ success: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import { PasswordForm, ProfileForm } from "./profile-forms";

const user = { id: "u1", email: "an@sv.vn", full_name: "Nguyễn Văn An", role: "student", teacher_status: null, email_verified: true } as const;
const apiErr = (status: number, code: string, message: string, headers: Record<string, string> = {}) =>
  HttpResponse.json({ error: { code, message, details: {} } }, { status, headers });

function wrap(ui: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  reloadUser.mockClear();
  toast.success.mockClear();
  setAccessToken(null);
});

describe("ProfileForm", () => {
  it("chỉ bật nút Lưu khi đã sửa; gửi họ tên đã gọn khoảng trắng rồi tải lại người dùng", async () => {
    let body: unknown = null;
    server.use(
      http.patch(url("/me"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...user, full_name: "Nguyễn Văn Bình" });
      }),
    );
    wrap(<ProfileForm user={user} />);
    const save = screen.getByRole("button", { name: "Lưu họ tên" });
    expect(save).toBeDisabled();
    const input = screen.getByLabelText("Họ tên");
    await userEvent.clear(input);
    await userEvent.type(input, "  Nguyễn   Văn Bình ");
    await userEvent.click(save);
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith("Đã lưu họ tên"));
    expect(body).toEqual({ full_name: "Nguyễn Văn Bình" });
    expect(reloadUser).toHaveBeenCalledOnce();
    expect(input).toHaveValue("Nguyễn Văn Bình");
  });

  it("họ tên toàn khoảng trắng: báo lỗi, không gọi API", async () => {
    wrap(<ProfileForm user={user} />);
    const input = screen.getByLabelText("Họ tên");
    await userEvent.clear(input);
    await userEvent.type(input, "   ");
    await userEvent.click(screen.getByRole("button", { name: "Lưu họ tên" }));
    expect(await screen.findByText("Nhập họ tên")).toBeInTheDocument();
  });
});

describe("PasswordForm", () => {
  async function fill(current: string, next: string, confirm = next) {
    await userEvent.type(screen.getByLabelText("Mật khẩu hiện tại"), current);
    await userEvent.type(screen.getByLabelText("Mật khẩu mới"), next);
    await userEvent.type(screen.getByLabelText("Nhập lại mật khẩu mới"), confirm);
    await userEvent.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
  }

  it("thành công: dùng ngay access token mới và xóa trắng các ô", async () => {
    let body: unknown = null;
    server.use(
      http.post(url("/me/password"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ access_token: "tok-moi", token_type: "bearer" });
      }),
    );
    wrap(<PasswordForm />);
    await fill("password123", "mat-khau-moi-1");
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(body).toEqual({ current_password: "password123", new_password: "mat-khau-moi-1" });
    expect(getAccessToken()).toBe("tok-moi");
    expect(screen.getByLabelText("Mật khẩu hiện tại")).toHaveValue("");
  });

  it("hai ô mật khẩu mới không khớp thì không gửi", async () => {
    wrap(<PasswordForm />);
    await fill("password123", "mat-khau-moi-1", "khac-hoan-toan");
    expect(await screen.findByText("Hai mật khẩu chưa khớp")).toBeInTheDocument();
  });

  it("sai mật khẩu hiện tại thì báo ở đúng ô đó; thử quá nhiều lần thì báo thời gian chờ", async () => {
    let calls = 0;
    server.use(
      http.post(url("/me/password"), () => {
        calls += 1;
        return calls === 1
          ? apiErr(400, "WRONG_PASSWORD", "Mật khẩu hiện tại không đúng")
          : apiErr(429, "RATE_LIMITED", "Chậm lại", { "Retry-After": "1800" });
      }),
    );
    wrap(<PasswordForm />);
    await fill("sai-roi", "mat-khau-moi-1");
    const current = screen.getByLabelText("Mật khẩu hiện tại");
    expect(await screen.findByText("Mật khẩu hiện tại không đúng")).toBeInTheDocument();
    expect(current).toHaveAttribute("aria-invalid", "true");
    await userEvent.click(screen.getByRole("button", { name: "Đổi mật khẩu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Thử lại sau khoảng 30 phút");
  });
});
```

```diff
--- a/frontend/src/app/(main)/account/page.tsx
+++ b/frontend/src/app/(main)/account/page.tsx
@@ -2,50 +2,47 @@
 
 import { LogOut, NotebookPen } from "lucide-react";
 import Link from "next/link";
-import { useRouter } from "next/navigation";
+import { PasswordForm, ProfileForm } from "@/components/account/profile-forms";
 import { PageHeader } from "@/components/app/states";
 import { ThemeSwitcher } from "@/components/app/theme-switcher";
+import { logoutAndGoHome, ROLE_LABEL } from "@/components/app/user-menu";
 import { Button } from "@/components/ui/button";
 import { useAuth } from "@/lib/auth/auth-context";
 import { RequireAuth } from "@/lib/auth/require-auth";
 
-const ROLE_LABEL = { student: "Học viên", teacher: "Giảng viên", admin: "Quản trị" } as const;
-
-/** Trang tài khoản (chủ yếu cho điện thoại, nơi không có menu góc trên). */
+/** Hồ sơ cá nhân: sửa họ tên, đổi mật khẩu, chế độ màu, đăng xuất. Mở từ menu tài khoản ở mọi trang. */
 export default function AccountPage() {
   const { user, logout } = useAuth();
-  const router = useRouter();
   return (
     <RequireAuth>
-      <PageHeader title="Tài khoản" />
+      <PageHeader title="Hồ sơ cá nhân">{user ? `${user.email} · ${ROLE_LABEL[user.role]}` : null}</PageHeader>
       {user ? (
-        <div className="max-w-md space-y-8">
-          <div>
-            <p className="font-medium">{user.full_name}</p>
-            <p className="text-sm text-muted-foreground">
-              {user.email} · {ROLE_LABEL[user.role]}
-            </p>
-          </div>
-          {user.role !== "admin" ? (
-            <Button asChild variant="outline">
-              <Link href="/notes">
-                <NotebookPen /> Ghi chú của tôi
-              </Link>
-            </Button>
-          ) : null}
-          <div>
-            <h2 className="mb-2 text-sm font-medium">Chế độ màu</h2>
+        <div className="grid max-w-3xl gap-10 md:grid-cols-2">
+          <ProfileForm key={user.id} user={user} />
+          <PasswordForm />
+          <section aria-labelledby="h-theme" className="space-y-3">
+            <h2 id="h-theme" className="text-lg font-semibold">
+              Chế độ màu
+            </h2>
             <ThemeSwitcher />
-          </div>
-          <Button
-            variant="outline"
-            onClick={async () => {
-              await logout();
-              router.push("/");
-            }}
-          >
-            <LogOut /> Đăng xuất
-          </Button>
+          </section>
+          <section aria-labelledby="h-session" className="space-y-3">
+            <h2 id="h-session" className="text-lg font-semibold">
+              Phiên đăng nhập
+            </h2>
+            <div className="flex flex-wrap gap-3">
+              {user.role !== "admin" ? (
+                <Button asChild variant="outline">
+                  <Link href="/notes">
+                    <NotebookPen /> Ghi chú của tôi
+                  </Link>
+                </Button>
+              ) : null}
+              <Button variant="outline" onClick={() => void logoutAndGoHome(logout)}>
+                <LogOut /> Đăng xuất
+              </Button>
+            </div>
+          </section>
         </div>
       ) : null}
     </RequireAuth>
```

- [ ] **Bước 5: Menu ở trang học, trang làm quiz, trang kết quả.** Test của trang làm quiz mock menu để không cần `AuthProvider`.

```diff
--- a/frontend/src/components/lesson/lesson-view.tsx
+++ b/frontend/src/components/lesson/lesson-view.tsx
@@ -19,6 +19,7 @@
 import * as React from "react";
 import { toast } from "sonner";
 import { ThemeSwitcher } from "@/components/app/theme-switcher";
+import { UserMenu } from "@/components/app/user-menu";
 import { ErrorState } from "@/components/app/states";
 import { Markdown } from "@/components/content/markdown";
 import { DocumentsPanel } from "@/components/studio/documents-panel";
@@ -205,6 +206,7 @@
         <Button variant="ghost" className="hidden lg:inline-flex" aria-pressed={tutorOpen} onClick={() => setTutorOpen((v) => !v)}>
           <MessageCircleQuestion /> Hỏi AI
         </Button>
+        <UserMenu compact />
       </header>
 
       <div className="flex">
```

```diff
--- a/frontend/src/components/quiz/quiz-player.tsx
+++ b/frontend/src/components/quiz/quiz-player.tsx
@@ -6,6 +6,7 @@
 import * as React from "react";
 import { toast } from "sonner";
 import { ErrorState } from "@/components/app/states";
+import { UserMenu } from "@/components/app/user-menu";
 import { BreakReminder } from "@/components/lesson/break-reminder";
 import { Button } from "@/components/ui/button";
 import { ConfirmDialog } from "@/components/ui/dialog";
@@ -300,6 +301,7 @@
         </Button>
         <h1 className="min-w-0 flex-1 truncate font-semibold">{title ?? "Quiz"}</h1>
         {aside}
+        <UserMenu compact />
       </header>
       <main id="main" className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 md:px-8">
         {children}
```

```diff
--- a/frontend/src/components/quiz/quiz-player.test.tsx
+++ b/frontend/src/components/quiz/quiz-player.test.tsx
@@ -13,6 +13,8 @@
 vi.mock("sonner", () => ({ toast: { info: (m: string) => toastInfo(m), error: (m: string) => toastError(m) } }));
 vi.mock("@/lib/quiz/queries", () => ({ useQuiz: () => ({ data: { title: "Quiz thử" } }) }));
 vi.mock("@/lib/quiz/use-quiz-attempt", () => ({ useQuizAttempt: () => hook.current }));
+// Menu tài khoản ở thanh trên cần AuthProvider; test này chỉ kiểm phần làm bài.
+vi.mock("@/components/app/user-menu", () => ({ UserMenu: () => null }));
 
 const attemptData = {
   id: "a1",
```

```diff
--- a/frontend/src/components/quiz/quiz-result.tsx
+++ b/frontend/src/components/quiz/quiz-result.tsx
@@ -4,6 +4,7 @@
 import Link from "next/link";
 import * as React from "react";
 import { ErrorState } from "@/components/app/states";
+import { UserMenu } from "@/components/app/user-menu";
 import { Button } from "@/components/ui/button";
 import { Badge, Skeleton } from "@/components/ui/misc";
 import { errorMessage } from "@/lib/api/errors";
@@ -30,6 +31,7 @@
           </Link>
         </Button>
         <p className="min-w-0 flex-1 truncate font-semibold">{quiz.data?.title ?? "Kết quả quiz"}</p>
+        <UserMenu compact />
       </header>
       <main id="main" className="mx-auto w-full max-w-3xl px-4 pb-16 pt-6 md:px-8">
         {result.isPending ? (
```

- [ ] **Bước 6: E2E.** Hai kịch bản:
  - Từ trang Khám phá mở menu → Hồ sơ cá nhân → sửa tên (menu hiện tên mới) → đổi mật khẩu.
  - Đang học bài thì mở menu → Đăng xuất → về trang chủ giới thiệu.

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { L1, mockApi, student } from "./mock-api";

test.describe("hồ sơ cá nhân và menu tài khoản", () => {
  test("mở Hồ sơ cá nhân từ menu ở trang bất kỳ, sửa họ tên và đổi mật khẩu", async ({ page }) => {
    let me = { ...student, email_verified: true };
    const bodies: Record<string, unknown> = {};
    await mockApi(page, {
      extra: {
        "GET /me": (r) => r.fulfill({ json: me }),
        "PATCH /me": (r) => {
          bodies.profile = r.request().postDataJSON();
          me = { ...me, full_name: (bodies.profile as { full_name: string }).full_name };
          return r.fulfill({ json: me });
        },
        "POST /me/password": (r) => {
          bodies.password = r.request().postDataJSON();
          return r.fulfill({ json: { access_token: "tok-2", token_type: "bearer" } });
        },
      },
    });
    await page.goto("/explore");
    await page.getByRole("button", { name: /Nguyễn Văn An/ }).click();
    await page.getByRole("menuitem", { name: "Hồ sơ cá nhân" }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole("heading", { name: "Hồ sơ cá nhân", level: 1 })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);

    await page.getByLabel("Họ tên").fill("Nguyễn Văn Bình");
    await page.getByRole("button", { name: "Lưu họ tên" }).click();
    await expect(page.getByText("Đã lưu họ tên")).toBeVisible();
    expect(bodies.profile).toEqual({ full_name: "Nguyễn Văn Bình" });
    // menu ở thanh trên đọc tên mới
    await expect(page.getByRole("button", { name: /Nguyễn Văn Bình/ })).toBeVisible();

    await page.getByLabel("Mật khẩu hiện tại").fill("password123");
    await page.getByLabel("Mật khẩu mới", { exact: true }).fill("mat-khau-moi-1");
    await page.getByLabel("Nhập lại mật khẩu mới").fill("mat-khau-moi-1");
    await page.getByRole("button", { name: "Đổi mật khẩu" }).click();
    await expect(page.getByText(/Đã đổi mật khẩu/)).toBeVisible();
    expect(bodies.password).toEqual({ current_password: "password123", new_password: "mat-khau-moi-1" });
  });

  test("đang học bài vẫn mở được menu tài khoản và đăng xuất về trang chủ", async ({ page }) => {
    let loggedOut = false;
    await mockApi(page, {
      extra: {
        "POST /auth/logout": (r) => {
          loggedOut = true;
          return r.fulfill({ status: 204 });
        },
        "POST /auth/refresh": (r) =>
          loggedOut
            ? r.fulfill({ status: 401, json: { error: { code: "INVALID_TOKEN", message: "x", details: {} } } })
            : r.fulfill({ json: { access_token: "tok", token_type: "bearer" } }),
      },
    });
    await page.goto(`/learn/giai-tich-1/${L1}`);
    await expect(page.getByRole("heading", { name: "Định nghĩa đạo hàm", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: /Nguyễn Văn An/ }).click();
    await expect(page.getByRole("menuitem", { name: "Hồ sơ cá nhân" })).toBeVisible();
    await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Hỏi bài, có số trang.", level: 1 })).toBeVisible();
    expect(loggedOut).toBe(true);
  });
});
```

- [ ] **Bước 7: Spec**

```diff
--- a/docs/specs/2026-09-29-lms-ai-design.md
+++ b/docs/specs/2026-09-29-lms-ai-design.md
@@ -473,7 +473,7 @@
 
 ### 6.2 Auth
 
-- **Endpoint:** `POST /auth/register|login|refresh|logout`, `GET /me`.
+- **Endpoint:** `POST /auth/register|login|refresh|logout`, `GET /me`, `PATCH /me` (sửa họ tên), `POST /me/password` (đổi mật khẩu khi đang đăng nhập).
 - **Access token:** JWT sống 15 phút, chỉ giữ trong bộ nhớ, gửi qua header `Authorization`.
 - **Refresh token:** sống 7 ngày, nằm trong cookie `httpOnly; SameSite=Lax; Path=/api/v1/auth`.
 - **Xoay vòng:** mỗi lần refresh thì cấp token mới và thu hồi token cũ. Token đã thu hồi mà bị dùng lại thì thu hồi toàn bộ phiên của user đó.
@@ -769,3 +769,4 @@
 | 2026-10-12 | AI Tutor: `availability` có `state` (ready/processing/model_mismatch/failed/empty/draft); lúc tài liệu đang xử lý vẫn gửi được câu hỏi (`waiting_for_docs`, tối đa 5 câu/phiên), job `tutor_waiting` sau `ingest_pdf` + cron 5 phút trả lời bằng đúng luồng Tutor, nhận câu bằng UPDATE có điều kiện, câu trả lời ghi `created_at` của câu hỏi |
 | 2026-10-12 | Trích PDF: chèn lại dấu cách bị mất ở PDF xuất từ slide (hai ký tự cách nhau > 10% cỡ chữ mà không có dấu cách); script `reprocess_pdfs` xử lý lại hàng loạt; `app.scripts.lock_user` khóa/mở khóa tài khoản bằng lệnh (kể cả admin, không khóa admin cuối cùng) |
 | 2026-10-12 | B1: `time_limit_sec` (60 giây – 4 giờ) và `shuffle` khi tạo/sửa quiz (null tường minh = bỏ giới hạn); `deadline_at` theo giờ DB, `server_now` trong bài làm để đồng hồ không lệch; quá `deadline_at + 5s` thì lưu/nộp bị từ chối và bài chốt `timed_out` với đáp án đã autosave; chốt khi có thao tác trên bài + cron mỗi phút. B2: hybrid vector top-20 + full-text top-20 gộp RRF (k=60), `RETRIEVAL_MODE=vector` để so sánh, benchmark có `mode=`. B3: `POST /attempts/{id}/answers/{qid}/explain` sau khi nộp, chỉ câu sai/bỏ trống, 30 lần/giờ/học viên, lỗi AI → 503 |
+| 2026-10-15 | Hồ sơ cá nhân: `PATCH /me` (họ tên, gọn khoảng trắng, 1–120 ký tự), `POST /me/password` (đúng mật khẩu hiện tại, khác mật khẩu cũ, 10 lần thử/giờ/tài khoản; thu hồi mọi phiên rồi cấp phiên mới cho trình duyệt đang dùng). Menu tài khoản (Hồ sơ cá nhân, Ghi chú, chế độ màu, Đăng xuất) ở thanh trên của mọi trang kể cả trang học và quiz; đăng xuất tải lại trang chủ. Giao diện: bảng màu sáng trung tính, bo góc 4px, `--mark` cho trích dẫn; trang chủ cho khách mới (không nằm trong khung app) có phần thử hỏi với 4 câu mẫu cố định |
```

- [ ] **Bước 8: Kiểm tra + commit**

```powershell
cd frontend
npx tsc --noEmit ; npx eslint .
npx vitest run                     # 164 pass
npx playwright test                # cả bộ: 95 pass + 1 bỏ qua có chủ ý
cd ..
git add frontend docs/specs
git commit -m "feat(web): menu tài khoản ở mọi trang, trang Hồ sơ cá nhân (sửa họ tên, đổi mật khẩu)"
```

---

## Task 4: Kiểm tay (bạn làm)

Sau khi pull: `docker compose --profile web up -d --build`. Nếu đang chạy `npm run dev` thì chỉ cần `docker compose up -d --build api worker` rồi tải lại trang.

- [ ] **Trang chủ khi chưa đăng nhập** (mở cửa sổ ẩn danh vào `http://localhost:3000`):
  - Thấy trang giới thiệu "Hỏi bài, có số trang.", không có thanh bên của app.
  - Bấm 4 câu ở phần "Thử hỏi"; "Giá vé tàu" thì AI từ chối.
  - Các nút "Tạo tài khoản", "Đăng nhập", "Khám phá khóa học" dẫn đúng trang.
  - Điện thoại (F12, 375px): không cuộn ngang, chữ không đè nhau.
- [ ] **Menu tài khoản ở mọi trang:** đăng nhập học viên, mở menu (chữ cái tròn góc trên) ở các trang:
  - Trang chủ, Khám phá, Khóa của tôi.
  - Trang học bài, trang làm quiz, trang kết quả quiz.

  Trang nào cũng có Hồ sơ cá nhân, Ghi chú của tôi, chế độ màu, Đăng xuất. Làm lại ở cỡ điện thoại.
- [ ] **Đăng xuất từ trang học bài:** về trang chủ giới thiệu, không bị đưa sang trang đăng nhập.
- [ ] **Hồ sơ cá nhân:**
  - Đổi họ tên rồi Lưu: báo "Đã lưu họ tên", menu hiện tên mới. Tải lại trang thì tên vẫn là tên mới.
- [ ] **Đổi mật khẩu:**
  - Nhập sai mật khẩu hiện tại: báo đỏ ngay ô đó.
  - Đổi đúng: vẫn ở lại trang, không bị đăng xuất. Đăng xuất rồi đăng nhập bằng mật khẩu mới được.
  - **Thu hồi phiên máy khác:** trước khi đổi, mở thêm một trình duyệt khác (hoặc cửa sổ ẩn danh) đăng nhập cùng tài khoản. Đổi mật khẩu xong, bên đó tải lại trang (F5) phải bị yêu cầu đăng nhập lại.
- [ ] **Màu:**
  - Số trích dẫn `[n]` trong câu trả lời AI Tutor có nền vàng nhạt, chữ đọc rõ ở cả 3 chế độ (Sáng, Tối dịu, Giấy).
  - Nút, thẻ, ô nhập ở các trang giảng viên và quản trị trông ổn với góc bo nhỏ.
- [ ] **Giảng viên và quản trị:**
  - Menu không có mục "Ghi chú của tôi" với quản trị viên.
  - Mọi vai trò đều mở được Hồ sơ cá nhân.
