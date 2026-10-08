import uuid
from datetime import timedelta

import anyio
from sqlalchemy import delete, func, select, update

from app import main
from app.core import ratelimit
from app.core.config import get_settings
from app.modules.auth.models import User
from app.modules.courses.models import Course, CourseStatus
from app.modules.enrollment.models import Enrollment
from app.modules.tutor import service
from app.modules.tutor.models import ChatMessage, ChatRole
from app.modules.tutor.text import REFUSAL_MESSAGE
from tests.factories import BINARY_SEARCH, seed_chunks
from tests.fakes import InMemoryStorage
from tests.helpers import API, make_published_course, make_student, make_teacher, parse_sse

TEST_TIMEOUT_S = 15  # mọi request chờ stream đều có giới hạn: hồi quy thì hỏng chứ không treo


def _tutor_counts(limiter) -> dict[str, int]:
    """Chỉ lượt đếm của Tutor (đăng ký tài khoản trong test cũng đi qua rate limiter theo IP)."""
    return {k: v for k, v in limiter.counts.items() if k.startswith("tutor:")}


async def _ready_session(client, db):
    _, gv = await make_teacher(client)
    course, _, lesson = await make_published_course(client, gv)
    await seed_chunks(db, uuid.UUID(lesson["id"]), [BINARY_SEARCH])
    _, sv = await make_student(client)
    assert (await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)).status_code == 201
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    session = (await client.post(f"{API}/tutor/sessions", json=body, headers=sv)).json()
    return gv, sv, course, lesson, session


async def _ask(client, headers, session_id, content="Tìm kiếm nhị phân là gì?", extra_headers=None):
    with anyio.fail_after(TEST_TIMEOUT_S):
        return await client.post(
            f"{API}/tutor/sessions/{session_id}/messages",
            json={"content": content},
            headers={**headers, **(extra_headers or {})},
        )


async def _messages(db, session_id) -> list[ChatMessage]:
    db.expire_all()
    rows = await db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == uuid.UUID(session_id))
        .order_by(ChatMessage.created_at, ChatMessage.role, ChatMessage.id)
    )
    return list(rows)


