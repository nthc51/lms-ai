# Giao diện sau đăng nhập: khung app, trang chủ học viên, Khám phá, Khóa của tôi: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** sau hai plan ngày 2026-10-15, trang chủ cho khách đã có giao diện mới. Đăng nhập vào thì các trang vẫn là thẻ viền mỏng và tiêu đề nhỏ, trông khô và không cùng bộ với trang chủ khách. Bạn đã duyệt bản demo `lms-ai-sau-dang-nhap-demo.html`; plan này đưa bản đó vào Next.js với dữ liệu thật.

**Mục tiêu:**

1. **Khung app:**
   - Ô "LMS-AI" nền đậm ở đầu thanh bên.
   - Thanh bên dùng một tông màu riêng, không viền.
   - Mục đang chọn: nền thẻ cộng vạch màu chính bên trái.
   - Thanh trên không viền, không làm mờ nền.
   - Thanh dưới điện thoại cùng tông với thanh bên.
2. **Tiêu đề trang (`PageHeader`)** lớn và đậm hơn (32–48px, độ đậm 800). Áp cho mọi trang có tiêu đề, kể cả trang giảng viên và quản trị.
3. **Trang chủ học viên:**
   - **Lời chào lớn** "Chào An.", câu tóm tắt và ngày hôm nay.
   - **Khối "đang học"** màu xanh lá:
     - Tên khóa.
     - Tên bài đang học, tô vàng. Tên lấy qua `GET /lessons/{id}`, vì máy chỉ lưu mã bài.
     - "Đã đọc khoảng N%", lấy từ vị trí đọc lưu trên máy.
     - Thanh tiến độ và nút lớn "Học tiếp".
   - **Ba con số:** khóa đang học, bài đã xong, khóa đã hoàn thành.
   - **"Việc nên làm tiếp"** liệt kê quiz chưa làm, lấy từ API mới. Không có quiz nào thì ẩn cả mục.
   - **"Khóa của tôi"** dạng hàng có thanh tiến độ.
4. **API mới `GET /api/v1/me/pending-quizzes`:**
   - Lấy quiz đã xuất bản trong các khóa đã xuất bản mà người dùng đã đăng ký, chưa nộp lần nào. Bài đang làm dở vẫn tính.
   - Bài làm dở xếp trước, rồi tới quiz mới nhất. Trả tối đa 6 quiz.
   - Nộp bài xong thì trang chủ tự tải lại danh sách.
5. **Khám phá:**
   - Tiêu đề lớn, ô tìm kiếm cao 56px.
   - Khóa mới nhất (đầu danh sách, catalog đã xếp mới trước) nằm trong khối màu lớn, kèm 3 bài đầu và thời lượng.
   - Các khóa còn lại dạng mục lục: tên to bên trái, mô tả bên phải.
   - Khóa học viên đã đăng ký có nhãn "Bạn đang học".
6. **Khóa của tôi:**
   - Hai nút "Đang học · N" / "Đã xong · N".
   - Mỗi khóa là một khối màu to nhỏ xen kẽ, có tiến độ, kèm "Học tiếp", "Bắt đầu học" hoặc "Xem lại khóa".
7. **Thanh tiến độ** dùng chung: góc vuông, nền `--track`, phần đã xong màu chính (trước là màu cam bo tròn).

**Token mới** (cả 3 chế độ màu): `--sidebar`, `--brand`, `--field-1/2/3`, `--track`.

- Đã kiểm tương phản: chữ chính trên mọi khối đạt ≥ 9:1.
- Riêng trên `--field-1`, chữ phụ và màu chính chỉ đạt khoảng 4.3:1, nên nội dung trên khối này luôn dùng màu chữ chính (đã ghi vào design system).

**Không đổi:** không có migration. Trang chủ giảng viên chỉ đổi theo `PageHeader` mới. Thẻ `CourseCard` cũ vẫn giữ trong file (không còn trang nào dùng), `Pagination` được làm lại cho hợp kiểu mới.

**Thứ tự làm:** **sau** `2026-10-15-home-mobile-nav-plan.md`. Diff tạo trên HEAD `c0ce7d6`.

**Mã trong plan đã được chạy thử** trên HEAD `c0ce7d6`:

- **Backend:** **786 test pass** (782 + 4 mới). `ruff check`, `ruff format --check` sạch, `lint-imports` 5 hợp đồng KEPT.
- **Frontend:** `tsc`, `eslint` sạch.
  - Unit test: **170 pass** (168 − 4 test cũ của `MyCourseList`/`ResumeCard` + 6 mới).
  - E2E cả bộ: **97 pass + 1 bỏ qua có chủ ý** (375px và 1280px, có kiểm axe, kể cả tương phản trang học ở 3 chế độ màu).
- Đã chụp màn hình trang chủ học viên (sáng, tối, điện thoại), Khám phá và Khóa của tôi để soát. Không trang nào bị cuộn ngang.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6, nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Commit **không** thêm dòng `Co-Authored-By` hay `Claude-Session`.

---

## Task 1: Backend: quiz chưa làm cho trang chủ

**Files:**
- Modify: `backend/app/modules/quiz/schemas.py`, `quizzes.py`, `router.py`
- Create: `backend/tests/test_pending_quizzes.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`

- [x] **Bước 1: Test (sẽ fail)**

```python
"""Trang chủ học viên: quiz chưa làm trong các khóa đã đăng ký (GET /me/pending-quizzes)."""

from tests.helpers import API, make_admin, make_published_quiz, make_student


async def _pending(client, headers):
    r = await client.get(f"{API}/me/pending-quizzes", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_pending_quiz_listed_until_submitted(client, db):
    _, sv, course, quiz, _ = await make_published_quiz(client, db, n_questions=2, time_limit_sec=600)

    (item,) = await _pending(client, sv)
    assert item["quiz_id"] == quiz["id"]
    assert item["title"] == "Quiz tìm kiếm nhị phân"
    assert item["course_title"] == course["title"] and item["course_slug"] == course["slug"]
    assert item["lesson_title"] == "Bài 1" and item["lesson_id"] == quiz["lesson_id"]
    assert item["question_count"] == 2 and item["time_limit_sec"] == 600
    assert item["in_progress"] is False

    attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
    (item,) = await _pending(client, sv)
    assert item["in_progress"] is True  # đang làm dở vẫn là việc cần làm

    r = await client.post(f"{API}/attempts/{attempt['id']}/submit", json={}, headers=sv)
    assert r.status_code == 200, r.text
    assert await _pending(client, sv) == []


async def test_not_enrolled_not_listed(client, db):
    gv, _, _, _, _ = await make_published_quiz(client, db)
    _, other = await make_student(client, "khac@x.com")  # chưa đăng ký khóa
    assert await _pending(client, other) == []
    assert await _pending(client, gv) == []  # giảng viên không đăng ký khóa của mình


async def test_hidden_course_hides_its_quizzes(client, db):
    _, sv, course, _, _ = await make_published_quiz(client, db)
    _, admin = await make_admin(client)
    r = await client.post(
        f"{API}/admin/courses/{course['id']}/hide", json={"reason": "Nội dung chưa phù hợp"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert await _pending(client, sv) == []


async def test_pending_quizzes_need_login(client):
    assert (await client.get(f"{API}/me/pending-quizzes")).status_code == 401
```

- [x] **Bước 2: Schema, service, router.**
  - Ẩn khóa ở trang quản trị sẽ chuyển khóa sang `archived`, nên điều kiện `Course.status == published` loại luôn khóa bị ẩn.
  - Điều kiện "chưa nộp" là không có lượt nào ở trạng thái `completed` hay `timed_out`.

```diff
--- a/backend/app/modules/quiz/schemas.py
+++ b/backend/app/modules/quiz/schemas.py
@@ -126,6 +126,20 @@
     pass
 
 
+class PendingQuizOut(BaseModel):
+    """Quiz đã xuất bản trong khóa học viên đã đăng ký mà học viên chưa nộp lần nào (trang chủ: việc nên làm tiếp)."""
+
+    quiz_id: uuid.UUID
+    title: str
+    lesson_id: uuid.UUID
+    lesson_title: str
+    course_title: str
+    course_slug: str
+    question_count: int
+    time_limit_sec: int | None
+    in_progress: bool  # đang có bài làm dở
+
+
 class AttemptQuestion(BaseModel):
     """Câu hỏi khi đang làm bài: KHÔNG có đáp án đúng, không có giải thích."""
 
```

