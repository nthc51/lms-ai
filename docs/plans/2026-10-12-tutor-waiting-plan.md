# Hỏi AI Tutor lúc tài liệu đang xử lý: Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** khi kiểm tay, PDF slide nặng mất khoảng 90 giây mới xử lý xong, trong lúc đó ô hỏi AI Tutor bị khóa với câu "Tài liệu đang được xử lý". Bạn muốn làm như Claude: **vẫn gửi câu hỏi được, AI trả lời sau** khi xử lý xong. Ngoài ra câu "Tài liệu đang được xử lý" đang hiện cho **mọi** trường hợp không có đoạn tài liệu nào, kể cả khi tài liệu đã xong nhưng được nhúng bằng model khác (đổi `fake` ↔ Gemini ↔ OpenRouter: đúng lỗi khóa "Thử Gemini" của bạn), hay xử lý bị lỗi. Học viên chờ mãi mà không biết vì sao.

**Mục tiêu:**

- `GET /tutor/availability` nói rõ trạng thái: `ready`, `processing` (còn N tài liệu đang xử lý), `model_mismatch`, `failed`, `empty`, `draft`, mỗi trạng thái một câu tiếng Việt riêng.
- Lúc `processing`: ô nhập **vẫn mở**. Câu hỏi được lưu với `waiting_for_docs = true`, hiện "Đang chờ tài liệu xử lý xong, AI sẽ trả lời ngay sau đó" dưới bong bóng câu hỏi.
- Worker xử lý PDF xong (hoặc lỗi) thì xếp job `tutor_waiting` cho bài đó. Job trả lời từng câu chờ (cũ trước) **bằng đúng luồng AI Tutor** (viết lại câu hỏi theo lịch sử, tìm tài liệu, chốt chặn, trích nguồn). Câu trả lời được ghi **ngay sau câu hỏi** trong hội thoại. Cron 5 phút vét các câu bị lỡ.
- Trang tự hỏi lại server mỗi 5 giây khi đang chờ; có câu trả lời thì hiện luôn và báo "AI đã trả lời câu hỏi bạn gửi lúc tài liệu đang xử lý". Xử lý xong thì ô hỏi trực tiếp (stream) mở lại.
- Tài liệu xử lý lỗi hết: câu chờ nhận một câu trả lời thông báo (không để chờ mãi). Học viên mất quyền (bị hủy đăng ký…) thì câu chờ bị bỏ, không trả lời.
- Giới hạn: tối đa **5 câu chờ / phiên**; mỗi câu chờ tính một lượt rate limit như câu hỏi thường.
- Đã hỏi được mà vẫn còn tài liệu đang xử lý: dòng nhỏ "Còn N tài liệu đang xử lý; câu trả lời lúc này chỉ dựa trên tài liệu đã xử lý xong".

**Thứ tự làm:** sau `2026-10-12-openrouter-plan.md` (cuối chuỗi 3 plan). Diff tạo trên bản đã xong hai plan trước.

**Mã trong plan đã được chạy thử** (bản cuối chuỗi):

- Backend: **751 test pass** (14 mới ở plan này, 1 test cũ sửa). Migration `a6d3f0c8e217` theo sau `f4c2a7d91b35`. `ruff` sạch; `lint-imports` 5 hợp đồng **KEPT** (`tutor` chỉ dùng `materials` / `courses` / `jobs` qua model, worker gọi `tutor.waiting`, đúng chiều cho phép).
- Frontend: `tsc`, `eslint` sạch; **151 unit test pass** (5 mới); E2E `tutor-waiting.spec.ts` (mới) + `student` + `studio` pass ở 375px và 1280px, có axe.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6 nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn dùng pgvector 0.8, **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Cách áp diff như hai plan trước.

### Hợp đồng API (tiền tố `/api/v1`)

| Endpoint | Thay đổi |
|---|---|
| `GET /tutor/availability` | Thêm `state`, `processing_docs`, `can_queue`. `message` theo trạng thái. Thứ tự ưu tiên khi chưa hỏi được: `draft` > `processing` > `model_mismatch` > `failed` > `empty` |
| `POST /tutor/sessions/{id}/questions` (mới) | Body như hỏi thường `{content}`. **202** `MessageOut` (`waiting_for_docs: true`). **409** `TUTOR_READY` (đã hỏi trực tiếp được), `NOT_PROCESSING` (không còn tài liệu đang xử lý; lý do trong message), `TOO_MANY_WAITING`; **429**, **403**, **404** như hỏi thường |
| `MessageOut` | Thêm `waiting_for_docs` |

Job mới `tutor_waiting` (ref_id = `lessons.id`, timeout 600 giây, dừng nhận câu mới khi còn 120 giây). Cron `answer_waiting_cron` phút 2, 7, 12… (lệch 2 phút với sweeper).

**Thứ tự câu trả lời:** câu trả lời muộn được ghi `created_at` = `created_at` của câu hỏi; danh sách tin nhắn sắp theo `(created_at, role, id)` với `user < assistant`, nên câu trả lời luôn nằm ngay dưới câu hỏi của nó dù được sinh sau các câu khác. Lịch sử dùng để viết lại câu hỏi chỉ lấy các tin **trước** câu hỏi đó.

**Hai bên cùng trả lời:** job và cron có thể chạy cùng lúc. Mỗi câu được "nhận" bằng `UPDATE … SET waiting_for_docs = false WHERE id = … AND waiting_for_docs RETURNING …`, nên chỉ một bên trả lời.

---

## Task 1: Backend: trạng thái tài liệu + câu hỏi chờ

**Files:**
- Create: `backend/alembic/versions/a6d3f0c8e217_tutor_waiting.py`
- Create: `backend/app/modules/tutor/state.py`, `backend/app/modules/tutor/waiting.py`
- Modify: `backend/app/modules/tutor/models.py`, `schemas.py`, `answer.py`, `service.py`, `router.py`
- Modify: `backend/app/modules/jobs/models.py` (docstring)
- Modify: `backend/app/worker/tasks.py`, `backend/app/worker/settings.py`
- Test: `backend/tests/test_tutor_waiting.py` (mới), `backend/tests/test_tutor_sessions.py` (sửa)

- [x] **Bước 1: Viết test (sẽ fail)**

