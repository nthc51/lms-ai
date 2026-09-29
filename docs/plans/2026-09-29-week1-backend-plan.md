# Tuần 1 — Backend nền tảng (A1–A4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng backend FastAPI chạy được với 4 phần: auth có phân quyền, quản lý khóa học, đăng ký học với tiến độ, upload file và pipeline xử lý PDF (từ PDF ra chunk kèm embedding, lưu trong Postgres). Toàn bộ có test.

**Architecture:** Monorepo `lms-ai/`, backend chia theo module (`router / schemas / service / models`). Postgres 16 có pgvector và unaccent, Redis dùng cho arq, MinIO lưu file. Mọi phần phụ thuộc bên ngoài (storage, hàng đợi job, embedder, vision) đều đi qua interface, nên khi test thay được bằng bản giả. Test integration chạy trên Postgres thật.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2 (async) + asyncpg, Alembic, pydantic-settings, pwdlib (argon2), PyJWT, minio, filetype, arq, PyMuPDF + pymupdf4llm, pgvector, google-genai, pytest + pytest-asyncio + httpx.

**Spec:** `2026-09-29-lms-ai-design.md` (mục 3, 4, 5.0, 5.1, 6, 7, 8).

**Ngoài phạm vi của plan này:** frontend (plan riêng), AI Tutor (A5, tuần 2), video/Whisper (C1). Video trong tuần này mới chỉ gắn vào bài học để phát, chưa transcribe.

**Ghi chú bổ sung so với spec** (cập nhật vào spec ở Task 23):

- **Mã lỗi thêm mới:** `EMAIL_TAKEN`, `INVALID_TOKEN`, `TOKEN_REUSED`, `NOT_AUTHENTICATED`, `FORBIDDEN`, `COURSE_EMPTY`, `INVALID_REORDER`, `UPLOAD_MISSING`, `INVALID_ASSET`, `INVALID_STATE`.
- **Endpoint thêm mới:** `GET /teacher/courses`, `GET /lessons/{id}` (nội dung bài học), `GET /lessons/{id}/video`, `GET /lessons/{id}/sources`.
- **`GET /jobs/{id}`:** chỉ cần đăng nhập là gọi được. ID là UUID không đoán được, và endpoint chỉ trả trạng thái job.
- **Upload qua key tạm (Task 14):** URL presign chỉ cho PUT vào `staging/<storage_key>`. `POST /uploads/{id}/complete` khóa dòng asset, copy phía server sang `storage_key`, kiểm tra kích thước và magic bytes trên bản chính thức, rồi xóa key tạm; hỏng thì xóa object và dòng asset. Client không bao giờ có URL ghi vào key chính thức. Học viên không được presign `pdf`/`video` (`403 FORBIDDEN`); `presign_get` luôn ký kèm `Content-Type` của asset.

---

## Cấu trúc file

```
lms-ai/
├── .gitignore
├── docker-compose.yml
├── infra/db/init.sql                      # tạo DB lms_test
└── backend/
    ├── pyproject.toml, uv.lock, .env.example, Dockerfile, .dockerignore
    ├── alembic.ini, alembic/env.py, alembic/script.py.mako, alembic/versions/
    ├── app/
    │   ├── main.py                        # create_app(), gắn middleware, error handler, router
    │   ├── models_registry.py             # import mọi models để Alembic nhìn thấy
    │   ├── core/
    │   │   ├── config.py                  # Settings
    │   │   ├── db.py                      # Base, mixin, engine, SessionLocal, get_db
    │   │   ├── time.py                    # utcnow()
    │   │   ├── errors.py                  # AppError + handler
    │   │   ├── middleware.py              # RequestIdMiddleware
    │   │   ├── security.py                # hash mật khẩu, JWT, refresh token
    │   │   ├── deps.py                    # get_current_user, require_role, require_staff...
    │   │   └── storage.py                 # Storage protocol + MinioStorage + get_storage
    │   ├── modules/
    │   │   ├── auth/{models,schemas,service,router}.py
    │   │   ├── courses/{models,schemas,service,router}.py
    │   │   ├── enrollment/{models,schemas,service,router}.py
    │   │   ├── materials/{models,assets,sources,schemas,router}.py
    │   │   └── jobs/{models,service,queue,router}.py
    │   ├── ai/{embedder,vision}.py
    │   ├── ingestion/{chunker,extract,pipeline}.py
    │   ├── worker/{tasks,settings}.py
    │   └── scripts/{seed_admin,approve_teacher}.py
    ├── scripts/smoke_week1.py
    └── tests/
        ├── conftest.py, helpers.py, factories.py, fakes.py, pdfs.py
        └── test_*.py
```

Mỗi module đi theo nguyên tắc: `models` chỉ định nghĩa bảng, `service` chứa nghiệp vụ và không biết gì về HTTP, còn `router` chỉ làm nhiệm vụ nối HTTP vào service.

---

### Task 0: Khởi tạo repo và hạ tầng Docker

**Files:**
- Create: `lms-ai/.gitignore`, `lms-ai/docker-compose.yml`, `lms-ai/infra/db/init.sql`

- [x] **Step 1: Tạo thư mục và git**

```bash
mkdir lms-ai && cd lms-ai && git init
mkdir -p infra/db backend
```

- [x] **Step 2: `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.ruff_cache/
node_modules/
.next/
```

- [x] **Step 3: `infra/db/init.sql`**

```sql
CREATE DATABASE lms_test;
```

- [x] **Step 4: `docker-compose.yml`** (service `api` và `worker` sẽ thêm ở Task 22)

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: lms
      POSTGRES_PASSWORD: lms
      POSTGRES_DB: lms
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./infra/db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lms"]
      interval: 5s
      retries: 10
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio12345
    ports: ["9000:9000", "9001:9001"]
    volumes:
      - miniodata:/data
volumes:
  pgdata:
  miniodata:
```

- [x] **Step 5: Chạy và kiểm tra**

Run: `docker compose up -d db redis minio` rồi `docker compose exec db psql -U lms -d lms_test -c "SELECT 1"`
Expected: in ra một bảng có giá trị `1`. Nếu báo `database "lms_test" does not exist`, nghĩa là volume đã được tạo từ trước khi có init.sql. Chạy `docker compose down -v` rồi `up` lại.

- [x] **Step 6: Lưu spec vào repo**: tải file `2026-09-29-lms-ai-design.md` từ chat về, đặt vào `lms-ai/docs/specs/`.

- [x] **Step 7: Commit**

```bash
git add . && git commit -m "chore: init repo with postgres/pgvector, redis, minio"
```

---

### Task 1: Khung backend và endpoint `/health`

**Files:**
- Create: `backend/pyproject.toml`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/app/core/db.py`, `backend/app/core/time.py`, `backend/app/main.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_health.py`

- [x] **Step 1: `backend/pyproject.toml`**

```toml
[project]
name = "lms-ai-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy[asyncio]>=2.0.30",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "pydantic-settings>=2.3",
  "email-validator>=2.1",
  "pwdlib[argon2]>=0.2",
  "pyjwt>=2.8",
  "minio>=7.2",
  "filetype>=1.2",
  "arq>=0.26",
  "pymupdf>=1.24",
  "pymupdf4llm>=0.0.17",
  "pgvector>=0.3",
  "python-slugify>=8.0",
  "google-genai>=1.0",
  "httpx>=0.27",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "ruff>=0.5"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 110
```

Run: `cd backend && uv sync`
Expected: tạo ra `.venv/` và `uv.lock`.

- [x] **Step 2: `backend/.env.example`** (copy thành `.env` để dev)

```
DATABASE_URL=postgresql+asyncpg://lms:lms@localhost:5432/lms
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=change-me
MINIO_ENDPOINT=localhost:9000
MINIO_PUBLIC_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=minio12345
MINIO_BUCKET=lms
EMBED_PROVIDER=fake
EMBED_DIM=768
VISION_PROVIDER=fake
# Khi dùng Gemini thật: EMBED_PROVIDER=gemini, EMBED_MODEL=gemini-embedding-001,
# VISION_PROVIDER=gemini, GEMINI_API_KEY=...  (kiểm tra lại tên model hiện hành trên trang Google AI)
GEMINI_API_KEY=
```

- [x] **Step 3: `app/core/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://lms:lms@localhost:5432/lms"
    db_null_pool: bool = False
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-me"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False

    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio12345"
    minio_bucket: str = "lms"
    minio_secure: bool = False

    embed_provider: str = "fake"  # fake | gemini
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    vision_provider: str = "fake"  # fake | gemini
    vision_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [x] **Step 4: `app/core/time.py`**

```python
from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
```

- [x] **Step 5: `app/core/db.py`**

```python
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _make_engine() -> AsyncEngine:
    s = get_settings()
    if s.db_null_pool:  # test: mỗi test có event loop riêng, không được giữ connection lại
        return create_async_engine(s.database_url, poolclass=NullPool)
    return create_async_engine(s.database_url, pool_size=5, max_overflow=5)


engine = _make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

- [x] **Step 6: Viết test hỏng trước — `tests/conftest.py` và `tests/test_health.py`**

`tests/__init__.py` để trống. `tests/conftest.py`:

```python
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
```

`tests/test_health.py`:

```python
async def test_health_ok(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [x] **Step 7: Chạy test để thấy nó hỏng**

Run: `uv run pytest tests/test_health.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.main'`

- [x] **Step 8: `app/main.py`** (`app/__init__.py` và `app/core/__init__.py` để trống)

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="LMS-AI API")

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    # routers
    return app


app = create_app()
```

- [x] **Step 9: Chạy lại test**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS

- [x] **Step 10: Commit**

```bash
git add backend && git commit -m "feat(backend): project skeleton with settings, db engine, health endpoint"
```

---

### Task 2: Alembic, migration đầu tiên và `immutable_unaccent`

**Files:**
- Create: `backend/alembic.ini` (do lệnh sinh ra), `backend/alembic/env.py`, `backend/alembic/versions/0001_extensions.py`, `backend/app/models_registry.py`
- Modify: `backend/alembic/script.py.mako`, `backend/tests/conftest.py`
- Test: `backend/tests/test_unaccent.py`

- [x] **Step 1: Khởi tạo alembic bằng template async**

Run: `uv run alembic init -t async alembic`
Expected: tạo ra `alembic.ini` và thư mục `alembic/`

- [x] **Step 2: `app/models_registry.py`**

```python
"""Import mọi module models để Base.metadata có đủ bảng (dùng cho Alembic và test)."""
```

- [x] **Step 3: Thay toàn bộ nội dung `alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

