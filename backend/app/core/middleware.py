import json
import logging
import uuid

from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware

from app.core.errors import internal_error_body

logger = logging.getLogger("app.errors")


class RequestIdMiddleware:
    """Gắn request_id vào scope.state và header x-request-id của mọi response.

    Exception không bắt được bên trong app cũng được xử lý tại đây (thay vì để ServerErrorMiddleware
    ngoài cùng của Starlette trả 500, vốn không đi qua middleware này nên thiếu x-request-id và header CORS):
    log traceback kèm request_id, trả 500 INTERNAL_ERROR thống nhất. Nếu response đã bắt đầu gửi
    (streaming) thì không thể đổi status nữa → ném tiếp.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_with_header(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        except Exception:
            logger.exception("Unhandled exception (request_id=%s)", request_id)
            if started:
                raise
            body = json.dumps(internal_error_body(request_id), ensure_ascii=False).encode()
            await send_with_header(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send_with_header({"type": "http.response.body", "body": body})


_CREDENTIAL_HEADERS = ("access-control-allow-credentials", "access-control-expose-headers")


def _strip_if_origin_denied(headers: MutableHeaders) -> None:
    if "access-control-allow-origin" not in headers:
        for key in _CREDENTIAL_HEADERS:
            if key in headers:
                del headers[key]


class StrictCORSMiddleware(CORSMiddleware):
    """CORSMiddleware của Starlette vẫn gắn Access-Control-Allow-Credentials (và Expose-Headers) cho
    origin không được phép. Bỏ các header đó để origin lạ không nhận header CORS nào."""

    def preflight_response(self, request_headers):
        response = super().preflight_response(request_headers)
        _strip_if_origin_denied(response.headers)
        return response

    async def send(self, message, send, request_headers):
        async def _send(msg):
            if msg["type"] == "http.response.start":
                _strip_if_origin_denied(MutableHeaders(scope=msg))
            await send(msg)

        await super().send(message, _send, request_headers)
