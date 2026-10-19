# Thảo luận theo bài (B4), thông báo realtime (B6), phân tích lớp học (B7): Kế hoạch triển khai

> **Dành cho agent thực thi:** BẮT BUỘC dùng `superpowers:subagent-driven-development` (khuyến nghị) hoặc `superpowers:executing-plans` để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Vì sao có plan này:** tầng A, B1–B3, B8 và tầng S (trừ deploy thật) đã xong. Ba mục tầng B còn lại mà làm được không cần OpenRouter trả phí là B4, B6 và B7. B5 (bài tập chấm rubric) không nằm trong plan này.

**Mục tiêu:**

1. **B4. Thảo luận dưới mỗi bài học**
   - Ai vào được bài (học viên đã đăng ký, giảng viên của khóa, admin) thì đọc và viết được.
   - Có 2 cấp: câu hỏi gốc và trả lời. Trả lời một câu trả lời thì nhận `422 INVALID_PARENT`.
   - Xóa là xóa mềm: còn dòng "Bình luận đã bị xóa." để giữ mạch trả lời.
   - Người được xóa là tác giả, giảng viên của khóa hoặc admin. Người khác nhận `404`.
   - Giới hạn 30 bình luận mỗi giờ mỗi người.
   - Giảng viên của khóa có nhãn "Giảng viên".
2. **B6. Thông báo realtime.** Chuông ở thanh trên (khung app và trang bài học) có số chưa đọc cập nhật ngay, không cần tải lại trang. Có các loại:
   - Có người trả lời câu hỏi của bạn.
   - Học viên đặt câu hỏi mới ở khóa bạn dạy.
   - Quiz mới được xuất bản ở khóa bạn đã đăng ký.
   - Tài liệu PDF xử lý xong hoặc lỗi; AI sinh câu hỏi xong hoặc lỗi. Hai loại này gửi cho người bấm chạy job.
3. **B7. Phân tích lớp học** nằm dưới trang Thống kê khóa học:
   - **Câu hỏi hay làm sai:** cần ít nhất 3 lượt trả lời mới được xếp hạng. Mỗi câu kèm phương án sai hay bị chọn nhất và trang tài liệu nguồn, bấm vào thì mở ngân hàng câu hỏi của bài.
   - **Bài học cần xem lại:** điểm quiz trung bình thấp nhất, rồi tới bài có nhiều câu hỏi AI Tutor nhất.
   - **Học viên cần để ý:** chưa xong khóa và điểm trung bình dưới 50%, hoặc 7 ngày không học.

**Thiết kế thông báo realtime:**

- Bảng `notifications` trong DB là nguồn dữ liệu. Thông báo được ghi **cùng transaction** với sự kiện (bình luận, xuất bản quiz, job xong).
- Sau khi commit, server bắn một tín hiệu rỗng lên Redis kênh `notif:{user_id}`. Redis lỗi thì chỉ ghi log, không làm hỏng thao tác chính.
- Luồng `GET /me/notifications/stream` (SSE) không giữ kết nối DB suốt luồng. Khi có tín hiệu, hoặc cứ 25 giây, nó mở một session ngắn, đọc số chưa đọc rồi gửi đi. Không có gì mới thì gửi dòng `: ping`.
- Mất Redis thì vẫn chạy, chỉ chậm tối đa 25 giây.
- Frontend đọc SSE bằng `fetch` có header Bearer, như AI Tutor, nên **không cần stream-token**. Spec cũ ghi `stream-token` + `EventSource`, plan này sửa lại spec.
- Mất kết nối thì frontend tự nối lại sau 2 giây, rồi gấp đôi mỗi lần lỗi, tối đa 30 giây.

**Kiến trúc:**

- Module mới `inbox` thuộc tầng base, là lá: không import `courses`, `jobs`... Hợp đồng `inbox-is-leaf` trong `.importlinter` giữ điều này.
- Module `discussion` là feature.
- `quiz` và `worker` gọi `inbox.service.add`.

**Migration:** `b9e1d4c7a352` (sau `a6d3f0c8e217`) tạo `lesson_comments` và `notifications`. Docker Compose tự chạy `alembic upgrade head` khi khởi động API.

**Thứ tự làm:** **sau** `2026-10-15-app-screens-plan.md`. Diff tạo trên HEAD `31161fc`.

**Mã trong plan đã được chạy thử** trên HEAD `31161fc`:

- **Backend:** **797 test pass** (786 + 11 mới). `ruff check`, `ruff format --check` sạch, `lint-imports` **6** hợp đồng KEPT. Migration lên/xuống sạch, `alembic check` không lệch so với model.
- **Frontend:** `tsc`, `eslint` sạch.
  - Unit test: **180 pass** (170 + 10 mới).
  - E2E cả bộ: **101 pass + 1 bỏ qua có chủ ý** (thêm 2 kịch bản × 2 kích thước màn hình, có kiểm axe).
- Đã chụp màn hình chuông thông báo, phần thảo luận (điện thoại) và trang phân tích để soát. Không trang nào bị cuộn ngang.

> **Ghi chú môi trường thử:** máy thử dùng pgvector 0.6, nên lúc chạy pytest đã tạm thay dòng `SET LOCAL hnsw.iterative_scan` bằng `pass` rồi trả lại nguyên trạng. Docker của bạn **không cần làm gì**.

Gõ **đúng** code trong plan. Nếu phải lệch thì ghi lý do vào commit. Commit **không** thêm dòng `Co-Authored-By` hay `Claude-Session`.

---

## Task 1: Backend: thông báo (B6) và thảo luận (B4)

**Files:**
- Create: `backend/app/modules/inbox/` (`__init__.py` rỗng, `models.py`, `hub.py`, `schemas.py`, `service.py`, `router.py`)
- Create: `backend/app/modules/discussion/` (`__init__.py` rỗng, `models.py`, `schemas.py`, `service.py`, `router.py`)
- Create: `backend/alembic/versions/b9e1d4c7a352_discussion_notifications.py`
- Create: `backend/tests/test_discussion.py`, `backend/tests/test_notifications.py`
- Modify: `backend/app/main.py`, `backend/app/models_registry.py`, `backend/.importlinter`, `backend/app/modules/quiz/quizzes.py`, `backend/app/modules/quiz/router.py`, `backend/app/worker/tasks.py`, `backend/tests/fakes.py`, `backend/tests/conftest.py`

- [x] **Bước 1: Hub giả và fixture cho test.**
  - `InMemoryHub` ghi lại các lần publish.
  - Mỗi lượt subscribe có một `asyncio.Event` để test luồng SSE.
  - Fixture `_worker_hub` tự động thay hub trong worker, để test cũ của `ingest_pdf`/`quiz_gen` không gọi Redis thật.

```diff
--- a/backend/tests/fakes.py
+++ b/backend/tests/fakes.py
@@ -1,3 +1,6 @@
+import asyncio
+from contextlib import asynccontextmanager
+
 from app.core.storage import download_headers
 
 
@@ -103,3 +106,36 @@
             self.fail_times -= 1
             raise ConnectionError("SMTP down")
         self.sent.append({"to": to, "subject": subject, "text": text, "html": html})
+
+
+class InMemoryHub:
+    """Hub thông báo giả: ghi lại ai được báo, và cho luồng SSE trong test chờ tín hiệu thật (asyncio.Event)."""
+
+    def __init__(self) -> None:
+        self.published: list[str] = []
+        self._events: dict[str, list] = {}
+
+    async def publish(self, user_ids: list[str]) -> None:
+        for uid in user_ids:
+            self.published.append(uid)
+            for ev in self._events.get(uid, []):
+                ev.set()
+
+    @asynccontextmanager
+    async def subscribe(self, user_id: str):
+        ev = asyncio.Event()
+        self._events.setdefault(user_id, []).append(ev)
+
+        class _Sub:
+            async def wait(self, timeout: float) -> bool:
+                try:
+                    await asyncio.wait_for(ev.wait(), timeout)
+                except TimeoutError:
+                    return False
+                ev.clear()
+                return True
+
+        try:
+            yield _Sub()
+        finally:
+            self._events[user_id].remove(ev)
```

```diff
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -30,9 +30,10 @@
 from app.core.ratelimit import get_rate_limiter
 from app.core.storage import get_storage
 from app.main import create_app
+from app.modules.inbox.hub import get_hub
 from app.modules.jobs.queue import get_queue
 from app.modules.notify.outbox import get_mail_kicker
-from tests.fakes import InMemoryRateLimiter, InMemoryStorage, RecordingKicker, RecordingQueue
+from tests.fakes import InMemoryHub, InMemoryRateLimiter, InMemoryStorage, RecordingKicker, RecordingQueue
 
 
 @pytest.fixture
@@ -65,13 +66,27 @@
 
 
 @pytest.fixture
-async def client(storage, queue, llm, limiter, kicker):
+def hub():
+    return InMemoryHub()
+
+
+@pytest.fixture(autouse=True)
+def _worker_hub(monkeypatch, hub):
+    """Worker tạo thông báo khi job xong (B6): dùng hub giả thay cho Redis thật."""
+    from app.worker import tasks
+
+    monkeypatch.setattr(tasks, "get_hub", lambda: hub)
+
+
+@pytest.fixture
+async def client(storage, queue, llm, limiter, kicker, hub):
     app = create_app()
     app.dependency_overrides[get_storage] = lambda: storage
     app.dependency_overrides[get_queue] = lambda: queue
     app.dependency_overrides[get_llm_client] = lambda: LLMClient(llm, get_settings(), sleep=_no_sleep)
     app.dependency_overrides[get_rate_limiter] = lambda: limiter
     app.dependency_overrides[get_mail_kicker] = lambda: kicker
+    app.dependency_overrides[get_hub] = lambda: hub
     async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
         yield c
 
```

- [x] **Bước 2: Test (sẽ fail)**

```python
"""B6: thông báo trong app (danh sách, đánh dấu đã đọc, luồng SSE) và các nơi tạo thông báo."""

import asyncio
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.inbox import service as inbox
from app.modules.inbox.models import Notification, NotificationKind
from app.modules.jobs.models import Job, JobStatus
from app.worker.tasks import _notify_job_owner
from tests.factories import make_question
from tests.helpers import API, make_published_course, make_student, make_teacher


async def _seed(user_id: str, n: int) -> None:
    async with SessionLocal() as db:
        for i in range(n):
            inbox.add(db, [uuid.UUID(user_id)], NotificationKind.quiz_published, f"Quiz {i}", f"/x/{i}")
            await db.commit()


async def test_list_read_one_read_all(client):
    sv_id, sv = await make_student(client)
    other_id, other = await make_student(client, "khac@x.com")
    await _seed(sv_id, 3)
    await _seed(other_id, 1)

    page = (await client.get(f"{API}/me/notifications", headers=sv)).json()
    assert page["total"] == 3 and page["unread"] == 3
    assert [i["title"] for i in page["items"]] == ["Quiz 2", "Quiz 1", "Quiz 0"]  # mới nhất trước
    first = page["items"][0]["id"]

    assert (await client.post(f"{API}/me/notifications/{first}/read", headers=other)).status_code == 404
    assert (await client.post(f"{API}/me/notifications/{first}/read", headers=sv)).status_code == 204
    assert (await client.get(f"{API}/me/notifications/unread", headers=sv)).json() == {"unread": 2}
    assert (await client.post(f"{API}/me/notifications/read-all", headers=sv)).status_code == 204
    assert (await client.get(f"{API}/me/notifications/unread", headers=sv)).json() == {"unread": 0}
    assert (await client.get(f"{API}/me/notifications/unread", headers=other)).json() == {"unread": 1}
    assert (await client.get(f"{API}/me/notifications")).status_code == 401


async def test_publishing_quiz_notifies_enrolled_students(client, db, hub):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    sv_id, sv = await make_student(client)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    q = await make_question(db, uuid.UUID(lesson["id"]))
    body = {"lesson_id": lesson["id"], "title": "Kiểm tra chương 1", "question_ids": [str(q.id)]}
    quiz = (await client.post(f"{API}/quizzes", json=body, headers=gv)).json()
    assert (await client.post(f"{API}/quizzes/{quiz['id']}/publish", headers=gv)).status_code == 200

    (item,) = (await client.get(f"{API}/me/notifications", headers=sv)).json()["items"]
    assert item["kind"] == "quiz_published" and item["title"] == "Quiz mới: Kiểm tra chương 1"
    assert item["link"] == f"/learn/{course['slug']}/{lesson['id']}/quiz/{quiz['id']}"
    assert sv_id in hub.published


async def test_worker_notifies_job_owner(client, hub):
    gv_id, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    async with SessionLocal() as db:
        ok = Job(
            type="quiz_gen",
            ref_id=uuid.UUID(lesson["id"]),
            status=JobStatus.done,
            created_by=uuid.UUID(gv_id),
        )
        bad = Job(
            type="quiz_gen",
            ref_id=uuid.UUID(lesson["id"]),
            status=JobStatus.failed,
            error_msg="Bài chưa có tài liệu đủ dài",
            created_by=uuid.UUID(gv_id),
        )
        db.add_all([ok, bad])
        await db.commit()
    await _notify_job_owner({"hub": hub}, ok.id, SessionLocal)
    await _notify_job_owner({"hub": hub}, bad.id, SessionLocal)

    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(Notification)
                .where(Notification.user_id == uuid.UUID(gv_id))
                .order_by(Notification.kind)
            )
        ).all()
    assert [(n.kind, n.link) for n in rows] == [
        ("questions_failed", f"/teach/{course['slug']}/lessons/{lesson['id']}/questions"),
        ("questions_ready", f"/teach/{course['slug']}/lessons/{lesson['id']}/questions"),
    ]
    assert rows[0].body == "Bài chưa có tài liệu đủ dài"
    assert hub.published.count(gv_id) == 2


async def test_stream_sends_count_then_updates_on_signal(client, hub):
    sv_id, _ = await make_student(client)
    await _seed(sv_id, 1)
    stop = asyncio.Event()

    async def disconnected() -> bool:
        return stop.is_set()

    events = inbox.notification_events(uuid.UUID(sv_id), hub, is_disconnected=disconnected, heartbeat_s=5)
    first = await anext(events)
    assert first.startswith("event: unread\n") and '"unread": 1' in first and '"title": "Quiz 0"' in first

    async def later():
        await asyncio.sleep(0.05)
        await _seed(sv_id, 1)
        await hub.publish([sv_id])

    task = asyncio.create_task(later())
    second = await asyncio.wait_for(anext(events), timeout=3)
    await task
    assert '"unread": 2' in second
    stop.set()
    await events.aclose()


async def test_stream_endpoint_requires_login(client):
    assert (await client.get(f"{API}/me/notifications/stream")).status_code == 401
```

