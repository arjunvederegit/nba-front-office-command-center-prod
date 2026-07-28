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


class InvalidTradeError(DomainError):
    """The trade as constructed cannot exist — a phantom move, a duplicate, a bad enum.

    422 rather than 400 so it lands in the same class as Pydantic's own request
    validation from a caller's point of view; the difference is only that these checks
    need a database session and therefore cannot live in a request model.
    """

    status_code = 422
    code = "validation_error"


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


def _field_path(location: tuple) -> str:
    """`('body', 'pick_moves', 4, 'draft_year')` → `pick_moves[4].draft_year`."""
    parts: list[str] = []
    for item in location:
        if item in ("body", "query", "path", "header"):
            continue
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{item}]"
            else:
                parts.append(f"[{item}]")
        else:
            parts.append(f".{item}" if parts else str(item))
    return "".join(parts) or "request body"


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """QA-13: the body used to carry `str(exc.errors())` verbatim, leaking Pydantic
    internals — `{'type': 'less_than_equal', 'loc': (...), 'ctx': {'le': 2033}}` — into
    a field a user reads. Errors are mapped to `{field, message}` pairs; the structured
    list is added alongside the flat `message` so the `{code, message, request_id}`
    contract is preserved rather than replaced."""
    assert isinstance(exc, RequestValidationError)
    fields = [
        {"field": _field_path(tuple(err.get("loc", ()))), "message": err.get("msg", "invalid")}
        for err in exc.errors()[:5]
    ]
    message = "; ".join(f"{f['field']}: {f['message']}" for f in fields) or "invalid request"
    body = error_body("validation_error", message, request)
    body["error"]["fields"] = fields
    return JSONResponse(status_code=422, content=body)