```python
"""Hỏi AI Tutor lúc tài liệu đang xử lý: trạng thái availability, gửi câu hỏi chờ, worker trả lời khi xong."""

import uuid

from sqlalchemy import select, update

from app.ai.embedder import FakeEmbedder
from app.ai.llm import FakeLLMProvider
from app.ai.llm_client import LLMClient
from app.ai.vision import FakeVision
from app.core.config import get_settings
from app.modules.jobs.service import create_job
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.modules.tutor.models import ChatMessage, ChatRole
from app.modules.tutor.waiting import DOCS_FAILED_ANSWER, answer_waiting
from app.worker.tasks import answer_waiting_cron, ingest_pdf, tutor_waiting
from tests.factories import BINARY_SEARCH, make_pdf_source, seed_chunks
from tests.fakes import InMemoryStorage, RecordingQueue
from tests.helpers import API, create_course, make_published_course, make_student, make_teacher
from tests.test_ai_retry import Sleeps

Q1 = "Tìm kiếm nhị phân là gì?"
Q2 = "Độ phức tạp của nó thế nào?"


async def _setup(client, db, *, source_status=SourceStatus.processing):
    """Khóa đã publish, học viên đã đăng ký, bài có một PDF ở trạng thái source_status (chưa có chunk)."""
    from app.modules.auth.models import Role, User
    from app.modules.courses.models import Lesson

    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    _, sv = await make_student(client)
    assert (await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)).status_code == 201
    lesson_row = await db.get(Lesson, uuid.UUID(lesson["id"]))
    owner = await db.scalar(select(User).where(User.role == Role.teacher))
    source = await make_pdf_source(
        db, InMemoryStorage(), owner, lesson_row, b"%PDF-1.7", status=source_status
    )
    s = (
        await client.post(
            f"{API}/tutor/sessions", json={"course_id": course["id"], "lesson_id": lesson["id"]}, headers=sv
        )
    ).json()
    return course, lesson, source, sv, s["id"]


def _params(course, lesson=None):
    return {"course_id": course["id"], **({"lesson_id": lesson["id"]} if lesson else {})}


async def _availability(client, headers, course, lesson=None):
    r = await client.get(f"{API}/tutor/availability", params=_params(course, lesson), headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _queue(client, headers, session_id, text=Q1):
    return await client.post(
        f"{API}/tutor/sessions/{session_id}/questions", json={"content": text}, headers=headers
    )


async def _finish(db, source, *, chunks=True):
    """Tài liệu xử lý xong: source ready + có chunk (seed_chunks gắn thêm một source ready khác)."""
    await db.execute(update(Source).where(Source.id == source.id).values(status=SourceStatus.ready))
    await db.commit()
    if chunks:
        await seed_chunks(db, source.lesson_id, [BINARY_SEARCH])


def _llm(provider=None):
    return LLMClient(provider or FakeLLMProvider(), get_settings(), sleep=Sleeps())


async def _messages(client, headers, session_id):
    r = await client.get(f"{API}/tutor/sessions/{session_id}/messages", headers=headers)
    return r.json()["items"]


# ---------- availability ----------


async def test_availability_states(client, db):
    course, lesson, source, sv, _ = await _setup(client, db)
    a = await _availability(client, sv, course, lesson)
    assert a["state"] == "processing" and a["can_queue"] is True and a["processing_docs"] == 1
    assert a["available"] is False and "AI sẽ trả lời ngay khi xử lý xong" in a["message"]

    await db.execute(update(Source).where(Source.id == source.id).values(status=SourceStatus.failed))
    await db.commit()
    a = await _availability(client, sv, course, lesson)
    assert (a["state"], a["can_queue"]) == ("failed", False)

    await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH])
    await db.execute(update(Chunk).values(embedding_model="model-khac"))
    await db.commit()
    a = await _availability(client, sv, course, lesson)
    assert a["state"] == "model_mismatch" and "model AI khác" in a["message"]

    await db.execute(update(Chunk).values(embedding_model="fake-768"))
    await db.commit()
    a = await _availability(client, sv, course, lesson)
    assert (a["state"], a["available"], a["message"], a["processing_docs"]) == ("ready", True, None, 0)
    a = await _availability(client, sv, course)  # cả khóa (đã publish)
    assert a["state"] == "ready" and a["ready_chunks"] == 1


async def test_ready_scope_still_reports_documents_in_progress(client, db):
    course, lesson, _, sv, _ = await _setup(client, db)
    await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH])
    a = await _availability(client, sv, course, lesson)
    assert (a["state"], a["available"], a["processing_docs"], a["can_queue"]) == ("ready", True, 1, False)


async def test_empty_lesson_and_draft_course_scope(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    a = await _availability(client, gv, course, lesson)
    assert (a["state"], a["message"]) == ("empty", "Bài này chưa có tài liệu cho AI Tutor.")
    draft = await create_course(client, gv, title="Khóa nháp")
    a = await _availability(client, gv, draft)
    assert (a["state"], a["can_queue"]) == ("draft", False)


# ---------- gửi câu hỏi chờ ----------


async def test_queue_question_only_while_processing(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    r = await _queue(client, sv, sid)
    assert r.status_code == 202, r.text
    assert r.json()["waiting_for_docs"] is True and r.json()["role"] == "user"
    [m] = await _messages(client, sv, sid)
    assert m["waiting_for_docs"] is True

    await _finish(db, source)
    r = await _queue(client, sv, sid)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "TUTOR_READY")


async def test_queue_rejected_when_nothing_is_processing(client, db):
    _, _, _, sv, sid = await _setup(client, db, source_status=SourceStatus.failed)
    r = await _queue(client, sv, sid)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "NOT_PROCESSING")
    assert "không thành công" in r.json()["error"]["message"]
    assert await _messages(client, sv, sid) == []


async def test_queue_is_capped_per_session_and_checks_ownership(client, db):
    _, _, _, sv, sid = await _setup(client, db)
    for i in range(5):
        assert (await _queue(client, sv, sid, f"Câu {i}")).status_code == 202
    r = await _queue(client, sv, sid, "Câu thứ sáu")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "TOO_MANY_WAITING")
    _, other = await make_student(client, "sv2@x.com")
    assert (await _queue(client, other, sid)).status_code == 404


async def test_queue_counts_against_rate_limit(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "tutor_rate_limit_per_hour", 1)
    _, _, _, sv, sid = await _setup(client, db)
    assert (await _queue(client, sv, sid)).status_code == 202
    r = await _queue(client, sv, sid, Q2)
    assert r.status_code == 429 and "Retry-After" in r.headers


# ---------- worker trả lời ----------


async def test_waiting_questions_answered_in_order_after_processing(client, db):
    _, lesson, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid, Q1)
    await _queue(client, sv, sid, Q2)
    provider = FakeLLMProvider()
    # Tài liệu chưa xong: không trả lời gì, câu hỏi vẫn chờ
    assert await answer_waiting(_llm(provider), FakeEmbedder(768)) == 0
    assert provider.calls == []

    await _finish(db, source)
    assert await answer_waiting(_llm(provider), FakeEmbedder(768), lesson_id=uuid.UUID(lesson["id"])) == 2
    items = await _messages(client, sv, sid)
    assert [(m["role"], m["waiting_for_docs"]) for m in items] == [
        ("user", False),
        ("assistant", False),
        ("user", False),
        ("assistant", False),
    ]
    assert items[0]["content"] == Q1 and items[2]["content"] == Q2
    assert items[1]["content"] and items[1]["citations"]
    # Câu 2 có lịch sử (câu 1 và câu trả lời của nó) nên được viết lại trước khi tìm tài liệu
    rewrites = [c for c in provider.calls if c.op == "tutor_rewrite"]
    assert len(rewrites) == 1 and Q1 in rewrites[0].prompt and Q2 in rewrites[0].prompt


async def test_waiting_question_is_answered_only_once(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    await _finish(db, source)
    assert await answer_waiting(_llm(), FakeEmbedder(768)) == 1
    assert await answer_waiting(_llm(), FakeEmbedder(768)) == 0
    answers = await db.scalars(select(ChatMessage).where(ChatMessage.role == ChatRole.assistant))
    assert len(list(answers)) == 1


async def test_failed_documents_get_a_notice_instead_of_waiting_forever(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    await db.execute(update(Source).where(Source.id == source.id).values(status=SourceStatus.failed))
    await db.commit()
    provider = FakeLLMProvider()
    assert await answer_waiting(_llm(provider), FakeEmbedder(768)) == 1
    items = await _messages(client, sv, sid)
    assert [m["role"] for m in items] == ["user", "assistant"]
    assert items[1]["content"] == DOCS_FAILED_ANSWER and items[1]["refused"] is True
    assert provider.calls == []


async def test_lost_access_drops_waiting_question(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    from sqlalchemy import delete

    from app.modules.enrollment.models import Enrollment

    await db.execute(delete(Enrollment))  # bị hủy đăng ký sau khi gửi câu hỏi
    await db.commit()
    await _finish(db, source)
    provider = FakeLLMProvider()
    assert await answer_waiting(_llm(provider), FakeEmbedder(768)) == 1
    msgs = list(await db.scalars(select(ChatMessage).execution_options(populate_existing=True)))
    assert [(m.role, m.waiting_for_docs) for m in msgs] == [(ChatRole.user, False)]
    assert provider.calls == []


async def test_ingest_end_queues_tutor_waiting_job_and_job_answers(client, db):
    from tests.pdfs import make_pdf

    _, lesson, source, sv, sid = await _setup(client, db, source_status=SourceStatus.pending)
    await _queue(client, sv, sid)
    storage = InMemoryStorage()
    from app.modules.materials.models import Asset

    asset = await db.get(Asset, source.asset_id)
    await storage.put(asset.storage_key, make_pdf([BINARY_SEARCH]), "application/pdf")
    job, _ = await create_job(db, "ingest_pdf", source.id, created_by=None)
    await db.commit()
    queue = RecordingQueue()
    ctx = {
        "storage": storage,
        "embedder": FakeEmbedder(768),
        "vision": FakeVision(),
        "queue": queue,
        "llm": _llm(),
    }
    await ingest_pdf(ctx, str(job.id))
    assert ("tutor_waiting", uuid.UUID(lesson["id"])) in queue.jobs

    waiting_job, created = await create_job(db, "tutor_waiting", uuid.UUID(lesson["id"]), created_by=None)
    await db.commit()
    assert created is False  # chính job vừa được xếp hàng, chưa chạy
    await tutor_waiting(ctx, str(waiting_job.id))
    items = await _messages(client, sv, sid)
    assert [m["role"] for m in items] == ["user", "assistant"] and items[1]["content"]


async def test_ingest_without_waiting_questions_queues_nothing_extra(client, db):
    from tests.pdfs import make_pdf

    _, _, source, _, _ = await _setup(client, db, source_status=SourceStatus.pending)
    storage = InMemoryStorage()
    from app.modules.materials.models import Asset

    asset = await db.get(Asset, source.asset_id)
    await storage.put(asset.storage_key, make_pdf([BINARY_SEARCH]), "application/pdf")
    job, _ = await create_job(db, "ingest_pdf", source.id, created_by=None)
    await db.commit()
    queue = RecordingQueue()
    await ingest_pdf(
        {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision(), "queue": queue},
        str(job.id),
    )
    assert [t for t, _ in queue.jobs] == ["source_guide"]


async def test_cron_sweeps_waiting_questions(client, db):
    _, _, source, sv, sid = await _setup(client, db)
    await _queue(client, sv, sid)
    await _finish(db, source)
    assert await answer_waiting_cron({"llm": _llm(), "embedder": FakeEmbedder(768)}) == 1
    assert [m["role"] for m in await _messages(client, sv, sid)] == ["user", "assistant"]
```

Test cũ: không có tài liệu nào giờ là `empty` (trước đây báo nhầm "đang xử lý").

```diff
--- a/backend/tests/test_tutor_sessions.py
+++ b/backend/tests/test_tutor_sessions.py
@@ -83,14 +83,27 @@
     course, _, lesson, sv = await _enrolled(client, gv)
     params = {"course_id": course["id"], "lesson_id": lesson["id"]}
     r = await client.get(f"{API}/tutor/availability", params=params, headers=sv)
-    assert r.json() == {"available": False, "ready_chunks": 0, "message": "Tài liệu đang được xử lý"}
+    assert r.json() == {
+        "available": False,
+        "ready_chunks": 0,
+        "message": "Bài này chưa có tài liệu cho AI Tutor.",
+        "state": "empty",
+        "processing_docs": 0,
+        "can_queue": False,
+    }
     await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH], status=SourceStatus.processing)
-    assert (await client.get(f"{API}/tutor/availability", params=params, headers=sv)).json()[
-        "available"
-    ] is False
+    r = (await client.get(f"{API}/tutor/availability", params=params, headers=sv)).json()
+    assert (r["available"], r["state"], r["can_queue"]) == (False, "processing", True)
     await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH])
     r = await client.get(f"{API}/tutor/availability", params={"course_id": course["id"]}, headers=sv)
-    assert r.json() == {"available": True, "ready_chunks": 1, "message": None}
+    assert r.json() == {
+        "available": True,
+        "ready_chunks": 1,
+        "message": None,
+        "state": "ready",
+        "processing_docs": 1,
+        "can_queue": False,
+    }
 
 
 async def test_messages_order_is_deterministic_for_same_timestamp(client, db):
@@ -130,4 +143,7 @@
         "available": True,
         "ready_chunks": 1,
         "message": None,
+        "state": "ready",
+        "processing_docs": 0,
+        "can_queue": False,
     }
```