```python
"""B4: thảo luận theo bài học (2 cấp, xóa mềm) và thông báo đi kèm (B6)."""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.inbox.models import Notification
from tests.helpers import API, make_published_course, make_student, make_teacher


async def _setup(client):
    gv_id, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    sv_id, sv = await make_student(client)
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    assert r.status_code == 201, r.text
    return gv_id, gv, sv_id, sv, course, lesson


async def _post(client, headers, lesson_id, body, parent_id=None):
    payload = {"body": body} | ({"parent_id": parent_id} if parent_id else {})
    return await client.post(f"{API}/lessons/{lesson_id}/comments", json=payload, headers=headers)


async def _notifications(user_id: str) -> list[Notification]:
    async with SessionLocal() as db:
        return list((await db.scalars(select(Notification).where(Notification.user_id == user_id))).all())


async def test_question_and_teacher_reply_with_notifications(client, hub):
    gv_id, gv, sv_id, sv, course, lesson = await _setup(client)

    r = await _post(client, sv, lesson["id"], "  Vì sao tìm kiếm nhị phân cần mảng đã sắp xếp?  ")
    assert r.status_code == 201, r.text
    root = r.json()
    assert root["body"] == "Vì sao tìm kiếm nhị phân cần mảng đã sắp xếp?"
    assert root["author_role"] == "student" and root["can_delete"] is True
    (n,) = await _notifications(gv_id)  # câu hỏi mới → báo giảng viên của khóa
    assert n.kind == "new_question" and n.link == f"/learn/{course['slug']}/{lesson['id']}#thao-luan"
    assert "Vì sao tìm kiếm nhị phân" in n.body and gv_id in hub.published

    r = await _post(client, gv, lesson["id"], "Vì mỗi bước loại được một nửa mảng.", root["id"])
    assert r.status_code == 201, r.text
    (n,) = await _notifications(sv_id)  # trả lời → báo tác giả bình luận gốc
    assert n.kind == "comment_reply" and n.title.endswith("trả lời bình luận của bạn")

    page = (await client.get(f"{API}/lessons/{lesson['id']}/comments", headers=sv)).json()
    assert page["total"] == 1
    (thread,) = page["items"]
    (reply,) = thread["replies"]
    assert reply["is_course_teacher"] is True and reply["author_role"] == "teacher"
    assert reply["can_delete"] is False  # học viên không xóa được trả lời của giảng viên

    # tự trả lời bình luận của chính mình thì không báo cho mình
    await _post(client, sv, lesson["id"], "Em cảm ơn thầy.", root["id"])
    assert len(await _notifications(sv_id)) == 1


async def test_two_levels_only_and_access(client):
    _, _, _, sv, _, lesson = await _setup(client)
    root = (await _post(client, sv, lesson["id"], "Câu hỏi")).json()
    reply = (await _post(client, sv, lesson["id"], "Trả lời", root["id"])).json()
    r = await _post(client, sv, lesson["id"], "Trả lời của trả lời", reply["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_PARENT"

    _, outsider = await make_student(client, "ngoai@x.com")  # chưa đăng ký khóa
    assert (await client.get(f"{API}/lessons/{lesson['id']}/comments", headers=outsider)).status_code == 403
    assert (await _post(client, outsider, lesson["id"], "Xin chào")).status_code == 403
    assert (await _post(client, sv, lesson["id"], "   ")).status_code == 422


async def test_soft_delete_rules(client):
    _, gv, _, sv, course, lesson = await _setup(client)
    _, other = await make_student(client, "khac@x.com")
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=other)
    root = (await _post(client, sv, lesson["id"], "Câu hỏi sẽ bị xóa")).json()

    assert (await client.delete(f"{API}/comments/{root['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"{API}/comments/{root['id']}", headers=sv)).status_code == 204
    (thread,) = (await client.get(f"{API}/lessons/{lesson['id']}/comments", headers=other)).json()["items"]
    assert thread["deleted"] is True and thread["body"] is None and thread["can_delete"] is False
    r = await _post(client, other, lesson["id"], "Trả lời muộn", root["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "COMMENT_DELETED"

    # giảng viên của khóa xóa được bình luận của học viên
    other_root = (await _post(client, other, lesson["id"], "Bình luận không phù hợp")).json()
    assert other_root["can_delete"] is True
    assert (await client.delete(f"{API}/comments/{other_root['id']}", headers=gv)).status_code == 204


async def test_comment_rate_limit(client):
    _, _, _, sv, _, lesson = await _setup(client)
    for i in range(30):
        assert (await _post(client, sv, lesson["id"], f"Câu {i}")).status_code == 201
    r = await _post(client, sv, lesson["id"], "Câu thứ 31")
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"
```

- [x] **Bước 3: Module `inbox`.** Tạo `backend/app/modules/inbox/__init__.py` rỗng.

```python
"""Thông báo trong app (B6): mỗi dòng là một thông báo cho một người, có liên kết tới nơi cần xem."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class NotificationKind(str, enum.Enum):
    comment_reply = "comment_reply"  # có người trả lời bình luận của bạn
    new_question = "new_question"  # học viên hỏi trong phần thảo luận khóa bạn dạy
    quiz_published = "quiz_published"  # khóa bạn học có quiz mới
    doc_ready = "doc_ready"  # tài liệu bạn tải lên đã xử lý xong
    doc_failed = "doc_failed"  # tài liệu bạn tải lên xử lý lỗi
    questions_ready = "questions_ready"  # AI đã sinh xong câu hỏi chờ duyệt
    questions_failed = "questions_failed"  # sinh câu hỏi không thành công


class Notification(IdMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # đếm thông báo chưa đọc: index một phần, chỉ chứa dòng chưa đọc
        Index("ix_notifications_unread", "user_id", postgresql_where=text("read_at IS NULL")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # chuỗi thay vì enum của Postgres: thêm loại thông báo mới không cần migration
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500), default="", server_default="")
    link: Mapped[str] = mapped_column(String(500))  # đường dẫn trong app, bắt đầu bằng "/"
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
"""Báo cho các tab đang mở biết người dùng có thông báo mới (B6).

Thông báo nằm trong bảng `notifications`; hub chỉ phát một tín hiệu "có thay đổi" theo người dùng qua Redis
pub/sub, luồng SSE của người đó nhận được thì đọc lại số chưa đọc từ DB. Mất tín hiệu (Redis lỗi, tab đang mất
mạng) không mất thông báo: lần kết nối lại sau sẽ đọc lại từ DB."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import lru_cache
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CHANNEL = "notif:{}"


class Subscription(Protocol):
    async def wait(self, timeout: float) -> bool:
        """Chờ tín hiệu tối đa `timeout` giây. True = có tín hiệu, False = hết giờ."""
        ...


class NotificationHub(Protocol):
    async def publish(self, user_ids: list[str]) -> None: ...

    def subscribe(self, user_id: str) -> AbstractAsyncContextManager[Subscription]: ...


class _RedisSubscription:
    def __init__(self, pubsub) -> None:
        self._pubsub = pubsub

    async def wait(self, timeout: float) -> bool:
        msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        return msg is not None


class RedisHub:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> "RedisHub":
        return cls(Redis.from_url(url, socket_connect_timeout=1.0))

    async def publish(self, user_ids: list[str]) -> None:
        """Phát tín hiệu cho từng người. Redis lỗi thì chỉ ghi log: thông báo đã nằm trong DB."""
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                for uid in dict.fromkeys(user_ids):
                    pipe.publish(CHANNEL.format(uid), "1")
                await pipe.execute()
        except RedisError:
            logger.warning("Không phát được tín hiệu thông báo qua Redis", exc_info=True)

    @asynccontextmanager
    async def subscribe(self, user_id: str) -> AsyncIterator[_RedisSubscription]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL.format(user_id))
        try:
            yield _RedisSubscription(pubsub)
        finally:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except (RedisError, asyncio.CancelledError):
                pass


@lru_cache
def get_hub() -> RedisHub:
    """Dependency FastAPI và worker dùng chung. Test override bằng InMemoryHub (tests/fakes.py)."""
    return RedisHub.from_url(get_settings().redis_url)
```

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.pagination import Page


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str
    read: bool
    created_at: datetime


class NotificationPage(Page[NotificationOut]):
    unread: int  # số chưa đọc (cả những cái không nằm trong trang này)


class UnreadOut(BaseModel):
    unread: int
```

```python
"""Thông báo trong app (B6): tạo, đọc, đánh dấu đã đọc, và luồng SSE báo số chưa đọc theo thời gian thực.

Cách dùng ở module khác: gọi `add(...)` trước khi commit (thông báo vào cùng transaction với việc gây ra nó),
commit xong thì `await hub.publish(ids)` để các tab đang mở cập nhật ngay."""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import SessionLocal
from app.core.errors import not_found
from app.core.pagination import PageParams, paginate
from app.core.time import utcnow
from app.modules.inbox.hub import NotificationHub
from app.modules.inbox.models import Notification, NotificationKind
from app.modules.inbox.schemas import NotificationOut, NotificationPage

logger = logging.getLogger(__name__)

HEARTBEAT_S = 25.0  # giữ kết nối qua proxy (Caddy, Nginx) và đọc lại số chưa đọc nếu lỡ mất tín hiệu


def add(
    db: AsyncSession,
    user_ids: list[uuid.UUID],
    kind: NotificationKind,
    title: str,
    link: str,
    body: str = "",
) -> list[str]:
    """Thêm thông báo cho từng người (bỏ trùng), CHƯA commit. Trả id người nhận dạng chuỗi để publish sau commit."""
    ids = list(dict.fromkeys(u for u in user_ids if u))
    db.add_all(
        Notification(user_id=uid, kind=kind.value, title=title[:200], body=body[:500], link=link)
        for uid in ids
    )
    return [str(u) for u in ids]


async def publish(hub: NotificationHub, user_ids: list[str]) -> None:
    """Phát tín hiệu sau commit. Không bao giờ ném lỗi: thông báo đã an toàn trong DB."""
    if not user_ids:
        return
    try:
        await hub.publish(user_ids)
    except Exception:
        logger.warning("Không phát được tín hiệu thông báo", exc_info=True)


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        link=n.link,
        read=n.read_at is not None,
        created_at=n.created_at,
    )


async def list_for(db: AsyncSession, user_id: uuid.UUID, params: PageParams) -> NotificationPage:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    total, paged = await paginate(db, stmt, params)
    items = [_out(n) for n in (await db.scalars(paged)).all()]
    return NotificationPage(
        items=items, total=total, page=params.page, size=params.size, unread=await unread_count(db, user_id)
    )


