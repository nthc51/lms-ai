from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import RequestIdMiddleware, StrictCORSMiddleware
from app.core.storage import get_storage
from app.modules.auth.router import router as auth_router
from app.modules.courses.router import router as courses_router
from app.modules.enrollment.router import router as enrollment_router
from app.modules.jobs.router import router as jobs_router
from app.modules.materials.router import router as materials_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = get_storage()
    ensure_bucket = getattr(storage, "ensure_bucket", None)
    if ensure_bucket is not None:
        await ensure_bucket()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="LMS-AI API", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    # allow_credentials: frontend gửi cookie refresh (HttpOnly) tới /auth/refresh.
    app.add_middleware(
        StrictCORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["x-request-id"],
    )
    register_error_handlers(app)

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    # routers
    app.include_router(auth_router)
    app.include_router(courses_router)
    app.include_router(enrollment_router)
    app.include_router(materials_router)
    app.include_router(jobs_router)
    return app


app = create_app()
