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