- [x] **Bước 2: Migration + model**

```python
"""chat_messages.waiting_for_docs: câu hỏi gửi lúc tài liệu đang xử lý, AI trả lời khi xử lý xong

Revision ID: a6d3f0c8e217
Revises: f4c2a7d91b35
Create Date: 2026-10-12 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6d3f0c8e217"
down_revision: str | Sequence[str] | None = "f4c2a7d91b35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat_messages",
        sa.Column("waiting_for_docs", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Worker chỉ quét các câu đang chờ: index một phần, gần như rỗng
    op.create_index(
        "ix_chat_messages_waiting",
        "chat_messages",
        ["created_at"],
        postgresql_where=sa.text("waiting_for_docs"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chat_messages_waiting", table_name="chat_messages")
    op.drop_column("chat_messages", "waiting_for_docs")
```

```diff
--- a/backend/app/modules/tutor/models.py
+++ b/backend/app/modules/tutor/models.py
@@ -41,6 +41,7 @@
     __table_args__ = (
         Index("ix_chat_messages_session_created", "session_id", "created_at"),
         CheckConstraint("feedback IN (1, -1)", name="ck_chat_messages_feedback"),
+        Index("ix_chat_messages_waiting", "created_at", postgresql_where=text("waiting_for_docs")),
     )
 
     session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
@@ -58,3 +59,5 @@
     prompt_version: Mapped[str | None] = mapped_column(String(80))
     # 3 câu hỏi gợi ý tiếp theo (AI Studio S5), sinh lần đầu khi frontend xin rồi lưu lại. NULL = chưa sinh.
     followups: Mapped[list[str] | None] = mapped_column(JSONB)
+    # Câu hỏi (role user) gửi lúc tài liệu còn đang xử lý: worker trả lời khi xử lý xong rồi tắt cờ này
+    waiting_for_docs: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
```

```diff
--- a/backend/app/modules/jobs/models.py
+++ b/backend/app/modules/jobs/models.py
@@ -20,7 +20,7 @@
 
 
 class Job(IdMixin, TimestampMixin, Base):
-    """type quyết định ref_id trỏ tới đâu: ingest_pdf/ingest_video → sources.id, quiz_gen → lessons.id,
+    """type quyết định ref_id trỏ tới đâu: ingest_pdf/ingest_video → sources.id, quiz_gen / tutor_waiting → lessons.id,
     grade_submission → submissions.id (ref_version = submissions.version).
 
     created_by: người tạo job (NULL = job hệ thống, vd. do cron tạo); GET /jobs/{id} chỉ trả cho người tạo
```

```powershell
cd backend
uv run alembic upgrade head
uv run alembic check          # "No new upgrade operations detected"
uv run alembic downgrade -1 ; uv run alembic upgrade head
```

- [x] **Bước 3: Schema**

```diff
--- a/backend/app/modules/tutor/schemas.py
+++ b/backend/app/modules/tutor/schemas.py
@@ -46,6 +46,8 @@
     refused: bool
     truncated: bool
     feedback: int | None
+    # Câu hỏi gửi lúc tài liệu đang xử lý, chưa có câu trả lời (worker trả lời khi xử lý xong)
+    waiting_for_docs: bool = False
     created_at: datetime
 
 
@@ -65,7 +67,17 @@
     value: Literal[1, -1] | None  # None = bỏ đánh giá
 
 
+# ready: hỏi được ngay. processing: chưa có chunk nào nhưng còn tài liệu đang xử lý (gửi câu hỏi chờ được).
+# model_mismatch: tài liệu đã xử lý bằng model embedding khác model hiện tại (đổi provider/model).
+# failed: tài liệu xử lý lỗi. empty: chưa có tài liệu (hoặc tài liệu không có chữ). draft: hỏi cả khóa khi khóa
+# còn nháp.
+TutorState = Literal["ready", "processing", "model_mismatch", "failed", "empty", "draft"]
+
+
 class AvailabilityOut(BaseModel):
     available: bool
     ready_chunks: int
-    message: str | None  # "Tài liệu đang được xử lý" khi chưa có chunk nào (spec 5.7)
+    message: str | None  # lý do chưa hỏi được (None khi available)
+    state: TutorState
+    processing_docs: int  # số tài liệu đang chờ / đang xử lý trong phạm vi
+    can_queue: bool  # gửi câu hỏi chờ được (POST /tutor/sessions/{id}/questions)
```

- [x] **Bước 4: `tutor/state.py`** (đếm tài liệu theo trạng thái trong phạm vi bài / cả khóa; phạm vi cả khóa đi qua `Lesson → Section`)

```python
"""Trạng thái tài liệu trong phạm vi hỏi của AI Tutor: hỏi được chưa, nếu chưa thì vì sao.

Trước đây chỉ có một câu "Tài liệu đang được xử lý" cho mọi trường hợp 0 chunk, kể cả khi tài liệu đã xử lý
xong bằng model embedding khác (đổi provider) hoặc xử lý lỗi. Ở đây tách rõ từng trường hợp."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval import SearchScope, count_ready_chunks
from app.modules.courses.models import Lesson, Section
from app.modules.materials.models import Chunk, Source, SourceStatus
from app.modules.tutor.schemas import AvailabilityOut

DRAFT_COURSE_SCOPE_MESSAGE = "Hỏi cả khóa chỉ dùng được khi khóa đã xuất bản"
MODEL_MISMATCH_MESSAGE = (
    "Tài liệu đã được xử lý bằng model AI khác với model đang dùng. "
    "Hãy báo giảng viên hoặc quản trị viên xử lý lại tài liệu."
)
FAILED_MESSAGE = "Tài liệu xử lý không thành công. Giảng viên cần tải lại hoặc bấm “Xử lý lại”."
EMPTY_MESSAGE = "Bài này chưa có tài liệu cho AI Tutor."
NO_TEXT_MESSAGE = "Tài liệu của bài này chưa có nội dung chữ để AI Tutor đọc."


def processing_message(n: int) -> str:
    return (
        f"Tài liệu đang được xử lý ({n} tài liệu). "
        "Bạn vẫn có thể đặt câu hỏi: AI sẽ trả lời ngay khi xử lý xong."
    )


@dataclass(frozen=True)
class ScopeState:
    ready_chunks: int  # chunk Tutor tìm được (đúng model, source ready; theo khóa thì khóa đã publish)
    processing_docs: int  # source pending / processing
    failed_docs: int
    ready_docs: int
    other_model_chunks: int  # chunk của source ready nhưng embedding bằng model khác


def _sources_in(scope: SearchScope):
    if scope.lesson_id is not None:
        return Source.lesson_id == scope.lesson_id
    lessons = select(Lesson.id).join(Section, Section.id == Lesson.section_id)
    return Source.lesson_id.in_(lessons.where(Section.course_id == scope.course_id))


async def scope_state(db: AsyncSession, scope: SearchScope, embedding_model: str) -> ScopeState:
    by_status = dict(
        (
            await db.execute(
                select(Source.status, func.count()).where(_sources_in(scope)).group_by(Source.status)
            )
        ).all()
    )
    other = select(func.count(Chunk.id)).join(Source, Source.id == Chunk.source_id)
    other = other.where(
        Chunk.course_id == scope.course_id,
        Chunk.embedding_model != embedding_model,
        Source.status == SourceStatus.ready,
    )
    if scope.lesson_id is not None:
        other = other.where(Chunk.lesson_id == scope.lesson_id)
    return ScopeState(
        ready_chunks=await count_ready_chunks(db, scope, embedding_model),
        processing_docs=by_status.get(SourceStatus.pending, 0) + by_status.get(SourceStatus.processing, 0),
        failed_docs=by_status.get(SourceStatus.failed, 0),
        ready_docs=by_status.get(SourceStatus.ready, 0),
        other_model_chunks=await db.scalar(other) or 0,
    )


def describe(st: ScopeState, *, draft_course_scope: bool) -> AvailabilityOut:
    """Thứ tự ưu tiên khi chưa hỏi được: khóa nháp > đang xử lý > khác model > lỗi > chưa có tài liệu.
    Đang xử lý đứng trước: còn tài liệu sắp xong thì học viên nên chờ (và gửi câu hỏi chờ được)."""
    base = {"ready_chunks": st.ready_chunks, "processing_docs": st.processing_docs}
    if draft_course_scope:
        return AvailabilityOut(
            available=False, message=DRAFT_COURSE_SCOPE_MESSAGE, state="draft", can_queue=False, **base
        )
    if st.ready_chunks > 0:
        return AvailabilityOut(available=True, message=None, state="ready", can_queue=False, **base)
    if st.processing_docs > 0:
        return AvailabilityOut(
            available=False,
            message=processing_message(st.processing_docs),
            state="processing",
            can_queue=True,
            **base,
        )
    if st.other_model_chunks > 0:
        state, message = "model_mismatch", MODEL_MISMATCH_MESSAGE
    elif st.failed_docs > 0:
        state, message = "failed", FAILED_MESSAGE
    else:
        state, message = "empty", NO_TEXT_MESSAGE if st.ready_docs else EMPTY_MESSAGE
    return AvailabilityOut(available=False, message=message, state=state, can_queue=False, **base)
```

