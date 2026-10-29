# Sửa B5 sau review: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** ngày 29/10, Claude review B5 (`291dc23..81653e8`) bằng 2 lượt review riêng cho backend và frontend. Không có lỗi nghiêm trọng, nhưng có 6 lỗi làm bài nộp bị kẹt, điểm ghi nhầm bản, mất bài đã chấm hoặc mất phần giảng viên đã gõ. Plan này sửa cả 6 lỗi và vài lỗi nhỏ, mỗi lỗi có test.

**Lỗi được sửa:**

| # | Lỗi | Cách sửa |
|---|---|---|
| 1 | Job chấm quá 270 giây hoặc worker chết: job chuyển failed nhưng bài vẫn `submitted`, giảng viên thấy "AI đang chấm" mãi. Lý do: bị hủy vì quá giờ thì không đi vào `except Exception` trong `grading.py`, còn sweeper chỉ dọn `sources` | `_fail_jobs` (dùng cho cả nhánh quá giờ của `run_job` lẫn sweeper) gọi `grading.fail_unfinished`: bài đúng `version` đó còn `submitted` thì chuyển `ai_failed`, kèm lý do, và báo giảng viên |
| 2 | Giảng viên đang xem bản 1 thì học viên nộp lại bản 2; bấm xác nhận thì điểm của bản 1 bị ghi vào bản 2 và bài bị khóa | `GradeIn` có thêm `version` (bắt buộc). `grade()` khóa dòng `FOR UPDATE`, lệch version thì 409 `STALE_VERSION`. Màn hình chấm gửi version đang xem; gặp 409 thì báo và tải bản mới |
| 3 | Xóa bài học hoặc chương xóa luôn (cascade) bài nộp đã chấm, không chặn | `_ensure_no_student_work` chặn khi đã có bài nộp (409, "đã có bài nộp của học viên"). Thêm ngoại lệ import-linter `courses.service -> assignment.models` (chỉ đọc bảng, như quiz) |
| 4 | AI trả điểm `NaN`: không ghi được vào JSONB, job hỏng, bài kẹt như lỗi 1 | `score: float = Field(allow_inf_nan=False)`: coi là output sai và thử lại |
| 5 | Màn hình chấm: giảng viên đang gõ điểm thì AI chấm xong, lần tải lại 4 giây sau dựng lại form và thay hết bằng điểm AI | Form chỉ gắn key theo `id` + `version`. Gợi ý AI tới sau chỉ được điền khi giảng viên chưa gõ gì |
| 6 | Bài đã chấm mà giảng viên đã xóa nhận xét: nhận xét AI hiện lại trong ô, bấm "Cập nhật điểm" là gửi cho học viên | Bài đã chấm chỉ điền điểm và nhận xét của giảng viên |

**Lỗi nhỏ sửa kèm:**

- Bấm đúp "Nộp bài" lần đầu: hai request cùng `INSERT`, request sau đụng unique và trả 500. Sửa: `INSERT … ON CONFLICT DO NOTHING` một dòng `version 0` rồi đi chung nhánh nộp lại, nên lần đầu thành version 1.
- Sửa bài tập (chỉ đổi tiêu đề) làm hạn nộp 23:59:59 thành 23:59:00, vì ô `datetime-local` bỏ phần giây. Sửa: chỉ gửi `due_at` khi ô hạn nộp đã đổi.
- Hộp tạo/sửa bài tập:
  - Thiếu `noValidate` nên hiện bong bóng lỗi của trình duyệt thay cho câu tiếng Việt.
  - Ô điểm tối đa không xóa trắng được (đang lưu dạng số).
- Trang chấm:
  - Tải bài tập lỗi thì treo ở khung xám; mở link `?bai=` khi bài tập chưa tải xong thì hiện "Chọn một bài nộp…".
  - `?bai=` của bài tập khác thì báo thay vì chấm theo rubric sai.

**Không sửa trong plan này:**

- Học viên chưa đăng ký nhận 403 (không phải 404): đây là cách chung của cả dự án (`ensure_lesson_access`), không phải lỗi.
- Học viên thấy trạng thái "AI đã chấm / AI lỗi" của bài mình (không thấy điểm).
- Bài dài hơn 40.000 ký tự bị cắt mà không báo giảng viên.
- File cũ không bị xóa khi nộp lại bằng file khác.

**Không có migration.** API đổi một chỗ: `POST /submissions/{id}/grade` bắt buộc có `version`. Frontend trong plan đã gửi trường này.

**Thứ tự làm:** **sau** `2026-10-29-assignments-plan.md`. Diff tạo trên HEAD `81653e8`. Code giống hệt bản mình đã kiểm, chỉ khác file plan đã tick.

**Mã trong plan đã được chạy thử** trên code của `81653e8`:

- **Backend:** **826 test pass** (820 + 6 mới). `ruff check`, `ruff format --check` sạch, `lint-imports` 6 hợp đồng KEPT, `alembic check` không lệch.
  - 6 test mới và 2 test cũ đã sửa (gửi `version`) đều **fail trên code cũ**.
- **Frontend:** `tsc`, `eslint` sạch.
  - Unit test: **196 pass** (191 + 5 mới). Trên code cũ, 4 test mới fail; test "chưa gõ gì thì gợi ý AI tới sau vẫn được điền sẵn" pass cả trước và sau, dùng để giữ hành vi cũ.
  - E2E cả bộ: **107 pass + 1 bỏ qua có chủ ý**.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6, nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Commit **không** thêm dòng `Co-Authored-By` hay `Claude-Session`. Khi chạy test giữ `*_PROVIDER=fake`, và chỉ chạy **một** lượt pytest một lúc.

---

## Task 1: Backend (lỗi 1–4, bấm đúp khi nộp)

**Files:**
- Modify: `backend/app/modules/assignment/grading.py`, `backend/app/modules/assignment/schemas.py`, `backend/app/modules/assignment/service.py`, `backend/app/modules/courses/service.py`, `backend/app/worker/tasks.py`, `backend/.importlinter`, `backend/tests/test_assignments.py`

- [x] **Bước 1: Test (sẽ fail).** Hai test cũ gửi thêm `version`. 6 test mới:
  - xác nhận điểm phải đúng version đang xem;
  - bấm đúp lần nộp đầu chỉ tạo một bài;
  - job quá giờ → bài `ai_failed` và giảng viên được báo;
  - sweeper chốt job treo → bài `ai_failed`;
  - không xóa được bài học đã có bài nộp;
  - điểm `NaN` bị từ chối.

