import argparse
import asyncio
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.db import SessionLocal
from app.modules.auth.service import create_admin


def valid_email(email: str) -> str:
    """Cùng kiểu kiểm tra với trang đăng nhập (EmailStr): email như admin@lms.local sẽ không đăng nhập được."""
    try:
        return TypeAdapter(EmailStr).validate_python(email).lower()
    except ValidationError:
        sys.exit(
            f"Email không hợp lệ để đăng nhập: {email} (dùng đuôi tên miền thật, ví dụ admin@example.com)"
        )


async def main(email: str, password: str) -> None:
    async with SessionLocal() as db:
        user = await create_admin(db, email, password)
    print(f"Admin sẵn sàng: {user.email}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    a = p.parse_args()
    if len(a.password) < 8:
        sys.exit("Mật khẩu cần ít nhất 8 ký tự")
    asyncio.run(main(valid_email(a.email), a.password))