async def test_ask_streams_sse_and_persists_both_messages(client, db):
    _, sv, _, _, session = await _ready_session(client, db)
    r = await _ask(client, sv, session["id"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
    assert r.headers["x-request-id"]
    events = parse_sse(r.text)
    assert events[0][0] == "sources" and events[-1][0] == "done"
    page = (await client.get(f"{API}/tutor/sessions/{session['id']}/messages", headers=sv)).json()
    question, answer = page["items"]
    assert (question["role"], question["content"]) == ("user", "Tìm kiếm nhị phân là gì?")
    assert answer["role"] == "assistant" and answer["id"] == events[-1][1]["message_id"]
    assert [c["n"] for c in answer["citations"]] == [1] and answer["truncated"] is False


async def test_follow_up_question_uses_history(client, db, llm):
    _, sv, _, _, session = await _ready_session(client, db)
    await _ask(client, sv, session["id"])
    await _ask(client, sv, session["id"], "Tìm kiếm nhị phân có cần mảng sắp xếp không?")
    assert [c.op for c in llm.calls] == ["tutor_answer", "tutor_rewrite", "tutor_answer"]
    # câu hỏi đang hỏi không nằm trong lịch sử; lịch sử là câu hỏi + câu trả lời trước, cũ → mới
    rewrite_prompt = llm.calls[1].prompt
    assert "Tìm kiếm nhị phân là gì?" in rewrite_prompt
    assert rewrite_prompt.index("Tìm kiếm nhị phân là gì?") < rewrite_prompt.index("câu trả lời mô phỏng")


async def test_refused_answer_through_api(client, db):
    _, sv, _, _, session = await _ready_session(client, db)
    events = parse_sse((await _ask(client, sv, session["id"], "Thời tiết Hà Nội hôm nay")).text)
    assert events[1] == ("token", {"text": REFUSAL_MESSAGE}) and events[-1][1]["refused"] is True


async def test_rate_limit_returns_429_with_retry_after(client, db, limiter, monkeypatch):
    monkeypatch.setattr(get_settings(), "tutor_rate_limit_per_hour", 2)
    gv, sv, course, lesson, session = await _ready_session(client, db)
    assert (await _ask(client, sv, session["id"])).status_code == 200
    assert (await _ask(client, sv, session["id"])).status_code == 200
    r = await _ask(client, sv, session["id"], extra_headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"
    # frontend đọc được Retry-After qua CORS
    assert "retry-after" in r.headers["access-control-expose-headers"].lower()
    err = r.json()["error"]
    assert err["code"] == "RATE_LIMITED" and err["details"] == {"retry_after": 3600} and err["request_id"]
    msgs = (await client.get(f"{API}/tutor/sessions/{session['id']}/messages", headers=sv)).json()
    assert msgs["total"] == 4  # câu bị chặn không được lưu
    student = await db.scalar(select(User).where(User.email == "sv@x.com"))
    assert _tutor_counts(limiter) == {
        f"tutor:{student.id}": 3
    }  # RedisRateLimiter thêm tiền tố → rl:tutor:<id>
    # giảng viên không bị giới hạn (và không bị đếm)
    body = {"course_id": course["id"], "lesson_id": lesson["id"]}
    teacher_session = (await client.post(f"{API}/tutor/sessions", json=body, headers=gv)).json()
    for _ in range(3):
        assert (await _ask(client, gv, teacher_session["id"])).status_code == 200
    assert list(_tutor_counts(limiter)) == [f"tutor:{student.id}"]


async def test_other_users_session_and_blank_question(client, db, limiter):
    _, sv, _, _, session = await _ready_session(client, db)
    _, other = await make_student(client, "sv2@x.com")
    assert (await _ask(client, other, session["id"])).status_code == 404
    r = await _ask(client, sv, session["id"], "   ")
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")
    assert _tutor_counts(limiter) == {}  # bị từ chối trước rate limit: không tốn lượt
    assert await _messages(db, session["id"]) == []


async def test_unenrolled_after_session_creation_cannot_ask(client, db, limiter):
    _, sv, course, _, session = await _ready_session(client, db)
    await db.execute(delete(Enrollment).where(Enrollment.course_id == uuid.UUID(course["id"])))
    await db.commit()
    r = await _ask(client, sv, session["id"])
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")  # như khi tạo phiên
    assert await _messages(db, session["id"]) == [] and _tutor_counts(limiter) == {}


async def test_unpublished_after_session_creation_cannot_ask(client, db):
    _, sv, course, _, session = await _ready_session(client, db)
    await db.execute(
        update(Course).where(Course.id == uuid.UUID(course["id"])).values(status=CourseStatus.draft)
    )
    await db.commit()
    r = await _ask(client, sv, session["id"])
    create = await client.post(
        f"{API}/tutor/sessions", json={"course_id": course["id"], "lesson_id": None}, headers=sv
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == create.json()["error"]["code"]
    assert create.status_code == 404
    assert await _messages(db, session["id"]) == []


async def test_provider_error_sends_error_event_and_keeps_question(client, db, llm):
    llm.replies.append(ValueError("hết quota"))  # lỗi không retry khi mở stream
    _, sv, _, _, session = await _ready_session(client, db)
    r = await _ask(client, sv, session["id"])
    assert r.status_code == 200
    events = parse_sse(r.text)
    assert [e for e, _ in events] == ["sources", "error"]
    assert events[-1][1]["code"] == "AI_UNAVAILABLE"
    question, answer = await _messages(db, session["id"])
    assert (question.role, question.content) == (ChatRole.user, "Tìm kiếm nhị phân là gì?")
    assert answer.role == ChatRole.assistant and answer.truncated is True and answer.content == ""


async def test_load_history_last_four_non_empty_oldest_first(client, db):
    _, _, _, _, session = await _ready_session(client, db)
    sid = uuid.UUID(session["id"])
    now = await db.scalar(func.now())
    later = now + timedelta(seconds=1)
    # cùng created_at: user đứng trước assistant dù id lớn hơn (giống list_messages)
    rows = [
        (ChatRole.user, "q1", now, 2**100),
        (ChatRole.assistant, "a1", now, 1),
        (ChatRole.user, "q2", later, 2**101),
        (ChatRole.assistant, "", later, 2),  # tin rỗng do lỗi: bỏ qua
        (ChatRole.assistant, "a2", later, 3),
    ]
    for role, content, at, i in rows:
        db.add(ChatMessage(session_id=sid, role=role, content=content, created_at=at, id=uuid.UUID(int=i)))
    await db.commit()
    db.add(
        ChatMessage(session_id=sid, role=ChatRole.user, content="q0", created_at=now - timedelta(seconds=1))
    )
    await db.commit()
    assert await service.load_history(db, sid) == [  # 4 tin gần nhất, q0 bị cắt
        (ChatRole.user, "q1"),
        (ChatRole.assistant, "a1"),
        (ChatRole.user, "q2"),
        (ChatRole.assistant, "a2"),
    ]
    assert await service.load_history(db, sid, limit=2) == [(ChatRole.user, "q2"), (ChatRole.assistant, "a2")]


async def test_feedback_on_own_assistant_message(client, db):
    _, sv, _, _, session = await _ready_session(client, db)
    done = parse_sse((await _ask(client, sv, session["id"])).text)[-1][1]
    url = f"{API}/tutor/messages/{done['message_id']}/feedback"
    assert (await client.post(url, json={"value": 1}, headers=sv)).json()["feedback"] == 1
    assert (await client.post(url, json={"value": -1}, headers=sv)).json()["feedback"] == -1
    assert (await client.post(url, json={"value": None}, headers=sv)).json()["feedback"] is None
    assert (await client.post(url, json={"value": 2}, headers=sv)).status_code == 422
    _, other = await make_student(client, "sv2@x.com")
    assert (await client.post(url, json={"value": 1}, headers=other)).status_code == 404
    question = await db.scalar(select(ChatMessage).where(ChatMessage.role == ChatRole.user))
    r = await client.post(f"{API}/tutor/messages/{question.id}/feedback", json={"value": 1}, headers=sv)
    assert r.status_code == 404


async def test_lifespan_closes_rate_limiter(monkeypatch):
    closed = []

    async def fake_close() -> None:
        closed.append(True)

    monkeypatch.setattr(main, "get_storage", InMemoryStorage)
    monkeypatch.setattr(main, "close_rate_limiter", fake_close)
    app = main.create_app()
    with anyio.fail_after(TEST_TIMEOUT_S):
        async with main.lifespan(app):
            assert closed == []
    assert closed == [True]


async def test_close_rate_limiter_closes_cached_client_only(monkeypatch):
    closed = []

    async def fake_aclose(self) -> None:
        closed.append(self)

    monkeypatch.setattr(ratelimit.RedisRateLimiter, "aclose", fake_aclose)
    ratelimit.get_rate_limiter.cache_clear()
    await ratelimit.close_rate_limiter()  # chưa tạo client: không tạo mới chỉ để đóng
    assert closed == [] and ratelimit.get_rate_limiter.cache_info().currsize == 0
    limiter = ratelimit.get_rate_limiter()
    await ratelimit.close_rate_limiter()
    assert closed == [limiter] and ratelimit.get_rate_limiter.cache_info().currsize == 0


async def test_close_rate_limiter_swallows_errors(monkeypatch):
    async def broken_aclose(self) -> None:
        raise ConnectionError("redis đã tắt")

    monkeypatch.setattr(ratelimit.RedisRateLimiter, "aclose", broken_aclose)
    ratelimit.get_rate_limiter.cache_clear()
    ratelimit.get_rate_limiter()
    await ratelimit.close_rate_limiter()  # không ném lỗi lúc tắt app
    assert ratelimit.get_rate_limiter.cache_info().currsize == 0
