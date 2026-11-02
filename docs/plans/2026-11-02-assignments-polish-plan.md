# Sửa nhỏ B5 sau review vòng 2: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** review vòng 2 (`81653e8..fdbef28`) kết luận các sửa của plan 7 đúng và đủ, chỉ còn vài điểm nhỏ. Plan này sửa 3 điểm đáng sửa.

| # | Điểm | Cách sửa |
|---|---|---|
| 1 | Job chấm bị hủy vì quá giờ hoặc bị sweeper chốt failed: thông báo "AI không chấm được" đã được lưu, nhưng không phát tín hiệu nên chuông của giảng viên không sáng tới khi tải lại trang. Đường AI lỗi bình thường (`_finish`) thì có phát | `fail_unfinished` trả danh sách người nhận. `_fail_jobs` nhận thêm `notified` để gom lại. `run_job` (nhánh quá giờ) và `sweep_stale_jobs` gọi `inbox.publish` sau commit |
| 2 | Lời báo lỗi lồng ngoặc: "… AI chấm lại (Quá thời gian xử lý (270 giây))" | Đổi thành "… AI chấm lại. Lý do: Quá thời gian xử lý (270 giây)" |
| 3 | Hộp sửa bài tập: hạn nộp ban đầu được tính lại mỗi lần render, nên bài tập được tải lại giữa chừng thì phép so "đã đổi hạn nộp chưa" bị lệch | Chốt một lần bằng `useState(() => …)` |

**Không sửa:** khả năng deadlock giữa sweeper và "AI chấm lại". Đây mới là suy luận, chưa tái hiện được. Giao diện không hiện nút "AI chấm lại" khi bài đang chờ AI, và nếu có xảy ra thì lượt dọn 5 phút sau tự xử lý. Ghi vào mục việc còn lại của báo cáo.

**Không có migration, không đổi API.**

**Thứ tự làm:** **sau** `2026-10-29-assignments-review-fixes-plan.md`. Diff tạo trên HEAD `fdbef28`.

**Mã trong plan đã được chạy thử** trên code của `fdbef28`:

- **Backend:** **826 test pass** (không thêm test mới; 2 test sẵn có được siết thêm điều kiện). `ruff check`, `ruff format --check` sạch, `lint-imports` 6 hợp đồng KEPT.
  - Hai test đã siết đều fail trên code cũ: lời báo lỗi khác.
  - Giữ code `grading.py` mới mà trả `tasks.py` về bản cũ thì fail ở `teacher_id in hub.published`.
- **Frontend:** `tsc`, `eslint` sạch.
  - Unit test: **196 pass**.
  - E2E cả bộ: **107 pass + 1 bỏ qua có chủ ý**.
  - Điểm 3 không có test riêng: chỉ đổi cách khởi tạo một biến, test "sửa bài tập không gửi lại hạn nộp" của plan 7 vẫn bao phần này.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6, nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Commit **không** thêm dòng `Co-Authored-By` hay `Claude-Session`. Khi chạy test giữ `*_PROVIDER=fake`, và chỉ chạy **một** lượt pytest một lúc.

---

## Task 1: Backend: báo ngay cho giảng viên khi job chấm quá giờ hoặc treo, lời báo lỗi gọn (điểm 1, 2)

**Files:** Modify `backend/tests/test_assignments.py`, `backend/app/modules/assignment/grading.py`, `backend/app/worker/tasks.py`

- [x] **Bước 1: Siết test (sẽ fail).** Hai test của plan 7 kiểm thêm: nội dung lời báo lỗi, và giảng viên có trong `hub.published`.

```diff
--- a/backend/tests/test_assignments.py
+++ b/backend/tests/test_assignments.py
@@ -325,12 +325,14 @@ async def test_timed_out_grading_job_marks_ai_failed(client, db, storage, hub, m
     job = await _job(db, sub["id"], 1)
     assert job.status == JobStatus.failed and job.error_msg.startswith("Quá thời gian xử lý")
     detail = (await client.get(f"{API}/submissions/{sub['id']}", headers=gv)).json()
-    assert detail["status"] == "ai_failed" and detail["ai_error"].startswith(AI_ERROR)
+    assert detail["status"] == "ai_failed"
+    assert detail["ai_error"] == f"{AI_ERROR}. Lý do: Quá thời gian xử lý (1 giây)"  # không lồng ngoặc
     teacher_id = (await client.get(f"{API}/me", headers=gv)).json()["id"]
     assert await _kinds(db, teacher_id) == ["submission_ready"]
+    assert teacher_id in hub.published  # chuông của giảng viên sáng ngay, không đợi tải lại trang
 
 
-async def test_sweeper_fails_stale_grading_job_and_submission(client, db):
+async def test_sweeper_fails_stale_grading_job_and_submission(client, db, hub):
     """Worker chết giữa chừng: sweeper chốt job failed và bài chuyển ai_failed, giảng viên chấm tay được."""
     gv, sv, _, _, a = await _setup(client)
     sub = await _submit(client, sv, a, text_content=ANSWER)
@@ -343,7 +345,10 @@ async def test_sweeper_fails_stale_grading_job_and_submission(client, db):
     await db.commit()
     assert await sweep_stale_jobs({}) == 1
     detail = (await client.get(f"{API}/submissions/{sub['id']}", headers=gv)).json()
-    assert detail["status"] == "ai_failed" and "Worker bị gián đoạn" in detail["ai_error"]
+    assert detail["status"] == "ai_failed"
+    assert detail["ai_error"] == f"{AI_ERROR}. Lý do: Worker bị gián đoạn"
+    teacher_id = (await client.get(f"{API}/me", headers=gv)).json()["id"]
+    assert hub.published.count(teacher_id) == 1
 
 
 async def test_cannot_delete_lesson_with_submissions(client, db):
```