async def mark_read(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    """Thông báo của người khác trả 404 như không tồn tại."""
    n = await db.get(Notification, notification_id)
    if n is None or n.user_id != user_id:
        raise not_found("Thông báo")
    if n.read_at is None:
        n.read_at = utcnow()
        await db.commit()


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    await db.commit()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class _NoSignal:
    """Redis không dùng được: không có tín hiệu, luồng tự đọc lại số chưa đọc mỗi nhịp HEARTBEAT_S."""

    async def wait(self, timeout: float) -> bool:
        import asyncio

        await asyncio.sleep(timeout)
        return False


@asynccontextmanager
async def _subscribe(hub: NotificationHub, user_id: str):
    try:
        cm = hub.subscribe(user_id)
        sub = await cm.__aenter__()
    except (RedisError, OSError):
        logger.warning("Không đăng ký được kênh thông báo, chuyển sang đọc lại định kỳ", exc_info=True)
        yield _NoSignal()
        return
    try:
        yield sub
    finally:
        await cm.__aexit__(None, None, None)


async def notification_events(
    user_id: uuid.UUID,
    hub: NotificationHub,
    *,
    is_disconnected: Callable[[], Awaitable[bool]],
    session_factory: async_sessionmaker = SessionLocal,
    heartbeat_s: float = HEARTBEAT_S,
) -> AsyncIterator[str]:
    """Luồng SSE: gửi `unread` {unread, latest} ngay khi mở và mỗi khi số chưa đọc đổi; giữa chừng gửi dòng
    chú thích `: ping` để giữ kết nối. Mỗi lần đọc DB mở session riêng: không giữ connection suốt luồng."""

    async def snapshot() -> dict:
        async with session_factory() as db:
            count = await unread_count(db, user_id)
            latest = await db.scalar(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(1)
            )
            return {"unread": count, "latest": _out(latest).model_dump(mode="json") if latest else None}

    async with _subscribe(
        hub, str(user_id)
    ) as sub:  # đăng ký trước khi đọc: không lỡ thông báo đến giữa chừng
        last = await snapshot()
        yield _sse("unread", last)
        while not await is_disconnected():
            signalled = await sub.wait(heartbeat_s)
            current = await snapshot()
            if signalled or current["unread"] != last["unread"]:
                last = current
                yield _sse("unread", current)
            else:
                yield ": ping\n\n"
```

  - `/me/notifications/stream` gọi `await db.close()` trước khi trả `StreamingResponse`, để kết nối của dependency `get_db` về pool ngay. Luồng tự mở session ngắn mỗi lần đọc.

```python
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pagination import PageParams, page_params
from app.modules.auth.models import User
from app.modules.inbox import service
from app.modules.inbox.hub import NotificationHub, get_hub
from app.modules.inbox.schemas import NotificationPage, UnreadOut

router = APIRouter(prefix="/api/v1", tags=["notifications"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/me/notifications", response_model=NotificationPage)
async def my_notifications(
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Thông báo của tôi, mới nhất trước, kèm tổng số chưa đọc."""
    return await service.list_for(db, user.id, params)


@router.get("/me/notifications/unread", response_model=UnreadOut)
async def my_unread(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return UnreadOut(unread=await service.unread_count(db, user.id))


@router.post("/me/notifications/{notification_id}/read", status_code=204)
async def read_one(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await service.mark_read(db, user.id, notification_id)


@router.post("/me/notifications/read-all", status_code=204)
async def read_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await service.mark_all_read(db, user.id)


@router.get(
    "/me/notifications/stream",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE: unread {unread, latest} và : ping"}
    },
)
async def notification_stream(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    hub: NotificationHub = Depends(get_hub),
):
    """Số thông báo chưa đọc theo thời gian thực (frontend đọc bằng fetch vì cần header Authorization). Token
    chỉ được kiểm lúc mở luồng; mất kết nối thì frontend tự mở lại (có refresh token nếu cần)."""
    # Trả connection về pool ngay: luồng sống nhiều phút, mỗi lần đọc DB tự mở session ngắn của riêng nó.
    await db.close()
    return StreamingResponse(
        service.notification_events(user.id, hub, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
```

- [x] **Bước 4: Module `discussion`.** Tạo `backend/app/modules/discussion/__init__.py` rỗng.

```python
"""Thảo luận theo bài học (B4): bình luận gốc và một cấp trả lời."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class LessonComment(IdMixin, TimestampMixin, Base):
    __tablename__ = "lesson_comments"
    __table_args__ = (Index("ix_lesson_comments_lesson_created", "lesson_id", "created_at"),)

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # None = bình luận gốc; có giá trị = trả lời (chỉ trả lời bình luận gốc, nên tối đa 2 cấp)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lesson_comments.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # xóa mềm: giữ chỗ trong luồng
```

```python
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.pagination import Page

MAX_BODY = 2000


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    parent_id: uuid.UUID | None = None  # trả lời bình luận gốc nào (bỏ trống = hỏi mới)

    @field_validator("body")
    @classmethod
    def strip_body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nội dung không được để trống")
        return v


class CommentOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str | None  # None khi đã xóa
    deleted: bool
    author_name: str
    author_role: Literal["student", "teacher", "admin"]
    is_course_teacher: bool  # người viết là giảng viên của khóa: hiện nhãn "Giảng viên"
    can_delete: bool  # người xem hiện tại xóa được (tác giả, giảng viên khóa, admin)
    created_at: datetime
    replies: list["CommentOut"] = []


class CommentPage(Page[CommentOut]):
    pass
```

```python
"""Thảo luận theo bài học (B4).

- Ai vào được bài học (học viên đã đăng ký khóa đã xuất bản, giảng viên của khóa, admin) thì đọc và viết được.
- Hai cấp: bình luận gốc (câu hỏi) và trả lời; không trả lời một câu trả lời.
- Xóa mềm: tác giả, giảng viên của khóa hoặc admin; luồng vẫn giữ chỗ "Bình luận đã bị xóa" để các trả lời
  bên dưới còn ngữ cảnh.
- Thông báo (B6): trả lời → báo tác giả bình luận gốc; câu hỏi mới của học viên → báo giảng viên của khóa."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import PageParams, paginate
from app.core.ratelimit import RateLimiter, rate_limited
from app.core.time import utcnow
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, Lesson
from app.modules.discussion.models import LessonComment
from app.modules.discussion.schemas import CommentIn, CommentOut, CommentPage
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.inbox import service as inbox
from app.modules.inbox.hub import NotificationHub
from app.modules.inbox.models import NotificationKind

COMMENT_LIMIT_PER_HOUR = 30
SNIPPET = 120


def _can_moderate(user: User, course: Course) -> bool:
    return user.role == Role.admin or course.teacher_id == user.id


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET else text[: SNIPPET - 1].rstrip() + "…"


def _link(course: Course, lesson: Lesson) -> str:
    return f"/learn/{course.slug}/{lesson.id}#thao-luan"


def _out(c: LessonComment, author: User, viewer: User, course: Course) -> CommentOut:
    deleted = c.deleted_at is not None
    return CommentOut(
        id=c.id,
        parent_id=c.parent_id,
        body=None if deleted else c.body,
        deleted=deleted,
        author_name=author.full_name,
        author_role=author.role.value,
        is_course_teacher=author.id == course.teacher_id,
        can_delete=not deleted and (author.id == viewer.id or _can_moderate(viewer, course)),
        created_at=c.created_at,
    )


async def list_threads(db: AsyncSession, user: User, lesson_id: uuid.UUID, params: PageParams) -> CommentPage:
    """Bình luận gốc mới nhất trước (phân trang), mỗi cái kèm mọi trả lời cũ trước mới sau."""
    _, course = await ensure_lesson_access(db, lesson_id, user)
    stmt = (
        select(LessonComment, User)
        .join(User, User.id == LessonComment.user_id)
        .where(LessonComment.lesson_id == lesson_id, LessonComment.parent_id.is_(None))
        .order_by(LessonComment.created_at.desc(), LessonComment.id.desc())
    )
    total, paged = await paginate(db, stmt, params)
    roots = [_out(c, a, user, course) for c, a in (await db.execute(paged)).all()]
    if roots:
        replies = (
            await db.execute(
                select(LessonComment, User)
                .join(User, User.id == LessonComment.user_id)
                .where(LessonComment.parent_id.in_([r.id for r in roots]))
                .order_by(LessonComment.created_at, LessonComment.id)
            )
        ).all()
        by_parent = {r.id: r for r in roots}
        for c, a in replies:
            by_parent[c.parent_id].replies.append(_out(c, a, user, course))
    return CommentPage(items=roots, total=total, page=params.page, size=params.size)


async def create_comment(
    db: AsyncSession,
    limiter: RateLimiter,
    hub: NotificationHub,
    user: User,
    lesson_id: uuid.UUID,
    data: CommentIn,
) -> CommentOut:
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    wait = await limiter.hit(f"comment:{user.id}", COMMENT_LIMIT_PER_HOUR, 3600)
    if wait is not None:
        raise rate_limited(wait)
    parent = None
    if data.parent_id is not None:
        parent = await db.get(LessonComment, data.parent_id)
        if parent is None or parent.lesson_id != lesson_id:
            raise not_found("Bình luận")
        if parent.parent_id is not None:
            raise AppError("INVALID_PARENT", "Chỉ trả lời được bình luận gốc", 422)
        if parent.deleted_at is not None:
            raise AppError("COMMENT_DELETED", "Bình luận này đã bị xóa, không trả lời được nữa", 409)

    comment = LessonComment(lesson_id=lesson_id, user_id=user.id, parent_id=data.parent_id, body=data.body)
    db.add(comment)
    recipients: list[uuid.UUID] = []
    if parent is not None and parent.user_id != user.id:
        recipients = [parent.user_id]
        notified = inbox.add(
            db,
            recipients,
            NotificationKind.comment_reply,
            f"{user.full_name} trả lời bình luận của bạn",
            _link(course, lesson),
            body=f"{lesson.title}: {_snippet(data.body)}",
        )
    elif parent is None and course.teacher_id != user.id:
        notified = inbox.add(
            db,
            [course.teacher_id],
            NotificationKind.new_question,
            f"Câu hỏi mới ở bài {lesson.title}",
            _link(course, lesson),
            body=f"{user.full_name}: {_snippet(data.body)}",
        )
    else:
        notified = []
    await db.commit()
    await db.refresh(comment)
    await inbox.publish(hub, notified)
    return _out(comment, user, user, course)


async def delete_comment(db: AsyncSession, user: User, comment_id: uuid.UUID) -> None:
    comment = await db.get(LessonComment, comment_id)
    if comment is None:
        raise not_found("Bình luận")
    _, course = await ensure_lesson_access(db, comment.lesson_id, user)  # mất quyền vào bài → 404 / 403
    if comment.user_id != user.id and not _can_moderate(user, course):
        raise not_found("Bình luận")  # không lộ là bình luận có tồn tại
    if comment.deleted_at is None:
        comment.deleted_at = utcnow()
        await db.commit()
```

```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.pagination import PageParams, page_params
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.modules.auth.models import User
from app.modules.discussion import service
from app.modules.discussion.schemas import CommentIn, CommentOut, CommentPage
from app.modules.inbox.hub import NotificationHub, get_hub

router = APIRouter(prefix="/api/v1", tags=["discussion"])


@router.get("/lessons/{lesson_id}/comments", response_model=CommentPage)
async def lesson_comments(
    lesson_id: uuid.UUID,
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Thảo luận của bài: bình luận gốc mới nhất trước, mỗi cái kèm các trả lời. 403 NOT_ENROLLED / 404 như bài học."""
    return await service.list_threads(db, user, lesson_id, params)


@router.post("/lessons/{lesson_id}/comments", response_model=CommentOut, status_code=201)
async def post_comment(
    lesson_id: uuid.UUID,
    data: CommentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_rate_limiter),
    hub: NotificationHub = Depends(get_hub),
):
    """Hỏi mới (không có parent_id) hoặc trả lời một bình luận gốc. 422 INVALID_PARENT khi trả lời một câu trả
    lời; 409 COMMENT_DELETED; 429 RATE_LIMITED (30 bình luận/giờ/người)."""
    return await service.create_comment(db, limiter, hub, user, lesson_id, data)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Xóa mềm: tác giả, giảng viên của khóa hoặc admin. Người khác nhận 404."""
    await service.delete_comment(db, user, comment_id)
```

- [x] **Bước 5: Gắn vào app, hợp đồng import, migration.**

```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -14,7 +14,9 @@
 from app.modules.analytics.router import router as analytics_router
 from app.modules.auth.router import router as auth_router
 from app.modules.courses.router import router as courses_router
+from app.modules.discussion.router import router as discussion_router
 from app.modules.enrollment.router import router as enrollment_router
+from app.modules.inbox.router import router as inbox_router
 from app.modules.jobs.router import router as jobs_router
 from app.modules.materials.router import router as materials_router
 from app.modules.quiz.router import router as quiz_router
@@ -69,6 +71,8 @@
     app.include_router(analytics_router)
     app.include_router(admin_router)
     app.include_router(studio_router)
+    app.include_router(discussion_router)
+    app.include_router(inbox_router)
     app.include_router(health_router)
     setup_metrics(app)
     return app
```

```diff
--- a/backend/app/models_registry.py
+++ b/backend/app/models_registry.py
@@ -4,7 +4,9 @@
 from app.modules.admin import models as admin_models  # noqa: F401
 from app.modules.auth import models as auth_models  # noqa: F401
 from app.modules.courses import models as courses_models  # noqa: F401
+from app.modules.discussion import models as discussion_models  # noqa: F401
 from app.modules.enrollment import models as enrollment_models  # noqa: F401
+from app.modules.inbox import models as inbox_models  # noqa: F401
 from app.modules.jobs import models as jobs_models  # noqa: F401
 from app.modules.materials import models as materials_models  # noqa: F401
 from app.modules.notify import models as notify_models  # noqa: F401
```

```diff
--- a/backend/.importlinter
+++ b/backend/.importlinter
@@ -1,6 +1,6 @@
 # Ranh giới module của backend. Chạy: uv run lint-imports (CI chạy ở job lint).
-# Phần NỀN (auth, courses, enrollment, materials, jobs, notify) không được phụ thuộc phần TÍNH NĂNG
-# (tutor, quiz, studio, analytics, admin). Nhờ vậy sửa / bỏ một tính năng không kéo theo phần nền.
+# Phần NỀN (auth, courses, enrollment, materials, jobs, notify, inbox) không được phụ thuộc phần TÍNH NĂNG
+# (tutor, quiz, studio, analytics, admin, discussion). Nhờ vậy sửa / bỏ một tính năng không kéo theo phần nền.
 # Mỗi ngoại lệ phải ghi lý do; thêm ngoại lệ mới nghĩa là phải giải thích được vì sao.
 
 [importlinter]
@@ -17,12 +17,14 @@
     app.modules.materials
     app.modules.jobs
     app.modules.notify
+    app.modules.inbox
 forbidden_modules =
     app.modules.tutor
     app.modules.quiz
     app.modules.studio
     app.modules.analytics
     app.modules.admin
+    app.modules.discussion
 ignore_imports =
     # Chặn xóa khóa / chương / bài khi học viên đã làm quiz hoặc hỏi AI Tutor: chỉ ĐỌC bảng, không gọi service
     app.modules.courses.service -> app.modules.quiz.models
@@ -40,6 +42,18 @@
     app.modules.materials
     app.modules.jobs
 
+[importlinter:contract:inbox-is-leaf]
+name = inbox (thông báo trong app) chỉ dựa vào core và auth, module nào cũng gọi được nó
+type = forbidden
+source_modules =
+    app.modules.inbox
+forbidden_modules =
+    app.modules.courses
+    app.modules.enrollment
+    app.modules.materials
+    app.modules.jobs
+    app.modules.notify
+
 [importlinter:contract:tutor-quiz-independent]
 name = AI Tutor và Quiz độc lập với nhau
 type = independence
@@ -64,6 +78,7 @@
     app.modules.studio
     app.modules.analytics
     app.modules.admin
+    app.modules.discussion
     app.worker
     app.main
 
```

```python
"""lesson_comments (B4 thảo luận theo bài) và notifications (B6 thông báo trong app)

Revision ID: b9e1d4c7a352
Revises: a6d3f0c8e217
Create Date: 2026-10-19 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9e1d4c7a352"
down_revision: str | Sequence[str] | None = "a6d3f0c8e217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lesson_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["lesson_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lesson_comments_lesson_created", "lesson_comments", ["lesson_id", "created_at"])
    op.create_index(op.f("ix_lesson_comments_parent_id"), "lesson_comments", ["parent_id"])
    op.create_index(op.f("ix_lesson_comments_user_id"), "lesson_comments", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), server_default="", nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])
    op.create_index(
        "ix_notifications_unread", "notifications", ["user_id"], postgresql_where=sa.text("read_at IS NULL")
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notifications_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_lesson_comments_user_id"), table_name="lesson_comments")
    op.drop_index(op.f("ix_lesson_comments_parent_id"), table_name="lesson_comments")
    op.drop_index("ix_lesson_comments_lesson_created", table_name="lesson_comments")
    op.drop_table("lesson_comments")
```

- [x] **Bước 6: Thông báo khi xuất bản quiz và khi job nền xong.**
  - Quiz chỉ báo cho học viên khi khóa đã xuất bản.
  - Worker báo cho `jobs.created_by`. Job hệ thống (`created_by` NULL) thì không báo ai.

```diff
--- a/backend/app/modules/quiz/quizzes.py
+++ b/backend/app/modules/quiz/quizzes.py
@@ -13,6 +13,9 @@
 from app.modules.courses.service import ensure_owner, get_owned_lesson
 from app.modules.enrollment.models import Enrollment
 from app.modules.enrollment.service import ensure_lesson_access
+from app.modules.inbox import service as inbox
+from app.modules.inbox.hub import NotificationHub
+from app.modules.inbox.models import NotificationKind
 from app.modules.quiz.models import (
     USABLE_REVIEW,
     AttemptStatus,
@@ -216,7 +219,10 @@
     await db.commit()
 
 
-async def publish_quiz(db: AsyncSession, user: User, quiz: Quiz) -> QuizOut:
+async def publish_quiz(
+    db: AsyncSession, user: User, quiz: Quiz, hub: NotificationHub | None = None
+) -> QuizOut:
+    """Xuất bản quiz. Khóa đang xuất bản thì báo cho mọi học viên đã đăng ký (B6), cùng transaction."""
     await _lock_quiz(db, quiz)
     if quiz.status == QuizStatus.published:
         raise AppError("INVALID_STATE", "Quiz đã được xuất bản", 409)
@@ -242,10 +248,36 @@
             {"invalid_question_ids": invalid},
         )
     quiz.status = QuizStatus.published
+    notified = await _notify_students(db, quiz)
     await db.commit()
+    if hub is not None:
+        await inbox.publish(hub, notified)
     return (await _to_outs(db, [quiz], user, True, with_questions=True))[0]
 
 
+async def _notify_students(db: AsyncSession, quiz: Quiz) -> list[str]:
+    row = (
+        await db.execute(
+            select(Course, Lesson)
+            .join(Section, Section.course_id == Course.id)
+            .join(Lesson, Lesson.section_id == Section.id)
+            .where(Lesson.id == quiz.lesson_id)
+        )
+    ).one()
+    course, lesson = row
+    if course.status != CourseStatus.published:
+        return []
+    students = (await db.scalars(select(Enrollment.user_id).where(Enrollment.course_id == course.id))).all()
+    return inbox.add(
+        db,
+        list(students),
+        NotificationKind.quiz_published,
+        f"Quiz mới: {quiz.title}",
+        f"/learn/{course.slug}/{lesson.id}/quiz/{quiz.id}",
+        body=f"{course.title} · {lesson.title}",
+    )
+
+
 async def list_lesson_quizzes(
     db: AsyncSession, user: User, lesson_id: uuid.UUID, params: PageParams
 ) -> QuizPage:
```

```diff
--- a/backend/app/modules/quiz/router.py
+++ b/backend/app/modules/quiz/router.py
@@ -9,6 +9,7 @@
 from app.core.pagination import PageParams, page_params
 from app.core.ratelimit import RateLimiter, get_rate_limiter
 from app.modules.auth.models import Role, User
+from app.modules.inbox.hub import NotificationHub, get_hub
 from app.modules.jobs.queue import JobQueue, get_queue
 from app.modules.materials.schemas import JobRef
 from app.modules.quiz import attempts, explain, questions, quizzes
@@ -120,10 +121,13 @@
 
 @router.post("/quizzes/{quiz_id}/publish", response_model=QuizOut)
 async def publish_quiz(
-    quiz_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
+    quiz_id: uuid.UUID,
+    user: User = Depends(require_staff),
+    db: AsyncSession = Depends(get_db),
+    hub: NotificationHub = Depends(get_hub),
 ):
     quiz = await quizzes.get_owned_quiz(db, quiz_id, user)
-    return await quizzes.publish_quiz(db, user, quiz)
+    return await quizzes.publish_quiz(db, user, quiz, hub)
 
 
 @router.post("/quizzes/{quiz_id}/attempts", response_model=AttemptOut, status_code=201)
```

```diff
--- a/backend/app/worker/tasks.py
+++ b/backend/app/worker/tasks.py
@@ -12,10 +12,14 @@
 from app.core.db import SessionLocal
 from app.core.time import utcnow
 from app.ingestion.pipeline import error_text, ingest_pdf_source
+from app.modules.courses.models import Course, Lesson, Section
+from app.modules.inbox import service as inbox
+from app.modules.inbox.hub import get_hub
+from app.modules.inbox.models import NotificationKind
 from app.modules.jobs.models import Job, JobStatus
 from app.modules.jobs.queue import ArqQueue, JobQueue
 from app.modules.jobs.service import create_and_enqueue, finish_job
-from app.modules.materials.models import Source, SourceStatus
+from app.modules.materials.models import Asset, Source, SourceStatus
 from app.modules.quiz.attempts import finalize_overdue_attempts
 from app.modules.quiz.generation import QuizGenerationError, generate_questions_for_lesson
 from app.modules.quiz.schemas import QuizGenerateIn
@@ -137,10 +141,72 @@
         )
 
     await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("ingest_pdf"))
+    await _notify_job_owner(ctx, uuid.UUID(job_id), session_factory)
     await _queue_source_guide(ctx, uuid.UUID(job_id), session_factory)
     await _queue_waiting_answers(ctx, uuid.UUID(job_id), session_factory)
 
 
+async def _notify_job_owner(ctx: dict, job_id: uuid.UUID, session_factory: async_sessionmaker) -> None:
+    """Job xử lý PDF / sinh câu hỏi kết thúc thì báo người tạo job (B6): xong → mở bài để xem, lỗi → kèm lý do.
+    Lỗi ở đây chỉ ghi log: thông báo là phần phụ, trạng thái job đã được ghi."""
+    try:
+        async with session_factory() as db:
+            job = await db.get(Job, job_id)
+            if job is None or job.created_by is None or job.status not in (JobStatus.done, JobStatus.failed):
+                return
+            ok = job.status == JobStatus.done
+            if job.type == "ingest_pdf":
+                row = (
+                    await db.execute(
+                        select(Asset.original_name, Lesson, Course)
+                        .select_from(Source)
+                        .join(Asset, Asset.id == Source.asset_id)
+                        .join(Lesson, Lesson.id == Source.lesson_id)
+                        .join(Section, Section.id == Lesson.section_id)
+                        .join(Course, Course.id == Section.course_id)
+                        .where(Source.id == job.ref_id)
+                    )
+                ).first()
+                if row is None:
+                    return
+                name, lesson, course = row
+                kind = NotificationKind.doc_ready if ok else NotificationKind.doc_failed
+                title = (
+                    f"Tài liệu đã sẵn sàng · {lesson.title}"
+                    if ok
+                    else f"Xử lý tài liệu không thành công · {lesson.title}"
+                )
+                body = (name or "Tài liệu PDF") + ("" if ok else f": {job.error_msg or 'lỗi không rõ'}")
+                link = f"/teach/{course.slug}/lessons/{lesson.id}"
+            elif job.type == "quiz_gen":
+                row = (
+                    await db.execute(
+                        select(Lesson, Course)
+                        .join(Section, Section.id == Lesson.section_id)
+                        .join(Course, Course.id == Section.course_id)
+                        .where(Lesson.id == job.ref_id)
+                    )
+                ).first()
+                if row is None:
+                    return
+                lesson, course = row
+                kind = NotificationKind.questions_ready if ok else NotificationKind.questions_failed
+                title = (
+                    f"Câu hỏi AI đã soạn xong · {lesson.title}"
+                    if ok
+                    else f"Sinh câu hỏi không thành công · {lesson.title}"
+                )
+                body = "Câu hỏi đang chờ bạn duyệt" if ok else (job.error_msg or "")
+                link = f"/teach/{course.slug}/lessons/{lesson.id}/questions"
+            else:
+                return
+            ids = inbox.add(db, [job.created_by], kind, title, link, body=body)
+            await db.commit()
+        await inbox.publish(ctx.get("hub") or get_hub(), ids)
+    except Exception:
+        logger.exception("Không tạo được thông báo cho job %s", job_id)
+
+
 def _queue_of(ctx: dict) -> JobQueue | None:
     return ctx.get("queue") or (ArqQueue(pool=ctx["redis"]) if "redis" in ctx else None)
 