import app.models_registry  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
```

- [x] **Step 4: Sửa `alembic/script.py.mako`**: ngay dưới dòng `import sqlalchemy as sa`, thêm:

```python
import pgvector.sqlalchemy  # noqa: F401
```

(Khi autogenerate sinh cột vector, migration sẽ có dạng `pgvector.sqlalchemy.vector.VECTOR(dim=768)`, nên cần sẵn import này.)

- [x] **Step 5: `alembic/versions/0001_extensions.py`**

```python
"""extensions and immutable_unaccent

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_unaccent(text)
        RETURNS text AS $$
          SELECT public.unaccent('public.unaccent'::regdictionary, $1);
        $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
```

- [x] **Step 6: Viết test — `tests/test_unaccent.py`**

```python
from sqlalchemy import text


async def test_unaccent_removes_vietnamese_marks(db):
    assert await db.scalar(text("SELECT immutable_unaccent('Tìm kiếm nhị phân')")) == "Tim kiem nhi phan"


async def test_unaccent_handles_d_stroke(db):
    assert await db.scalar(text("SELECT immutable_unaccent('Đồ thị đường đi')")) == "Do thi duong di"


async def test_unaccent_function_is_immutable(db):
    vol = await db.scalar(text("SELECT provolatile FROM pg_proc WHERE proname = 'immutable_unaccent'"))
    assert vol == "i"
```

- [x] **Step 7: Thêm các fixture migrate, clean và db vào cuối `tests/conftest.py`**

```python
import asyncio  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.models_registry  # noqa: E402,F401
from app.core.db import Base, SessionLocal, engine  # noqa: E402


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
```

- [x] **Step 8: Chạy test**

Run: `uv run pytest -v`
Expected: PASS cả 4 test (health + 3 test unaccent).
Nếu `test_unaccent_handles_d_stroke` hỏng: kiểm tra `SELECT unaccent('Đđ')` trong psql. Bộ rules mặc định của image postgres có map `Đ→D`, `đ→d`. Nếu không có, **dừng lại và báo**, đừng tự sửa rules.

- [x] **Step 9: Tạo schema cho DB dev**

Run: `cp .env.example .env && uv run alembic upgrade head`
Expected: `Running upgrade  -> 0001`

- [x] **Step 10: Commit**

```bash
git add . && git commit -m "feat(db): alembic async setup, extensions, immutable_unaccent + tests"
```

---

### Task 3: Định dạng lỗi thống nhất và request_id

**Files:**
- Create: `backend/app/core/errors.py`, `backend/app/core/middleware.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_errors.py`

- [x] **Step 1: Viết test hỏng trước — `tests/test_errors.py`**

```python
import httpx
from pydantic import BaseModel

from app.core.errors import AppError
from app.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_app_error_has_unified_format_and_request_id():
    app = create_app()

    @app.get("/boom")
    async def boom():
        raise AppError("SOMETHING_WRONG", "Có lỗi", 409, {"x": 1})

    async with _client(app) as c:
        r = await c.get("/boom")
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "SOMETHING_WRONG"
    assert err["message"] == "Có lỗi"
    assert err["details"] == {"x": 1}
    assert err["request_id"] == r.headers["x-request-id"]


async def test_validation_error_is_normalized():
    app = create_app()

    class Body(BaseModel):
        name: str

    @app.post("/echo")
    async def echo(body: Body):
        return body

    async with _client(app) as c:
        r = await c.post("/echo", json={})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["errors"][0]["loc"] == ["body", "name"]


async def test_app_error_can_set_headers():
    app = create_app()

    @app.get("/limited")
    async def limited():
        raise AppError("RATE_LIMITED", "Chậm lại", 429, headers={"Retry-After": "30"})

    async with _client(app) as c:
        r = await c.get("/limited")
    assert r.headers["retry-after"] == "30"
```

- [x] **Step 2: Chạy test**

Run: `uv run pytest tests/test_errors.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.core.errors'`

- [x] **Step 3: `app/core/errors.py`**

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400,
                 details: dict | None = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}
        self.headers = headers


def not_found(what: str = "Tài nguyên") -> AppError:
    return AppError("NOT_FOUND", f"{what} không tồn tại", 404)


def forbidden(message: str = "Bạn không có quyền thực hiện thao tác này") -> AppError:
    return AppError("FORBIDDEN", message, 403)


def _body(request: Request, code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details,
                      "request_id": getattr(request.state, "request_id", None)}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(request, exc.code, exc.message, exc.details),
                            status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(_body(request, "VALIDATION_ERROR", "Dữ liệu không hợp lệ", {"errors": errors}),
                            status_code=422)
```

- [x] **Step 4: `app/core/middleware.py`**: middleware ASGI thuần. Không dùng `BaseHTTPMiddleware`, vì loại đó can thiệp vào luồng streaming mà ta sẽ cần cho SSE.

```python
import uuid


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_with_header)
```

- [x] **Step 5: Thay `app/main.py`**

```python
from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.core.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="LMS-AI API")
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    # routers
    return app


app = create_app()
```

- [x] **Step 6: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: PASS hết

- [x] **Step 7: Commit**

```bash
git add . && git commit -m "feat(core): unified error format and request id middleware"
```

---

### Task 4: Model User, RefreshToken và các hàm bảo mật

**Files:**
- Create: `backend/app/modules/__init__.py`, `backend/app/modules/auth/__init__.py`, `backend/app/modules/auth/models.py`, `backend/app/core/security.py`
- Modify: `backend/app/models_registry.py`
- Create (sinh bằng lệnh): `backend/alembic/versions/<rev>_users.py`
- Test: `backend/tests/test_security.py`

- [x] **Step 1: Viết test hỏng trước — `tests/test_security.py`**

```python
import uuid

import pytest

from app.core.errors import AppError
from app.core.security import (
    create_access_token, decode_access_token, hash_password, hash_refresh_token,
    new_refresh_token, verify_password,
)


def test_hash_and_verify_password():
    h = hash_password("password123")
    assert h != "password123"
    assert verify_password("password123", h)
    assert not verify_password("wrong-pass", h)


def test_access_token_roundtrip():
    uid = uuid.uuid4()
    payload = decode_access_token(create_access_token(uid, "teacher"))
    assert payload["sub"] == str(uid)
    assert payload["role"] == "teacher"


def test_expired_access_token_raises_token_expired():
    token = create_access_token(uuid.uuid4(), "student", expires_minutes=-1)
    with pytest.raises(AppError) as e:
        decode_access_token(token)
    assert e.value.code == "TOKEN_EXPIRED" and e.value.status == 401


def test_garbage_token_raises_invalid_token():
    with pytest.raises(AppError) as e:
        decode_access_token("not-a-jwt")
    assert e.value.code == "INVALID_TOKEN"


def test_refresh_token_is_random_and_hashable():
    raw1, h1 = new_refresh_token()
    raw2, _ = new_refresh_token()
    assert raw1 != raw2 and len(raw1) >= 40
    assert hash_refresh_token(raw1) == h1 and len(h1) == 64
```

- [x] **Step 2: Chạy test**

Run: `uv run pytest tests/test_security.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.core.security'`

- [x] **Step 3: `app/core/security.py`**

```python
import hashlib
import secrets
import uuid
from datetime import timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utcnow

_pwd = PasswordHash.recommended()  # argon2


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd.verify(password, hashed)


def create_access_token(user_id: uuid.UUID, role: str, expires_minutes: int | None = None) -> str:
    s = get_settings()
    minutes = s.access_token_minutes if expires_minutes is None else expires_minutes
    payload = {"sub": str(user_id), "role": role, "type": "access",
               "exp": utcnow() + timedelta(minutes=minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AppError("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn", 401) from None
    except jwt.InvalidTokenError:
        raise AppError("INVALID_TOKEN", "Token không hợp lệ", 401) from None
    if payload.get("type") != "access":
        raise AppError("INVALID_TOKEN", "Token không hợp lệ", 401)
    return payload


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)
```

- [x] **Step 4: Chạy test**

Run: `uv run pytest tests/test_security.py -v`
Expected: PASS

- [x] **Step 5: `app/modules/auth/models.py`** (`app/modules/__init__.py` và `app/modules/auth/__init__.py` để trống)

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class TeacherStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    # Email luôn được lưu dạng chữ thường, nên UNIQUE thường cũng chặn được trùng hoa/thường,
    # kể cả khi có ai insert thẳng vào DB bằng script. (Dùng CHECK thay cho index LOWER(email) vì
    # Alembic autogenerate so sánh index biểu thức không ổn định, dễ sinh migration thừa.)
    __table_args__ = (CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    avatar_key: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="user_role"))
    teacher_status: Mapped[TeacherStatus | None] = mapped_column(SAEnum(TeacherStatus, name="teacher_status"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(IdMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [x] **Step 6: Đăng ký vào `app/models_registry.py`**: thêm vào cuối file:

```python
from app.modules.auth import models as auth_models  # noqa: F401
```

- [x] **Step 7: Sinh migration**

Run: `uv run alembic revision --autogenerate -m "users"` rồi `uv run alembic upgrade head`
Expected: file mới có `op.create_table('users', ...)` (bên trong có `sa.CheckConstraint('email = lower(email)', name='ck_users_email_lowercase')`) và `op.create_table('refresh_tokens', ...)`, với `down_revision = '0001'`. Mở file ra kiểm tra lại rồi mới upgrade.

- [x] **Step 8: Chạy toàn bộ test** (fixture `_migrate` sẽ chạy migration mới)

Run: `uv run pytest -v`
Expected: PASS

- [x] **Step 9: Commit**

```bash
git add . && git commit -m "feat(auth): user and refresh token models, password hashing, jwt helpers"
```

---

### Task 5: Đăng ký, đăng nhập và `/me`

**Files:**
- Create: `backend/app/core/deps.py`, `backend/app/modules/auth/schemas.py`, `backend/app/modules/auth/service.py`, `backend/app/modules/auth/router.py`, `backend/tests/helpers.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

- [x] **Step 1: `tests/helpers.py`**

```python
import uuid

from app.core.db import SessionLocal
from app.modules.auth.models import TeacherStatus, User

API = "/api/v1"


async def register_user(client, email, password="password123", role="student", full_name="Người dùng"):
    r = await client.post(f"{API}/auth/register",
                          json={"email": email, "password": password, "role": role, "full_name": full_name})
    assert r.status_code == 201, r.text
    return r.json()


async def login(client, email, password="password123") -> dict[str, str]:
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def approve_teacher_in_db(user_id: str) -> None:
    async with SessionLocal() as db:
        user = await db.get(User, uuid.UUID(user_id))
        user.teacher_status = TeacherStatus.approved
        await db.commit()


async def make_student(client, email="sv@x.com") -> tuple[str, dict]:
    user = await register_user(client, email, role="student")
    return user["id"], await login(client, email)


async def make_teacher(client, email="gv@x.com", approved=True) -> tuple[str, dict]:
    user = await register_user(client, email, role="teacher", full_name="Giảng viên")
    if approved:
        await approve_teacher_in_db(user["id"])
    return user["id"], await login(client, email)
```

- [x] **Step 2: Viết test hỏng trước — `tests/test_auth.py`**

```python
from tests.helpers import API, login, register_user


async def test_register_student(client):
    body = await register_user(client, "a@x.com")
    assert body["role"] == "student"
    assert body["teacher_status"] is None
    assert "password_hash" not in body


async def test_register_teacher_is_pending(client):
    body = await register_user(client, "gv@x.com", role="teacher")
    assert body["teacher_status"] == "pending"


async def test_register_cannot_create_admin(client):
    r = await client.post(f"{API}/auth/register",
                          json={"email": "ad@x.com", "password": "password123", "role": "admin", "full_name": "A"})
    assert r.status_code == 422


async def test_register_duplicate_email_is_case_insensitive(client):
    await register_user(client, "A@x.com")
    r = await client.post(f"{API}/auth/register",
                          json={"email": "a@x.com", "password": "password123", "full_name": "B"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_db_rejects_uppercase_email_even_outside_the_api(db):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.modules.auth.models import Role, User

    db.add(User(email="Admin@lms.local", password_hash="x", full_name="A", role=Role.admin))
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_register_short_password_is_422(client):
    r = await client.post(f"{API}/auth/register", json={"email": "b@x.com", "password": "123", "full_name": "B"})
    assert r.status_code == 422


async def test_login_returns_access_token_and_sets_refresh_cookie(client):
    await register_user(client, "c@x.com")
    r = await client.post(f"{API}/auth/login", json={"email": "c@x.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    set_cookie = r.headers["set-cookie"]
    assert "refresh_token=" in set_cookie and "HttpOnly" in set_cookie and "Path=/api/v1/auth" in set_cookie


async def test_login_wrong_password(client):
    await register_user(client, "d@x.com")
    r = await client.post(f"{API}/auth/login", json={"email": "d@x.com", "password": "wrongpass1"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_requires_token(client):
    r = await client.get(f"{API}/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_me_returns_current_user(client):
    await register_user(client, "e@x.com", full_name="Chiến")
    headers = await login(client, "e@x.com")
    r = await client.get(f"{API}/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "e@x.com" and r.json()["full_name"] == "Chiến"
```

- [x] **Step 3: Chạy test**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL (404 do chưa có route, hoặc lỗi import `app.modules.auth.models` trong helpers chạy được nhưng route thì chưa có)

- [x] **Step 4: `app/modules/auth/schemas.py`**

```python
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.models import Role, TeacherStatus


def _lower(v: str) -> str:
    return v.strip().lower()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal["student", "teacher"] = "student"

    normalize_email = field_validator("email")(_lower)  # tên không được bắt đầu bằng "_" (pydantic coi là private)


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    normalize_email = field_validator("email")(_lower)  # tên không được bắt đầu bằng "_" (pydantic coi là private)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    teacher_status: TeacherStatus | None
```

- [x] **Step 5: `app/modules/auth/service.py`**

```python
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, new_refresh_token, verify_password
from app.core.time import utcnow
from app.modules.auth.models import RefreshToken, Role, TeacherStatus, User
from app.modules.auth.schemas import LoginIn, RegisterIn


async def register(db: AsyncSession, data: RegisterIn) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise AppError("EMAIL_TAKEN", "Email đã được sử dụng", 409)
    role = Role(data.role)
    user = User(email=email, password_hash=hash_password(data.password), full_name=data.full_name,
                role=role, teacher_status=TeacherStatus.pending if role == Role.teacher else None)
    db.add(user)
    await db.commit()
    return user


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    """Trả về (access_token, refresh_token_raw). Commit luôn cả các thay đổi đang chờ trong session."""
    raw, hashed = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hashed,
                        expires_at=utcnow() + timedelta(days=get_settings().refresh_token_days)))
    await db.commit()
    return create_access_token(user.id, user.role.value), raw


async def login(db: AsyncSession, data: LoginIn) -> tuple[str, str]:
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng", 401)
    if user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    return await issue_tokens(db, user)
```

- [x] **Step 6: `app/core/deps.py`**

```python
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.modules.auth.models import User

_bearer = HTTPBearer(auto_error=False)


async def _user_from_token(token: str, db: AsyncSession) -> User:
    payload = decode_access_token(token)
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise AppError("INVALID_TOKEN", "Token không hợp lệ", 401)
    if user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    return user


async def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                           db: AsyncSession = Depends(get_db)) -> User:
    if cred is None:
        raise AppError("NOT_AUTHENTICATED", "Bạn cần đăng nhập", 401)
    return await _user_from_token(cred.credentials, db)


async def get_optional_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                            db: AsyncSession = Depends(get_db)) -> User | None:
    """Không có token thì trả None. Token có nhưng sai hoặc hết hạn thì vẫn báo 401 để frontend refresh."""
    if cred is None:
        return None
    return await _user_from_token(cred.credentials, db)
```

- [x] **Step 7: `app/modules/auth/router.py`**

```python
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/api/v1", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(REFRESH_COOKIE, raw, httponly=True, samesite="lax", secure=s.cookie_secure,
                        path=REFRESH_PATH, max_age=s.refresh_token_days * 86400)


@router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    return await service.register(db, data)


@router.post("/auth/login", response_model=TokenOut)
async def login(data: LoginIn, response: Response, db: AsyncSession = Depends(get_db)):
    access, raw = await service.login(db, data)
    set_refresh_cookie(response, raw)
    return TokenOut(access_token=access)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
```

- [x] **Step 8: Gắn router vào `app/main.py`**
  - Import ở đầu file: `from app.modules.auth.router import router as auth_router`
  - Thêm ngay dưới dòng `# routers`: `app.include_router(auth_router)`

- [x] **Step 9: Chạy test**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS cả 10 test

- [x] **Step 10: Commit**

```bash
git add . && git commit -m "feat(auth): register, login with refresh cookie, /me"
```

---

### Task 6: Refresh token xoay vòng và logout

**Files:**
- Modify: `backend/app/modules/auth/service.py`, `backend/app/modules/auth/router.py`
- Test: `backend/tests/test_refresh.py`

- [x] **Step 1: Viết test hỏng trước — `tests/test_refresh.py`**

```python
from tests.helpers import API, register_user


async def _login_raw(client, email):
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": "password123"})
    assert r.status_code == 200
    return r.cookies["refresh_token"]


async def _refresh_with(client, raw):
    client.cookies.clear()  # chỉ gửi đúng cookie mình chỉ định
    return await client.post(f"{API}/auth/refresh", headers={"Cookie": f"refresh_token={raw}"})


async def test_refresh_rotates_token(client):
    await register_user(client, "r1@x.com")
    old = await _login_raw(client, "r1@x.com")
    r = await _refresh_with(client, old)
    assert r.status_code == 200
    assert r.json()["access_token"]
    new = r.cookies["refresh_token"]
    assert new and new != old


async def test_reusing_rotated_token_revokes_whole_family(client):
    await register_user(client, "r2@x.com")
    old = await _login_raw(client, "r2@x.com")
    new = (await _refresh_with(client, old)).cookies["refresh_token"]

    reuse = await _refresh_with(client, old)
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "TOKEN_REUSED"

    after = await _refresh_with(client, new)  # token mới cũng đã bị thu hồi
    assert after.status_code == 401


async def test_refresh_without_cookie(client):
    client.cookies.clear()
    r = await client.post(f"{API}/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


async def test_logout_revokes_refresh_token(client):
    await register_user(client, "r3@x.com")
    raw = await _login_raw(client, "r3@x.com")
    client.cookies.clear()
    out = await client.post(f"{API}/auth/logout", headers={"Cookie": f"refresh_token={raw}"})
    assert out.status_code == 204
    assert "refresh_token=" in out.headers["set-cookie"]  # cookie bị xóa
    r = await _refresh_with(client, raw)
    assert r.status_code == 401
```

- [x] **Step 2: Chạy test**

Run: `uv run pytest tests/test_refresh.py -v`
Expected: FAIL (404 vì chưa có route refresh/logout)

- [x] **Step 3: Thêm vào `app/modules/auth/service.py`**
  - Sửa dòng import sqlalchemy thành `from sqlalchemy import select, update`
  - Thêm `hash_refresh_token` vào dòng import từ `app.core.security`
  - Thêm 2 hàm sau vào cuối file:

```python
async def refresh(db: AsyncSession, raw: str) -> tuple[str, str]:
    token = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)).with_for_update()
    )
    if token is None:
        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
    if token.revoked_at is not None:
        # Token đã bị xoay mà vẫn có người dùng lại, coi như bị đánh cắp: thu hồi toàn bộ phiên của user.
        await db.execute(update(RefreshToken)
                         .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
                         .values(revoked_at=utcnow()))
        await db.commit()
        raise AppError("TOKEN_REUSED", "Phiên đăng nhập đã bị thu hồi, vui lòng đăng nhập lại", 401)
    if token.expires_at <= utcnow():
        raise AppError("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn", 401)
    user = await db.get(User, token.user_id)
    if user is None or user.locked_at is not None:
        raise AppError("ACCOUNT_LOCKED", "Tài khoản đã bị khóa", 403)
    token.revoked_at = utcnow()
    return await issue_tokens(db, user)


async def logout(db: AsyncSession, raw: str) -> None:
    token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw)))
    if token is not None and token.revoked_at is None:
        token.revoked_at = utcnow()
        await db.commit()
```

- [x] **Step 4: Thêm vào `app/modules/auth/router.py`**
  - Sửa import fastapi thành `from fastapi import APIRouter, Cookie, Depends, Response`
  - Thêm `from app.core.errors import AppError`
  - Thêm 2 route:

```python
@router.post("/auth/refresh", response_model=TokenOut)
async def refresh(response: Response, refresh_token: str | None = Cookie(default=None),
                  db: AsyncSession = Depends(get_db)):
    if not refresh_token:
        raise AppError("INVALID_TOKEN", "Phiên đăng nhập không hợp lệ", 401)
    access, raw = await service.refresh(db, refresh_token)
    set_refresh_cookie(response, raw)
    return TokenOut(access_token=access)


@router.post("/auth/logout", status_code=204)
async def logout(refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    if refresh_token:
        await service.logout(db, refresh_token)
    resp = Response(status_code=204)
    resp.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    return resp
```

- [x] **Step 5: Chạy test**

Run: `uv run pytest tests/test_refresh.py tests/test_auth.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add . && git commit -m "feat(auth): refresh token rotation with reuse detection, logout"
```

---

### Task 7: Dependency phân quyền và script tạo admin / duyệt giáo viên

**Files:**
- Modify: `backend/app/core/deps.py`, `backend/app/modules/auth/service.py`, `backend/tests/helpers.py`
- Create: `backend/app/scripts/__init__.py`, `backend/app/scripts/seed_admin.py`, `backend/app/scripts/approve_teacher.py`
- Test: `backend/tests/test_deps.py`

- [x] **Step 1: Thêm vào cuối `tests/helpers.py`**

```python
async def make_admin(client, email="admin@x.com") -> tuple[str, dict]:
    from app.modules.auth.service import create_admin

    async with SessionLocal() as db:
        user = await create_admin(db, email, "password123")
    return str(user.id), await login(client, email)
```

- [x] **Step 2: Viết test hỏng trước — `tests/test_deps.py`**

```python
import httpx
from fastapi import Depends

from app.core.deps import require_role, require_staff, require_teacher_approved
from app.main import create_app
from app.modules.auth.models import Role
from tests.helpers import make_admin, make_student, make_teacher


def _app_with_probe_routes():
    app = create_app()

    @app.get("/probe/teacher")
    async def teacher_only(user=Depends(require_teacher_approved)):
        return {"ok": True}

    @app.get("/probe/staff")
    async def staff_only(user=Depends(require_staff)):
        return {"ok": True}

    @app.get("/probe/student")
    async def student_only(user=Depends(require_role(Role.student))):
        return {"ok": True}

    return app


async def test_role_matrix(client):
    _, sv = await make_student(client)
    _, gv = await make_teacher(client)
    _, gv_pending = await make_teacher(client, "pending@x.com", approved=False)
    _, ad = await make_admin(client)

    app = _app_with_probe_routes()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        async def code(path, headers):
            r = await c.get(path, headers=headers)
            return r.status_code, (r.json().get("error") or {}).get("code")

        assert await code("/probe/teacher", gv) == (200, None)
        assert await code("/probe/teacher", gv_pending) == (403, "TEACHER_NOT_APPROVED")
        assert await code("/probe/teacher", sv) == (403, "FORBIDDEN")
        assert await code("/probe/staff", ad) == (200, None)
        assert await code("/probe/staff", gv) == (200, None)
        assert await code("/probe/staff", gv_pending) == (403, "TEACHER_NOT_APPROVED")
        assert await code("/probe/staff", sv) == (403, "FORBIDDEN")
        assert await code("/probe/student", sv) == (200, None)
        assert await code("/probe/student", gv) == (403, "FORBIDDEN")


async def test_approve_teacher_service(client, db):
    from app.modules.auth.service import approve_teacher

    uid, _ = await make_teacher(client, "later@x.com", approved=False)
    user = await approve_teacher(db, "later@x.com")
    assert str(user.id) == uid and user.teacher_status.value == "approved"
```

- [x] **Step 3: Chạy test**

Run: `uv run pytest tests/test_deps.py -v`
Expected: FAIL với `ImportError: cannot import name 'require_role'`

- [x] **Step 4: Thêm vào cuối `app/core/deps.py`**
  - Thêm import: `from app.core.errors import AppError, forbidden` (thay cho dòng import `AppError` cũ)
  - Thêm import: `from app.modules.auth.models import Role, TeacherStatus, User` (thay cho dòng import `User` cũ)
  - Thêm các hàm sau:

```python
def require_role(*roles: Role):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise forbidden()
        return user

    return dependency


def _ensure_approved(user: User) -> None:
    if user.teacher_status != TeacherStatus.approved:
        raise AppError("TEACHER_NOT_APPROVED", "Tài khoản giảng viên chưa được duyệt", 403)


async def require_teacher_approved(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.teacher:
        raise forbidden()
    _ensure_approved(user)
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    """Giảng viên đã được duyệt hoặc admin."""
    if user.role == Role.admin:
        return user
    if user.role == Role.teacher:
        _ensure_approved(user)
        return user
    raise forbidden()
```

- [x] **Step 5: Thêm vào cuối `app/modules/auth/service.py`**

```python
async def create_admin(db: AsyncSession, email: str, password: str, full_name: str = "Quản trị viên") -> User:
    email = email.lower()
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(password), full_name=full_name, role=Role.admin)
        db.add(user)
    else:
        user.role = Role.admin
        user.password_hash = hash_password(password)
    await db.commit()
    return user


async def approve_teacher(db: AsyncSession, email: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower(), User.role == Role.teacher))
    if user is None:
        raise AppError("NOT_FOUND", "Không tìm thấy giảng viên", 404)
    user.teacher_status = TeacherStatus.approved
    await db.commit()
    return user
```

- [x] **Step 6: Các script dòng lệnh** (`app/scripts/__init__.py` để trống)

`app/scripts/seed_admin.py`:

```python
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
```

`app/scripts/approve_teacher.py`:

```python
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
```

- [x] **Step 7: Chạy test**

Run: `uv run pytest -v`
Expected: PASS hết

- [x] **Step 8: Chạy thử script trên DB dev**

Run: `uv run python -m app.scripts.seed_admin --email admin@lms.local --password admin12345`
Expected: `Admin sẵn sàng: admin@lms.local`

- [x] **Step 9: Commit**

```bash
git add . && git commit -m "feat(auth): role dependencies, admin seed and teacher approval scripts"
```

---

### Task 8: Model Course, Section, Lesson

**Files:**
- Create: `backend/app/modules/courses/__init__.py`, `backend/app/modules/courses/models.py`
- Modify: `backend/app/models_registry.py`
- Create (sinh bằng lệnh): `backend/alembic/versions/<rev>_courses.py`

- [x] **Step 1: `app/modules/courses/models.py`**

```python
import enum
import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin


class CourseStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class Course(IdMixin, TimestampMixin, Base):
    __tablename__ = "courses"

    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    cover_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[CourseStatus] = mapped_column(SAEnum(CourseStatus, name="course_status"),
                                                 default=CourseStatus.draft)

    sections: Mapped[list["Section"]] = relationship(
        back_populates="course", order_by="Section.position", passive_deletes=True)


class Section(IdMixin, TimestampMixin, Base):
    __tablename__ = "sections"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)

    course: Mapped[Course] = relationship(back_populates="sections")
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="section", order_by="Lesson.position", passive_deletes=True)


class Lesson(IdMixin, TimestampMixin, Base):
    __tablename__ = "lessons"

    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    content_md: Mapped[str] = mapped_column(Text, default="")
    duration_sec: Mapped[int | None] = mapped_column(Integer)

    section: Mapped[Section] = relationship(back_populates="lessons")
```

Quy ước với async: **không bao giờ để quan hệ tự lazy-load**. Cần đọc `sections` hay `lessons` thì dùng `selectinload(...)`. Xóa thì dùng câu `delete()` và để DB tự `ON DELETE CASCADE`.

- [x] **Step 2: Đăng ký vào `app/models_registry.py`**: thêm dòng:

```python
from app.modules.courses import models as courses_models  # noqa: F401
```

- [x] **Step 3: Sinh migration và upgrade**

Run: `uv run alembic revision --autogenerate -m "courses"` rồi `uv run alembic upgrade head`
Expected: migration tạo 3 bảng `courses`, `sections`, `lessons` và enum `course_status`

- [x] **Step 4: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add . && git commit -m "feat(courses): course, section, lesson models"
```

---

### Task 9: CRUD khóa học cho giảng viên

**Files:**
- Create: `backend/app/modules/courses/schemas.py`, `backend/app/modules/courses/service.py`, `backend/app/modules/courses/router.py`
- Modify: `backend/app/main.py`, `backend/tests/helpers.py`
- Test: `backend/tests/test_courses.py`

- [x] **Step 1: Thêm vào cuối `tests/helpers.py`**

```python
async def create_course(client, headers, title="Cấu trúc dữ liệu và Giải thuật", description="Mô tả") -> dict:
    r = await client.post(f"{API}/courses", json={"title": title, "description": description}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()
```

- [x] **Step 2: Viết test hỏng trước — `tests/test_courses.py`**

```python
from tests.helpers import API, create_course, make_admin, make_student, make_teacher


async def test_approved_teacher_creates_draft_course(client):
    uid, gv = await make_teacher(client)
    c = await create_course(client, gv)
    assert c["status"] == "draft"
    assert c["teacher_id"] == uid
    assert c["slug"].startswith("cau-truc-du-lieu-va-giai-thuat-")


async def test_pending_teacher_and_student_cannot_create(client):
    _, pending = await make_teacher(client, "p@x.com", approved=False)
    _, sv = await make_student(client)
    r1 = await client.post(f"{API}/courses", json={"title": "Khóa A"}, headers=pending)
    r2 = await client.post(f"{API}/courses", json={"title": "Khóa A"}, headers=sv)
    assert (r1.status_code, r1.json()["error"]["code"]) == (403, "TEACHER_NOT_APPROVED")
    assert (r2.status_code, r2.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_teacher_lists_only_own_courses(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    await create_course(client, gv1, title="Khóa của GV1")
    await create_course(client, gv2, title="Khóa của GV2")
    r = await client.get(f"{API}/teacher/courses", headers=gv1)
    assert [c["title"] for c in r.json()] == ["Khóa của GV1"]


async def test_other_teacher_gets_404_but_admin_can_edit(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, ad = await make_admin(client)
    c = await create_course(client, gv1)
    r = await client.patch(f"{API}/courses/{c['id']}", json={"title": "Bị sửa trộm"}, headers=gv2)
    assert r.status_code == 404
    r = await client.patch(f"{API}/courses/{c['id']}", json={"title": "Admin sửa"}, headers=ad)
    assert r.status_code == 200 and r.json()["title"] == "Admin sửa"


async def test_patch_ignores_null_fields(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    r = await client.patch(f"{API}/courses/{c['id']}", json={"title": None, "description": "Mới"}, headers=gv)
    assert r.status_code == 200
    assert r.json()["title"] == c["title"] and r.json()["description"] == "Mới"


async def test_delete_course(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    assert (await client.delete(f"{API}/courses/{c['id']}", headers=gv)).status_code == 204
    assert (await client.patch(f"{API}/courses/{c['id']}", json={"title": "Xyz"}, headers=gv)).status_code == 404


async def test_publish_empty_course_is_rejected(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    r = await client.post(f"{API}/courses/{c['id']}/publish", headers=gv)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "COURSE_EMPTY"
```

- [x] **Step 3: Chạy test**

Run: `uv run pytest tests/test_courses.py -v`
Expected: FAIL (404 vì chưa có route)

- [x] **Step 4: `app/modules/courses/schemas.py`**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.courses.models import CourseStatus


class CourseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=5000)


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    title: str
    slug: str
    description: str
    status: CourseStatus
    created_at: datetime
```

- [x] **Step 5: `app/modules/courses/service.py`**

```python
import secrets
import uuid

from slugify import slugify
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.modules.auth.models import Role, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.courses.schemas import CourseCreate, CourseUpdate


def make_slug(title: str) -> str:
    base = slugify(title)[:200] or "khoa-hoc"
    return f"{base}-{secrets.token_hex(3)}"


def ensure_owner(course: Course, user: User) -> None:
    """Admin hoặc giảng viên sở hữu khóa. Người khác nhận 404 để không lộ khóa có tồn tại."""
    if user.role != Role.admin and course.teacher_id != user.id:
        raise not_found("Khóa học")


async def get_owned_course(db: AsyncSession, course_id: uuid.UUID, user: User) -> Course:
    course = await db.get(Course, course_id)
    if course is None:
        raise not_found("Khóa học")
    ensure_owner(course, user)
    return course


async def create_course(db: AsyncSession, teacher: User, data: CourseCreate) -> Course:
    course = Course(teacher_id=teacher.id, title=data.title, description=data.description,
                    slug=make_slug(data.title), status=CourseStatus.draft)
    db.add(course)
    await db.commit()
    return course


async def list_teacher_courses(db: AsyncSession, teacher: User) -> list[Course]:
    rows = await db.scalars(select(Course).where(Course.teacher_id == teacher.id)
                            .order_by(Course.created_at.desc()))
    return list(rows)


async def update_course(db: AsyncSession, course: Course, data: CourseUpdate) -> Course:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(course, field, value)
    await db.commit()
    return course


async def delete_course(db: AsyncSession, course: Course) -> None:
    await db.execute(delete(Course).where(Course.id == course.id))
    await db.commit()


async def count_lessons(db: AsyncSession, course_id: uuid.UUID) -> int:
    return await db.scalar(select(func.count(Lesson.id)).join(Section, Section.id == Lesson.section_id)
                           .where(Section.course_id == course_id))


async def publish_course(db: AsyncSession, course: Course) -> Course:
    if await count_lessons(db, course.id) == 0:
        raise AppError("COURSE_EMPTY", "Khóa học cần ít nhất một bài học trước khi xuất bản", 409)
    course.status = CourseStatus.published
    await db.commit()
    return course
```

- [x] **Step 6: `app/modules/courses/router.py`**

```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_staff, require_teacher_approved
from app.modules.auth.models import User
from app.modules.courses import service
from app.modules.courses.schemas import CourseCreate, CourseOut, CourseUpdate

router = APIRouter(prefix="/api/v1", tags=["courses"])


@router.post("/courses", response_model=CourseOut, status_code=201)
async def create_course(data: CourseCreate, user: User = Depends(require_teacher_approved),
                        db: AsyncSession = Depends(get_db)):
    return await service.create_course(db, user, data)


@router.get("/teacher/courses", response_model=list[CourseOut])
async def my_teaching_courses(user: User = Depends(require_teacher_approved), db: AsyncSession = Depends(get_db)):
    return await service.list_teacher_courses(db, user)


@router.patch("/courses/{course_id}", response_model=CourseOut)
async def update_course(course_id: uuid.UUID, data: CourseUpdate, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)):
    course = await service.get_owned_course(db, course_id, user)
    return await service.update_course(db, course, data)


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(course_id: uuid.UUID, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)) -> None:
    course = await service.get_owned_course(db, course_id, user)
    await service.delete_course(db, course)


@router.post("/courses/{course_id}/publish", response_model=CourseOut)
async def publish_course(course_id: uuid.UUID, user: User = Depends(require_staff),
                         db: AsyncSession = Depends(get_db)):
    course = await service.get_owned_course(db, course_id, user)
    return await service.publish_course(db, course)
```

- [x] **Step 7: Gắn router vào `app/main.py`**
  - Import: `from app.modules.courses.router import router as courses_router`
  - Dưới `# routers`: `app.include_router(courses_router)`

- [x] **Step 8: Chạy test**

Run: `uv run pytest tests/test_courses.py -v`
Expected: PASS cả 7 test

- [x] **Step 9: Commit**

```bash
git add . && git commit -m "feat(courses): teacher course CRUD with ownership checks and publish guard"
```

---

### Task 10: Chương, bài học, sắp xếp lại và xuất bản

**Files:**
- Modify: `backend/app/modules/courses/schemas.py`, `backend/app/modules/courses/service.py`, `backend/app/modules/courses/router.py`, `backend/tests/helpers.py`
- Test: `backend/tests/test_course_content.py`

- [x] **Step 1: Thêm vào cuối `tests/helpers.py`**

```python
async def add_section(client, headers, course_id, title="Chương 1") -> dict:
    r = await client.post(f"{API}/courses/{course_id}/sections", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def add_lesson(client, headers, section_id, title="Bài 1", content_md="# Nội dung") -> dict:
    r = await client.post(f"{API}/sections/{section_id}/lessons",
                          json={"title": title, "content_md": content_md}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def make_published_course(client, teacher_headers, title="Cấu trúc dữ liệu") -> tuple[dict, dict, dict]:
    course = await create_course(client, teacher_headers, title=title)
    section = await add_section(client, teacher_headers, course["id"])
    lesson = await add_lesson(client, teacher_headers, section["id"])
    r = await client.post(f"{API}/courses/{course['id']}/publish", headers=teacher_headers)
    assert r.status_code == 200, r.text
    return r.json(), section, lesson
```

- [x] **Step 2: Viết test hỏng trước — `tests/test_course_content.py`**

```python
import uuid

from sqlalchemy import func, select

from app.modules.courses.models import Lesson, Section
from tests.helpers import API, add_lesson, add_section, create_course, make_teacher


async def test_positions_are_sequential(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s1 = await add_section(client, gv, c["id"], "Chương 1")
    s2 = await add_section(client, gv, c["id"], "Chương 2")
    l1 = await add_lesson(client, gv, s1["id"], "Bài 1")
    l2 = await add_lesson(client, gv, s1["id"], "Bài 2")
    assert (s1["position"], s2["position"]) == (1, 2)
    assert (l1["position"], l2["position"]) == (1, 2)


async def test_other_teacher_cannot_add_or_edit_content(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    c = await create_course(client, gv1)
    s = await add_section(client, gv1, c["id"])
    lesson = await add_lesson(client, gv1, s["id"])
    r1 = await client.post(f"{API}/sections/{s['id']}/lessons", json={"title": "Chen"}, headers=gv2)
    r2 = await client.patch(f"{API}/lessons/{lesson['id']}", json={"title": "Sửa"}, headers=gv2)
    r3 = await client.post(f"{API}/courses/{c['id']}/sections", json={"title": "X"}, headers=gv2)
    assert (r1.status_code, r2.status_code, r3.status_code) == (404, 404, 404)


async def test_update_lesson(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    lesson = await add_lesson(client, gv, s["id"])
    r = await client.patch(f"{API}/lessons/{lesson['id']}",
                           json={"content_md": "## Tìm kiếm nhị phân", "duration_sec": 600}, headers=gv)
    assert r.status_code == 200
    assert r.json()["content_md"] == "## Tìm kiếm nhị phân" and r.json()["duration_sec"] == 600


async def test_reorder_moves_lesson_between_sections(client, db):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s1 = await add_section(client, gv, c["id"], "Chương 1")
    s2 = await add_section(client, gv, c["id"], "Chương 2")
    a = await add_lesson(client, gv, s1["id"], "A")
    b = await add_lesson(client, gv, s1["id"], "B")
    body = {"sections": [{"id": s2["id"], "lesson_ids": [b["id"]]},
                         {"id": s1["id"], "lesson_ids": [a["id"]]}]}
    r = await client.patch(f"{API}/courses/{c['id']}/reorder", json=body, headers=gv)
    assert r.status_code == 204
    sec2 = await db.get(Section, uuid.UUID(s2["id"]))
    lesson_b = await db.get(Lesson, uuid.UUID(b["id"]))
    assert sec2.position == 1
    assert str(lesson_b.section_id) == s2["id"] and lesson_b.position == 1


async def test_reorder_rejects_incomplete_list(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s1 = await add_section(client, gv, c["id"])
    await add_lesson(client, gv, s1["id"], "A")
    body = {"sections": [{"id": s1["id"], "lesson_ids": []}]}
    r = await client.patch(f"{API}/courses/{c['id']}/reorder", json=body, headers=gv)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REORDER"


async def test_delete_section_cascades_lessons(client, db):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    await add_lesson(client, gv, s["id"])
    assert (await client.delete(f"{API}/sections/{s['id']}", headers=gv)).status_code == 204
    assert await db.scalar(select(func.count(Lesson.id))) == 0


async def test_publish_after_adding_lesson(client):
    _, gv = await make_teacher(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    await add_lesson(client, gv, s["id"])
    r = await client.post(f"{API}/courses/{c['id']}/publish", headers=gv)
    assert r.status_code == 200 and r.json()["status"] == "published"
```

- [x] **Step 3: Chạy test**

Run: `uv run pytest tests/test_course_content.py -v`
Expected: FAIL (404 vì chưa có route)

- [x] **Step 4: Thêm vào cuối `app/modules/courses/schemas.py`**

```python
class SectionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SectionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    position: int


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content_md: str = Field(default="", max_length=100_000)


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_md: str | None = Field(default=None, max_length=100_000)
    duration_sec: int | None = Field(default=None, ge=0)


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    title: str
    position: int
    content_md: str
    duration_sec: int | None


class ReorderSection(BaseModel):
    id: uuid.UUID
    lesson_ids: list[uuid.UUID]


class ReorderIn(BaseModel):
    sections: list[ReorderSection]
```

- [x] **Step 5: Thêm vào `app/modules/courses/service.py`**
  - Sửa dòng import schemas thành:
    `from app.modules.courses.schemas import (CourseCreate, CourseUpdate, LessonCreate, LessonUpdate, ReorderIn, SectionCreate, SectionUpdate)`
  - Thêm các hàm sau vào cuối file:

```python
async def _next_position(db: AsyncSession, column, condition) -> int:
    return (await db.scalar(select(func.coalesce(func.max(column), 0)).where(condition))) + 1


async def add_section(db: AsyncSession, course: Course, data: SectionCreate) -> Section:
    position = await _next_position(db, Section.position, Section.course_id == course.id)
    section = Section(course_id=course.id, title=data.title, position=position)
    db.add(section)
    await db.commit()
    return section


async def get_owned_section(db: AsyncSession, section_id: uuid.UUID, user: User) -> Section:
    row = (await db.execute(select(Section, Course).join(Course, Course.id == Section.course_id)
                            .where(Section.id == section_id))).one_or_none()
    if row is None:
        raise not_found("Chương")
    section, course = row
    ensure_owner(course, user)
    return section


async def update_section(db: AsyncSession, section: Section, data: SectionUpdate) -> Section:
    section.title = data.title
    await db.commit()
    return section


async def delete_section(db: AsyncSession, section: Section) -> None:
    await db.execute(delete(Section).where(Section.id == section.id))
    await db.commit()


async def add_lesson(db: AsyncSession, section: Section, data: LessonCreate) -> Lesson:
    position = await _next_position(db, Lesson.position, Lesson.section_id == section.id)
    lesson = Lesson(section_id=section.id, title=data.title, content_md=data.content_md, position=position)
    db.add(lesson)
    await db.commit()
    return lesson


async def get_lesson_with_course(db: AsyncSession, lesson_id: uuid.UUID) -> tuple[Lesson, Course]:
    row = (await db.execute(
        select(Lesson, Course)
        .join(Section, Section.id == Lesson.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Lesson.id == lesson_id)
    )).one_or_none()
    if row is None:
        raise not_found("Bài học")
    return row[0], row[1]


async def get_owned_lesson(db: AsyncSession, lesson_id: uuid.UUID, user: User) -> tuple[Lesson, Course]:
    lesson, course = await get_lesson_with_course(db, lesson_id)
    ensure_owner(course, user)
    return lesson, course


async def update_lesson(db: AsyncSession, lesson: Lesson, data: LessonUpdate) -> Lesson:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(lesson, field, value)
    await db.commit()
    return lesson


async def delete_lesson(db: AsyncSession, lesson: Lesson) -> None:
    await db.execute(delete(Lesson).where(Lesson.id == lesson.id))
    await db.commit()


async def reorder(db: AsyncSession, course: Course, data: ReorderIn) -> None:
    sections = {s.id: s for s in await db.scalars(select(Section).where(Section.course_id == course.id))}
    lessons = {lesson.id: lesson for lesson in await db.scalars(
        select(Lesson).join(Section, Section.id == Lesson.section_id).where(Section.course_id == course.id))}
    given_sections = [s.id for s in data.sections]
    given_lessons = [lid for s in data.sections for lid in s.lesson_ids]
    if (sorted(given_sections) != sorted(sections) or sorted(given_lessons) != sorted(lessons)):
        raise AppError("INVALID_REORDER", "Danh sách sắp xếp không khớp với khóa học", 400)
    for s_pos, item in enumerate(data.sections, start=1):
        sections[item.id].position = s_pos
        for l_pos, lesson_id in enumerate(item.lesson_ids, start=1):
            lessons[lesson_id].section_id = item.id
            lessons[lesson_id].position = l_pos
    await db.commit()
```

(`sorted` trên danh sách có trùng phần tử thì kết quả vẫn khác, nên trường hợp gửi trùng ID cũng bị chặn.)

- [x] **Step 6: Thêm vào `app/modules/courses/router.py`**
  - Sửa import schemas thành:
    `from app.modules.courses.schemas import (CourseCreate, CourseOut, CourseUpdate, LessonCreate, LessonOut, LessonUpdate, ReorderIn, SectionCreate, SectionOut, SectionUpdate)`
  - Thêm các route sau:

```python
@router.post("/courses/{course_id}/sections", response_model=SectionOut, status_code=201)
async def add_section(course_id: uuid.UUID, data: SectionCreate, user: User = Depends(require_staff),
                      db: AsyncSession = Depends(get_db)):
    course = await service.get_owned_course(db, course_id, user)
    return await service.add_section(db, course, data)


@router.patch("/sections/{section_id}", response_model=SectionOut)
async def update_section(section_id: uuid.UUID, data: SectionUpdate, user: User = Depends(require_staff),
                         db: AsyncSession = Depends(get_db)):
    section = await service.get_owned_section(db, section_id, user)
    return await service.update_section(db, section, data)


@router.delete("/sections/{section_id}", status_code=204)
async def delete_section(section_id: uuid.UUID, user: User = Depends(require_staff),
                         db: AsyncSession = Depends(get_db)) -> None:
    section = await service.get_owned_section(db, section_id, user)
    await service.delete_section(db, section)


@router.post("/sections/{section_id}/lessons", response_model=LessonOut, status_code=201)
async def add_lesson(section_id: uuid.UUID, data: LessonCreate, user: User = Depends(require_staff),
                     db: AsyncSession = Depends(get_db)):
    section = await service.get_owned_section(db, section_id, user)
    return await service.add_lesson(db, section, data)


@router.patch("/lessons/{lesson_id}", response_model=LessonOut)
async def update_lesson(lesson_id: uuid.UUID, data: LessonUpdate, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)):
    lesson, _ = await service.get_owned_lesson(db, lesson_id, user)
    return await service.update_lesson(db, lesson, data)


@router.delete("/lessons/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: uuid.UUID, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)) -> None:
    lesson, _ = await service.get_owned_lesson(db, lesson_id, user)
    await service.delete_lesson(db, lesson)


@router.patch("/courses/{course_id}/reorder", status_code=204)
async def reorder(course_id: uuid.UUID, data: ReorderIn, user: User = Depends(require_staff),
                  db: AsyncSession = Depends(get_db)) -> None:
    course = await service.get_owned_course(db, course_id, user)
    await service.reorder(db, course, data)
```

- [x] **Step 7: Chạy test**

Run: `uv run pytest tests/test_course_content.py tests/test_courses.py -v`
Expected: PASS

- [x] **Step 8: Commit**

```bash
git add . && git commit -m "feat(courses): sections, lessons, reorder and publish"
```

---

### Task 11: Đăng ký khóa học và "Khóa của tôi"

**Files:**
- Create: `backend/app/modules/enrollment/__init__.py`, `backend/app/modules/enrollment/models.py`, `backend/app/modules/enrollment/schemas.py`, `backend/app/modules/enrollment/service.py`, `backend/app/modules/enrollment/router.py`
- Modify: `backend/app/models_registry.py`, `backend/app/main.py`
- Create (sinh bằng lệnh): `backend/alembic/versions/<rev>_enrollment.py`
- Test: `backend/tests/test_enrollment.py`

- [x] **Step 1: `app/modules/enrollment/models.py`**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProgressStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    done = "done"


class Enrollment(Base):
    __tablename__ = "enrollments"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"),
                                                 primary_key=True, index=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[ProgressStatus] = mapped_column(SAEnum(ProgressStatus, name="progress_status"),
                                                   default=ProgressStatus.not_started)
    video_position_sec: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
```

- [x] **Step 2: Đăng ký model và sinh migration**
  - Thêm vào `app/models_registry.py`: `from app.modules.enrollment import models as enrollment_models  # noqa: F401`

Run: `uv run alembic revision --autogenerate -m "enrollment"` rồi `uv run alembic upgrade head`
Expected: tạo 2 bảng `enrollments` và `lesson_progress`

- [x] **Step 3: Viết test hỏng trước — `tests/test_enrollment.py`**

```python
from tests.helpers import API, create_course, make_published_course, make_student, make_teacher


async def test_student_enrolls_published_course(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    assert r.status_code == 201
    assert r.json()["course_id"] == course["id"]


async def test_enroll_twice_is_conflict(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "ALREADY_ENROLLED")


async def test_cannot_enroll_draft_course(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    draft = await create_course(client, gv)
    r = await client.post(f"{API}/courses/{draft['id']}/enroll", headers=sv)
    assert r.status_code == 404


async def test_teacher_cannot_enroll(client):
    _, gv = await make_teacher(client)
    course, _, _ = await make_published_course(client, gv)
    r = await client.post(f"{API}/courses/{course['id']}/enroll", headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_my_courses_shows_progress(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    r = await client.get(f"{API}/me/courses", headers=sv)
    assert r.status_code == 200
    [item] = r.json()
    assert item["course_id"] == course["id"]
    assert (item["total_lessons"], item["done_lessons"], item["progress_pct"]) == (1, 0, 0)
```

- [x] **Step 4: Chạy test**

Run: `uv run pytest tests/test_enrollment.py -v`
Expected: FAIL (404 vì chưa có route)

- [x] **Step 5: `app/modules/enrollment/schemas.py`**

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class EnrollmentOut(BaseModel):
    course_id: uuid.UUID
    enrolled_at: datetime


class MyCourseOut(BaseModel):
    course_id: uuid.UUID
    title: str
    slug: str
    enrolled_at: datetime
    completed_at: datetime | None
    total_lessons: int
    done_lessons: int
    progress_pct: int
```

- [x] **Step 6: `app/modules/enrollment/service.py`**

```python
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.modules.auth.models import User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.enrollment.models import Enrollment, LessonProgress, ProgressStatus
from app.modules.enrollment.schemas import EnrollmentOut, MyCourseOut


async def enroll(db: AsyncSession, user: User, course_id: uuid.UUID) -> EnrollmentOut:
    course = await db.get(Course, course_id)
    if course is None or course.status != CourseStatus.published:
        raise not_found("Khóa học")
    stmt = (pg_insert(Enrollment).values(user_id=user.id, course_id=course_id)
            .on_conflict_do_nothing().returning(Enrollment.course_id, Enrollment.enrolled_at))
    row = (await db.execute(stmt)).first()
    if row is None:
        raise AppError("ALREADY_ENROLLED", "Bạn đã đăng ký khóa học này", 409)
    await db.commit()
    return EnrollmentOut(course_id=row.course_id, enrolled_at=row.enrolled_at)


async def is_enrolled(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    return await db.scalar(select(func.count()).select_from(Enrollment)
                           .where(Enrollment.user_id == user_id, Enrollment.course_id == course_id)) > 0


async def my_courses(db: AsyncSession, user: User) -> list[MyCourseOut]:
    rows = (await db.execute(
        select(Enrollment, Course).join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.user_id == user.id).order_by(Enrollment.enrolled_at.desc())
    )).all()
    course_ids = [course.id for _, course in rows]
    totals = dict((await db.execute(
        select(Section.course_id, func.count(Lesson.id)).join(Lesson, Lesson.section_id == Section.id)
        .where(Section.course_id.in_(course_ids)).group_by(Section.course_id)
    )).all())
    dones = dict((await db.execute(
        select(Section.course_id, func.count(LessonProgress.lesson_id))
        .join(Lesson, Lesson.id == LessonProgress.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(LessonProgress.user_id == user.id, LessonProgress.status == ProgressStatus.done,
               Section.course_id.in_(course_ids))
        .group_by(Section.course_id)
    )).all())
    result = []
    for enrollment, course in rows:
        total, done = totals.get(course.id, 0), dones.get(course.id, 0)
        result.append(MyCourseOut(
            course_id=course.id, title=course.title, slug=course.slug,
            enrolled_at=enrollment.enrolled_at, completed_at=enrollment.completed_at,
            total_lessons=total, done_lessons=done,
            progress_pct=round(done * 100 / total) if total else 0,
        ))
    return result
```

- [x] **Step 7: `app/modules/enrollment/router.py`**

```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_role
from app.modules.auth.models import Role, User
from app.modules.enrollment import service
from app.modules.enrollment.schemas import EnrollmentOut, MyCourseOut

router = APIRouter(prefix="/api/v1", tags=["enrollment"])


@router.post("/courses/{course_id}/enroll", response_model=EnrollmentOut, status_code=201)
async def enroll(course_id: uuid.UUID, user: User = Depends(require_role(Role.student)),
                 db: AsyncSession = Depends(get_db)):
    return await service.enroll(db, user, course_id)


@router.get("/me/courses", response_model=list[MyCourseOut])
async def my_courses(user: User = Depends(require_role(Role.student)), db: AsyncSession = Depends(get_db)):
    return await service.my_courses(db, user)
```

- [x] **Step 8: Gắn router vào `app/main.py`**
  - Import: `from app.modules.enrollment.router import router as enrollment_router`
  - Dưới `# routers`: `app.include_router(enrollment_router)`

- [x] **Step 9: Chạy test**

Run: `uv run pytest tests/test_enrollment.py -v`
Expected: PASS cả 5 test

- [x] **Step 10: Commit**

```bash
git add . && git commit -m "feat(enrollment): enroll in published courses, my courses with progress"
```

---

### Task 12: Catalog công khai và trang chi tiết khóa học (auth tùy chọn)

**Files:**
- Modify: `backend/app/modules/courses/schemas.py`, `backend/app/modules/courses/service.py`, `backend/app/modules/courses/router.py`
- Test: `backend/tests/test_catalog.py`

- [x] **Step 1: Viết test hỏng trước — `tests/test_catalog.py`**

```python
from tests.helpers import API, create_course, make_published_course, make_student, make_teacher


async def test_catalog_lists_only_published(client):
    _, gv = await make_teacher(client)
    await make_published_course(client, gv, title="Cấu trúc dữ liệu")
    await create_course(client, gv, title="Bản nháp bí mật")
    r = await client.get(f"{API}/courses")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Cấu trúc dữ liệu"
    assert body["items"][0]["teacher_name"] == "Giảng viên"


async def test_catalog_search_ignores_diacritics_and_case(client):
    _, gv = await make_teacher(client)
    await make_published_course(client, gv, title="Cấu trúc dữ liệu")
    await make_published_course(client, gv, title="Mạng máy tính")
    r = await client.get(f"{API}/courses", params={"q": "CAU TRUC"})
    assert [c["title"] for c in r.json()["items"]] == ["Cấu trúc dữ liệu"]


async def test_catalog_pagination(client):
    _, gv = await make_teacher(client)
    for i in range(3):
        await make_published_course(client, gv, title=f"Khóa số {i}")
    r = await client.get(f"{API}/courses", params={"page": 2, "size": 2})
    assert r.json()["total"] == 3 and len(r.json()["items"]) == 1


async def test_course_detail_anonymous_shows_outline_without_content(client):
    _, gv = await make_teacher(client)
    course, section, lesson = await make_published_course(client, gv)
    client.cookies.clear()
    r = await client.get(f"{API}/courses/{course['slug']}")
    assert r.status_code == 200
    d = r.json()
    assert d["is_enrolled"] is False and d["is_owner"] is False
    assert d["sections"][0]["id"] == section["id"]
    lesson_brief = d["sections"][0]["lessons"][0]
    assert lesson_brief["id"] == lesson["id"]
    assert "content_md" not in lesson_brief


async def test_course_detail_shows_enrolled_flag(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, _ = await make_published_course(client, gv)
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    r = await client.get(f"{API}/courses/{course['slug']}", headers=sv)
    assert r.json()["is_enrolled"] is True


async def test_draft_detail_hidden_from_public_visible_to_owner(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    draft = await create_course(client, gv)
    assert (await client.get(f"{API}/courses/{draft['slug']}")).status_code == 404
    assert (await client.get(f"{API}/courses/{draft['slug']}", headers=sv)).status_code == 404
    r = await client.get(f"{API}/courses/{draft['slug']}", headers=gv)
    assert r.status_code == 200 and r.json()["is_owner"] is True


async def test_course_routes_are_not_shadowed_by_slug(client):
    """Canh luật thứ tự route: GET /courses (không có slug) vẫn là catalog, không bị hiểu thành slug rỗng."""
    r = await client.get(f"{API}/courses")
    assert r.status_code == 200 and "items" in r.json()


async def test_invalid_token_on_optional_auth_is_401(client):
    _, gv = await make_teacher(client)
    course, _, _ = await make_published_course(client, gv)
    r = await client.get(f"{API}/courses/{course['slug']}", headers={"Authorization": "Bearer rac"})
    assert r.status_code == 401
```

- [x] **Step 2: Chạy test**

Run: `uv run pytest tests/test_catalog.py -v`
Expected: FAIL (405 Method Not Allowed, hoặc 404 vì chưa có `GET /courses`)

- [x] **Step 3: Thêm vào cuối `app/modules/courses/schemas.py`**

```python
class CourseCard(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    description: str
    teacher_name: str


class CoursePage(BaseModel):
    items: list[CourseCard]
    total: int
    page: int
    size: int


class LessonBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    position: int
    duration_sec: int | None


class SectionBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    position: int
    lessons: list[LessonBrief]


class CourseDetail(CourseOut):
    teacher_name: str
    sections: list[SectionBrief]
    is_enrolled: bool
    is_owner: bool
```

- [x] **Step 4: Thêm vào `app/modules/courses/service.py`**
  - Thêm import: `from sqlalchemy.orm import selectinload`
  - Thêm `CourseCard, CourseDetail, CourseOut, CoursePage, SectionBrief` vào dòng import schemas
  - Thêm các hàm sau vào cuối file:

```python
async def list_published(db: AsyncSession, q: str | None, page: int, size: int) -> CoursePage:
    base = (select(Course, User.full_name).join(User, User.id == Course.teacher_id)
            .where(Course.status == CourseStatus.published))
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        base = base.where(func.immutable_unaccent(func.lower(Course.title)).like(func.immutable_unaccent(pattern)))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(Course.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    items = [CourseCard(id=c.id, title=c.title, slug=c.slug, description=c.description, teacher_name=name)
             for c, name in rows]
    return CoursePage(items=items, total=total, page=page, size=size)


async def get_course_detail(db: AsyncSession, slug: str, user: User | None) -> CourseDetail:
    from app.modules.enrollment.service import is_enrolled  # import trong hàm để tránh vòng import

    course = await db.scalar(select(Course).where(Course.slug == slug)
                             .options(selectinload(Course.sections).selectinload(Section.lessons)))
    if course is None:
        raise not_found("Khóa học")
    is_owner = user is not None and (user.role == Role.admin or course.teacher_id == user.id)
    if course.status != CourseStatus.published and not is_owner:
        raise not_found("Khóa học")
    teacher_name = await db.scalar(select(User.full_name).where(User.id == course.teacher_id))
    enrolled = user is not None and await is_enrolled(db, user.id, course.id)
    return CourseDetail(
        **CourseOut.model_validate(course).model_dump(),
        teacher_name=teacher_name,
        sections=[SectionBrief.model_validate(s) for s in course.sections],
        is_enrolled=enrolled,
        is_owner=is_owner,
    )
```

- [x] **Step 5: Thêm vào `app/modules/courses/router.py`**
  - Sửa import fastapi thành `from fastapi import APIRouter, Depends, Query`
  - Sửa import deps thành `from app.core.deps import get_optional_user, require_staff, require_teacher_approved`
  - Thêm `CourseDetail, CoursePage` vào dòng import schemas
  - Thêm 2 route vào **cuối file**. **Luật thứ tự route:** `GET /courses/{slug}` luôn là route `GET /courses/...` **cuối cùng**. Mọi path tĩnh sau này (ví dụ `/courses/featured`) phải khai báo **trong router này, phía trên** nó. Nếu đặt ở router khác được include sau, path tĩnh sẽ bị `{slug}` nuốt mất. Hiện tại chưa có xung đột: các route khác dưới `/courses/...` đều có thêm segment (`/{id}/publish`, `/{id}/enroll`...) hoặc khác method.

```python
@router.get("/courses", response_model=CoursePage)
async def catalog(q: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                  db: AsyncSession = Depends(get_db)):
    return await service.list_published(db, q, page, size)


@router.get("/courses/{slug}", response_model=CourseDetail)
async def course_detail(slug: str, user: User | None = Depends(get_optional_user),
                        db: AsyncSession = Depends(get_db)):
    return await service.get_course_detail(db, slug, user)
```

- [x] **Step 6: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: PASS hết

- [x] **Step 7: Commit**

```bash
git add . && git commit -m "feat(courses): public catalog with accent-insensitive search, course detail with optional auth"
```

---

### Task 13: Quyền truy cập bài học và cập nhật tiến độ

**Files:**
- Modify: `backend/app/modules/enrollment/schemas.py`, `backend/app/modules/enrollment/service.py`, `backend/app/modules/enrollment/router.py`
- Test: `backend/tests/test_lesson_access.py`

- [x] **Step 1: Viết test hỏng trước — `tests/test_lesson_access.py`**

```python
from tests.helpers import (
    API, add_lesson, add_section, create_course, make_published_course, make_student, make_teacher,
)


async def _enroll(client, headers, course_id):
    r = await client.post(f"{API}/courses/{course_id}/enroll", headers=headers)
    assert r.status_code == 201


async def test_enrolled_student_reads_lesson(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    await _enroll(client, sv, course["id"])
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)
    assert r.status_code == 200
    assert r.json()["content_md"] == "# Nội dung"
    assert r.json()["progress"] is None


async def test_not_enrolled_student_gets_403(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")


async def test_draft_lesson_is_404_for_student(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    c = await create_course(client, gv)
    s = await add_section(client, gv, c["id"])
    lesson = await add_lesson(client, gv, s["id"])
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=sv)
    assert r.status_code == 404


async def test_owner_previews_without_enrolling_other_teacher_cannot(client):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, _, lesson = await make_published_course(client, gv1)
    assert (await client.get(f"{API}/lessons/{lesson['id']}", headers=gv1)).status_code == 200
    r = await client.get(f"{API}/lessons/{lesson['id']}", headers=gv2)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "NOT_ENROLLED")


async def test_progress_done_completes_course_and_never_downgrades(client):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    await _enroll(client, sv, course["id"])

    r = await client.put(f"{API}/lessons/{lesson['id']}/progress",
                         json={"status": "done", "video_position_sec": 120}, headers=sv)
    assert r.status_code == 200 and r.json()["status"] == "done"

    [mine] = (await client.get(f"{API}/me/courses", headers=sv)).json()
    assert mine["progress_pct"] == 100 and mine["completed_at"] is not None

    r = await client.put(f"{API}/lessons/{lesson['id']}/progress",
                         json={"status": "in_progress", "video_position_sec": 30}, headers=sv)
    assert r.json()["status"] == "done" and r.json()["video_position_sec"] == 30


async def test_teacher_cannot_save_progress(client):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await client.put(f"{API}/lessons/{lesson['id']}/progress",
                         json={"status": "done", "video_position_sec": 0}, headers=gv)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
```

- [x] **Step 2: Chạy test**

Run: `uv run pytest tests/test_lesson_access.py -v`
Expected: FAIL (405 Method Not Allowed cho `GET /lessons/{id}`)

- [x] **Step 3: Thêm vào cuối `app/modules/enrollment/schemas.py`**
  - Thêm import: `from typing import Literal` và `from pydantic import ConfigDict, Field`
  - Thêm import: `from app.modules.enrollment.models import ProgressStatus`

```python
class ProgressIn(BaseModel):
    status: Literal["in_progress", "done"]
    video_position_sec: int = Field(ge=0)


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: ProgressStatus
    video_position_sec: int
    completed_at: datetime | None


class LessonDetail(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    course_id: uuid.UUID
    title: str
    content_md: str
    duration_sec: int | None
    progress: ProgressOut | None
```

- [x] **Step 4: Thêm vào `app/modules/enrollment/service.py`**
  - Sửa import sqlalchemy thành `from sqlalchemy import case, func, select, update`
  - Thêm import: `from app.core.errors import forbidden` (gộp vào dòng import errors có sẵn)
  - Thêm import: `from app.core.time import utcnow`
  - Thêm import: `from app.modules.auth.models import Role` (gộp vào dòng import `User`)
  - Thêm import: `from app.modules.courses.service import get_lesson_with_course`
  - Thêm `LessonDetail, ProgressIn, ProgressOut` vào dòng import schemas
  - Thêm các hàm sau vào cuối file:

```python
async def ensure_lesson_access(db: AsyncSession, lesson_id: uuid.UUID, user: User) -> tuple[Lesson, Course]:
    """Admin và giảng viên sở hữu khóa luôn được vào. Học viên phải đăng ký khóa đã xuất bản."""
    lesson, course = await get_lesson_with_course(db, lesson_id)
    if user.role == Role.admin or course.teacher_id == user.id:
        return lesson, course
    if course.status != CourseStatus.published:
        raise not_found("Bài học")
    if not await is_enrolled(db, user.id, course.id):
        raise AppError("NOT_ENROLLED", "Bạn cần đăng ký khóa học để xem bài này", 403)
    return lesson, course


async def get_lesson_detail(db: AsyncSession, lesson_id: uuid.UUID, user: User) -> LessonDetail:
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    progress = await db.get(LessonProgress, (user.id, lesson.id))
    return LessonDetail(id=lesson.id, section_id=lesson.section_id, course_id=course.id, title=lesson.title,
                        content_md=lesson.content_md, duration_sec=lesson.duration_sec,
                        progress=ProgressOut.model_validate(progress) if progress else None)


async def update_progress(db: AsyncSession, lesson_id: uuid.UUID, user: User, data: ProgressIn) -> ProgressOut:
    if user.role != Role.student:
        raise forbidden("Chỉ học viên mới lưu tiến độ")
    lesson, course = await ensure_lesson_access(db, lesson_id, user)
    new_status = ProgressStatus(data.status)
    now = utcnow()
    stmt = pg_insert(LessonProgress).values(
        user_id=user.id, lesson_id=lesson.id, status=new_status, video_position_sec=data.video_position_sec,
        completed_at=now if new_status == ProgressStatus.done else None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[LessonProgress.user_id, LessonProgress.lesson_id],
        set_={
            # Đã "done" thì giữ nguyên "done" (học viên xem lại bài không làm mất tiến độ)
            "status": case((LessonProgress.status == ProgressStatus.done, LessonProgress.status),
                           else_=stmt.excluded.status),
            "video_position_sec": stmt.excluded.video_position_sec,
            "completed_at": func.coalesce(LessonProgress.completed_at, stmt.excluded.completed_at),
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)

    total = await db.scalar(select(func.count(Lesson.id)).join(Section, Section.id == Lesson.section_id)
                            .where(Section.course_id == course.id))
    done = await db.scalar(
        select(func.count(LessonProgress.lesson_id))
        .join(Lesson, Lesson.id == LessonProgress.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .where(Section.course_id == course.id, LessonProgress.user_id == user.id,
               LessonProgress.status == ProgressStatus.done))
    if total and done >= total:
        await db.execute(update(Enrollment)
                         .where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)
                         .values(completed_at=func.coalesce(Enrollment.completed_at, func.now())))
    await db.commit()
    progress = await db.get(LessonProgress, (user.id, lesson.id), populate_existing=True)
    return ProgressOut.model_validate(progress)
```

- [x] **Step 5: Thêm vào `app/modules/enrollment/router.py`**
  - Sửa import deps thành `from app.core.deps import get_current_user, require_role`
  - Thêm `LessonDetail, ProgressIn, ProgressOut` vào dòng import schemas
  - Thêm 2 route:

```python
@router.get("/lessons/{lesson_id}", response_model=LessonDetail)
async def lesson_detail(lesson_id: uuid.UUID, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await service.get_lesson_detail(db, lesson_id, user)


@router.put("/lessons/{lesson_id}/progress", response_model=ProgressOut)
async def save_progress(lesson_id: uuid.UUID, data: ProgressIn, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await service.update_progress(db, lesson_id, user, data)
```

- [x] **Step 6: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: PASS hết

- [x] **Step 7: Commit**

```bash
git add . && git commit -m "feat(enrollment): lesson access rules, progress upsert, course completion"
```

---

### Task 14: Storage, Asset, upload có presign và gắn video vào bài học

**Files:**
- Create: `backend/app/core/storage.py`, `backend/app/modules/materials/__init__.py`, `backend/app/modules/materials/models.py`, `backend/app/modules/materials/assets.py`, `backend/app/modules/materials/schemas.py`, `backend/app/modules/materials/router.py`, `backend/tests/fakes.py`
- Modify: `backend/app/modules/courses/models.py`, `backend/app/modules/courses/schemas.py`, `backend/app/modules/courses/router.py`, `backend/app/models_registry.py`, `backend/app/main.py`, `backend/tests/conftest.py`
- Create (sinh bằng lệnh): `backend/alembic/versions/<rev>_assets.py`, `backend/alembic/versions/<rev>_lesson_video_index.py`
- Test: `backend/tests/test_uploads.py`, `backend/tests/test_storage.py`

- [x] **Step 1: `app/core/storage.py`**
  - Trình duyệt chỉ được ký URL PUT vào key tạm `staging/<key>`; key chính thức chỉ server ghi (copy sau khi kiểm tra).
  - `presign_get` luôn ký kèm `response-content-type` = mime của asset (spec §6.3), nên `mime` là tham số bắt buộc.

```python
import asyncio
import io
from datetime import timedelta
from functools import lru_cache
from typing import Protocol

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from app.core.config import Settings, get_settings

STAGING_PREFIX = "staging/"


def staging_key(key: str) -> str:
    """Key tạm mà trình duyệt được PUT vào. Key chính thức chỉ server ghi (copy sau khi kiểm tra)."""
    return STAGING_PREFIX + key


def download_headers(mime: str, download_name: str | None = None) -> dict[str, str]:
    """Header response ký kèm presigned GET: luôn trả đúng Content-Type, thêm attachment nếu có tên file."""
    headers = {"response-content-type": mime}
    if download_name:
        headers["response-content-disposition"] = f'attachment; filename="{download_name}"'
    return headers


class Storage(Protocol):
    async def presign_put(self, key: str, expires_s: int = 900) -> str: ...
    async def presign_get(self, key: str, mime: str, expires_s: int = 3600,
                          download_name: str | None = None) -> str: ...
    async def stat_size(self, key: str) -> int | None: ...
    async def read_head(self, key: str, n: int = 2048) -> bytes: ...
    async def read_all(self, key: str) -> bytes: ...
    async def put(self, key: str, data: bytes, mime: str) -> None: ...
    async def copy(self, src_key: str, dst_key: str) -> None: ...
    async def remove(self, key: str) -> None: ...


class MinioStorage:
    REGION = "us-east-1"  # có sẵn region thì client không cần gọi mạng để dò region khi ký URL

    def __init__(self, s: Settings):
        kw = dict(access_key=s.minio_access_key, secret_key=s.minio_secret_key,
                  secure=s.minio_secure, region=self.REGION)
        self._internal = Minio(s.minio_endpoint, **kw)       # API và worker gọi trong mạng Docker
        self._public = Minio(s.minio_public_endpoint, **kw)  # chỉ dùng để ký URL cho trình duyệt
        self._bucket = s.minio_bucket

    async def ensure_bucket(self) -> None:
        def run() -> None:
            if not self._internal.bucket_exists(self._bucket):
                self._internal.make_bucket(self._bucket)
        await asyncio.to_thread(run)

    async def presign_put(self, key: str, expires_s: int = 900) -> str:
        return await asyncio.to_thread(self._public.presigned_put_object, self._bucket, key,
                                       timedelta(seconds=expires_s))

    async def presign_get(self, key: str, mime: str, expires_s: int = 3600,
                          download_name: str | None = None) -> str:
        headers = download_headers(mime, download_name)
        return await asyncio.to_thread(lambda: self._public.presigned_get_object(
            self._bucket, key, expires=timedelta(seconds=expires_s), response_headers=headers))

    async def stat_size(self, key: str) -> int | None:
        def run() -> int | None:
            try:
                return self._internal.stat_object(self._bucket, key).size
            except S3Error as e:
                if e.code in ("NoSuchKey", "NoSuchObject"):
                    return None
                raise
        return await asyncio.to_thread(run)

    async def read_head(self, key: str, n: int = 2048) -> bytes:
        def run() -> bytes:
            resp = self._internal.get_object(self._bucket, key, offset=0, length=n)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        return await asyncio.to_thread(run)

    async def read_all(self, key: str) -> bytes:
        def run() -> bytes:
            resp = self._internal.get_object(self._bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        return await asyncio.to_thread(run)

    async def put(self, key: str, data: bytes, mime: str) -> None:
        await asyncio.to_thread(self._internal.put_object, self._bucket, key, io.BytesIO(data), len(data),
                                content_type=mime)

    async def copy(self, src_key: str, dst_key: str) -> None:
        # copy phía server, giữ nguyên metadata (Content-Type) của object nguồn
        await asyncio.to_thread(self._internal.copy_object, self._bucket, dst_key,
                                CopySource(self._bucket, src_key))

    async def remove(self, key: str) -> None:
        await asyncio.to_thread(self._internal.remove_object, self._bucket, key)


@lru_cache
def get_storage() -> Storage:
    return MinioStorage(get_settings())
```

- [x] **Step 2: `tests/fakes.py`**

```python
from app.core.storage import download_headers


class InMemoryStorage:
    """Storage giả trong bộ nhớ. Test đóng vai trình duyệt PUT bằng `client_put` vào đúng key của URL presign."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.mimes: dict[str, str] = {}
        self.signed_gets: dict[str, dict[str, str]] = {}  # key -> header response đã được yêu cầu ký
        self.on_copy = None  # hook chạy ngay trước khi copy, để mô phỏng client PUT chen vào giữa chừng

    def client_put(self, put_url: str, data: bytes, mime: str = "application/octet-stream") -> str:
        key = put_url.removeprefix("memory://put/")
        self.objects[key] = data
        self.mimes[key] = mime
        return key

    async def presign_put(self, key, expires_s=900):
        return f"memory://put/{key}"

    async def presign_get(self, key, mime, expires_s=3600, download_name=None):
        self.signed_gets[key] = download_headers(mime, download_name)
        return f"memory://get/{key}"

    async def stat_size(self, key):
        data = self.objects.get(key)
        return None if data is None else len(data)

    async def read_head(self, key, n=2048):
        return self.objects[key][:n]

    async def read_all(self, key):
        return self.objects[key]

    async def put(self, key, data, mime):
        self.objects[key] = data
        self.mimes[key] = mime

    async def copy(self, src_key, dst_key):
        if self.on_copy is not None:
            self.on_copy()
        self.objects[dst_key] = self.objects[src_key]
        if src_key in self.mimes:
            self.mimes[dst_key] = self.mimes[src_key]

    async def remove(self, key):
        self.objects.pop(key, None)
        self.mimes.pop(key, None)
