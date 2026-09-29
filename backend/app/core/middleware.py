import uuid

from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware


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