```diff
--- a/backend/tests/test_assignments.py
+++ b/backend/tests/test_assignments.py
@@ -4,7 +4,7 @@ import json
 import uuid
 from datetime import timedelta
 
-from sqlalchemy import select
+from sqlalchemy import select, update
 
 from app.ai.llm import FakeLLMProvider
 from app.ai.llm_client import LLMClient
@@ -13,7 +13,7 @@ from app.core.time import utcnow
 from app.modules.assignment.grading import AI_ERROR, GradeDraft, check_draft, evidence_found
 from app.modules.inbox.models import Notification
 from app.modules.jobs.models import Job, JobStatus
-from app.worker.tasks import grade_submission
+from app.worker.tasks import JOB_TIMEOUTS, grade_submission, sweep_stale_jobs
 from tests.helpers import API, keys_in, make_published_course, make_student, make_teacher, upload_file
 from tests.pdfs import make_pdf
 from tests.test_ai_retry import Sleeps
@@ -99,7 +99,7 @@ async def test_full_flow_submit_ai_suggests_teacher_confirms(client, db, storage
 
     r = await client.post(
         f"{API}/submissions/{mine['id']}/grade",
-        json={"scores": {"c1": 5.5, "c2": 4}, "feedback": " Tốt "},
+        json={"version": 1, "scores": {"c1": 5.5, "c2": 4}, "feedback": " Tốt "},
         headers=gv,
     )
     assert r.status_code == 200, r.text
@@ -180,7 +180,9 @@ async def test_rules_and_permissions(client, db):
     assert (await client.delete(f"{API}/assignments/{a['id']}", headers=gv)).status_code == 409
 
     for scores in ({"c1": 1}, {"c1": 7, "c2": 1}, {"c1": 1, "c2": 1, "c9": 1}):
-        r = await client.post(f"{API}/submissions/{sub['id']}/grade", json={"scores": scores}, headers=gv)
+        r = await client.post(
+            f"{API}/submissions/{sub['id']}/grade", json={"version": 1, "scores": scores}, headers=gv
+        )
         assert (r.status_code, r.json()["error"]["code"]) == (422, "INVALID_SCORES"), scores
 
     _, other_gv = await make_teacher(client, "gv2@x.com")
@@ -276,3 +278,88 @@ async def test_submission_cannot_close_tag_with_case_or_space_variants(client, d
     prompt = provider.calls[0].prompt
     assert prompt.count("</submission>") == 1
     assert "</SUBMISSION>" not in prompt and "</ submission >" not in prompt
+
+
+async def test_grade_must_match_version_teacher_is_viewing(client, db, storage, hub):
+    """Học viên nộp lại khi giảng viên đang chấm bản cũ: điểm không bị ghi vào bản mới."""
+    gv, sv, _, _, a = await _setup(client)
+    sub = await _submit(client, sv, a, text_content="bản một")
+    await grade_submission(_ctx(storage, hub), str((await _job(db, sub["id"], 1)).id))
+    await _submit(client, sv, a, text_content=ANSWER)  # version 2
+    body = {"version": 1, "scores": {"c1": 6, "c2": 4}}
+    r = await client.post(f"{API}/submissions/{sub['id']}/grade", json=body, headers=gv)
+    assert (r.status_code, r.json()["error"]["code"]) == (409, "STALE_VERSION")
+    mine = (await client.get(f"{API}/assignments/{a['id']}", headers=sv)).json()["my_submission"]
+    assert (mine["status"], mine["version"], mine["final_total"]) == ("submitted", 2, None)
+    r = await client.post(f"{API}/submissions/{sub['id']}/grade", json={**body, "version": 2}, headers=gv)
+    assert (r.status_code, r.json()["final_total"]) == (200, 10.0)
+
+
+async def test_double_click_first_submit_keeps_one_row(client, db):
+    import asyncio
+
+    _, sv, _, _, a = await _setup(client)
+    url = f"{API}/assignments/{a['id']}/submission"
+    r1, r2 = await asyncio.gather(
+        client.put(url, json={"text_content": "lần một"}, headers=sv),
+        client.put(url, json={"text_content": "lần hai"}, headers=sv),
+    )
+    assert (r1.status_code, r2.status_code) == (200, 200), (r1.text, r2.text)
+    assert r1.json()["id"] == r2.json()["id"]
+    assert sorted([r1.json()["version"], r2.json()["version"]]) == [1, 2]
+
+
+async def test_timed_out_grading_job_marks_ai_failed(client, db, storage, hub, monkeypatch):
+    """Job quá thời gian bị hủy giữa lúc chờ AI: bài không kẹt ở "AI đang chấm"."""
+    import asyncio
+
+    gv, sv, _, _, a = await _setup(client)
+    sub = await _submit(client, sv, a, text_content=ANSWER)
+    monkeypatch.setitem(JOB_TIMEOUTS, "grade_submission", 2)  # handler bị hủy sau 1 giây
+
+    class Hang(FakeLLMProvider):
+        async def generate(self, prompt, **kw):
+            await asyncio.sleep(30)
+
+    await grade_submission(_ctx(storage, hub, Hang()), str((await _job(db, sub["id"], 1)).id))
+    job = await _job(db, sub["id"], 1)
+    assert job.status == JobStatus.failed and job.error_msg.startswith("Quá thời gian xử lý")
+    detail = (await client.get(f"{API}/submissions/{sub['id']}", headers=gv)).json()
+    assert detail["status"] == "ai_failed" and detail["ai_error"].startswith(AI_ERROR)
+    teacher_id = (await client.get(f"{API}/me", headers=gv)).json()["id"]
+    assert await _kinds(db, teacher_id) == ["submission_ready"]
+
+
+async def test_sweeper_fails_stale_grading_job_and_submission(client, db):
+    """Worker chết giữa chừng: sweeper chốt job failed và bài chuyển ai_failed, giảng viên chấm tay được."""
+    gv, sv, _, _, a = await _setup(client)
+    sub = await _submit(client, sv, a, text_content=ANSWER)
+    old = utcnow() - timedelta(seconds=JOB_TIMEOUTS["grade_submission"]) - timedelta(minutes=6)
+    await db.execute(
+        update(Job)
+        .where(Job.ref_id == uuid.UUID(sub["id"]))
+        .values(status=JobStatus.processing, started_at=old)
+    )
+    await db.commit()
+    assert await sweep_stale_jobs({}) == 1
+    detail = (await client.get(f"{API}/submissions/{sub['id']}", headers=gv)).json()
+    assert detail["status"] == "ai_failed" and "Worker bị gián đoạn" in detail["ai_error"]
+
+
+async def test_cannot_delete_lesson_with_submissions(client, db):
+    gv, sv, _, _, a = await _setup(client)
+    await _submit(client, sv, a, text_content=ANSWER)
+    r = await client.delete(f"{API}/lessons/{a['lesson_id']}", headers=gv)
+    assert (r.status_code, r.json()["error"]["code"]) == (409, "INVALID_STATE")
+    assert "bài nộp" in r.json()["error"]["message"]
+
+
+def test_nan_score_from_ai_is_rejected():
+    import pytest
+    from pydantic import ValidationError
+
+    raw = (
+        '{"scores": [{"key": "c1", "score": NaN, "justification": "", "evidence_quote": ""}], "feedback": ""}'
+    )
+    with pytest.raises(ValidationError):
+        GradeDraft.model_validate_json(raw)
```

```powershell
cd backend
uv run pytest tests/test_assignments.py -q    # 8 failed, 8 passed
```

- [x] **Bước 2: Bài nộp không kẹt "AI đang chấm" (lỗi 1, 4).** `fail_unfinished` không commit: nó chạy trong cùng transaction với việc chốt job failed.

```diff
--- a/backend/app/modules/assignment/grading.py
+++ b/backend/app/modules/assignment/grading.py
@@ -13,9 +13,9 @@ import unicodedata
 import uuid
 
 import pymupdf
-from pydantic import BaseModel
+from pydantic import BaseModel, Field
 from sqlalchemy import select, update
-from sqlalchemy.ext.asyncio import async_sessionmaker
+from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
 
 from app.ai.llm_client import LLMClient, LLMOutputError
 from app.ai.prompts import load_prompt
@@ -42,7 +42,9 @@ class GradingError(Exception):
 
 class _CriterionDraft(BaseModel):
     key: str
-    score: float
+    score: float = Field(
+        allow_inf_nan=False
+    )  # NaN/Infinity coi như output sai (thử lại), không ghi được vào JSONB
     justification: str
     evidence_quote: str
 
@@ -241,3 +243,42 @@ async def _finish(
     if hub is not None:
         await inbox.publish(hub, notified)
     return True
+
+
+async def fail_unfinished(db: AsyncSession, refs: list[tuple[uuid.UUID, int]], reason: str) -> int:
+    """Job grade_submission bị hủy vì quá thời gian hoặc bị sweeper chốt failed (worker chết, không vào được hàng
+    đợi): bài của đúng version đó đang chờ AI thì chuyển ai_failed và báo giảng viên, để không kẹt "AI đang chấm"
+    mãi. Chưa commit: caller commit cùng transaction với job. Trả số bài đã chuyển."""
+    failed = 0
+    for submission_id, version in refs:
+        assignment_id = await db.scalar(
+            update(Submission)
+            .where(
+                Submission.id == submission_id,
+                Submission.version == version,
+                Submission.status == SubmissionStatus.submitted,
+            )
+            .values(status=SubmissionStatus.ai_failed, ai_error=f"{AI_ERROR} ({reason})"[:500])
+            .returning(Submission.assignment_id)
+        )
+        if assignment_id is None:
+            continue
+        assignment, course = (
+            await db.execute(
+                select(Assignment, Course)
+                .join(Lesson, Lesson.id == Assignment.lesson_id)
+                .join(Section, Section.id == Lesson.section_id)
+                .join(Course, Course.id == Section.course_id)
+                .where(Assignment.id == assignment_id)
+            )
+        ).one()
+        inbox.add(
+            db,
+            [course.teacher_id],
+            NotificationKind.submission_ready,
+            f"AI không chấm được một bài nộp: {assignment.title}",
+            teacher_link(course, assignment, submission_id),
+            reason,
+        )
+        failed += 1
+    return failed
```

