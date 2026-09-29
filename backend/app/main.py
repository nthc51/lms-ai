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
