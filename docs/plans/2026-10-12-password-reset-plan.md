# Quên mật khẩu: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** người dùng quên mật khẩu hiện không có cách nào tự lấy lại (chỉ admin can thiệp DB). Hạ tầng email (bảng `email_tokens`, outbox, Mailpit / Brevo) đã có từ phần xác nhận email, nên chỉ cần thêm một loại token mới.

**Mục tiêu:**

- Trang đăng nhập có link **"Quên mật khẩu?"** → trang `/forgot-password` nhập email → email chứa link `/reset-password?token=…` (hết hạn sau 60 phút).
- Đặt mật khẩu mới (nhập 2 lần) → **mọi phiên đăng nhập cũ bị thu hồi** (refresh token) → mời đăng nhập lại.
- Không lộ email nào đã đăng ký: luôn trả 202. Email không tồn tại / tài khoản bị khóa thì không gửi gì.
- Chống spam: tối đa **3 lần / giờ / email** và **10 lần / giờ / IP** (429 kèm số phút chờ).
- Xin link mới thì **link cũ hết hiệu lực**. Link đã dùng hoặc hết hạn → trang báo rõ "Link không dùng được" + nút "Gửi link mới".
- Nội dung email chứa link bị **xóa khỏi outbox sau khi gửi** (như email xác nhận).
- Đặt lại mật khẩu qua link email cũng chứng minh người dùng sở hữu email đó, nên tài khoản chưa xác nhận email sẽ được **xác nhận luôn** (giảng viên đang chờ duyệt thì admin được báo như khi xác nhận email).

**Thứ tự làm:** plan này làm **sau** plan module / CI-CD (`2026-10-08-modules-cicd-plan.md` Task 1–5) và các task code của tầng S. Diff tạo trên HEAD `48196db`; những plan kia không đụng các file ở đây (trừ `.env.example` / `config.py` ở vài dòng khác), nên `git apply --3way` khớp được. Sau plan này là `2026-10-12-openrouter-plan.md`, rồi `2026-10-12-tutor-waiting-plan.md` (ba plan tạo trên cùng một chuỗi, phải làm **đúng thứ tự**).

**Mã trong plan đã được chạy thử** (chuỗi 3 plan, bản cuối):

- Backend: **751 test pass** (718 cũ + 7 của plan này + 12 OpenRouter + 14 hỏi chờ). `ruff check`, `ruff format --check` sạch; `lint-imports` (5 hợp đồng của plan module) giữ nguyên.
- Frontend: `tsc`, `eslint` sạch; **151 unit test pass** (2 mới ở plan này); E2E mới `e2e/auth-password.spec.ts` (3 kịch bản × 375px / 1280px, có axe) pass.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6, nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn dùng pgvector 0.8 nên **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit.

**Cách áp diff:** mỗi khối `diff` có đường dẫn tính từ gốc repo. Có thể chép khối vào file rồi `git apply --3way <file>`, hoặc sửa tay theo diff. File mới thì tạo đúng nội dung trong plan.

### Hợp đồng API (tiền tố `/api/v1`, chỉ thêm mới)

| Endpoint | Body | Kết quả |
|---|---|---|
| `POST /auth/forgot-password` | `{email}` | Luôn **202** `{status: "accepted"}`. **429** `RATE_LIMITED` + `Retry-After` khi quá 3 lần/giờ/email hoặc 10 lần/giờ/IP |
| `POST /auth/reset-password` | `{token, password}` (mật khẩu 8–128 ký tự) | **200** `UserOut`. **400** `INVALID_TOKEN` (sai / đã dùng / đã bị link mới thay) hoặc `TOKEN_EXPIRED`; **403** `ACCOUNT_LOCKED`; **422** mật khẩu không hợp lệ |

Token: 32 byte ngẫu nhiên, DB chỉ lưu sha256 (`email_tokens.purpose = "reset_password"`), dùng một lần. Token xác nhận email (`purpose = "verify_email"`) **không** dùng được để đặt lại mật khẩu và ngược lại.

---

## Task 1: Backend

**Files:**
- Modify: `backend/.env.example`, `backend/app/core/config.py`
- Modify: `backend/app/modules/auth/models.py`, `schemas.py`, `service.py`, `router.py`
- Modify: `backend/app/modules/notify/templates.py`, `outbox.py`
- Test: `backend/tests/test_password_reset.py` (mới)

- [x] **Bước 1: Viết test (sẽ fail)**

`backend/tests/test_password_reset.py`:

```python
"""Quên mật khẩu: gửi link đặt lại qua email (outbox), đặt mật khẩu mới, thu hồi mọi phiên cũ."""

import re
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import EmailToken, RefreshToken, User
from app.modules.notify.models import EmailOutbox, EmailStatus
from app.modules.notify.outbox import REDACTED, send_pending
from tests.fakes import RecordingMailer
from tests.helpers import API, login, make_admin, register_user

NEW_PASSWORD = "mat-khau-moi-123"


async def _reset_mails(to: str) -> list[EmailOutbox]:
    async with SessionLocal() as db:
        stmt = (
            select(EmailOutbox)
            .where(EmailOutbox.to_email == to, EmailOutbox.template == "reset_password")
            .order_by(EmailOutbox.created_at, EmailOutbox.id)
        )
        return list((await db.scalars(stmt)).all())


def _token(mail: EmailOutbox) -> str:
    return re.search(r"reset-password\?token=([\w-]+)", mail.body_text).group(1)


def _code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


async def _forgot(client, email):
    return await client.post(f"{API}/auth/forgot-password", json={"email": email})


async def _reset(client, token, password=NEW_PASSWORD):
    return await client.post(f"{API}/auth/reset-password", json={"token": token, "password": password})


async def test_forgot_password_sends_link_and_reset_logs_out_everywhere(client, kicker):
    await register_user(client, "an@x.com", full_name="Nguyễn Văn An")
    await login(client, "an@x.com")  # một phiên đang mở

    r = await _forgot(client, "AN@x.com")
    assert r.status_code == 202 and kicker.kicks >= 1
    (mail,) = await _reset_mails("an@x.com")
    assert mail.status == EmailStatus.pending
    assert (
        "http://localhost:3000/reset-password?token=" in mail.body_text and "Nguyễn Văn An" in mail.body_html
    )

    assert (await _reset(client, _token(mail))).status_code == 200
    old = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": "password123"})
    assert _code(old) == (401, "INVALID_CREDENTIALS")
    new = await client.post(f"{API}/auth/login", json={"email": "an@x.com", "password": NEW_PASSWORD})
    assert new.status_code == 200
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "an@x.com"))
        tokens = (await db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))).all()
    # phiên mở trước khi đổi mật khẩu bị thu hồi; chỉ phiên vừa đăng nhập bằng mật khẩu mới còn dùng được
    assert sum(t.revoked_at is None for t in tokens) == 1

    # link chỉ dùng một lần
    assert _code(await _reset(client, _token(mail))) == (400, "INVALID_TOKEN")


async def test_unknown_or_locked_email_gets_202_but_no_mail(client):
    assert (await _forgot(client, "ai-do@x.com")).status_code == 202
    assert await _reset_mails("ai-do@x.com") == []
    user = await register_user(client, "khoa@x.com")
    async with SessionLocal() as db:
        await db.execute(update(User).where(User.id == uuid.UUID(user["id"])).values(locked_at=utcnow()))
        await db.commit()
    assert (await _forgot(client, "khoa@x.com")).status_code == 202
    assert await _reset_mails("khoa@x.com") == []


async def test_new_request_replaces_old_link_and_expired_link_is_rejected(client):
    user = await register_user(client, "b@x.com")
    await _forgot(client, "b@x.com")
    await _forgot(client, "b@x.com")
    old, new = await _reset_mails("b@x.com")
    assert _code(await _reset(client, _token(old))) == (400, "INVALID_TOKEN")
    async with SessionLocal() as db:
        await db.execute(
            update(EmailToken)
            .where(EmailToken.user_id == uuid.UUID(user["id"]), EmailToken.purpose == "reset_password")
            .values(expires_at=utcnow() - timedelta(minutes=1))
        )
        await db.commit()
    assert _code(await _reset(client, _token(new))) == (400, "TOKEN_EXPIRED")


async def test_reset_validates_password_and_does_not_accept_verify_tokens(client):
    await register_user(client, "c@x.com", verify=False)
    async with SessionLocal() as db:
        verify_mail = await db.scalar(
            select(EmailOutbox).where(
                EmailOutbox.to_email == "c@x.com", EmailOutbox.template == "verify_email"
            )
        )
    verify_token = re.search(r"verify-email\?token=([\w-]+)", verify_mail.body_text).group(1)
    assert _code(await _reset(client, verify_token)) == (400, "INVALID_TOKEN")

    await _forgot(client, "c@x.com")
    (mail,) = await _reset_mails("c@x.com")
    assert (await _reset(client, _token(mail), password="ngan")).status_code == 422
    # đặt lại mật khẩu qua email là đã chứng minh sở hữu hộp thư: coi như đã xác nhận email
    assert (await _reset(client, _token(mail))).status_code == 200
    r = await client.post(f"{API}/auth/login", json={"email": "c@x.com", "password": NEW_PASSWORD})
    assert r.status_code == 200


async def test_reset_by_unverified_pending_teacher_tells_admins(client):
    await make_admin(client)
    await register_user(client, "gv@x.com", role="teacher", full_name="Cô Ba", verify=False)
    await _forgot(client, "gv@x.com")
    (mail,) = await _reset_mails("gv@x.com")
    assert (await _reset(client, _token(mail))).status_code == 200
    async with SessionLocal() as db:
        notices = (
            await db.scalars(select(EmailOutbox).where(EmailOutbox.template == "new_pending_teacher"))
        ).all()
    assert [m.to_email for m in notices] == ["admin@x.com"]


async def test_forgot_password_is_rate_limited(client, limiter):
    await register_user(client, "d@x.com")
    for _ in range(3):
        assert (await _forgot(client, "d@x.com")).status_code == 202
    r = await _forgot(client, "d@x.com")
    assert _code(r) == (429, "RATE_LIMITED") and r.headers["retry-after"]
    assert any(k.startswith("pwd-reset-ip:") for k in limiter.counts)


async def test_reset_mail_body_is_redacted_after_sending(client):
    await register_user(client, "e@x.com")
    await _forgot(client, "e@x.com")
    await send_pending(SessionLocal, RecordingMailer())
    (mail,) = await _reset_mails("e@x.com")
    assert mail.status == EmailStatus.sent and mail.body_text == REDACTED
```