```diff
--- a/backend/app/modules/quiz/quizzes.py
+++ b/backend/app/modules/quiz/quizzes.py
@@ -9,12 +9,21 @@
 from app.core.errors import AppError, not_found
 from app.core.pagination import PageParams, paginate
 from app.modules.auth.models import Role, User
-from app.modules.courses.models import Course, Lesson, Section
+from app.modules.courses.models import Course, CourseStatus, Lesson, Section
 from app.modules.courses.service import ensure_owner, get_owned_lesson
+from app.modules.enrollment.models import Enrollment
 from app.modules.enrollment.service import ensure_lesson_access
-from app.modules.quiz.models import USABLE_REVIEW, Question, Quiz, QuizAttempt, QuizQuestion, QuizStatus
+from app.modules.quiz.models import (
+    USABLE_REVIEW,
+    AttemptStatus,
+    Question,
+    Quiz,
+    QuizAttempt,
+    QuizQuestion,
+    QuizStatus,
+)
 from app.modules.quiz.questions import to_out
-from app.modules.quiz.schemas import QuestionOut, QuizCreate, QuizOut, QuizPage, QuizUpdate
+from app.modules.quiz.schemas import PendingQuizOut, QuestionOut, QuizCreate, QuizOut, QuizPage, QuizUpdate
 
 
 async def get_quiz_context(db: AsyncSession, quiz_id: uuid.UUID) -> tuple[Quiz, Course]:
@@ -258,3 +267,51 @@
             raise not_found("Quiz")
         await ensure_lesson_access(db, quiz.lesson_id, user)
     return (await _to_outs(db, [quiz], user, manager, with_questions=True))[0]
+
+
+PENDING_LIMIT = 6
+
+
+async def list_pending_quizzes(
+    db: AsyncSession, user: User, limit: int = PENDING_LIMIT
+) -> list[PendingQuizOut]:
+    """Quiz đã xuất bản trong các khóa đã xuất bản mà người dùng đã đăng ký, chưa nộp lần nào (bài làm dở vẫn tính
+    là chưa xong). Bài làm dở lên trước, rồi tới quiz mới nhất. Không đăng ký khóa nào thì danh sách rỗng."""
+    finished = select(QuizAttempt.quiz_id).where(
+        QuizAttempt.user_id == user.id,
+        QuizAttempt.status.in_([AttemptStatus.completed, AttemptStatus.timed_out]),
+    )
+    open_ = select(QuizAttempt.quiz_id).where(
+        QuizAttempt.user_id == user.id, QuizAttempt.status == AttemptStatus.in_progress
+    )
+    in_progress = Quiz.id.in_(open_)
+    stmt = (
+        select(Quiz, Lesson.title, Course.title, Course.slug, in_progress)
+        .join(Lesson, Lesson.id == Quiz.lesson_id)
+        .join(Section, Section.id == Lesson.section_id)
+        .join(Course, Course.id == Section.course_id)
+        .join(Enrollment, (Enrollment.course_id == Course.id) & (Enrollment.user_id == user.id))
+        .where(
+            Quiz.status == QuizStatus.published,
+            Course.status == CourseStatus.published,
+            Quiz.id.not_in(finished),
+        )
+        .order_by(in_progress.desc(), Quiz.created_at.desc(), Quiz.id)
+        .limit(limit)
+    )
+    rows = (await db.execute(stmt)).all()
+    counts = await _question_counts(db, [r[0].id for r in rows])
+    return [
+        PendingQuizOut(
+            quiz_id=quiz.id,
+            title=quiz.title,
+            lesson_id=quiz.lesson_id,
+            lesson_title=lesson_title,
+            course_title=course_title,
+            course_slug=course_slug,
+            question_count=counts.get(quiz.id, 0),
+            time_limit_sec=quiz.time_limit_sec,
+            in_progress=bool(doing),
+        )
+        for quiz, lesson_title, course_title, course_slug, doing in rows
+    ]
```

```diff
--- a/backend/app/modules/quiz/router.py
+++ b/backend/app/modules/quiz/router.py
@@ -19,6 +19,7 @@
     AttemptOut,
     AttemptResult,
     ExplainOut,
+    PendingQuizOut,
     QuestionOut,
     QuestionPage,
     QuestionReview,
@@ -85,6 +86,12 @@
     return await quizzes.list_lesson_quizzes(db, user, lesson_id, params)
 
 
+@router.get("/me/pending-quizzes", response_model=list[PendingQuizOut])
+async def my_pending_quizzes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
+    """Tối đa 6 quiz chưa nộp lần nào trong các khóa đã đăng ký (bài làm dở trước). Trang chủ học viên dùng."""
+    return await quizzes.list_pending_quizzes(db, user)
+
+
 @router.get("/quizzes/{quiz_id}", response_model=QuizOut)
 async def quiz_detail(
     quiz_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
```

- [x] **Bước 3: Chạy test, kiểu API, commit**

```powershell
cd backend
uv run pytest tests/test_pending_quizzes.py -q          # 4 pass
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
uv run pytest -q                                         # 786 pass
cd ..\frontend; npm run gen:api                          # schema.d.ts có /api/v1/me/pending-quizzes, PendingQuizOut
cd ..
git add backend frontend/openapi.json frontend/src/lib/api/schema.d.ts
git commit -m "feat(quiz): GET /me/pending-quizzes, quiz chưa làm trong các khóa đã đăng ký"
```

---

## Task 2: Màu, khung app, tiêu đề trang, thanh tiến độ

**Files:**
- Modify: `frontend/src/app/globals.css`, `frontend/src/components/app/app-shell.tsx`, `frontend/src/components/app/states.tsx`, `frontend/src/components/ui/misc.tsx`, `frontend/src/components/course/course-card.tsx`

- [x] **Bước 1: Token**

```diff
--- a/frontend/src/app/globals.css
+++ b/frontend/src/app/globals.css
@@ -21,6 +21,13 @@
   --ring: #0f6e66;
   --mark: #ffe68f;
   --mark-foreground: #24292f;
+  /* Khung app và các khối màu (2026-10-15b): thanh bên, ô tên app, ba màu khối, nền thanh tiến độ */
+  --sidebar: #e8ebe5;
+  --brand: #16181b;
+  --field-1: #cddfd7;
+  --field-2: #dfe6ec;
+  --field-3: #e4ece8;
+  --track: #d6dbd3;
   --radius: 4px;
   --reader-size: 17px;
 }
@@ -40,6 +47,12 @@
   --ring: #5fbfb3;
   --mark: #e3c55a;
   --mark-foreground: #1a1608;
+  --sidebar: #1b1f23;
+  --brand: #0f1113;
+  --field-1: #1f3330;
+  --field-2: #222b33;
+  --field-3: #1d2a27;
+  --track: #3a4048;
   color-scheme: dark;
 }
 
@@ -58,6 +71,12 @@
   --ring: #2f6b5e;
   --mark: #f2d36b;
   --mark-foreground: #3a2f24;
+  --sidebar: #ece2cc;
+  --brand: #3a2f24;
+  --field-1: #e2d6b5;
+  --field-2: #e9dfc7;
+  --field-3: #efe6cf;
+  --track: #d9cba9;
 }
 
 @theme inline {
@@ -75,6 +94,12 @@
   --color-ring: var(--ring);
   --color-mark: var(--mark);
   --color-mark-foreground: var(--mark-foreground);
+  --color-sidebar: var(--sidebar);
+  --color-brand: var(--brand);
+  --color-field-1: var(--field-1);
+  --color-field-2: var(--field-2);
+  --color-field-3: var(--field-3);
+  --color-track: var(--track);
   --radius-lg: var(--radius);
   --radius-md: var(--radius);
   --font-sans: "Be Vietnam Pro", system-ui, sans-serif;
```

- [x] **Bước 2: Khung app.**
  - Ô tên app lúc thanh bên thu gọn (768–1023px) chỉ hiện chữ "L"; tên đầy đủ nằm trong `aria-label`.
  - Thanh bên có `z-40` để đè lên thanh trên.