```powershell
cd backend
uv run pytest tests/test_assignments.py -q -k "timed_out or sweeper"    # 2 failed
```

- [x] **Bước 2: Sửa.** `inbox.publish` không bao giờ ném lỗi; thông báo đã nằm an toàn trong DB, nên Redis lỗi thì chỉ chậm chuông chứ không mất thông báo.

```diff
--- a/backend/app/modules/assignment/grading.py
+++ b/backend/app/modules/assignment/grading.py
@@ -245,11 +245,11 @@ async def _finish(
     return True
 
 
-async def fail_unfinished(db: AsyncSession, refs: list[tuple[uuid.UUID, int]], reason: str) -> int:
+async def fail_unfinished(db: AsyncSession, refs: list[tuple[uuid.UUID, int]], reason: str) -> list[str]:
     """Job grade_submission bị hủy vì quá thời gian hoặc bị sweeper chốt failed (worker chết, không vào được hàng
     đợi): bài của đúng version đó đang chờ AI thì chuyển ai_failed và báo giảng viên, để không kẹt "AI đang chấm"
-    mãi. Chưa commit: caller commit cùng transaction với job. Trả số bài đã chuyển."""
-    failed = 0
+    mãi. Chưa commit: caller commit cùng transaction với job. Trả id giảng viên cần báo (caller publish sau commit)."""
+    notified: list[str] = []
     for submission_id, version in refs:
         assignment_id = await db.scalar(
             update(Submission)
@@ -258,7 +258,7 @@ async def fail_unfinished(db: AsyncSession, refs: list[tuple[uuid.UUID, int]], r
                 Submission.version == version,
                 Submission.status == SubmissionStatus.submitted,
             )
-            .values(status=SubmissionStatus.ai_failed, ai_error=f"{AI_ERROR} ({reason})"[:500])
+            .values(status=SubmissionStatus.ai_failed, ai_error=f"{AI_ERROR}. Lý do: {reason}"[:500])
             .returning(Submission.assignment_id)
         )
         if assignment_id is None:
@@ -272,7 +272,7 @@ async def fail_unfinished(db: AsyncSession, refs: list[tuple[uuid.UUID, int]], r
                 .where(Assignment.id == assignment_id)
             )
         ).one()
-        inbox.add(
+        notified += inbox.add(
             db,
             [course.teacher_id],
             NotificationKind.submission_ready,
@@ -280,5 +280,4 @@ async def fail_unfinished(db: AsyncSession, refs: list[tuple[uuid.UUID, int]], r
             teacher_link(course, assignment, submission_id),
             reason,
         )
-        failed += 1
-    return failed
+    return notified
```

