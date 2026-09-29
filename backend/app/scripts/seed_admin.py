import argparse
import asyncio

from app.core.db import SessionLocal
from app.modules.auth.service import create_admin


async def main(email: str, password: str) -> None:
    async with SessionLocal() as db:
        user = await create_admin(db, email, password)
    print(f"Admin sẵn sàng: {user.email}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    a = p.parse_args()
    asyncio.run(main(a.email, a.password))