```diff
--- a/backend/app/worker/tasks.py
+++ b/backend/app/worker/tasks.py
@@ -13,6 +13,7 @@ from app.core.db import SessionLocal
 from app.core.storage import get_storage
 from app.core.time import utcnow
 from app.ingestion.pipeline import error_text, ingest_pdf_source
+from app.modules.assignment.grading import fail_unfinished as fail_unfinished_grading
 from app.modules.assignment.grading import grade_submission as run_grading
 from app.modules.courses.models import Course, Lesson, Section
 from app.modules.inbox import service as inbox
@@ -56,6 +57,8 @@ PENDING_JOB_ERROR = "Không đưa được job vào hàng đợi"
 # quiz_gen (ref_id = lessons.id) không cần: câu hỏi chỉ được ghi ở commit cuối cùng với job done, nên job bị
 # sweeper chốt failed không để lại dữ liệu dở dang nào.
 SOURCE_JOB_TYPES = frozenset({"ingest_pdf"})
+# grade_submission (ref_id = submissions.id, ref_version = version): bài nộp còn chờ AI chuyển ai_failed.
+GRADE_JOB_TYPE = "grade_submission"
 # quiz_gen: lỗi nghiệp vụ (QuizGenerationError, vd. NO_CHUNKS_ERROR) ghi nguyên văn vào job; lỗi khác
 # (LLM/hạ tầng) ghi thông báo chung này, chi tiết nằm trong log.
 QUIZ_GEN_ERROR = "Không sinh được câu hỏi do lỗi hệ thống hoặc dịch vụ AI, vui lòng thử lại sau"
@@ -370,16 +373,20 @@ async def grade_submission(ctx: dict, job_id: str) -> None:
 
 async def _fail_jobs(db, jobs_where, error: str, now) -> int:
     """Chuyển các job khớp điều kiện sang failed; source tương ứng (loại ingest_*) còn pending/processing
-    cũng failed cùng lỗi. Chưa commit — caller commit để job và source đổi trạng thái trong cùng transaction."""
+    cũng failed cùng lỗi, bài nộp đang chờ AI (grade_submission) chuyển ai_failed. Chưa commit — caller commit
+    để job, source và bài nộp đổi trạng thái trong cùng transaction."""
     rows = (
         await db.execute(
             update(Job)
             .where(*jobs_where)
             .values(status=JobStatus.failed, error_msg=error, finished_at=now)
-            .returning(Job.type, Job.ref_id)
+            .returning(Job.type, Job.ref_id, Job.ref_version)
         )
     ).all()
-    source_ids = [ref_id for type_, ref_id in rows if type_ in SOURCE_JOB_TYPES]
+    grading = [(ref_id, ref_version) for type_, ref_id, ref_version in rows if type_ == GRADE_JOB_TYPE]
+    if grading:
+        await fail_unfinished_grading(db, grading, error)
+    source_ids = [ref_id for type_, ref_id, _ in rows if type_ in SOURCE_JOB_TYPES]
     if source_ids:
         await db.execute(
             update(Source)
```

- [x] **Bước 3: Xác nhận điểm theo version, nộp lần đầu không lỗi khi bấm đúp (lỗi 2).**

```diff
--- a/backend/app/modules/assignment/schemas.py
+++ b/backend/app/modules/assignment/schemas.py
@@ -185,5 +185,8 @@ class SubmissionDetail(BaseModel):
 class GradeIn(BaseModel):
     model_config = ConfigDict(extra="forbid")
 
+    version: int = Field(
+        ge=1
+    )  # version của bài giảng viên đang xem; lệch với bản mới nhất → 409 STALE_VERSION
     scores: dict[str, float]  # đủ mọi tiêu chí của rubric, mỗi điểm trong 0..max_points
     feedback: str | None = Field(None, max_length=MAX_FEEDBACK)
```

```diff
--- a/backend/app/modules/assignment/service.py
+++ b/backend/app/modules/assignment/service.py
@@ -6,6 +6,7 @@ viên chấm: điểm cuối nằm ở final_scores / final_total. Học viên c
 import uuid
 
 from sqlalchemy import case, func, null, select, update
+from sqlalchemy.dialects.postgresql import insert as pg_insert
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from app.core.errors import AppError, not_found
@@ -268,33 +269,36 @@ async def submit(
         raise AppError("DEADLINE_PASSED", "Đã quá hạn nộp bài", 409)
     if data.asset_id is not None:
         await require_verified_asset(db, data.asset_id, user, AssetKind.submission)
-    sub = await db.scalar(
-        select(Submission)
-        .where(Submission.assignment_id == assignment.id, Submission.user_id == user.id)
-        .with_for_update()
-    )
     now = utcnow()
-    if sub is None:
-        sub = Submission(
+    # Lần nộp đầu: tạo sẵn dòng version 0 (bỏ qua nếu đã có). Hai lần nộp đầu gần như cùng lúc (bấm đúp) không
+    # đụng uq_submissions_assignment_user nữa: lần sau đợi lần trước commit rồi đi tiếp nhánh nộp lại.
+    await db.execute(
+        pg_insert(Submission)
+        .values(
+            id=uuid.uuid4(),
             assignment_id=assignment.id,
             user_id=user.id,
-            text_content=data.text_content,
-            asset_id=data.asset_id,
-            version=1,
+            version=0,
             submitted_at=now,
             status=SubmissionStatus.submitted,
         )
-        db.add(sub)
-    else:
-        if sub.status == SubmissionStatus.graded:
-            raise AppError("ALREADY_GRADED", "Bài đã được giảng viên chấm, không nộp lại được", 409)
-        sub.text_content = data.text_content
-        sub.asset_id = data.asset_id
-        sub.version += 1
-        sub.submitted_at = now
-        sub.status = SubmissionStatus.submitted
-        sub.ai_result = None
-        sub.ai_error = None
+        .on_conflict_do_nothing(constraint="uq_submissions_assignment_user")
+    )
+    sub = await db.scalar(
+        select(Submission)
+        .where(Submission.assignment_id == assignment.id, Submission.user_id == user.id)
+        .with_for_update()
+        .execution_options(populate_existing=True)
+    )
+    if sub.status == SubmissionStatus.graded:
+        raise AppError("ALREADY_GRADED", "Bài đã được giảng viên chấm, không nộp lại được", 409)
+    sub.text_content = data.text_content
+    sub.asset_id = data.asset_id
+    sub.version += 1
+    sub.submitted_at = now
+    sub.status = SubmissionStatus.submitted
+    sub.ai_result = None
+    sub.ai_error = None
     await db.flush()
     await create_and_enqueue(db, queue, GRADE_JOB, sub.id, sub.version, created_by=user.id)
     return await _my_submission(db, sub)
@@ -398,7 +402,13 @@ async def grade(
     data: GradeIn,
     hub: NotificationHub | None = None,
 ) -> None:
-    """Giảng viên xác nhận điểm (chấm lần đầu hoặc sửa điểm đã chấm). Không đụng tới ai_result."""
+    """Giảng viên xác nhận điểm (chấm lần đầu hoặc sửa điểm đã chấm). Không đụng tới ai_result.
+
+    Khóa dòng bài nộp và yêu cầu đúng version giảng viên đang xem: học viên nộp lại giữa lúc giảng viên chấm thì
+    trả 409 STALE_VERSION thay vì ghi điểm của bản cũ vào bản mới."""
+    await db.refresh(sub, with_for_update=True)
+    if sub.version != data.version:
+        raise AppError("STALE_VERSION", "Học viên vừa nộp lại bài. Hãy xem bản mới rồi chấm lại", 409)
     keys = {r["key"]: r for r in assignment.rubric}
     if set(data.scores) != set(keys):
         raise AppError("INVALID_SCORES", "Cần chấm đủ và đúng các tiêu chí của rubric", 422)
```

