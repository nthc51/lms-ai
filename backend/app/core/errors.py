import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

INTERNAL_ERROR_MESSAGE = "Lỗi hệ thống"

_HTTP_CODES: dict[int, tuple[str, str]] = {
    400: ("VALIDATION_ERROR", "Yêu cầu không hợp lệ"),
    401: ("NOT_AUTHENTICATED", "Bạn cần đăng nhập"),
    403: ("FORBIDDEN", "Bạn không có quyền thực hiện thao tác này"),
    404: ("NOT_FOUND", "Tài nguyên không tồn tại"),
    405: ("METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ"),
    422: ("VALIDATION_ERROR", "Dữ liệu không hợp lệ"),
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: dict | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}
        self.headers = headers


def not_found(what: str = "Tài nguyên") -> AppError:
    return AppError("NOT_FOUND", f"{what} không tồn tại", 404)


def forbidden(message: str = "Bạn không có quyền thực hiện thao tác này") -> AppError:
    return AppError("FORBIDDEN", message, 403)


def error_body(request_id: str | None, code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}


def _body(request: Request, code: str, message: str, details: dict) -> dict:
    return error_body(getattr(request.state, "request_id", None), code, message, details)


def internal_error_body(request_id: str | None) -> dict:
    """Thân 500 thống nhất: không bao giờ chứa traceback/nội dung exception."""
    return error_body(request_id, "INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE, {})


def http_error_code(status: int) -> tuple[str, str]:
    if status in _HTTP_CODES:
        return _HTTP_CODES[status]
    return (
        ("INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE)
        if status >= 500
        else ("HTTP_ERROR", "Yêu cầu không hợp lệ")
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            _body(request, exc.code, exc.message, exc.details), status_code=exc.status, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(
            _body(request, "VALIDATION_ERROR", "Dữ liệu không hợp lệ", {"errors": errors}), status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = http_error_code(exc.status_code)
        return JSONResponse(
            _body(request, code, message, {}), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Dự phòng: bình thường RequestIdMiddleware đã bắt exception trước (để 500 cũng có x-request-id);
        # handler này chỉ chạy nếu exception lọt ra ngoài middleware đó (ServerErrorMiddleware).
        request_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled exception (request_id=%s)", request_id)
        return JSONResponse(internal_error_body(request_id), status_code=500)