- [x] **Bước 5: `answer.py` và `service.py`**

`AskContext.answer_created_at` (mặc định `None`, luồng hỏi trực tiếp không đổi). `availability` dùng `state.py`; `load_history` nhận thêm `before`. Hằng `NOT_READY_MESSAGE` bỏ, `DRAFT_COURSE_SCOPE_MESSAGE` chuyển sang `state.py` (grep thấy không còn chỗ nào khác dùng).

```diff
--- a/backend/app/modules/tutor/answer.py
+++ b/backend/app/modules/tutor/answer.py
@@ -13,6 +13,7 @@
 from collections.abc import AsyncIterator, Awaitable, Callable
 from contextlib import AsyncExitStack
 from dataclasses import dataclass, field
+from datetime import datetime
 
 import anyio
 from sqlalchemy.ext.asyncio import async_sessionmaker
@@ -48,6 +49,10 @@
     course_title: str
     question: str
     history: list[tuple[ChatRole, str]] = field(default_factory=list)  # ≤ 4 tin gần nhất, cũ → mới
+    # Câu trả lời muộn (câu hỏi gửi lúc tài liệu đang xử lý): ghi created_at bằng đúng created_at của câu hỏi,
+    # nên trong danh sách tin nhắn câu trả lời đứng ngay sau câu hỏi (cùng giờ thì user trước assistant).
+    # None = câu trả lời trực tiếp, created_at do DB đặt (sau câu hỏi).
+    answer_created_at: datetime | None = None
 
 
 class _Answer:
@@ -124,6 +129,8 @@
             tokens_out=self.extra_tokens_out + (self.stream.tokens_out if self.stream else 0),
             prompt_version=self.prompt_version,
         )
+        if self.ctx.answer_created_at is not None:
+            message.created_at = self.ctx.answer_created_at
         async with self._session_factory() as db:
             db.add(message)
             await db.commit()
```

```diff
--- a/backend/app/modules/tutor/service.py
+++ b/backend/app/modules/tutor/service.py
@@ -1,9 +1,10 @@
 import uuid
+from datetime import datetime
 
 from sqlalchemy import select
 from sqlalchemy.ext.asyncio import AsyncSession
 
-from app.ai.retrieval import SearchScope, count_ready_chunks
+from app.ai.retrieval import SearchScope
 from app.core.config import get_settings
 from app.core.errors import AppError, not_found
 from app.core.pagination import PageParams, paginate
@@ -21,11 +22,8 @@
     SessionOut,
     SessionPage,
 )
+from app.modules.tutor.state import describe, scope_state
 
-NOT_READY_MESSAGE = "Tài liệu đang được xử lý"
-# Tìm tài liệu theo phạm vi cả khóa chỉ xét khóa đã publish; chủ khóa/admin mở được phiên trên khóa nháp nên cần
-# thông báo riêng thay vì "đang xử lý" (tài liệu có thể đã xong).
-DRAFT_COURSE_SCOPE_MESSAGE = "Hỏi cả khóa chỉ dùng được khi khóa đã xuất bản"
 HISTORY_LIMIT = 4  # số tin nhắn gần nhất dùng để viết lại câu hỏi (spec 5.3 bước 1)
 RATE_WINDOW_S = 3600
 
@@ -104,22 +102,26 @@
 async def availability(
     db: AsyncSession, user: User, course_id: uuid.UUID, lesson_id: uuid.UUID | None, embedding_model: str
 ) -> AvailabilityOut:
+    """Hỏi được chưa, nếu chưa thì vì sao (xem tutor/state.py). Tìm theo cả khóa chỉ xét khóa đã publish; chủ
+    khóa/admin mở được phiên trên khóa nháp nên có trạng thái riêng 'draft'."""
     course, lesson = await resolve_scope(db, user, course_id, lesson_id)
-    n = await count_ready_chunks(db, SearchScope(course.id, lesson.id if lesson else None), embedding_model)
-    if lesson is None and course.status != CourseStatus.published:
-        return AvailabilityOut(available=False, ready_chunks=n, message=DRAFT_COURSE_SCOPE_MESSAGE)
-    return AvailabilityOut(available=n > 0, ready_chunks=n, message=None if n else NOT_READY_MESSAGE)
+    st = await scope_state(db, SearchScope(course.id, lesson.id if lesson else None), embedding_model)
+    return describe(st, draft_course_scope=lesson is None and course.status != CourseStatus.published)
 
 
 async def load_history(
-    db: AsyncSession, session_id: uuid.UUID, limit: int = HISTORY_LIMIT
+    db: AsyncSession, session_id: uuid.UUID, limit: int = HISTORY_LIMIT, *, before: datetime | None = None
 ) -> list[tuple[ChatRole, str]]:
     """Tối đa `limit` tin nhắn gần nhất (bỏ tin rỗng do lỗi), xếp cũ → mới theo đúng thứ tự của list_messages
-    (created_at, role, id): lấy theo thứ tự đảo ngược rồi đảo lại."""
+    (created_at, role, id): lấy theo thứ tự đảo ngược rồi đảo lại. before: chỉ lấy tin trước thời điểm này
+    (câu hỏi chờ trả lời muộn chỉ dùng lịch sử trước nó)."""
+    conds = [ChatMessage.session_id == session_id, ChatMessage.content != ""]
+    if before is not None:
+        conds.append(ChatMessage.created_at < before)
     rows = (
         await db.execute(
             select(ChatMessage.role, ChatMessage.content)
-            .where(ChatMessage.session_id == session_id, ChatMessage.content != "")
+            .where(*conds)
             .order_by(ChatMessage.created_at.desc(), ChatMessage.role.desc(), ChatMessage.id.desc())
             .limit(limit)
         )
```

- [x] **Bước 6: `tutor/waiting.py`**