- [x] **Bước 4: Chặn xóa bài học / chương đã có bài nộp (lỗi 3).**

```diff
--- a/backend/app/modules/courses/service.py
+++ b/backend/app/modules/courses/service.py
@@ -92,12 +92,14 @@ async def _ensure_no_student_work(
 ) -> None:
     """Chặn xóa (409) chỉ khi phần bị xóa (cascade) kéo theo dữ liệu của HỌC VIÊN:
     - bất kỳ lượt làm quiz nào trên các bài trong phạm vi;
+    - bất kỳ bài nộp nào cho bài tập của các bài trong phạm vi (B5);
     - phiên hỏi Tutor có tin nhắn của người không phải staff của khóa (bỏ qua chủ khóa và admin: phiên xem thử);
     - xóa khóa: có ít nhất một lượt đăng ký; xóa chương/bài: có tiến độ học của học viên đang đăng ký khóa.
     Quiz (kể cả đã xuất bản nhưng chưa ai làm), câu hỏi, tài liệu và phiên xem thử của staff vẫn bị xóa theo
     cascade như trước. Khóa FOR UPDATE dòng khóa học (khi xóa khóa) và các bài/quiz trong phạm vi: lệnh tạo
     lượt làm, đăng ký, tiến độ hay phiên Tutor (khóa ngoại tới các dòng này) phải đợi tới khi xóa xong, nên dữ liệu
     học viên không thể chen vào giữa lúc kiểm tra và lúc xóa."""
+    from app.modules.assignment.models import Assignment, Submission
     from app.modules.enrollment.models import Enrollment, LessonProgress
     from app.modules.quiz.models import Quiz, QuizAttempt
     from app.modules.tutor.models import ChatMessage, ChatSession
@@ -115,6 +117,17 @@ async def _ensure_no_student_work(
 
     if quiz_ids and await exists(select(QuizAttempt.id).where(QuizAttempt.quiz_id.in_(quiz_ids))):
         raise AppError("INVALID_STATE", f"Không xóa được: {what} đã có bài làm quiz của học viên", 409)
+    assignment_ids = list(
+        (
+            await db.scalars(
+                select(Assignment.id).where(Assignment.lesson_id.in_(lesson_ids)).with_for_update()
+            )
+        ).all()
+    )
+    if assignment_ids and await exists(
+        select(Submission.id).where(Submission.assignment_id.in_(assignment_ids))
+    ):
+        raise AppError("INVALID_STATE", f"Không xóa được: {what} đã có bài nộp của học viên", 409)
     student_chat = (
         select(ChatSession.id)
         .join(User, User.id == ChatSession.user_id)
```

```diff
--- a/backend/.importlinter
+++ b/backend/.importlinter
@@ -27,9 +27,11 @@ forbidden_modules =
     app.modules.discussion
     app.modules.assignment
 ignore_imports =
-    # Chặn xóa khóa / chương / bài khi học viên đã làm quiz hoặc hỏi AI Tutor: chỉ ĐỌC bảng, không gọi service
+    # Chặn xóa khóa / chương / bài khi học viên đã làm quiz, hỏi AI Tutor hoặc nộp bài tập: chỉ ĐỌC bảng,
+    # không gọi service
     app.modules.courses.service -> app.modules.quiz.models
     app.modules.courses.service -> app.modules.tutor.models
+    app.modules.courses.service -> app.modules.assignment.models
 
 [importlinter:contract:notify-is-leaf]
 name = notify (hộp thư đi email) không phụ thuộc module nào khác
@@ -66,6 +68,7 @@ ignore_imports =
     # Cùng ngoại lệ chặn xóa ở trên (đường vòng qua courses.service, chỉ đọc bảng)
     app.modules.courses.service -> app.modules.quiz.models
     app.modules.courses.service -> app.modules.tutor.models
+    app.modules.courses.service -> app.modules.assignment.models
 
 [importlinter:contract:core-and-ai-below-features]
 name = core, lớp AI và ingestion không phụ thuộc phần tính năng
```

- [x] **Bước 5: Chạy kiểm tra, commit**

```powershell
uv run pytest -q                                      # 826 passed
uv run ruff check . ; uv run ruff format --check .
uv run lint-imports                                   # 6 contracts KEPT
cd ..
git add backend
git commit -m "fix(api): bài nộp không kẹt khi job chấm quá giờ/treo, xác nhận điểm theo version, chặn xóa bài học có bài nộp, điểm NaN từ AI là output sai"
```

Sau commit này frontend cũ chưa gửi `version` nên tạm thời không xác nhận điểm được (422). Task 2 sửa phần đó.

---

## Task 2: Frontend: màn hình chấm và hộp tạo/sửa bài tập (lỗi 5, 6 và lỗi nhỏ)

**Files:**
- Regenerate: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`
- Modify: `frontend/src/lib/assignments.ts`, `frontend/src/components/teach/submission-review.tsx`, `frontend/src/components/teach/assignment-manager.tsx`, `frontend/src/components/teach/submission-review.test.tsx`, `frontend/src/components/teach/assignment-manager.test.tsx`, `frontend/e2e/assignments.spec.ts`

- [ ] **Bước 1: Sinh lại kiểu API** (`GradeIn` có thêm `version: number`)

```powershell
cd frontend
npm run gen:api
```

- [ ] **Bước 2: Test (sẽ fail).** Màn hình chấm:
  - gửi `version`;
  - AI chấm xong khi đang gõ thì giữ phần đã gõ;
  - chưa gõ thì vẫn điền gợi ý AI;
  - bài đã chấm không lấy lại nhận xét AI;
  - gặp 409 thì báo lỗi và tải bản mới.

  Hộp sửa bài tập: không gửi lại hạn nộp; điểm tối đa trống thì báo lỗi tiếng Việt. E2E gửi thêm `version`.

```diff
--- a/frontend/src/components/teach/submission-review.test.tsx
+++ b/frontend/src/components/teach/submission-review.test.tsx
@@ -2,6 +2,7 @@ import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
 import { render, screen, waitFor } from "@testing-library/react";
 import userEvent from "@testing-library/user-event";
 import { http, HttpResponse } from "msw";
+import { toast } from "sonner";
 import { describe, expect, it, vi } from "vitest";
 import { assignment } from "@/components/assignment/fixtures";
 import { api as url, server } from "@/test/msw";
@@ -45,8 +46,9 @@ const detail = (over: Record<string, unknown> = {}) => ({
   ...over,
 });
 
