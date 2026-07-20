"""Deterministic API error format.

Every error response body is: {"error": {"code": str, "message": str, "request_id": str}}
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class DataUnavailableError(DomainError):
    """Raised when required provider-backed data is missing; never guessed around."""

    status_code = 409
    code = "data_unavailable"


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def error_body(code: str, message: str, request: Request) -> dict:
    return {"error": {"code": code, "message": message, "request_id": _request_id(request)}}


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(
        status_code=exc.status_code, content=error_body(exc.code, exc.message, request)
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body("http_error", str(exc.detail), request),
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", str(exc.errors()[:5]), request),
    )
