# Sửa lỗi sau rà soát toàn dự án: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** ngày 28/10, Claude rà soát toàn bộ code ở HEAD `1691c26` bằng 4 lượt review song song: backend lõi, phần AI, frontend và đối chiếu với spec. Không có lỗi nghiêm trọng, nhưng có 6 lỗi đáng sửa trước khi demo và một số lỗi nhỏ. Plan này sửa hết các lỗi đó và cập nhật bảng tiến độ trong spec cho đúng thực tế.

**Lỗi được sửa:**

| # | Lỗi | Cách sửa |
|---|---|---|
| 1 | Đổi mật khẩu khi đăng nhập ở 2 máy: máy còn lại gửi refresh token cũ, backend tưởng token bị đánh cắp và thu hồi luôn phiên mới của máy vừa đổi | Thêm cột `refresh_tokens.rotated_at`. Chỉ token bị xoay (refresh) mà bị dùng lại mới coi là bị đánh cắp. Token bị thu hồi vì đăng xuất, đổi mật khẩu hay khóa tài khoản chỉ bị từ chối (`401 INVALID_TOKEN`) |
| 2 | "Sinh lại" trong AI Studio ra y nguyên bản cũ (lấy từ `llm_cache`) | Báo cáo và flashcard gọi AI với `use_cache=False` |
| 3 | AI giải thích câu sai và gợi ý hỏi tiếp giữ kết nối DB trong lúc chờ AI. Khi Gemini miễn phí báo 429 và phải thử lại thì cạn pool kết nối, cả web treo | `rollback` (trả kết nối) trước khi gọi AI, sau đó ghi kết quả bằng một câu `UPDATE` ngắn |
| 4 | Bài làm gần nhất lưu ở localStorage: đổi tài khoản trên cùng máy thì thấy điểm người khác; sang máy khác thì không xem lại được kết quả; quiz quá giờ vẫn hiện "Làm tiếp" | `GET /quizzes` và `GET /quizzes/{id}` trả `my_last_attempt` cho học viên (id, trạng thái, điểm, `expired`). Bỏ `attempt-store.ts` |
| 5 | Giảng viên bị từ chối đăng nhập thì bị đưa vào `/teach`, không thấy nút "Gửi lại yêu cầu duyệt" (nút chỉ có ở trang chủ) | Giảng viên chưa được duyệt về `/` sau đăng nhập; thanh điều hướng có "Trang chủ"; trang chặn có nút "Về trang chủ" |
| 6 | Mục lục bài học không bao giờ hiện dấu đã học | `GET /courses/{slug}` trả `done_lesson_ids` khi người xem đã đăng ký. Mục lục đọc trường này; học xong một bài thì tải lại khóa |

**Lỗi nhỏ sửa kèm:**

- Lọc REFUSE nhận cả `**REFUSE**` và "REFUSE" có dòng viết thêm phía sau. Trước đây hai dạng này lọt ra cho học viên.
- Rớt kết nối mạng (`ConnectError`, "Server disconnected") được thử lại như timeout.
- Tìm khóa học: `%` và `_` là ký tự thường, không còn khớp mọi khóa.
- `video_position_sec`, `duration_sec` có giới hạn trên, nên số quá lớn trả 422 thay vì 500.
- Chữ trên giao diện:
  - Hộp xuất bản quiz không còn nói "chỉ đổi được tiêu đề", vì nút Sửa không hiện ở quiz đã xuất bản.
  - Hộp xóa bài và xóa chương nói đúng là bài đã có học viên học thì không xóa được.
- Trên điện thoại, hộp "Đăng ký khóa học" không còn che bài cuối cùng của mục lục.
- Trang đăng ký có viền focus ở ô chọn vai trò khi dùng bàn phím.

**Không sửa trong plan này:** đây là những việc cần bạn quyết hoặc phải chạy thật.

- Temperature 0 với Gemini 3: cần thử với AI thật trước.
- Hạn mức ngày (429 daily quota) vẫn bị thử lại.
- Lịch sử AI Tutor chỉ tải 100 tin.
- Upload không giới hạn dung lượng.
- `JWT_SECRET` trống ở bản production.

**Migration:** `c5a8e2f9d104` (sau `b9e1d4c7a352`) thêm `refresh_tokens.rotated_at`. Các token đã bị thu hồi từ trước được coi là đã bị xoay, để giữ nguyên cách phát hiện cũ. Docker Compose tự chạy `alembic upgrade head` khi khởi động API.

**Thứ tự làm:** **sau** `2026-10-19-discussion-notifications-insights-plan.md`. Diff tạo trên HEAD `1691c26`.

**Mã trong plan đã được chạy thử** trên HEAD `1691c26`:

- **Backend:** **806 test pass** (797 + 9 mới). `ruff check`, `ruff format --check` sạch, `lint-imports` 6 hợp đồng KEPT. Migration lên/xuống sạch, `alembic check` không lệch so với model. ERD đã sinh lại.
- **Frontend:** `tsc`, `eslint` sạch.
  - Unit test: **184 pass** (180 + 4 mới).
  - E2E cả bộ: **103 pass + 1 bỏ qua có chủ ý**.
  - Một lần chạy có kịch bản "ẩn khóa học" ở khung 375px báo axe `aria-prohibited-attr: :root`. Chạy lại `admin.spec.ts` 3 lần (60 lượt) đều pass. Đây là lỗi chập chờn do thời điểm hộp thoại đóng, không liên quan plan này. Nếu gặp thì chạy lại.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6, nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Commit **không** thêm dòng `Co-Authored-By` hay `Claude-Session`.

---

## Task 1: Đổi mật khẩu không làm chính máy đó bị đăng xuất (lỗi 1)

**Files:**
- Modify: `backend/app/modules/auth/models.py`, `backend/app/modules/auth/service.py`, `backend/tests/test_refresh.py`
- Create: `backend/alembic/versions/c5a8e2f9d104_refresh_token_rotated_at.py`
- Regenerate: `docs/architecture/erd.md`

- [x] **Bước 1: Test (sẽ fail).** Máy "phone" giữ token cũ. Máy "laptop" đổi mật khẩu và nhận token mới. Phone refresh thì bị từ chối, laptop vẫn refresh được.

```diff
--- a/backend/tests/test_refresh.py
+++ b/backend/tests/test_refresh.py
@@ -51,3 +51,25 @@
     assert "refresh_token=" in out.headers["set-cookie"]  # cookie bị xóa
     r = await _refresh_with(client, raw)
     assert r.status_code == 401
+
+
+async def test_token_revoked_by_password_change_does_not_log_out_new_session(client):
+    """Máy B còn giữ refresh token cũ sau khi người dùng đổi mật khẩu ở máy A: B bị từ chối, A vẫn đăng nhập."""
+    await register_user(client, "r4@x.com")
+    phone = await _login_raw(client, "r4@x.com")
+    login = await client.post(f"{API}/auth/login", json={"email": "r4@x.com", "password": "password123"})
+    client.cookies.clear()
+    changed = await client.post(
+        f"{API}/me/password",
+        json={"current_password": "password123", "new_password": "newpass12345"},
+        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
+    )
+    assert changed.status_code == 200, changed.text
+    laptop_new = changed.cookies["refresh_token"]
+
+    stale = await _refresh_with(client, phone)
+    assert stale.status_code == 401
+    assert stale.json()["error"]["code"] == "INVALID_TOKEN"
+
+    still = await _refresh_with(client, laptop_new)  # phiên vừa đổi mật khẩu vẫn còn
+    assert still.status_code == 200
```

- [x] **Bước 2: Model, service, migration**

```diff
--- a/backend/app/modules/auth/models.py
+++ b/backend/app/modules/auth/models.py
@@ -55,6 +55,9 @@
     token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
     expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
     revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
+    # Chỉ có khi token bị thu hồi vì đã xoay sang token mới (refresh). Dùng lại token loại này mới là dấu hiệu bị
+    # đánh cắp; token bị thu hồi vì đăng xuất, đổi/đặt lại mật khẩu hay khóa tài khoản thì chỉ bị từ chối.
+    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
 
 
 class EmailToken(IdMixin, TimestampMixin, Base):
```

```diff
--- a/backend/app/modules/auth/service.py
+++ b/backend/app/modules/auth/service.py
@@ -89,6 +89,10 @@
     )
     if token is None:
         raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
+    if token.revoked_at is not None and token.rotated_at is None:
+        # Thu hồi vì đăng xuất, đổi/đặt lại mật khẩu hay khóa tài khoản: chỉ từ chối, không đụng tới phiên khác
+        # (vd. máy còn lại gửi token cũ sau khi người dùng đổi mật khẩu ở máy này).
+        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
     if token.revoked_at is not None:
         # Token đã bị xoay mà vẫn có người dùng lại, coi như bị đánh cắp: thu hồi toàn bộ phiên của user.
         await db.execute(
@@ -103,7 +107,7 @@
     user = await db.get(User, token.user_id)
     if user is None or user.locked_at is not None:
         raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
-    token.revoked_at = utcnow()
+    token.revoked_at = token.rotated_at = utcnow()
     return await issue_tokens(db, user)
 
 
```

```python
"""refresh_tokens.rotated_at: chỉ token bị xoay mới coi là bị đánh cắp khi dùng lại

Revision ID: c5a8e2f9d104
Revises: b9e1d4c7a352
Create Date: 2026-10-28 09:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5a8e2f9d104"
down_revision: str | Sequence[str] | None = "b9e1d4c7a352"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))
    # Không biết token đã thu hồi trước đây bị thu hồi vì lý do gì: coi như bị xoay để giữ cách phát hiện cũ.
    op.execute("UPDATE refresh_tokens SET rotated_at = revoked_at WHERE revoked_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("refresh_tokens", "rotated_at")
```

- [x] **Bước 3: Chạy test, migration, ERD, commit**

```powershell
docker compose up -d db redis
cd backend
uv run pytest tests/test_refresh.py tests/test_auth.py -q
uv run alembic upgrade head ; uv run alembic downgrade -1 ; uv run alembic upgrade head
uv run alembic check                                      # No new upgrade operations detected
uv run python -m scripts.gen_erd                          # erd.md thêm dòng rotated_at
uv run ruff check . ; uv run ruff format --check .
cd ..
git add backend docs/architecture/erd.md
git commit -m "fix(auth): chỉ token bị xoay mới coi là bị đánh cắp khi dùng lại (đổi mật khẩu không đăng xuất chính máy đó)"
```

---

## Task 2: AI chạy ổn hơn với nhà cung cấp thật (lỗi 2, 3 và lọc REFUSE, thử lại khi rớt mạng)

**Files:**
- Modify: `backend/app/modules/studio/generation.py`, `backend/app/modules/studio/service.py`, `backend/app/modules/quiz/explain.py`, `backend/app/modules/tutor/text.py`, `backend/app/ai/retry.py`
- Modify tests: `backend/tests/test_studio.py`, `backend/tests/test_tutor_text.py`, `backend/tests/test_ai_retry.py`