-function setup() {
+function setup(first: ReturnType<typeof detail> = detail()) {
   const graded: unknown[] = [];
+  const state = { detail: first, gradeStatus: 200 };
   server.use(
     http.get(url("/assignments/as-1"), () => HttpResponse.json(assignment({ submission_count: 1, to_review: 1 }))),
     http.get(url("/assignments/as-1/submissions"), () =>
@@ -57,9 +59,14 @@ function setup() {
         size: 20,
       }),
     ),
-    http.get(url("/submissions/sub-1"), () => HttpResponse.json(detail())),
+    http.get(url("/submissions/sub-1"), () => HttpResponse.json(state.detail)),
     http.post(url("/submissions/sub-1/grade"), async ({ request }) => {
       graded.push(await request.json());
+      if (state.gradeStatus === 409)
+        return HttpResponse.json(
+          { error: { code: "STALE_VERSION", message: "Học viên vừa nộp lại bài. Hãy xem bản mới rồi chấm lại" } },
+          { status: 409 },
+        );
       return HttpResponse.json(detail({ status: "graded", final_scores: { c1: 5, c2: 3 }, final_total: 8 }));
     }),
   );
@@ -69,7 +76,7 @@ function setup() {
       <SubmissionReview slug="khoa" lessonId="l1" assignmentId="as-1" />
     </QueryClientProvider>,
   );
-  return { graded };
+  return { graded, state, qc };
 }
 
 describe("SubmissionReview", () => {
@@ -91,7 +98,50 @@ describe("SubmissionReview", () => {
     await user.clear(c1);
     await user.type(c1, "5");
     await user.click(screen.getByRole("button", { name: "Xác nhận điểm" }));
-    await waitFor(() => expect(graded).toEqual([{ scores: { c1: 5, c2: 3 }, feedback: "Bài khá tốt." }]));
+    await waitFor(() => expect(graded).toEqual([{ version: 1, scores: { c1: 5, c2: 3 }, feedback: "Bài khá tốt." }]));
     expect(await screen.findByRole("button", { name: "Cập nhật điểm" })).toBeInTheDocument();
   });
+
+  it("AI chấm xong trong lúc giảng viên đang chấm tay: giữ nguyên điểm và nhận xét đã gõ", async () => {
+    const user = userEvent.setup();
+    const { state, qc } = setup(detail({ status: "submitted", ai_result: null }));
+    const c1 = await screen.findByLabelText("Điểm Đúng khái niệm");
+    expect(c1).toHaveValue(null);
+    await user.type(c1, "2");
+    await user.type(screen.getByLabelText(/Nhận xét cho học viên/), "Tự chấm");
+    state.detail = detail();
+    await qc.refetchQueries();
+    expect(await screen.findByText("AI gợi ý 4/6")).toBeInTheDocument();
+    expect(screen.getByLabelText("Điểm Đúng khái niệm")).toHaveValue(2);
+    expect(screen.getByLabelText("Điểm Trình bày")).toHaveValue(null);
+    expect(screen.getByLabelText(/Nhận xét cho học viên/)).toHaveValue("Tự chấm");
+  });
+
+  it("chưa gõ gì thì gợi ý AI tới sau vẫn được điền sẵn", async () => {
+    const { state, qc } = setup(detail({ status: "submitted", ai_result: null }));
+    expect(await screen.findByLabelText("Điểm Đúng khái niệm")).toHaveValue(null);
+    state.detail = detail();
+    await qc.refetchQueries();
+    await waitFor(() => expect(screen.getByLabelText("Điểm Đúng khái niệm")).toHaveValue(4));
+    expect(screen.getByLabelText(/Nhận xét cho học viên/)).toHaveValue("Bài khá tốt.");
+  });
+
+  it("bài đã chấm mà giảng viên bỏ nhận xét: không lấy lại nhận xét AI", async () => {
+    setup(detail({ status: "graded", final_scores: { c1: 5, c2: 3 }, final_total: 8, teacher_feedback: null }));
+    expect(await screen.findByLabelText("Điểm Đúng khái niệm")).toHaveValue(5);
+    expect(screen.getByLabelText(/Nhận xét cho học viên/)).toHaveValue("");
+    expect(screen.getByRole("button", { name: "Cập nhật điểm" })).toBeInTheDocument();
+  });
+
+  it("học viên vừa nộp lại: báo lỗi và tải bản mới", async () => {
+    const user = userEvent.setup();
+    const { state } = setup();
+    await screen.findByLabelText("Điểm Đúng khái niệm");
+    state.gradeStatus = 409;
+    state.detail = detail({ version: 2, status: "submitted", ai_result: null, text_content: "Bản nộp lại" });
+    await user.click(screen.getByRole("button", { name: "Xác nhận điểm" }));
+    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Học viên vừa nộp lại bài. Hãy xem bản mới rồi chấm lại"));
+    expect(await screen.findByText("Bản nộp lại")).toBeInTheDocument();
+    expect(screen.getByText(/lần nộp thứ 2/)).toBeInTheDocument();
+  });
 });
