from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.core.middleware import RequestIdMiddleware
from app.modules.auth.router import router as auth_router
from app.modules.courses.router import router as courses_router
from app.modules.enrollment.router import router as enrollment_router
from app.modules.materials.router import router as materials_router


def create_app() -> FastAPI:
    app = FastAPI(title="LMS-AI API")
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    # routers
    app.include_router(auth_router)
    app.include_router(courses_router)
    app.include_router(enrollment_router)
    app.include_router(materials_router)
    return app


app = create_app()