@@ -275,6 +341,7 @@
             raise RuntimeError(QUIZ_GEN_ERROR) from e
 
     await run_job(job_id, handler, session_factory, timeout_s=handler_timeout("quiz_gen"))
+    await _notify_job_owner(ctx, jid, session_factory)
 
 
 async def _fail_jobs(db, jobs_where, error: str, now) -> int:
```

- [x] **Bước 7: Chạy test, kiểm migration, commit**

```powershell
docker compose up -d db redis
cd backend
uv run alembic upgrade head ; uv run alembic downgrade -1 ; uv run alembic upgrade head
uv run alembic check                                       # No new upgrade operations detected
uv run pytest tests/test_notifications.py tests/test_discussion.py -q   # 9 pass
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports   # 6 contracts kept
uv run pytest -q                                           # 795 pass
cd ..\frontend; npm run gen:api
cd ..
git add backend frontend/openapi.json frontend/src/lib/api/schema.d.ts
git commit -m "feat: thảo luận theo bài (B4) và thông báo realtime qua SSE (B6)"
```

---

## Task 2: Backend: phân tích lớp học (B7)

**Files:**
- Modify: `backend/app/modules/analytics/schemas.py`, `service.py`, `router.py`
- Create: `backend/tests/test_insights.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/lib/api/schema.d.ts`

- [x] **Bước 1: Test (sẽ fail)**

```python
"""B7: phân tích lớp học (câu hay sai, bài yếu, học viên cần để ý)."""

import uuid
from datetime import timedelta

from sqlalchemy import update

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.enrollment.models import Enrollment
from tests.helpers import API, make_published_quiz, make_student


async def test_insights_rank_hard_questions_weak_lessons_and_students(client, db):
    gv, sv1, course, quiz, qs = await make_published_quiz(client, db, n_questions=2)
    students = [sv1]
    for i in range(2):
        _, sv = await make_student(client, f"sv{i}@x.com")
        await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
        students.append(sv)
    # câu 1 (theo thứ tự tạo) cả 3 người sai, 2 người chọn C; câu 0 chỉ 1 người sai
    order = {q.id: i for i, q in enumerate(qs)}
    for sv, (p0, p1) in zip(students, [("A", "C"), ("A", "C"), ("B", "D")], strict=True):
        attempt = (await client.post(f"{API}/quizzes/{quiz['id']}/attempts", headers=sv)).json()
        by_index = {order[uuid.UUID(q["id"])]: q["id"] for q in attempt["questions"]}
        final = [
            {"question_id": by_index[0], "selected_option_id": p0},
            {"question_id": by_index[1], "selected_option_id": p1},
        ]
        r = await client.post(
            f"{API}/attempts/{attempt['id']}/submit", json={"final_answers": final}, headers=sv
        )
        assert r.status_code == 200, r.text

    r = await client.get(f"{API}/courses/{course['id']}/insights", headers=gv)
    assert r.status_code == 200, r.text
    data = r.json()
    hard = data["hard_questions"]
    assert [h["question_id"] for h in hard] == [str(qs[1].id), str(qs[0].id)]
    assert hard[0]["wrong"] == 3 and hard[0]["answers"] == 3 and hard[0]["wrong_rate"] == 1.0
    assert hard[0]["top_wrong"] == {"id": "C", "text": "Danh sách liên kết", "count": 2}
    assert hard[0]["correct_option"] == "A" and hard[0]["lesson_title"] == "Bài 1"

    (weak,) = data["weak_lessons"]
    assert weak["attempts"] == 3 and weak["avg_score"] == round((50 + 50 + 0) / 3, 2)

    # điểm trung bình 0% → cần để ý; hai người 50% thì không (ngưỡng < 50)
    (risk,) = data["students_at_risk"]
    assert risk["avg_score"] == 0 and risk["reasons"] == ["Điểm quiz trung bình 0%"]


async def test_inactive_student_listed_and_access(client, db):
    gv, sv, course, _, _ = await make_published_quiz(client, db)
    async with SessionLocal() as s:
        await s.execute(
            update(Enrollment)
            .where(Enrollment.course_id == course["id"])
            .values(enrolled_at=utcnow() - timedelta(days=10))
        )
        await s.commit()
    data = (await client.get(f"{API}/courses/{course['id']}/insights", headers=gv)).json()
    (risk,) = data["students_at_risk"]
    assert risk["reasons"] == ["Không học 10 ngày"] and risk["progress_pct"] == 0
    assert data["hard_questions"] == []  # chưa có ai nộp bài

    # học viên và giảng viên khác không xem được
    assert (await client.get(f"{API}/courses/{course['id']}/insights", headers=sv)).status_code == 403
```

- [x] **Bước 2: Schema, service, router.**
  - Chỉ tính bài quiz đã nộp (`completed`, `timed_out`).
  - "Hoạt động gần nhất" là thời điểm muộn nhất trong: lúc đăng ký, lần cập nhật tiến độ, lần bắt đầu làm quiz, câu hỏi gửi AI Tutor.

```diff
--- a/backend/app/modules/analytics/schemas.py
+++ b/backend/app/modules/analytics/schemas.py
@@ -59,3 +59,54 @@
 
 class TutorFeedbackPage(Page[TutorFeedbackItem]):
     pass
+
+
+class WrongOption(BaseModel):
+    id: str  # A–D
+    text: str
+    count: int  # số lượt chọn phương án sai này
+
+
+class HardQuestion(BaseModel):
+    """Câu hỏi quiz học viên hay làm sai (B7)."""
+
+    question_id: uuid.UUID
+    stem: str
+    lesson_id: uuid.UUID
+    lesson_title: str
+    answers: int  # số lượt trả lời trong các bài đã nộp
+    wrong: int
+    wrong_rate: float  # 0..1
+    correct_option: str
+    top_wrong: WrongOption | None  # phương án sai được chọn nhiều nhất
+    source_page: int | None  # trang tài liệu mà câu hỏi dựa vào
+
+
+class WeakLesson(BaseModel):
+    """Bài học có điểm quiz thấp hoặc học viên hỏi AI Tutor nhiều (B7)."""
+
+    lesson_id: uuid.UUID
+    title: str
+    section_title: str
+    attempts: int  # số bài quiz đã nộp ở các quiz của bài
+    avg_score: float | None
+    tutor_questions: int  # số câu học viên hỏi AI Tutor trong phiên gắn với bài
+
+
+class StudentAtRisk(BaseModel):
+    """Học viên cần giảng viên để ý (B7): điểm quiz trung bình thấp hoặc lâu không học."""
+
+    user_id: uuid.UUID
+    full_name: str
+    progress_pct: int
+    avg_score: float | None
+    last_active_at: datetime
+    reasons: list[str]
+
+
+class CourseInsights(BaseModel):
+    course_id: uuid.UUID
+    min_answers: int  # câu hỏi cần ít nhất chừng này lượt trả lời mới được xếp hạng
+    hard_questions: list[HardQuestion]
+    weak_lessons: list[WeakLesson]
+    students_at_risk: list[StudentAtRisk]
```

```diff
--- a/backend/app/modules/analytics/service.py
+++ b/backend/app/modules/analytics/service.py
@@ -1,24 +1,32 @@
-"""Số liệu cơ bản cho dashboard giảng viên (A8). Phân tích sâu (câu hay sai, chủ đề yếu) là B7."""
+"""Số liệu cho dashboard giảng viên: số liệu cơ bản (A8) và phân tích lớp học (B7: câu hay sai, bài yếu,
+học viên cần để ý)."""
 
 import uuid
 
-from sqlalchemy import and_, distinct, func, select
+from sqlalchemy import and_, distinct, func, or_, select
 from sqlalchemy.ext.asyncio import AsyncSession
 from sqlalchemy.orm import aliased
 
 from app.core.pagination import PageParams, paginate
+from app.core.time import utcnow
 from app.modules.analytics.schemas import (
     CourseAnalytics,
+    CourseInsights,
+    HardQuestion,
     LessonStat,
     QuizStat,
+    StudentAtRisk,
     TutorFeedbackItem,
     TutorFeedbackPage,
     TutorStat,
+    WeakLesson,
+    WrongOption,
 )
 from app.modules.auth.models import User
 from app.modules.courses.models import Course, Lesson, Section
 from app.modules.enrollment.models import Enrollment, LessonProgress, ProgressStatus
-from app.modules.quiz.models import AttemptStatus, Quiz, QuizAttempt
+from app.modules.materials.models import Chunk
+from app.modules.quiz.models import AttemptAnswer, AttemptStatus, Question, Quiz, QuizAttempt
 from app.modules.tutor.models import ChatMessage, ChatRole, ChatSession
 
 
@@ -171,3 +179,232 @@
         for m, q, cid, ctitle, slug, lid, ltitle, student in rows
     ]
     return TutorFeedbackPage(items=items, total=total, page=params.page, size=params.size)
+
+
+# ---------- B7: phân tích lớp học ----------
+
+MIN_ANSWERS = 3  # ít hơn thì tỉ lệ sai chưa nói lên gì
+HARD_LIMIT = 10
+WEAK_LIMIT = 5
+RISK_LIMIT = 20
+LOW_SCORE = 50.0  # điểm quiz trung bình (phần trăm) dưới mức này là thấp
+INACTIVE_DAYS = 7
+
+
+async def course_insights(db: AsyncSession, course: Course) -> CourseInsights:
+    """Câu hay sai, bài yếu, học viên cần để ý. Chỉ tính bài quiz đã nộp (completed / timed_out)."""
+    finished = QuizAttempt.status.in_((AttemptStatus.completed, AttemptStatus.timed_out))
+    course_quiz_attempts = (
+        select(QuizAttempt.id)
+        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
+        .join(Lesson, Lesson.id == Quiz.lesson_id)
+        .join(Section, Section.id == Lesson.section_id)
+        .where(Section.course_id == course.id, finished)
+    )
+    return CourseInsights(
+        course_id=course.id,
+        min_answers=MIN_ANSWERS,
+        hard_questions=await _hard_questions(db, course_quiz_attempts),
+        weak_lessons=await _weak_lessons(db, course, finished),
+        students_at_risk=await _students_at_risk(db, course, finished),
+    )
+
+
+async def _hard_questions(db: AsyncSession, attempts) -> list[HardQuestion]:
+    stats = (
+        select(
+            AttemptAnswer.question_id,
+            func.count().label("answers"),
+            func.count().filter(AttemptAnswer.is_correct.is_(False)).label("wrong"),
+        )
+        .where(AttemptAnswer.attempt_id.in_(attempts))
+        .group_by(AttemptAnswer.question_id)
+        .subquery()
+    )
+    rate = stats.c.wrong * 1.0 / stats.c.answers
+    rows = (
+        await db.execute(
+            select(Question, stats.c.answers, stats.c.wrong, Lesson.title, Chunk.page_no)
+            .join(stats, stats.c.question_id == Question.id)
+            .join(Lesson, Lesson.id == Question.lesson_id)
+            .outerjoin(Chunk, Chunk.id == Question.source_chunk_id)
+            .where(stats.c.answers >= MIN_ANSWERS, stats.c.wrong > 0)
+            .order_by(rate.desc(), stats.c.wrong.desc(), Question.id)
+            .limit(HARD_LIMIT)
+        )
+    ).all()
+    if not rows:
+        return []
+    picks = (
+        await db.execute(
+            select(AttemptAnswer.question_id, AttemptAnswer.selected_option_id, func.count())
+            .where(
+                AttemptAnswer.attempt_id.in_(attempts),
+                AttemptAnswer.is_correct.is_(False),
+                AttemptAnswer.question_id.in_([q.id for q, *_ in rows]),
+            )
+            .group_by(AttemptAnswer.question_id, AttemptAnswer.selected_option_id)
+        )
+    ).all()
+    top: dict[uuid.UUID, tuple[str, int]] = {}
+    for qid, opt, n in sorted(picks, key=lambda p: (-p[2], p[1])):
+        top.setdefault(qid, (opt, n))
+    out = []
+    for q, answers, wrong, lesson_title, page in rows:
+        texts = {o["id"]: o["text"] for o in q.options}
+        tw = top.get(q.id)
+        out.append(
+            HardQuestion(
+                question_id=q.id,
+                stem=q.stem,
+                lesson_id=q.lesson_id,
+                lesson_title=lesson_title,
+                answers=answers,
+                wrong=wrong,
+                wrong_rate=round(wrong / answers, 4),
+                correct_option=q.correct_option_id,
+                top_wrong=WrongOption(id=tw[0], text=texts.get(tw[0], ""), count=tw[1]) if tw else None,
+                source_page=page,
+            )
+        )
+    return out
+
+
+async def _weak_lessons(db: AsyncSession, course: Course, finished) -> list[WeakLesson]:
+    quiz_stats = (
+        select(
+            Quiz.lesson_id, func.count(QuizAttempt.id).label("n"), func.avg(QuizAttempt.score).label("avg")
+        )
+        .join(QuizAttempt, and_(QuizAttempt.quiz_id == Quiz.id, finished))
+        .group_by(Quiz.lesson_id)
+        .subquery()
+    )
+    asked = (
+        select(ChatSession.lesson_id, func.count(ChatMessage.id).label("n"))
+        .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
+        .where(ChatSession.course_id == course.id, ChatMessage.role == ChatRole.user)
+        .group_by(ChatSession.lesson_id)
+        .subquery()
+    )
+    rows = (
+        await db.execute(
+            select(
+                Lesson.id,
+                Lesson.title,
+                Section.title,
+                func.coalesce(quiz_stats.c.n, 0),
+                quiz_stats.c.avg,
+                func.coalesce(asked.c.n, 0),
+            )
+            .join(Section, Section.id == Lesson.section_id)
+            .outerjoin(quiz_stats, quiz_stats.c.lesson_id == Lesson.id)
+            .outerjoin(asked, asked.c.lesson_id == Lesson.id)
+            .where(Section.course_id == course.id, or_(quiz_stats.c.n > 0, asked.c.n > 0))
+            .order_by(quiz_stats.c.avg.asc().nulls_last(), func.coalesce(asked.c.n, 0).desc(), Lesson.id)
+            .limit(WEAK_LIMIT)
+        )
+    ).all()
+    return [
+        WeakLesson(
+            lesson_id=lid,
+            title=title,
+            section_title=section_title,
+            attempts=n,
+            avg_score=round(float(avg), 2) if avg is not None else None,
+            tutor_questions=q,
+        )
+        for lid, title, section_title, n, avg, q in rows
+    ]
+
+
+async def _students_at_risk(db: AsyncSession, course: Course, finished) -> list[StudentAtRisk]:
+    lesson_ids = (
+        select(Lesson.id).join(Section, Section.id == Lesson.section_id).where(Section.course_id == course.id)
+    )
+    total_lessons = await db.scalar(select(func.count()).select_from(lesson_ids.subquery())) or 0
+    students = (
+        await db.execute(
+            select(User.id, User.full_name, Enrollment.enrolled_at)
+            .join(Enrollment, Enrollment.user_id == User.id)
+            .where(Enrollment.course_id == course.id, Enrollment.completed_at.is_(None))
+        )
+    ).all()
+    if not students:
+        return []
+    ids = [s[0] for s in students]
+    progress = dict(
+        (
+            await db.execute(
+                select(
+                    LessonProgress.user_id,
+                    func.count().filter(LessonProgress.status == ProgressStatus.done),
+                )
+                .where(LessonProgress.user_id.in_(ids), LessonProgress.lesson_id.in_(lesson_ids))
+                .group_by(LessonProgress.user_id)
+            )
+        ).all()
+    )
+    touched = dict(
+        (
+            await db.execute(
+                select(LessonProgress.user_id, func.max(LessonProgress.updated_at))
+                .where(LessonProgress.user_id.in_(ids), LessonProgress.lesson_id.in_(lesson_ids))
+                .group_by(LessonProgress.user_id)
+            )
+        ).all()
+    )
+    quiz = {
+        uid: (avg, last)
+        for uid, avg, last in (
+            await db.execute(
+                select(
+                    QuizAttempt.user_id,
+                    func.avg(QuizAttempt.score).filter(finished),
+                    func.max(QuizAttempt.started_at),
+                )
+                .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
+                .where(QuizAttempt.user_id.in_(ids), Quiz.lesson_id.in_(lesson_ids))
+                .group_by(QuizAttempt.user_id)
+            )
+        ).all()
+    }
+    asked = dict(
+        (
+            await db.execute(
+                select(ChatSession.user_id, func.max(ChatMessage.created_at))
+                .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
+                .where(
+                    ChatSession.course_id == course.id,
+                    ChatSession.user_id.in_(ids),
+                    ChatMessage.role == ChatRole.user,
+                )
+                .group_by(ChatSession.user_id)
+            )
+        ).all()
+    )
+    now = utcnow()
+    out = []
+    for uid, name, enrolled_at in students:
+        avg, quiz_last = quiz.get(uid, (None, None))
+        last = max(t for t in (enrolled_at, touched.get(uid), quiz_last, asked.get(uid)) if t is not None)
+        reasons = []
+        if avg is not None and avg < LOW_SCORE:
+            reasons.append(f"Điểm quiz trung bình {round(float(avg))}%")
+        idle = (now - last).days
+        if idle >= INACTIVE_DAYS:
+            reasons.append(f"Không học {idle} ngày")
+        if not reasons:
+            continue
+        done = progress.get(uid, 0)
+        out.append(
+            StudentAtRisk(
+                user_id=uid,
+                full_name=name,
+                progress_pct=round(100 * done / total_lessons) if total_lessons else 0,
+                avg_score=round(float(avg), 2) if avg is not None else None,
+                last_active_at=last,
+                reasons=reasons,
+            )
+        )
+    out.sort(key=lambda s: s.last_active_at)
+    return out[:RISK_LIMIT]
```

```diff
--- a/backend/app/modules/analytics/router.py
+++ b/backend/app/modules/analytics/router.py
@@ -7,7 +7,7 @@
 from app.core.deps import require_staff
 from app.core.pagination import PageParams, page_params
 from app.modules.analytics import service