```

- [x] **Step 3: Sửa fixture `client` trong `tests/conftest.py`**: thay fixture `client` cũ bằng:

```python
from app.core.storage import get_storage  # noqa: E402
from tests.fakes import InMemoryStorage  # noqa: E402


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
async def client(storage):
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [x] **Step 4: `app/modules/materials/models.py`** (phần Asset; Source và Chunk sẽ thêm ở Task 16)

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class AssetKind(str, enum.Enum):
    pdf = "pdf"
    video = "video"
    submission = "submission"
    certificate = "certificate"
    image = "image"


class Asset(IdMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[AssetKind] = mapped_column(SAEnum(AssetKind, name="asset_kind"))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [x] **Step 5: Thêm cột video vào `Lesson`** (`app/modules/courses/models.py`)
  - Thêm vào class `Lesson`, ngay dưới `duration_sec`:

```python
    video_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
```

  - Trong `app/modules/courses/schemas.py`:
    - Thêm vào `LessonUpdate`: `video_asset_id: uuid.UUID | None = None`
    - Thêm vào `LessonOut`: `video_asset_id: uuid.UUID | None`

- [x] **Step 6: Đăng ký model và sinh migration**
  - Thêm vào `app/models_registry.py`: `from app.modules.materials import models as materials_models  # noqa: F401`

Run: `uv run alembic revision --autogenerate -m "assets"` rồi `uv run alembic upgrade head`
Expected: migration tạo bảng `assets`, enum `asset_kind`, và thêm cột `lessons.video_asset_id` kèm FK

- [x] **Step 7: Index cho `lessons.video_asset_id` (migration riêng)**
  - Trong `app/modules/courses/models.py`, sửa cột vừa thêm ở Step 5 thành:

```python
    video_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"),
                                                            index=True)
```

Run: `uv run alembic revision --autogenerate -m "lesson video index"` rồi `uv run alembic upgrade head`
Expected: migration mới (revises `<rev>_assets`) chỉ có `op.create_index(op.f('ix_lessons_video_asset_id'), 'lessons', ['video_asset_id'], unique=False)`, downgrade là `op.drop_index(...)`

- [x] **Step 8: Viết test hỏng trước — `tests/test_uploads.py`**

```python
import pytest

from app.core.storage import STAGING_PREFIX
from tests.helpers import API, make_published_course, make_student, make_teacher

PDF = b"%PDF-1.7\n" + b"0" * 100
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
EXE = b"MZ\x90\x00" + b"\x00" * 100
MB = 1024 * 1024


async def _presign(client, headers, kind="pdf", mime="application/pdf", size=1000):
    return await client.post(f"{API}/uploads/presign", json={"kind": kind, "mime": mime, "size": size},
                             headers=headers)


def _staging(presign_response) -> str:
    """Key mà URL presign cho phép PUT (luôn là key tạm)."""
    return presign_response.json()["put_url"].removeprefix("memory://put/")


def _final(presign_response) -> str:
    return _staging(presign_response).removeprefix(STAGING_PREFIX)


async def _complete(client, presign_response, headers):
    return await client.post(f"{API}/uploads/{presign_response.json()['asset_id']}/complete", headers=headers)


async def _upload(client, storage, headers, data, kind="pdf", mime="application/pdf"):
    r = await _presign(client, headers, kind, mime, len(data))
    assert r.status_code == 200, r.text
    storage.client_put(r.json()["put_url"], data, mime)
    return r, await _complete(client, r, headers)


async def test_presign_returns_staging_url_and_asset(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv)
    assert r.status_code == 200
    assert r.json()["asset_id"] and _staging(r).startswith(f"{STAGING_PREFIX}pdf/") and _final(r).endswith(".pdf")


async def test_presign_rejects_mime_not_allowed_for_kind(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, kind="pdf", mime="image/png")
    assert (r.status_code, r.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")


async def test_presign_rejects_declared_size_over_limit(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, size=60 * MB)
    assert (r.status_code, r.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


@pytest.mark.parametrize(("kind", "mime", "limit"), [("pdf", "application/pdf", 50 * MB),
                                                     ("video", "video/mp4", 500 * MB)])
async def test_presign_declared_size_boundary(client, kind, mime, limit):
    _, gv = await make_teacher(client)
    assert (await _presign(client, gv, kind, mime, size=limit)).status_code == 200
    over = await _presign(client, gv, kind, mime, size=limit + 1)
    assert (over.status_code, over.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


async def test_submission_declared_size_boundary(client):
    _, sv = await make_student(client)
    assert (await _presign(client, sv, "submission", "text/plain", size=20 * MB)).status_code == 200
    over = await _presign(client, sv, "submission", "text/plain", size=20 * MB + 1)
    assert (over.status_code, over.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")


@pytest.mark.parametrize(("kind", "mime"), [("pdf", "application/pdf"), ("video", "video/mp4")])
async def test_student_cannot_presign_course_material(client, kind, mime):
    _, sv = await make_student(client)
    r = await _presign(client, sv, kind, mime)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_complete_without_upload(client):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv)
    done = await _complete(client, r, gv)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "UPLOAD_MISSING")


async def test_complete_valid_pdf_moves_staging_to_final(client, storage):
    _, gv = await make_teacher(client)
    r, done = await _upload(client, storage, gv, PDF)
    assert done.status_code == 200
    assert done.json()["verified_at"] is not None and done.json()["size_bytes"] == len(PDF)
    assert _staging(r) not in storage.objects
    assert storage.objects[_final(r)] == PDF and storage.mimes[_final(r)] == "application/pdf"


async def test_reput_after_verify_cannot_touch_final_object(client, storage):
    _, gv = await make_teacher(client)
    r, done = await _upload(client, storage, gv, PDF)
    assert done.status_code == 200
    # URL presign chỉ trỏ vào key tạm: PUT lại (ví dụ thay bằng file .exe) không chạm tới key chính thức
    assert r.json()["put_url"].startswith(f"memory://put/{STAGING_PREFIX}")
    storage.client_put(r.json()["put_url"], EXE, "application/pdf")
    again = await _complete(client, r, gv)
    assert again.status_code == 200 and again.json()["verified_at"] == done.json()["verified_at"]
    assert storage.objects[_final(r)] == PDF


async def test_reput_during_complete_is_verified_on_final_copy(client, storage):
    _, gv = await make_teacher(client)
    r = await _presign(client, gv, size=len(PDF))
    storage.client_put(r.json()["put_url"], PDF, "application/pdf")
    # client đổi file ở key tạm ngay sau lúc stat, trước lúc copy
    storage.on_copy = lambda: storage.client_put(r.json()["put_url"], EXE, "application/pdf")
    done = await _complete(client, r, gv)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")
    assert _staging(r) not in storage.objects and _final(r) not in storage.objects


async def test_complete_rejects_renamed_executable(client, storage):
    _, gv = await make_teacher(client)
    r, done = await _upload(client, storage, gv, EXE)
    assert (done.status_code, done.json()["error"]["code"]) == (400, "INVALID_FILE_TYPE")
    assert _staging(r) not in storage.objects and _final(r) not in storage.objects
    assert (await _complete(client, r, gv)).status_code == 404


async def test_complete_rejects_actual_size_over_limit(client, storage):
    _, sv = await make_student(client)
    big = b"a" * (20 * MB + 1)
    r = await _presign(client, sv, kind="submission", mime="text/plain", size=100)
    storage.client_put(r.json()["put_url"], big, "text/plain")
    done = await _complete(client, r, sv)
    assert (done.status_code, done.json()["error"]["code"]) == (413, "FILE_TOO_LARGE")
    assert _staging(r) not in storage.objects and _final(r) not in storage.objects
    assert (await _complete(client, r, sv)).status_code == 404


async def test_other_user_cannot_complete(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    r = await _presign(client, gv)
    storage.client_put(r.json()["put_url"], PDF, "application/pdf")
    done = await _complete(client, r, sv)
    assert done.status_code == 404


async def test_attach_video_and_stream_url(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    r, done = await _upload(client, storage, gv, MP4, kind="video", mime="video/mp4")
    assert done.status_code == 200
    patch = await client.patch(f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]},
                               headers=gv)
    assert patch.status_code == 200 and patch.json()["video_asset_id"] == r.json()["asset_id"]

    denied = await client.get(f"{API}/lessons/{lesson['id']}/video", headers=sv)
    assert denied.status_code == 403
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    ok = await client.get(f"{API}/lessons/{lesson['id']}/video", headers=sv)
    assert ok.status_code == 200 and ok.json()["url"] == f"memory://get/{_final(r)}"
    assert storage.signed_gets[_final(r)] == {"response-content-type": "video/mp4"}


async def test_attach_pdf_as_video_is_rejected(client, storage):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r, _ = await _upload(client, storage, gv, PDF)
    patch = await client.patch(f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]},
                               headers=gv)
    assert (patch.status_code, patch.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_attach_other_teachers_video_is_rejected(client, storage):
    _, gv = await make_teacher(client)
    _, gv2 = await make_teacher(client, email="gv2@x.com")
    _, _, lesson = await make_published_course(client, gv)
    r, done = await _upload(client, storage, gv2, MP4, kind="video", mime="video/mp4")
    assert done.status_code == 200
    patch = await client.patch(f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]},
                               headers=gv)
    assert (patch.status_code, patch.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_attach_unverified_video_is_rejected(client):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await _presign(client, gv, kind="video", mime="video/mp4")
    patch = await client.patch(f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]},
                               headers=gv)
    assert (patch.status_code, patch.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_student_cannot_patch_lesson(client, storage):
    _, gv = await make_teacher(client)
    _, sv = await make_student(client)
    course, _, lesson = await make_published_course(client, gv)
    r, _ = await _upload(client, storage, gv, MP4, kind="video", mime="video/mp4")
    await client.post(f"{API}/courses/{course['id']}/enroll", headers=sv)
    patch = await client.patch(f"{API}/lessons/{lesson['id']}", json={"video_asset_id": r.json()["asset_id"]},
                               headers=sv)
    assert (patch.status_code, patch.json()["error"]["code"]) == (403, "FORBIDDEN")
```

  - `tests/test_storage.py`: ký URL bằng `MinioStorage` thật mà không cần MinIO chạy (region cố định nên ký cục bộ)

```python
from urllib.parse import parse_qs, urlsplit

from app.core.config import Settings
from app.core.storage import MinioStorage, download_headers, staging_key

# Ký URL là tính toán cục bộ (region cố định), không cần MinIO chạy


def _storage() -> MinioStorage:
    return MinioStorage(Settings(minio_endpoint="minio:9000", minio_public_endpoint="files.example.com"))


def test_download_headers():
    assert download_headers("application/pdf") == {"response-content-type": "application/pdf"}
    assert download_headers("text/plain", "bai.txt") == {
        "response-content-type": "text/plain",
        "response-content-disposition": 'attachment; filename="bai.txt"'}


async def test_presign_get_signs_public_host_with_content_type():
    url = await _storage().presign_get("video/u/a.mp4", "video/mp4")
    parts = urlsplit(url)
    assert parts.netloc == "files.example.com" and parts.path == "/lms/video/u/a.mp4"
    assert parse_qs(parts.query)["response-content-type"] == ["video/mp4"]


async def test_presign_put_targets_given_staging_key():
    url = await _storage().presign_put(staging_key("pdf/u/a.pdf"))
    parts = urlsplit(url)
    assert parts.netloc == "files.example.com" and parts.path == "/lms/staging/pdf/u/a.pdf"
```

- [x] **Step 9: Chạy test**

Run: `uv run pytest tests/test_uploads.py tests/test_storage.py -v`
Expected: `test_uploads.py` FAIL (404 vì chưa có route `/uploads/presign`); `test_storage.py` PASS (storage.py đã có từ Step 1)

- [x] **Step 10: `app/modules/materials/schemas.py`**

```python
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.materials.models import AssetKind


class PresignIn(BaseModel):
    kind: Literal["pdf", "video", "submission", "image"]
    mime: str = Field(max_length=100)
    size: int = Field(gt=0)


class PresignOut(BaseModel):
    asset_id: uuid.UUID
    put_url: str


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: AssetKind
    mime: str
    size_bytes: int
    verified_at: datetime | None


class UrlOut(BaseModel):
    url: str
```

- [x] **Step 11: `app/modules/materials/assets.py`**
  - `pdf`/`video` chỉ giảng viên đã duyệt hoặc admin được presign (`require_staff`); học viên nhận `403 FORBIDDEN`.
  - `complete` khóa dòng asset (`FOR UPDATE`), copy `staging/<key>` sang key chính thức, rồi kiểm tra kích thước và magic bytes trên bản ở key chính thức (client không ghi được vào đó). Hỏng thì xóa cả hai object và dòng asset. Thành công thì commit rồi mới xóa key tạm.

```python
import uuid

import filetype
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_staff
from app.core.errors import AppError, not_found
from app.core.storage import Storage, staging_key
from app.core.time import utcnow
from app.modules.auth.models import Role, User
from app.modules.materials.models import Asset, AssetKind
from app.modules.materials.schemas import PresignIn, PresignOut

MB = 1024 * 1024
SIZE_LIMITS = {AssetKind.pdf: 50 * MB, AssetKind.video: 500 * MB,
               AssetKind.submission: 20 * MB, AssetKind.image: 5 * MB}
ALLOWED_MIME = {
    AssetKind.pdf: {"application/pdf"},
    AssetKind.video: {"video/mp4"},
    AssetKind.submission: {"application/pdf", "text/plain"},
    AssetKind.image: {"image/png", "image/jpeg", "image/webp"},
}
STAFF_ONLY_KINDS = {AssetKind.pdf, AssetKind.video}  # tài liệu và video bài học chỉ giảng viên/admin upload
EXTENSIONS = {"application/pdf": "pdf", "video/mp4": "mp4", "text/plain": "txt",
              "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _too_large() -> AppError:
    return AppError("FILE_TOO_LARGE", "File vượt quá dung lượng cho phép", 413)


def _invalid_type() -> AppError:
    return AppError("INVALID_FILE_TYPE", "Định dạng file không hợp lệ", 400)


def mime_matches(declared: str, head: bytes) -> bool:
    """So magic bytes của 2KB đầu với mime đã khai báo. Text thuần thì không có magic bytes."""
    guessed = filetype.guess(head)
    if declared == "text/plain":
        return guessed is None and b"\x00" not in head
    return guessed is not None and guessed.mime == declared


async def create_presigned_upload(db: AsyncSession, storage: Storage, user: User, data: PresignIn) -> PresignOut:
    kind = AssetKind(data.kind)
    if kind in STAFF_ONLY_KINDS:
        await require_staff(user)
    if data.mime not in ALLOWED_MIME[kind]:
        raise _invalid_type()
    if data.size > SIZE_LIMITS[kind]:
        raise _too_large()
    key = f"{kind.value}/{user.id}/{uuid.uuid4().hex}.{EXTENSIONS[data.mime]}"
    asset = Asset(owner_id=user.id, kind=kind, storage_key=key, mime=data.mime, size_bytes=0)
    db.add(asset)
    await db.commit()
    # Trình duyệt chỉ nhận URL ghi vào key tạm; key chính thức chỉ có server ghi sau khi kiểm tra xong.
    return PresignOut(asset_id=asset.id, put_url=await storage.presign_put(staging_key(key)))


async def complete_upload(db: AsyncSession, storage: Storage, user: User, asset_id: uuid.UUID) -> Asset:
    # Khóa dòng asset để các lần complete đồng thời chạy tuần tự
    asset = await db.get(Asset, asset_id, with_for_update=True)
    if asset is None or asset.owner_id != user.id:
        raise not_found("File")
    if asset.verified_at is not None:
        return asset
    staged = staging_key(asset.storage_key)
    size = await storage.stat_size(staged)
    if size is None:
        raise AppError("UPLOAD_MISSING", "Chưa tìm thấy file đã upload", 400)

    async def reject(err: AppError, *keys: str) -> None:
        for key in keys:
            await storage.remove(key)
        await db.delete(asset)
        await db.commit()
        raise err

    limit = SIZE_LIMITS[asset.kind]
    if size > limit:
        await reject(_too_large(), staged)
    # Copy trước rồi mới kiểm tra bản ở key chính thức (client không ghi được vào đó): tránh việc client
    # PUT lại vào key tạm giữa lúc kiểm tra và lúc copy.
    await storage.copy(staged, asset.storage_key)
    size = await storage.stat_size(asset.storage_key)
    if size is None or size > limit:
        await reject(_too_large(), staged, asset.storage_key)
    if not mime_matches(asset.mime, await storage.read_head(asset.storage_key)):
        await reject(_invalid_type(), staged, asset.storage_key)
    asset.size_bytes = size
    asset.verified_at = utcnow()
    await db.commit()
    # Xóa key tạm sau khi commit: nếu commit lỗi thì vẫn còn file tạm để complete lại
    await storage.remove(staged)
    return asset


async def require_verified_asset(db: AsyncSession, asset_id: uuid.UUID, user: User, kind: AssetKind) -> Asset:
    asset = await db.get(Asset, asset_id)
    if (asset is None or asset.kind != kind or asset.verified_at is None
            or (asset.owner_id != user.id and user.role != Role.admin)):
        raise AppError("INVALID_ASSET", "File không hợp lệ hoặc chưa upload xong", 400)
    return asset
```

- [x] **Step 12: `app/modules/materials/router.py`**

```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.core.storage import Storage, get_storage
from app.modules.auth.models import User
from app.modules.enrollment.service import ensure_lesson_access
from app.modules.materials import assets
from app.modules.materials.models import Asset
from app.modules.materials.schemas import AssetOut, PresignIn, PresignOut, UrlOut

router = APIRouter(prefix="/api/v1", tags=["materials"])


@router.post("/uploads/presign", response_model=PresignOut)
async def presign(data: PresignIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                  storage: Storage = Depends(get_storage)):
    return await assets.create_presigned_upload(db, storage, user, data)


@router.post("/uploads/{asset_id}/complete", response_model=AssetOut)
async def complete(asset_id: uuid.UUID, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db), storage: Storage = Depends(get_storage)):
    return await assets.complete_upload(db, storage, user, asset_id)


@router.get("/lessons/{lesson_id}/video", response_model=UrlOut)
async def lesson_video(lesson_id: uuid.UUID, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db), storage: Storage = Depends(get_storage)):
    lesson, _ = await ensure_lesson_access(db, lesson_id, user)
    asset = await db.get(Asset, lesson.video_asset_id) if lesson.video_asset_id else None
    if asset is None:
        raise not_found("Video")
    return UrlOut(url=await storage.presign_get(asset.storage_key, asset.mime))
```

- [x] **Step 13: Kiểm tra video khi PATCH bài học** (`app/modules/courses/router.py`): thay hàm `update_lesson` bằng:

```python
@router.patch("/lessons/{lesson_id}", response_model=LessonOut)
async def update_lesson(lesson_id: uuid.UUID, data: LessonUpdate, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)):
    from app.modules.materials.assets import require_verified_asset
    from app.modules.materials.models import AssetKind

    lesson, _ = await service.get_owned_lesson(db, lesson_id, user)
    if data.video_asset_id is not None:
        await require_verified_asset(db, data.video_asset_id, user, AssetKind.video)
    return await service.update_lesson(db, lesson, data)
```

- [x] **Step 14: Gắn router vào `app/main.py`**
  - Import: `from app.modules.materials.router import router as materials_router`
  - Dưới `# routers`: `app.include_router(materials_router)`

- [x] **Step 15: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: PASS hết

- [x] **Step 16: Commit**

```bash
git add . && git commit -m "feat(materials): presigned uploads with magic-byte verification, lesson video"
```

---

### Task 15: Bảng jobs, chống tạo job trùng và hàng đợi arq

**Files:**
- Create: `backend/app/modules/jobs/__init__.py`, `backend/app/modules/jobs/models.py`, `backend/app/modules/jobs/service.py`, `backend/app/modules/jobs/queue.py`, `backend/app/modules/jobs/router.py`
- Modify: `backend/app/models_registry.py`, `backend/app/main.py`, `backend/tests/fakes.py`, `backend/tests/conftest.py`
- Create (sinh bằng lệnh): `backend/alembic/versions/<rev>_jobs.py`
- Test: `backend/tests/test_jobs.py`

- [x] **Step 1: `app/modules/jobs/models.py`**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin

ACTIVE_JOB_PREDICATE = "status IN ('pending', 'processing')"


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class Job(IdMixin, TimestampMixin, Base):
    """type quyết định ref_id trỏ tới đâu: ingest_pdf/ingest_video → sources.id, quiz_gen → lessons.id,
    grade_submission → submissions.id (ref_version = submissions.version)."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("uq_active_job", "type", "ref_id", "ref_version", unique=True,
              postgresql_where=text(ACTIVE_JOB_PREDICATE)),
    )

    type: Mapped[str] = mapped_column(String(50))
    ref_id: Mapped[uuid.UUID] = mapped_column()
    ref_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, name="job_status"), default=JobStatus.pending)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [x] **Step 2: Đăng ký model và sinh migration**
  - Thêm vào `app/models_registry.py`: `from app.modules.jobs import models as jobs_models  # noqa: F401`

Run: `uv run alembic revision --autogenerate -m "jobs"`
Mở file migration và kiểm tra có dòng `op.create_index('uq_active_job', ..., unique=True, postgresql_where=sa.text("status IN ('pending', 'processing')"))`.

Run tiếp: `uv run alembic upgrade head`

- [x] **Step 3: `app/modules/jobs/queue.py`**

```python
from functools import lru_cache
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.modules.jobs.models import Job


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> None: ...


class ArqQueue:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def enqueue(self, job: Job) -> None:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
        # Tên hàm trong worker trùng với job.type; _job_id giúp arq tự bỏ qua nếu enqueue trùng
        await self._pool.enqueue_job(job.type, str(job.id), _job_id=str(job.id))


@lru_cache
def get_queue() -> JobQueue:
    return ArqQueue(get_settings().redis_url)
```

- [x] **Step 4: Thêm `RecordingQueue` vào cuối `tests/fakes.py`**

```python
class RecordingQueue:
    """Queue giả. Kiểm tra luôn luật 'job phải được commit trước khi enqueue'."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, object]] = []

    async def enqueue(self, job) -> None:
        from app.core.db import SessionLocal
        from app.modules.jobs.models import Job

        async with SessionLocal() as s:
            assert await s.get(Job, job.id) is not None, "Job phải được commit trước khi enqueue"
        self.jobs.append((job.type, job.ref_id))
```

- [x] **Step 5: Cập nhật `tests/conftest.py`**: thêm fixture `queue` và override trong `client`

```python
from app.modules.jobs.queue import get_queue  # noqa: E402
from tests.fakes import RecordingQueue  # noqa: E402


@pytest.fixture
def queue():
    return RecordingQueue()
```

Thay fixture `client` bằng:

```python
@pytest.fixture
async def client(storage, queue):
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_queue] = lambda: queue
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [x] **Step 6: Viết test hỏng trước — `tests/test_jobs.py`**

