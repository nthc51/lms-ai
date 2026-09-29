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


async def test_unknown_route_404_has_unified_format():
    async with _client(create_app()) as c:
        r = await c.get("/api/v1/khong-ton-tai")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert set(err) == {"code", "message", "details", "request_id"}
    assert err["request_id"] == r.headers["x-request-id"]


async def test_wrong_method_405_has_unified_format_and_allow_header():
    async with _client(create_app()) as c:
        r = await c.delete("/api/v1/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]
    assert "GET" in r.headers["allow"]


async def test_http_exception_codes_are_mapped():
    from fastapi import HTTPException

    app = create_app()

    @app.get("/raise/{status}")
    async def raise_status(status: int):
        raise HTTPException(status, "chi tiết nội bộ")

    async with _client(app) as c:
        codes = {s: (await c.get(f"/raise/{s}")).json()["error"]["code"] for s in (400, 401, 403, 409, 418)}
    assert codes == {
        400: "VALIDATION_ERROR",
        401: "NOT_AUTHENTICATED",
        403: "FORBIDDEN",
        409: "HTTP_ERROR",
        418: "HTTP_ERROR",
    }


async def test_unhandled_exception_is_500_internal_error_without_details(caplog):
    app = create_app()

    @app.get("/crash")
    async def crash():
        raise RuntimeError("bí mật: postgres password=hunter2")

    async with _client(app) as c:
        r = await c.get("/crash", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500
    err = r.json()["error"]
    assert err == {
        "code": "INTERNAL_ERROR",
        "message": "Lỗi hệ thống",
        "details": {},
        "request_id": r.headers["x-request-id"],
    }
    assert "hunter2" not in r.text and "RuntimeError" not in r.text
    # 500 vẫn đi qua CORS để frontend đọc được lỗi
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    # traceback được log kèm request_id
    logged = [rec for rec in caplog.records if err["request_id"] in rec.getMessage()]
    assert logged and logged[0].exc_info is not None


async def test_streaming_response_still_works():
    from fastapi.responses import StreamingResponse

    app = create_app()

    @app.get("/stream")
    async def stream():
        async def gen():
            for part in (b"a", b"b", b"c"):
                yield part

        return StreamingResponse(gen(), media_type="text/plain")

    async with _client(app) as c:
        r = await c.get("/stream")
    assert r.status_code == 200
    assert r.text == "abc"
    assert r.headers["x-request-id"]


async def test_huge_page_is_422_not_500(client):
    for url in ("/api/v1/courses?page=99999999999999999", "/api/v1/courses?page=10001"):
        r = await client.get(url)
        assert r.status_code == 422, url
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (await client.get("/api/v1/courses?page=10000")).status_code == 200
