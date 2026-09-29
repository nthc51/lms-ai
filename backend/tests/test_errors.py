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