```python
import asyncio
import uuid

from app.core.db import SessionLocal
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_and_enqueue, create_job
from tests.fakes import RecordingQueue
from tests.helpers import API, make_student


async def test_active_job_is_deduplicated(db):
    ref = uuid.uuid4()
    j1, created1 = await create_job(db, "quiz_gen", ref)
    await db.commit()
    j2, created2 = await create_job(db, "quiz_gen", ref)
    await db.commit()
    assert created1 is True and created2 is False
    assert j1.id == j2.id


async def test_new_ref_version_creates_new_job(db):
    ref = uuid.uuid4()
    j1, _ = await create_job(db, "grade_submission", ref, ref_version=1)
    await db.commit()
    j2, created = await create_job(db, "grade_submission", ref, ref_version=2)
    await db.commit()
    assert created is True and j1.id != j2.id


async def test_finished_job_allows_a_new_one(db):
    ref = uuid.uuid4()
    j1, _ = await create_job(db, "ingest_pdf", ref)
    j1.status = JobStatus.done
    await db.commit()
    j2, created = await create_job(db, "ingest_pdf", ref)
    await db.commit()
    assert created is True and j2.id != j1.id


async def test_concurrent_creates_produce_one_job():
    ref = uuid.uuid4()

    async def attempt() -> bool:
        async with SessionLocal() as s:
            _, created = await create_job(s, "quiz_gen", ref)
            await s.commit()
            return created

    results = await asyncio.gather(attempt(), attempt())
    assert sorted(results) == [False, True]


async def test_create_and_enqueue_commits_first_and_enqueues_once(db):
    queue = RecordingQueue()
    ref = uuid.uuid4()
    job = await create_and_enqueue(db, queue, "ingest_pdf", ref)
    again = await create_and_enqueue(db, queue, "ingest_pdf", ref)
    assert again.id == job.id
    assert queue.jobs == [("ingest_pdf", ref)]


async def test_get_job_endpoint(client, db):
    _, sv = await make_student(client)
    job = Job(type="ingest_pdf", ref_id=uuid.uuid4())
    db.add(job)
    await db.commit()
    r = await client.get(f"{API}/jobs/{job.id}", headers=sv)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert (await client.get(f"{API}/jobs/{uuid.uuid4()}", headers=sv)).status_code == 404
    assert (await client.get(f"{API}/jobs/{job.id}")).status_code == 401
```