```

```diff
--- a/frontend/src/components/teach/assignment-manager.test.tsx
+++ b/frontend/src/components/teach/assignment-manager.test.tsx
@@ -11,6 +11,7 @@ vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), err
 
 function setup(items: ReturnType<typeof assignment>[]) {
   const created: unknown[] = [];
+  const updated: unknown[] = [];
   const published: string[] = [];
   server.use(
     http.get(url("/assignments"), () => HttpResponse.json({ items, total: items.length, page: 1, size: 50 })),
@@ -18,6 +19,10 @@ function setup(items: ReturnType<typeof assignment>[]) {
       created.push(await request.json());
       return HttpResponse.json(assignment({ status: "draft" }), { status: 201 });
     }),
+    http.patch(url("/assignments/:id"), async ({ request }) => {
+      updated.push(await request.json());
+      return HttpResponse.json(assignment());
+    }),
     http.post(url("/assignments/:id/publish"), ({ params }) => {
       published.push(params.id as string);
       return HttpResponse.json(assignment());
@@ -29,7 +34,7 @@ function setup(items: ReturnType<typeof assignment>[]) {
       <AssignmentManager slug="khoa" lessonId="l1" />
     </QueryClientProvider>,
   );
-  return { created, published };
+  return { created, updated, published };
 }
 
 describe("AssignmentManager", () => {
@@ -71,4 +76,29 @@ describe("AssignmentManager", () => {
     await user.click(within(confirm).getByRole("button", { name: "Xuất bản" }));
     await waitFor(() => expect(published).toEqual(["as-1"]));
   });
+
+  it("sửa bài tập: không đổi hạn nộp thì không gửi lại (giữ phần giây); điểm tối đa trống báo lỗi tiếng Việt", async () => {
+    const user = userEvent.setup();
+    const { updated } = setup([assignment({ due_at: "2026-11-01T16:59:59Z", submission_count: 0, to_review: 0 })]);
+    await user.click(await screen.findByRole("button", { name: /Thao tác với bài tập/ }));
+    await user.click(await screen.findByRole("menuitem", { name: "Sửa" }));
+    const dialog = await screen.findByRole("dialog");
+    const points = within(dialog).getAllByLabelText("Điểm tối đa")[0];
+    await user.clear(points);
+    expect(points).toHaveValue(null);
+    await user.click(within(dialog).getByRole("button", { name: "Lưu" }));
+    expect(within(dialog).getByRole("alert")).toHaveTextContent("Điểm tối đa mỗi tiêu chí là số nguyên từ 1 đến 100");
+    await user.type(points, "5");
+    await user.type(within(dialog).getByLabelText("Tiêu đề"), " (sửa)");
+    await user.click(within(dialog).getByRole("button", { name: "Lưu" }));
+    await waitFor(() => expect(updated).toHaveLength(1));
+    expect(updated[0]).not.toHaveProperty("due_at");
+    expect(updated[0]).toMatchObject({
+      title: "Bài tập tìm kiếm nhị phân (sửa)",
+      rubric: [
+        { criterion: "Đúng khái niệm", max_points: 5, description: "Nêu đúng điều kiện" },
+        { criterion: "Trình bày", max_points: 4, description: "" },
+      ],
+    });
+  });
 });
```

```diff
--- a/frontend/e2e/assignments.spec.ts
+++ b/frontend/e2e/assignments.spec.ts
@@ -143,6 +143,7 @@ test.describe("bài tập (B5)", () => {
     await panel.getByRole("button", { name: "Xác nhận điểm" }).click();
     await expect(panel.getByRole("button", { name: "Cập nhật điểm" })).toBeVisible();
     expect(graded).toEqual({
+      version: 1,
       scores: { c1: 5.5, c2: 4 },
       feedback: "Bài làm đúng hướng, nên trình bày rõ bước rút gọn.",
     });
```

```powershell
npx vitest run src/components/teach    # 4 test mới fail + test cũ "điền sẵn điểm..." fail (chưa gửi version)
```

- [ ] **Bước 3: Sửa.** Gợi ý AI tới sau được "điều chỉnh state trong lúc render" (so `ai_result` với bản đã thấy) thay vì `useEffect`. TanStack Query giữ nguyên tham chiếu khi dữ liệu không đổi, nên lần tải lại 4 giây không kích hoạt nhầm.

```diff
--- a/frontend/src/lib/assignments.ts
+++ b/frontend/src/lib/assignments.ts
@@ -2,6 +2,7 @@
 
 import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
 import { api, unwrap } from "@/lib/api/client";
+import { ApiError } from "@/lib/api/errors";
 import type { components } from "@/lib/api/schema";
 
 export type Assignment = components["schemas"]["AssignmentOut"];
@@ -127,6 +128,10 @@ export function useGradeMutations(submissionId: string) {
         qc.setQueryData(assignmentKeys.submission(submissionId), detail);
         void qc.invalidateQueries({ queryKey: assignmentKeys.all });
       },
+      // học viên vừa nộp lại: tải bản mới để giảng viên xem rồi chấm lại
+      onError: (err) => {
+        if (err instanceof ApiError && err.code === "STALE_VERSION") refresh();
+      },
     }),
     regrade: useMutation({
       mutationFn: () => unwrap(api.POST("/api/v1/submissions/{submission_id}/regrade", path)),
```

```diff
--- a/frontend/src/components/teach/submission-review.tsx
+++ b/frontend/src/components/teach/submission-review.tsx
@@ -9,7 +9,7 @@ import { EmptyState, ErrorState } from "@/components/app/states";
 import { Button } from "@/components/ui/button";
 import { Field, Input, Textarea } from "@/components/ui/input";
 import { Badge, Skeleton } from "@/components/ui/misc";
-import { errorMessage } from "@/lib/api/errors";
+import { ApiError, errorMessage } from "@/lib/api/errors";
 import {
   type Assignment,
   SUBMISSION_STATUS_LABEL,
@@ -62,7 +62,9 @@ export function SubmissionReview({ slug, lessonId, assignmentId }: { slug: strin
       >
         <ArrowLeft className="size-4" aria-hidden /> Bài tập của bài
       </Link>
-      {assignment.data ? (
+      {assignment.isError ? (
+        <ErrorState error={assignment.error} onRetry={() => assignment.refetch()} />
+      ) : assignment.data ? (
         <div>
           <h2 className="text-lg font-semibold">{assignment.data.title}</h2>
           <p className="text-sm text-muted-foreground">
@@ -142,6 +144,8 @@ export function SubmissionReview({ slug, lessonId, assignmentId }: { slug: strin
         </div>
         {selected && assignment.data ? (
           <SubmissionPanel id={selected} assignment={assignment.data} />
+        ) : selected && assignment.isPending ? (
+          <Skeleton className="h-96 w-full" />
         ) : (
           <EmptyState icon={FileText} title="Chọn một bài nộp ở danh sách để xem và chấm." />
         )}
@@ -155,6 +159,8 @@ function SubmissionPanel({ id, assignment }: { id: string; assignment: Assignmen
   if (detail.isPending) return <Skeleton className="h-96 w-full" />;
   if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
   const d = detail.data;
+  if (d.assignment_id !== assignment.id)
+    return <EmptyState icon={FileText} title="Bài nộp này thuộc bài tập khác. Chọn một bài ở danh sách." />;
   return (
     <section aria-label={`Bài nộp của ${d.student_name}`} className="space-y-4 rounded-lg border bg-surface p-4 md:p-6">
       <div className="flex flex-wrap items-center justify-between gap-2">
@@ -191,20 +197,42 @@ function SubmissionPanel({ id, assignment }: { id: string; assignment: Assignmen
           <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {d.ai_error ?? "AI không chấm được bài này."}
         </p>
       ) : null}
-      <GradeForm key={`${d.id}-${d.version}-${d.status}`} detail={d} assignment={assignment} />
+      {/* Không gắn key theo trạng thái: AI chấm xong trong lúc giảng viên đang gõ thì không được dựng lại form */}
+      <GradeForm key={`${d.id}-${d.version}`} detail={d} assignment={assignment} />
     </section>
   );
 }
 
+/** Giá trị điền sẵn: bài đã chấm lấy điểm và nhận xét của giảng viên (nhận xét đã xóa thì để trống, không lấy lại
+ * bản AI soạn); chưa chấm thì lấy gợi ý của AI nếu có. */
+function prefill(detail: SubmissionDetail, assignment: Assignment) {
+  const final = detail.final_scores;
+  const ai = detail.ai_result;
+  return {
+    scores: Object.fromEntries(
+      assignment.rubric.map((r) => [r.key, String((final ? final[r.key] : ai?.scores[r.key]?.score) ?? "")]),
+    ) as Record<string, string>,
+    feedback: final ? (detail.teacher_feedback ?? "") : (ai?.feedback ?? ""),
+  };
+}
+
 function GradeForm({ detail, assignment }: { detail: SubmissionDetail; assignment: Assignment }) {
   const mut = useGradeMutations(detail.id);
   const ai = detail.ai_result;
-  const [scores, setScores] = React.useState<Record<string, string>>(() =>
-    Object.fromEntries(
-      assignment.rubric.map((r) => [r.key, String(detail.final_scores?.[r.key] ?? ai?.scores[r.key]?.score ?? "")]),
-    ),
-  );
-  const [feedback, setFeedback] = React.useState(detail.teacher_feedback ?? ai?.feedback ?? "");
+  const [scores, setScores] = React.useState(() => prefill(detail, assignment).scores);
+  const [feedback, setFeedback] = React.useState(() => prefill(detail, assignment).feedback);
+  const [touched, setTouched] = React.useState(false);
+  const [seenAi, setSeenAi] = React.useState(ai);
+  // Gợi ý AI tới khi form đang mở (AI chấm xong / chấm lại): chỉ điền vào khi giảng viên chưa gõ gì và bài chưa
+  // được chấm; đã gõ thì giữ nguyên phần của giảng viên (khối "AI gợi ý" bên dưới vẫn hiện điểm AI để so).
+  if (ai !== seenAi) {
+    setSeenAi(ai);
+    if (ai && !touched && !detail.final_scores) {
+      const next = prefill(detail, assignment);
+      setScores(next.scores);
+      setFeedback(next.feedback);
+    }
+  }
   const [error, setError] = React.useState<string | null>(null);
   const total = assignment.rubric.reduce((n, r) => n + (Number(scores[r.key]) || 0), 0);
 
@@ -220,10 +248,12 @@ function GradeForm({ detail, assignment }: { detail: SubmissionDetail; assignmen
     }
     setError(null);
     try {
-      await mut.grade.mutateAsync({ scores: parsed, feedback: feedback.trim() || null });
+      await mut.grade.mutateAsync({ version: detail.version, scores: parsed, feedback: feedback.trim() || null });
       toast.success("Đã xác nhận điểm, học viên được thông báo");
     } catch (err) {
-      setError(errorMessage(err));
+      // bản mới của học viên được tải lại và form dựng lại theo bản đó, nên báo bằng toast
+      if (err instanceof ApiError && err.code === "STALE_VERSION") toast.error(errorMessage(err));
+      else setError(errorMessage(err));
     }
   }
 
@@ -251,7 +281,10 @@ function GradeForm({ detail, assignment }: { detail: SubmissionDetail; assignmen
                     step={0.25}
                     className="w-24"
                     value={scores[r.key]}
-                    onChange={(e) => setScores((cur) => ({ ...cur, [r.key]: e.target.value }))}
+                    onChange={(e) => {
+                      setTouched(true);
+                      setScores((cur) => ({ ...cur, [r.key]: e.target.value }));
+                    }}
                   />
                 </Field>
               </div>
@@ -277,7 +310,15 @@ function GradeForm({ detail, assignment }: { detail: SubmissionDetail; assignmen
         })}
       </ol>
       <Field id="teacher-feedback" label="Nhận xét cho học viên" hint={ai ? "AI soạn sẵn từ bài làm, bạn sửa lại cho đúng ý" : undefined}>
-        <Textarea rows={4} maxLength={5000} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
+        <Textarea
+          rows={4}
+          maxLength={5000}
+          value={feedback}
+          onChange={(e) => {
+            setTouched(true);
+            setFeedback(e.target.value);
+          }}
+        />
       </Field>
       {error ? (
         <p role="alert" className="text-sm text-destructive">
```

```diff
--- a/frontend/src/components/teach/assignment-manager.tsx
+++ b/frontend/src/components/teach/assignment-manager.tsx
@@ -11,11 +11,13 @@ import { Field, Input, Textarea } from "@/components/ui/input";
 import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
 import { Badge, Skeleton } from "@/components/ui/misc";
 import { errorMessage } from "@/lib/api/errors";
-import { type Assignment, type RubricItemIn, useAssignmentMutations, useLessonAssignments } from "@/lib/assignments";
+import { type Assignment, useAssignmentMutations, useLessonAssignments } from "@/lib/assignments";
 import { formatDateTime, fromLocalInput, toLocalInput } from "@/lib/format";
 
 const MAX_CRITERIA = 8;
-const emptyCriterion = (): RubricItemIn => ({ criterion: "", max_points: 2, description: "" });
+/** Một dòng rubric trong form; điểm tối đa giữ dạng chuỗi để xóa trắng ô được khi đang gõ. */
+type CriterionDraft = { criterion: string; max_points: string; description: string };
+const emptyCriterion = (): CriterionDraft => ({ criterion: "", max_points: "2", description: "" });
 
 /** Bài tập của một bài (B5): tạo/sửa (đề bài, hạn nộp, rubric), xuất bản có xác nhận, xem bài nộp để chấm. */
 export function AssignmentManager({ slug, lessonId }: { slug: string; lessonId: string }) {
@@ -139,36 +141,55 @@ function AssignmentDialog({ lessonId, assignment, onClose }: { lessonId: string;
   const locked = !!assignment?.submission_count; // đã có bài nộp: không đổi rubric được nữa
   const [title, setTitle] = React.useState(assignment?.title ?? "");
   const [instructions, setInstructions] = React.useState(assignment?.instructions ?? "");
-  const [due, setDue] = React.useState(assignment?.due_at ? toLocalInput(assignment.due_at) : "");
-  const [rubric, setRubric] = React.useState<RubricItemIn[]>(
+  const initialDue = assignment?.due_at ? toLocalInput(assignment.due_at) : "";
+  const [due, setDue] = React.useState(initialDue);
+  const [rubric, setRubric] = React.useState<CriterionDraft[]>(
     assignment
-      ? assignment.rubric.map(({ criterion, max_points, description }) => ({ criterion, max_points, description }))
+      ? assignment.rubric.map(({ criterion, max_points, description }) => ({
+          criterion,
+          max_points: String(max_points),
+          description: description ?? "",
+        }))
       : [emptyCriterion()],
   );
   const [error, setError] = React.useState<string | null>(null);
   const [pending, setPending] = React.useState(false);
   const total = rubric.reduce((n, r) => n + (Number(r.max_points) || 0), 0);
 
-  const setItem = (i: number, patch: Partial<RubricItemIn>) => setRubric((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
+  const setItem = (i: number, patch: Partial<CriterionDraft>) => setRubric((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
 
   async function submit(e: React.FormEvent) {
     e.preventDefault();
     if (!title.trim()) return setError("Nhập tiêu đề bài tập");
     if (!instructions.trim()) return setError("Nhập đề bài");
     if (rubric.some((r) => !r.criterion.trim())) return setError("Mỗi tiêu chí cần có tên");
-    if (rubric.some((r) => !Number.isInteger(Number(r.max_points)) || r.max_points < 1 || r.max_points > 100))
+    const points = rubric.map((r) => Number(r.max_points.trim() || NaN));
+    if (points.some((p) => !Number.isInteger(p) || p < 1 || p > 100))
       return setError("Điểm tối đa mỗi tiêu chí là số nguyên từ 1 đến 100");
     setPending(true);
     setError(null);
-    const body = {
-      title: title.trim(),
-      instructions: instructions.trim(),
-      due_at: due ? fromLocalInput(due) : null,
-      ...(locked ? {} : { rubric: rubric.map((r) => ({ ...r, criterion: r.criterion.trim(), max_points: Number(r.max_points) })) }),
-    };
+    const items = rubric.map((r, i) => ({ criterion: r.criterion.trim(), max_points: points[i], description: r.description }));
+    const dueAt = due ? fromLocalInput(due) : null;
     try {
-      if (assignment) await mut.update.mutateAsync({ id: assignment.id, body });
-      else await mut.create.mutateAsync({ lesson_id: lessonId, ...body, rubric: body.rubric! });
+      if (assignment)
+        await mut.update.mutateAsync({
+          id: assignment.id,
+          body: {
+            title: title.trim(),
+            instructions: instructions.trim(),
+            // chỉ gửi hạn nộp khi đã đổi: ô datetime-local bỏ phần giây, gửi lại sẽ làm 23:59:59 thành 23:59:00
+            ...(due !== initialDue ? { due_at: dueAt } : {}),
+            ...(locked ? {} : { rubric: items }),
+          },
+        });
+      else
+        await mut.create.mutateAsync({
+          lesson_id: lessonId,
+          title: title.trim(),
+          instructions: instructions.trim(),
+          due_at: dueAt,
+          rubric: items,
+        });
       toast.success(assignment ? "Đã lưu bài tập" : "Đã tạo bài tập (nháp)");
       onClose();
     } catch (err) {
@@ -184,7 +205,8 @@ function AssignmentDialog({ lessonId, assignment, onClose }: { lessonId: string;
         description="Bài tập ở dạng nháp cho tới khi bạn xuất bản. AI chấm gợi ý theo đúng rubric này."
         className="max-h-[90dvh] max-w-2xl overflow-y-auto"
       >
-        <form onSubmit={submit} className="space-y-4">
+        {/* noValidate: báo lỗi bằng câu tiếng Việt của mình thay vì bong bóng mặc định của trình duyệt */}
+        <form onSubmit={submit} noValidate className="space-y-4">
           <Field id="as-title" label="Tiêu đề">
             <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus />
           </Field>
@@ -213,7 +235,7 @@ function AssignmentDialog({ lessonId, assignment, onClose }: { lessonId: string;
                     max={100}
                     value={r.max_points}
                     disabled={locked}
-                    onChange={(e) => setItem(i, { max_points: Number(e.target.value) })}
+                    onChange={(e) => setItem(i, { max_points: e.target.value })}
                   />
                 </Field>
                 <Button
```

- [ ] **Bước 4: Chạy kiểm tra, commit**

```powershell
npx tsc --noEmit ; npx eslint .
npx vitest run                     # 196 pass
npx playwright test                # 107 pass + 1 bỏ qua có chủ ý
cd ..
git add -A frontend
git commit -m "fix(web): màn hình chấm không đè phần giảng viên đã gõ, gửi version khi xác nhận, sửa bài tập không làm lệch hạn nộp"
```

---

## Task 3: Cập nhật spec và bản đồ module

**Files:** Modify `docs/specs/2026-09-29-lms-ai-design.md`, `docs/architecture/modules.md`

- [ ] **Bước 1:** bảng API ghi `version` và 409 `STALE_VERSION` cho `POST /submissions/{id}/grade`; thêm dòng quyết định; `modules.md` ghi ngoại lệ đọc bảng bài tập.

```diff
--- a/docs/specs/2026-09-29-lms-ai-design.md
+++ b/docs/specs/2026-09-29-lms-ai-design.md
@@ -501,7 +501,7 @@ Mọi lời gọi LLM đều đi qua lớp này:
 | Tutor | `POST /tutor/sessions` · `GET /tutor/sessions?course_id=` (phiên của chính mình, phân trang) · `GET /tutor/availability?course_id=&lesson_id=` (`{available, ready_chunks, message, state, processing_docs, can_queue}`) · `POST /tutor/sessions/{id}/questions` → 202 (câu hỏi chờ khi tài liệu đang xử lý) · `GET /tutor/sessions/{id}/messages` · `POST /tutor/sessions/{id}/messages` (SSE, frontend đọc bằng `fetch` + `ReadableStream`) · `POST /tutor/messages/{id}/feedback` |
 | Câu hỏi | `POST /lessons/{id}/questions/generate` → 202 · `GET /lessons/{id}/questions?review_status=` · `PATCH /questions/{id}` |
 | Quiz | `POST /quizzes` · `GET /quizzes?lesson_id=` (phân trang) · `GET/PATCH/DELETE /quizzes/{id}` · `POST /quizzes/{id}/publish` · `POST /quizzes/{id}/attempts` (**không trả đáp án**) · `PUT /attempts/{id}/answers/{qid}` · `POST /attempts/{id}/submit {final_answers?}` · `GET /attempts/{id}/result` (chỉ khi `completed` hoặc `timed_out`) · `POST /attempts/{id}/answers/{qid}/explain` |
-| Assignment | `POST /assignments` · `GET /assignments?lesson_id=` · `GET/PATCH/DELETE /assignments/{id}` · `POST /assignments/{id}/publish` · `PUT /assignments/{id}/submission` · `GET /assignments/{id}/submissions` · `GET /submissions/{id}` · `POST /submissions/{id}/grade` · `POST /submissions/{id}/regrade` |
+| Assignment | `POST /assignments` · `GET /assignments?lesson_id=` · `GET/PATCH/DELETE /assignments/{id}` · `POST /assignments/{id}/publish` · `PUT /assignments/{id}/submission` · `GET /assignments/{id}/submissions` · `GET /submissions/{id}` · `POST /submissions/{id}/grade {version, scores, feedback}` (version lệch bản mới nhất → 409 `STALE_VERSION`) · `POST /submissions/{id}/regrade` |
 | Thảo luận | `GET/POST /lessons/{id}/comments` · `DELETE /comments/{id}` |
 | Thông báo | `GET /me/notifications` (kèm `unread`) · `GET /me/notifications/unread` · `POST /me/notifications/{id}/read` · `POST /me/notifications/read-all` · `GET /me/notifications/stream` (SSE, đọc bằng `fetch` có header Bearer nên không cần stream-token) |
 | Vận hành | `GET /api/v1/health` (tiến trình còn sống) · `GET /api/v1/ready` (DB, Redis, MinIO; `503` khi có phần lỗi) · `GET /metrics` (Prometheus, chỉ trong mạng nội bộ, Caddy không chuyển ra ngoài) |
@@ -776,3 +776,4 @@ Việc còn lại từ phần upload (Task 14):
 | 2026-10-19 | B4 thảo luận: bảng `lesson_comments` (gốc + trả lời một cấp, xóa mềm), ai vào được bài thì đọc và viết được; tác giả, giảng viên của khóa hoặc admin được xóa, người khác nhận 404; 30 bình luận/giờ/người. B6 thông báo: bảng `notifications` (trả lời bình luận, câu hỏi mới cho giảng viên, quiz mới xuất bản cho học viên đã đăng ký, tài liệu/câu hỏi AI xong hoặc lỗi cho người tạo job); ghi cùng transaction với sự kiện, sau commit mới phát tín hiệu Redis `notif:{user_id}`; SSE `/me/notifications/stream` không giữ kết nối DB, gửi số chưa đọc khi có tín hiệu, ping 25 giây, Redis lỗi thì tự đọc lại DB theo chu kỳ. B7 `GET /courses/{id}/insights` (xem mục Dashboard) |
 | 2026-10-28 | Sửa lỗi sau rà soát: refresh token có `rotated_at`, chỉ token bị xoay mới coi là bị đánh cắp khi dùng lại (đổi mật khẩu ở máy này không còn làm máy này bị đăng xuất khi máy khác gửi token cũ); `GET /quizzes` trả `my_last_attempt` cho học viên (bỏ lưu bài làm gần nhất ở localStorage); `GET /courses/{slug}` trả `done_lesson_ids` khi người xem đã đăng ký (mục lục hiện dấu đã học); "Sinh lại" trong AI Studio không lấy cache; AI giải thích câu sai và gợi ý hỏi tiếp trả kết nối DB trước khi gọi AI; lọc REFUSE nhận cả dạng in đậm / có dòng sau; thử lại khi rớt kết nối mạng; giảng viên chưa được duyệt đăng nhập thì về trang chủ |
 | 2026-10-29 | B5 bài tập: bảng `assignments` (rubric JSONB 1–8 tiêu chí, key c1…cN do server đặt, nháp/xuất bản) và `submissions` (một bài mỗi học viên, nộp lại cập nhật tại chỗ và tăng `version`); job `grade_submission` (ref_version = version) bọc bài làm trong `<submission>`, hậu kiểm điểm và câu trích (khớp gần đúng ≥ 80%), chỉ ghi khi version còn khớp và bài chưa được chấm, lỗi thì `ai_failed`; giảng viên xác nhận điểm vào `final_scores` (không ghi đè `ai_result`), học viên chỉ thấy điểm sau xác nhận; thông báo `assignment_published`, `submission_ready`, `grade_released`; `eval/grading.py` (MAE, Spearman, lệch ≤ 1 điểm, cặp injection). Cắt C1 (Whisper) và C2 (chứng chỉ) |
+| 2026-10-29 | Sửa B5 sau review: job chấm bị hủy vì quá giờ hoặc bị sweeper chốt failed thì bài nộp chuyển `ai_failed` và báo giảng viên (không kẹt "AI đang chấm"); xác nhận điểm phải gửi đúng `version` đang xem (409 `STALE_VERSION`); xóa chương/bài bị chặn khi đã có bài nộp; nộp lần đầu dùng `INSERT … ON CONFLICT DO NOTHING` nên bấm đúp không lỗi 500; điểm NaN từ AI coi là output sai. Màn hình chấm: AI chấm xong không đè phần giảng viên đã gõ, bài đã chấm không lấy lại nhận xét AI; sửa bài tập không gửi lại hạn nộp khi không đổi |
```

```diff
--- a/docs/architecture/modules.md
+++ b/docs/architecture/modules.md
@@ -59,7 +59,7 @@ flowchart TB
 - `notify` không phụ thuộc module nào: ai cần gửi mail thì gọi `queue_email`.
 - `inbox` chỉ dựa vào `core` và `auth`: module nào cần báo cho người dùng thì gọi `inbox.service.add` trước commit, `publish` sau commit.
 - `core`, `ai`, `ingestion` không import phần tính năng, `main` hay `worker`.
-- Ngoại lệ duy nhất (ghi rõ trong `.importlinter`): `courses.service` **đọc** bảng của quiz và tutor để chặn xóa khóa đã có học viên làm bài / hỏi AI.
+- Ngoại lệ duy nhất (ghi rõ trong `.importlinter`): `courses.service` **đọc** bảng của quiz, tutor và bài tập để chặn xóa khóa / chương / bài đã có học viên làm quiz, hỏi AI hoặc nộp bài.
 
 ## 2. Bản đồ frontend (`frontend/src/`)
 
```

- [ ] **Bước 2: Commit**

```powershell
git add docs
git commit -m "docs: ghi lại các sửa B5 sau review"
```

---

## Task 4: Kiểm tay (bạn làm, cùng lúc với Task 5 của plan B5)

Sau khi pull: `docker compose --profile web up -d --build`.

- [ ] **Chấm tay trong lúc AI đang chấm:** học viên nộp bài. Giảng viên mở bài ngay (còn "AI đang chấm") và gõ điểm một tiêu chí cùng nhận xét. Đợi AI chấm xong (khối "AI gợi ý" hiện ra): điểm và nhận xét vừa gõ vẫn còn.
- [ ] **Nộp lại khi giảng viên đang xem:** giảng viên mở một bài đã có gợi ý AI. Học viên nộp lại ở tab khác. Giảng viên bấm "Xác nhận điểm": báo "Học viên vừa nộp lại bài…" và hiện bản mới (lần nộp thứ 2).
- [ ] **Bỏ nhận xét:** xác nhận điểm với ô nhận xét trống. Tải lại trang: ô nhận xét vẫn trống.
- [ ] **Xóa bài học có bài nộp:** báo "đã có bài nộp của học viên", bài học còn nguyên.
- [ ] **AI bị treo** (không bắt buộc): tắt mạng hoặc dùng key Gemini sai, nộp bài. Sau tối đa vài phút bài chuyển "AI lỗi", giảng viên nhận thông báo và chấm tay được.
