import argparse
import asyncio

from app.core.db import SessionLocal
from app.modules.auth.service import approve_teacher


async def main(email: str) -> None:
    async with SessionLocal() as db:
        user = await approve_teacher(db, email)
    print(f"Đã duyệt giảng viên: {user.email}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("email")
    asyncio.run(main(p.parse_args().email))