- [x] **Step 7: Chạy test**

Run: `uv run pytest tests/test_jobs.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.modules.jobs.service'`

- [x] **Step 8: `app/modules/jobs/service.py`**

```python
import uuid

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.models import ACTIVE_JOB_PREDICATE, Job, JobStatus
from app.modules.jobs.queue import JobQueue

ACTIVE = (JobStatus.pending, JobStatus.processing)


async def create_job(db: AsyncSession, type_: str, ref_id: uuid.UUID, ref_version: int = 0) -> tuple[Job, bool]:
    """Tạo job nếu chưa có job đang chạy cho (type, ref_id, ref_version). Chưa commit — caller tự commit.

    Nhờ partial unique index uq_active_job, hai request đồng thời vẫn chỉ tạo được một job.
    """
    for _ in range(2):  # lặp lại một lần phòng khi job cũ vừa kết thúc giữa hai câu lệnh
        stmt = (
            pg_insert(Job)
            .values(id=uuid.uuid4(), type=type_, ref_id=ref_id, ref_version=ref_version,
                    status=JobStatus.pending, attempts=0)
            .on_conflict_do_nothing(index_elements=["type", "ref_id", "ref_version"],
                                    index_where=text(ACTIVE_JOB_PREDICATE))
            .returning(Job.id)
        )
        new_id = await db.scalar(stmt)
        if new_id is not None:
            return await db.get(Job, new_id), True
        existing = await db.scalar(select(Job).where(
            Job.type == type_, Job.ref_id == ref_id, Job.ref_version == ref_version, Job.status.in_(ACTIVE)))
        if existing is not None:
            return existing, False
    raise RuntimeError("Không tạo được job")


async def create_and_enqueue(db: AsyncSession, queue: JobQueue, type_: str, ref_id: uuid.UUID,
                             ref_version: int = 0) -> Job:
    """Commit mọi thay đổi đang chờ trong session cùng với job, rồi mới đẩy lên hàng đợi."""
    job, created = await create_job(db, type_, ref_id, ref_version)
    await db.commit()
    if created:
        await queue.enqueue(job)
    return job
```

