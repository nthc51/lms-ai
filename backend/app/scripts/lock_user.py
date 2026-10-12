"""Khóa / mở khóa một tài khoản bằng lệnh (kể cả quản trị viên, việc trang quản trị không cho làm).

Dùng cho tài khoản admin cũ hoặc tạo nhầm, ví dụ admin@lms.local (email đuôi .local không đăng nhập được):

    docker compose exec api python -m app.scripts.lock_user admin@lms.local --reason "Tài khoản cũ"
    docker compose exec api python -m app.scripts.lock_user admin@lms.local --unlock

Khóa thì thu hồi mọi phiên đăng nhập. Không cho khóa quản trị viên cuối cùng còn hoạt động."""

import argparse
import asyncio

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.modules.auth.models import RefreshToken, Role, User


class LockError(Exception):
    pass


async def set_locked(db: AsyncSession, email: str, locked: bool, reason: str | None = None) -> User:
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise LockError(f"Không có tài khoản {email}")
    if locked and user.locked_at is None:
        if user.role == Role.admin:
            active_admins = await db.scalar(
                select(func.count(User.id)).where(User.role == Role.admin, User.locked_at.is_(None))
            )
            if active_admins <= 1:
                raise LockError("Không thể khóa quản trị viên cuối cùng còn hoạt động")
        user.locked_at = utcnow()
        user.lock_reason = reason
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    elif not locked and user.locked_at is not None:
        user.locked_at = None
        user.lock_reason = None
    await db.commit()
    return user


async def main(email: str, unlock: bool, reason: str | None) -> None:
    async with SessionLocal() as db:
        try:
            user = await set_locked(db, email, not unlock, reason)
        except LockError as e:
            raise SystemExit(str(e)) from None
    print(f"{'Đã mở khóa' if unlock else 'Đã khóa'}: {user.email} ({user.role.value})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("email")
    p.add_argument("--unlock", action="store_true")
    p.add_argument("--reason")
    a = p.parse_args()
    asyncio.run(main(a.email, a.unlock, a.reason))