```python
"""Câu hỏi chờ tài liệu: học viên hỏi lúc tài liệu còn đang xử lý, AI trả lời ngay khi xử lý xong.

Luồng:
1. API `POST /tutor/sessions/{id}/questions` (queue_question): chỉ nhận khi phạm vi chưa có chunk nào và còn
   tài liệu đang xử lý; lưu câu hỏi với waiting_for_docs = true (tính lượt rate limit như câu hỏi thường).
2. Worker xử lý PDF xong (thành công hay lỗi) thì xếp job `tutor_waiting` cho bài đó; cron 5 phút vét phần sót.
3. answer_waiting: nhận từng câu (UPDATE có điều kiện, nên job và cron chạy song song không trả lời hai lần),
   kiểm quyền lại, chạy đúng luồng trả lời của AI Tutor (answer_stream) và lưu câu trả lời ngay sau câu hỏi.
   Tài liệu xử lý lỗi hết (không còn gì để đọc) thì trả lời bằng một thông báo thay vì để câu hỏi chờ mãi."""

import logging
import time
import uuid
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.llm_client import LLMClient
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.ratelimit import RateLimiter, rate_limited
from app.modules.auth.models import Role, User
from app.modules.courses.models import CourseStatus, Lesson, Section
from app.modules.tutor.answer import AskContext, answer_stream
from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
from app.modules.tutor.service import (
    RATE_WINDOW_S,
    get_own_session,
    load_history,
    resolve_scope,
    scope_of,
)
from app.modules.tutor.state import describe, scope_state

logger = logging.getLogger(__name__)

MAX_WAITING_PER_SESSION = 5
DOCS_FAILED_ANSWER = (
    "Tài liệu của bài này xử lý không thành công nên AI chưa trả lời được câu hỏi này. "
    "Bạn hãy hỏi lại sau khi giảng viên tải lại tài liệu."
)


async def queue_question(
    db: AsyncSession,
    limiter: RateLimiter,
    user: User,
    session_id: uuid.UUID,
    question: str,
    embedding_model: str,
) -> ChatMessage:
    """Kiểm quyền như câu hỏi thường, rồi chỉ nhận khi trạng thái là 'processing' (409 nếu không), tối đa
    MAX_WAITING_PER_SESSION câu chờ mỗi phiên. Rate limit đứng sau các kiểm tra: bị từ chối thì không tốn lượt."""
    session = await get_own_session(db, session_id, user)
    course, lesson = await resolve_scope(db, user, session.course_id, session.lesson_id)
    st = await scope_state(db, scope_of(session), embedding_model)
    info = describe(st, draft_course_scope=lesson is None and course.status != CourseStatus.published)
    if info.state == "ready":
        raise AppError("TUTOR_READY", "Tài liệu đã sẵn sàng, hãy hỏi trực tiếp", 409)
    if not info.can_queue:
        raise AppError("NOT_PROCESSING", info.message or "Chưa hỏi được AI Tutor", 409)
    waiting = await db.scalar(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == session.id, ChatMessage.waiting_for_docs
        )
    )
    if waiting >= MAX_WAITING_PER_SESSION:
        raise AppError(
            "TOO_MANY_WAITING",
            f"Bạn đã có {MAX_WAITING_PER_SESSION} câu hỏi đang chờ, hãy đợi tài liệu xử lý xong",
            409,
        )
    if user.role == Role.student:
        retry_after = await limiter.hit(
            f"tutor:{user.id}", get_settings().tutor_rate_limit_per_hour, RATE_WINDOW_S
        )
        if retry_after is not None:
            raise rate_limited(retry_after)
    message = ChatMessage(session_id=session.id, role=ChatRole.user, content=question, waiting_for_docs=True)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


def _waiting_in_lesson(lesson_id: uuid.UUID):
    """Câu chờ có thể được trả lời khi tài liệu của bài này xử lý xong: phiên theo bài này, hoặc phiên theo cả
    khóa chứa bài này."""
    course_of_lesson = (
        select(Section.course_id)
        .join(Lesson, Lesson.section_id == Section.id)
        .where(Lesson.id == lesson_id)
        .scalar_subquery()
    )
    return or_(
        ChatSession.lesson_id == lesson_id,
        (ChatSession.lesson_id.is_(None)) & (ChatSession.course_id == course_of_lesson),
    )


async def has_waiting(db: AsyncSession, lesson_id: uuid.UUID) -> bool:
    stmt = (
        select(ChatMessage.id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.waiting_for_docs, _waiting_in_lesson(lesson_id))
        .limit(1)
    )
    return await db.scalar(stmt) is not None


async def _never_disconnected() -> bool:
    return False


async def _answer_one(
    message_id: uuid.UUID,
    llm: LLMClient,
    embedder: Embedder,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> bool:
    """Trả lời một câu chờ. False = chưa đến lúc (tài liệu còn đang xử lý) hoặc đã có worker khác nhận."""
    async with session_factory() as db:
        row = (
            await db.execute(
                select(ChatSession, User)
                .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
                .join(User, User.id == ChatSession.user_id)
                .where(ChatMessage.id == message_id, ChatMessage.waiting_for_docs)
            )
        ).first()
        if row is None:
            return False
        session, user = row
        try:
            course, _ = await resolve_scope(db, user, session.course_id, session.lesson_id)
        except AppError:
            course = None  # mất quyền (bị hủy đăng ký, khóa bị gỡ publish...): bỏ câu chờ, không trả lời
        st = await scope_state(db, scope_of(session), embedder.model) if course is not None else None
        if st is not None and st.ready_chunks == 0 and st.processing_docs > 0:
            return False
        # Nhận câu hỏi bằng UPDATE có điều kiện: job và cron chạy song song cũng chỉ một bên trả lời
        claimed = (
            await db.execute(
                update(ChatMessage)
                .where(ChatMessage.id == message_id, ChatMessage.waiting_for_docs)
                .values(waiting_for_docs=False)
                .returning(ChatMessage.content, ChatMessage.created_at)
            )
        ).first()
        if claimed is None:
            return False
        question, asked_at = claimed
        history = await load_history(db, session.id, before=asked_at) if course is not None else []
        await db.commit()

    if course is None:
        logger.info("Bỏ câu hỏi chờ %s: người hỏi không còn quyền", message_id)
        return True
    if st.ready_chunks == 0:
        await _save_notice(session_factory, session.id, asked_at, DOCS_FAILED_ANSWER)
        return True
    ctx = AskContext(
        session_id=session.id,
        scope=scope_of(session),
        course_title=course.title,
        question=question,
        history=history,
        answer_created_at=asked_at,
    )
    # Cùng luồng với câu hỏi trực tiếp (viết lại câu hỏi, tìm tài liệu, chốt chặn, lưu); không có client nên
    # chỉ chạy hết stream. Lỗi AI → answer_stream tự lưu câu trả lời dở (truncated) như mọi đường lỗi.
    async for _ in answer_stream(
        ctx,
        llm=llm,
        embedder=embedder,
        is_disconnected=_never_disconnected,
        session_factory=session_factory,
        settings=settings,
    ):
        pass
    return True


async def _save_notice(
    session_factory: async_sessionmaker, session_id: uuid.UUID, asked_at: datetime, text: str
) -> None:
    async with session_factory() as db:
        db.add(
            ChatMessage(
                session_id=session_id,
                role=ChatRole.assistant,
                content=text,
                refused=True,
                created_at=asked_at,
            )
        )
        await db.commit()


async def answer_waiting(
    llm: LLMClient,
    embedder: Embedder,
    *,
    lesson_id: uuid.UUID | None = None,
    session_factory: async_sessionmaker = SessionLocal,
    settings: Settings | None = None,
    budget_s: float | None = None,
) -> int:
    """Trả lời các câu chờ (cũ trước), trong một bài (job sau khi xử lý PDF) hoặc tất cả (cron). Trả về số câu
    đã xử lý. budget_s: hết thời gian thì dừng nhận câu mới (câu còn lại để lần sau), tránh job bị arq hủy giữa
    chừng. Lỗi ở một câu chỉ ghi log rồi làm câu tiếp theo."""
    s = settings or get_settings()
    stmt = (
        select(ChatMessage.id)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.waiting_for_docs)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    if lesson_id is not None:
        stmt = stmt.where(_waiting_in_lesson(lesson_id))
    async with session_factory() as db:
        ids = list(await db.scalars(stmt))
    started = time.monotonic()
    done = 0
    for message_id in ids:
        if budget_s is not None and time.monotonic() - started > budget_s:
            break
        try:
            if await _answer_one(message_id, llm, embedder, session_factory, s):
                done += 1
        except Exception:
            logger.exception("Không trả lời được câu hỏi chờ %s", message_id)
    return done
```

- [x] **Bước 7: Endpoint**

```diff
--- a/backend/app/modules/tutor/router.py
+++ b/backend/app/modules/tutor/router.py
@@ -11,7 +11,7 @@
 from app.core.pagination import PageParams, page_params
 from app.core.ratelimit import RateLimiter, get_rate_limiter
 from app.modules.auth.models import User
-from app.modules.tutor import service
+from app.modules.tutor import service, waiting
 from app.modules.tutor.answer import answer_stream
 from app.modules.tutor.schemas import (
     AskIn,
@@ -106,6 +106,28 @@
     )
 
 
+@router.post(
+    "/tutor/sessions/{session_id}/questions",
+    response_model=MessageOut,
+    status_code=202,
+    responses={409: {"description": "TUTOR_READY | NOT_PROCESSING | TOO_MANY_WAITING"}},
+)
+async def queue_question(
+    session_id: uuid.UUID,
+    data: AskIn,
+    user: User = Depends(get_current_user),
+    db: AsyncSession = Depends(get_db),
+    embedder: Embedder = Depends(get_api_embedder),
+    limiter: RateLimiter = Depends(get_rate_limiter),
+):
+    """Gửi câu hỏi lúc tài liệu còn đang xử lý (availability.can_queue): lưu câu hỏi với waiting_for_docs, AI trả
+    lời khi xử lý xong (worker). Frontend tải lại danh sách tin nhắn để thấy câu trả lời.
+
+    409 TUTOR_READY khi đã hỏi trực tiếp được; 409 NOT_PROCESSING khi không còn tài liệu nào đang xử lý (lý do
+    trong message); 409 TOO_MANY_WAITING khi phiên đã có 5 câu chờ; 429 như câu hỏi thường."""
+    return await waiting.queue_question(db, limiter, user, session_id, data.content, embedder.model)
+
+
 @router.post("/tutor/messages/{message_id}/feedback", response_model=MessageOut)
 async def feedback(
     message_id: uuid.UUID,
```

- [x] **Bước 8: Worker**

Sau `ingest_pdf` (xong **hoặc** lỗi) mà bài có câu chờ thì xếp `tutor_waiting`. Dùng `create_and_enqueue` nên trùng job đang chạy cho cùng bài thì không tạo thêm (index `uq_active_job`), và sweeper đã có sẵn dọn job treo.

```diff
--- a/backend/app/worker/tasks.py
+++ b/backend/app/worker/tasks.py
@@ -19,6 +19,7 @@
 from app.modules.quiz.generation import QuizGenerationError, generate_questions_for_lesson
 from app.modules.quiz.schemas import QuizGenerateIn
 from app.modules.studio.jobs import run_notes_synth, run_source_guide, run_studio
+from app.modules.tutor.waiting import answer_waiting, has_waiting
 
 logger = logging.getLogger(__name__)
 
@@ -29,7 +30,12 @@
     "source_guide": 300,
     "studio_gen": 900,
     "notes_synth": 300,
+    "tutor_waiting": 600,
 }
+# tutor_waiting dừng nhận câu hỏi mới khi còn chừng này giây trước hạn của handler (một câu trả lời có thể mất
+# vài chục giây); câu còn lại để job sau hoặc cron.
+TUTOR_WAITING_RESERVE_S = 120
+TUTOR_WAITING_CRON_BUDGET_S = 180
 # Handler bị hủy sớm hơn job_timeout của arq một khoảng này, để run_job kịp ghi job + source failed
 # ngay (arq hủy ở đúng job_timeout thì không còn cơ hội ghi, phải đợi sweeper).
 JOB_TIMEOUT_MARGIN_S = 30
@@ -131,6 +137,11 @@
 
     await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("ingest_pdf"))
     await _queue_source_guide(ctx, uuid.UUID(job_id), session_factory)
+    await _queue_waiting_answers(ctx, uuid.UUID(job_id), session_factory)
+
+
+def _queue_of(ctx: dict) -> JobQueue | None:
+    return ctx.get("queue") or (ArqQueue(pool=ctx["redis"]) if "redis" in ctx else None)
 
 
 async def _queue_source_guide(
@@ -138,7 +149,7 @@
 ) -> None:
     """Xử lý PDF xong (job done) thì xếp hàng job hướng dẫn tài liệu (AI Studio S1). Lỗi chỉ ghi log: hướng dẫn
     là phần phụ, không làm hỏng việc xử lý tài liệu."""
-    queue = ctx.get("queue") or (ArqQueue(pool=ctx["redis"]) if "redis" in ctx else None)
+    queue = _queue_of(ctx)
     if queue is None:  # test chạy job ingest đơn lẻ, không có hàng đợi
         return
     try:
@@ -151,6 +162,54 @@
         logger.exception("Không xếp hàng được job hướng dẫn tài liệu cho job %s", ingest_job_id)
 
 
+async def _queue_waiting_answers(
+    ctx: dict, ingest_job_id: uuid.UUID, session_factory: async_sessionmaker
+) -> None:
+    """Xử lý PDF kết thúc (xong hoặc lỗi) mà bài có câu hỏi chờ thì xếp job tutor_waiting (ref_id = lessons.id).
+    Lỗi ở đây chỉ ghi log: cron answer_waiting_cron sẽ vét lại."""
+    queue = _queue_of(ctx)
+    if queue is None:
+        return
+    try:
+        async with session_factory() as db:
+            job = await db.get(Job, ingest_job_id)
+            if job is None or job.status not in (JobStatus.done, JobStatus.failed):
+                return
+            lesson_id = await db.scalar(select(Source.lesson_id).where(Source.id == job.ref_id))
+            if lesson_id is None or not await has_waiting(db, lesson_id):
+                return
+            await create_and_enqueue(db, queue, "tutor_waiting", lesson_id, created_by=None)
+    except Exception:
+        logger.exception("Không xếp hàng được job trả lời câu hỏi chờ cho job %s", ingest_job_id)
+
+
+async def tutor_waiting(ctx: dict, job_id: str) -> None:
+    """Trả lời câu hỏi chờ của một bài: ref_id = lessons.id."""
+    session_factory = ctx.get("session_factory", SessionLocal)
+    timeout_s = handler_timeout("tutor_waiting")
+
+    async def handler(lesson_id: uuid.UUID) -> None:
+        await answer_waiting(
+            ctx["llm"],
+            ctx["embedder"],
+            lesson_id=lesson_id,
+            session_factory=session_factory,
+            budget_s=timeout_s - TUTOR_WAITING_RESERVE_S,
+        )
+
+    await run_job(job_id, handler, session_factory, timeout_s=timeout_s)
+
+
+async def answer_waiting_cron(ctx: dict) -> int:
+    """Cron 5 phút: vét câu hỏi chờ mà job sau xử lý PDF bị lỡ (Redis mất job, tài liệu bị sweeper chốt lỗi...)."""
+    return await answer_waiting(
+        ctx["llm"],
+        ctx["embedder"],
+        session_factory=ctx.get("session_factory", SessionLocal),
+        budget_s=TUTOR_WAITING_CRON_BUDGET_S,
+    )
+
+
 async def source_guide(ctx: dict, job_id: str) -> None:
     """Hướng dẫn tài liệu: ref_id = sources.id."""
     session_factory = ctx.get("session_factory", SessionLocal)
```

