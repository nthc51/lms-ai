from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware, StrictCORSMiddleware
from app.core.ratelimit import close_rate_limiter
from app.core.storage import get_storage
from app.modules.admin.router import router as admin_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.courses.router import router as courses_router
from app.modules.enrollment.router import router as enrollment_router
from app.modules.jobs.router import router as jobs_router
from app.modules.materials.router import router as materials_router
from app.modules.quiz.router import router as quiz_router
from app.modules.studio.router import router as studio_router
from app.modules.tutor.router import router as tutor_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = get_storage()
    ensure_bucket = getattr(storage, "ensure_bucket", None)
    if ensure_bucket is not None:
        await ensure_bucket()
    try:
        yield
    finally:
        await close_rate_limiter()  # tự bắt lỗi, không làm hỏng việc tắt app


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
        expose_headers=["x-request-id", "retry-after"],
    )
    # Thêm sau cùng = lớp ngoài cùng: bọc cả response CORS preflight và 500
    app.add_middleware(SecurityHeadersMiddleware)
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
    app.include_router(tutor_router)
    app.include_router(quiz_router)
    app.include_router(analytics_router)
    app.include_router(admin_router)
    app.include_router(studio_router)
    return app


app = create_app()