- [x] **Step 9: `app/modules/jobs/router.py`**

```python
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.modules.auth.models import User
from app.modules.jobs.models import Job, JobStatus

router = APIRouter(prefix="/api/v1", tags=["jobs"])


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: JobStatus
    attempts: int
    error_msg: str | None
    finished_at: datetime | None


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if job is None:
        raise not_found("Job")
    return job
```

- [x] **Step 10: Gắn router vào `app/main.py`**
  - Import: `from app.modules.jobs.router import router as jobs_router`
  - Dưới `# routers`: `app.include_router(jobs_router)`

- [x] **Step 11: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: PASS hết. Nếu `test_concurrent_creates_produce_one_job` báo `there is no unique or exclusion constraint matching the ON CONFLICT specification`, nghĩa là predicate trong `index_where` không khớp với index. Kiểm tra migration dùng đúng chuỗi `ACTIVE_JOB_PREDICATE`.

- [x] **Step 12: Commit**

```bash
git add . && git commit -m "feat(jobs): jobs table with partial unique index, dedup create, arq queue"
```

---

### Task 16: Model Source, SourcePage, Chunk (vector + full-text)

**Files:**
- Modify: `backend/app/modules/materials/models.py`
- Create: `backend/tests/factories.py`
- Create (sinh bằng lệnh): `backend/alembic/versions/<rev>_sources_chunks.py`
- Test: `backend/tests/test_chunks_db.py`

- [ ] **Step 1: Thêm vào `app/modules/materials/models.py`**
  - Sửa các dòng import thành:

```python
import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.db import Base, IdMixin, TimestampMixin

EMBED_DIM = get_settings().embed_dim
```

  - Thêm các class sau vào cuối file:

```python
class SourceType(str, enum.Enum):
    pdf = "pdf"
    video = "video"


class SourceStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ExtractionMethod(str, enum.Enum):
    text = "text"
    vision = "vision"


class Source(IdMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"))
    type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"))
    status: Mapped[SourceStatus] = mapped_column(SAEnum(SourceStatus, name="source_status"),
                                                 default=SourceStatus.pending)
    error_msg: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourcePage(Base):
    __tablename__ = "source_pages"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    page_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(SAEnum(ExtractionMethod, name="extraction_method"))
    markdown: Mapped[str] = mapped_column(Text)


class Chunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_scope", "course_id", "lesson_id", "embedding_model"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    lesson_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    heading_path: Mapped[str] = mapped_column(String(500), default="")
    page_no: Mapped[int | None] = mapped_column(Integer)
    start_sec: Mapped[float | None] = mapped_column(Float)
    end_sec: Mapped[float | None] = mapped_column(Float)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, immutable_unaccent(coalesce(content, '')))", persisted=True),
    )
```

- [ ] **Step 2: Sinh migration và upgrade**

Run: `uv run alembic revision --autogenerate -m "sources and chunks"`
Mở file migration và kiểm tra 3 điều:
  1. Cột `tsv` có `sa.Computed("to_tsvector('simple'::regconfig, immutable_unaccent(coalesce(content, '')))", persisted=True)`.
  2. Cột `embedding` có dạng `pgvector.sqlalchemy.vector.VECTOR(dim=768)`.
  3. Có index `ix_chunks_embedding_hnsw` với `postgresql_using='hnsw'` và `postgresql_ops={'embedding': 'vector_cosine_ops'}`.

Run tiếp: `uv run alembic upgrade head`
Expected: không lỗi. Nếu báo `generation expression is not immutable`, kiểm tra migration 0001 đã chạy và hàm có `IMMUTABLE`.

- [ ] **Step 3: `tests/factories.py`** (tạo dữ liệu thẳng trong DB, không qua API)

```python
import uuid

from app.core.security import hash_password
from app.core.time import utcnow
from app.modules.auth.models import Role, TeacherStatus, User
from app.modules.courses.models import Course, CourseStatus, Lesson, Section
from app.modules.materials.models import Asset, AssetKind, Chunk, Source, SourceType


async def make_user(db, role: Role = Role.teacher) -> User:
    user = User(email=f"{uuid.uuid4().hex[:8]}@x.com", password_hash=hash_password("password123"),
                full_name="Người dùng", role=role,
                teacher_status=TeacherStatus.approved if role == Role.teacher else None)
    db.add(user)
    await db.commit()
    return user


async def make_lesson(db, teacher: User) -> tuple[Course, Lesson]:
    course = Course(teacher_id=teacher.id, title="Khóa test", slug=f"khoa-{uuid.uuid4().hex[:6]}",
                    status=CourseStatus.published)
    db.add(course)
    await db.flush()
    section = Section(course_id=course.id, title="Chương 1", position=1)
    db.add(section)
    await db.flush()
    lesson = Lesson(section_id=section.id, title="Bài 1", position=1)
    db.add(lesson)
    await db.commit()
    return course, lesson


async def make_pdf_source(db, storage, owner: User, lesson: Lesson, pdf_bytes: bytes) -> Source:
    key = f"pdf/{owner.id}/{uuid.uuid4().hex}.pdf"
    await storage.put(key, pdf_bytes, "application/pdf")
    asset = Asset(owner_id=owner.id, kind=AssetKind.pdf, storage_key=key, mime="application/pdf",
                  size_bytes=len(pdf_bytes), verified_at=utcnow())
    db.add(asset)
    await db.flush()
    source = Source(lesson_id=lesson.id, asset_id=asset.id, type=SourceType.pdf)
    db.add(source)
    await db.commit()
    return source


def unit_vector(index: int, dim: int = 768) -> list[float]:
    v = [0.0] * dim
    v[index] = 1.0
    return v


async def add_chunk(db, source: Source, course: Course, lesson: Lesson, content: str,
                    embedding: list[float]) -> Chunk:
    chunk = Chunk(source_id=source.id, course_id=course.id, lesson_id=lesson.id, content=content,
                  heading_path="", page_no=1, token_count=len(content.split()),
                  embedding_model="fake-768", embedding=embedding)
    db.add(chunk)
    await db.commit()
    return chunk
```

- [ ] **Step 4: Viết test hỏng trước — `tests/test_chunks_db.py`**

```python
from sqlalchemy import func, select, text

from app.modules.materials.models import Chunk, ExtractionMethod, Source, SourcePage
from tests.factories import add_chunk, make_lesson, make_pdf_source, make_user, unit_vector
from tests.fakes import InMemoryStorage

FTS = text("SELECT count(*) FROM chunks "
           "WHERE tsv @@ websearch_to_tsquery('simple', immutable_unaccent(:q))")


async def _setup(db):
    teacher = await make_user(db)
    course, lesson = await make_lesson(db, teacher)
    source = await make_pdf_source(db, InMemoryStorage(), teacher, lesson, b"%PDF-1.7")
    return course, lesson, source


async def test_full_text_matches_without_diacritics(db):
    course, lesson, source = await _setup(db)
    await add_chunk(db, source, course, lesson, "Tìm kiếm nhị phân chia đôi khoảng tìm", unit_vector(0))
    assert await db.scalar(FTS, {"q": "tim kiem nhi phan"}) == 1
    assert await db.scalar(FTS, {"q": "Tìm Kiếm"}) == 1
    assert await db.scalar(FTS, {"q": "đồ thị"}) == 0


async def test_hnsw_index_can_serve_nearest_neighbour_query(db):
    course, lesson, source = await _setup(db)
    for i in range(3):
        await add_chunk(db, source, course, lesson, f"đoạn {i}", unit_vector(i))
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = (await db.execute(
        text("EXPLAIN SELECT id FROM chunks ORDER BY embedding <=> CAST(:v AS vector) LIMIT 3"),
        {"v": str(unit_vector(1))},
    )).scalars().all()
    await db.rollback()
    assert any("ix_chunks_embedding_hnsw" in line for line in plan), plan


async def test_deleting_source_cascades_pages_and_chunks(db):
    course, lesson, source = await _setup(db)
    db.add(SourcePage(source_id=source.id, page_no=1, extraction_method=ExtractionMethod.text, markdown="x"))
    await db.commit()
    await add_chunk(db, source, course, lesson, "nội dung", unit_vector(0))
    await db.execute(Source.__table__.delete().where(Source.id == source.id))
    await db.commit()
    assert await db.scalar(select(func.count(Chunk.id))) == 0
    assert await db.scalar(select(func.count()).select_from(SourcePage)) == 0
```

- [ ] **Step 5: Chạy test**

Run: `uv run pytest tests/test_chunks_db.py -v`
Expected: PASS cả 3 test (model và migration đã có từ Step 1–2). Nếu `test_full_text_matches_without_diacritics` hỏng, nghĩa là `tsv` không đi qua `immutable_unaccent`: kiểm tra lại biểu thức `Computed`.

- [ ] **Step 6: Commit**

```bash
git add . && git commit -m "feat(materials): sources, pages, chunks with pgvector hnsw and unaccented tsvector"
```

---

### Task 17: Chunker (chia markdown thành chunk)

**Files:**
- Create: `backend/app/ingestion/__init__.py`, `backend/app/ingestion/chunker.py`
- Test: `backend/tests/test_chunker.py`

- [ ] **Step 1: Viết test hỏng trước — `tests/test_chunker.py`**

```python
from app.ingestion.chunker import PageText, chunk_pages, count_tokens


def words(n: int, w: str = "tu") -> str:
    return " ".join([w] * n)


def test_count_tokens_estimate():
    assert count_tokens("") == 0
    assert count_tokens(words(10)) == 14


def test_short_document_is_one_chunk_with_heading_path():
    md = "# Chương 1\n\n## Tìm kiếm nhị phân\n\n" + words(50)
    [chunk] = chunk_pages([PageText(1, md, "text")])
    assert chunk.heading_path == "Chương 1 > Tìm kiếm nhị phân"
    assert chunk.page_no == 1
    assert words(50) in chunk.content


def test_new_heading_starts_new_chunk_when_buffer_is_big_enough():
    md = "# A\n\n" + words(120) + "\n\n# B\n\n" + words(120)
    chunks = chunk_pages([PageText(1, md, "text")])
    assert [c.heading_path for c in chunks] == ["A", "B"]


def test_long_text_splits_with_overlap():
    paragraphs = [words(20, f"p{i}") for i in range(10)]  # mỗi đoạn 28 token
    chunks = chunk_pages([PageText(1, "\n\n".join(paragraphs), "text")], max_tokens=100, overlap_tokens=30)
    assert len(chunks) > 1
    for prev, nxt in zip(chunks, chunks[1:]):
        assert prev.content.split("\n\n")[-1] == nxt.content.split("\n\n")[0]  # có đoạn gối đầu
    for c in chunks:
        assert c.token_count <= 100 + 30


def test_chunk_page_is_page_of_first_paragraph():
    chunks = chunk_pages([PageText(1, words(60, "a"), "text"), PageText(2, words(60, "b"), "text")],
                         max_tokens=100, overlap_tokens=0)
    assert [c.page_no for c in chunks] == [1, 2]


def test_oversized_paragraph_is_hard_split():
    chunks = chunk_pages([PageText(1, words(300), "text")], max_tokens=100, overlap_tokens=0)
    assert len(chunks) >= 4
    assert all(c.token_count <= 100 for c in chunks)


def test_empty_pages_give_no_chunks():
    assert chunk_pages([PageText(1, "   \n\n  ", "text")]) == []
```

- [ ] **Step 2: Chạy test**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.ingestion'`

- [ ] **Step 3: `app/ingestion/chunker.py`** (`app/ingestion/__init__.py` để trống)

