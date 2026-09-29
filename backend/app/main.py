from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="LMS-AI API")

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok"}

    # routers
    return app


app = create_app()
