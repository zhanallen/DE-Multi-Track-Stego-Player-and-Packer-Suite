"""Unified API error type and handlers producing ``{"error": {code, message}}``."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Raised by services/routers; rendered with the contract error format."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def build_error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def _render_api_error(_request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(build_error_body(error.code, error.message), status_code=error.status_code)


async def _render_http_error(_request: Request, error: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if error.status_code == 404 else f"http_{error.status_code}"
    return JSONResponse(build_error_body(code, str(error.detail)), status_code=error.status_code)


async def _render_validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(build_error_body("validation_error", str(error.errors())), status_code=422)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _render_api_error)
    app.add_exception_handler(StarletteHTTPException, _render_http_error)
    app.add_exception_handler(RequestValidationError, _render_validation_error)