```python
import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
TOKENS_PER_WORD = 1.4  # ước lượng cho tiếng Việt (mỗi âm tiết là một "từ"), đủ dùng để chia chunk


def count_tokens(text: str) -> int:
    n = len(text.split())
    return round(n * TOKENS_PER_WORD) if n else 0


@dataclass(frozen=True)
class PageText:
    page_no: int
    markdown: str
    method: str  # "text" | "vision"


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    heading_path: str
    page_no: int
    token_count: int


@dataclass(frozen=True)
class _Para:
    text: str
    page_no: int
    tokens: int
    is_heading: bool = False


def _hard_split(text: str, max_tokens: int) -> list[str]:
    words = text.split()
    step = max(1, int(max_tokens / TOKENS_PER_WORD))
    return [" ".join(words[i:i + step]) for i in range(0, len(words), step)]


def chunk_pages(pages: list[PageText], max_tokens: int = 700, overlap_tokens: int = 100,
                flush_min_tokens: int = 150) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    buf: list[_Para] = []
    headings: list[tuple[int, str]] = []
    buf_heading = ""

    def buf_tokens() -> int:
        return sum(p.tokens for p in buf)

    def current_path() -> str:
        return " > ".join(title for _, title in headings)

    def flush(keep_overlap: bool) -> None:
        nonlocal buf
        if not buf:
            return
        content = "\n\n".join(p.text for p in buf)
        chunks.append(ChunkDraft(content, buf_heading, buf[0].page_no, count_tokens(content)))
        kept: list[_Para] = []
        if keep_overlap:
            total = 0
            for p in reversed(buf):
                if total + p.tokens > overlap_tokens:
                    break
                kept.insert(0, p)
                total += p.tokens
        buf = kept

    for page in pages:
        for raw in PARAGRAPH_SPLIT_RE.split(page.markdown):
            text = raw.strip()
            if not text:
                continue
            match = HEADING_RE.match(text.splitlines()[0])
            if match:
                if buf_tokens() >= flush_min_tokens:
                    flush(keep_overlap=False)
                level = len(match.group(1))
                headings = [h for h in headings if h[0] < level] + [(level, match.group(2).strip())]
            pieces = _hard_split(text, max_tokens) if count_tokens(text) > max_tokens else [text]
            for piece in pieces:
                tokens = count_tokens(piece)
                if buf and buf_tokens() + tokens > max_tokens:
                    flush(keep_overlap=True)
                    buf_heading = current_path()
                buf.append(_Para(piece, page.page_no, tokens, is_heading=bool(match)))
                # Chunk mới bắt đầu, hoặc chunk mới chỉ gồm các heading: gán theo heading hiện tại
                if len(buf) == 1 or all(p.is_heading for p in buf):
                    buf_heading = current_path()
    flush(keep_overlap=False)
    return chunks
```

- [ ] **Step 4: Chạy test**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: PASS cả 7 test

- [ ] **Step 5: Commit**

```bash
git add . && git commit -m "feat(ingestion): markdown chunker with heading paths, overlap and hard split"
```

---

### Task 18: Embedder và Vision (interface + bản giả + bản Gemini)

**Files:**
- Create: `backend/app/ai/__init__.py`, `backend/app/ai/embedder.py`, `backend/app/ai/vision.py`
- Test: `backend/tests/test_ai_providers.py`

- [ ] **Step 1: Viết test hỏng trước — `tests/test_ai_providers.py`**

```python
import math
from types import SimpleNamespace

from app.ai.embedder import FakeEmbedder, GeminiEmbedder, get_embedder
from app.ai.vision import FakeVision, get_vision
from app.core.config import Settings


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


async def test_fake_embedder_shape_norm_and_determinism():
    e = FakeEmbedder(768)
    [v1] = await e.embed_documents(["Tìm kiếm nhị phân"])
    v2 = await e.embed_query("Tìm kiếm nhị phân")
    assert len(v1) == 768 and e.model == "fake-768"
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-6)
    assert v1 == v2


async def test_fake_embedder_ignores_diacritics_and_ranks_related_higher():
    e = FakeEmbedder(768)
    a = await e.embed_query("Tìm kiếm nhị phân trên mảng đã sắp xếp")
    b = await e.embed_query("tim kiem nhi phan tren mang")
    c = await e.embed_query("mạng máy tính và giao thức TCP")
    assert cosine(a, b) > cosine(a, c)


async def test_fake_embedder_never_returns_zero_vector():
    [v] = await FakeEmbedder(8).embed_documents([""])
    assert any(v)


class _Models:
    def __init__(self):
        self.batch_sizes = []

    async def embed_content(self, model, contents, config):
        self.batch_sizes.append(len(contents))
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0]) for _ in contents])


async def test_gemini_embedder_batches_and_normalizes():
    models = _Models()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    e = GeminiEmbedder(api_key="x", model="gemini-embedding-001", dim=2, client=client)
    vectors = await e.embed_documents([f"t{i}" for i in range(250)])
    assert models.batch_sizes == [100, 100, 50]
    assert vectors[0] == [0.6, 0.8]


def test_factories_pick_fake_by_default():
    s = Settings(embed_provider="fake", vision_provider="fake", embed_dim=768)
    assert isinstance(get_embedder(s), FakeEmbedder)
    assert isinstance(get_vision(s), FakeVision)


async def test_fake_vision_records_calls():
    v = FakeVision()
    md = await v.page_to_markdown(b"\x89PNG...")
    assert v.calls == 1 and len(md) > 50
```

- [ ] **Step 2: Chạy test**

Run: `uv run pytest tests/test_ai_providers.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.ai'`

- [ ] **Step 3: `app/ai/embedder.py`** (`app/ai/__init__.py` để trống)

```python
import hashlib
import math
import re
import unicodedata
from typing import Protocol

from app.core.config import Settings


class Embedder(Protocol):
    model: str
    dim: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in values))
    return [x / norm for x in values] if norm else values


def _fold(text: str) -> str:
    text = text.lower().replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


class FakeEmbedder:
    """Embedding giả, tất định: băm từng từ (đã bỏ dấu) vào một ô của vector.
    Dùng cho test và dev không có API key; văn bản nhiều từ chung thì cosine cao."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.model = f"fake-{dim}"

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for token in re.findall(r"\w+", _fold(text)):
            h = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            v[h % self.dim] += 1.0
        if not any(v):
            v[0] = 1.0
        return _normalize(v)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class GeminiEmbedder:
    BATCH = 100

    def __init__(self, api_key: str, model: str, dim: int, client=None):
        if client is None:
            from google import genai
            client = genai.Client(api_key=api_key)
        self._client = client
        self.model = model
        self.dim = dim

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            resp = await self._client.aio.models.embed_content(
                model=self.model, contents=texts[i:i + self.BATCH],
                config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim),
            )
            # Khi giảm số chiều, vector trả về không còn chuẩn hóa → tự chuẩn hóa để dùng cosine
            out.extend(_normalize(list(e.values)) for e in resp.embeddings)
        return out

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


def get_embedder(s: Settings) -> Embedder:
    if s.embed_provider == "gemini":
        return GeminiEmbedder(s.gemini_api_key, s.embed_model, s.embed_dim)
    return FakeEmbedder(s.embed_dim)
```

- [ ] **Step 4: `app/ai/vision.py`**

```python
from typing import Protocol

from app.core.config import Settings

VISION_PROMPT = (
    "Chuyển nội dung trang tài liệu trong ảnh thành Markdown. Giữ nguyên tiếng Việt có dấu, "
    "heading, danh sách và bảng. Công thức toán viết dạng LaTeX trong $...$. "
    "Chỉ trả về Markdown, không giải thích thêm."
)


class VisionExtractor(Protocol):
    async def page_to_markdown(self, png: bytes) -> str: ...


class FakeVision:
    def __init__(self, text: str = "Nội dung được trích từ ảnh của trang tài liệu (chế độ giả lập, không gọi AI)."):
        self.text = text
        self.calls = 0

    async def page_to_markdown(self, png: bytes) -> str:
        self.calls += 1
        return self.text


class GeminiVision:
    def __init__(self, api_key: str, model: str, client=None):
        if client is None:
            from google import genai
            client = genai.Client(api_key=api_key)
        self._client = client
        self._model = model

    async def page_to_markdown(self, png: bytes) -> str:
        from google.genai import types

        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[types.Part.from_bytes(data=png, mime_type="image/png"), VISION_PROMPT],
        )
        return (resp.text or "").strip()


def get_vision(s: Settings) -> VisionExtractor:
    if s.vision_provider == "gemini":
        return GeminiVision(s.gemini_api_key, s.vision_model)
    return FakeVision()
```

- [ ] **Step 5: Chạy test**

Run: `uv run pytest tests/test_ai_providers.py -v`
Expected: PASS cả 6 test

- [ ] **Step 6: Commit**

```bash
git add . && git commit -m "feat(ai): embedder and vision interfaces with fake and gemini implementations"
```

---

### Task 19: Trích xuất PDF (text trước, vision làm fallback)

**Files:**
- Create: `backend/app/ingestion/extract.py`, `backend/tests/pdfs.py`
- Test: `backend/tests/test_extract.py`

- [ ] **Step 1: `tests/pdfs.py`**: tạo PDF thật trong bộ nhớ. Dùng chữ ASCII, vì font mặc định của PyMuPDF không có glyph tiếng Việt.

```python
import pymupdf

LONG_TEXT = "Binary search repeatedly halves the search interval of a sorted array. " * 5


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        if body:
            page.insert_textbox(pymupdf.Rect(72, 72, 540, 770), body, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data
```

- [ ] **Step 2: Viết test hỏng trước — `tests/test_extract.py`**

```python
import pytest

from app.ai.vision import FakeVision
from app.ingestion.extract import extract_pages, needs_vision
from tests.pdfs import LONG_TEXT, make_pdf


def test_needs_vision_rules():
    assert needs_vision("")
    assert needs_vision("# \n\n---\n\n| |")
    assert needs_vision("x" * 60 + "�" * 6)
    assert not needs_vision(LONG_TEXT)


async def test_text_page_uses_text_blank_page_falls_back_to_vision():
    vision = FakeVision()
    pages = await extract_pages(make_pdf([LONG_TEXT, ""]), vision)
    assert [(p.page_no, p.method) for p in pages] == [(1, "text"), (2, "vision")]
    assert "Binary search" in pages[0].markdown
    assert pages[1].markdown == vision.text
    assert vision.calls == 1


async def test_vision_receives_png(monkeypatch):
    seen = {}

    class Spy(FakeVision):
        async def page_to_markdown(self, png: bytes) -> str:
            seen["png"] = png
            return await super().page_to_markdown(png)

    await extract_pages(make_pdf([""]), Spy())
    assert seen["png"].startswith(b"\x89PNG")


async def test_corrupt_pdf_raises():
    with pytest.raises(Exception):
        await extract_pages(b"not a pdf", FakeVision())
```

- [ ] **Step 3: Chạy test**

Run: `uv run pytest tests/test_extract.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.ingestion.extract'`

- [ ] **Step 4: `app/ingestion/extract.py`**

```python
import asyncio
import re

import pymupdf
import pymupdf4llm

from app.ai.vision import VisionExtractor
from app.ingestion.chunker import PageText

MIN_TEXT_CHARS = 50
MAX_PAGES = 300
_MARKUP_RE = re.compile(r"[#*_`>\-|\s]")


def needs_vision(markdown: str) -> bool:
    """Trang gần như không có chữ (scan/ảnh) hoặc chữ bị vỡ font → nhờ vision đọc lại."""
    visible = _MARKUP_RE.sub("", markdown)
    return len(visible) < MIN_TEXT_CHARS or markdown.count("�") > 5


def _extract_text_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count > MAX_PAGES:
            raise ValueError(f"PDF quá dài (tối đa {MAX_PAGES} trang)")
        parts = pymupdf4llm.to_markdown(doc, page_chunks=True)
        return [(i + 1, part["text"]) for i, part in enumerate(parts)]
    finally:
        doc.close()