- [x] **Bước 1: Test (sẽ fail)**
  - Test "Sinh lại" bật cache: bản thứ hai phải khác bản thứ nhất.
  - Test REFUSE: thêm dạng in đậm, dạng có dòng sau, dạng trong backtick.
  - Test rớt kết nối thì được thử lại.

```diff
--- a/backend/tests/test_studio.py
+++ b/backend/tests/test_studio.py
@@ -85,6 +85,17 @@
     assert out.prompt_version == "studio_study_guide@v1"
 
 
+async def test_regenerating_report_calls_ai_again(client, db):
+    """ "Sinh lại" với cùng tài liệu phải gọi AI lần nữa, không lấy lại bản cũ trong llm_cache."""
+    _, _, course, lesson = await _course_with_chunks(client, db)
+    chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
+    provider = FakeLLMProvider(["## Bản một [1]", "## Bản hai [1]"])
+    llm = _llm(provider, llm_cache_enabled=True)
+    first = await generate_report(llm, ArtifactKind.study_guide, "Bài: X", chunks, get_settings())
+    second = await generate_report(llm, ArtifactKind.study_guide, "Bài: X", chunks, get_settings())
+    assert (first.content_md, second.content_md) == ("## Bản một [1]", "## Bản hai [1]")
+
+
 async def test_long_material_is_mapped_then_reduced(client, db):
     _, _, course, lesson = await _course_with_chunks(client, db, ["a " * 50, "b " * 50, "c " * 50])
     chunks = await load_scope_chunks(db, uuid.UUID(course["id"]), uuid.UUID(lesson["id"]))
```

```diff
--- a/backend/tests/test_tutor_text.py
+++ b/backend/tests/test_tutor_text.py
@@ -28,6 +28,16 @@
         assert _run(pieces) == ("", True)
 
 
+def test_refuse_with_markdown_or_extra_lines_is_still_refusal():
+    for pieces in (
+        ["**REFUSE**"],
+        ["REFUSE\n\nTài liệu ", "không đề cập."],
+        ["`REF", "USE`\nxin lỗi"],
+        ["_REFUSE._"],
+    ):
+        assert _run(pieces) == ("", True), pieces
+
+
 def test_normal_answer_passes_through_immediately():
     f = RefuseFilter()
     assert f.feed("Tìm") == "Tìm" and f.feed(" kiếm") == " kiếm"
```

```diff
--- a/backend/tests/test_ai_retry.py
+++ b/backend/tests/test_ai_retry.py
@@ -83,6 +83,15 @@
     assert models.calls == 2 and sleep.delays == [1.0]
 
 
+async def test_dropped_connection_is_retried():
+    sleep = Sleeps()
+    e, models = embedder(
+        [httpx.RemoteProtocolError("Server disconnected"), httpx.ConnectError("x"), None], sleep
+    )
+    assert await e.embed_query("q") == [0.6, 0.8]
+    assert models.calls == 3
+
+
 async def test_asyncio_timeout_is_retried_too():
     sleep = Sleeps()
     v, models = vision([TimeoutError(), None], sleep)
```

- [x] **Bước 2: Sửa code**
  - AI Studio: lời gọi cuối của báo cáo và flashcard không dùng cache. Bước tóm tắt từng phần (map) vẫn dùng cache, vì phần tài liệu không đổi thì kết quả tóm tắt như cũ.
  - `explain_answer`, `followups`:
    - Đọc xong mọi thứ cần thiết rồi mới `await db.rollback()`. Sau rollback, các object ORM hết hạn, không được đọc lại thuộc tính của chúng.
    - Gọi AI.
    - Ghi kết quả bằng một câu `UPDATE` theo khóa chính rồi commit.
  - Giải thích câu sai chỉ ghi khi `ai_explanation` còn trống, để hai lần bấm cùng lúc không ghi đè nhau.
  - Lọc REFUSE xét **dòng đầu tiên** sau khi bỏ `*`, `_`, `` ` ``, dấu chấm. "REFUSE nhưng vẫn trả lời" (cùng dòng) vẫn là câu trả lời thường, như test cũ.

```diff
--- a/backend/app/modules/studio/generation.py
+++ b/backend/app/modules/studio/generation.py
@@ -154,7 +154,9 @@
         raise ValueError(NO_CONTENT_ERROR)
     context, _, _ = await _context_for(llm, title, chunks, settings)
     prompt = load_prompt(f"studio_{kind.value}").render(scope=title, context=context)
-    result = await llm.generate(prompt, op=f"studio_{kind.value}")
+    # Không dùng cache: job studio chỉ chạy lại với cùng ngữ cảnh khi giảng viên bấm "Sinh lại", lúc đó cache sẽ
+    # trả nguyên bản cũ (temperature 0, cùng prompt).
+    result = await llm.generate(prompt, op=f"studio_{kind.value}", use_cache=False)
     content, cited = clean_citations(result.text.strip(), len(chunks))
     return ReportResult(
         content_md=content, citations=citations_for(cited, chunks), prompt_version=prompt.prompt_version
@@ -196,7 +198,7 @@
         count = _cards_wanted(sum(c.token_count for _, c in part))
         prompt = template.render(scope=title, count=count, context=numbered_context(part))
         try:
-            batch, _ = await llm.generate_json(prompt, CardBatch, op="studio_flashcards")
+            batch, _ = await llm.generate_json(prompt, CardBatch, op="studio_flashcards", use_cache=False)
         except LLMOutputError:
             logger.warning("Bỏ một phần flashcard: AI trả JSON sai schema")
             continue
```

```diff
--- a/backend/app/modules/studio/service.py
+++ b/backend/app/modules/studio/service.py
@@ -4,7 +4,7 @@
 import uuid
 
 from pydantic import BaseModel, Field
-from sqlalchemy import delete, func, insert, select
+from sqlalchemy import delete, func, insert, select, update
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from app.ai.llm_client import LLMClient
@@ -486,6 +486,8 @@
         answer=message.content,
         sections="\n".join(f"- {h}" for h in headings if h) or "-",
     )
+    message_pk = message.id
+    await db.rollback()  # trả kết nối về pool trong lúc chờ AI
     try:
         result, _ = await llm.generate_json(
             prompt, _Followups, op="tutor_followups", model=get_settings().llm_cheap_model
@@ -494,6 +496,6 @@
         logger.warning("Không sinh được gợi ý hỏi tiếp cho tin %s", message_id, exc_info=True)
         return FollowupsOut(questions=[])
     questions = [" ".join(q.split())[:150] for q in result.questions if q.strip()][:3]
-    message.followups = questions
+    await db.execute(update(ChatMessage).where(ChatMessage.id == message_pk).values(followups=questions))
     await db.commit()
     return FollowupsOut(questions=questions)
```

```diff
--- a/backend/app/modules/quiz/explain.py
+++ b/backend/app/modules/quiz/explain.py
@@ -8,7 +8,7 @@
 import logging
 import uuid
 
-from sqlalchemy import select
+from sqlalchemy import select, update
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from app.ai.llm_client import LLMClient
@@ -87,6 +87,9 @@
         explanation=question.explanation or "(không có)",
         source=chunk.content if chunk else "(không có đoạn tài liệu nguồn)",
     )
+    has_answer, attempt_pk = answer is not None, attempt.id
+    # Kết thúc transaction đọc để trả kết nối về pool trước khi chờ AI (có thể vài phút khi bị 429 và phải thử lại).
+    await db.rollback()
     try:
         result = await llm.generate(prompt, op="quiz_explain")
     except Exception as e:
@@ -97,7 +100,15 @@
     text = result.text.strip()
     if not text:
         raise AppError("AI_UNAVAILABLE", "AI tạm thời không giải thích được, vui lòng thử lại sau", 503)
-    if answer is not None:
-        answer.ai_explanation = text
+    if has_answer:
+        await db.execute(
+            update(AttemptAnswer)
+            .where(
+                AttemptAnswer.attempt_id == attempt_pk,
+                AttemptAnswer.question_id == question_id,
+                AttemptAnswer.ai_explanation.is_(None),
+            )
+            .values(ai_explanation=text)
+        )
         await db.commit()
     return ExplainOut(text=text, source_page_no=page_no)
```

```diff
--- a/backend/app/modules/tutor/text.py
+++ b/backend/app/modules/tutor/text.py
@@ -17,13 +17,23 @@
 _SPEAKERS = {ChatRole.user: "Học viên", ChatRole.assistant: "Trợ giảng"}
 
 
+_MARKS = "*_` "
+
+
+def _bare(line: str) -> str:
+    """Bỏ khoảng trắng, dấu định dạng Markdown (**, _, `) và dấu chấm/than ở hai đầu một dòng."""
+    return line.strip().strip(_MARKS).rstrip(".!").strip(_MARKS)
+
+
 def _is_refusal(text: str) -> bool:
-    return text.strip().rstrip(".!").strip() == REFUSE_TOKEN
+    """Dòng đầu tiên chỉ có token REFUSE (có thể in đậm, có dấu chấm); phần sau dòng đó (nếu có) bị bỏ."""
+    return _bare(text.strip().split("\n", 1)[0]) == REFUSE_TOKEN
 
 
 class RefuseFilter:
-    """LLM trả đúng token REFUSE khi thiếu ngữ cảnh (spec 5.3 bước 4). Giữ lại phần đầu câu trả lời chừng nào
-    nó còn có thể là "REFUSE", để học viên không bao giờ thấy token này; câu trả lời thường được đẩy ra ngay."""
+    """LLM trả token REFUSE khi thiếu ngữ cảnh (spec 5.3 bước 4). Giữ lại dòng đầu của câu trả lời chừng nào nó còn
+    có thể là "REFUSE" (kể cả "**REFUSE**", hay "REFUSE" rồi xuống dòng viết thêm), để học viên không bao giờ thấy
+    token này; câu trả lời thường được đẩy ra ngay."""
 
     def __init__(self) -> None:
         self._buffer = ""
@@ -32,10 +42,19 @@
 
     def feed(self, piece: str) -> str:
         if self._decided:
-            return piece
+            return "" if self.refused else piece
         self._buffer += piece
         head = self._buffer.lstrip()
-        if REFUSE_TOKEN.startswith(head) or _is_refusal(head):
+        first, newline, _ = head.partition("\n")
+        if newline:  # đã có trọn dòng đầu: quyết định ngay
+            if _bare(first) == REFUSE_TOKEN:
+                self.refused = self._decided = True
+                return ""
+            return self._flush()
+        if (
+            REFUSE_TOKEN.startswith(first.lstrip(_MARKS).rstrip(_MARKS + ".!"))
+            or _bare(first) == REFUSE_TOKEN
+        ):
             return ""
         return self._flush()
 
```

```diff
--- a/backend/app/ai/retry.py
+++ b/backend/app/ai/retry.py
@@ -1,4 +1,4 @@
-"""Retry dùng chung cho các lời gọi AI (Gemini, OpenRouter): chỉ thử lại khi 429, 5xx hoặc timeout."""
+"""Retry dùng chung cho các lời gọi AI (Gemini, OpenRouter): chỉ thử lại khi 429, 5xx, timeout hoặc rớt kết nối."""
 
 import asyncio
 import logging
@@ -31,7 +31,8 @@
 
 
 def is_retryable(exc: BaseException) -> bool:
-    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
+    # TransportError gồm timeout và lỗi kết nối (ConnectError, "Server disconnected"...): đều là lỗi mạng tạm thời
+    if isinstance(exc, (httpx.TransportError, TimeoutError)):
         return True
     code = _status_code(exc)
     return code is not None and (code == 429 or 500 <= code <= 599)
```

- [x] **Bước 3: Chạy test, commit**

```powershell
cd backend
uv run pytest tests/test_studio.py tests/test_tutor_text.py tests/test_ai_retry.py tests/test_quiz_explain.py tests/test_tutor_api.py tests/test_openrouter.py -q
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
cd ..
git add backend
git commit -m "fix(ai): Sinh lại không lấy cache, trả kết nối DB trước khi gọi AI, lọc REFUSE chặt hơn, thử lại khi rớt mạng"
```

---

## Task 3: Backend: bài làm gần nhất, bài đã học, tìm kiếm, giới hạn số (lỗi 4, 6 và lỗi nhỏ)

**Files:**
- Modify: `backend/app/modules/quiz/schemas.py`, `quizzes.py`, `attempts.py`
- Modify: `backend/app/modules/courses/schemas.py`, `service.py`
- Modify: `backend/app/modules/enrollment/schemas.py`, `service.py`
- Create: `backend/tests/test_quiz_last_attempt.py`
- Modify tests: `backend/tests/test_enrollment.py`, `backend/tests/test_catalog.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`

- [x] **Bước 1: Test (sẽ fail)**

```python
"""Lượt làm gần nhất của học viên trả kèm quiz (my_last_attempt): trang bài học biết "Làm tiếp" / "Xem kết quả"
trên mọi thiết bị, không phụ thuộc localStorage của trình duyệt."""

import uuid
from datetime import timedelta

from sqlalchemy import func, update

from app.core.db import SessionLocal
from app.modules.quiz.models import QuizAttempt
from tests.helpers import API, make_published_quiz, make_student


async def _listed(client, headers, quiz):
    r = await client.get(f"{API}/quizzes", params={"lesson_id": quiz["lesson_id"]}, headers=headers)
    assert r.status_code == 200, r.text
    (item,) = r.json()["items"]
    return item


async def test_last_attempt_follows_progress_and_is_per_user(client, db):
    gv, sv, course, quiz, _ = await make_published_quiz(client, db, n_questions=2)
    assert (await _listed(client, sv, quiz))["my_last_attempt"] is None

    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    last = (await _listed(client, sv, quiz))["my_last_attempt"]
    assert (last["id"], last["status"], last["score"], last["expired"]) == (
        attempt["id"],
        "in_progress",
        None,
        False,
    )

    await client.post(f"{API}/attempts/{attempt['id']}/submit", json={}, headers=sv)
    last = (await _listed(client, sv, quiz))["my_last_attempt"]
    assert last["status"] == "completed" and last["score"] == 0.0

    one = (await client.get(f"{API}/quizzes/{quiz['id']}", headers=sv)).json()
    assert one["my_last_attempt"]["id"] == attempt["id"]

    _, other = await make_student(client, "ban-khac@x.com")
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=other)
    assert r.status_code in (200, 201), r.text
    assert (await _listed(client, other, quiz))["my_last_attempt"] is None  # của ai người nấy thấy
    assert (await _listed(client, gv, quiz))["my_last_attempt"] is None  # giảng viên không có trường này


async def test_overdue_attempt_is_marked_expired(client, db):
    _, sv, _, quiz, _ = await make_published_quiz(client, db, n_questions=1, time_limit_sec=600)
    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    async with SessionLocal() as s:
        await s.execute(
            update(QuizAttempt)
            .where(QuizAttempt.id == uuid.UUID(attempt["id"]))
            .values(deadline_at=func.clock_timestamp() - timedelta(seconds=30))
        )
        await s.commit()
    last = (await _listed(client, sv, quiz))["my_last_attempt"]
    assert (last["status"], last["expired"]) == ("in_progress", True)
    # mở kết quả thì bài được chốt timed_out
    r = await client.get(f"{API}/attempts/{attempt['id']}/result", headers=sv)
    assert r.status_code == 200, r.text
    assert (await _listed(client, sv, quiz))["my_last_attempt"]["status"] == "timed_out"
```

```diff
--- a/backend/tests/test_enrollment.py
+++ b/backend/tests/test_enrollment.py
@@ -44,3 +44,34 @@
     [item] = r.json()["items"]
     assert item["course_id"] == course["id"]
     assert (item["total_lessons"], item["done_lessons"], item["progress_pct"]) == (1, 0, 0)
+
+
+async def test_course_detail_lists_done_lessons_for_enrolled_viewer(client):
+    _, gv = await make_teacher(client)
+    _, sv = await make_student(client)
+    course, _, lesson = await make_published_course(client, gv)
+    slug = course["slug"]
+    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
+    assert (await client.get(f"{API}/courses/{slug}", headers=sv)).json()["done_lesson_ids"] == []
+
+    r = await client.put(
+        f"{API}/lessons/{lesson['id']}/progress", json={"status": "done", "video_position_sec": 0}, headers=sv
+    )
+    assert r.status_code == 200, r.text
+    assert (await client.get(f"{API}/courses/{slug}", headers=sv)).json()["done_lesson_ids"] == [lesson["id"]]
+    # người khác (chủ khóa, khách) không thấy tiến độ của học viên
+    assert (await client.get(f"{API}/courses/{slug}", headers=gv)).json()["done_lesson_ids"] == []
+    assert (await client.get(f"{API}/courses/{slug}")).json()["done_lesson_ids"] == []
+
+
+async def test_huge_video_position_is_rejected_not_500(client):
+    _, gv = await make_teacher(client)
+    _, sv = await make_student(client)
+    course, _, lesson = await make_published_course(client, gv)
+    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
+    r = await client.put(
+        f"{API}/lessons/{lesson['id']}/progress",
+        json={"status": "in_progress", "video_position_sec": 3_000_000_000},
+        headers=sv,
+    )
+    assert r.status_code == 422
```

```diff
--- a/backend/tests/test_catalog.py
+++ b/backend/tests/test_catalog.py
@@ -21,6 +21,15 @@
     assert [c["title"] for c in r.json()["items"]] == ["Cấu trúc dữ liệu"]
 
 
+async def test_catalog_search_treats_percent_and_underscore_literally(client):
+    _, gv = await make_teacher(client)
+    await make_published_course(client, gv, title="Giảm 50% học phí")
+    await make_published_course(client, gv, title="Mạng máy tính")
+    for q, expected in (("%", ["Giảm 50% học phí"]), ("_", []), ("m_ng", [])):
+        r = await client.get(f"{API}/courses", params={"q": q})
+        assert [c["title"] for c in r.json()["items"]] == expected, q
+
+
 async def test_catalog_pagination(client):
     _, gv = await make_teacher(client)
     for i in range(3):
```

- [x] **Bước 2: Quiz trả `my_last_attempt`.**
  - `LATE_GRACE` chuyển từ `attempts.py` sang `quizzes.py`, vì `attempts.py` đã import từ `quizzes.py`.
  - `expired` tính theo đồng hồ DB (`clock_timestamp()`), giống cách chốt bài.
  - Dùng `distinct_on` (SQLAlchemy 2.1) thay cho `.distinct(cột)` đã bị đánh dấu deprecated.

```diff
--- a/backend/app/modules/quiz/schemas.py
+++ b/backend/app/modules/quiz/schemas.py
@@ -107,6 +107,16 @@
     shuffle: bool | None = None
 
 
+class MyAttemptBrief(BaseModel):
+    """Lượt làm gần nhất của chính học viên: để trang bài học hiện "Làm tiếp" / "Xem kết quả" trên mọi thiết bị."""
+
+    id: uuid.UUID
+    attempt_no: int
+    status: AttemptStatus
+    score: float | None  # chỉ có khi đã nộp
+    expired: bool  # còn in_progress nhưng đã quá giờ: mở kết quả sẽ chốt timed_out
+
+
 class QuizOut(BaseModel):
     id: uuid.UUID
     lesson_id: uuid.UUID
@@ -119,6 +129,7 @@
     question_count: int
     created_at: datetime
     attempts_used: int | None = None  # chỉ trả cho học viên: số lần đã làm
+    my_last_attempt: MyAttemptBrief | None = None  # chỉ trả cho học viên
     questions: list[QuestionOut] | None = None  # chỉ giảng viên sở hữu / admin (có đáp án)
 
 
```

```diff
--- a/backend/app/modules/quiz/quizzes.py
+++ b/backend/app/modules/quiz/quizzes.py
@@ -2,8 +2,10 @@
 
 import uuid
 from collections.abc import Sequence
+from datetime import timedelta
 
 from sqlalchemy import delete, func, select
+from sqlalchemy.dialects.postgresql import distinct_on
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from app.core.errors import AppError, not_found
@@ -26,7 +28,17 @@
     QuizStatus,
 )
 from app.modules.quiz.questions import to_out
-from app.modules.quiz.schemas import PendingQuizOut, QuestionOut, QuizCreate, QuizOut, QuizPage, QuizUpdate
+from app.modules.quiz.schemas import (
+    MyAttemptBrief,
+    PendingQuizOut,
+    QuestionOut,
+    QuizCreate,
+    QuizOut,
+    QuizPage,
+    QuizUpdate,
+)
+
+LATE_GRACE = timedelta(seconds=5)  # spec 6.5: từ chối đáp án đến sau deadline_at + 5 giây
 
 
 async def get_quiz_context(db: AsyncSession, quiz_id: uuid.UUID) -> tuple[Quiz, Course]:
@@ -125,6 +137,31 @@
     return dict(rows.all())
 
 
+async def _last_attempts(
+    db: AsyncSession, user_id: uuid.UUID, quiz_ids: list[uuid.UUID]
+) -> dict[uuid.UUID, MyAttemptBrief]:
+    """Lượt làm mới nhất của học viên ở từng quiz (DISTINCT ON), kèm cờ đã quá giờ theo đồng hồ DB."""
+    if not quiz_ids:
+        return {}
+    expired = (
+        (QuizAttempt.status == AttemptStatus.in_progress)
+        & QuizAttempt.deadline_at.is_not(None)
+        & (QuizAttempt.deadline_at + LATE_GRACE < func.clock_timestamp())
+    )
+    rows = await db.execute(
+        select(QuizAttempt, expired.label("expired"))
+        .where(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id.in_(quiz_ids))
+        .ext(distinct_on(QuizAttempt.quiz_id))
+        .order_by(QuizAttempt.quiz_id, QuizAttempt.attempt_no.desc())
+    )
+    return {
+        a.quiz_id: MyAttemptBrief(
+            id=a.id, attempt_no=a.attempt_no, status=a.status, score=a.score, expired=bool(late)
+        )
+        for a, late in rows.all()
+    }
+
+
 async def quiz_questions(db: AsyncSession, quiz_id: uuid.UUID) -> list[QuestionOut]:
     rows = await db.scalars(
         select(Question)
@@ -141,6 +178,7 @@
     ids = [q.id for q in quizzes]
     counts = await _question_counts(db, ids)
     used = {} if manager else await _attempts_used(db, user.id, ids)
+    last = {} if manager else await _last_attempts(db, user.id, ids)
     result = []
     for q in quizzes:
         out = QuizOut(
@@ -155,6 +193,7 @@
             question_count=counts.get(q.id, 0),
             created_at=q.created_at,
             attempts_used=None if manager else used.get(q.id, 0),
+            my_last_attempt=None if manager else last.get(q.id),
         )
         if manager and with_questions:
             out.questions = await quiz_questions(db, q.id)
```

```diff
--- a/backend/app/modules/quiz/attempts.py
+++ b/backend/app/modules/quiz/attempts.py
@@ -36,7 +36,7 @@
     QuizQuestion,
     QuizStatus,
 )