```diff
--- a/backend/app/worker/settings.py
+++ b/backend/app/worker/settings.py
@@ -12,6 +12,7 @@
 from app.modules.notify.mailer import SmtpMailer
 from app.worker.tasks import (
     JOB_TIMEOUTS,
+    answer_waiting_cron,
     ingest_pdf,
     notes_synth,
     quiz_gen,
@@ -19,6 +20,7 @@
     source_guide,
     studio_gen,
     sweep_stale_jobs,
+    tutor_waiting,
 )
 
 
@@ -42,6 +44,7 @@
         func(source_guide, name="source_guide", timeout=JOB_TIMEOUTS["source_guide"]),
         func(studio_gen, name="studio_gen", timeout=JOB_TIMEOUTS["studio_gen"]),
         func(notes_synth, name="notes_synth", timeout=JOB_TIMEOUTS["notes_synth"]),
+        func(tutor_waiting, name="tutor_waiting", timeout=JOB_TIMEOUTS["tutor_waiting"]),
     ]
     # 5 phút một lần: job processing quá timeout + 5 phút → failed "Worker bị gián đoạn";
     # job pending bị kẹt → enqueue lại một lần, vẫn kẹt → failed "Không đưa được job vào hàng đợi"
@@ -61,6 +64,13 @@
             run_at_startup=True,
             timeout=120,
         ),
+        # Vét câu hỏi chờ tài liệu mà job tutor_waiting bị lỡ (lệch 2 phút so với sweeper)
+        cron(
+            answer_waiting_cron,
+            name="answer_waiting_cron",
+            minute=set(range(2, 60, 5)),
+            timeout=300,
+        ),
     ]
     on_startup = startup
     redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
```

- [x] **Bước 9: Chạy test**

```powershell
uv run pytest tests/test_tutor_waiting.py tests/test_tutor_sessions.py tests/test_tutor_answer.py tests/test_tutor_api.py tests/test_worker.py tests/test_studio.py -q
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
```

Kỳ vọng: pass hết; 5 hợp đồng KEPT.

- [x] **Bước 10: Commit**

```powershell
git add backend
git commit -m "feat(tutor): hỏi lúc tài liệu đang xử lý (câu chờ, worker trả lời sau) + trạng thái tài liệu rõ ràng"
```

---

## Task 2: Frontend

**Files:**
- Regenerate: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`
- Modify: `frontend/src/lib/tutor/types.ts`, `use-tutor-chat.ts`
- Modify: `frontend/src/components/tutor/tutor-panel.tsx`
- Test: `frontend/src/lib/tutor/use-tutor-chat-waiting.test.tsx` (mới)

- [x] **Bước 1:** `cd frontend; npm run gen:api` (kỳ vọng: `AvailabilityOut` có `state`, `processing_docs`, `can_queue`; có path `/questions`).

- [x] **Bước 2: Test (sẽ fail)**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TutorPanel } from "@/components/tutor/tutor-panel";
import { api, server } from "@/test/msw";
import { useTutorChat, WAIT_POLL_MS } from "./use-tutor-chat";

const PROCESSING = {
  available: false,
  ready_chunks: 0,
  message: "Tài liệu đang được xử lý (1 tài liệu). Bạn vẫn có thể đặt câu hỏi: AI sẽ trả lời ngay khi xử lý xong.",
  state: "processing",
  processing_docs: 1,
  can_queue: true,
};
const FAILED = {
  available: false,
  ready_chunks: 0,
  message: "Tài liệu xử lý không thành công.",
  state: "failed",
  processing_docs: 0,
  can_queue: false,
};

function msg(id: string, role: "user" | "assistant", content: string, waiting = false) {
  return {
    id,
    role,
    content,
    citations: [],
    refused: false,
    truncated: false,
    feedback: null,
    waiting_for_docs: waiting,
    created_at: "2026-10-12T00:00:00Z",
  };
}

function handlers(availability: object) {
  server.use(
    http.get(api("/tutor/availability"), () => HttpResponse.json(availability)),
    http.get(api("/tutor/sessions"), () => HttpResponse.json({ items: [], total: 0, page: 1, size: 100 })),
    http.post(api("/tutor/sessions"), () =>
      HttpResponse.json({ id: "s1", course_id: "c1", lesson_id: "l1", created_at: "2026-10-12T00:00:00Z" }, { status: 201 }),
    ),
  );
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

afterEach(() => vi.useRealTimers());

describe("useTutorChat: hỏi lúc tài liệu đang xử lý", () => {
  it("gửi câu hỏi chờ qua /questions (không mở stream), câu hỏi hiện trạng thái chờ", async () => {
    handlers(PROCESSING);
    let streamed = false;
    let body: unknown = null;
    server.use(
      http.post(api("/tutor/sessions/s1/messages"), () => {
        streamed = true;
        return HttpResponse.json({});
      }),
      http.post(api("/tutor/sessions/s1/questions"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(msg("q1", "user", "Đạo hàm là gì?", true), { status: 202 });
      }),
    );
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.availability?.can_queue).toBe(true));
    await act(() => result.current.send("Đạo hàm là gì?"));
    expect(body).toEqual({ content: "Đạo hàm là gì?" });
    expect(streamed).toBe(false);
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({ id: "q1", role: "user", status: "waiting" });
  });

  it("409 khi gửi câu chờ → báo lỗi ngay dưới câu hỏi", async () => {
    handlers(PROCESSING);
    server.use(
      http.post(api("/tutor/sessions/s1/questions"), () =>
        HttpResponse.json(
          { error: { code: "TOO_MANY_WAITING", message: "Bạn đã có 5 câu hỏi đang chờ" } },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.availability?.can_queue).toBe(true));
    await act(() => result.current.send("Câu thứ sáu"));
    expect(result.current.messages[0]).toMatchObject({ status: "error", error: "Bạn đã có 5 câu hỏi đang chờ" });
  });

  it("câu chờ được trả lời: hỏi lại định kỳ rồi thay bằng câu trả lời của server", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    handlers(PROCESSING);
    let answered = false;
    server.use(
      http.get(api("/tutor/sessions"), () =>
        HttpResponse.json({
          items: [{ id: "s1", course_id: "c1", lesson_id: "l1", created_at: "2026-10-12T00:00:00Z" }],
          total: 1,
          page: 1,
          size: 100,
        }),
      ),
      http.get(api("/tutor/sessions/s1/messages"), () =>
        HttpResponse.json({
          items: answered
            ? [msg("q1", "user", "Đạo hàm là gì?"), msg("a1", "assistant", "Là giới hạn [1].")]
            : [msg("q1", "user", "Đạo hàm là gì?", true)],
          total: answered ? 2 : 1,
          page: 1,
          size: 100,
        }),
      ),
    );
    const { result } = renderHook(() => useTutorChat({ courseId: "c1", lessonId: "l1" }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.messages[0]?.status).toBe("waiting"));
    await act(() => vi.advanceTimersByTimeAsync(WAIT_POLL_MS));
    expect(result.current.messages).toHaveLength(1); // chưa trả lời: giữ nguyên
    answered = true;
    await act(() => vi.advanceTimersByTimeAsync(WAIT_POLL_MS));
    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    expect(result.current.messages[0].status).toBe("done");
    expect(result.current.messages[1]).toMatchObject({ id: "a1", role: "assistant", content: "Là giới hạn [1]." });
  });
});

describe("TutorPanel: trạng thái tài liệu", () => {
  function Harness() {
    const chat = useTutorChat({ courseId: "c1", lessonId: "l1" });
    return <TutorPanel chat={chat} lessonId="l1" />;
  }

  it("đang xử lý: vẫn nhập và gửi được, có lời nhắn AI sẽ trả lời sau", async () => {
    handlers(PROCESSING);
    render(<Harness />, { wrapper: wrapper() });
    expect(await screen.findByText(/AI sẽ trả lời ngay khi xử lý xong/)).toBeInTheDocument();
    const input = screen.getByLabelText("Câu hỏi cho AI Tutor");
    await waitFor(() => expect(input).toBeEnabled());
    expect(input).toHaveAttribute("placeholder", expect.stringMatching(/khi tài liệu xử lý xong/));
    fireEvent.change(input, { target: { value: "Hỏi trước" } });
    expect(screen.getByRole("button", { name: /Gửi/ })).toBeEnabled();
  });

  it("xử lý lỗi: hiện đúng lý do, khóa ô nhập", async () => {
    handlers(FAILED);
    render(<Harness />, { wrapper: wrapper() });
    expect(await screen.findByText("Tài liệu xử lý không thành công.")).toBeInTheDocument();
    expect(screen.getByLabelText("Câu hỏi cho AI Tutor")).toBeDisabled();
  });
});
```