-from app.modules.analytics.schemas import CourseAnalytics, TutorFeedbackPage
+from app.modules.analytics.schemas import CourseAnalytics, CourseInsights, TutorFeedbackPage
 from app.modules.auth.models import User
 from app.modules.courses.service import get_owned_course
 
@@ -22,6 +22,15 @@
     return await service.course_analytics(db, course)
 
 
+@router.get("/courses/{course_id}/insights", response_model=CourseInsights)
+async def course_insights(
+    course_id: uuid.UUID, user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)
+):
+    """Phân tích lớp học (B7): câu hay sai, bài yếu, học viên cần để ý. Chỉ giảng viên của khóa hoặc admin."""
+    course = await get_owned_course(db, course_id, user)
+    return await service.course_insights(db, course)
+
+
 @router.get("/courses/{course_id}/tutor-feedback", response_model=TutorFeedbackPage)
 async def course_tutor_feedback(
     course_id: uuid.UUID,
```

- [x] **Bước 3: Chạy test, kiểu API, commit**

```powershell
cd backend
uv run pytest tests/test_insights.py -q                    # 2 pass
uv run ruff check . ; uv run ruff format --check . ; uv run lint-imports
uv run pytest -q                                           # 797 pass
cd ..\frontend; npm run gen:api                            # schema.d.ts có CommentOut, NotificationOut, CourseInsights
cd ..
git add backend frontend/openapi.json frontend/src/lib/api/schema.d.ts
git commit -m "feat(analytics): GET /courses/{id}/insights, câu hay sai, bài yếu, học viên cần để ý (B7)"
```

---

## Task 3: Frontend: chuông thông báo và phần thảo luận

**Files:**
- Create: `frontend/src/lib/format.ts`, `frontend/src/lib/notifications.ts`, `frontend/src/lib/discussion.ts`
- Create: `frontend/src/components/app/notification-bell.tsx`, `frontend/src/components/lesson/lesson-discussion.tsx`
- Create tests: `frontend/src/lib/format.test.ts`, `frontend/src/components/app/notification-bell.test.tsx`, `frontend/src/components/lesson/lesson-discussion.test.tsx`
- Modify: `frontend/src/components/app/app-shell.tsx`, `frontend/src/components/lesson/lesson-view.tsx`

- [ ] **Bước 1: Định dạng thời gian.** Hiện "vừa xong", "5 phút trước"...; quá 30 ngày thì ghi ngày/tháng/năm.

```ts
/** "vừa xong", "5 phút trước", "3 giờ trước", "2 ngày trước"; quá 30 ngày thì ghi ngày tháng năm. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "vừa xong";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} phút trước`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} giờ trước`;
  const d = Math.floor(h / 24);
  if (d <= 30) return `${d} ngày trước`;
  const date = new Date(t);
  return `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}/${date.getFullYear()}`;
}
```

```ts
import { describe, expect, it } from "vitest";
import { timeAgo } from "./format";

describe("timeAgo", () => {
  const now = new Date(2026, 9, 19, 12, 0, 0).getTime();
  const ago = (sec: number) => new Date(now - sec * 1000).toISOString();

  it("đổi khoảng thời gian sang chữ tiếng Việt", () => {
    expect(timeAgo(ago(30), now)).toBe("vừa xong");
    expect(timeAgo(ago(5 * 60), now)).toBe("5 phút trước");
    expect(timeAgo(ago(3 * 3600), now)).toBe("3 giờ trước");
    expect(timeAgo(ago(2 * 86400), now)).toBe("2 ngày trước");
  });

  it("quá 30 ngày thì ghi ngày/tháng/năm; thời điểm trong tương lai coi như vừa xong", () => {
    expect(timeAgo(new Date(2026, 7, 2, 9, 0).toISOString(), now)).toBe("02/08/2026");
    expect(timeAgo(ago(-120), now)).toBe("vừa xong");
  });
});
```

- [ ] **Bước 2: Truy vấn thông báo và luồng SSE.**
  - Luồng ghi thẳng số chưa đọc vào cache của TanStack Query.
  - Trước khi ghi, nó hủy lệnh `GET /unread` đang chạy dở. Nếu không, lệnh gửi trước mà về sau sẽ ghi đè số mới hơn (lỗi này đã gặp trong test).

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { api, apiBase, authFetch, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { readSse } from "@/lib/api/sse";

export type Notification = components["schemas"]["NotificationOut"];

export const notifKeys = {
  all: ["notifications"] as const,
  list: ["notifications", "list"] as const,
  unread: ["notifications", "unread"] as const,
};

/** 10 thông báo mới nhất (mở khi bấm chuông). */
export function useNotifications(enabled: boolean) {
  return useQuery({
    queryKey: notifKeys.list,
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/me/notifications", { params: { query: { size: 10 } } })),
  });
}

/** Số chưa đọc. Luồng SSE cập nhật thẳng vào cache này, nên không cần tải lại định kỳ. */
export function useUnreadCount(enabled: boolean) {
  return useQuery({
    queryKey: notifKeys.unread,
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/me/notifications/unread")),
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/api/v1/me/notifications/{notification_id}/read", { params: { path: { notification_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifKeys.all }),
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/me/notifications/read-all")),
    onSuccess: () => qc.invalidateQueries({ queryKey: notifKeys.all }),
  });
}

const RETRY_MIN_MS = 2_000;
const RETRY_MAX_MS = 30_000;

/**
 * Mở luồng SSE /me/notifications/stream và ghi số chưa đọc vào cache (B6). Mất kết nối thì mở lại sau 2 giây,
 * mỗi lần lỗi liên tiếp gấp đôi thời gian chờ (tối đa 30 giây). authFetch tự refresh access token khi gặp 401.
 */
export function useNotificationStream(enabled: boolean) {
  const qc = useQueryClient();
  React.useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    let delay = RETRY_MIN_MS;
    (async () => {
      while (!ctrl.signal.aborted) {
        try {
          const res = await authFetch(new Request(`${apiBase()}/api/v1/me/notifications/stream`, { signal: ctrl.signal }));
          if (res.ok && res.body) {
            for await (const ev of readSse(res.body, ctrl.signal)) {
              if (ev.event !== "unread") continue;
              delay = RETRY_MIN_MS; // đã nhận dữ liệu: kết nối tốt
              const data = JSON.parse(ev.data) as { unread: number };
              const prev = qc.getQueryData<{ unread: number }>(notifKeys.unread);
              // lệnh GET /unread gửi trước có thể về sau và ghi đè số mới hơn: hủy nó đi
              await qc.cancelQueries({ queryKey: notifKeys.unread });
              qc.setQueryData(notifKeys.unread, { unread: data.unread });
              if (prev && prev.unread !== data.unread) void qc.invalidateQueries({ queryKey: notifKeys.list });
            }
          }
        } catch {
          // mất mạng, tab bị đóng (abort) hay máy chủ khởi động lại: thử lại bên dưới
        }
        if (ctrl.signal.aborted) return;
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, RETRY_MAX_MS);
      }
    })();
    return () => ctrl.abort();
  }, [enabled, qc]);
}
```

- [ ] **Bước 3: Chuông thông báo.** Đặt cạnh menu tài khoản ở khung app và ở thanh trên trang bài học.

```tsx
"use client";

import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { Popover } from "radix-ui";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth/auth-context";
import { timeAgo } from "@/lib/format";
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  useNotificationStream,
  useUnreadCount,
} from "@/lib/notifications";
import { cn } from "@/lib/utils";

/**
 * Chuông thông báo (B6) ở thanh trên: số chưa đọc cập nhật theo thời gian thực qua SSE; bấm mở danh sách
 * 10 thông báo mới nhất. Bấm một thông báo thì đánh dấu đã đọc và mở trang liên quan.
 */