Chạy: `cd backend; uv run pytest tests/test_password_reset.py -q` → fail (404 / ImportError).

- [x] **Bước 2: Cấu hình**

```diff
--- a/backend/.env.example
+++ b/backend/.env.example
@@ -50,6 +50,7 @@
 APP_BASE_URL=http://localhost:3000
 EMAIL_VERIFICATION_REQUIRED=true
 VERIFY_TOKEN_HOURS=24
+RESET_TOKEN_MINUTES=60
 # Dev: Mailpit trong docker compose (SMTP_HOST=mailpit khi chạy trong Docker, localhost khi chạy uvicorn ngoài),
 # xem thư ở http://localhost:8025. Chạy thật với Brevo: SMTP_HOST=smtp-relay.brevo.com, SMTP_PORT=587,
 # SMTP_STARTTLS=true, SMTP_USER/SMTP_PASSWORD lấy ở Brevo › SMTP & API, MAIL_FROM là email đã xác minh trong Brevo.
```

```diff
--- a/backend/app/core/config.py
+++ b/backend/app/core/config.py
@@ -75,6 +75,7 @@
     # Bắt buộc bấm link xác nhận email trước khi đăng nhập được.
     email_verification_required: bool = True
     verify_token_hours: int = 24
+    reset_token_minutes: int = 60  # hiệu lực link đặt lại mật khẩu
     # SMTP. Mặc định trỏ vào Mailpit (docker compose) để dev không gửi mail thật; chạy thật thì dùng Brevo.
     smtp_host: str = "localhost"
     smtp_port: int = 1025
```

- [x] **Bước 3: Schema, template email, outbox**

`ForgotPasswordIn` hạ chữ thường email (khớp cách lưu lúc đăng ký). `reset_password` vào `SECRET_TEMPLATES`: gửi xong thì xóa nội dung (link) khỏi outbox.

```diff
--- a/backend/app/modules/auth/models.py
+++ b/backend/app/modules/auth/models.py
@@ -58,12 +58,12 @@
 
 
 class EmailToken(IdMixin, TimestampMixin, Base):
-    """Token một lần gửi qua email (hiện chỉ dùng để xác nhận email). Chỉ lưu hash, giống refresh token."""
+    """Token một lần gửi qua email (xác nhận email, đặt lại mật khẩu). Chỉ lưu hash, giống refresh token."""
 
     __tablename__ = "email_tokens"
 
     user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
-    purpose: Mapped[str] = mapped_column(String(20))  # verify_email
+    purpose: Mapped[str] = mapped_column(String(20))  # verify_email | reset_password
     token_hash: Mapped[str] = mapped_column(String(64), unique=True)
     expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
     used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

```diff
--- a/backend/app/modules/auth/schemas.py
+++ b/backend/app/modules/auth/schemas.py
@@ -40,6 +40,17 @@
     normalize_email = field_validator("email")(_lower)
 
 
+class ForgotPasswordIn(BaseModel):
+    email: EmailStr
+
+    normalize_email = field_validator("email")(_lower)
+
+
+class ResetPasswordIn(BaseModel):
+    token: str = Field(min_length=10, max_length=200)
+    password: str = Field(min_length=8, max_length=128)
+
+
 class TokenOut(BaseModel):
     access_token: str
     token_type: str = "bearer"
```

```diff
--- a/backend/app/modules/notify/templates.py
+++ b/backend/app/modules/notify/templates.py
@@ -39,6 +39,24 @@
     return subject, text, html
 
 
+def reset_password(name: str, url: str, minutes: int) -> Mail:
+    subject = "Đặt lại mật khẩu LMS-AI"
+    text = (
+        f"Chào {name},\n\nBấm link sau để đặt mật khẩu mới (hiệu lực {minutes} phút, dùng được một lần):\n{url}\n\n"
+        "Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này: mật khẩu hiện tại vẫn giữ nguyên."
+    )
+    html = _html(
+        "Đặt lại mật khẩu",
+        [
+            f"Chào {escape(name)},",
+            f"Bấm nút dưới đây để đặt mật khẩu mới. Link có hiệu lực {minutes} phút và chỉ dùng được một lần.",
+            "Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này: mật khẩu hiện tại vẫn giữ nguyên.",
+        ],
+        ("Đặt mật khẩu mới", url),
+    )
+    return subject, text, html
+
+
 def teacher_approved(name: str, url: str) -> Mail:
     subject = "Tài khoản giảng viên đã được duyệt"
     text = f"Chào {name},\n\nTài khoản giảng viên của bạn đã được duyệt. Bạn có thể tạo khóa học ngay:\n{url}"
```

```diff
--- a/backend/app/modules/notify/outbox.py
+++ b/backend/app/modules/notify/outbox.py
@@ -58,7 +58,7 @@
 RETRY_BACKOFF = timedelta(minutes=1)  # lỗi lần n thì chờ n phút rồi thử lại
 REDACTED = "[Nội dung đã xóa sau khi gửi]"
 # Email chứa link một lần (token thật): xóa nội dung sau khi gửi để DB không giữ token dạng rõ.
