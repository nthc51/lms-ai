import os

# Ép dùng DB test (không dùng setdefault: nếu shell đang export DATABASE_URL của DB dev,
# fixture _migrate sẽ DROP SCHEMA trên DB dev).
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL",
                                            "postgresql+asyncpg://lms:lms@localhost:5432/lms_test")
assert os.environ["DATABASE_URL"].rsplit("/", 1)[-1].endswith("_test"), "Test chỉ được chạy trên DB *_test"
os.environ["DB_NULL_POOL"] = "true"
os.environ["EMBED_PROVIDER"] = "fake"
os.environ["VISION_PROVIDER"] = "fake"
os.environ["JWT_SECRET"] = "test-secret"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.main import create_app  # noqa: E402


@pytest.fixture
async def client():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
