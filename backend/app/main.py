from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.core.middleware import RequestIdMiddleware
from app.modules.auth.router import router as auth_router


def create_app() -> FastAPI:
    app = FastAPI(title="LMS-AI API")
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    # routers
    app.include_router(auth_router)
    return app


app = create_app()