```diff
--- a/frontend/src/components/app/app-shell.tsx
+++ b/frontend/src/components/app/app-shell.tsx
@@ -9,7 +9,8 @@
 import { UserMenu } from "./user-menu";
 
 /**
- * Khung chung: thanh bên 240px (≥1024px), thu gọn icon 64px (768–1023px),
+ * Khung chung (cùng ngôn ngữ với trang chủ cho khách): ô tên app nền đậm, thanh bên một tông màu riêng không viền,
+ * mục đang chọn là nền thẻ + vạch màu chính bên trái. Thanh bên 240px (≥1024px), thu gọn icon 64px (768–1023px),
  * thanh dưới tối đa 3 mục (<768px; tài khoản nằm ở menu góc trên). Góc trên luôn có menu tài khoản (hồ sơ, ghi chú, chế độ màu, đăng xuất).
  * Trang bài học và quiz không dùng khung này nhưng có cùng menu tài khoản ở thanh trên.
  */
@@ -27,12 +28,18 @@
       <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
         Bỏ qua tới nội dung
       </a>
-      <aside className="fixed inset-y-0 left-0 hidden w-16 flex-col border-r bg-surface md:flex lg:w-60">
-        <Link href="/" className="flex h-14 items-center gap-2 px-4 font-semibold">
-          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">L</span>
+      <aside className="fixed inset-y-0 left-0 z-40 hidden w-16 flex-col bg-sidebar md:flex lg:w-60">
+        <Link
+          href="/"
+          aria-label="LMS-AI, trang chủ"
+          className="flex h-16 shrink-0 items-center justify-center bg-brand text-xl font-extrabold tracking-[-0.04em] text-white lg:justify-start lg:px-6"
+        >
+          <span className="lg:hidden" aria-hidden>
+            L
+          </span>
           <span className="hidden lg:inline">LMS-AI</span>
         </Link>
-        <nav aria-label="Điều hướng chính" className="flex flex-col gap-1 p-2">
+        <nav aria-label="Điều hướng chính" className="flex flex-col gap-0.5 px-2 py-5 lg:px-3">
           {items.map(({ href, label, icon: Icon }) => (
             <Link
               key={href}
@@ -40,8 +47,9 @@
               title={label}
               aria-current={isActive(pathname, href) ? "page" : undefined}
               className={cn(
-                "flex h-10 items-center gap-3 rounded-md px-3 text-sm transition-colors duration-150 hover:bg-muted",
-                isActive(pathname, href) && "bg-muted font-medium text-primary",
+                "relative flex h-11 items-center justify-center gap-3 px-3 text-[15px] font-semibold text-muted-foreground transition-colors duration-150 hover:bg-field-3 hover:text-foreground lg:justify-start lg:px-3.5",
+                isActive(pathname, href) &&
+                  "bg-surface text-foreground before:absolute before:inset-y-2.5 before:left-0 before:w-1 before:bg-primary hover:bg-surface",
               )}
             >
               <Icon className="size-5 shrink-0" aria-hidden />
@@ -51,21 +59,21 @@
         </nav>
       </aside>
 
-      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur md:px-6">
-        <Link href="/" className="font-semibold md:hidden">
+      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-background px-4 md:h-16 md:px-8">
+        <Link href="/" className="text-lg font-extrabold tracking-[-0.04em] md:hidden">
           LMS-AI
         </Link>
         <div className="hidden md:block" />
         <UserMenu />
       </header>
 
-      <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 md:px-8 md:pb-10 md:pt-8">
+      <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 pt-4 md:px-8 md:pb-16 md:pt-6">
         {children}
       </main>
 
       <nav
         aria-label="Điều hướng chính"
-        className="fixed inset-x-0 bottom-0 z-30 grid h-16 border-t bg-surface md:hidden"
+        className="fixed inset-x-0 bottom-0 z-30 grid h-16 bg-sidebar md:hidden"
         style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
       >
         {items.map(({ href, label, icon: Icon }) => (
@@ -74,8 +82,8 @@
             href={href}
             aria-current={isActive(pathname, href) ? "page" : undefined}
             className={cn(
-              "flex flex-col items-center justify-center gap-0.5 text-xs",
-              isActive(pathname, href) ? "text-primary" : "text-muted-foreground",
+              "flex flex-col items-center justify-center gap-0.5 text-xs font-semibold",
+              isActive(pathname, href) ? "bg-surface text-primary" : "text-muted-foreground",
             )}
           >
             <Icon className="size-5" aria-hidden />
```

- [x] **Bước 3: Tiêu đề trang, thanh tiến độ, nút phân trang**

```diff
--- a/frontend/src/components/app/states.tsx
+++ b/frontend/src/components/app/states.tsx
@@ -59,8 +59,8 @@
   return (
     <div className="mb-6 flex flex-wrap items-end justify-between gap-3 md:mb-8">
       <div>
-        <h1 className="text-2xl font-semibold md:text-3xl">{title}</h1>
-        {children ? <div className="mt-1 text-muted-foreground">{children}</div> : null}
+        <h1 className="text-[clamp(2rem,1.4rem+2vw,3rem)] font-extrabold leading-[1.05] tracking-[-0.035em]">{title}</h1>
+        {children ? <div className="mt-2 text-lg text-muted-foreground">{children}</div> : null}
       </div>
       {actions}
     </div>
```

```diff
--- a/frontend/src/components/ui/misc.tsx
+++ b/frontend/src/components/ui/misc.tsx
@@ -31,10 +31,10 @@
     <ProgressPrimitive.Root
       value={value}
       aria-label={label}
-      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-muted", className)}
+      className={cn("relative h-2 w-full overflow-hidden bg-track", className)}
     >
       <ProgressPrimitive.Indicator
-        className="h-full bg-accent transition-transform duration-200"
+        className="h-full bg-primary transition-transform duration-500"
         style={{ transform: `translateX(-${100 - Math.min(100, Math.max(0, value))}%)` }}
       />
     </ProgressPrimitive.Root>
```

```diff
--- a/frontend/src/components/course/course-card.tsx
+++ b/frontend/src/components/course/course-card.tsx
@@ -38,14 +38,14 @@
   const pages = Math.max(1, Math.ceil(total / size));
   if (pages <= 1) return null;
   return (
-    <nav aria-label="Phân trang" className="mt-6 flex items-center justify-center gap-3 text-sm">
-      <button className="h-10 rounded-md border px-3 disabled:opacity-50" disabled={page <= 1} onClick={() => onPage(page - 1)}>
+    <nav aria-label="Phân trang" className="mt-6 flex items-center justify-center gap-3 text-[15px]">
+      <button className="h-11 bg-surface px-4 font-semibold transition-colors duration-150 hover:bg-field-3 disabled:opacity-50" disabled={page <= 1} onClick={() => onPage(page - 1)}>
         Trang trước
       </button>
       <span aria-current="page">
         {page}/{pages}
       </span>
-      <button className="h-10 rounded-md border px-3 disabled:opacity-50" disabled={page >= pages} onClick={() => onPage(page + 1)}>
+      <button className="h-11 bg-surface px-4 font-semibold transition-colors duration-150 hover:bg-field-3 disabled:opacity-50" disabled={page >= pages} onClick={() => onPage(page + 1)}>
         Trang sau
       </button>
     </nav>
```

- [x] **Bước 4:** `cd frontend; npx tsc --noEmit; npx eslint .; npx vitest run` (pass hết). Commit:

```powershell
git add frontend/src/app/globals.css frontend/src/components/app frontend/src/components/ui/misc.tsx frontend/src/components/course/course-card.tsx
git commit -m "feat(web): khung app cùng giọng trang chủ khách, tiêu đề trang lớn, thanh tiến độ mới"
```

---

## Task 3: Trang chủ học viên, Khóa của tôi, Khám phá

**Files:**
- Modify: `frontend/src/lib/queries.ts`, `frontend/src/lib/quiz/use-quiz-attempt.ts`
- Modify: `frontend/src/components/course/my-course-list.tsx`, `my-course-list.test.tsx`
- Create: `frontend/src/components/home/student-home.tsx`, `student-home.test.tsx`
- Modify: `frontend/src/app/(main)/page.tsx`, `frontend/src/app/(main)/my/page.tsx`, `frontend/src/app/(main)/explore/page.tsx`
- Modify: `frontend/e2e/mock-api.ts`, `frontend/e2e/home-student.spec.ts`
- Modify: `docs/design/design-system.md`, `docs/specs/2026-09-29-lms-ai-design.md`

- [ ] **Bước 1: Truy vấn quiz chưa làm.** Nộp bài xong thì làm mới danh sách này, để quiz vừa làm biến khỏi trang chủ.

```diff
--- a/frontend/src/lib/queries.ts
+++ b/frontend/src/lib/queries.ts
@@ -17,6 +17,7 @@
   catalog: (q: string, page: number) => ["catalog", q, page] as const,
   course: (slug: string) => ["course", slug] as const,
   myCourses: (page: number) => ["my-courses", page] as const,
+  pendingQuizzes: ["pending-quizzes"] as const,
   lesson: (id: string) => ["lesson", id] as const,
   lessonVideo: (id: string) => ["lesson-video", id] as const,
   teacherCourses: (page: number) => [...TEACHER_COURSES, page] as const,
@@ -50,6 +51,15 @@
     enabled,
   });
 }
+
+/** Quiz chưa nộp trong các khóa đã đăng ký (trang chủ học viên: "Việc nên làm tiếp"). */
+export function usePendingQuizzes(enabled = true) {
+  return useQuery({
+    queryKey: qk.pendingQuizzes,
+    queryFn: () => unwrap(api.GET("/api/v1/me/pending-quizzes")),
+    enabled,
+  });
+}
 
 export function useLesson(id: string) {
   return useQuery({
```

```diff
--- a/frontend/src/lib/quiz/use-quiz-attempt.ts
+++ b/frontend/src/lib/quiz/use-quiz-attempt.ts
@@ -83,6 +83,7 @@
     qc.setQueryData(quizKeys.result(a.id), result);
     qc.invalidateQueries({ queryKey: quizKeys.quiz(quizId) });
     qc.invalidateQueries({ queryKey: ["lesson-quizzes"] });
+    qc.invalidateQueries({ queryKey: ["pending-quizzes"] }); // trang chủ: quiz này không còn là việc cần làm
     return result;
   }, [a, answers, closed, quizId, qc, saverFor]);
 
```

- [ ] **Bước 2: Danh sách khóa.**
  - `MyCourseList` và `ResumeCard` của plan trước được thay bằng `CourseRows` (dạng hàng, cho trang chủ) và `CourseBoard` (dạng khối, cho Khóa của tôi).
  - Hàm `pickResume` chọn khóa để học tiếp: ưu tiên khóa máy này nhớ bài đang học; không có thì lấy khóa chưa xong đầu tiên, khi đó nút đổi thành "Vào khóa học".