-from app.modules.quiz.quizzes import get_quiz_context
+from app.modules.quiz.quizzes import LATE_GRACE, get_quiz_context
 from app.modules.quiz.schemas import (
     AnswerIn,
     AnswerOut,
@@ -51,7 +51,6 @@
 logger = logging.getLogger(__name__)
 
 FINISHED = (AttemptStatus.completed, AttemptStatus.timed_out)
-LATE_GRACE = timedelta(seconds=5)  # spec 6.5: từ chối đáp án đến sau deadline_at + 5 giây
 TIME_UP_MESSAGE = "Đã hết giờ làm bài. Bài đã được nộp với các đáp án đã lưu"
 
 
```

- [x] **Bước 3: Khóa học trả `done_lesson_ids`; tìm kiếm escape `%` `_`; giới hạn số.**
  - Phần mục lục của trang chi tiết khóa vẫn được cache chung cho mọi người xem.
  - `done_lesson_ids` đọc riêng theo từng người, chỉ khi người đó đã đăng ký khóa.

```diff
--- a/backend/app/modules/courses/schemas.py
+++ b/backend/app/modules/courses/schemas.py
@@ -55,7 +55,7 @@
 class LessonUpdate(BaseModel):
     title: str | None = Field(default=None, min_length=1, max_length=200)
     content_md: str | None = Field(default=None, max_length=100_000)
-    duration_sec: int | None = Field(default=None, ge=0)
+    duration_sec: int | None = Field(default=None, ge=0, le=86_400 * 7)  # cột INTEGER
     video_asset_id: uuid.UUID | None = None
 
 
@@ -119,3 +119,4 @@
     sections: list[SectionBrief]
     is_enrolled: bool
     is_owner: bool
+    done_lesson_ids: list[uuid.UUID] = []  # bài đã học xong (chỉ khi người xem đã đăng ký khóa)
```

```diff
--- a/backend/app/modules/courses/service.py
+++ b/backend/app/modules/courses/service.py
@@ -313,9 +313,12 @@
         .where(Course.status == CourseStatus.published)
     )
     if q and q.strip():
-        pattern = f"%{q.strip().lower()}%"
+        # % và _ người dùng gõ là ký tự thường, không phải ký tự đại diện của LIKE
+        term = q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
         base = base.where(
-            func.immutable_unaccent(func.lower(Course.title)).like(func.immutable_unaccent(pattern))
+            func.immutable_unaccent(func.lower(Course.title)).like(
+                func.immutable_unaccent(f"%{term}%"), escape="\\"
+            )
         )
     total, paged = await paginate(db, base.order_by(Course.created_at.desc(), Course.id.desc()), params)
     rows = (await db.execute(paged)).all()
@@ -361,7 +364,8 @@
 
 
 async def get_course_detail(db: AsyncSession, slug: str, user: User | None) -> CourseDetail:
-    from app.modules.enrollment.service import is_enrolled  # import trong hàm để tránh vòng import
+    # import trong hàm để tránh vòng import
+    from app.modules.enrollment.service import done_lesson_ids, is_enrolled
 
     async def load():
         base = await _load_detail_base(db, slug)
@@ -376,4 +380,7 @@
     if base["status"] != CourseStatus.published.value and not is_owner:
         raise not_found("Khóa học")
     enrolled = user is not None and await is_enrolled(db, user.id, course_id)
-    return CourseDetail.model_validate({**base, "is_enrolled": enrolled, "is_owner": is_owner})
+    done = await done_lesson_ids(db, user.id, course_id) if user is not None and enrolled else []
+    return CourseDetail.model_validate(
+        {**base, "is_enrolled": enrolled, "is_owner": is_owner, "done_lesson_ids": done}
+    )
```

```diff
--- a/backend/app/modules/enrollment/schemas.py
+++ b/backend/app/modules/enrollment/schemas.py
@@ -30,7 +30,7 @@
 
 class ProgressIn(BaseModel):
     status: Literal["in_progress", "done"]
-    video_position_sec: int = Field(ge=0)
+    video_position_sec: int = Field(ge=0, le=86_400 * 7)  # cột INTEGER: chặn số quá lớn (422 thay vì 500)
 
 
 class ProgressOut(BaseModel):
```

```diff
--- a/backend/app/modules/enrollment/service.py
+++ b/backend/app/modules/enrollment/service.py
@@ -49,6 +49,22 @@
     )
 
 
+async def done_lesson_ids(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> list[uuid.UUID]:
+    """Các bài của khóa mà người dùng đã học xong (mục lục ở trang học hiện dấu tích)."""
+    return list(
+        await db.scalars(
+            select(LessonProgress.lesson_id)
+            .join(Lesson, Lesson.id == LessonProgress.lesson_id)
+            .join(Section, Section.id == Lesson.section_id)
+            .where(
+                LessonProgress.user_id == user_id,
+                LessonProgress.status == ProgressStatus.done,
+                Section.course_id == course_id,
+            )
+        )
+    )
+
+
 async def my_courses(db: AsyncSession, user: User, params: PageParams) -> MyCoursePage:
     stmt = (
         select(Enrollment, Course)
```

- [x] **Bước 4: Chạy test, kiểu API, commit**

```powershell
cd backend
uv run pytest tests/test_quiz_last_attempt.py tests/test_enrollment.py tests/test_catalog.py tests/test_quiz_timing.py tests/test_pending_quizzes.py -q
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
uv run pytest -q                                          # 806 pass
cd ..\frontend; npm run gen:api                           # schema.d.ts có MyAttemptBrief, done_lesson_ids
cd ..
git add backend frontend/openapi.json frontend/src/lib/api/schema.d.ts
git commit -m "feat(api): my_last_attempt cho học viên, done_lesson_ids ở trang khóa; tìm kiếm escape % _, chặn số quá lớn"
```

---

## Task 4: Frontend: kết quả quiz theo tài khoản, dấu đã học, giảng viên chờ duyệt, chữ giao diện

**Files:**
- Delete: `frontend/src/lib/quiz/attempt-store.ts`
- Modify:
  - `frontend/src/lib/quiz/use-quiz-attempt.ts`, `use-quiz-attempt.test.tsx`
  - `frontend/src/components/quiz/quiz-player.tsx`, `quiz-player.test.tsx`
  - `frontend/src/components/lesson/lesson-quizzes.tsx`, `course-outline.tsx`
  - `frontend/src/lib/queries.ts`
  - `frontend/src/app/(auth)/login/login-form.tsx`, `frontend/src/app/(auth)/register/register-form.tsx`
  - `frontend/src/components/app/nav-items.ts`, `nav-items.test.ts`
  - `frontend/src/lib/auth/require-auth.tsx`, `require-auth.test.tsx`
  - `frontend/src/app/(main)/courses/[slug]/page.tsx`
  - `frontend/src/components/teach/quiz-manager.tsx`, `lesson-editor.tsx`, `curriculum.tsx`
- Create: `frontend/src/components/lesson/lesson-quizzes.test.tsx`, `frontend/src/components/lesson/course-outline.test.tsx`
- Modify e2e: `frontend/e2e/quiz.spec.ts`, `frontend/e2e/student.spec.ts`, `frontend/e2e/admin.spec.ts`

- [x] **Bước 1: Bỏ localStorage, dùng `my_last_attempt`.**
  - Chạy `git rm frontend/src/lib/quiz/attempt-store.ts`.
  - Mở bài làm xong thì tải lại danh sách quiz của bài, để quay về bài học thấy ngay "Làm tiếp".

```diff
--- a/frontend/src/lib/quiz/use-quiz-attempt.ts
+++ b/frontend/src/lib/quiz/use-quiz-attempt.ts
@@ -4,7 +4,6 @@
 import * as React from "react";
 import { ApiError } from "@/lib/api/errors";
 import { AnswerSaver, type SaveState } from "./answer-saver";
-import { lastAttempt } from "./attempt-store";
 import { quizKeys, saveAnswer, startAttempt, submitAttempt } from "./queries";
 import type { AttemptResult } from "./types";
 
@@ -38,9 +37,11 @@
     [a, pickedStates],
   );
 
+  // Mở bài xong thì danh sách quiz của bài phải biết đang có bài làm dở ("Làm tiếp"), trên mọi thiết bị
+  const openedId = a?.id;
   React.useEffect(() => {
-    if (a) lastAttempt.set(quizId, { attemptId: a.id, status: "in_progress" });
-  }, [a, quizId]);
+    if (openedId) void qc.invalidateQueries({ queryKey: ["lesson-quizzes"] });
+  }, [openedId, qc]);
 
   const saverFor = React.useCallback((attemptId: string) => {
     if (saverRef.current?.attemptId !== attemptId) {
@@ -79,7 +80,6 @@
       if (isAttemptClosed(e)) setClosed(true); // nơi gọi quyết định (Task 4 chuyển sang trang kết quả)
       throw e;
     }
-    lastAttempt.set(quizId, { attemptId: a.id, status: result.status, score: result.score, passed: result.passed });
     qc.setQueryData(quizKeys.result(a.id), result);
     qc.invalidateQueries({ queryKey: quizKeys.quiz(quizId) });
     qc.invalidateQueries({ queryKey: ["lesson-quizzes"] });
```

```diff
--- a/frontend/src/lib/quiz/use-quiz-attempt.test.tsx
+++ b/frontend/src/lib/quiz/use-quiz-attempt.test.tsx
@@ -4,7 +4,6 @@
 import * as React from "react";
 import { describe, expect, it } from "vitest";
 import { api, server } from "@/test/msw";
-import { lastAttempt } from "./attempt-store";
 import { useQuizAttempt } from "./use-quiz-attempt";
 
 const attempt = {
@@ -65,7 +64,6 @@
         { question_id: "q2", selected_option_id: "A" },
       ],
     });