export function NotificationBell() {
  const { status } = useAuth();
  const authed = status === "authenticated";
  const [open, setOpen] = React.useState(false);
  useNotificationStream(authed);
  const unread = useUnreadCount(authed);
  const list = useNotifications(authed && open);
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  if (!authed) return null;

  const count = unread.data?.unread ?? 0;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button variant="ghost" size="icon" className="relative shrink-0" aria-label={count ? `Thông báo, ${count} chưa đọc` : "Thông báo"}>
          <Bell className="size-5" />
          {count ? (
            <span
              aria-hidden
              className="absolute right-1 top-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-primary px-1 text-[11px] font-bold leading-none text-primary-foreground"
            >
              {count > 99 ? "99+" : count}
            </span>
          ) : null}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-50 flex max-h-[min(70dvh,520px)] w-[min(92vw,380px)] flex-col border bg-surface shadow-md"
        >
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <h2 className="font-semibold">Thông báo</h2>
            <Button variant="ghost" size="sm" disabled={!count} loading={markAll.isPending} onClick={() => markAll.mutate()}>
              <CheckCheck /> Đã đọc hết
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {list.isPending ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : list.isError || list.data.items.length === 0 ? (
              <p className="px-4 pb-6 pt-2 text-sm text-muted-foreground">
                {list.isError ? "Chưa tải được thông báo." : "Chưa có thông báo nào."}
              </p>
            ) : (
              <ul className="flex flex-col">
                {list.data.items.map((n) => (
                  <li key={n.id}>
                    <Link
                      href={n.link}
                      onClick={() => {
                        if (!n.read) markRead.mutate(n.id);
                        setOpen(false);
                      }}
                      className={cn(
                        "flex gap-3 px-4 py-3 transition-colors duration-150 hover:bg-field-3",
                        !n.read && "bg-field-3/60",
                      )}
                    >
                      <span
                        aria-hidden
                        className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-primary")}
                      />
                      <span className="min-w-0">
                        <span className={cn("block text-sm leading-snug", !n.read && "font-semibold")}>
                          {n.read ? null : <span className="sr-only">Chưa đọc: </span>}
                          {n.title}
                        </span>
                        {n.body ? <span className="mt-0.5 line-clamp-2 block text-sm text-muted-foreground">{n.body}</span> : null}
                        <span className="mt-1 block text-xs text-muted-foreground">{timeAgo(n.created_at)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
```

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";

vi.mock("@/lib/auth/auth-context", () => ({ useAuth: () => ({ status: "authenticated" }) }));

import { NotificationBell } from "./notification-bell";

const item = (id: string, read: boolean) => ({
  id,
  kind: "comment_reply",
  title: `Thông báo ${id}`,
  body: "Nội dung ngắn",
  link: `/learn/c/l#thao-luan`,
  read,
  created_at: new Date().toISOString(),
});

function setup({ unread = 2, stream }: { unread?: number; stream?: string } = {}) {
  const marked: string[] = [];
  server.use(
    http.get(url("/me/notifications/unread"), () => HttpResponse.json({ unread })),
    http.get(url("/me/notifications"), () =>
      HttpResponse.json({ items: [item("n1", false), item("n2", true)], total: 2, page: 1, size: 10, unread }),
    ),
    // luồng SSE: mặc định treo (không gửi gì) như máy chủ đang giữ kết nối
    http.get(url("/me/notifications/stream"), () =>
      stream === undefined
        ? new HttpResponse(new ReadableStream(), { headers: { "Content-Type": "text/event-stream" } })
        : new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream" } }),
    ),
    http.post(url("/me/notifications/:id/read"), ({ params }) => {
      marked.push(params.id as string);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <NotificationBell />
    </QueryClientProvider>,
  );
  return { marked, unmount: view.unmount };
}

describe("NotificationBell", () => {
  it("nút chuông đọc được số chưa đọc; mở ra thấy danh sách, bấm thông báo chưa đọc thì đánh dấu đã đọc", async () => {
    const user = userEvent.setup();
    const { marked, unmount } = setup();
    const bell = await screen.findByRole("button", { name: "Thông báo, 2 chưa đọc" });
    await user.click(bell);
    expect(await screen.findByText("Thông báo n1")).toBeInTheDocument();
    expect(screen.getByText("Chưa đọc:")).toBeInTheDocument(); // chỉ n1 có nhãn cho trình đọc màn hình
    await user.click(screen.getByRole("link", { name: /Thông báo n1/ }));
    await waitFor(() => expect(marked).toEqual(["n1"]));
    unmount();
  });

  it("luồng SSE cập nhật số chưa đọc mà không cần tải lại trang", async () => {
    const { unmount } = setup({ unread: 0, stream: 'event: unread\ndata: {"unread": 5, "latest": null}\n\n' });
    expect(await screen.findByRole("button", { name: "Thông báo, 5 chưa đọc" })).toBeInTheDocument();
    unmount(); // hủy vòng lặp kết nối lại
  });

  it("không có gì chưa đọc: không có huy hiệu, nút 'Đã đọc hết' bị khóa", async () => {
    const user = userEvent.setup();
    const { unmount } = setup({ unread: 0 });
    await user.click(await screen.findByRole("button", { name: "Thông báo" }));
    expect(await screen.findByRole("button", { name: /Đã đọc hết/ })).toBeDisabled();
    unmount();
  });
});
```

```diff
--- a/frontend/src/components/app/app-shell.tsx
+++ b/frontend/src/components/app/app-shell.tsx
@@ -6,6 +6,7 @@
 import { useAuth } from "@/lib/auth/auth-context";
 import { cn } from "@/lib/utils";
 import { isActive, navItems } from "./nav-items";
+import { NotificationBell } from "./notification-bell";
 import { UserMenu } from "./user-menu";
 
 /**
@@ -64,7 +65,10 @@
           LMS-AI
         </Link>
         <div className="hidden md:block" />
-        <UserMenu />
+        <div className="flex items-center gap-1">
+          <NotificationBell />
+          <UserMenu />
+        </div>
       </header>
 
       <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-24 pt-4 md:px-8 md:pb-16 md:pt-6">
```

- [ ] **Bước 4: Phần thảo luận.**
  - Đặt cuối bài học, sau nút "Đánh dấu đã học xong" và "Bài tiếp".
  - Mở từ thông báo (`#thao-luan`) thì đợi danh sách tải xong rồi mới cuộn tới.
  - Ctrl+Enter để gửi, Esc để đóng ô trả lời.

```ts
"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Comment = components["schemas"]["CommentOut"];

const PAGE_SIZE = 10;

export const discussionKeys = {
  lesson: (lessonId: string) => ["discussion", lessonId] as const,
};

/** Thảo luận của một bài (B4): bình luận gốc mới nhất trước, mỗi trang 10 cái; "Xem thêm" tải trang kế. */
export function useLessonComments(lessonId: string) {
  return useInfiniteQuery({
    queryKey: discussionKeys.lesson(lessonId),
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/lessons/{lesson_id}/comments", {
          params: { path: { lesson_id: lessonId }, query: { page: pageParam, size: PAGE_SIZE } },
        }),
      ),
    getNextPageParam: (last) => (last.page * last.size < last.total ? last.page + 1 : undefined),
  });
}

export function usePostComment(lessonId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { body: string; parent_id?: string | null }) =>
      unwrap(api.POST("/api/v1/lessons/{lesson_id}/comments", { params: { path: { lesson_id: lessonId } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: discussionKeys.lesson(lessonId) }),
  });
}

export function useDeleteComment(lessonId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/comments/{comment_id}", { params: { path: { comment_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: discussionKeys.lesson(lessonId) }),
  });
}
```

```tsx
"use client";

import { MessageSquare, Reply, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { errorMessage } from "@/lib/api/errors";
import { type Comment, useDeleteComment, useLessonComments, usePostComment } from "@/lib/discussion";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const MAX_LEN = 2000;

/** Ô viết bình luận/trả lời: Ctrl+Enter để gửi, đếm ký tự khi gần chạm giới hạn. */
function CommentForm({
  id,
  label,
  placeholder,
  submitLabel,
  autoFocus = false,
  onSubmit,
  onCancel,
}: {
  id: string;
  label: string;
  placeholder: string;
  submitLabel: string;
  autoFocus?: boolean;
  onSubmit: (body: string) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const [body, setBody] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const text = body.trim();

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!text || pending) return;
    setPending(true);
    try {
      await onSubmit(text);
      setBody("");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Textarea
        id={id}
        rows={3}
        maxLength={MAX_LEN}
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void submit();
          if (e.key === "Escape" && onCancel) onCancel();
        }}
      />
      <div className="flex flex-wrap items-center justify-end gap-2">
        {body.length > MAX_LEN - 200 ? (
          <span className="mr-auto text-xs tabular-nums text-muted-foreground">
            {body.length}/{MAX_LEN}
          </span>
        ) : null}
        {onCancel ? (
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Hủy
          </Button>
        ) : null}
        <Button type="submit" size="sm" disabled={!text} loading={pending} loadingText="Đang gửi">
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

function Author({ c }: { c: Comment }) {
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
      <span className="font-semibold">{c.author_name}</span>
      {c.is_course_teacher ? (
        <span className="bg-field-1 px-1.5 py-px text-xs font-semibold text-foreground">Giảng viên</span>
      ) : c.author_role === "admin" ? (
        <span className="bg-field-2 px-1.5 py-px text-xs font-semibold text-foreground">Quản trị</span>
      ) : null}
      <time dateTime={c.created_at} className="text-xs text-muted-foreground">
        {timeAgo(c.created_at)}
      </time>
    </p>
  );
}

function CommentBody({ c }: { c: Comment }) {
  if (c.deleted) return <p className="mt-1 text-sm italic text-muted-foreground">Bình luận đã bị xóa.</p>;
  return <p className="mt-1 whitespace-pre-line break-words text-[15px] leading-relaxed">{c.body}</p>;
}

function CommentThread({
  c,
  lessonId,
  onDelete,
}: {
  c: Comment;
  lessonId: string;
  onDelete: (c: Comment) => void;
}) {
  const [replying, setReplying] = React.useState(false);
  const post = usePostComment(lessonId);
  return (
    <li className="bg-surface p-4 md:p-5">
      <Author c={c} />
      <CommentBody c={c} />
      {!c.deleted ? (
        <div className="mt-2 flex gap-1">
          <Button variant="ghost" size="sm" aria-expanded={replying} onClick={() => setReplying((v) => !v)}>
            <Reply /> Trả lời
          </Button>
          {c.can_delete ? (
            <Button variant="ghost" size="sm" onClick={() => onDelete(c)} aria-label={`Xóa bình luận của ${c.author_name}`}>
              <Trash2 /> Xóa
            </Button>
          ) : null}
        </div>
      ) : null}

      {c.replies.length > 0 || replying ? (
        <div className="mt-3 border-l-2 border-field-1 pl-4">
          {c.replies.length > 0 ? (
            <ul className="flex flex-col gap-4" aria-label={`Trả lời cho ${c.author_name}`}>
              {c.replies.map((r) => (
                <li key={r.id}>
                  <Author c={r} />
                  <CommentBody c={r} />
                  {r.can_delete && !r.deleted ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-1"
                      onClick={() => onDelete(r)}
                      aria-label={`Xóa trả lời của ${r.author_name}`}
                    >
                      <Trash2 /> Xóa
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          {replying ? (
            <div className={cn(c.replies.length > 0 && "mt-4")}>
              <CommentForm
                id={`reply-${c.id}`}
                label={`Trả lời ${c.author_name}`}
                placeholder={`Trả lời ${c.author_name}…`}
                submitLabel="Gửi trả lời"
                autoFocus
                onCancel={() => setReplying(false)}
                onSubmit={async (body) => {
                  await post.mutateAsync({ body, parent_id: c.id });
                  setReplying(false);
                }}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/**
 * Thảo luận dưới bài học (B4): học viên hỏi, giảng viên và bạn cùng khóa trả lời (một cấp). Giảng viên được báo
 * khi có câu hỏi mới, người hỏi được báo khi có trả lời (qua chuông thông báo). Liên kết `#thao-luan` cuộn tới đây.
 */
export function LessonDiscussion({ lessonId }: { lessonId: string }) {
  const comments = useLessonComments(lessonId);
  const post = usePostComment(lessonId);
  const del = useDeleteComment(lessonId);
  const [toDelete, setToDelete] = React.useState<Comment | null>(null);
  const ref = React.useRef<HTMLElement>(null);

  // Mở từ thông báo (…#thao-luan): đợi danh sách tải xong rồi mới cuộn, để vị trí không bị xô khi nội dung hiện ra
  const loaded = comments.isSuccess;
  React.useEffect(() => {
    if (loaded && window.location.hash === "#thao-luan") ref.current?.scrollIntoView({ block: "start" });
  }, [loaded]);

  const items = comments.data?.pages.flatMap((p) => p.items) ?? [];
  const total = comments.data?.pages[0]?.total ?? 0;

  return (
    <section id="thao-luan" ref={ref} aria-labelledby="h-thao-luan" className="mt-12 scroll-mt-20">
      <h2 id="h-thao-luan" className="mb-4 flex items-center gap-2 text-xl font-semibold">
        <MessageSquare className="size-5" aria-hidden /> Thảo luận{total ? ` · ${total}` : ""}
      </h2>
      <CommentForm
        id="new-comment"
        label="Đặt câu hỏi hoặc chia sẻ về bài này"
        placeholder="Bạn chưa hiểu chỗ nào trong bài? Hỏi ở đây, giảng viên sẽ được báo."
        submitLabel="Gửi"
        onSubmit={(body) => post.mutateAsync({ body })}
      />

      <div className="mt-6" aria-live="polite" aria-busy={comments.isFetching}>
        {comments.isPending ? (
          <div className="flex flex-col gap-1.5">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : comments.isError ? (
          <p className="text-sm text-muted-foreground">
            Chưa tải được thảo luận.{" "}
            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => comments.refetch()}>
              Thử lại
            </Button>
          </p>
        ) : items.length === 0 ? (
          <p className="bg-surface p-5 text-sm text-muted-foreground">Chưa có thảo luận nào. Hãy là người đầu tiên đặt câu hỏi.</p>
        ) : (
          <>
            <ul className="flex flex-col gap-1.5">
              {items.map((c) => (
                <CommentThread key={c.id} c={c} lessonId={lessonId} onDelete={setToDelete} />
              ))}
            </ul>
            {comments.hasNextPage ? (
              <Button
                variant="outline"
                className="mt-4"
                loading={comments.isFetchingNextPage}
                onClick={() => comments.fetchNextPage()}
              >
                Xem thêm thảo luận
              </Button>
            ) : null}
          </>
        )}
      </div>

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Xóa bình luận?"
        description="Nội dung sẽ được thay bằng “Bình luận đã bị xóa”. Các trả lời bên dưới vẫn được giữ."
        confirmLabel="Xóa"
        pendingLabel="Đang xóa"
        destructive
        onConfirm={async () => {
          if (!toDelete) return;
          try {
            await del.mutateAsync(toDelete.id);
          } catch (err) {
            toast.error(errorMessage(err));
            throw err;
          }
        }}
      />
    </section>
  );
}
```

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { api as url, server } from "@/test/msw";
import { LessonDiscussion } from "./lesson-discussion";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const comment = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  parent_id: null,
  body: `Câu hỏi ${id}`,
  deleted: false,
  author_name: "Bình",
  author_role: "student",
  is_course_teacher: false,
  can_delete: false,
  created_at: new Date().toISOString(),
  replies: [],
  ...over,
});

function setup(items: ReturnType<typeof comment>[], total = items.length) {
  const posted: unknown[] = [];
  const deleted: string[] = [];
  server.use(
    http.get(url("/lessons/l1/comments"), ({ request }) => {
      const page = Number(new URL(request.url).searchParams.get("page") ?? 1);
      const slice = page === 1 ? items : [comment("trang2")];
      return HttpResponse.json({ items: slice, total, page, size: 10 });
    }),
    http.post(url("/lessons/l1/comments"), async ({ request }) => {
      posted.push(await request.json());
      return HttpResponse.json(comment("moi"), { status: 201 });
    }),
    http.delete(url("/comments/:id"), ({ params }) => {
      deleted.push(params.id as string);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <LessonDiscussion lessonId="l1" />
    </QueryClientProvider>,
  );
  return { posted, deleted };
}

describe("LessonDiscussion", () => {
  it("chưa có gì: mời đặt câu hỏi; gửi thì nút khóa khi ô trống và gửi nội dung đã cắt khoảng trắng", async () => {
    const user = userEvent.setup();
    const { posted } = setup([]);
    expect(await screen.findByText(/Chưa có thảo luận nào/)).toBeInTheDocument();
    const send = screen.getByRole("button", { name: "Gửi" });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText("Đặt câu hỏi hoặc chia sẻ về bài này"), "  Em chưa hiểu phần 2  ");
    await user.click(send);
    await waitFor(() => expect(posted).toEqual([{ body: "Em chưa hiểu phần 2" }]));
    expect(screen.getByLabelText("Đặt câu hỏi hoặc chia sẻ về bài này")).toHaveValue("");
  });

  it("hiện nhãn Giảng viên ở câu trả lời, bình luận đã xóa và trả lời một cấp", async () => {
    const user = userEvent.setup();
    const { posted } = setup([
      comment("c1", {
        replies: [comment("r1", { parent_id: "c1", author_name: "Cô Lan", author_role: "teacher", is_course_teacher: true, body: "Xem trang 3 nhé" })],
      }),
      comment("c2", { deleted: true, body: null }),
    ]);
    expect(await screen.findByText("Câu hỏi c1")).toBeInTheDocument();
    const replies = screen.getByRole("list", { name: "Trả lời cho Bình" });
    expect(within(replies).getByText("Giảng viên")).toBeInTheDocument();
    expect(screen.getByText("Bình luận đã bị xóa.")).toBeInTheDocument();
    // bình luận đã xóa không có nút Trả lời: chỉ c1 có
    const replyButtons = screen.getAllByRole("button", { name: "Trả lời" });
    expect(replyButtons).toHaveLength(1);
    await user.click(replyButtons[0]);
    await user.type(screen.getByLabelText("Trả lời Bình"), "Dạ em hiểu rồi");
    await user.click(screen.getByRole("button", { name: "Gửi trả lời" }));
    await waitFor(() => expect(posted).toEqual([{ body: "Dạ em hiểu rồi", parent_id: "c1" }]));
  });

  it("xóa cần xác nhận; 'Xem thêm' tải trang kế", async () => {
    const user = userEvent.setup();
    const { deleted } = setup([comment("c1", { can_delete: true })], 11);
    await user.click(await screen.findByRole("button", { name: "Xóa bình luận của Bình" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Xóa" }));
    await waitFor(() => expect(deleted).toEqual(["c1"]));
    await user.click(screen.getByRole("button", { name: "Xem thêm thảo luận" }));
    expect(await screen.findByText("Câu hỏi trang2")).toBeInTheDocument();
  });
});
```

```diff
--- a/frontend/src/components/lesson/lesson-view.tsx
+++ b/frontend/src/components/lesson/lesson-view.tsx
@@ -19,6 +19,7 @@
 import * as React from "react";
 import { toast } from "sonner";
 import { ThemeSwitcher } from "@/components/app/theme-switcher";
+import { NotificationBell } from "@/components/app/notification-bell";
 import { UserMenu } from "@/components/app/user-menu";
 import { ErrorState } from "@/components/app/states";
 import { Markdown } from "@/components/content/markdown";
@@ -41,6 +42,7 @@
 import { canAskTutor, useTutorChat } from "@/lib/tutor/use-tutor-chat";
 import { cn } from "@/lib/utils";
 import { BreakReminder } from "./break-reminder";
+import { LessonDiscussion } from "./lesson-discussion";
 import { LessonMaterials } from "./lesson-materials";
 import { LessonQuizzes } from "./lesson-quizzes";
 import { CourseOutline } from "./course-outline";
@@ -206,6 +208,7 @@
         <Button variant="ghost" className="hidden lg:inline-flex" aria-pressed={tutorOpen} onClick={() => setTutorOpen((v) => !v)}>
           <MessageCircleQuestion /> Hỏi AI
         </Button>
+        <NotificationBell />
         <UserMenu compact />
       </header>
 
@@ -264,6 +267,8 @@
                   onGo={go}
                   videoRef={videoRef}
                 />
+
+                <LessonDiscussion lessonId={lessonId} />
               </>
             )}
           </article>
```

- [ ] **Bước 5:** `cd frontend; npx tsc --noEmit; npx eslint .; npx vitest run` (**178 pass**). Commit:

```powershell
git add frontend
git commit -m "feat(web): chuông thông báo realtime và phần thảo luận dưới bài học"
```

---

## Task 4: Frontend: phân tích lớp, E2E, tài liệu

**Files:**
- Create: `frontend/src/components/teach/meter.tsx`, `frontend/src/components/teach/course-insights.tsx`, `frontend/src/components/teach/course-insights.test.tsx`, `frontend/e2e/discussion-notifications.spec.ts`
- Modify: `frontend/src/lib/quiz/queries.ts`, `frontend/src/components/teach/course-analytics.tsx`, `frontend/e2e/mock-api.ts`, `docs/specs/2026-09-29-lms-ai-design.md`, `docs/design/design-system.md`

- [ ] **Bước 1: Truy vấn và giao diện.** `Meter` được chuyển ra file riêng để trang thống kê và phần phân tích dùng chung, không import vòng.

```diff
--- a/frontend/src/lib/quiz/queries.ts
+++ b/frontend/src/lib/quiz/queries.ts
@@ -14,6 +14,7 @@
   quiz: (quizId: string) => ["quiz", quizId] as const,
   result: (attemptId: string) => ["attempt-result", attemptId] as const,
   analytics: (courseId: string) => ["analytics", courseId] as const,
+  insights: (courseId: string) => ["insights", courseId] as const,
   job: (jobId: string) => ["job", jobId] as const,
 };
 
@@ -161,3 +162,12 @@
     queryFn: () => unwrap(api.GET("/api/v1/courses/{course_id}/analytics", { params: { path: { course_id: courseId! } } })),
   });
 }
+
+/** Phân tích lớp học (B7): câu hay sai, bài yếu, học viên cần để ý. */
+export function useCourseInsights(courseId: string | undefined) {
+  return useQuery({
+    queryKey: quizKeys.insights(courseId ?? "none"),
+    enabled: !!courseId,
+    queryFn: () => unwrap(api.GET("/api/v1/courses/{course_id}/insights", { params: { path: { course_id: courseId! } } })),
+  });
+}
```

```tsx
/** Thanh ngang một màu; con số luôn in kèm nên không phụ thuộc màu (dataviz: text dùng màu chữ, không dùng màu thanh). */
export function Meter({ value, label }: { value: number; label: string }) {
  const v = Math.min(1, Math.max(0, value));
  return (
    <div className="flex items-center gap-3" title={label}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className="h-full rounded-full bg-accent" style={{ width: `${v * 100}%` }} />
      </div>
      <span className="w-24 shrink-0 text-right tabular-nums">{label}</span>
    </div>
  );
}
```

```tsx
"use client";

import { CircleAlert } from "lucide-react";
import Link from "next/link";
import { Skeleton } from "@/components/ui/misc";
import { Meter } from "@/components/teach/meter";
import { timeAgo } from "@/lib/format";
import { useCourseInsights } from "@/lib/quiz/queries";

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Phân tích lớp học (B7) dưới bảng thống kê: ba danh sách ngắn giúp giảng viên biết nên sửa gì và nhắc ai.
 * Mỗi dòng dẫn tới đúng chỗ cần sửa (ngân hàng câu hỏi của bài, trang bài học).
 */
export function CourseInsightsSection({ slug, courseId }: { slug: string; courseId: string }) {
  const insights = useCourseInsights(courseId);
  if (insights.isPending) return <Skeleton className="mt-10 h-60" aria-label="Đang tải phân tích lớp học" />;
  if (insights.isError) return null; // bảng thống kê phía trên đã báo lỗi tải nếu có
  const { hard_questions, weak_lessons, students_at_risk, min_answers } = insights.data;

  return (
    <div className="mt-10 space-y-10">
      <section aria-labelledby="hard-q">
        <h2 id="hard-q" className="mb-1 text-lg font-semibold">
          Câu hỏi học viên hay làm sai
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Chỉ xếp hạng câu có từ {min_answers} lượt trả lời. Tỉ lệ sai cao thường do đề chưa rõ, đáp án sai hoặc tài liệu chưa nói kỹ.
        </p>
        {hard_questions.length === 0 ? (
          <p className="bg-surface p-4 text-sm text-muted-foreground">Chưa đủ lượt làm bài để xếp hạng.</p>
        ) : (
          <ol className="flex flex-col gap-1.5">
            {hard_questions.map((q) => (
              <li key={q.question_id}>
                <Link
                  href={`/teach/${slug}/lessons/${q.lesson_id}/questions`}
                  className="group grid gap-3 bg-surface p-4 transition-colors duration-150 hover:bg-field-3 md:grid-cols-[minmax(0,1fr)_220px] md:gap-6"
                >
                  <span className="min-w-0">
                    <span className="line-clamp-2 block font-medium">{q.stem}</span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      {q.lesson_title}
                      {q.source_page != null ? ` · tài liệu trang ${q.source_page}` : ""} · đáp án đúng {q.correct_option}
                      {q.top_wrong ? `, hay chọn nhầm ${q.top_wrong.id} (${q.top_wrong.count} lượt)` : ""}
                    </span>
                  </span>
                  <span className="flex flex-col justify-center gap-1 text-sm">
                    <Meter value={q.wrong_rate} label={`${pct(q.wrong_rate)} sai`} />
                    <span className="text-right text-xs text-muted-foreground tabular-nums">
                      {q.wrong}/{q.answers} lượt
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="weak-l">
        <h2 id="weak-l" className="mb-1 text-lg font-semibold">
          Bài học cần xem lại
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">Xếp theo điểm quiz trung bình thấp nhất, rồi theo số câu học viên hỏi AI Tutor.</p>
        {weak_lessons.length === 0 ? (
          <p className="bg-surface p-4 text-sm text-muted-foreground">Chưa có bài nào có số liệu.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border bg-surface" tabIndex={0} role="region" aria-label="Bảng bài học cần xem lại">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="border-b text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Bài học</th>
                  <th className="px-4 py-2 font-medium">Điểm quiz TB</th>
                  <th className="px-4 py-2 font-medium">Bài nộp</th>
                  <th className="px-4 py-2 font-medium">Câu hỏi AI Tutor</th>
                </tr>
              </thead>
              <tbody>
                {weak_lessons.map((l) => (
                  <tr key={l.lesson_id} className="border-b last:border-b-0">
                    <td className="px-4 py-2.5">
                      <Link href={`/teach/${slug}/lessons/${l.lesson_id}`} className="block font-medium hover:underline">
                        {l.title}
                      </Link>
                      <span className="text-xs text-muted-foreground">{l.section_title}</span>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums">{l.avg_score == null ? "—" : `${l.avg_score.toFixed(1)}%`}</td>
                    <td className="px-4 py-2.5 tabular-nums">{l.attempts}</td>
                    <td className="px-4 py-2.5 tabular-nums">{l.tutor_questions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="at-risk">
        <h2 id="at-risk" className="mb-1 text-lg font-semibold">
          Học viên cần để ý ({students_at_risk.length})
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Chưa xong khóa và điểm quiz trung bình dưới 50% hoặc 7 ngày không học. Ai lâu không học nhất đứng đầu.
        </p>
        {students_at_risk.length === 0 ? (
          <p className="bg-surface p-4 text-sm text-muted-foreground">Không có học viên nào cần để ý lúc này.</p>
        ) : (
          <ul className="grid gap-1.5 md:grid-cols-2">
            {students_at_risk.map((s) => (
              <li key={s.user_id} className="flex flex-col gap-2 bg-surface p-4">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="font-semibold">{s.full_name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">học lần cuối {timeAgo(s.last_active_at)}</span>
                </span>
                <Meter value={s.progress_pct / 100} label={`${s.progress_pct}% khóa`} />
                <ul className="flex flex-wrap gap-1.5">
                  {s.reasons.map((r) => (
                    <li key={r} className="inline-flex items-center gap-1 bg-field-2 px-2 py-0.5 text-xs font-semibold text-foreground">
                      <CircleAlert className="size-3.5" aria-hidden /> {r}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
```

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api as url, server } from "@/test/msw";
import { CourseInsightsSection } from "./course-insights";

function setup(body: Record<string, unknown>) {
  server.use(http.get(url("/courses/c1/insights"), () => HttpResponse.json({ course_id: "c1", min_answers: 3, ...body })));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CourseInsightsSection slug="khoa" courseId="c1" />
    </QueryClientProvider>,
  );
}

describe("CourseInsightsSection", () => {
  it("câu hay sai dẫn tới ngân hàng câu hỏi của bài, ghi rõ trang tài liệu và phương án hay chọn nhầm", async () => {
    setup({
      hard_questions: [
        {
          question_id: "q1",
          stem: "TCP khác UDP ở điểm nào?",
          lesson_id: "l1",
          lesson_title: "Tầng giao vận",
          answers: 4,
          wrong: 3,
          wrong_rate: 0.75,
          correct_option: "B",
          top_wrong: { id: "C", text: "…", count: 2 },
          source_page: 12,
        },
      ],
      weak_lessons: [
        { lesson_id: "l1", title: "Tầng giao vận", section_title: "Chương 2", attempts: 4, avg_score: 37.5, tutor_questions: 6 },
      ],
      students_at_risk: [
        {
          user_id: "u1",
          full_name: "Trần Thị Mai",
          progress_pct: 20,
          avg_score: 30,
          last_active_at: new Date(Date.now() - 9 * 86400_000).toISOString(),
          reasons: ["Điểm quiz trung bình 30%", "Không học 9 ngày"],
        },
      ],
    });
    const link = await screen.findByRole("link", { name: /TCP khác UDP/ });
    expect(link).toHaveAttribute("href", "/teach/khoa/lessons/l1/questions");
    expect(link).toHaveTextContent("tài liệu trang 12");
    expect(link).toHaveTextContent("hay chọn nhầm C (2 lượt)");
    expect(link).toHaveTextContent("75% sai");
    expect(screen.getByRole("cell", { name: "37.5%" })).toBeInTheDocument();
    expect(screen.getByText("Học viên cần để ý (1)")).toBeInTheDocument();
    expect(screen.getByText("Không học 9 ngày")).toBeInTheDocument();
    expect(screen.getByText("học lần cuối 9 ngày trước")).toBeInTheDocument();
  });

  it("chưa đủ số liệu: mỗi phần có câu giải thích thay vì bảng trống", async () => {
    setup({ hard_questions: [], weak_lessons: [], students_at_risk: [] });
    expect(await screen.findByText("Chưa đủ lượt làm bài để xếp hạng.")).toBeInTheDocument();
    expect(screen.getByText("Chưa có bài nào có số liệu.")).toBeInTheDocument();
    expect(screen.getByText("Không có học viên nào cần để ý lúc này.")).toBeInTheDocument();
  });
});
```

```diff
--- a/frontend/src/components/teach/course-analytics.tsx
+++ b/frontend/src/components/teach/course-analytics.tsx
@@ -3,6 +3,8 @@
 import { ArrowLeft, BarChart3 } from "lucide-react";
 import Link from "next/link";
 import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
+import { CourseInsightsSection } from "@/components/teach/course-insights";
+import { Meter } from "@/components/teach/meter";
 import { FeedbackList } from "@/components/tutor/feedback-list";
 import { Badge, Skeleton } from "@/components/ui/misc";
 import { useCourse } from "@/lib/queries";
@@ -122,6 +124,7 @@
           </section>
         </div>
       )}
+      {course.data && stats.data && stats.data.enrollments > 0 ? <CourseInsightsSection slug={slug} courseId={course.data.id} /> : null}
       {course.data ? <TutorFeedbackSection courseId={course.data.id} /> : null}
     </>
   );
@@ -153,16 +156,3 @@
     </div>
   );
 }
-
-/** Thanh ngang một màu; con số luôn in kèm nên không phụ thuộc màu (dataviz: text dùng màu chữ, không dùng màu thanh). */
-function Meter({ value, label }: { value: number; label: string }) {
-  const v = Math.min(1, Math.max(0, value));
-  return (
-    <div className="flex items-center gap-3" title={label}>
-      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
-        <div className="h-full rounded-full bg-accent" style={{ width: `${v * 100}%` }} />
-      </div>
-      <span className="w-24 shrink-0 text-right tabular-nums">{label}</span>
-    </div>
-  );
-}
```

- [ ] **Bước 2: E2E.**
  - `mock-api.ts` thêm handler mặc định cho thảo luận, thông báo và phân tích, để các spec cũ không gặp `UNMOCKED`.
  - Muốn ghi đè thì spec phải dùng **đúng khóa** của handler mặc định (ví dụ `"GET /courses/*/insights"`). Lý do: bộ mock lấy handler khớp đầu tiên.

```diff
--- a/frontend/e2e/mock-api.ts
+++ b/frontend/e2e/mock-api.ts
@@ -141,6 +141,14 @@
     "POST /tutor/messages/*/followups": (r) => json(r, { questions: [] }),
     "GET /notes": (r) => json(r, { items: [], total: 0, page: 1, size: 20 }),
     "GET /me/pending-quizzes": (r) => json(r, []),
+    // B4/B6/B7: mặc định chưa có thảo luận, thông báo hay số liệu phân tích
+    "GET /lessons/*/comments": (r) => json(r, { items: [], total: 0, page: 1, size: 10 }),
+    "GET /me/notifications": (r) => json(r, { items: [], total: 0, page: 1, size: 10, unread: 0 }),
+    "GET /me/notifications/unread": (r) => json(r, { unread: 0 }),
+    "GET /me/notifications/stream": (r) =>
+      r.fulfill({ status: 200, contentType: "text/event-stream", body: 'event: unread\ndata: {"unread": 0, "latest": null}\n\n' }),
+    "GET /courses/*/insights": (r) =>
+      json(r, { course_id: COURSE_ID, min_answers: 3, hard_questions: [], weak_lessons: [], students_at_risk: [] }),
     ...opts.extra,
   };
 
```

```ts
import { expect, test } from "@playwright/test";
import { expectAccessible, expectNoHorizontalScroll } from "./a11y";
import { COURSE_ID, courseDetail, L1, mockApi, teacher } from "./mock-api";

const now = () => new Date(Date.now() - 5 * 60_000).toISOString();

const reply = {
  id: "c-2",
  parent_id: "c-1",
  body: "Em xem lại ví dụ ở trang 4 giáo trình nhé.",
  deleted: false,
  author_name: "Trần Thị Bình",
  author_role: "teacher",
  is_course_teacher: true,
  can_delete: false,
  created_at: now(),
  replies: [],
};
const thread = {
  id: "c-1",
  parent_id: null,
  body: "Tại sao h phải tiến về 0 mà không bằng 0 ạ?",
  deleted: false,
  author_name: "Nguyễn Văn An",
  author_role: "student",
  is_course_teacher: false,
  can_delete: true,
  created_at: now(),
  replies: [reply],
};

test.describe("thảo luận và thông báo", () => {
  test("học viên nhận thông báo có trả lời, bấm vào thì tới đúng phần thảo luận của bài và hỏi tiếp", async ({ page }) => {
    let unread = 1;
    let marked = "";
    let posted: unknown = null;
    const notif = {
      id: "n-1",
      kind: "comment_reply",
      title: "Trần Thị Bình đã trả lời bạn",
      body: reply.body,
      link: `/learn/giai-tich-1/${L1}#thao-luan`,
      read: false,
      created_at: now(),
    };
    await mockApi(page, {
      extra: {
        "GET /me/notifications/unread": (r) => r.fulfill({ json: { unread } }),
        "GET /me/notifications/stream": (r) =>
          r.fulfill({ status: 200, contentType: "text/event-stream", body: `event: unread\ndata: {"unread": ${unread}, "latest": null}\n\n` }),
        "GET /me/notifications": (r) =>
          r.fulfill({ json: { items: [{ ...notif, read: unread === 0 }], total: 1, page: 1, size: 10, unread } }),
        "POST /me/notifications/*/read": (r) => {
          marked = new URL(r.request().url()).pathname.split("/").at(-2) ?? "";
          unread = 0;
          return r.fulfill({ status: 204 });
        },
        "GET /lessons/*/comments": (r) => r.fulfill({ json: { items: [thread], total: 1, page: 1, size: 10 } }),
        "POST /lessons/*/comments": (r) => {
          posted = r.request().postDataJSON();
          return r.fulfill({ status: 201, json: { ...thread, id: "c-3", replies: [] } });
        },
      },
    });
    await page.goto("/");
    const bell = page.getByRole("button", { name: "Thông báo, 1 chưa đọc" });
    await expect(bell).toBeVisible();
    await bell.click();
    await expect(page.getByRole("heading", { name: "Thông báo" })).toBeVisible();
    await expectAccessible(page);
    await page.getByRole("link", { name: /Trần Thị Bình đã trả lời bạn/ }).click();

    await expect(page).toHaveURL(new RegExp(`/learn/giai-tich-1/${L1}#thao-luan$`));
    expect(marked).toBe("n-1");
    const section = page.getByRole("region", { name: /Thảo luận/ });
    await expect(section.getByText(reply.body)).toBeInViewport();
    await expect(section.getByText("Giảng viên", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Thông báo", exact: true })).toBeVisible();

    await section.getByRole("button", { name: "Trả lời" }).click();
    await section.getByLabel("Trả lời Nguyễn Văn An").fill("Em cảm ơn cô, em hiểu rồi ạ.");
    await section.getByRole("button", { name: "Gửi trả lời" }).click();
    await expect.poll(() => posted).toEqual({ body: "Em cảm ơn cô, em hiểu rồi ạ.", parent_id: "c-1" });
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });

  test("giảng viên xem phân tích lớp: câu hay sai, bài cần xem lại, học viên cần để ý", async ({ page }) => {
    await mockApi(page, {
      user: teacher,
      extra: {
        "GET /courses/giai-tich-1": (r) => r.fulfill({ json: courseDetail({ is_owner: true }) }),
        [`GET /courses/${COURSE_ID}/analytics`]: (r) =>
          r.fulfill({
            json: {
              course_id: COURSE_ID,
              enrollments: 12,
              completed_enrollments: 3,
              lessons: [{ lesson_id: L1, title: "Định nghĩa đạo hàm", section_title: "Đạo hàm", done_count: 9, completion_rate: 0.75 }],
              quizzes: [],
              tutor: { sessions: 20, questions: 57, refused_answers: 4 },
            },
          }),
        "GET /courses/*/insights": (r) =>
          r.fulfill({
            json: {
              course_id: COURSE_ID,
              min_answers: 3,
              hard_questions: [
                {
                  question_id: "q-1",
                  stem: "Đạo hàm của x² tại x = 3 bằng bao nhiêu?",
                  lesson_id: L1,
                  lesson_title: "Định nghĩa đạo hàm",
                  answers: 10,
                  wrong: 7,
                  wrong_rate: 0.7,
                  correct_option: "B",
                  top_wrong: { id: "A", text: "3", count: 5 },
                  source_page: 4,
                },
              ],
              weak_lessons: [
                { lesson_id: L1, title: "Định nghĩa đạo hàm", section_title: "Đạo hàm", attempts: 10, avg_score: 42.5, tutor_questions: 31 },
              ],
              students_at_risk: [
                {
                  user_id: "u-9",
                  full_name: "Lê Minh Châu",
                  progress_pct: 15,
                  avg_score: 30,
                  last_active_at: new Date(Date.now() - 10 * 86_400_000).toISOString(),
                  reasons: ["Điểm quiz trung bình 30%", "Không học 10 ngày"],
                },
              ],
            },
          }),
      },
    });
    await page.goto("/teach/giai-tich-1/analytics");
    await expect(page.getByRole("heading", { name: "Câu hỏi học viên hay làm sai" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Đạo hàm của x²/ })).toHaveAttribute(
      "href",
      `/teach/giai-tich-1/lessons/${L1}/questions`,
    );
    await expect(page.getByText("70% sai")).toBeVisible();
    await expect(page.getByText("42.5%")).toBeVisible();
    await expect(page.getByText("Không học 10 ngày")).toBeVisible();
    await expectAccessible(page);
    await expectNoHorizontalScroll(page);
  });
});
```

- [ ] **Bước 3: Tài liệu.** Đánh dấu B4, B6, B7 đã xong. Sửa bảng API thông báo theo thiết kế thật (không dùng stream-token), thêm mục phân tích B7 và dòng quyết định 2026-10-19. Design system thêm chuông, phần thảo luận và trang phân tích.

```diff
--- a/docs/specs/2026-09-29-lms-ai-design.md
+++ b/docs/specs/2026-09-29-lms-ai-design.md
@@ -32,10 +32,10 @@
 - [x] B1. Quiz nâng cao: tính giờ, xáo trộn, làm lại nhiều lần, autosave, cron chốt bài khi hết giờ (xáo thứ tự câu hỏi; chưa xáo phương án)
 - [x] B2. Hybrid search (full-text + vector, RRF)
 - [x] B3. AI giải thích câu học viên làm sai (dùng chung qua `llm_cache`, lưu ở `attempt_answers.ai_explanation`; không tạo bảng `explanation_cache`)
-- [ ] B4. Thảo luận theo bài học (2 cấp)
+- [x] B4. Thảo luận theo bài học (2 cấp: câu hỏi gốc và trả lời, không trả lời lồng sâu hơn)
 - [ ] B5. Assignment + AI gợi ý chấm theo rubric, giáo viên xác nhận
-- [ ] B6. Thông báo realtime (SSE)
-- [ ] B7. Phân tích lớp học (câu hay sai, chủ đề yếu)
+- [x] B6. Thông báo realtime (SSE qua `fetch` có Bearer token, Redis pub/sub chỉ để báo hiệu, DB là nguồn dữ liệu)
+- [x] B7. Phân tích lớp học (câu hay sai, bài yếu, học viên cần để ý)
 - [x] B8. Trang admin (duyệt giáo viên, quản lý user và khóa học)
 
 ### Tầng S: chất lượng hệ thống (rải từ tuần 1 đến tuần 4, trước tầng C)
@@ -503,15 +503,17 @@
 | Quiz | `POST /quizzes` · `GET /quizzes?lesson_id=` (phân trang) · `GET/PATCH/DELETE /quizzes/{id}` · `POST /quizzes/{id}/publish` · `POST /quizzes/{id}/attempts` (**không trả đáp án**) · `PUT /attempts/{id}/answers/{qid}` · `POST /attempts/{id}/submit {final_answers?}` · `GET /attempts/{id}/result` (chỉ khi `completed` hoặc `timed_out`) · `POST /attempts/{id}/answers/{qid}/explain` |
 | Assignment | CRUD `/assignments` · `PUT /assignments/{id}/submission` · `GET /assignments/{id}/submissions` · `POST /submissions/{id}/grade` |
 | Thảo luận | `GET/POST /lessons/{id}/comments` · `DELETE /comments/{id}` |
-| Thông báo | `GET /notifications` · `POST /notifications/read` · `GET /notifications/stream-token` (sống 60 giây) · `GET /notifications/stream?t=` (dùng `EventSource`) |
+| Thông báo | `GET /me/notifications` (kèm `unread`) · `GET /me/notifications/unread` · `POST /me/notifications/{id}/read` · `POST /me/notifications/read-all` · `GET /me/notifications/stream` (SSE, đọc bằng `fetch` có header Bearer nên không cần stream-token) |
 | Vận hành | `GET /api/v1/health` (tiến trình còn sống) · `GET /api/v1/ready` (DB, Redis, MinIO; `503` khi có phần lỗi) · `GET /metrics` (Prometheus, chỉ trong mạng nội bộ, Caddy không chuyển ra ngoài) |
-| Khác | `GET /jobs/{id}` (chỉ người tạo job hoặc admin; người khác nhận `404`) · `GET /courses/{id}/analytics` (giảng viên sở hữu hoặc admin) · `GET /me/certificates` · `GET /certificates/verify/{code}` (công khai) |
+| Khác | `GET /jobs/{id}` (chỉ người tạo job hoặc admin; người khác nhận `404`) · `GET /courses/{id}/analytics` và `GET /courses/{id}/insights` (giảng viên sở hữu hoặc admin) · `GET /me/certificates` · `GET /certificates/verify/{code}` (công khai) |
 | Admin | `GET/PATCH /admin/users` · `GET/PATCH /admin/courses` |
 
 **Dashboard A8 (`GET /courses/{id}/analytics`):** `enrollments`, `completed_enrollments` (có `completed_at`); `lessons[]` = `{done_count, completion_rate}` với `completion_rate = done_count / số đăng ký` (0..1); `quizzes[]` = `{attempts, students, avg_score, pass_rate}` chỉ tính bài đã nộp (`completed` + `timed_out`), `avg_score` là trung bình điểm phần trăm, `pass_rate` = số bài có `score ≥ pass_score` chia `attempts`; `tutor` = `{sessions, questions, refused_answers}`. Phân tích sâu (câu hay sai, chủ đề yếu) là B7.
 
 - `completion_rate` (chốt 2026-10-04): `done_count` chỉ đếm học viên **đang** đăng ký khóa có tiến độ `done` ở bài đó (tiến độ của người đã hủy đăng ký không tính); mẫu số là số đăng ký hiện tại; không có đăng ký nào → `0.0`; làm tròn 4 chữ số. `avg_score` là trung bình của các điểm đã làm tròn; thống kê Tutor gồm cả phiên xem thử của giảng viên/admin.
 
+**Phân tích lớp B7 (`GET /courses/{id}/insights`, chốt 2026-10-19):** chỉ tính bài quiz đã nộp. `hard_questions` (tối đa 10): câu có ít nhất `min_answers = 3` lượt trả lời và ít nhất một lượt sai, xếp theo tỉ lệ sai giảm dần, kèm phương án sai được chọn nhiều nhất và trang tài liệu của chunk nguồn. `weak_lessons` (tối đa 5): xếp theo điểm quiz trung bình tăng dần (bài chưa có bài nộp đứng sau), rồi số câu hỏi AI Tutor giảm dần. `students_at_risk` (tối đa 20): học viên chưa hoàn thành khóa có điểm quiz trung bình dưới 50% hoặc 7 ngày không hoạt động (hoạt động gần nhất = muộn nhất trong lúc đăng ký, cập nhật tiến độ, bắt đầu làm quiz, câu hỏi gửi Tutor), người lâu không học nhất đứng đầu.
+
 **Xóa khóa/chương/bài (chốt 2026-10-04):** `DELETE /courses/{id}`, `/sections/{id}`, `/lessons/{id}` trả `409 INVALID_STATE` (thông báo tiếng Việt nêu lý do) **chỉ khi** phần bị xóa (cascade) chứa dữ liệu của học viên: (1) bất kỳ lượt làm quiz nào trên các bài trong phạm vi; (2) phiên hỏi Tutor có tin nhắn của người không phải staff của khóa (bỏ qua chủ khóa và admin, vì đó là phiên xem thử) — với khóa: mọi phiên của khóa, kể cả hỏi cả khóa; với chương/bài: phiên gắn với các bài đó; (3) xóa khóa: khóa có ít nhất một lượt đăng ký; (4) xóa chương/bài: có `lesson_progress` của học viên đang đăng ký khóa trên các bài đó. Quiz (kể cả quiz đã xuất bản nhưng chưa ai làm), câu hỏi, tài liệu và phiên xem thử của staff vẫn bị xóa theo cascade như trước. Trong lúc kiểm tra, dòng khóa học (khi xóa khóa), các bài và quiz trong phạm vi bị khóa `FOR UPDATE`, nên lượt làm/đăng ký/tiến độ/phiên Tutor mới (có khóa ngoại tới các dòng đó) phải đợi tới khi xóa xong và không chen được vào giữa.
 
 ### 6.5 Luật làm quiz
@@ -771,3 +773,4 @@
 | 2026-10-12 | B1: `time_limit_sec` (60 giây – 4 giờ) và `shuffle` khi tạo/sửa quiz (null tường minh = bỏ giới hạn); `deadline_at` theo giờ DB, `server_now` trong bài làm để đồng hồ không lệch; quá `deadline_at + 5s` thì lưu/nộp bị từ chối và bài chốt `timed_out` với đáp án đã autosave; chốt khi có thao tác trên bài + cron mỗi phút. B2: hybrid vector top-20 + full-text top-20 gộp RRF (k=60), `RETRIEVAL_MODE=vector` để so sánh, benchmark có `mode=`. B3: `POST /attempts/{id}/answers/{qid}/explain` sau khi nộp, chỉ câu sai/bỏ trống, 30 lần/giờ/học viên, lỗi AI → 503 |
 | 2026-10-15 | Hồ sơ cá nhân: `PATCH /me` (họ tên, gọn khoảng trắng, 1–120 ký tự), `POST /me/password` (đúng mật khẩu hiện tại, khác mật khẩu cũ, 10 lần thử/giờ/tài khoản; thu hồi mọi phiên rồi cấp phiên mới cho trình duyệt đang dùng). Menu tài khoản (Hồ sơ cá nhân, Ghi chú, chế độ màu, Đăng xuất) ở thanh trên của mọi trang kể cả trang học và quiz; đăng xuất tải lại trang chủ. Giao diện: bảng màu sáng trung tính, bo góc 4px, `--mark` cho trích dẫn; trang chủ cho khách mới (không nằm trong khung app) có phần thử hỏi với 4 câu mẫu cố định |
 | 2026-10-15 | Giao diện sau đăng nhập cùng giọng với trang chủ cho khách: thanh bên một tông màu, ô tên app nền đậm, tiêu đề trang 800; trang chủ học viên có lời chào lớn, khối đang học (tên bài lấy từ API, phần đã đọc lưu trên máy), ba con số, "Việc nên làm tiếp" từ `GET /me/pending-quizzes` (quiz đã xuất bản trong khóa đã đăng ký, chưa nộp lần nào, bài làm dở trước, tối đa 6), danh sách khóa dạng hàng; Khám phá có khóa mới nhất trong khối màu và mục lục khóa; Khóa của tôi chia Đang học / Đã xong |
+| 2026-10-19 | B4 thảo luận: bảng `lesson_comments` (gốc + trả lời một cấp, xóa mềm), ai vào được bài thì đọc và viết được; tác giả, giảng viên của khóa hoặc admin được xóa, người khác nhận 404; 30 bình luận/giờ/người. B6 thông báo: bảng `notifications` (trả lời bình luận, câu hỏi mới cho giảng viên, quiz mới xuất bản cho học viên đã đăng ký, tài liệu/câu hỏi AI xong hoặc lỗi cho người tạo job); ghi cùng transaction với sự kiện, sau commit mới phát tín hiệu Redis `notif:{user_id}`; SSE `/me/notifications/stream` không giữ kết nối DB, gửi số chưa đọc khi có tín hiệu, ping 25 giây, Redis lỗi thì tự đọc lại DB theo chu kỳ. B7 `GET /courses/{id}/insights` (xem mục Dashboard) |
```

```diff
--- a/docs/design/design-system.md
+++ b/docs/design/design-system.md
@@ -177,7 +177,7 @@
   - Học viên: Trang chủ, Khám phá, Khóa của tôi.
   - Giảng viên: Khóa đang dạy, Câu hỏi chờ duyệt.
   - Admin: Duyệt giảng viên.
-  - Menu tài khoản ở góc trên phải.
+  - Menu tài khoản ở góc trên phải, bên trái nó là chuông thông báo (số chưa đọc trên huy hiệu, `aria-label` đọc cả số; danh sách 10 thông báo mới nhất trong popover, thông báo chưa đọc in đậm và có chấm màu kèm nhãn ẩn "Chưa đọc"). Chuông có cả ở thanh trên của trang bài học.
 - **Điện thoại (< 768px):** thanh điều hướng dưới cùng, **tối đa 3 mục**, có icon và chữ. Tài khoản (hồ sơ, đăng xuất) nằm ở nút chữ cái tròn góc trên, có ở mọi trang. Trang bài học **ẩn thanh dưới** để có thêm chỗ đọc.
 - **Tablet:** thanh bên thu gọn (icon).
 - **Breadcrumb** (Khóa học › Chương › Bài) trên desktop. Trên điện thoại chỉ hiện nút ← với tên cấp cha.
@@ -201,6 +201,7 @@
 - **Desktop:** cột nội dung 68 ký tự ở giữa; mục lục khóa ở trái (thu gọn được); panel Tutor ở phải (400px, mở/đóng). Khi mở Tutor, cột nội dung **không bị co** dưới 60 ký tự; nếu màn hình hẹp, Tutor đè lên làm lớp nổi.
 - **Điện thoại:** video ở trên, dính trên cùng khi cuộn (có nút thu nhỏ). Nội dung ở dưới. Nút nổi "Hỏi AI" ở góc dưới phải, mở khung trượt từ dưới lên chiếm 85% chiều cao, vuốt xuống để đóng, và giữ nguyên lịch sử chat.
 - Thanh tiến độ mảnh (2px) màu `--accent` ở mép trên, cho biết đã đọc tới đâu.
+- Cuối bài là phần **Thảo luận** (`#thao-luan`, liên kết từ thông báo cuộn thẳng tới đây): ô hỏi ở trên, câu hỏi mới nhất trước, trả lời thụt vào một cấp có vạch `--field-1` bên trái; giảng viên của khóa có nhãn "Giảng viên" nền `--field-1` chữ `--foreground`; bình luận đã xóa còn dòng "Bình luận đã bị xóa." để giữ mạch trả lời; xóa luôn qua hộp xác nhận.
 
 ### 7.3 Luồng giảng viên
 
@@ -214,6 +215,8 @@
 
 Trình soạn khóa trên desktop có 3 vùng: mục lục bên trái, nội dung bài ở giữa, thông tin và tài liệu của bài bên phải. Trên điện thoại chỉ cho xem và sửa nhẹ (tên, nội dung). Kéo thả dùng nút ↑↓ thay thế. Có dòng chữ "Soạn nội dung dài nên dùng máy tính".
 
+Trang **Thống kê khóa học** có thêm ba phần phân tích lớp (B7) dưới bảng quiz: câu hay sai (mỗi dòng dẫn tới ngân hàng câu hỏi của bài), bài cần xem lại (bảng), học viên cần để ý (thẻ có tiến độ và lý do in bằng chữ, không chỉ dựa vào màu). Phần nào chưa đủ số liệu thì có một câu giải thích thay vì bảng trống.
+
 ---
 
 ## 8. Tính năng cho buổi học dài
```

- [ ] **Bước 4: Kiểm tra + commit**

```powershell
cd frontend
npx tsc --noEmit ; npx eslint .
npx vitest run                     # 180 pass
npx playwright test                # 101 pass + 1 bỏ qua có chủ ý
cd ..
git add frontend docs
git commit -m "feat(web): phân tích lớp học trên trang thống kê (B7), e2e thảo luận và thông báo"
```

---

## Task 5: Kiểm tay (bạn làm)

Sau khi pull: `docker compose --profile web up -d --build`. API tự chạy migration khi khởi động. Cần 2 trình duyệt (hoặc 1 cửa sổ thường + 1 cửa sổ ẩn danh): một học viên, một giảng viên của cùng khóa.

- [ ] **Thảo luận:**
  - Học viên mở một bài, cuộn xuống cuối, gửi câu hỏi ở phần "Thảo luận".
  - Bên giảng viên, chuông hiện số **1** trong vài giây mà không cần tải lại trang.
  - Giảng viên bấm vào thông báo thì mở đúng bài và cuộn tới phần thảo luận. Giảng viên trả lời thì câu trả lời có nhãn "Giảng viên".
  - Bên học viên, chuông hiện số 1. Bấm vào thì số về 0.
- [ ] **Xóa:**
  - Học viên xóa câu hỏi của mình (có hộp xác nhận). Câu hỏi thành "Bình luận đã bị xóa.", câu trả lời của giảng viên vẫn còn.
  - Học viên khác không thấy nút Xóa ở bình luận của người khác.
- [ ] **Quiz mới:** giảng viên xuất bản một quiz. Học viên đã đăng ký nhận "Quiz mới: …", bấm vào thì mở trang làm quiz.
- [ ] **Job nền:** giảng viên tải một PDF lên bài học. Xử lý xong thì có thông báo "Tài liệu đã sẵn sàng · <tên bài>". Sinh câu hỏi bằng AI xong thì có "Câu hỏi AI đã soạn xong · <tên bài>", bấm vào mở ngân hàng câu hỏi.
- [ ] **Đã đọc hết:** nút "Đã đọc hết" đưa số về 0 và các dòng hết in đậm.
- [ ] **Mất kết nối:** tắt API (`docker compose stop api`) rồi bật lại. Trong khoảng 30 giây chuông tự kết nối lại, không phải tải lại trang.
- [ ] **Phân tích lớp:** khóa có ít nhất 3 bài nộp cho cùng một quiz thì trang Thống kê khóa học có câu hay sai, bài cần xem lại, học viên cần để ý. Khóa ít dữ liệu thì mỗi phần có câu giải thích, không có bảng trống.
- [ ] **Điện thoại (375px):** chuông nằm cạnh nút tài khoản; danh sách thông báo không tràn màn hình; phần thảo luận không cuộn ngang.
