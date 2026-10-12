"""Lệnh vận hành: khóa tài khoản bằng lệnh, xử lý lại PDF hàng loạt."""

import pytest
from sqlalchemy import select

from app.modules.auth.models import RefreshToken, Role
from app.modules.jobs.models import Job
from app.modules.materials.models import SourceStatus
from app.scripts.lock_user import LockError, set_locked
from scripts.reprocess_pdfs import reprocess
from tests.factories import make_lesson, make_pdf_source, make_user
from tests.fakes import InMemoryStorage, RecordingQueue
from tests.helpers import API, make_student


async def test_lock_admin_by_command_revokes_sessions_but_keeps_last_admin(client, db):
    old = await make_user(db, Role.admin)
    main = await make_user(db, Role.admin)
    db.add(RefreshToken(user_id=old.id, token_hash="x" * 64, expires_at=old.created_at))
    await db.commit()

    user = await set_locked(db, old.email.upper(), True, "Tài khoản cũ")
    assert user.locked_at is not None and user.lock_reason == "Tài khoản cũ"
    token = await db.scalar(select(RefreshToken).where(RefreshToken.user_id == old.id))
    assert token.revoked_at is not None
    with pytest.raises(LockError, match="cuối cùng"):
        await set_locked(db, main.email, True)

    user = await set_locked(db, old.email, False)
    assert user.locked_at is None and user.lock_reason is None
    with pytest.raises(LockError, match="Không có tài khoản"):
        await set_locked(db, "khongco@x.com", True)


async def test_locked_student_cannot_log_in(client, db):
    await make_student(client, "sv@x.com")
    await set_locked(db, "sv@x.com", True)
    r = await client.post(f"{API}/auth/login", json={"email": "sv@x.com", "password": "password123"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"


async def test_reprocess_queues_ready_and_failed_pdfs_only(db):
    from app.core.db import SessionLocal

    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    storage = InMemoryStorage()
    ready = await make_pdf_source(db, storage, teacher, lesson, b"%PDF-1.7", status=SourceStatus.ready)
    failed = await make_pdf_source(db, storage, teacher, lesson, b"%PDF-1.7", status=SourceStatus.failed)
    busy = await make_pdf_source(db, storage, teacher, lesson, b"%PDF-1.7", status=SourceStatus.processing)
    queue = RecordingQueue()

    assert await reprocess(SessionLocal, queue) == (2, 1)
    assert sorted(ref for _, ref in queue.jobs) == sorted([ready.id, failed.id])
    for s in (ready, failed):
        await db.refresh(s)
        assert s.status == SourceStatus.pending and s.error_msg is None
    await db.refresh(busy)
    assert busy.status == SourceStatus.processing
    # Chạy lại khi job cũ còn chờ: không tạo job trùng
    assert await reprocess(SessionLocal, RecordingQueue()) == (0, 3)
    assert len(list(await db.scalars(select(Job)))) == 2