-    expect(lastAttempt.get("qz-1")).toMatchObject({ attemptId: "at-1", status: "completed", score: 50 });
   });
 
   it("hết lượt làm bài → lỗi QUIZ_ATTEMPT_LIMIT để giao diện hiện thông báo", async () => {
```

```diff
--- a/frontend/src/components/quiz/quiz-player.tsx
+++ b/frontend/src/components/quiz/quiz-player.tsx
@@ -13,7 +13,6 @@
 import { Progress, Skeleton } from "@/components/ui/misc";
 import { ApiError, errorMessage } from "@/lib/api/errors";
 import type { SaveState } from "@/lib/quiz/answer-saver";
-import { lastAttempt } from "@/lib/quiz/attempt-store";
 import { useQuiz } from "@/lib/quiz/queries";
 import { useQuizAttempt } from "@/lib/quiz/use-quiz-attempt";
 import { cn } from "@/lib/utils";
@@ -74,15 +73,15 @@
   if (attempt.isError) {
     const err = attempt.error;
     if (err instanceof ApiError && err.code === "QUIZ_ATTEMPT_LIMIT") {
-      const last = lastAttempt.get(quizId);
+      const last = quiz.data?.my_last_attempt;
       return (
         <Shell title={quiz.data?.title} lessonHref={lessonHref}>
           <div className="mx-auto max-w-md rounded-lg border p-6 text-center">
             <p className="font-medium">Bạn đã dùng hết số lần làm quiz này.</p>
             <div className="mt-4 flex flex-col justify-center gap-2 sm:flex-row">
-              {last && last.status !== "in_progress" ? (
+              {last ? (
                 <Button asChild>
-                  <Link href={`${lessonHref}/quiz/${quizId}/result/${last.attemptId}`}>Xem kết quả gần nhất</Link>
+                  <Link href={`${lessonHref}/quiz/${quizId}/result/${last.id}`}>Xem kết quả gần nhất</Link>
                 </Button>
               ) : null}
               <Button asChild variant="outline">
```

```diff
--- a/frontend/src/components/quiz/quiz-player.test.tsx
+++ b/frontend/src/components/quiz/quiz-player.test.tsx
@@ -11,7 +11,8 @@
 
 vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));
 vi.mock("sonner", () => ({ toast: { info: (m: string) => toastInfo(m), error: (m: string) => toastError(m) } }));
-vi.mock("@/lib/quiz/queries", () => ({ useQuiz: () => ({ data: { title: "Quiz thử" } }) }));
+const quizData = vi.hoisted(() => ({ current: { title: "Quiz thử" } as Record<string, unknown> }));
+vi.mock("@/lib/quiz/queries", () => ({ useQuiz: () => ({ data: quizData.current }) }));
 vi.mock("@/lib/quiz/use-quiz-attempt", () => ({ useQuizAttempt: () => hook.current }));
 // Menu tài khoản ở thanh trên cần AuthProvider; test này chỉ kiểm phần làm bài.
 vi.mock("@/components/app/user-menu", () => ({ UserMenu: () => null }));
@@ -69,6 +70,24 @@
     setHook();
   });
 
+  it("hết lượt: mở kết quả gần nhất theo tài khoản (my_last_attempt từ server), không dựa vào máy này", () => {
+    quizData.current = {
+      title: "Quiz thử",
+      my_last_attempt: { id: "at-9", attempt_no: 1, status: "completed", score: 80, expired: false },
+    };
+    setHook({
+      attempt: { isError: true, isPending: false, error: new ApiError(409, "QUIZ_ATTEMPT_LIMIT", "Hết lượt") },
+      attemptId: null,
+    });
+    renderPlayer();
+    expect(screen.getByText("Bạn đã dùng hết số lần làm quiz này.")).toBeInTheDocument();
+    expect(screen.getByRole("link", { name: "Xem kết quả gần nhất" })).toHaveAttribute(
+      "href",
+      "/learn/toan/l1/quiz/qz1/result/at-9",
+    );
+    quizData.current = { title: "Quiz thử" };
+  });
+
   it("closed=true: chuyển sang trang kết quả đúng một lần, báo toast, không hiện 'sẽ gửi khi nộp'", async () => {
     setHook({ closed: true });
     const { rerender } = renderPlayer();
```

```diff
--- a/frontend/src/components/lesson/lesson-quizzes.tsx
+++ b/frontend/src/components/lesson/lesson-quizzes.tsx
@@ -4,12 +4,12 @@
 import Link from "next/link";
 import { Button } from "@/components/ui/button";
 import { Badge, Skeleton } from "@/components/ui/misc";
-import { lastAttempt } from "@/lib/quiz/attempt-store";
 import { useLessonQuizzes } from "@/lib/quiz/queries";
 import { formatScore } from "@/components/quiz/quiz-result";
 
 /**
- * Quiz của bài, hiện dưới nội dung bài học. Học viên chỉ thấy quiz đã xuất bản (backend lọc).
+ * Quiz của bài, hiện dưới nội dung bài học. Học viên chỉ thấy quiz đã xuất bản (backend lọc), kèm lượt làm gần
+ * nhất của chính mình (my_last_attempt) để mở lại kết quả hay làm tiếp bài dở.
  * Lỗi tải không chặn trang học: chỉ hiện một dòng nhỏ.
  */
 export function LessonQuizzes({ slug, lessonId, isStudent }: { slug: string; lessonId: string; isStudent: boolean }) {
@@ -27,10 +27,12 @@
       <ul className="mt-3 space-y-3">
         {items.map((q) => {
           const base = `/learn/${slug}/${lessonId}/quiz/${q.id}`;
-          const last = isStudent ? lastAttempt.get(q.id) : null;
+          // lượt làm gần nhất lấy từ server (theo tài khoản, đúng trên mọi thiết bị)
+          const last = isStudent ? (q.my_last_attempt ?? null) : null;
           const used = q.attempts_used ?? 0;
           const left = q.max_attempts - used;
-          const inProgress = last?.status === "in_progress";
+          // bài dở đã quá giờ: không làm tiếp được, mở kết quả thì server chốt bài
+          const inProgress = last?.status === "in_progress" && !last.expired;
           return (
             <li key={q.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-surface p-4">
               <div className="min-w-0 flex-1">
@@ -47,9 +49,11 @@
                 </Badge>
               ) : (
                 <div className="flex flex-wrap items-center gap-2">
-                  {last && last.status !== "in_progress" && last.score != null ? (
+                  {last && !inProgress ? (
                     <Button asChild variant="link">
-                      <Link href={`${base}/result/${last.attemptId}`}>Điểm gần nhất {formatScore(last.score)}</Link>
+                      <Link href={`${base}/result/${last.id}`}>
+                        {last.score != null ? `Điểm gần nhất ${formatScore(last.score)}` : "Xem kết quả"}
+                      </Link>
                     </Button>
                   ) : null}
                   {inProgress || left > 0 ? (
```

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api as url, server } from "@/test/msw";
import { LessonQuizzes } from "./lesson-quizzes";

type Last = { id: string; attempt_no: number; status: "in_progress" | "completed" | "timed_out"; score: number | null; expired: boolean };

const quiz = (id: string, used: number, last: Last | null, max_attempts = 2) => ({
  id,
  lesson_id: "l1",
  title: `Quiz ${id}`,
  max_attempts,
  pass_score: 50,
  time_limit_sec: null,
  shuffle: false,
  status: "published",
  question_count: 3,
  created_at: "2026-10-01T00:00:00Z",
  attempts_used: used,
  my_last_attempt: last,
});

function setup(items: ReturnType<typeof quiz>[]) {
  server.use(http.get(url("/quizzes"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 50 })));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <LessonQuizzes slug="khoa" lessonId="l1" isStudent />
    </QueryClientProvider>,
  );
}

const base = (id: string) => `/learn/khoa/l1/quiz/${id}`;

describe("LessonQuizzes (lượt làm gần nhất lấy từ server)", () => {
  it("chưa làm: Làm bài; đang làm dở: Làm tiếp; đã nộp: điểm gần nhất + Làm lại", async () => {
    setup([
      quiz("a", 0, null),
      quiz("b", 1, { id: "at-b", attempt_no: 1, status: "in_progress", score: null, expired: false }),
      quiz("c", 1, { id: "at-c", attempt_no: 1, status: "completed", score: 66.67, expired: false }),
    ]);
    expect(await screen.findByRole("link", { name: /Làm bài/ })).toHaveAttribute("href", base("a"));
    expect(screen.getByRole("link", { name: /Làm tiếp/ })).toHaveAttribute("href", base("b"));
    expect(screen.getByRole("link", { name: "Điểm gần nhất 66.7%" })).toHaveAttribute("href", `${base("c")}/result/at-c`);
    expect(screen.getByRole("link", { name: /Làm lại/ })).toHaveAttribute("href", base("c"));
  });

  it("bài dở đã quá giờ: không còn Làm tiếp, có Xem kết quả; hết lượt thì báo Đã hết lượt", async () => {
    setup([quiz("d", 1, { id: "at-d", attempt_no: 1, status: "in_progress", score: null, expired: true }, 1)]);
    expect(await screen.findByRole("link", { name: "Xem kết quả" })).toHaveAttribute("href", `${base("d")}/result/at-d`);
    expect(screen.queryByRole("link", { name: /Làm tiếp/ })).toBeNull();
    expect(screen.getByText("Đã hết lượt")).toBeInTheDocument();
  });
});
```

- [x] **Bước 2: Dấu đã học trong mục lục.**
  - Mục lục mặc định đọc `course.done_lesson_ids`.
  - Một bài vừa chuyển sang "đã học xong" thì tải lại khóa và danh sách Khóa của tôi.
  - Video đã xong vẫn lưu vị trí mỗi 15 giây với status `done`. Những lần lưu đó không gây tải lại.

```diff
--- a/frontend/src/components/lesson/course-outline.tsx
+++ b/frontend/src/components/lesson/course-outline.tsx
@@ -3,7 +3,8 @@
 import type { CourseDetail } from "@/lib/queries";
 import { cn } from "@/lib/utils";
 
-/** Mục lục khóa trong trang học bài; bài đang mở được đánh dấu aria-current. */
+/** Mục lục khóa trong trang học bài; bài đang mở được đánh dấu aria-current, bài đã học xong có dấu tích
+ * (mặc định lấy từ `course.done_lesson_ids`, chỉ có khi người xem đã đăng ký khóa). */
 export function CourseOutline({
   course,
   currentLessonId,
@@ -13,11 +14,12 @@
 }: {
   course: CourseDetail;
   currentLessonId: string;
-  doneIds?: Set<string>;
+  doneIds?: ReadonlySet<string>;
   onNavigate?: () => void;
   /** Link của mỗi bài; mặc định là trang học, trình soạn truyền link soạn bài. */
   hrefFor?: (lessonId: string) => string;
 }) {
+  const done = doneIds ?? new Set(course.done_lesson_ids ?? []);
   return (
     <nav aria-label="Mục lục khóa học" className="space-y-4 p-3">
       {[...course.sections]
@@ -32,7 +34,7 @@
                 .sort((a, b) => a.position - b.position)
                 .map((l) => {
                   const current = l.id === currentLessonId;
-                  const done = doneIds?.has(l.id);
+                  const isDone = done.has(l.id);
                   return (
                     <li key={l.id}>
                       <Link
@@ -44,7 +46,7 @@
                           current && "bg-muted font-medium text-primary",
                         )}
                       >
-                        {done ? (
+                        {isDone ? (
                           <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="Đã học" />
                         ) : (
                           <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
```

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CourseDetail } from "@/lib/queries";
import { CourseOutline } from "./course-outline";

const course = {
  id: "c1",
  slug: "khoa",
  title: "Khóa",
  sections: [
    {
      id: "s1",
      title: "Chương 1",
      position: 0,
      lessons: [
        { id: "l1", title: "Bài một", position: 0, duration_sec: null },
        { id: "l2", title: "Bài hai", position: 1, duration_sec: null },
      ],
    },
  ],
  done_lesson_ids: ["l1"],
} as unknown as CourseDetail;

describe("CourseOutline", () => {
  it("bài đã học xong (done_lesson_ids) có dấu tích, bài chưa học thì không", () => {
    render(<CourseOutline course={course} currentLessonId="l2" />);
    expect(screen.getByRole("link", { name: /Bài một/ })).toContainElement(screen.getByLabelText("Đã học"));
    expect(screen.getAllByLabelText("Đã học")).toHaveLength(1);
    expect(screen.getByRole("link", { name: /Bài hai/ })).toHaveAttribute("aria-current", "page");
  });
});
```

```diff
--- a/frontend/src/lib/queries.ts
+++ b/frontend/src/lib/queries.ts
@@ -103,8 +103,13 @@
     mutationFn: (body: components["schemas"]["ProgressIn"]) =>
       unwrap(api.PUT("/api/v1/lessons/{lesson_id}/progress", { params: { path: { lesson_id: lessonId } }, body })),
     onSuccess: (progress) => {
+      // video đã xong vẫn lưu vị trí mỗi 15 giây (status "done"): chỉ tải lại khi bài vừa chuyển sang xong
+      const wasDone = qc.getQueryData<LessonDetail>(qk.lesson(lessonId))?.progress?.status === "done";
       qc.setQueryData<LessonDetail>(qk.lesson(lessonId), (old) => (old ? { ...old, progress } : old));
-      if (progress.status === "done") qc.invalidateQueries({ queryKey: ["my-courses"] });
+      if (progress.status === "done" && !wasDone) {
+        qc.invalidateQueries({ queryKey: ["my-courses"] });
+        qc.invalidateQueries({ queryKey: ["course"] }); // mục lục hiện dấu tích bài vừa học xong (done_lesson_ids)
+      }
     },
   });
 }
```

- [x] **Bước 3: Giảng viên chưa được duyệt**

```diff
--- a/frontend/src/app/(auth)/login/login-form.tsx
+++ b/frontend/src/app/(auth)/login/login-form.tsx
@@ -32,7 +32,9 @@
     setUnverified(null);
     try {
       const user = await login(values.email, values.password);
-      const fallback = user.role === "student" ? "/" : user.role === "admin" ? "/admin" : "/teach";
+      // Giảng viên chưa được duyệt về trang chủ: ở đó có trạng thái duyệt và nút gửi lại yêu cầu
+      const fallback =
+        user.role === "admin" ? "/admin" : user.role === "teacher" && user.teacher_status === "approved" ? "/teach" : "/";
       router.replace(safeNext(params.get("next"), fallback));
     } catch (err) {
       if (err instanceof ApiError && err.code === "EMAIL_NOT_VERIFIED") {
```

```diff
--- a/frontend/src/components/app/nav-items.ts
+++ b/frontend/src/components/app/nav-items.ts
@@ -20,7 +20,7 @@
   // Chỉ giảng viên đã duyệt: GET /teacher/courses dùng require_teacher_approved (admin nhận 403).
   if (user.role === "teacher" && user.teacher_status === "approved")
     return [{ href: "/teach", label: "Khóa đang dạy", icon: GraduationCap }, ...base.slice(1)];
-  return base.slice(1); // giảng viên chờ duyệt / bị từ chối
+  return base; // giảng viên chờ duyệt / bị từ chối: trang chủ có trạng thái duyệt và nút gửi lại yêu cầu
 }
 
 /** Mục chỉ sáng khi khớp đúng đường dẫn (không khớp tiền tố): "/" và "/admin" là cha của các mục khác. */
```

```diff
--- a/frontend/src/components/app/nav-items.test.ts
+++ b/frontend/src/components/app/nav-items.test.ts
@@ -14,7 +14,7 @@
   });
   it("giảng viên đã duyệt có Khóa đang dạy; chờ duyệt thì không", () => {
     expect(navItems(user("teacher", "approved")).map((i) => i.href)).toEqual(["/teach", "/explore"]);
-    expect(navItems(user("teacher", "pending")).map((i) => i.href)).toEqual(["/explore"]);
+    expect(navItems(user("teacher", "pending")).map((i) => i.href)).toEqual(["/", "/explore"]);
   });
   it("tối đa 3 mục (tài khoản nằm ở menu góc trên, không chiếm chỗ thanh dưới)", () => {
     for (const r of ["student", "teacher", "admin"] as const) expect(navItems(user(r, "approved")).length).toBeLessThanOrEqual(3);
```

```diff
--- a/frontend/src/lib/auth/require-auth.tsx
+++ b/frontend/src/lib/auth/require-auth.tsx
@@ -1,7 +1,9 @@
 "use client";
 
+import Link from "next/link";
 import { usePathname, useRouter } from "next/navigation";
 import * as React from "react";
+import { Button } from "@/components/ui/button";
 import { Skeleton } from "@/components/ui/misc";
 import { isStaff, useAuth } from "./auth-context";
 
@@ -38,10 +40,15 @@
         <p className="mt-2 text-muted-foreground">
           {user?.role === "teacher"
             ? user.teacher_status === "rejected"
-              ? "Yêu cầu giảng dạy của bạn đã bị từ chối. Vui lòng liên hệ quản trị viên."
+              ? "Yêu cầu giảng dạy của bạn chưa được chấp nhận. Xem lý do và gửi lại yêu cầu ở trang chủ."
               : "Tài khoản giảng viên của bạn đang chờ quản trị viên duyệt."
             : "Trang này chỉ dành cho giảng viên."}
         </p>
+        {user?.role === "teacher" ? (
+          <Button asChild variant="outline" className="mt-4">
+            <Link href="/">Về trang chủ</Link>
+          </Button>
+        ) : null}
       </div>
     );
   }
```

```diff
--- a/frontend/src/lib/auth/require-auth.test.tsx
+++ b/frontend/src/lib/auth/require-auth.test.tsx
@@ -29,8 +29,10 @@
     auth.status = "authenticated";
     auth.user = { role: "teacher", teacher_status: "rejected" };
     render(<RequireAuth staff>soạn khóa</RequireAuth>);
-    expect(screen.getByText(/đã bị từ chối/)).toBeInTheDocument();
+    expect(screen.getByText(/chưa được chấp nhận/)).toBeInTheDocument();
     expect(screen.queryByText(/đang chờ quản trị viên duyệt/)).not.toBeInTheDocument();
+    // nút gửi lại yêu cầu nằm ở trang chủ
+    expect(screen.getByRole("link", { name: "Về trang chủ" })).toHaveAttribute("href", "/");
   });
 
   it("trang quản trị: giảng viên đã duyệt cũng bị chặn, admin thì vào được", () => {
```

- [x] **Bước 4: Chữ giao diện, mục lục trên điện thoại, focus ở trang đăng ký**

```diff
--- a/frontend/src/components/teach/quiz-manager.tsx
+++ b/frontend/src/components/teach/quiz-manager.tsx
@@ -105,7 +105,7 @@
         open={!!publishing}
         onOpenChange={(o) => !o && setPublishing(null)}
         title={`Xuất bản “${publishing?.title}”?`}
-        description="Học viên đã đăng ký sẽ thấy và làm được quiz này. Sau khi xuất bản chỉ đổi được tiêu đề, không thêm bớt câu hỏi."
+        description="Học viên đã đăng ký sẽ thấy, làm được quiz này và nhận thông báo. Sau khi xuất bản không thêm bớt câu hỏi hay đổi cài đặt được nữa."
         confirmLabel="Xuất bản"
         pendingLabel="Đang xuất bản…"
         onConfirm={async () => {
```

```diff
--- a/frontend/src/components/teach/lesson-editor.tsx
+++ b/frontend/src/components/teach/lesson-editor.tsx
@@ -177,7 +177,7 @@
         onOpenChange={setDeleteOpen}
         destructive
         title={`Xóa bài “${lesson.title}”?`}
-        description="Nội dung, video, tài liệu PDF và tiến độ học của bài sẽ bị xóa và không khôi phục được."
+        description="Nội dung, video, tài liệu PDF và quiz của bài sẽ bị xóa, không khôi phục được. Bài đã có học viên học, làm quiz hoặc hỏi AI thì không xóa được."
         confirmLabel="Xóa bài"
         pendingLabel="Đang xóa…"
         onConfirm={async () => {
```

```diff
--- a/frontend/src/components/teach/curriculum.tsx
+++ b/frontend/src/components/teach/curriculum.tsx
@@ -83,8 +83,8 @@
         title={pendingDelete?.kind === "section" ? `Xóa chương “${pendingDelete.title}”?` : `Xóa bài “${pendingDelete?.title}”?`}
         description={
           pendingDelete?.kind === "section"
-            ? `Chương này có ${pendingDelete.lessons} bài. Toàn bộ bài, tài liệu và tiến độ học của các bài đó sẽ bị xóa và không khôi phục được.`
-            : "Nội dung, video, tài liệu PDF và tiến độ học của bài sẽ bị xóa và không khôi phục được."
+            ? `Chương này có ${pendingDelete.lessons} bài. Toàn bộ bài, tài liệu và quiz của các bài đó sẽ bị xóa, không khôi phục được. Chương đã có học viên học, làm quiz hoặc hỏi AI thì không xóa được.`
+            : "Nội dung, video, tài liệu PDF và quiz của bài sẽ bị xóa, không khôi phục được. Bài đã có học viên học, làm quiz hoặc hỏi AI thì không xóa được."
         }
         confirmLabel={pendingDelete?.kind === "section" ? "Xóa chương" : "Xóa bài"}
         pendingLabel="Đang xóa…"
```

```diff
--- a/frontend/src/app/(main)/courses/[slug]/page.tsx
+++ b/frontend/src/app/(main)/courses/[slug]/page.tsx
@@ -94,6 +94,8 @@
 
       {/* Hộp hành động: dính bên phải trên desktop, dính đáy trên điện thoại */}
       <aside className="lg:sticky lg:top-20 lg:self-start">
+        {/* chừa chỗ cho hộp dính đáy trên điện thoại để bài cuối của mục lục không bị che */}
+        <div aria-hidden className="h-20 md:hidden" />
         <div className="fixed inset-x-0 bottom-16 z-20 border-t bg-surface p-3 md:static md:rounded-lg md:border md:p-5">
           {c.is_owner ? (
             <Button asChild size="lg" className="w-full">
```

```diff
--- a/frontend/src/app/(auth)/register/register-form.tsx
+++ b/frontend/src/app/(auth)/register/register-form.tsx
@@ -57,7 +57,8 @@
               <label
                 key={r}
                 className={cn(
-                  "flex h-11 cursor-pointer items-center justify-center rounded-md border text-sm",
+                  // radio ẩn (sr-only): viền focus hiện trên nhãn để người dùng bàn phím thấy đang ở ô nào
+                  "flex h-11 cursor-pointer items-center justify-center rounded-md border text-sm has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                   role === r && "border-primary bg-primary/10 font-medium text-primary",
                 )}
               >
```

- [x] **Bước 5: E2E.**
  - `quiz.spec.ts`: API giả trả `my_last_attempt` thay đổi theo bài làm.
  - `student.spec.ts`: đánh dấu xong thì mục lục có dấu tích (chỉ kiểm ở desktop, vì trên điện thoại mục lục nằm trong khung trượt).
  - `admin.spec.ts`: giảng viên bị từ chối đăng nhập thì về trang chủ.

```diff
--- a/frontend/e2e/quiz.spec.ts
+++ b/frontend/e2e/quiz.spec.ts
@@ -8,11 +8,17 @@
     const saved: Record<string, string> = {};
     let submitted: { final_answers: { question_id: string; selected_option_id: string }[] } | null = null;
     let used = 0;
+    // lượt làm gần nhất do server trả kèm quiz (theo tài khoản, không lưu trên máy)
+    let last: Record<string, unknown> | null = null;
     await mockApi(page, {
       extra: {
-        "GET /quizzes": (r) => r.fulfill({ json: { items: [quiz({ attempts_used: used })], total: 1, page: 1, size: 50 } }),
-        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz({ attempts_used: used }) }),
-        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) => r.fulfill({ status: 201, json: attempt() }),
+        "GET /quizzes": (r) =>
+          r.fulfill({ json: { items: [quiz({ attempts_used: used, my_last_attempt: last })], total: 1, page: 1, size: 50 } }),
+        [`GET /quizzes/${QUIZ_ID}`]: (r) => r.fulfill({ json: quiz({ attempts_used: used, my_last_attempt: last }) }),
+        [`POST /quizzes/${QUIZ_ID}/attempts`]: (r) => {
+          last = { id: ATTEMPT_ID, attempt_no: 1, status: "in_progress", score: null, expired: false };
+          return r.fulfill({ status: 201, json: attempt() });
+        },
         [`PUT /attempts/${ATTEMPT_ID}/answers/*`]: async (r, url) => {
           const qid = url.pathname.split("/").pop()!;
           saved[qid] = r.request().postDataJSON().selected_option_id;
@@ -22,7 +28,9 @@
           submitted = r.request().postDataJSON();
           used = 1;
           const answers = Object.fromEntries(submitted!.final_answers.map((a) => [a.question_id, a.selected_option_id]));
-          return r.fulfill({ json: result(answers) });
+          const graded = result(answers);
+          last = { id: ATTEMPT_ID, attempt_no: 1, status: graded.status, score: graded.score, expired: false };
+          return r.fulfill({ json: graded });
         },
         [`POST /attempts/${ATTEMPT_ID}/answers/*/explain`]: (r) =>
           r.fulfill({ json: { text: "Bạn chọn x, nhưng theo quy tắc lũy thừa đạo hàm của x² là 2x [1].", source_page_no: 4 } }),
```

```diff
--- a/frontend/e2e/student.spec.ts
+++ b/frontend/e2e/student.spec.ts
@@ -1,6 +1,6 @@
 import { expect, test } from "@playwright/test";
 import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
-import { L1, L2, mockApi } from "./mock-api";
+import { courseDetail, L1, L2, mockApi } from "./mock-api";
 
 test.describe("học viên", () => {
   test("khách xem catalog → chi tiết → bấm Đăng ký thì được chuyển tới đăng nhập", async ({ page }) => {
@@ -41,7 +41,17 @@
   });
 
   test("học bài: đọc, hỏi AI có trích nguồn, đánh dấu xong, sang bài tiếp", async ({ page, isMobile }) => {
-    await mockApi(page);
+    const done: string[] = [];
+    await mockApi(page, {
+      extra: {
+        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: courseDetail({ is_enrolled: true, done_lesson_ids: done }) }),
+        "PUT /lessons/*/progress": (r, url) => {
+          const status = r.request().postDataJSON().status;
+          if (status === "done") done.push(url.pathname.split("/").at(-2)!); // /api/v1/lessons/<id>/progress
+          return r.fulfill({ json: { status, video_position_sec: 0, completed_at: "2026-10-01T00:00:00Z" } });
+        },
+      },
+    });
     await page.goto(`/learn/giai-tich-1/${L1}`);
     await expect(page.getByRole("heading", { name: "Định nghĩa đạo hàm", level: 1 })).toBeVisible();
     await expect(page.locator(".katex").first()).toBeVisible();
@@ -62,6 +72,11 @@
 
     await page.getByRole("button", { name: "Đánh dấu đã học xong" }).click();
     await expect(page.getByText("Đã học xong bài này")).toBeVisible();
+    if (!isMobile) {
+      // mục lục bên trái có dấu tích ở bài vừa học xong (done_lesson_ids của khóa)
+      const outline = page.getByRole("navigation", { name: "Mục lục khóa học" });
+      await expect(outline.getByRole("link", { name: /Định nghĩa đạo hàm/ }).getByLabel("Đã học")).toBeVisible();
+    }
     await page.getByRole("button", { name: /Bài tiếp: Quy tắc tính đạo hàm/ }).click();
     await expect(page).toHaveURL(new RegExp(L2));
   });
```

```diff
--- a/frontend/e2e/admin.spec.ts
+++ b/frontend/e2e/admin.spec.ts
@@ -148,6 +148,17 @@
     await expectAccessible(page);
   });
 
+  test("giảng viên bị từ chối đăng nhập thì về trang chủ, nơi có nút gửi lại yêu cầu", async ({ page }) => {
+    const rejected = { ...teacher, teacher_status: "rejected", review_note: "Chưa có minh chứng chuyên môn" };
+    await mockApi(page, { user: rejected });
+    await page.goto("/login");
+    await page.getByLabel("Email").fill(rejected.email);
+    await page.getByLabel("Mật khẩu").fill("password123");
+    await page.getByRole("button", { name: "Đăng nhập" }).click();
+    await expect(page).toHaveURL(/\/$/);
+    await expect(page.getByRole("button", { name: "Gửi lại yêu cầu duyệt" })).toBeVisible();
+  });
+
   test("khóa bị ẩn: trình soạn hiện lý do và không còn nút Xuất bản", async ({ page }) => {
     const hiddenCourse = courseDetail({ status: "archived", is_owner: true, hidden_reason: "Sao chép giáo trình" });
     await mockApi(page, { user: teacher, extra: { "GET /courses/giai-tich-1": (r) => r.fulfill({ json: hiddenCourse }) } });
```

- [x] **Bước 6: Kiểm tra + commit**

```powershell
cd frontend
npx tsc --noEmit ; npx eslint .
npx vitest run                     # 184 pass
npx playwright test                # 103 pass + 1 bỏ qua có chủ ý
cd ..
git add -A frontend
git commit -m "fix(web): kết quả quiz theo tài khoản, dấu đã học ở mục lục, giảng viên chờ duyệt về trang chủ, sửa chữ giao diện"
```

---

## Task 5: Cập nhật tiến độ trong spec và bản đồ module

**Files:** Modify `docs/specs/2026-09-29-lms-ai-design.md`, `docs/architecture/modules.md`

- [x] **Bước 1:**
  - Dòng trạng thái và dòng tổng tiến độ: **22/41 xong, 8 đang làm, 1 đã cắt**.
  - D1 và D3 thành `[x]` (đã làm xong từ trước nhưng chưa tick). D4 thành `[~]`. Sửa ghi chú S5.
  - Thêm dòng quyết định 2026-10-28.
  - `modules.md` thêm `inbox`, `discussion`, phần B7 của `analytics`, và OpenRouter.

```diff
--- a/docs/specs/2026-09-29-lms-ai-design.md
+++ b/docs/specs/2026-09-29-lms-ai-design.md
@@ -4,7 +4,7 @@
 - **Ngày tạo:** 2026-09-29
 - **Loại:** Đồ án tốt nghiệp: full stack, web động, tích hợp AI
 - **Nguồn lực:** 1 người làm full-time trong 5 tuần, có Claude hỗ trợ viết code
-- **Trạng thái spec:** Đã duyệt thiết kế (5/5 phần), đang triển khai (xong backend tuần 1 và tuần 2)
+- **Trạng thái spec:** Đã duyệt thiết kế (5/5 phần), đang triển khai (xong tầng A; tầng B trừ B5; tầng S xong phần code, chưa deploy và đo thật)
 
 ---
 
@@ -12,7 +12,7 @@
 
 > Cập nhật mục này mỗi khi xong việc. Ký hiệu: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[-]` đã cắt.
 
-**Tuần hiện tại:** 2 / 5  **Tổng tiến độ:** 9 / 40 hạng mục
+**Cập nhật:** 2026-10-28 (tuần 5)  **Tổng tiến độ:** 22 / 41 hạng mục xong, 8 đang làm, 1 đã cắt
 
 **Thứ tự ưu tiên:** A (lõi) → B (mức Khá) → S (chất lượng hệ thống) → C (điểm nhấn). Hết thời gian mà vẫn còn việc thì phần bị trễ là tầng C, không phải S. Tuần 5 vẫn giữ cho báo cáo và bộ đánh giá.
 
@@ -49,7 +49,7 @@
   - `/health` (tiến trình còn sống) và `/ready` (DB, Redis, MinIO đều kết nối được).
   - Thu metrics Prometheus (`prometheus-fastapi-instrumentator`, cộng metric riêng cho số job trong hàng đợi và số job lỗi).
   - Dashboard Grafana gồm: số request/giây, độ trễ p50/p95, tỉ lệ lỗi 5xx, job đang chờ và job lỗi, thời gian tới token đầu tiên (TTFT) của AI Tutor.
-- [~] **S5. Hiệu năng:** (đã có cache có phiên bản, `perf_seed` và kịch bản k6 catalog + học viên; chưa đo, chưa có kịch bản làm quiz)
+- [~] **S5. Hiệu năng:** (đã có cache có phiên bản, `perf_seed` và kịch bản k6 cho catalog và trang chi tiết khóa; chưa có kịch bản đọc bài và làm quiz, chưa đo)
   - Viết kịch bản load test k6 cho catalog, trang chi tiết khóa học, đọc bài học và làm quiz.
   - Báo cáo p95 và throughput ở mức 50 người dùng ảo.
   - Cache catalog và trang chi tiết khóa học bằng Redis (TTL 60 giây, xóa cache khi publish hoặc sửa khóa). So sánh số liệu trước và sau khi cache.
@@ -70,10 +70,10 @@
 
 ### Phục vụ bảo vệ
 
-- [~] D1. Nút 👍/👎 cho câu trả lời của AI Tutor
+- [x] D1. Nút 👍/👎 cho câu trả lời của AI Tutor (admin xem tên học viên, giảng viên xem ẩn danh ở trang thống kê)
 - [ ] D2. Deploy VPS có domain và HTTPS
-- [ ] D3. Test tự động (unit, integration, API, phân quyền, đồng thời, 3–4 luồng E2E)
-- [ ] D4. Bộ đánh giá RAG khoảng 80 câu hỏi + script `eval/`
+- [x] D3. Test tự động (unit, integration, API, phân quyền, đồng thời, 3–4 luồng E2E): pytest (backend, DB thật), Vitest (giao diện), Playwright (E2E với API giả lập, khung điện thoại và máy tính, có kiểm axe); CI chạy cả ba
+- [~] D4. Bộ đánh giá RAG khoảng 80 câu hỏi + script `eval/` (đã có script trong `backend/eval/`, bộ dữ liệu mới có 5 câu mẫu)
 - [ ] D5. Đánh giá sinh quiz, chấm bài, Whisper
 - [ ] D6. Đợt dùng thử (5–10 người, 3–4 ngày) + khảo sát SUS
 - [ ] D7. Video demo dự phòng + cache câu trả lời cho các câu demo
@@ -774,3 +774,4 @@
 | 2026-10-15 | Hồ sơ cá nhân: `PATCH /me` (họ tên, gọn khoảng trắng, 1–120 ký tự), `POST /me/password` (đúng mật khẩu hiện tại, khác mật khẩu cũ, 10 lần thử/giờ/tài khoản; thu hồi mọi phiên rồi cấp phiên mới cho trình duyệt đang dùng). Menu tài khoản (Hồ sơ cá nhân, Ghi chú, chế độ màu, Đăng xuất) ở thanh trên của mọi trang kể cả trang học và quiz; đăng xuất tải lại trang chủ. Giao diện: bảng màu sáng trung tính, bo góc 4px, `--mark` cho trích dẫn; trang chủ cho khách mới (không nằm trong khung app) có phần thử hỏi với 4 câu mẫu cố định |
 | 2026-10-15 | Giao diện sau đăng nhập cùng giọng với trang chủ cho khách: thanh bên một tông màu, ô tên app nền đậm, tiêu đề trang 800; trang chủ học viên có lời chào lớn, khối đang học (tên bài lấy từ API, phần đã đọc lưu trên máy), ba con số, "Việc nên làm tiếp" từ `GET /me/pending-quizzes` (quiz đã xuất bản trong khóa đã đăng ký, chưa nộp lần nào, bài làm dở trước, tối đa 6), danh sách khóa dạng hàng; Khám phá có khóa mới nhất trong khối màu và mục lục khóa; Khóa của tôi chia Đang học / Đã xong |
 | 2026-10-19 | B4 thảo luận: bảng `lesson_comments` (gốc + trả lời một cấp, xóa mềm), ai vào được bài thì đọc và viết được; tác giả, giảng viên của khóa hoặc admin được xóa, người khác nhận 404; 30 bình luận/giờ/người. B6 thông báo: bảng `notifications` (trả lời bình luận, câu hỏi mới cho giảng viên, quiz mới xuất bản cho học viên đã đăng ký, tài liệu/câu hỏi AI xong hoặc lỗi cho người tạo job); ghi cùng transaction với sự kiện, sau commit mới phát tín hiệu Redis `notif:{user_id}`; SSE `/me/notifications/stream` không giữ kết nối DB, gửi số chưa đọc khi có tín hiệu, ping 25 giây, Redis lỗi thì tự đọc lại DB theo chu kỳ. B7 `GET /courses/{id}/insights` (xem mục Dashboard) |
+| 2026-10-28 | Sửa lỗi sau rà soát: refresh token có `rotated_at`, chỉ token bị xoay mới coi là bị đánh cắp khi dùng lại (đổi mật khẩu ở máy này không còn làm máy này bị đăng xuất khi máy khác gửi token cũ); `GET /quizzes` trả `my_last_attempt` cho học viên (bỏ lưu bài làm gần nhất ở localStorage); `GET /courses/{slug}` trả `done_lesson_ids` khi người xem đã đăng ký (mục lục hiện dấu đã học); "Sinh lại" trong AI Studio không lấy cache; AI giải thích câu sai và gợi ý hỏi tiếp trả kết nối DB trước khi gọi AI; lọc REFUSE nhận cả dạng in đậm / có dòng sau; thử lại khi rớt kết nối mạng; giảng viên chưa được duyệt đăng nhập thì về trang chủ |
```

```diff
--- a/docs/architecture/modules.md
+++ b/docs/architecture/modules.md
@@ -14,6 +14,7 @@
 | `materials` | Upload (staging → kiểm tra → key chính thức), tài liệu PDF, đoạn (chunk) | `assets`, `sources`, `source_pages`, `chunks` | `test_uploads.py`, `test_sources_api.py`, `test_chunks_db.py`, `test_pipeline.py` |
 | `jobs` | Tạo job nền chống trùng, đưa vào hàng đợi sau commit | `jobs` | `test_jobs.py`, `test_worker.py` |
 | `notify` | Hộp thư đi email (outbox), gửi SMTP | `email_outbox` | `test_email.py`, `test_mailer.py` |
+| `inbox` | Thông báo trong app (B6): ghi cùng transaction với sự kiện, báo hiệu qua Redis, luồng SSE số chưa đọc | `notifications` | `test_notifications.py` |
 
 ### Phần tính năng
 
@@ -22,7 +23,8 @@
 | `tutor` | AI Tutor: RAG, SSE, phản hồi 👍👎 | `chat_sessions`, `chat_messages` | `test_tutor_*.py` (`models`, `api`, `sessions`, `answer`, `text`) |
 | `quiz` | Sinh câu hỏi bằng AI, duyệt, quiz, làm bài, chấm | `questions`, `quizzes`, `quiz_questions`, `quiz_attempts`, `attempt_answers` | `test_quiz_*.py`, `test_questions_api.py`, `test_quizzes_api.py`, `test_attempts_api.py`, `test_submit_api.py` |
 | `studio` | AI Studio: hướng dẫn tài liệu, báo cáo, flashcard, ghi chú | `source_guides`, `study_artifacts`, `flashcard_reviews`, `notes` | `test_studio.py`, `test_notes.py` |
-| `analytics` | Thống kê khóa cho giảng viên | (chỉ đọc) | `test_analytics.py` |
+| `analytics` | Thống kê khóa cho giảng viên, phân tích lớp (B7: câu hay sai, bài yếu, học viên cần để ý) | (chỉ đọc) | `test_analytics.py`, `test_insights.py` |
+| `discussion` | Thảo luận theo bài (B4): câu hỏi và trả lời một cấp, xóa mềm | `lesson_comments` | `test_discussion.py` |
 | `admin` | Duyệt giảng viên, khóa tài khoản, ẩn khóa, nhật ký, CSV, token AI | `admin_actions` | `test_admin.py` |
 
 ### Lớp dùng chung
@@ -30,7 +32,7 @@
 | Thư mục | Làm gì |
 |---|---|
 | `core/` | Cấu hình, DB, lỗi, middleware, phân quyền, rate limit, storage, cache, metrics, `/ready` |
-| `ai/` | Provider AI (giả / Gemini; sau này OpenRouter), `LLMClient` (thử lại, cache `llm_cache`, ghi `ai_calls`), prompt, retrieval |
+| `ai/` | Provider AI (giả / Gemini / OpenRouter), `LLMClient` (thử lại, cache `llm_cache`, ghi `ai_calls`), prompt, retrieval |
 | `ingestion/` | PDF → trang → đoạn → embedding |
 | `worker/` | Khai báo job nền cho arq (gọi vào service của module) |
 | `backend/eval/` | Benchmark AI (không chạy trong server) |
@@ -40,10 +42,10 @@
 ```mermaid
 flowchart TB
     subgraph F[Phần tính năng]
-        TUT[tutor] ~~~ QZ[quiz] ~~~ STU[studio] ~~~ ANA[analytics] ~~~ ADM[admin]
+        TUT[tutor] ~~~ QZ[quiz] ~~~ STU[studio] ~~~ ANA[analytics] ~~~ ADM[admin] ~~~ DIS[discussion]
     end
     subgraph B[Phần nền]
-        AUTH[auth] ~~~ CRS[courses] ~~~ ENR[enrollment] ~~~ MAT[materials] ~~~ JOB[jobs] ~~~ NTF[notify]
+        AUTH[auth] ~~~ CRS[courses] ~~~ ENR[enrollment] ~~~ MAT[materials] ~~~ JOB[jobs] ~~~ NTF[notify] ~~~ INB[inbox]
     end
     subgraph L[Lớp dùng chung]
         CORE[core] ~~~ AI[ai] ~~~ ING[ingestion]
@@ -54,6 +56,7 @@
 - Phần tính năng được dùng phần nền; **phần nền không được import phần tính năng**.
 - `tutor` và `quiz` không phụ thuộc nhau.
 - `notify` không phụ thuộc module nào: ai cần gửi mail thì gọi `queue_email`.
+- `inbox` chỉ dựa vào `core` và `auth`: module nào cần báo cho người dùng thì gọi `inbox.service.add` trước commit, `publish` sau commit.
 - `core`, `ai`, `ingestion` không import phần tính năng, `main` hay `worker`.
 - Ngoại lệ duy nhất (ghi rõ trong `.importlinter`): `courses.service` **đọc** bảng của quiz và tutor để chặn xóa khóa đã có học viên làm bài / hỏi AI.
 
```

- [x] **Bước 2: Commit**

```powershell
git add docs
git commit -m "docs: cập nhật tiến độ thật (22/41), D1 D3 xong, bản đồ module thêm inbox và discussion"
```

---

## Task 6: Kiểm tay (bạn làm)

Sau khi pull: `docker compose --profile web up -d --build`. API tự chạy migration.

- [ ] **Đổi mật khẩu ở 2 nơi:**
  - Đăng nhập cùng một tài khoản ở trình duyệt thường và cửa sổ ẩn danh.
  - Ở trình duyệt thường: Hồ sơ cá nhân → đổi mật khẩu.
  - Ở cửa sổ ẩn danh: tải lại trang, phải bị đăng xuất.
  - Quay lại trình duyệt thường: dùng tiếp vài phút, chuyển trang, **không** bị đăng xuất.
- [ ] **Kết quả quiz theo tài khoản:**
  - Học viên A làm xong một quiz rồi đăng xuất. Học viên B đăng nhập trên cùng trình duyệt: không thấy "Điểm gần nhất" của A.
  - A đăng nhập trên máy hoặc trình duyệt khác: thấy "Điểm gần nhất …" và mở được kết quả.
  - Quiz có giờ: bắt đầu làm, đóng tab, chờ quá giờ rồi mở lại bài học. Thấy "Xem kết quả", không còn "Làm tiếp".
- [ ] **Dấu đã học:** bấm "Đánh dấu đã học xong" thì mục lục bên trái có dấu tích. Tải lại trang vẫn còn.
- [ ] **AI Studio:** giảng viên bấm "Sinh lại" một tài liệu đã có. Nội dung mới khác bản cũ (cần AI thật, ví dụ Gemini miễn phí).
- [ ] **Giảng viên bị từ chối:**
  - Admin từ chối một giảng viên.
  - Giảng viên đó đăng nhập thì về trang chủ, thấy lý do và nút "Gửi lại yêu cầu duyệt".
- [ ] **Điện thoại (375px):** trang chi tiết khóa cuộn xuống cuối, bài cuối của mục lục không bị hộp "Đăng ký khóa học" che.