- [x] **Bước 3: Kiểu + hook**

- `send`: availability chưa sẵn sàng mà `can_queue` → gửi câu chờ (`POST /questions`), không mở stream. 409 thì tải lại availability; lỗi hiện ngay dưới câu hỏi.
- availability tự hỏi lại mỗi 5 giây khi `state = "processing"`.
- Còn câu chờ (đã có id server) và không có stream nào → hỏi lại danh sách tin nhắn mỗi 5 giây; số câu chờ giảm thì thay bằng dữ liệu server và báo toast.

```diff
--- a/frontend/src/lib/tutor/types.ts
+++ b/frontend/src/lib/tutor/types.ts
@@ -5,7 +5,8 @@
 /** Một nguồn trong event `sources` (có thêm phần hiển thị so với Citation). */
 export type Source = Citation & { lesson_title: string; heading_path: string; snippet: string };
 
-export type ChatStatus = "streaming" | "done" | "error" | "stopped";
+/** waiting: câu hỏi (role user) gửi lúc tài liệu đang xử lý, AI sẽ trả lời khi xử lý xong. */
+export type ChatStatus = "streaming" | "done" | "error" | "stopped" | "waiting";
 
 export type ChatMessage = {
   id: string; // id tạm "local-…" cho tới khi nhận `done`
```

```diff
--- a/frontend/src/lib/tutor/use-tutor-chat.ts
+++ b/frontend/src/lib/tutor/use-tutor-chat.ts
@@ -2,6 +2,7 @@
 
 import { useQuery } from "@tanstack/react-query";
 import * as React from "react";
+import { toast } from "sonner";
 import { api, apiBase, authFetch, unwrap } from "@/lib/api/client";
 import { ApiError, errorMessage, toApiError } from "@/lib/api/errors";
 import { readSse } from "@/lib/api/sse";
@@ -10,6 +11,8 @@
 type Scope = { courseId: string; lessonId: string | null };
 
 const AI_ERROR = "AI Tutor tạm thời không trả lời được. Câu hỏi của bạn đã được lưu, bấm Thử lại sau ít phút.";
+/** Chu kỳ hỏi lại server khi tài liệu đang xử lý / còn câu hỏi chờ trả lời. */
+export const WAIT_POLL_MS = 5000;
 
 function fromServer(m: {
   id: string;
@@ -19,8 +22,10 @@
   refused: boolean;
   truncated: boolean;
   feedback: number | null;
+  waiting_for_docs?: boolean;
 }): ChatMessage {
-  return { ...m, sources: [], status: m.truncated ? "stopped" : "done" };
+  const { waiting_for_docs, ...rest } = m;
+  return { ...rest, sources: [], status: waiting_for_docs ? "waiting" : m.truncated ? "stopped" : "done" };
 }
 
 /**
@@ -72,6 +77,8 @@
         }),
       ),
     enabled,
+    // Tài liệu đang xử lý: hỏi lại định kỳ để mở ô hỏi trực tiếp ngay khi xong
+    refetchInterval: (q) => (q.state.data?.state === "processing" ? WAIT_POLL_MS : false),
   });
 
   const history = useQuery({
@@ -113,10 +120,45 @@
     return s.id;
   };
 
+  /** Tài liệu đang xử lý: gửi câu hỏi chờ (POST /questions), AI trả lời khi xử lý xong. */
+  const queue = async (text: string) => {
+    setBusy(true);
+    const localId = `local-w-${Date.now()}`;
+    setMessages((ms) => [
+      ...ms,
+      { id: localId, role: "user", content: text, citations: [], sources: [], refused: false, truncated: false, feedback: null, status: "waiting" },
+    ]);
+    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
+      setMessages((ms) => ms.map((m) => (m.id === localId ? fn(m) : m)));
+    const isCurrent = () => true;
+    try {
+      const sid = await ensureSession(isCurrent);
+      const saved = await unwrap(
+        api.POST("/api/v1/tutor/sessions/{session_id}/questions", {
+          params: { path: { session_id: sid } },
+          body: { content: text },
+        }),
+      );
+      patch((m) => ({ ...m, id: saved.id }));
+    } catch (err) {
+      if (err instanceof ApiError && err.status === 429 && err.retryAfter) setRetryAt(Date.now() + err.retryAfter * 1000);
+      // 409: trạng thái đã đổi (vừa xử lý xong, hoặc lỗi) → tải lại availability để ô nhập theo đúng trạng thái
+      if (err instanceof ApiError && err.status === 409) void availability.refetch();
+      patch((m) => ({ ...m, status: "error", error: errorMessage(err) }));
+    } finally {
+      setBusy(false);
+    }
+  };
+
   const send = React.useCallback(
     async (content: string) => {
       const text = content.trim();
       if (!text || busy) return;
+      const avail = availability.data;
+      if (avail && !avail.available) {
+        if (avail.can_queue) await queue(text);
+        return;
+      }
       setBusy(true);
       const now = Date.now();
       setMessages((ms) => [
@@ -185,9 +227,41 @@
       }
     },
     // eslint-disable-next-line react-hooks/exhaustive-deps
-    [busy, sessionId, courseId, lessonId],
+    [busy, sessionId, courseId, lessonId, availability.data],
   );
 
+  // Còn câu hỏi chờ: hỏi lại danh sách tin nhắn định kỳ (khi không có stream nào đang chạy); có câu vừa được
+  // trả lời thì thay bằng dữ liệu server và báo cho học viên.
+  const waitingCount = messages.filter((m) => m.status === "waiting" && !m.id.startsWith("local-")).length;
+  React.useEffect(() => {
+    if (!enabled || !sessionId || busy || waitingCount === 0) return;
+    let cancelled = false;
+    const id = window.setInterval(async () => {
+      try {
+        const page = await unwrap(
+          api.GET("/api/v1/tutor/sessions/{session_id}/messages", {
+            params: { path: { session_id: sessionId }, query: { size: 100 } },
+          }),
+        );
+        if (cancelled) return;
+        const fresh = page.items.map(fromServer);
+        const stillWaiting = fresh.filter((m) => m.status === "waiting").length;
+        if (stillWaiting < waitingCount) {
+          setMessages(fresh);
+          void availability.refetch();
+          toast.success("AI đã trả lời câu hỏi bạn gửi lúc tài liệu đang xử lý");
+        }
+      } catch {
+        // lỗi mạng tạm thời: lần sau hỏi lại
+      }
+    }, WAIT_POLL_MS);
+    return () => {
+      cancelled = true;
+      window.clearInterval(id);
+    };
+    // eslint-disable-next-line react-hooks/exhaustive-deps
+  }, [enabled, sessionId, busy, waitingCount]);
+
   const clearRetry = React.useCallback(() => setRetryAt(null), []);
   const stop = React.useCallback(() => abortRef.current?.abort(), []);
 
```

- [x] **Bước 4: Panel**