```tsx
"use client";

import { ArrowRight, BookMarked } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/misc";
import type { components } from "@/lib/api/schema";
import { useMyCourses } from "@/lib/queries";
import { lastLesson } from "@/lib/study/storage";
import { cn } from "@/lib/utils";

export type MyCourse = components["schemas"]["MyCourseOut"];

/** Có bài mở gần nhất trên máy này → vào thẳng bài đó; không thì mở trang khóa. */
export function resumeHref(courseId: string, slug: string) {
  const last = lastLesson.get(courseId);
  return last ? `/learn/${slug}/${last}` : `/courses/${slug}`;
}

/** Khóa để "học tiếp": khóa chưa xong đầu tiên mà máy này còn nhớ bài đang học; không có thì khóa chưa xong đầu tiên. */
export function pickResume(items: MyCourse[]): { course: MyCourse; lessonId: string | null } | null {
  const open = items.filter((c) => !c.completed_at);
  for (const c of open) {
    const lessonId = lastLesson.get(c.course_id);
    if (lessonId) return { course: c, lessonId };
  }
  return open[0] ? { course: open[0], lessonId: null } : null;
}

/** "02/09": ngày/tháng theo giờ máy, không phụ thuộc cách trình duyệt định dạng locale. */
const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
};

function NoCourses() {
  return (
    <EmptyState
      icon={BookMarked}
      title="Bạn chưa đăng ký khóa học nào."
      action={
        <Button asChild>
          <Link href="/explore">Khám phá khóa học</Link>
        </Button>
      }
    />
  );
}

/**
 * Danh sách khóa dạng hàng (trang chủ): tên khóa, thanh tiến độ, số bài. `moreHref`: liên kết xem tất cả, chỉ hiện
 * khi còn khóa chưa hiện (tổng nhiều hơn `limit`).
 */
export function CourseRows({ limit, moreHref }: { limit?: number; moreHref?: string }) {
  const my = useMyCourses();
  if (my.isPending) return <CardListSkeleton count={limit ?? 3} />;
  if (my.isError) return <ErrorState error={my.error} onRetry={() => my.refetch()} />;
  if (my.data.items.length === 0) return <NoCourses />;
  const items = limit ? my.data.items.slice(0, limit) : my.data.items;
  return (
    <>
      <ul className="flex flex-col gap-1.5">
        {items.map((c) => (
          <li key={c.course_id}>
            <Link
              href={resumeHref(c.course_id, c.slug)}
              className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-3 bg-surface px-4 py-5 transition-colors duration-150 hover:bg-field-3 md:grid-cols-[minmax(0,1.4fr)_minmax(140px,1fr)_auto_auto] md:px-6"
            >
              <span className="min-w-0">
                <span className="block truncate text-lg font-semibold tracking-[-0.02em] md:text-xl">{c.title}</span>
                <span className="mt-0.5 block text-sm text-muted-foreground">
                  {c.completed_at ? `Đã hoàn thành ${fmtDate(c.completed_at)}` : `Đăng ký ${fmtDate(c.enrolled_at)}`}
                </span>
              </span>
              <Progress
                value={c.progress_pct}
                label={`Tiến độ ${c.title}`}
                className="col-span-2 row-start-2 md:col-span-1 md:row-start-auto"
              />
              <span className="text-right text-[15px] font-semibold tabular-nums">
                {c.done_lessons}/{c.total_lessons} bài
              </span>
              <ArrowRight
                className="hidden size-5 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-primary md:block"
                aria-hidden
              />
            </Link>
          </li>
        ))}
      </ul>
      {moreHref && my.data.total > items.length ? (
        <Button asChild variant="link" className="mt-4">
          <Link href={moreHref}>
            Xem tất cả {my.data.total} khóa của tôi <ArrowRight />
          </Link>
        </Button>
      ) : null}
    </>
  );
}

const TILE_COLORS = ["bg-field-1", "bg-field-2", "bg-surface", "bg-field-3"];

/** Lưới khối: khối đầu rộng 7/12, khối hai 5/12, các khối sau 6/12; khối lẻ cuối cùng trải hết hàng. */
function tileSpan(i: number, n: number) {
  if (i === 0) return n === 1 ? "md:col-span-12" : "md:col-span-7";
  if (i === 1) return "md:col-span-5";
  const lastAlone = i === n - 1 && (n - 2) % 2 === 1;
  return lastAlone ? "md:col-span-12" : "md:col-span-6";
}

/** Trang Khóa của tôi: hai nhóm Đang học / Đã xong, mỗi khóa là một khối màu có tiến độ và lối vào học tiếp. */
export function CourseBoard() {
  const my = useMyCourses();
  const [tab, setTab] = React.useState<"doing" | "done">("doing");
  if (my.isPending) return <CardListSkeleton />;
  if (my.isError) return <ErrorState error={my.error} onRetry={() => my.refetch()} />;
  if (my.data.items.length === 0) return <NoCourses />;
  const doing = my.data.items.filter((c) => !c.completed_at);
  const done = my.data.items.filter((c) => c.completed_at);
  const shown = tab === "doing" ? doing : done;
  return (
    <>
      <div role="group" aria-label="Lọc khóa học" className="mb-6 flex gap-1.5">
        {(
          [
            ["doing", `Đang học · ${doing.length}`],
            ["done", `Đã xong · ${done.length}`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "h-11 px-4 text-[15px] font-semibold transition-colors duration-150",
              tab === key ? "bg-brand text-white" : "bg-surface text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="bg-surface p-8 text-lg text-muted-foreground">
          {tab === "doing" ? "Bạn đã học xong mọi khóa đã đăng ký." : "Chưa có khóa nào học xong."}
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-1.5 md:grid-cols-12">
          {shown.map((c, i) => (
            <li key={c.course_id} className={tileSpan(i, shown.length)}>
              <Link
                href={resumeHref(c.course_id, c.slug)}
                className={cn(
                  "flex h-full min-h-52 flex-col gap-2 p-6 transition-transform duration-300 hover:-translate-y-1 md:p-8",
                  TILE_COLORS[i % TILE_COLORS.length],
                )}
              >
                <span className="text-[clamp(1.375rem,1.1rem+1vw,2.125rem)] font-extrabold leading-[1.08] tracking-[-0.035em]">
                  {c.title}
                </span>
                <span className="text-sm font-semibold">
                  {c.completed_at ? `Hoàn thành ${fmtDate(c.completed_at)}` : `Đăng ký ${fmtDate(c.enrolled_at)}`}
                </span>
                <span className="mt-auto flex flex-col gap-2.5 pt-6">
                  <Progress value={c.progress_pct} label={`Tiến độ ${c.title}`} className="bg-foreground/15" />
                  <span className="flex justify-between text-[15px] font-semibold tabular-nums">
                    <span>
                      {c.done_lessons}/{c.total_lessons} bài
                    </span>
                    <span>{c.progress_pct}%</span>
                  </span>
                  <span className="inline-flex items-center gap-2 text-[15px] font-semibold underline-offset-4 group-hover:underline">
                    {c.completed_at ? "Xem lại khóa" : c.done_lessons > 0 || lastLesson.get(c.course_id) ? "Học tiếp" : "Bắt đầu học"}
                    <ArrowRight className="size-4" aria-hidden />
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
```

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { lastLesson } from "@/lib/study/storage";
import { api as url, server } from "@/test/msw";
import { CourseBoard, CourseRows, pickResume } from "./my-course-list";

const course = (n: number, over: Record<string, unknown> = {}) => ({
  course_id: `c${n}`,
  title: `Khóa ${n}`,
  slug: `khoa-${n}`,
  enrolled_at: "2026-09-02T00:00:00Z",
  completed_at: null as string | null,
  total_lessons: 10,
  done_lessons: 4,
  progress_pct: 40,
  ...over,
});

function serve(items: ReturnType<typeof course>[], total = items.length) {
  server.use(http.get(url("/me/courses"), () => HttpResponse.json({ items, total, page: 1, size: 20 })));
}