-SECRET_TEMPLATES = frozenset({"verify_email"})
+SECRET_TEMPLATES = frozenset({"verify_email", "reset_password"})
 
 
 async def _claim(session_factory: async_sessionmaker) -> tuple[EmailOutbox, int] | None:
```

- [x] **Bước 4: Service**

Tách `_mark_email_verified` (dùng chung cho xác nhận email và đặt lại mật khẩu). `forgot_password` vô hiệu các link đặt lại cũ còn hạn trước khi tạo link mới. `reset_password` kiểm token theo thứ tự: không có / đã dùng → `INVALID_TOKEN`, hết hạn → `TOKEN_EXPIRED`, tài khoản khóa → `ACCOUNT_LOCKED`; rồi đổi mật khẩu, đánh dấu token đã dùng, **thu hồi mọi refresh token**, xác nhận email nếu chưa, commit một lần.

```diff
--- a/backend/app/modules/auth/service.py
+++ b/backend/app/modules/auth/service.py
@@ -20,6 +20,7 @@
 from app.modules.notify.outbox import queue_email
 
 VERIFY = "verify_email"
+RESET = "reset_password"
 
 
 def _email_taken() -> AppError:
@@ -196,13 +197,20 @@
     if token.expires_at <= utcnow():
         raise AppError("TOKEN_EXPIRED", "Link xác nhận đã hết hạn, hãy gửi lại email xác nhận", 400)
     token.used_at = utcnow()
+    await _mark_email_verified(db, user)
+    await db.commit()
+    return user
+
+
+async def _mark_email_verified(db: AsyncSession, user: User) -> None:
+    """Đánh dấu email đã xác nhận (nếu chưa). Giảng viên đang chờ duyệt thì lúc này mới báo admin: chỉ báo khi
+    email đã thật; tắt bắt buộc xác nhận thì đã báo lúc đăng ký rồi."""
+    if user.email_verified_at is not None:
+        return
     user.email_verified_at = utcnow()
-    # chỉ báo admin khi email đã thật; tắt bắt buộc xác nhận thì đã báo lúc đăng ký rồi
     required = get_settings().email_verification_required
     if required and user.role == Role.teacher and user.teacher_status == TeacherStatus.pending:
         await notify_admins_pending_teacher(db, user)
-    await db.commit()
-    return user
 
 
 async def resend_verification(db: AsyncSession, email: str) -> bool:
@@ -215,6 +223,62 @@
     return True
 
 
+async def forgot_password(db: AsyncSession, email: str) -> bool:
+    """Gửi link đặt lại mật khẩu. Trả True nếu có gửi; API luôn trả 202 để không lộ email nào đã đăng ký.
+    Tài khoản bị khóa không nhận link (đặt lại mật khẩu không mở khóa được)."""
+    user = await db.scalar(select(User).where(User.email == email.lower()))
+    if user is None or user.locked_at is not None:
+        return False
+    s = get_settings()
+    # link cũ chưa dùng hết hiệu lực ngay: chỉ link mới nhất dùng được
+    await db.execute(
+        update(EmailToken)
+        .where(EmailToken.user_id == user.id, EmailToken.purpose == RESET, EmailToken.used_at.is_(None))
+        .values(used_at=utcnow())
+    )
+    raw, hashed = new_refresh_token()
+    db.add(
+        EmailToken(
+            user_id=user.id,
+            purpose=RESET,
+            token_hash=hashed,
+            expires_at=utcnow() + timedelta(minutes=s.reset_token_minutes),
+        )
+    )
+    url = f"{s.app_base_url}/reset-password?token={raw}"
+    queue_email(db, user.email, RESET, templates.reset_password(user.full_name, url, s.reset_token_minutes))
+    await db.commit()
+    return True
+
+
+async def reset_password(db: AsyncSession, raw: str, password: str) -> User:
+    """Đặt mật khẩu mới bằng link trong email: link dùng một lần, thu hồi MỌI phiên đăng nhập cũ (ai đang giữ
+    phiên bằng mật khẩu cũ đều bị đăng xuất). Bấm link trong email cũng là đã chứng minh sở hữu hộp thư nên
+    email được coi là đã xác nhận."""
+    token = await db.scalar(
+        select(EmailToken)
+        .where(EmailToken.token_hash == hash_refresh_token(raw), EmailToken.purpose == RESET)
+        .with_for_update()
+    )
+    if token is None or token.used_at is not None:
+        raise AppError("INVALID_TOKEN", "Link đặt lại mật khẩu không hợp lệ hoặc đã được dùng", 400)
+    if token.expires_at <= utcnow():
+        raise AppError("TOKEN_EXPIRED", "Link đặt lại mật khẩu đã hết hạn, hãy yêu cầu link mới", 400)
+    user = await db.get(User, token.user_id)
+    if user is None or user.locked_at is not None:
+        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
+    token.used_at = utcnow()
+    user.password_hash = hash_password(password)
+    await db.execute(
+        update(RefreshToken)
+        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
+        .values(revoked_at=utcnow())
+    )
+    await _mark_email_verified(db, user)
+    await db.commit()
+    return user
+
+
 async def request_teacher_review(db: AsyncSession, user: User) -> User:
     """Giảng viên bị từ chối gửi lại yêu cầu duyệt: quay về hàng chờ, xóa lý do cũ, báo admin."""
     if user.role != Role.teacher or user.teacher_status != TeacherStatus.rejected:
```

- [x] **Bước 5: Router**

Rate limit theo IP trước, rồi theo email (key `pwd-reset-ip:<ip>`, `pwd-reset:<email>`). `kicker.kick()` để worker gửi email ngay.

```diff
--- a/backend/app/modules/auth/router.py
+++ b/backend/app/modules/auth/router.py
@@ -9,9 +9,11 @@
 from app.modules.auth import service
 from app.modules.auth.models import User
 from app.modules.auth.schemas import (
+    ForgotPasswordIn,
     LoginIn,
     RegisterIn,
     ResendVerificationIn,
+    ResetPasswordIn,
     TokenOut,
     UserOut,
     VerifyEmailIn,
@@ -40,6 +42,8 @@
 REGISTER_IP_LIMIT = 20  # mỗi IP tối đa 20 lần đăng ký / giờ (mỗi lần đăng ký gửi một email)
 RESEND_LIMIT = 3  # mỗi email tối đa 3 lần / giờ
 RESEND_IP_LIMIT = 10  # mỗi IP tối đa 10 lần / giờ (chặn spam nhiều email khác nhau)
+RESET_LIMIT = 3  # quên mật khẩu: mỗi email tối đa 3 lần / giờ
+RESET_IP_LIMIT = 10  # và mỗi IP tối đa 10 lần / giờ
 
 
 def _too_many(wait: int) -> AppError:
@@ -106,6 +110,34 @@
     return {"status": "accepted"}
 
 
+@router.post("/auth/forgot-password", status_code=202)
+async def forgot_password(
+    data: ForgotPasswordIn,
+    request: Request,
+    db: AsyncSession = Depends(get_db),
+    limiter: RateLimiter = Depends(get_rate_limiter),
+    kicker: MailKicker = Depends(get_mail_kicker),
+) -> dict:
+    """Gửi link đặt lại mật khẩu. Luôn 202 (không lộ email nào đã đăng ký). 429 RATE_LIMITED khi quá 3 lần/giờ
+    cho một email hoặc quá 10 lần/giờ từ một IP."""
+    await _limit(limiter, f"pwd-reset-ip:{_ip(request)}", RESET_IP_LIMIT)
+    await _limit(limiter, f"pwd-reset:{data.email}", RESET_LIMIT)
+    if await service.forgot_password(db, data.email):
+        await kicker.kick()
+    return {"status": "accepted"}
+
+
+@router.post("/auth/reset-password", response_model=UserOut)
+async def reset_password(
+    data: ResetPasswordIn, db: AsyncSession = Depends(get_db), kicker: MailKicker = Depends(get_mail_kicker)
+):
+    """Đặt mật khẩu mới. 400 INVALID_TOKEN (sai / đã dùng / đã thay bằng link mới) hoặc TOKEN_EXPIRED;
+    403 ACCOUNT_LOCKED. Thành công thì mọi phiên đăng nhập cũ bị thu hồi."""
+    user = await service.reset_password(db, data.token, data.password)
+    await kicker.kick()  # giảng viên chưa xác nhận email vừa xác nhận qua link này: báo admin
+    return user
+
+
 @router.post("/me/teacher-request", response_model=UserOut)
 async def request_teacher_review(
     user: User = Depends(get_current_user),
```

- [x] **Bước 6: Chạy test**

```powershell
cd backend
uv run pytest tests/test_password_reset.py tests/test_email.py tests/test_config.py -q
uv run ruff check . ; uv run ruff format --check .
uv run lint-imports
```

Kỳ vọng: pass hết (7 test mới); ruff, lint-imports sạch.

- [x] **Bước 7: Commit**

```powershell
git add backend
git commit -m "feat(auth): quên mật khẩu qua email (link 60 phút, thu hồi phiên cũ)"
```

---

## Task 2: Frontend

**Files:**
- Create: `frontend/src/lib/auth/password-reset.ts`, `password-reset.test.ts`
- Create: `frontend/src/app/(auth)/forgot-password/page.tsx`, `forgot-password-form.tsx`
- Create: `frontend/src/app/(auth)/reset-password/page.tsx`, `reset-password-form.tsx`
- Modify: `frontend/src/app/(auth)/login/login-form.tsx`
- Regenerate: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`

- [ ] **Bước 1: Sinh lại kiểu API** (backend Task 1 phải xong)

```powershell
cd frontend
npm run gen:api
```

Kỳ vọng: `schema.d.ts` có `"/api/v1/auth/forgot-password"`, `"/api/v1/auth/reset-password"`, `ForgotPasswordIn`, `ResetPasswordIn`.

- [ ] **Bước 2: Hook + test**

```ts
"use client";

import { useMutation } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

/** Xin link đặt lại mật khẩu. API luôn trả 202 (không lộ email nào đã đăng ký); 429 khi xin quá nhiều lần. */
export function useForgotPassword() {
  return useMutation({
    mutationFn: (email: string) => unwrap(api.POST("/api/v1/auth/forgot-password", { body: { email } })),
  });
}

/** Đặt mật khẩu mới bằng token trong link. Thành công thì mọi phiên đăng nhập cũ bị thu hồi. */
export function useResetPassword() {
  return useMutation({
    mutationFn: (body: { token: string; password: string }) =>
      unwrap(api.POST("/api/v1/auth/reset-password", { body })),
  });
}

export function forgotErrorMessage(err: unknown) {
  if (err instanceof ApiError && err.status === 429) {
    const minutes = Math.max(1, Math.ceil((err.retryAfter ?? 60) / 60));
    return `Bạn đã yêu cầu quá nhiều lần. Thử lại sau khoảng ${minutes} phút.`;
  }
  return err instanceof Error ? err.message : "Không gửi được email";
}

/** Link hỏng / hết hạn / đã dùng: người dùng cần xin link mới (khác lỗi mạng, lỗi mật khẩu). */
export function isDeadResetLink(err: unknown) {
  return err instanceof ApiError && (err.code === "INVALID_TOKEN" || err.code === "TOKEN_EXPIRED");
}
```

```ts
import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { forgotErrorMessage, isDeadResetLink } from "./password-reset";

describe("password reset helpers", () => {
  it("429: báo số phút phải chờ", () => {
    expect(forgotErrorMessage(new ApiError(429, "RATE_LIMITED", "x", null, {}, 1500))).toContain("khoảng 25 phút");
  });
  it("chỉ link hỏng / hết hạn mới bắt xin link mới", () => {
    expect(isDeadResetLink(new ApiError(400, "INVALID_TOKEN", "x", null, {}, null))).toBe(true);
    expect(isDeadResetLink(new ApiError(400, "TOKEN_EXPIRED", "x", null, {}, null))).toBe(true);
    expect(isDeadResetLink(new ApiError(422, "VALIDATION_ERROR", "x", null, {}, null))).toBe(false);
    expect(isDeadResetLink(new Error("mất mạng"))).toBe(false);
  });
});
```

- [ ] **Bước 3: Trang "Quên mật khẩu"**

Gửi xong thì chuyển sang trạng thái "Kiểm tra hộp thư" (tiêu đề nhận focus cho trình đọc màn hình), có nút "Gửi lại hoặc dùng email khác". 429 báo ngay dưới ô email.

```tsx
import { Suspense } from "react";
import { ForgotPasswordForm } from "./forgot-password-form";

export const metadata = { title: "Quên mật khẩu" };

export default function ForgotPasswordPage() {
  return (
    <Suspense>
      <ForgotPasswordForm />
    </Suspense>
  );
}
```

```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { forgotErrorMessage, useForgotPassword } from "@/lib/auth/password-reset";

const schema = z.object({ email: z.email("Email không hợp lệ") });
type Values = z.infer<typeof schema>;

export function ForgotPasswordForm() {
  const params = useSearchParams();
  const forgot = useForgotPassword();
  const [sentTo, setSentTo] = React.useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: params.get("email") ?? "" } });
  const { errors } = form.formState;
  const heading = React.useRef<HTMLHeadingElement>(null);
  React.useEffect(() => {
    if (sentTo) heading.current?.focus();
  }, [sentTo]);

  async function onSubmit(values: Values) {
    const email = values.email.trim().toLowerCase();
    try {
      await forgot.mutateAsync(email);
      setSentTo(email);
    } catch (err) {
      form.setError("email", { message: forgotErrorMessage(err) }, { shouldFocus: true });
    }
  }

  if (sentTo)
    return (
      <div className="text-center">
        <MailCheck className="mx-auto size-10 text-primary" aria-hidden />
        <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
          Kiểm tra hộp thư
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Nếu {sentTo} đã đăng ký, chúng tôi vừa gửi link đặt lại mật khẩu (hiệu lực 60 phút). Xem cả mục Spam.
        </p>
        <Button variant="outline" className="mt-6 w-full" onClick={() => setSentTo(null)}>
          Gửi lại hoặc dùng email khác
        </Button>
        <p className="mt-4 text-sm">
          <Link href="/login" className="font-medium text-primary underline underline-offset-4">
            Quay lại đăng nhập
          </Link>
        </p>
      </div>
    );

  return (
    <>
      <h1 className="text-2xl font-semibold">Quên mật khẩu</h1>
      <p className="mt-1 text-sm text-muted-foreground">Nhập email đã đăng ký, chúng tôi sẽ gửi link để đặt mật khẩu mới.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <Field id="email" label="Email" error={errors.email?.message}>
          <Input type="email" autoComplete="email" inputMode="email" {...form.register("email")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={forgot.isPending} loadingText="Đang gửi…">
          Gửi link đặt lại mật khẩu
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">
        Nhớ ra rồi?{" "}
        <Link href="/login" className="font-medium text-primary underline underline-offset-4">
          Đăng nhập
        </Link>
      </p>
    </>
  );
}
```

- [ ] **Bước 4: Trang "Đặt lại mật khẩu"**

Ba trạng thái: `form` → `done` ("Đã đặt mật khẩu mới" + link Đăng nhập) hoặc `dead` (link sai / đã dùng / hết hạn: "Link không dùng được" + link "Gửi link mới"). Thiếu `?token` thì vào thẳng `dead`.

```tsx
import { Suspense } from "react";
import { ResetPasswordForm } from "./reset-password-form";

export const metadata = { title: "Đặt mật khẩu mới" };

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordForm />
    </Suspense>
  );
}
```

```tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/errors";
import { isDeadResetLink, useResetPassword } from "@/lib/auth/password-reset";

const schema = z
  .object({
    password: z.string().min(8, "Mật khẩu ít nhất 8 ký tự").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Hai mật khẩu chưa khớp" });
type Values = z.infer<typeof schema>;

export function ResetPasswordForm() {
  const token = useSearchParams().get("token");
  const reset = useResetPassword();
  const [state, setState] = React.useState<"form" | "done" | "dead">(token ? "form" : "dead");
  const [deadMessage, setDeadMessage] = React.useState("Thiếu mã đặt lại trong link.");
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { password: "", confirm: "" } });
  const { errors } = form.formState;
  const heading = React.useRef<HTMLHeadingElement>(null);
  React.useEffect(() => {
    if (state !== "form") heading.current?.focus();
  }, [state]);

  async function onSubmit(values: Values) {
    try {
      await reset.mutateAsync({ token: token!, password: values.password });
      setState("done");
    } catch (err) {
      if (isDeadResetLink(err)) {
        setDeadMessage(errorMessage(err));
        setState("dead");
        return;
      }
      form.setError("password", { message: errorMessage(err) }, { shouldFocus: true });
    }
  }

  if (state === "done")
    return (
      <div className="text-center">
        <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
        <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
          Đã đặt mật khẩu mới
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Bạn đã được đăng xuất khỏi mọi thiết bị. Đăng nhập lại bằng mật khẩu mới.
        </p>
        <Button asChild size="lg" className="mt-6 w-full">
          <Link href="/login">Đăng nhập</Link>
        </Button>
      </div>
    );

  if (state === "dead")
    return (
      <div className="text-center">
        <XCircle className="mx-auto size-10 text-destructive" aria-hidden />
        <h1 ref={heading} tabIndex={-1} className="mt-3 text-2xl font-semibold outline-none">
          Link không dùng được
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{deadMessage} Mỗi link chỉ dùng được một lần.</p>
        <Button asChild size="lg" className="mt-6 w-full">
          <Link href="/forgot-password">Gửi link mới</Link>
        </Button>
      </div>
    );

  return (
    <>
      <h1 className="text-2xl font-semibold">Đặt mật khẩu mới</h1>
      <p className="mt-1 text-sm text-muted-foreground">Sau khi đổi, mọi phiên đăng nhập cũ sẽ bị đăng xuất.</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <Field id="password" label="Mật khẩu mới" error={errors.password?.message} hint="Ít nhất 8 ký tự">
          <Input type="password" autoComplete="new-password" {...form.register("password")} />
        </Field>
        <Field id="confirm" label="Nhập lại mật khẩu mới" error={errors.confirm?.message}>
          <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={reset.isPending} loadingText="Đang lưu…">
          Đặt mật khẩu mới
        </Button>
      </form>
    </>
  );
}
```

- [ ] **Bước 5: Link trên trang đăng nhập**

```diff
--- a/frontend/src/app/(auth)/login/login-form.tsx
+++ b/frontend/src/app/(auth)/login/login-form.tsx
@@ -56,6 +56,11 @@
         <Field id="password" label="Mật khẩu" error={errors.password?.message}>
           <Input type="password" autoComplete="current-password" {...form.register("password")} />
         </Field>
+        <p className="-mt-2 text-right text-sm">
+          <Link href="/forgot-password" className="text-primary underline underline-offset-4">
+            Quên mật khẩu?
+          </Link>
+        </p>
         {unverified ? (
           <div role="alert" className="space-y-3 rounded-md border border-accent/60 p-3 text-sm">
             <p>Bạn cần xác nhận email trước khi đăng nhập. Mở email chúng tôi đã gửi tới {unverified} và bấm link xác nhận.</p>
```

- [ ] **Bước 6: Kiểm tra**

```powershell
npx tsc --noEmit ; npx eslint .
npx vitest run src/lib/auth
```

Kỳ vọng: sạch; test `password-reset` pass.

- [ ] **Bước 7: Commit**

```powershell
git add frontend
git commit -m "feat(web): trang quên mật khẩu và đặt lại mật khẩu"
```

---

## Task 3: E2E

**Files:** Create `frontend/e2e/auth-password.spec.ts`

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { mockApi, student } from "./mock-api";

const err = (code: string, message: string) => ({ error: { code, message, details: {}, request_id: "rq-e2e" } });

test.describe("quên mật khẩu", () => {
  test("từ trang đăng nhập xin link đặt lại; gửi quá nhiều lần thì báo thời gian chờ", async ({ page }) => {
    const bodies: unknown[] = [];
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/forgot-password": (r) => {
          bodies.push(r.request().postDataJSON());
          return bodies.length === 1
            ? r.fulfill({ status: 202, json: { status: "accepted" } })
            : r.fulfill({ status: 429, headers: { "Retry-After": "600" }, json: err("RATE_LIMITED", "Chậm lại") });
        },
      },
    });
    await page.goto("/login");
    await page.getByRole("link", { name: "Quên mật khẩu?" }).click();
    await expect(page.getByRole("heading", { name: "Quên mật khẩu" })).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
    await page.getByLabel("Email").fill("An@SV.vn");
    await page.getByRole("button", { name: "Gửi link đặt lại mật khẩu" }).click();
    await expect(page.getByRole("heading", { name: "Kiểm tra hộp thư" })).toBeFocused();
    await expect(page.getByText(/Nếu an@sv\.vn đã đăng ký/)).toBeVisible();
    expect(bodies[0]).toEqual({ email: "an@sv.vn" });

    await page.getByRole("button", { name: "Gửi lại hoặc dùng email khác" }).click();
    await page.getByLabel("Email").fill("an@sv.vn");
    await page.getByRole("button", { name: "Gửi link đặt lại mật khẩu" }).click();
    await expect(page.getByText(/Thử lại sau khoảng 10 phút/)).toBeVisible();
  });

  test("đặt mật khẩu mới: kiểm khớp hai ô, thành công thì mời đăng nhập lại", async ({ page }) => {
    let body: unknown = null;
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/reset-password": (r) => {
          body = r.request().postDataJSON();
          return r.fulfill({ json: { ...student, email_verified: true } });
        },
      },
    });
    await page.goto("/reset-password?token=tok-123456789");
    await expect(page.getByRole("heading", { name: "Đặt mật khẩu mới" })).toBeVisible();
    await expectAccessible(page);
    await page.getByLabel("Mật khẩu mới", { exact: true }).fill("matkhau-moi-1");
    await page.getByLabel("Nhập lại mật khẩu mới").fill("matkhau-khac");
    await page.getByRole("button", { name: "Đặt mật khẩu mới" }).click();
    await expect(page.getByText("Hai mật khẩu chưa khớp")).toBeVisible();
    expect(body).toBeNull();

    await page.getByLabel("Nhập lại mật khẩu mới").fill("matkhau-moi-1");
    await page.getByRole("button", { name: "Đặt mật khẩu mới" }).click();
    await expect(page.getByRole("heading", { name: "Đã đặt mật khẩu mới" })).toBeFocused();
    expect(body).toEqual({ token: "tok-123456789", password: "matkhau-moi-1" });
    await page.getByRole("link", { name: "Đăng nhập" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("link đã dùng hoặc hết hạn: báo rõ và cho xin link mới", async ({ page }) => {
    await mockApi(page, {
      user: null,
      extra: {
        "POST /auth/reset-password": (r) =>
          r.fulfill({ status: 400, json: err("TOKEN_EXPIRED", "Link đặt lại mật khẩu đã hết hạn, hãy yêu cầu link mới") }),
      },
    });
    await page.goto("/reset-password?token=tok-cu-123456");
    await page.getByLabel("Mật khẩu mới", { exact: true }).fill("matkhau-moi-1");
    await page.getByLabel("Nhập lại mật khẩu mới").fill("matkhau-moi-1");
    await page.getByRole("button", { name: "Đặt mật khẩu mới" }).click();
    await expect(page.getByRole("heading", { name: "Link không dùng được" })).toBeFocused();
    await expect(page.getByText(/đã hết hạn/)).toBeVisible();
    await page.getByRole("link", { name: "Gửi link mới" }).click();
    await expect(page.getByRole("heading", { name: "Quên mật khẩu" })).toBeVisible();
  });
});
```

- [ ] Chạy: `npx playwright test e2e/auth-password.spec.ts e2e/auth-email.spec.ts e2e/student.spec.ts` → pass (cả 375px và 1280px).
- [ ] Commit: `git commit -am "test(e2e): quên mật khẩu"` (nhớ `git add` file mới).

---

## Task 4: Kiểm tay (bạn làm)

Docker đang chạy, `.env` để `*_PROVIDER=fake`. Sau khi pull code: `docker compose up -d --build api worker` rồi `cd backend; uv run alembic upgrade head` (plan này không có migration, nhưng hai plan sau có).

- [ ] Trang đăng nhập → **Quên mật khẩu?** → nhập email học viên có thật → thấy "Kiểm tra hộp thư".
- [ ] Mở Mailpit (http://localhost:8025): có email "Đặt lại mật khẩu LMS-AI" với link. Bấm link → đặt mật khẩu mới (thử nhập 2 ô khác nhau: báo "Hai mật khẩu chưa khớp").
- [ ] Đăng nhập bằng mật khẩu mới được; mật khẩu cũ không được. Tab trình duyệt khác đang đăng nhập tài khoản đó bị đăng xuất ở lần làm mới token kế tiếp.
- [ ] Bấm lại đúng link cũ → "Link không dùng được" → "Gửi link mới" đưa về trang quên mật khẩu.
- [ ] Xin link 2 lần liên tiếp: link trong email thứ nhất không dùng được nữa.
- [ ] Gửi 4 lần cho cùng email trong một giờ: lần thứ 4 báo "thử lại sau khoảng N phút".
- [ ] Nhập email không tồn tại: vẫn "Kiểm tra hộp thư", Mailpit không có email mới.
- [ ] Trong DB (bảng `email_outbox`): sau khi gửi, `body_text` của email đặt lại thành "[Nội dung đã xóa sau khi gửi]", giống email xác nhận (Mailpit vẫn giữ bản đã nhận, bình thường).
