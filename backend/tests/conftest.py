import os

# Ép dùng DB test (không dùng setdefault: nếu shell đang export DATABASE_URL của DB dev,
# fixture _migrate sẽ DROP SCHEMA trên DB dev).
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lms:lms@localhost:5432/lms_test"
)
assert os.environ["DATABASE_URL"].rsplit("/", 1)[-1].endswith("_test"), "Test chỉ được chạy trên DB *_test"
os.environ["DB_NULL_POOL"] = "true"
os.environ["EMBED_PROVIDER"] = "fake"
os.environ["VISION_PROVIDER"] = "fake"
os.environ["JWT_SECRET"] = "test-secret-0123456789abcdef-0123456789"

import httpx
import pytest

from app.core.storage import get_storage
from app.main import create_app
from app.modules.jobs.queue import get_queue
from tests.fakes import InMemoryStorage, RecordingQueue


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def queue():
    return RecordingQueue()


@pytest.fixture
async def client(storage, queue):
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_queue] = lambda: queue
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.models_registry  # noqa: F401
from app.core.db import Base, SessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    """Xóa sạch schema của lms_test rồi chạy migration thật (test luôn cả migration)."""
    # engine dùng chung giữa các test (mỗi test một event loop) bắt buộc phải là NullPool:
    # connection mở ở loop nào thì đóng ở loop đó, không bị giữ lại sang loop khác.
    assert isinstance(engine.sync_engine.pool, NullPool), "DB_NULL_POOL phải được set trước khi import app"

    async def reset() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await eng.dispose()

    asyncio.run(reset())
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
async def _clean_tables():
    yield
    tables = [t.name for t in Base.metadata.sorted_tables]
    if tables:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def db():
    async with SessionLocal() as session:
        yield session