```diff
--- a/frontend/src/components/tutor/tutor-panel.tsx
+++ b/frontend/src/components/tutor/tutor-panel.tsx
@@ -1,6 +1,6 @@
 "use client";
 
-import { BookmarkPlus, MessageCircleQuestion, RotateCcw, SendHorizontal, Sparkles, Square, ThumbsDown, ThumbsUp } from "lucide-react";
+import { BookmarkPlus, Clock, MessageCircleQuestion, RotateCcw, SendHorizontal, Sparkles, Square, ThumbsDown, ThumbsUp } from "lucide-react";
 import * as React from "react";
 import { toast } from "sonner";
 import { Markdown } from "@/components/content/markdown";
@@ -33,6 +33,10 @@
   const inputRef = React.useRef<HTMLTextAreaElement>(null);
   const countdown = useCountdown(chat.retryAt, chat.clearRetry);
   const unavailable = chat.availability && !chat.availability.available;
+  // Tài liệu đang xử lý: vẫn cho gửi câu hỏi, AI trả lời khi xử lý xong
+  const canQueue = !!unavailable && !!chat.availability?.can_queue;
+  const blocked = !!unavailable && !canQueue;
+  const stillProcessing = !unavailable ? (chat.availability?.processing_docs ?? 0) : 0;
 
   React.useEffect(() => {
     inputRef.current?.focus();
@@ -70,9 +74,7 @@
         ) : (
           chat.messages.map((m, i) =>
             m.role === "user" ? (
-              <div key={m.id} className="ml-auto max-w-[85%] rounded-lg bg-muted px-3 py-2 whitespace-pre-wrap">
-                {m.content}
-              </div>
+              <UserMessage key={m.id} m={m} />
             ) : (
               <AssistantMessage
                 key={m.id}
@@ -102,6 +104,10 @@
       <form onSubmit={submit} className="border-t p-3">
         {unavailable ? (
           <p className="mb-2 text-sm text-muted-foreground">{chat.availability?.message ?? "AI Tutor chưa sẵn sàng cho bài này."}</p>
+        ) : stillProcessing > 0 ? (
+          <p className="mb-2 text-xs text-muted-foreground">
+            Còn {stillProcessing} tài liệu đang xử lý; câu trả lời lúc này chỉ dựa trên tài liệu đã xử lý xong.
+          </p>
         ) : null}
         <div className="flex items-end gap-2">
           <label htmlFor="tutor-input" className="sr-only">
@@ -117,8 +123,12 @@
             }}
             rows={2}
             maxLength={2000}
-            disabled={!!unavailable || chat.loadingHistory}
-            placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
+            disabled={blocked || chat.loadingHistory}
+            placeholder={
+              canQueue
+                ? "Nhập câu hỏi… AI sẽ trả lời khi tài liệu xử lý xong"
+                : "Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
+            }
             className="max-h-40 min-h-11 flex-1 resize-none rounded-md border bg-surface px-3 py-2 text-base md:text-sm"
           />
           {chat.busy ? (
@@ -126,7 +136,7 @@
               <Square /> Dừng
             </Button>
           ) : (
-            <Button type="submit" disabled={!draft.trim() || countdown > 0 || !!unavailable || chat.loadingHistory}>
+            <Button type="submit" disabled={!draft.trim() || countdown > 0 || blocked || chat.loadingHistory}>
               <SendHorizontal /> {countdown > 0 ? `${countdown}s` : "Gửi"}
             </Button>
           )}
@@ -135,6 +145,23 @@
     </div>
   );
 }
+
+function UserMessage({ m }: { m: ChatMessage }) {
+  return (
+    <div className="ml-auto flex max-w-[85%] flex-col items-end gap-1">
+      <div className="rounded-lg bg-muted px-3 py-2 whitespace-pre-wrap">{m.content}</div>
+      {m.status === "waiting" ? (
+        <p className="flex items-center gap-1 text-xs text-muted-foreground">
+          <Clock className="size-3.5" aria-hidden /> Đang chờ tài liệu xử lý xong, AI sẽ trả lời ngay sau đó
+        </p>
+      ) : m.status === "error" ? (
+        <p role="alert" className="text-xs text-destructive">
+          {m.error}
+        </p>
+      ) : null}
+    </div>
+  );
+}
 
 function AssistantMessage({
   m,
```

- [x] **Bước 5: Kiểm tra + commit**

```powershell
npx tsc --noEmit ; npx eslint .
npx vitest run src/lib/tutor src/components/tutor
git add frontend
git commit -m "feat(web): gửi câu hỏi cho AI Tutor lúc tài liệu đang xử lý, tự hiện câu trả lời"
```

---

## Task 3: E2E

**Files:** Modify `frontend/e2e/mock-api.ts`; Create `frontend/e2e/tutor-waiting.spec.ts`

```diff
--- a/frontend/e2e/mock-api.ts
+++ b/frontend/e2e/mock-api.ts
@@ -114,7 +114,8 @@
     [`GET /lessons/${L2}`]: (r) => json(r, lesson(L2)),
     "GET /lessons/*/video": (r) => err(r, 404, "NOT_FOUND", "Video không tồn tại"),
     "PUT /lessons/*/progress": (r) => json(r, { status: "done", video_position_sec: 0, completed_at: "2026-10-01T00:00:00Z" }),
-    "GET /tutor/availability": (r) => json(r, { available: true, ready_chunks: 12, message: null }),
+    "GET /tutor/availability": (r) =>
+      json(r, { available: true, ready_chunks: 12, message: null, state: "ready", processing_docs: 0, can_queue: false }),
     "GET /tutor/sessions": (r) => json(r, { items: [], total: 0, page: 1, size: 20 }),
     "POST /tutor/sessions": (r) => json(r, { id: "s-1", course_id: COURSE_ID, lesson_id: L1, created_at: "2026-10-01T00:00:00Z" }, 201),
     "POST /tutor/sessions/s-1/messages": (r) => {
```

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, L1, mockApi } from "./mock-api";

const msg = (id: string, role: "user" | "assistant", content: string, waiting = false) => ({
  id,
  role,
  content,
  citations: [],
  refused: false,
  truncated: false,
  feedback: null,
  waiting_for_docs: waiting,
  created_at: "2026-10-12T00:00:00Z",
});

test("tài liệu đang xử lý: vẫn gửi được câu hỏi, AI trả lời khi xử lý xong", async ({ page }) => {
  let answered = false;
  await mockApi(page, {
    extra: {
      "GET /tutor/availability": (r) =>
        r.fulfill({
          json: answered
            ? { available: true, ready_chunks: 3, message: null, state: "ready", processing_docs: 0, can_queue: false }
            : {
                available: false,
                ready_chunks: 0,
                message: "Tài liệu đang được xử lý (1 tài liệu). Bạn vẫn có thể đặt câu hỏi: AI sẽ trả lời ngay khi xử lý xong.",
                state: "processing",
                processing_docs: 1,
                can_queue: true,
              },
        }),
      "POST /tutor/sessions/s-1/questions": (r) => r.fulfill({ status: 202, json: msg("q-1", "user", "Đạo hàm là gì?", true) }),
      "GET /tutor/sessions/s-1/messages": (r) =>
        r.fulfill({
          json: {
            items: answered
              ? [msg("q-1", "user", "Đạo hàm là gì?"), msg("a-1", "assistant", "Đạo hàm là giới hạn của tỉ số gia số.")]
              : [msg("q-1", "user", "Đạo hàm là gì?", true)],
            total: answered ? 2 : 1,
            page: 1,
            size: 100,
          },
        }),
      "POST /tutor/sessions": (r) =>
        r.fulfill({ status: 201, json: { id: "s-1", course_id: COURSE_ID, lesson_id: L1, created_at: "2026-10-12T00:00:00Z" } }),
    },
  });
  await page.goto(`/learn/giai-tich-1/${L1}`);
  await page.getByRole("button", { name: "Hỏi AI" }).first().click();
  await expect(page.getByText(/AI sẽ trả lời ngay khi xử lý xong/)).toBeVisible();
  const input = page.getByLabel("Câu hỏi cho AI Tutor");
  await expect(input).toBeEnabled();
  await input.fill("Đạo hàm là gì?");
  await input.press("Enter");
  await expect(page.getByText("Đang chờ tài liệu xử lý xong, AI sẽ trả lời ngay sau đó")).toBeVisible();
  await expectAccessible(page);
  await expectNoHorizontalScroll(page);

  answered = true;
  await expect(page.getByText("Đạo hàm là giới hạn của tỉ số gia số.")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("AI đã trả lời câu hỏi bạn gửi lúc tài liệu đang xử lý")).toBeVisible();
  await expect(page.getByText("Đang chờ tài liệu xử lý xong", { exact: false })).toBeHidden();
});
```

- [ ] Chạy: `npx playwright test e2e/tutor-waiting.spec.ts e2e/student.spec.ts e2e/studio.spec.ts` → pass. Rồi chạy cả bộ `npx playwright test` một lần.
- [ ] Commit: `git add frontend/e2e; git commit -m "test(e2e): hỏi AI lúc tài liệu đang xử lý"`.

---

## Task 4: Kiểm tay (bạn làm)

Sau khi pull: `cd backend; uv run alembic upgrade head`, rồi `docker compose up -d --build api worker` (**worker phải build lại** để có job và cron mới). `.env` để `fake` vẫn kiểm được hết (AI giả trả lời "đây là câu trả lời mô phỏng").

- [ ] Giảng viên tải một PDF nặng (slide "Kỹ thuật truyền thông") vào một bài. Học viên mở bài **ngay lúc đang xử lý** → AI Tutor báo "Tài liệu đang được xử lý (1 tài liệu). Bạn vẫn có thể đặt câu hỏi…", ô nhập mở.
- [ ] Gửi 2 câu liên tiếp → mỗi câu có dòng "Đang chờ tài liệu xử lý xong…". Không có bong bóng AI trống.
- [ ] Đợi xử lý xong (`docker compose logs -f worker`: thấy `ingest_pdf` xong rồi `tutor_waiting`) → trong ~5 giây trang hiện 2 câu trả lời đúng thứ tự, toast "AI đã trả lời…"; ô nhập chuyển sang hỏi trực tiếp (stream) bình thường.
- [ ] Đóng tab trong lúc chờ, mở lại sau khi xong: câu trả lời đã có sẵn trong hội thoại.
- [ ] Gửi 6 câu khi đang xử lý: câu thứ 6 báo "Bạn đã có 5 câu hỏi đang chờ…".
- [ ] Khóa "Thử Gemini" (tài liệu nhúng bằng model khác `.env` hiện tại): AI Tutor giờ báo "Tài liệu đã được xử lý bằng model AI khác…" thay vì "đang xử lý". Chạy `uv run python -m scripts.reembed` (plan OpenRouter) → hỏi được.
- [ ] Bài không có PDF: "Bài này chưa có tài liệu cho AI Tutor." PDF bị lỗi: "Tài liệu xử lý không thành công…".
- [ ] Điện thoại (F12, 375px): dòng chờ không tràn, trang không cuộn ngang.