function wrap(ui: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe("pickResume", () => {
  it("ưu tiên khóa chưa xong mà máy này nhớ bài đang học; không có thì khóa chưa xong đầu tiên", () => {
    lastLesson.set("c1", "l-xong"); // khóa 1 đã xong: bỏ qua
    lastLesson.set("c3", "l-7");
    const items = [course(1, { completed_at: "2026-10-01T00:00:00Z" }), course(2), course(3)];
    expect(pickResume(items)).toEqual({ course: items[2], lessonId: "l-7" });
    localStorage.clear();
    expect(pickResume(items)).toEqual({ course: items[1], lessonId: null });
    expect(pickResume([items[0]])).toBeNull();
  });
});

describe("CourseRows", () => {
  it("không có khóa: chỉ ô trống mời khám phá, không có liên kết Xem tất cả", async () => {
    serve([]);
    wrap(<CourseRows limit={3} moreHref="/my" />);
    expect(await screen.findByText("Bạn chưa đăng ký khóa học nào.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Xem tất cả/ })).not.toBeInTheDocument();
  });

  it("chỉ hiện Xem tất cả khi còn khóa chưa hiện; hàng dẫn vào bài đang học", async () => {
    lastLesson.set("c2", "l-5");
    serve([course(1), course(2), course(3), course(4)]);
    const { unmount } = wrap(<CourseRows limit={3} moreHref="/my" />);
    expect(await screen.findByRole("link", { name: /Xem tất cả 4 khóa của tôi/ })).toHaveAttribute("href", "/my");
    expect(screen.getByRole("link", { name: /Khóa 2/ })).toHaveAttribute("href", "/learn/khoa-2/l-5");
    expect(screen.getByRole("link", { name: /Khóa 1/ })).toHaveAttribute("href", "/courses/khoa-1");
    expect(screen.queryByRole("link", { name: /Khóa 4/ })).not.toBeInTheDocument();
    unmount();
    serve([course(1), course(2)]);
    wrap(<CourseRows limit={3} moreHref="/my" />);
    expect(await screen.findByRole("link", { name: /Khóa 2/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Xem tất cả/ })).not.toBeInTheDocument();
  });
});

describe("CourseBoard", () => {
  it("tách Đang học / Đã xong, đếm đúng, đổi nhóm bằng nút", async () => {
    serve([course(1), course(2, { completed_at: "2026-10-02T00:00:00Z", progress_pct: 100 }), course(3)]);
    wrap(<CourseBoard />);
    const doing = await screen.findByRole("button", { name: "Đang học · 2" });
    expect(doing).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: /Khóa 1/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Khóa 2/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Đã xong · 1" }));
    expect(screen.getByRole("link", { name: /Khóa 2/ })).toHaveTextContent("Xem lại khóa");
    expect(screen.queryByRole("link", { name: /Khóa 1/ })).not.toBeInTheDocument();
  });
});
```

- [ ] **Bước 3: Trang chủ học viên.**
  - Ngày hôm nay và bài đang học (đọc từ localStorage) chỉ vẽ sau khi mount, để không lệch giữa server và trình duyệt.
  - Mục "Việc nên làm tiếp" chỉ hiện khi API trả về ít nhất một quiz.

```tsx
"use client";

import { ArrowRight, CirclePlay, Timer } from "lucide-react";
import Link from "next/link";
import { ErrorState } from "@/components/app/states";
import { CourseRows, pickResume } from "@/components/course/my-course-list";
import { Button } from "@/components/ui/button";
import { Progress, Skeleton } from "@/components/ui/misc";
import { useLesson, useMyCourses, usePendingQuizzes } from "@/lib/queries";
import { scrollPosition } from "@/lib/study/storage";
import { useMounted } from "@/lib/use-mounted";
import { cn } from "@/lib/utils";

const DAYS = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];

/** Trang tài liệu có một dòng được tô: cùng hình với trang chủ cho khách. */
function PageMotif() {
  return (
    <svg viewBox="0 0 120 160" className="h-auto w-[min(62%,220px)] transition-transform duration-500 group-hover:-translate-y-1.5 group-hover:-rotate-1" aria-hidden>
      <path d="M0 0h86l34 34v126H0z" className="fill-surface" />
      <path d="M86 0v34h34z" className="fill-foreground" />
      <g className="fill-foreground" opacity=".16">
        <rect x="14" y="22" width="56" height="7" />
        <rect x="14" y="44" width="90" height="5" />
        <rect x="14" y="56" width="84" height="5" />
        <rect x="14" y="68" width="90" height="5" />
        <rect x="14" y="104" width="78" height="5" />
        <rect x="14" y="116" width="90" height="5" />
        <rect x="14" y="128" width="60" height="5" />
      </g>
      <rect x="12" y="84" width="92" height="9" className="fill-mark" />
      <circle cx="106" cy="88.5" r="6" className="fill-foreground" />
    </svg>
  );
}

/** Tên bài đang học (tải bài từ API) và phần đã đọc (lưu trên máy). */
function LessonLine({ lessonId }: { lessonId: string }) {
  const lesson = useLesson(lessonId);
  const read = Math.round(scrollPosition.get(lessonId) * 100);
  if (lesson.isPending) return <Skeleton className="h-7 w-2/3 bg-foreground/10" />;
  if (lesson.isError) return null;
  return (
    <p className="max-w-[34ch] text-xl leading-snug md:text-2xl">
      <span className="bg-mark px-1 text-mark-foreground [box-decoration-break:clone]">{lesson.data.title}</span>
      {read >= 5 && read < 98 ? `, đã đọc khoảng ${read}%` : null}
    </p>
  );
}

/**
 * Trang chủ học viên: lời chào lớn, khối "đang học" (vào thẳng bài đang dở), ba con số, quiz chưa làm, khóa của tôi.
 * Nội dung trên khối màu luôn dùng màu chữ chính (màu phụ không đủ tương phản trên khối xanh đậm nhất).
 */
export function StudentHome({ givenName }: { givenName: string }) {
  const my = useMyCourses();
  const pending = usePendingQuizzes();
  const mounted = useMounted(); // ngày hôm nay và bài đang học (localStorage) chỉ có trên trình duyệt
  const items = my.data?.items ?? [];
  const resume = mounted ? pickResume(items) : null;
  const doing = items.filter((c) => !c.completed_at).length;
  const doneLessons = items.reduce((n, c) => n + c.done_lessons, 0);
  const finished = items.length - doing;
  const now = new Date();

  return (
    <div className="flex flex-col">
      <section aria-labelledby="h-hello" className="flex flex-wrap items-end justify-between gap-x-10 gap-y-4 pb-8 pt-4 md:pb-10 md:pt-8">
        <div className="min-w-0">
          <h1 id="h-hello" className="text-[clamp(2.75rem,1.6rem+4.6vw,5.5rem)] font-extrabold leading-[0.98] tracking-[-0.045em]">
            Chào {givenName}.
          </h1>
          <p className="mt-4 max-w-[46ch] text-lg leading-snug text-muted-foreground md:text-2xl">
            {resume
              ? `Còn ${resume.course.total_lessons - resume.course.done_lessons} bài trong khóa ${resume.course.title}. Học tiếp từ chỗ bạn đã dừng nhé.`
              : items.length
                ? "Bạn đã học xong mọi khóa đã đăng ký. Tìm khóa mới ở trang Khám phá."
                : "Bạn chưa đăng ký khóa nào. Bắt đầu từ trang Khám phá nhé."}
          </p>
        </div>
        {mounted ? (
          <p className="text-sm font-semibold text-muted-foreground md:text-right">
            <span className="block text-xl font-extrabold tracking-[-0.02em] text-foreground">
              {DAYS[now.getDay()]}, {now.getDate()}/{now.getMonth() + 1}
            </span>
            {doneLessons > 0 ? `Bạn đã học xong ${doneLessons} bài` : "Chúc bạn một buổi học tốt"}
          </p>
        ) : null}
      </section>

      {my.isPending ? (
        <Skeleton className="h-72 w-full" />
      ) : my.isError ? (
        <ErrorState error={my.error} onRetry={() => my.refetch()} />
      ) : resume ? (
        <>
          <section aria-labelledby="h-resume" className="group grid bg-field-1 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div className="flex flex-col gap-5 p-6 md:p-10">
              <h2 id="h-resume" className="text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.02] tracking-[-0.04em]">
                {resume.course.title}
              </h2>
              {resume.lessonId ? <LessonLine lessonId={resume.lessonId} /> : <p className="text-xl">Bạn chưa mở bài nào của khóa này trên máy này.</p>}
              <div className="flex max-w-md items-center gap-4 text-[15px] font-semibold">
                <Progress value={resume.course.progress_pct} label={`Tiến độ ${resume.course.title}`} className="flex-1 bg-foreground/15" />
                <span className="tabular-nums">
                  {resume.course.done_lessons}/{resume.course.total_lessons} bài · {resume.course.progress_pct}%
                </span>
              </div>
              <Button asChild size="lg" className="mt-auto h-14 text-base">
                <Link href={resume.lessonId ? `/learn/${resume.course.slug}/${resume.lessonId}` : `/courses/${resume.course.slug}`}>
                  <CirclePlay className="size-5" /> {resume.lessonId ? "Học tiếp" : "Vào khóa học"}
                </Link>
              </Button>
            </div>
            <div className="relative hidden place-items-center bg-field-3 px-8 pb-16 pt-8 md:grid">
              <PageMotif />
              <span className="absolute bottom-5 left-6 text-sm font-semibold">Mở lại đúng đoạn bạn đang đọc</span>
            </div>
          </section>
          <dl className="grid grid-cols-3 bg-surface">
            {(
              [
                [doing, "khóa đang học"],
                [doneLessons, "bài đã học xong"],
                [finished, "khóa đã hoàn thành"],
              ] as const
            ).map(([n, label], i) => (
              <div key={label} className={cn("flex flex-col-reverse px-4 py-5 md:px-8 md:py-7", i === 1 && "bg-background/60")}>
                <dt className="mt-2 text-[13px] font-semibold text-muted-foreground md:text-[15px]">{label}</dt>
                <dd className="text-[clamp(2.25rem,1.6rem+2vw,3.5rem)] font-extrabold leading-none tracking-[-0.05em] tabular-nums">{n}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}

      {pending.data && pending.data.length > 0 ? (
        <section aria-labelledby="h-next" className="mt-16 md:mt-24">
          <h2 id="h-next" className="mb-6 text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.05] tracking-[-0.04em]">
            Việc nên làm tiếp
          </h2>
          <ul className="grid gap-1.5 md:grid-cols-2">
            {pending.data.slice(0, 4).map((q, i) => (
              <li key={q.quiz_id}>
                <Link
                  href={`/learn/${q.course_slug}/${q.lesson_id}/quiz/${q.quiz_id}`}
                  className={cn("flex h-full items-start gap-4 p-5 transition-colors duration-150 md:p-6", i % 2 ? "bg-field-3 hover:bg-field-1" : "bg-field-2 hover:bg-field-1")}
                >
                  <span className="grid size-11 shrink-0 place-items-center bg-surface" aria-hidden>
                    <Timer className="size-5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[17px] font-semibold leading-snug">
                      {q.title} · {q.course_title}
                    </span>
                    <span className="mt-1 block text-[15px]">
                      {q.question_count} câu · {q.time_limit_sec ? `${Math.round(q.time_limit_sec / 60)} phút` : "không giới hạn giờ"} ·{" "}
                      {q.in_progress ? "đang làm dở" : "chưa làm"}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="h-mine" className="mt-16 md:mt-24">
        <div className="mb-6 flex flex-wrap items-baseline justify-between gap-4">
          <h2 id="h-mine" className="text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.05] tracking-[-0.04em]">
            Khóa của tôi
          </h2>
          <Link href="/explore" className="inline-flex items-center gap-2 text-[15px] font-semibold text-primary underline-offset-4 hover:underline">
            Tìm thêm khóa học <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
        <CourseRows limit={3} moreHref="/my" />
      </section>
    </div>
  );
}
```

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { lastLesson, scrollPosition } from "@/lib/study/storage";
import { api as url, server } from "@/test/msw";

vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ status: "authenticated" }) }));

import { StudentHome } from "./student-home";

const course = (n: number, over: Record<string, unknown> = {}) => ({
  course_id: `c${n}`,
  title: `Khóa ${n}`,
  slug: `khoa-${n}`,
  enrolled_at: "2026-09-02T00:00:00Z",
  completed_at: null as string | null,
  total_lessons: 12,
  done_lessons: 5,
  progress_pct: 41,
  ...over,
});

const quiz = (over: Record<string, unknown> = {}) => ({
  quiz_id: "q1",
  title: "Kiểm tra chương 3",
  lesson_id: "l-6",
  lesson_title: "Điều chế biên độ",
  course_title: "Khóa 1",
  course_slug: "khoa-1",
  question_count: 10,
  time_limit_sec: 900,
  in_progress: false,
  ...over,
});

function setup(items: ReturnType<typeof course>[], pending: ReturnType<typeof quiz>[] = []) {
  server.use(
    http.get(url("/me/courses"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 20 })),
    http.get(url("/me/pending-quizzes"), () => HttpResponse.json(pending)),
    http.get(url("/lessons/l-6"), () =>
      HttpResponse.json({ id: "l-6", section_id: "s", course_id: "c1", title: "Điều chế biên độ", content_md: "", duration_sec: null, progress: null }),
    ),
  );
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StudentHome givenName="An" />
    </QueryClientProvider>,
  );
}

describe("StudentHome", () => {
  it("khối đang học: tên bài, phần đã đọc, nút Học tiếp vào đúng bài; ba con số; quiz chưa làm", async () => {
    lastLesson.set("c1", "l-6");
    scrollPosition.set("l-6", 0.6);
    setup([course(1), course(2, { completed_at: "2026-10-01T00:00:00Z", done_lessons: 12, progress_pct: 100 })], [quiz(), quiz({ quiz_id: "q2", title: "Quiz 2", in_progress: true, time_limit_sec: null })]);

    expect(screen.getByRole("heading", { name: "Chào An.", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("Điều chế biên độ")).toBeInTheDocument();
    expect(screen.getByText(/đã đọc khoảng 60%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Học tiếp/ })).toHaveAttribute("href", "/learn/khoa-1/l-6");
    expect(screen.getByText(/Còn 7 bài trong khóa Khóa 1/)).toBeInTheDocument();
    // 1 khóa đang học, 17 bài đã xong, 1 khóa hoàn thành
    expect(screen.getByText("khóa đang học").parentElement).toHaveTextContent(/^khóa đang học1$/);
    expect(screen.getByText("bài đã học xong").parentElement).toHaveTextContent(/^bài đã học xong17$/);
    expect(screen.getByText("khóa đã hoàn thành").parentElement).toHaveTextContent(/^khóa đã hoàn thành1$/);

    const next = await screen.findByRole("link", { name: /Kiểm tra chương 3 · Khóa 1/ });
    expect(next).toHaveAttribute("href", "/learn/khoa-1/l-6/quiz/q1");
    expect(next).toHaveTextContent("10 câu · 15 phút · chưa làm");
    expect(screen.getByRole("link", { name: /Quiz 2/ })).toHaveTextContent("không giới hạn giờ · đang làm dở");
  });

  it("chưa đăng ký khóa nào: lời mời khám phá, không có khối đang học hay Việc nên làm tiếp", async () => {
    setup([]);
    expect(await screen.findByText("Bạn chưa đăng ký khóa học nào.")).toBeInTheDocument();
    expect(screen.getByText(/Bạn chưa đăng ký khóa nào/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Học tiếp/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Việc nên làm tiếp" })).not.toBeInTheDocument();
  });
});
```

```diff
--- a/frontend/src/app/(main)/page.tsx
+++ b/frontend/src/app/(main)/page.tsx
@@ -6,7 +6,7 @@
 import * as React from "react";
 import { toast } from "sonner";
 import { PageHeader } from "@/components/app/states";
-import { MyCourseList, ResumeCard } from "@/components/course/my-course-list";
+import { StudentHome } from "@/components/home/student-home";
 import { Landing } from "@/components/landing/landing";
 import { Button } from "@/components/ui/button";
 import { Skeleton } from "@/components/ui/misc";
@@ -71,25 +71,20 @@
   // Khách: trang giới thiệu riêng, không nằm trong khung app (AppShell bỏ khung ở "/" khi chưa đăng nhập).
   if (!user) return <Landing />;
 
+  if (user.role === "student") return <StudentHome givenName={givenName(user.full_name)} />;
+
   // Chỉ giảng viên đã duyệt mới vào được /teach.
   const canTeach = user.role === "teacher" && user.teacher_status === "approved";
 
   return (
     <>
       <PageHeader title={`Chào ${givenName(user.full_name)}`}>
-        {user.role === "student" ? "Tiếp tục từ chỗ bạn đã dừng." : canTeach ? "Quản lý các khóa bạn đang dạy." : "Chào mừng bạn đến với LMS-AI."}
+        {canTeach ? "Quản lý các khóa bạn đang dạy." : "Chào mừng bạn đến với LMS-AI."}
       </PageHeader>
       <TeacherReviewNotice user={user} />
-      {user.role === "student" ? (
-        <>
-          <ResumeCard />
-          <MyCourseList limit={3} moreHref="/my" />
-        </>
-      ) : (
-        <Button asChild>
-          <Link href={canTeach ? "/teach" : "/explore"}>{canTeach ? "Tới khóa đang dạy" : "Khám phá khóa học"}</Link>
-        </Button>
-      )}
+      <Button asChild>
+        <Link href={canTeach ? "/teach" : "/explore"}>{canTeach ? "Tới khóa đang dạy" : "Khám phá khóa học"}</Link>
+      </Button>
     </>
   );
 }
```

```diff
--- a/frontend/src/app/(main)/my/page.tsx
+++ b/frontend/src/app/(main)/my/page.tsx
@@ -1,14 +1,14 @@
 "use client";
 
 import { PageHeader } from "@/components/app/states";
-import { MyCourseList } from "@/components/course/my-course-list";
+import { CourseBoard } from "@/components/course/my-course-list";
 import { RequireAuth } from "@/lib/auth/require-auth";
 
 export default function MyCoursesPage() {
   return (
     <RequireAuth>
       <PageHeader title="Khóa của tôi" />
-      <MyCourseList />
+      <CourseBoard />
     </RequireAuth>
   );
 }
```

- [ ] **Bước 4: Khám phá.**
  - Khối "khóa mới nhất" chỉ hiện ở trang 1, khi không tìm kiếm và có từ 2 khóa trở lên. Mỗi lần hiện, khối này gọi thêm `GET /courses/{slug}` để lấy 3 bài đầu.
  - Nhãn "Bạn đang học" lấy từ trang đầu `/me/courses`, và chỉ gọi khi người dùng là học viên.

```tsx
"use client";

import { ArrowRight, Compass, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { CardListSkeleton, EmptyState, ErrorState } from "@/components/app/states";
import { Pagination } from "@/components/course/course-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import type { components } from "@/lib/api/schema";
import { useAuth } from "@/lib/auth/auth-context";
import { flattenLessons, useCatalog, useCourse, useMyCourses } from "@/lib/queries";
import { useDebounced } from "@/lib/use-debounced";

type CatalogItem = components["schemas"]["CourseCard"];

const minutes = (sec: number | null | undefined) => (sec ? `${Math.max(1, Math.round(sec / 60))} phút` : null);

/** Vài bài đầu của khóa nổi bật (lấy từ trang chi tiết khóa). */
function FirstLessons({ slug }: { slug: string }) {
  const course = useCourse(slug);
  if (course.isPending) return <Skeleton className="h-32 w-full" />;
  if (course.isError) return null;
  const lessons = flattenLessons(course.data).slice(0, 3);
  if (lessons.length === 0) return <p className="text-muted-foreground">Khóa học đang được soạn bài.</p>;
  return (
    <>
      <h3 className="text-[15px] font-semibold text-muted-foreground">Những bài đầu tiên</h3>
      <ol className="flex flex-col">
        {lessons.map((l) => (
          <li key={l.id} className="flex justify-between gap-4 py-2.5 text-base">
            <span className="min-w-0">{l.title}</span>
            {minutes(l.duration_sec) ? <span className="shrink-0 text-sm text-muted-foreground">{minutes(l.duration_sec)}</span> : null}
          </li>
        ))}
      </ol>
    </>
  );
}

/** Khóa mới nhất (đầu danh sách, catalog xếp mới trước) đặt trong một khối màu lớn. */
function FeaturedCourse({ c, enrolled }: { c: CatalogItem; enrolled: boolean }) {
  return (
    <article aria-labelledby={`c-${c.id}`} className="grid bg-field-2 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <h2 id={`c-${c.id}`} className="text-[clamp(1.75rem,1.2rem+2.2vw,3rem)] font-extrabold leading-[1.02] tracking-[-0.04em]">
          {c.title}
        </h2>
        <p className="text-[15px] font-semibold">
          Khóa mới nhất · {c.teacher_name}
          {enrolled ? " · Bạn đang học" : ""}
        </p>
        {c.description ? <p className="line-clamp-4 max-w-[40ch] text-lg leading-snug md:text-xl">{c.description}</p> : null}
        <Button asChild size="lg" className="mt-auto h-14 self-start text-base">
          <Link href={`/courses/${c.slug}`}>
            Xem khóa học <ArrowRight className="size-5" />
          </Link>
        </Button>
      </div>
      <div className="flex flex-col justify-center gap-3 bg-surface p-6 md:p-10">
        <FirstLessons slug={c.slug} />
      </div>
    </article>
  );
}

/** Một dòng trong mục lục khóa học: tên lớn bên trái, mô tả bên phải. */
function CatalogEntry({ c, enrolled }: { c: CatalogItem; enrolled: boolean }) {
  return (
    <li>
      <Link
        href={`/courses/${c.slug}`}
        className="group grid gap-3 bg-surface px-4 py-6 transition-colors duration-150 hover:bg-field-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto] md:gap-8 md:px-6 md:py-7"
      >
        <span className="min-w-0">
          <span className="block text-[clamp(1.375rem,1.1rem+1vw,2rem)] font-extrabold leading-[1.08] tracking-[-0.035em]">{c.title}</span>
          {enrolled ? <span className="mt-2.5 inline-block bg-field-1 px-2 py-0.5 text-[13px] font-semibold">Bạn đang học</span> : null}
        </span>
        <span className="min-w-0">
          {c.description ? <span className="line-clamp-3 block max-w-[52ch] text-base leading-relaxed">{c.description}</span> : null}
          <span className="mt-2 block text-sm font-semibold text-muted-foreground">{c.teacher_name}</span>
        </span>
        <span className="inline-flex items-center gap-2 pt-1 text-[15px] font-semibold text-primary">
          Xem <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" aria-hidden />
        </span>
      </Link>
    </li>
  );
}

export default function ExplorePage() {
  const { user } = useAuth();
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  // đổi từ khóa thì quay về trang 1 (trang gắn với từ khóa đã tìm)
  const [paging, setPaging] = React.useState({ query: "", page: 1 });
  const page = paging.query === query ? paging.page : 1;
  const setPage = (p: number) => setPaging({ query, page: p });
  const catalog = useCatalog(query, page);
  // Học viên: đánh dấu khóa đã đăng ký (chỉ trang đầu danh sách khóa của tôi, đủ cho số khóa một học viên học)
  const my = useMyCourses(1, user?.role === "student");
  const enrolled = new Set((my.data?.items ?? []).map((c) => c.course_id));

  const items = catalog.data?.items ?? [];
  const featured = !query && page === 1 && items.length > 1 ? items[0] : null;
  const rest = featured ? items.slice(1) : items;

  return (
    <>
      <div className="mb-8 grid items-end gap-6 pt-4 md:mb-10 md:pt-8 lg:grid-cols-[minmax(0,1fr)_minmax(260px,380px)]">
        <div>
          <h1 className="text-[clamp(2.25rem,1.3rem+3vw,4.25rem)] font-extrabold leading-[1] tracking-[-0.045em]">Khám phá khóa học</h1>
          <p className="mt-4 max-w-[46ch] text-lg leading-snug text-muted-foreground md:text-xl">
            {catalog.data && !query
              ? `${catalog.data.total} khóa học đang mở. Khóa nào cũng có AI Tutor trả lời theo đúng tài liệu của khóa.`
              : "Khóa nào cũng có AI Tutor trả lời theo đúng tài liệu của khóa."}
          </p>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="catalog-search" className="sr-only">
            Tìm khóa học
          </label>
          <input
            id="catalog-search"
            type="search"
            placeholder="Tìm theo tên, gõ không dấu cũng được"
            className="h-14 w-full bg-surface pl-12 pr-4 text-base outline-2 outline-transparent transition-[outline-color] duration-150 placeholder:text-muted-foreground focus:outline-primary"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      {catalog.isPending ? (
        <CardListSkeleton />
      ) : catalog.isError ? (
        <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={Compass} title={query ? `Không tìm thấy khóa học nào cho “${query}”.` : "Chưa có khóa học nào được xuất bản."} />
      ) : (
        <div aria-busy={catalog.isFetching} className="flex flex-col gap-1.5">
          {featured ? <FeaturedCourse c={featured} enrolled={enrolled.has(featured.id)} /> : null}
          <ul className="flex flex-col gap-1.5">
            {rest.map((c) => (
              <CatalogEntry key={c.id} c={c} enrolled={enrolled.has(c.id)} />
            ))}
          </ul>
          <Pagination page={page} total={catalog.data.total} size={catalog.data.size} onPage={setPage} />
        </div>
      )}
    </>
  );
}
```

- [ ] **Bước 5: E2E**

```diff
--- a/frontend/e2e/mock-api.ts
+++ b/frontend/e2e/mock-api.ts
@@ -140,6 +140,7 @@
     "GET /lessons/*/documents": (r) => json(r, []),
     "POST /tutor/messages/*/followups": (r) => json(r, { questions: [] }),
     "GET /notes": (r) => json(r, { items: [], total: 0, page: 1, size: 20 }),
+    "GET /me/pending-quizzes": (r) => json(r, []),
     ...opts.extra,
   };
 
```

```diff
--- a/frontend/e2e/home-student.spec.ts
+++ b/frontend/e2e/home-student.spec.ts
@@ -2,15 +2,40 @@
 import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
 import { COURSE_ID, L2, mockApi } from "./mock-api";
 
-test("trang chủ học viên: thẻ Học tiếp vào thẳng bài đang học, thanh dưới không còn mục Tài khoản", async ({ page, isMobile }) => {
+test("trang chủ học viên: khối Học tiếp vào thẳng bài đang học, quiz chưa làm, thanh dưới không còn mục Tài khoản", async ({ page, isMobile }) => {
   await page.addInitScript(
     ([courseId, lessonId]) => localStorage.setItem(`lms:last-lesson:${courseId}`, JSON.stringify(lessonId)),
     [COURSE_ID, L2],
   );
-  await mockApi(page);
+  await mockApi(page, {
+    extra: {
+      "GET /me/pending-quizzes": (r) =>
+        r.fulfill({
+          json: [
+            {
+              quiz_id: "q-1",
+              title: "Kiểm tra đạo hàm",
+              lesson_id: L2,
+              lesson_title: "Quy tắc tính đạo hàm",
+              course_title: "Giải tích 1",
+              course_slug: "giai-tich-1",
+              question_count: 10,
+              time_limit_sec: 900,
+              in_progress: false,
+            },
+          ],
+        }),
+    },
+  });
   await page.goto("/");
+  await expect(page.getByRole("heading", { name: "Chào An.", level: 1 })).toBeVisible();
   const resume = page.getByRole("region", { name: "Giải tích 1" });
   await expect(resume.getByRole("link", { name: "Học tiếp" })).toHaveAttribute("href", `/learn/giai-tich-1/${L2}`);
+  await expect(resume.getByText("Quy tắc tính đạo hàm")).toBeVisible();
+  await expect(page.getByRole("link", { name: /Kiểm tra đạo hàm · Giải tích 1/ })).toHaveAttribute(
+    "href",
+    `/learn/giai-tich-1/${L2}/quiz/q-1`,
+  );
   // chỉ 1 khóa nên không có "Xem tất cả"
   await expect(page.getByRole("link", { name: /Xem tất cả/ })).toHaveCount(0);
   if (isMobile) {
```

- [ ] **Bước 6: Tài liệu**

```diff
--- a/docs/design/design-system.md
+++ b/docs/design/design-system.md
@@ -32,6 +32,10 @@
 | `--primary-foreground` | `#FFFFFF` | `#0E1A19` | `#FFFFFF` | Chữ trên nút chính |
 | `--accent` | `#A15C07` | `#E0A458` | `#8A5313` | Tiến độ, điểm nổi bật |
 | `--mark` | `#FFE68F` | `#E3C55A` | `#F2D36B` | Nền số trích dẫn [n] và dòng tài liệu được tô (như bút dạ quang); chữ trên nó là `--mark-foreground` |
+| `--sidebar` | `#E8EBE5` | `#1B1F23` | `#ECE2CC` | Thanh bên, thanh dưới điện thoại (không viền, tách bằng tông màu) |
+| `--brand` | `#16181B` | `#0F1113` | `#3A2F24` | Ô tên "LMS-AI" ở đầu thanh bên, nút lọc đang chọn (chữ trắng) |
+| `--field-1/2/3` | `#CDDFD7` / `#DFE6EC` / `#E4ECE8` | `#1F3330` / `#222B33` / `#1D2A27` | `#E2D6B5` / `#E9DFC7` / `#EFE6CF` | Khối màu lớn (khối đang học, khóa nổi bật, khối khóa). Trên `--field-1` chỉ dùng màu chữ chính: chữ phụ và màu chính chỉ đạt khoảng 4.3:1 |
+| `--track` | `#D6DBD3` | `#3A4048` | `#D9CBA9` | Nền thanh tiến độ (phần đã xong là màu chính, góc vuông) |
 | `--success` | `#2F7D4F` | `#7CC49A` | `#3B6E45` | Đúng, hoàn thành, đã xử lý |
 | `--destructive` | `#B42318` | `#F2867A` | `#A3321F` | Xóa, lỗi, sai |
 
@@ -63,7 +67,7 @@
 
 - `xs` 12px: chỉ dùng cho nhãn phụ, không bao giờ dùng cho nội dung.
 - `sm` 14px, `base` 16px, `lg` 18px, `xl` 20px, `2xl` 24px, `3xl` 30px.
-- Tiêu đề trang trên điện thoại 24px, desktop 30px. Độ đậm 600, không dùng 800–900 trong app. Ngoại lệ duy nhất: trang chủ cho khách (`components/landing`) dùng 800 cho tiêu đề lớn.
+- Tiêu đề trang (`PageHeader`) từ 2026-10-15: 32–48px, độ đậm 800, giãn chữ -0.035em, cùng giọng với trang chủ cho khách. Lời chào ở trang chủ học viên và tiêu đề trang Khám phá lớn hơn (tới 88px / 68px). Chữ nội dung và nhãn vẫn 400–600.
 
 ---
 
```

```diff
--- a/docs/specs/2026-09-29-lms-ai-design.md
+++ b/docs/specs/2026-09-29-lms-ai-design.md
@@ -496,7 +496,7 @@
 | Module | Endpoint |
 |---|---|
 | Khóa học | `GET /courses` · `GET /courses/{slug}` · `POST/PATCH/DELETE /courses` · `POST /courses/{id}/publish` · CRUD sections/lessons · `PATCH /courses/{id}/reorder` · `GET /teacher/courses?page=&size=` (khóa của giảng viên đang đăng nhập, phân trang) |
-| Học | `POST /courses/{id}/enroll` · `GET /me/courses?page=&size=` (phân trang) · `GET /lessons/{id}` (nội dung bài học) · `GET /lessons/{id}/video` (presigned GET) · `PUT /lessons/{id}/progress` |
+| Học | `POST /courses/{id}/enroll` · `GET /me/courses?page=&size=` (phân trang) · `GET /me/pending-quizzes` (quiz chưa làm, trang chủ) · `GET /lessons/{id}` (nội dung bài học) · `GET /lessons/{id}/video` (presigned GET) · `PUT /lessons/{id}/progress` |
 | Tài liệu | `POST /uploads/presign` · `POST /uploads/{id}/complete` · `POST /lessons/{id}/sources` → 202 · `GET /lessons/{id}/sources` · `GET /sources/{id}` · `POST /sources/{id}/reprocess` → 202 · `GET /sources/{id}/pages?page=&size=` (`size ≤ 100`, trả `{items, total, page, size}`) |
 | Tutor | `POST /tutor/sessions` · `GET /tutor/sessions?course_id=` (phiên của chính mình, phân trang) · `GET /tutor/availability?course_id=&lesson_id=` (`{available, ready_chunks, message, state, processing_docs, can_queue}`) · `POST /tutor/sessions/{id}/questions` → 202 (câu hỏi chờ khi tài liệu đang xử lý) · `GET /tutor/sessions/{id}/messages` · `POST /tutor/sessions/{id}/messages` (SSE, frontend đọc bằng `fetch` + `ReadableStream`) · `POST /tutor/messages/{id}/feedback` |
 | Câu hỏi | `POST /lessons/{id}/questions/generate` → 202 · `GET /lessons/{id}/questions?review_status=` · `PATCH /questions/{id}` |
@@ -770,3 +770,4 @@
 | 2026-10-12 | Trích PDF: chèn lại dấu cách bị mất ở PDF xuất từ slide (hai ký tự cách nhau > 10% cỡ chữ mà không có dấu cách); script `reprocess_pdfs` xử lý lại hàng loạt; `app.scripts.lock_user` khóa/mở khóa tài khoản bằng lệnh (kể cả admin, không khóa admin cuối cùng) |
 | 2026-10-12 | B1: `time_limit_sec` (60 giây – 4 giờ) và `shuffle` khi tạo/sửa quiz (null tường minh = bỏ giới hạn); `deadline_at` theo giờ DB, `server_now` trong bài làm để đồng hồ không lệch; quá `deadline_at + 5s` thì lưu/nộp bị từ chối và bài chốt `timed_out` với đáp án đã autosave; chốt khi có thao tác trên bài + cron mỗi phút. B2: hybrid vector top-20 + full-text top-20 gộp RRF (k=60), `RETRIEVAL_MODE=vector` để so sánh, benchmark có `mode=`. B3: `POST /attempts/{id}/answers/{qid}/explain` sau khi nộp, chỉ câu sai/bỏ trống, 30 lần/giờ/học viên, lỗi AI → 503 |
 | 2026-10-15 | Hồ sơ cá nhân: `PATCH /me` (họ tên, gọn khoảng trắng, 1–120 ký tự), `POST /me/password` (đúng mật khẩu hiện tại, khác mật khẩu cũ, 10 lần thử/giờ/tài khoản; thu hồi mọi phiên rồi cấp phiên mới cho trình duyệt đang dùng). Menu tài khoản (Hồ sơ cá nhân, Ghi chú, chế độ màu, Đăng xuất) ở thanh trên của mọi trang kể cả trang học và quiz; đăng xuất tải lại trang chủ. Giao diện: bảng màu sáng trung tính, bo góc 4px, `--mark` cho trích dẫn; trang chủ cho khách mới (không nằm trong khung app) có phần thử hỏi với 4 câu mẫu cố định |
+| 2026-10-15 | Giao diện sau đăng nhập cùng giọng với trang chủ cho khách: thanh bên một tông màu, ô tên app nền đậm, tiêu đề trang 800; trang chủ học viên có lời chào lớn, khối đang học (tên bài lấy từ API, phần đã đọc lưu trên máy), ba con số, "Việc nên làm tiếp" từ `GET /me/pending-quizzes` (quiz đã xuất bản trong khóa đã đăng ký, chưa nộp lần nào, bài làm dở trước, tối đa 6), danh sách khóa dạng hàng; Khám phá có khóa mới nhất trong khối màu và mục lục khóa; Khóa của tôi chia Đang học / Đã xong |
```

- [ ] **Bước 7: Kiểm tra + commit**

```powershell
cd frontend
npx tsc --noEmit ; npx eslint .
npx vitest run                     # 170 pass
npx playwright test                # 97 pass + 1 bỏ qua có chủ ý
cd ..
git add frontend docs
git commit -m "feat(web): trang chủ học viên (khối học tiếp, quiz chưa làm), Khám phá dạng mục lục, Khóa của tôi dạng khối"
```

---

## Task 4: Kiểm tay (bạn làm)

Sau khi pull: `docker compose --profile web up -d --build`.

- [ ] **Trang chủ học viên:** đăng nhập học viên đã học dở một bài (mở bài, cuộn xuống giữa bài rồi quay về trang chủ).
  - Thấy "Chào …." chữ lớn và ngày hôm nay.
  - Khối xanh có tên khóa, tên bài tô vàng, "đã đọc khoảng N%".
  - Bấm "Học tiếp" vào đúng bài, đúng đoạn đang đọc.
- [ ] **Việc nên làm tiếp:**
  - Giảng viên xuất bản một quiz ở khóa học viên đã đăng ký → trang chủ học viên hiện quiz đó, ghi "chưa làm".
  - Mở quiz rồi quay về mà chưa nộp → ghi "đang làm dở".
  - Nộp bài xong → quiz biến khỏi trang chủ.
- [ ] **Khám phá:**
  - Có từ 2 khóa: khóa mới nhất nằm trong khối màu, kèm 3 bài đầu.
  - Gõ tìm kiếm không dấu thì khối nổi bật ẩn, chỉ còn danh sách.
  - Khóa đã đăng ký có nhãn "Bạn đang học".
- [ ] **Khóa của tôi:** nút "Đang học" / "Đã xong" đếm đúng; khối khóa đã học xong ghi "Xem lại khóa".
- [ ] **Chế độ màu:** đổi Tối dịu và Giấy (menu tài khoản), xem 3 trang trên. Chữ trên khối màu đọc rõ, không có chỗ trắng lóa.
- [ ] **Điện thoại (375px):** thanh dưới cùng tông thanh bên, không cuộn ngang, nút "Học tiếp" rộng hết khối.
- [ ] **Giảng viên và quản trị:** tiêu đề trang to hơn trước. Xem các trang của mình, chỗ nào tiêu đề quá to hoặc xuống dòng xấu thì chụp màn hình gửi Claude.