```diff
--- a/backend/app/worker/tasks.py
+++ b/backend/app/worker/tasks.py
@@ -115,6 +115,7 @@ async def run_job(
         # vd. asyncio.wait_for bên trong, là lỗi thường → nhánh dưới).
         if deadline.expired():
             logger.error("Job %s quá thời gian xử lý (%s giây), đã hủy", job_id, timeout_s)
+            notified: list[str] = []
             async with session_factory() as db:
                 # Cùng điều kiện với finish_job (chỉ job còn processing); source ingest_* failed cùng transaction
                 if await _fail_jobs(
@@ -122,8 +123,10 @@ async def run_job(
                     (Job.id == jid, Job.status == JobStatus.processing),
                     timeout_error(timeout_s),
                     utcnow(),
+                    notified,
                 ):
                     await db.commit()
+            await inbox.publish(get_hub(), notified)
             return
         logger.exception("Job %s thất bại", job_id)
         status, error = JobStatus.failed, error_text(e)
@@ -371,10 +374,11 @@ async def grade_submission(ctx: dict, job_id: str) -> None:
     await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("grade_submission"))
 
 
-async def _fail_jobs(db, jobs_where, error: str, now) -> int:
+async def _fail_jobs(db, jobs_where, error: str, now, notified: list[str] | None = None) -> int:
     """Chuyển các job khớp điều kiện sang failed; source tương ứng (loại ingest_*) còn pending/processing
     cũng failed cùng lỗi, bài nộp đang chờ AI (grade_submission) chuyển ai_failed. Chưa commit — caller commit
-    để job, source và bài nộp đổi trạng thái trong cùng transaction."""
+    để job, source và bài nộp đổi trạng thái trong cùng transaction, rồi publish các id được thêm vào `notified`
+    (người nhận thông báo) để chuông của họ sáng ngay."""
     rows = (
         await db.execute(
             update(Job)
@@ -385,7 +389,9 @@ async def _fail_jobs(db, jobs_where, error: str, now) -> int:
     ).all()
     grading = [(ref_id, ref_version) for type_, ref_id, ref_version in rows if type_ == GRADE_JOB_TYPE]
     if grading:
-        await fail_unfinished_grading(db, grading, error)
+        recipients = await fail_unfinished_grading(db, grading, error)
+        if notified is not None:
+            notified.extend(recipients)
     source_ids = [ref_id for type_, ref_id, _ in rows if type_ in SOURCE_JOB_TYPES]
     if source_ids:
         await db.execute(
@@ -445,6 +451,7 @@ async def sweep_stale_jobs(ctx: dict) -> int:
     now = utcnow()
     pending_after = timedelta(minutes=get_settings().pending_job_requeue_after_min)
     swept = 0
+    notified: list[str] = []
     async with session_factory() as db:
         for type_, timeout_s in JOB_TIMEOUTS.items():
             cutoff = now - timedelta(seconds=timeout_s) - STALE_GRACE
@@ -453,6 +460,7 @@ async def sweep_stale_jobs(ctx: dict) -> int:
                 (Job.type == type_, Job.status == JobStatus.processing, Job.started_at < cutoff),
                 STALE_JOB_ERROR,
                 now,
+                notified,
             )
         swept += await _fail_jobs(
             db,
@@ -463,8 +471,10 @@ async def sweep_stale_jobs(ctx: dict) -> int:
             ),
             PENDING_JOB_ERROR,
             now,
+            notified,
         )
         await db.commit()
+        await inbox.publish(get_hub(), notified)
         requeued = await _requeue_pending(
             db, lambda: ctx.get("queue") or ArqQueue(pool=ctx["redis"]), now - pending_after, now
         )
```

- [x] **Bước 3: Chạy kiểm tra, commit**

```powershell
uv run pytest -q                                      # 826 passed
uv run ruff check . ; uv run ruff format --check .
uv run lint-imports                                   # 6 contracts KEPT
cd ..
git add backend
git commit -m "fix(api): báo ngay cho giảng viên khi job chấm quá giờ hoặc bị sweeper chốt failed, lời báo lỗi không lồng ngoặc"
```

---

## Task 2: Frontend: chốt hạn nộp ban đầu của hộp sửa bài tập (điểm 3)

**Files:** Modify `frontend/src/components/teach/assignment-manager.tsx`

- [ ] **Bước 1: Sửa**

```diff
--- a/frontend/src/components/teach/assignment-manager.tsx
+++ b/frontend/src/components/teach/assignment-manager.tsx
@@ -141,7 +141,8 @@ function AssignmentDialog({ lessonId, assignment, onClose }: { lessonId: string;
   const locked = !!assignment?.submission_count; // đã có bài nộp: không đổi rubric được nữa
   const [title, setTitle] = React.useState(assignment?.title ?? "");
   const [instructions, setInstructions] = React.useState(assignment?.instructions ?? "");
-  const initialDue = assignment?.due_at ? toLocalInput(assignment.due_at) : "";
+  // chốt lúc mở hộp: bài tập được tải lại trong lúc đang sửa cũng không làm lệch phép so "đã đổi hạn nộp chưa"
+  const [initialDue] = React.useState(() => (assignment?.due_at ? toLocalInput(assignment.due_at) : ""));
   const [due, setDue] = React.useState(initialDue);
   const [rubric, setRubric] = React.useState<CriterionDraft[]>(
     assignment
```

- [ ] **Bước 2: Chạy kiểm tra, commit**

```powershell
cd frontend
npx tsc --noEmit ; npx eslint .
npx vitest run                     # 196 pass
cd ..
git add frontend
git commit -m "fix(web): hộp sửa bài tập chốt hạn nộp ban đầu lúc mở"
```

Không cần chạy lại Playwright: E2E không mở hộp sửa bài tập (bản thử đã chạy cả bộ: 107 pass + 1 bỏ qua).

---

## Không có kiểm tay riêng

Muốn job chấm quá giờ hay bị sweeper chốt failed thì phải làm worker treo hoặc chết đúng lúc đang chấm, nên khó dựng lại bằng tay. Hai test backend ở Task 1 đã bao cả hai đường. Danh sách kiểm tay B5 hôm trước vẫn giữ nguyên.