def _render_png(pdf_bytes: bytes, page_no: int, dpi: int = 150) -> bytes:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return doc[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()


async def extract_pages(pdf_bytes: bytes, vision: VisionExtractor) -> list[PageText]:
    # PyMuPDF là code đồng bộ, nặng CPU → chạy trong thread để không chặn event loop của worker
    raw = await asyncio.to_thread(_extract_text_pages, pdf_bytes)
    pages: list[PageText] = []
    for page_no, markdown in raw:
        if needs_vision(markdown):
            png = await asyncio.to_thread(_render_png, pdf_bytes, page_no)
            pages.append(PageText(page_no, (await vision.page_to_markdown(png)).strip(), "vision"))
        else:
            pages.append(PageText(page_no, markdown.strip(), "text"))
    return pages
```

- [ ] **Step 5: Chạy test**

Run: `uv run pytest tests/test_extract.py -v`
Expected: PASS cả 4 test

- [ ] **Step 6: Commit**

```bash
git add . && git commit -m "feat(ingestion): pdf extraction with pymupdf4llm and vision fallback"
```

---

### Task 20: Pipeline xử lý tài liệu (PDF → pages → chunks → embedding)

**Files:**
- Create: `backend/app/ingestion/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Viết test hỏng trước — `tests/test_pipeline.py`**

```python
import pytest
from sqlalchemy import func, select

from app.ai.embedder import FakeEmbedder
from app.ai.vision import FakeVision
from app.ingestion.pipeline import ingest_pdf_source
from app.modules.materials.models import Chunk, Source, SourcePage, SourceStatus
from tests.factories import make_lesson, make_pdf_source, make_user
from tests.fakes import InMemoryStorage
from tests.pdfs import LONG_TEXT, make_pdf


async def _source(db, storage, pdf: bytes):
    teacher = await make_user(db)
    course, lesson = await make_lesson(db, teacher)
    source = await make_pdf_source(db, storage, teacher, lesson, pdf)
    return course, lesson, source


async def test_ingest_success_writes_pages_and_chunks(db):
    storage = InMemoryStorage()
    course, lesson, source = await _source(db, storage, make_pdf([LONG_TEXT, ""]))
    n = await ingest_pdf_source(source.id, storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())
    assert n >= 1

    await db.refresh(source)
    assert source.status == SourceStatus.ready and source.processed_at is not None
    methods = (await db.scalars(select(SourcePage.extraction_method).where(SourcePage.source_id == source.id)
                                .order_by(SourcePage.page_no))).all()
    assert [m.value for m in methods] == ["text", "vision"]
    chunk = await db.scalar(select(Chunk).where(Chunk.source_id == source.id).limit(1))
    assert (chunk.course_id, chunk.lesson_id) == (course.id, lesson.id)
    assert chunk.embedding_model == "fake-768" and len(chunk.embedding) == 768


async def test_reingest_replaces_instead_of_duplicating(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, make_pdf([LONG_TEXT]))
    kw = dict(storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())
    first = await ingest_pdf_source(source.id, **kw)
    second = await ingest_pdf_source(source.id, **kw)
    total = await db.scalar(select(func.count(Chunk.id)).where(Chunk.source_id == source.id))
    assert first == second == total


async def test_corrupt_pdf_marks_source_failed(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, b"not a pdf")
    with pytest.raises(Exception):
        await ingest_pdf_source(source.id, storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())
    fresh = await db.get(Source, source.id, populate_existing=True)
    assert fresh.status == SourceStatus.failed and fresh.error_msg


async def test_document_without_any_text_fails(db):
    storage = InMemoryStorage()
    _, _, source = await _source(db, storage, make_pdf([""]))
    with pytest.raises(ValueError):
        await ingest_pdf_source(source.id, storage=storage, embedder=FakeEmbedder(768), vision=FakeVision(text=""))
    fresh = await db.get(Source, source.id, populate_existing=True)
    assert fresh.status == SourceStatus.failed
```

- [ ] **Step 2: Chạy test**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.ingestion.pipeline'`

- [ ] **Step 3: `app/ingestion/pipeline.py`**

```python
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.embedder import Embedder
from app.ai.vision import VisionExtractor
from app.core.db import SessionLocal
from app.core.storage import Storage
from app.core.time import utcnow
from app.ingestion.chunker import chunk_pages
from app.ingestion.extract import extract_pages
from app.modules.courses.models import Lesson, Section
from app.modules.materials.models import Asset, Chunk, ExtractionMethod, Source, SourcePage, SourceStatus


async def _mark_failed(session_factory: async_sessionmaker, source_id: uuid.UUID, error: Exception) -> None:
    async with session_factory() as db:
        source = await db.get(Source, source_id)
        if source is not None:
            source.status = SourceStatus.failed
            source.error_msg = (str(error) or type(error).__name__)[:500]
            await db.commit()


async def ingest_pdf_source(source_id: uuid.UUID, *, storage: Storage, embedder: Embedder,
                            vision: VisionExtractor,
                            session_factory: async_sessionmaker = SessionLocal) -> int:
    """Xử lý một source PDF. Trả về số chunk đã ghi.

    Dùng các DB session ngắn: không giữ connection trong lúc tải file, gọi vision và embedding (có thể mất vài phút).
    """
    async with session_factory() as db:
        row = (await db.execute(
            select(Source, Asset.storage_key, Lesson.id, Section.course_id)
            .join(Asset, Asset.id == Source.asset_id)
            .join(Lesson, Lesson.id == Source.lesson_id)
            .join(Section, Section.id == Lesson.section_id)
            .where(Source.id == source_id)
        )).one_or_none()
        if row is None:
            raise ValueError(f"Source {source_id} không tồn tại")
        source, storage_key, lesson_id, course_id = row
        source.status = SourceStatus.processing
        source.error_msg = None
        await db.commit()

    try:
        pdf_bytes = await storage.read_all(storage_key)
        pages = await extract_pages(pdf_bytes, vision)
        drafts = chunk_pages(pages)
        if not drafts:
            raise ValueError("Tài liệu không có nội dung đọc được")
        vectors = await embedder.embed_documents([d.content for d in drafts])
    except Exception as e:
        await _mark_failed(session_factory, source_id, e)
        raise

    async with session_factory() as db:
        await db.execute(delete(Chunk).where(Chunk.source_id == source_id))
        await db.execute(delete(SourcePage).where(SourcePage.source_id == source_id))
        db.add_all([SourcePage(source_id=source_id, page_no=p.page_no,
                               extraction_method=ExtractionMethod(p.method), markdown=p.markdown)
                    for p in pages])
        db.add_all([Chunk(source_id=source_id, course_id=course_id, lesson_id=lesson_id, content=d.content,
                          heading_path=d.heading_path[:500], page_no=d.page_no, token_count=d.token_count,
                          embedding_model=embedder.model, embedding=v)
                    for d, v in zip(drafts, vectors, strict=True)])
        source = await db.get(Source, source_id)
        source.status = SourceStatus.ready
        source.processed_at = utcnow()
        await db.commit()
    return len(drafts)
```

- [ ] **Step 4: Chạy test**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS cả 4 test

- [ ] **Step 5: Commit**

```bash
git add . && git commit -m "feat(ingestion): pdf ingestion pipeline with short-lived sessions and failure marking"
```

---

### Task 21: API tài liệu của bài học (gắn PDF, xem trạng thái, xem trang, xử lý lại)

> Điều chỉnh sau Task 14: `upload_file` PUT qua `storage.client_put` (vào key tạm `staging/...`, kèm mime) thay vì ghi thẳng `storage.objects`, khớp storage giả mới.

**Files:**
- Create: `backend/app/modules/materials/sources.py`
- Modify: `backend/app/modules/materials/schemas.py`, `backend/app/modules/materials/router.py`, `backend/tests/helpers.py`
- Test: `backend/tests/test_sources_api.py`

- [ ] **Step 1: Thêm vào cuối `tests/helpers.py`**

```python
async def upload_file(client, storage, headers, data: bytes, kind="pdf", mime="application/pdf") -> str:
    """Presign → 'upload' vào key tạm của storage giả → complete. Trả về asset_id."""
    r = await client.post(f"{API}/uploads/presign", json={"kind": kind, "mime": mime, "size": len(data)},
                          headers=headers)
    assert r.status_code == 200, r.text
    storage.client_put(r.json()["put_url"], data, mime)  # vào key tạm; complete sẽ copy sang key chính thức
    done = await client.post(f"{API}/uploads/{r.json()['asset_id']}/complete", headers=headers)
    assert done.status_code == 200, done.text
    return r.json()["asset_id"]
```

- [ ] **Step 2: Viết test hỏng trước — `tests/test_sources_api.py`**

```python
import uuid

from app.ai.embedder import FakeEmbedder
from app.ai.vision import FakeVision
from app.ingestion.pipeline import ingest_pdf_source
from app.modules.materials.models import Source, SourceStatus
from tests.helpers import API, make_published_course, make_student, make_teacher, upload_file
from tests.pdfs import LONG_TEXT, make_pdf


async def _attach(client, headers, lesson_id, asset_id):
    return await client.post(f"{API}/lessons/{lesson_id}/sources", json={"asset_id": asset_id}, headers=headers)


async def test_teacher_attaches_pdf_and_job_is_enqueued(client, storage, queue):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf([LONG_TEXT]))
    r = await _attach(client, gv, lesson["id"], asset_id)
    assert r.status_code == 202
    body = r.json()
    assert body["source"]["status"] == "pending"
    assert queue.jobs == [("ingest_pdf", uuid.UUID(body["source"]["id"]))]
    job = await client.get(f"{API}/jobs/{body['job_id']}", headers=gv)
    assert job.json()["status"] == "pending"
    listed = await client.get(f"{API}/lessons/{lesson['id']}/sources", headers=gv)
    assert [s["id"] for s in listed.json()] == [body["source"]["id"]]


async def test_student_and_other_teacher_cannot_attach(client, storage):
    _, gv1 = await make_teacher(client, "gv1@x.com")
    _, gv2 = await make_teacher(client, "gv2@x.com")
    _, sv = await make_student(client)
    _, _, lesson = await make_published_course(client, gv1)
    asset_id = await upload_file(client, storage, gv1, make_pdf([LONG_TEXT]))
    r_sv = await _attach(client, sv, lesson["id"], asset_id)
    r_gv2 = await _attach(client, gv2, lesson["id"], asset_id)
    assert (r_sv.status_code, r_sv.json()["error"]["code"]) == (403, "FORBIDDEN")
    assert r_gv2.status_code == 404


async def test_unverified_asset_is_rejected(client):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    r = await client.post(f"{API}/uploads/presign", json={"kind": "pdf", "mime": "application/pdf", "size": 10},
                          headers=gv)
    attach = await _attach(client, gv, lesson["id"], r.json()["asset_id"])
    assert (attach.status_code, attach.json()["error"]["code"]) == (400, "INVALID_ASSET")


async def test_reprocess_only_when_finished(client, storage, queue, db):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf([LONG_TEXT]))
    source_id = (await _attach(client, gv, lesson["id"], asset_id)).json()["source"]["id"]

    busy = await client.post(f"{API}/sources/{source_id}/reprocess", headers=gv)
    assert (busy.status_code, busy.json()["error"]["code"]) == (409, "INVALID_STATE")

    src = await db.get(Source, uuid.UUID(source_id))
    src.status = SourceStatus.failed
    await db.commit()
    # job đầu vẫn 'pending' trong bảng jobs; đánh dấu xong để partial unique index cho tạo job mới
    from sqlalchemy import update

    from app.modules.jobs.models import Job, JobStatus
    await db.execute(update(Job).values(status=JobStatus.failed))
    await db.commit()

    ok = await client.post(f"{API}/sources/{source_id}/reprocess", headers=gv)
    assert ok.status_code == 202 and len(queue.jobs) == 2


async def test_pages_and_counts_after_processing(client, storage):
    _, gv = await make_teacher(client)
    _, _, lesson = await make_published_course(client, gv)
    asset_id = await upload_file(client, storage, gv, make_pdf([LONG_TEXT, ""]))
    source_id = (await _attach(client, gv, lesson["id"], asset_id)).json()["source"]["id"]

    await ingest_pdf_source(uuid.UUID(source_id), storage=storage, embedder=FakeEmbedder(768), vision=FakeVision())

    detail = (await client.get(f"{API}/sources/{source_id}", headers=gv)).json()
    assert detail["status"] == "ready" and detail["page_count"] == 2 and detail["chunk_count"] >= 1
    pages = (await client.get(f"{API}/sources/{source_id}/pages", headers=gv)).json()
    assert [p["extraction_method"] for p in pages] == ["text", "vision"]
```

- [ ] **Step 3: Chạy test**

Run: `uv run pytest tests/test_sources_api.py -v`
Expected: FAIL (405/404 vì chưa có route `/lessons/{id}/sources`)

- [ ] **Step 4: Thêm vào cuối `app/modules/materials/schemas.py`**
  - Thêm import: `from app.modules.materials.models import AssetKind, ExtractionMethod, SourceStatus, SourceType` (thay dòng import `AssetKind` cũ)

```python
class SourceCreate(BaseModel):
    asset_id: uuid.UUID


class SourceOut(BaseModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    type: SourceType
    status: SourceStatus
    error_msg: str | None
    processed_at: datetime | None
    page_count: int
    chunk_count: int


class SourceCreated(BaseModel):
    source: SourceOut
    job_id: uuid.UUID


class JobRef(BaseModel):
    job_id: uuid.UUID


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_no: int
    extraction_method: ExtractionMethod
    markdown: str
```

- [ ] **Step 5: `app/modules/materials/sources.py`**

```python
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.modules.auth.models import User
from app.modules.courses.models import Course, Lesson, Section
from app.modules.courses.service import ensure_owner, get_owned_lesson
from app.modules.jobs.models import Job
from app.modules.jobs.queue import JobQueue
from app.modules.jobs.service import create_and_enqueue
from app.modules.materials.assets import require_verified_asset
from app.modules.materials.models import AssetKind, Chunk, Source, SourcePage, SourceStatus, SourceType
from app.modules.materials.schemas import SourceOut

INGEST_PDF = "ingest_pdf"


async def get_owned_source(db: AsyncSession, source_id: uuid.UUID, user: User) -> Source:
    row = (await db.execute(
        select(Source, Course)
        .join(Lesson, Lesson.id == Source.lesson_id)
        .join(Section, Section.id == Lesson.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(Source.id == source_id)
    )).one_or_none()
    if row is None:
        raise not_found("Tài liệu")
    ensure_owner(row[1], user)
    return row[0]


async def to_out(db: AsyncSession, source: Source) -> SourceOut:
    pages = await db.scalar(select(func.count()).select_from(SourcePage).where(SourcePage.source_id == source.id))
    chunks = await db.scalar(select(func.count(Chunk.id)).where(Chunk.source_id == source.id))
    return SourceOut(id=source.id, lesson_id=source.lesson_id, type=source.type, status=source.status,
                     error_msg=source.error_msg, processed_at=source.processed_at,
                     page_count=pages, chunk_count=chunks)


async def attach_pdf(db: AsyncSession, queue: JobQueue, user: User, lesson_id: uuid.UUID,
                     asset_id: uuid.UUID) -> tuple[Source, Job]:
    lesson, _ = await get_owned_lesson(db, lesson_id, user)
    asset = await require_verified_asset(db, asset_id, user, AssetKind.pdf)
    source = Source(lesson_id=lesson.id, asset_id=asset.id, type=SourceType.pdf, status=SourceStatus.pending)
    db.add(source)
    await db.flush()
    job = await create_and_enqueue(db, queue, INGEST_PDF, source.id)  # commit source + job cùng lúc
    return source, job


async def list_lesson_sources(db: AsyncSession, user: User, lesson_id: uuid.UUID) -> list[SourceOut]:
    await get_owned_lesson(db, lesson_id, user)
    sources = await db.scalars(select(Source).where(Source.lesson_id == lesson_id).order_by(Source.created_at))
    return [await to_out(db, s) for s in sources]


async def list_pages(db: AsyncSession, source: Source) -> list[SourcePage]:
    rows = await db.scalars(select(SourcePage).where(SourcePage.source_id == source.id)
                            .order_by(SourcePage.page_no))
    return list(rows)


async def reprocess(db: AsyncSession, queue: JobQueue, source: Source) -> Job:
    if source.status not in (SourceStatus.ready, SourceStatus.failed):
        raise AppError("INVALID_STATE", "Tài liệu đang được xử lý", 409)
    source.status = SourceStatus.pending
    source.error_msg = None
    return await create_and_enqueue(db, queue, INGEST_PDF, source.id)
```

- [ ] **Step 6: Thêm vào `app/modules/materials/router.py`**
  - Thêm import:
    - `from app.core.deps import get_current_user, require_staff` (thay dòng import deps cũ)
    - `from app.modules.jobs.queue import JobQueue, get_queue`
    - `from app.modules.materials import assets, sources` (thay dòng `from app.modules.materials import assets`)
    - Thêm `JobRef, PageOut, SourceCreate, SourceCreated, SourceOut` vào dòng import schemas
  - Thêm các route sau:

```python
@router.post("/lessons/{lesson_id}/sources", response_model=SourceCreated, status_code=202)
async def attach_source(lesson_id: uuid.UUID, data: SourceCreate, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db), queue: JobQueue = Depends(get_queue)):
    source, job = await sources.attach_pdf(db, queue, user, lesson_id, data.asset_id)
    return SourceCreated(source=await sources.to_out(db, source), job_id=job.id)


@router.get("/lessons/{lesson_id}/sources", response_model=list[SourceOut])
async def lesson_sources(lesson_id: uuid.UUID, user: User = Depends(require_staff),
                         db: AsyncSession = Depends(get_db)):
    return await sources.list_lesson_sources(db, user, lesson_id)


@router.get("/sources/{source_id}", response_model=SourceOut)
async def source_detail(source_id: uuid.UUID, user: User = Depends(require_staff),
                        db: AsyncSession = Depends(get_db)):
    return await sources.to_out(db, await sources.get_owned_source(db, source_id, user))


@router.get("/sources/{source_id}/pages", response_model=list[PageOut])
async def source_pages(source_id: uuid.UUID, user: User = Depends(require_staff),
                       db: AsyncSession = Depends(get_db)):
    return await sources.list_pages(db, await sources.get_owned_source(db, source_id, user))


@router.post("/sources/{source_id}/reprocess", response_model=JobRef, status_code=202)
async def reprocess_source(source_id: uuid.UUID, user: User = Depends(require_staff),
                           db: AsyncSession = Depends(get_db), queue: JobQueue = Depends(get_queue)):
    source = await sources.get_owned_source(db, source_id, user)
    job = await sources.reprocess(db, queue, source)
    return JobRef(job_id=job.id)
```

- [ ] **Step 7: Chạy toàn bộ test**

Run: `uv run pytest -v`
Expected: PASS hết

- [ ] **Step 8: Commit**

```bash
git add . && git commit -m "feat(materials): attach pdf sources to lessons, status, pages, reprocess"
```

---

### Task 22: Worker arq, Docker cho api/worker và smoke test end-to-end

**Files:**
- Create: `backend/app/worker/__init__.py`, `backend/app/worker/tasks.py`, `backend/app/worker/settings.py`, `backend/Dockerfile`, `backend/.dockerignore`, `backend/scripts/smoke_week1.py`
- Modify: `backend/app/main.py`, `docker-compose.yml`
- Test: `backend/tests/test_worker.py`

- [ ] **Step 1: Viết test hỏng trước — `tests/test_worker.py`**

```python
from app.ai.embedder import FakeEmbedder
from app.ai.vision import FakeVision
from app.modules.jobs.models import Job, JobStatus
from app.modules.jobs.service import create_job
from app.modules.materials.models import Source, SourceStatus
from app.worker.tasks import ingest_pdf, run_job
from tests.factories import make_lesson, make_pdf_source, make_user
from tests.fakes import InMemoryStorage
from tests.pdfs import LONG_TEXT, make_pdf


async def _job_for_new_source(db, storage, pdf):
    teacher = await make_user(db)
    _, lesson = await make_lesson(db, teacher)
    source = await make_pdf_source(db, storage, teacher, lesson, pdf)
    job, _ = await create_job(db, "ingest_pdf", source.id)
    await db.commit()
    return source, job


async def test_ingest_pdf_job_succeeds(db):
    storage = InMemoryStorage()
    source, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))
    ctx = {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision()}
    await ingest_pdf(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    source = await db.get(Source, source.id, populate_existing=True)
    assert job.status == JobStatus.done and job.attempts == 1 and job.finished_at is not None
    assert source.status == SourceStatus.ready


async def test_failing_handler_marks_job_failed_without_raising(db):
    storage = InMemoryStorage()
    _, job = await _job_for_new_source(db, storage, b"not a pdf")
    ctx = {"storage": storage, "embedder": FakeEmbedder(768), "vision": FakeVision()}
    await ingest_pdf(ctx, str(job.id))
    job = await db.get(Job, job.id, populate_existing=True)
    assert job.status == JobStatus.failed and job.error_msg


async def test_finished_job_is_not_run_again(db):
    storage = InMemoryStorage()
    _, job = await _job_for_new_source(db, storage, make_pdf([LONG_TEXT]))
    job.status = JobStatus.done
    await db.commit()
    calls = []

    async def handler(ref_id):
        calls.append(ref_id)

    await run_job(str(job.id), handler)
    assert calls == []
```

- [ ] **Step 2: Chạy test**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'app.worker'`

- [ ] **Step 3: `app/worker/tasks.py`** (`app/worker/__init__.py` để trống)

```python
import logging
import uuid
from collections.abc import Awaitable, Callable

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.ingestion.pipeline import ingest_pdf_source
from app.modules.jobs.models import Job, JobStatus

logger = logging.getLogger(__name__)


async def run_job(job_id: str, handler: Callable[[uuid.UUID], Awaitable[object]]) -> None:
    """Chạy một job: đánh dấu processing, gọi handler(ref_id), ghi done/failed.
    Không ném lỗi ra ngoài: trạng thái lỗi nằm trong bảng jobs, arq không tự retry."""
    jid = uuid.UUID(job_id)
    async with SessionLocal() as db:
        job = await db.get(Job, jid)
        if job is None or job.status in (JobStatus.done, JobStatus.failed):
            logger.warning("Bỏ qua job %s (không tồn tại hoặc đã kết thúc)", job_id)
            return
        job.status = JobStatus.processing
        job.attempts += 1
        job.started_at = utcnow()
        ref_id = job.ref_id
        await db.commit()

    status, error = JobStatus.done, None
    try:
        await handler(ref_id)
    except Exception as e:  # noqa: BLE001 — mọi lỗi đều phải được ghi vào job
        logger.exception("Job %s thất bại", job_id)
        status, error = JobStatus.failed, (str(e) or type(e).__name__)[:500]

    async with SessionLocal() as db:
        job = await db.get(Job, jid)
        job.status = status
        job.error_msg = error
        job.finished_at = utcnow()
        await db.commit()


async def ingest_pdf(ctx: dict, job_id: str) -> None:
    async def handler(source_id: uuid.UUID) -> None:
        await ingest_pdf_source(source_id, storage=ctx["storage"], embedder=ctx["embedder"], vision=ctx["vision"])

    await run_job(job_id, handler)
```

- [ ] **Step 4: `app/worker/settings.py`**

```python
from arq import func
from arq.connections import RedisSettings

from app.ai.embedder import get_embedder
from app.ai.vision import get_vision
from app.core.config import get_settings
from app.core.storage import MinioStorage
from app.worker.tasks import ingest_pdf


async def startup(ctx: dict) -> None:
    s = get_settings()
    storage = MinioStorage(s)
    await storage.ensure_bucket()
    ctx["storage"] = storage
    ctx["embedder"] = get_embedder(s)
    ctx["vision"] = get_vision(s)


class WorkerSettings:
    # Tên hàm = job.type. timeout riêng cho từng loại job (spec K4)
    functions = [func(ingest_pdf, name="ingest_pdf", timeout=600)]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 5
```

- [ ] **Step 5: Chạy test**

Run: `uv run pytest tests/test_worker.py -v`
Expected: PASS cả 3 test

- [ ] **Step 6: Tạo bucket khi API khởi động** (`app/main.py`)
  - Thêm import: `from contextlib import asynccontextmanager` và `from app.core.storage import get_storage`
  - Thêm hàm sau ngay trên `def create_app()`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = get_storage()
    ensure_bucket = getattr(storage, "ensure_bucket", None)
    if ensure_bucket is not None:
        await ensure_bucket()
    yield
```

  - Sửa dòng tạo app thành: `app = FastAPI(title="LMS-AI API", lifespan=lifespan)`

(Test dùng `httpx.ASGITransport`, không gửi sự kiện lifespan, nên không đụng tới MinIO thật.)

- [ ] **Step 7: `backend/Dockerfile` và `backend/.dockerignore`**

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```
.venv
__pycache__
.pytest_cache
.ruff_cache
.env
tests
```

- [ ] **Step 8: Thêm `api` và `worker` vào `docker-compose.yml`** (dưới service `minio`, trong khối `services:`)

```yaml
  api:
    build: ./backend
    env_file: ./backend/.env
    environment: &backend_env
      DATABASE_URL: postgresql+asyncpg://lms:lms@db:5432/lms
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      MINIO_PUBLIC_ENDPOINT: localhost:9000
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
    ports: ["8000:8000"]
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
      minio:
        condition: service_started
  worker:
    build: ./backend
    env_file: ./backend/.env
    environment: *backend_env
    command: arq app.worker.settings.WorkerSettings
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
      minio:
        condition: service_started
```

- [ ] **Step 9: `backend/scripts/smoke_week1.py`**: kiểm tra end-to-end trên hệ thống thật (API, worker, MinIO, Postgres)

```python
"""Smoke test tuần 1. Cần `docker compose up -d --build` trước.

Chạy từ thư mục backend/:  uv run python scripts/smoke_week1.py duong/dan/file.pdf
"""
import asyncio
import sys
import time
import uuid

import httpx

from app.core.db import SessionLocal
from app.modules.auth.service import approve_teacher

API = "http://localhost:8000/api/v1"


async def _approve(email: str) -> None:
    async with SessionLocal() as db:
        await approve_teacher(db, email)


def main(pdf_path: str) -> int:
    data = open(pdf_path, "rb").read()
    email = f"smoke-{uuid.uuid4().hex[:6]}@lms.local"
    with httpx.Client(base_url=API, timeout=30) as c:
        c.post("/auth/register", json={"email": email, "password": "password123",
                                       "full_name": "Smoke GV", "role": "teacher"}).raise_for_status()
        asyncio.run(_approve(email))
        token = c.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        course = c.post("/courses", json={"title": "Khóa smoke test"}, headers=h).json()
        section = c.post(f"/courses/{course['id']}/sections", json={"title": "Chương 1"}, headers=h).json()
        lesson = c.post(f"/sections/{section['id']}/lessons", json={"title": "Bài 1"}, headers=h).json()

        pre = c.post("/uploads/presign", json={"kind": "pdf", "mime": "application/pdf", "size": len(data)},
                     headers=h).json()
        httpx.put(pre["put_url"], content=data, timeout=120).raise_for_status()
        c.post(f"/uploads/{pre['asset_id']}/complete", headers=h).raise_for_status()

        created = c.post(f"/lessons/{lesson['id']}/sources", json={"asset_id": pre["asset_id"]}, headers=h).json()
        job_id, source_id = created["job_id"], created["source"]["id"]
        print("Đã gắn tài liệu, job:", job_id)

        deadline = time.time() + 180
        while time.time() < deadline:
            job = c.get(f"/jobs/{job_id}", headers=h).json()
            if job["status"] in ("done", "failed"):
                break
            time.sleep(2)
        print("Job:", job["status"], job.get("error_msg") or "")
        detail = c.get(f"/sources/{source_id}", headers=h).json()
        pages = c.get(f"/sources/{source_id}/pages", headers=h).json()
        print(f"Source: {detail['status']} · {detail['page_count']} trang · {detail['chunk_count']} chunk")
        print("Cách trích từng trang:", [p["extraction_method"] for p in pages])
        return 0 if job["status"] == "done" and detail["chunk_count"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
```

- [ ] **Step 10: Chạy toàn bộ hệ thống và smoke test**

Run: `docker compose up -d --build` rồi `docker compose logs -f worker` (mở ở cửa sổ khác)
Run: `uv run python scripts/smoke_week1.py <một file PDF bài giảng có text>`
Expected:
```
Đã gắn tài liệu, job: <uuid>
Job: done
Source: ready · N trang · M chunk
Cách trích từng trang: ['text', 'text', ...]
```
Nếu `put_url` lỗi `SignatureDoesNotMatch`: kiểm tra `MINIO_PUBLIC_ENDPOINT` của service `api` phải là `localhost:9000`, đúng host mà script dùng để PUT.

- [ ] **Step 11 (tùy chọn, cần API key): chạy với Gemini thật**
  - Trong `backend/.env`: đặt `EMBED_PROVIDER=gemini`, `EMBED_MODEL=gemini-embedding-001`, `VISION_PROVIDER=gemini` và `GEMINI_API_KEY=...`. Trước đó kiểm tra lại tên model hiện hành trên trang tài liệu Google AI.
  - Chạy `docker compose up -d --build worker` rồi chạy lại smoke test với một PDF có trang scan.
  - Expected: có trang mang `vision`, và chunk có `embedding_model = gemini-embedding-001`.

- [ ] **Step 12: Commit**

```bash
git add . && git commit -m "feat(worker): arq worker for pdf ingestion, dockerized api/worker, e2e smoke script"
```

---

### Task 23: Kiểm tra cuối và cập nhật spec

**Files:**
- Modify: `docs/specs/2026-09-29-lms-ai-design.md`

- [ ] **Step 1: Chạy toàn bộ test và lint**

Run: `uv run pytest -v` rồi `uv run ruff check .`
Expected: toàn bộ test PASS, ruff không báo lỗi (nếu có lỗi import thừa thì sửa rồi chạy lại)

- [ ] **Step 2: Kiểm tra migration chạy lại từ đầu được**

Run: `uv run alembic downgrade base && uv run alembic upgrade head` (trên DB dev)
Expected: không lỗi. Nếu `downgrade` lỗi vì enum type còn tồn tại, thêm `op.execute("DROP TYPE IF EXISTS <tên_enum>")` vào hàm `downgrade()` của migration tương ứng.

- [ ] **Step 3: Cập nhật spec**
  - **Bảng tiến độ:** A1, A2, A3, A4 chuyển thành `[~]` (backend xong, còn frontend). Dòng "Tuần hiện tại" đặt `1 / 5`.
  - **Mục 7:** thêm các mã lỗi `EMAIL_TAKEN`, `INVALID_TOKEN`, `TOKEN_REUSED`, `NOT_AUTHENTICATED`, `FORBIDDEN`, `COURSE_EMPTY`, `INVALID_REORDER`, `UPLOAD_MISSING`, `INVALID_ASSET`, `INVALID_STATE`.
  - **Mục 6.4:** thêm `GET /teacher/courses`, `GET /lessons/{id}`, `GET /lessons/{id}/video`, `GET /lessons/{id}/sources`.
  - **Mục 13 (Nhật ký quyết định):** thêm dòng `2026-xx-xx | Email lưu chữ thường, bảo đảm bằng CHECK constraint; test bắt buộc chạy trên DB *_test; token ước lượng 1.4 × số từ`.

- [ ] **Step 4: Commit**

```bash
git add . && git commit -m "docs: update spec progress after week-1 backend"
```
