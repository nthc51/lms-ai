from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


def _body(request: Request, code: str, message: str, details: dict) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


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
