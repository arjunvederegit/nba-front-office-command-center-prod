"""TradeLab API application."""

import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1 import assets, comparisons, health, players, scenarios, teams, trades
from app.config import get_settings
from app.core.errors import (
    DomainError,
    domain_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(
    title="TradeLab: NBA Trade Deadline Decision Room",
    version=__version__,
    description=(
        "Decision-support API for exploratory NBA trade analysis. Basketball data: "
        "NBA.com via the `nba_api` package, with full provenance. This is an "
        "analytical portfolio project, not an official NBA cap-management product."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Simple in-process rate limiter (per client IP, sliding minute window). A demo-scale
# guard, not a substitute for infrastructure rate limiting in production.
_request_log: dict[str, deque] = defaultdict(deque)
RATE_LIMIT_PER_MINUTE = 600


@app.middleware("http")
def observability(request: Request, call_next):
    async def run():
        request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:8])
        request.state.request_id = request_id

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        # Asset serving (photos/logos) is cheap, cacheable, and fired dozens of times
        # per page — it is exempt from the API rate window.
        is_asset = request.url.path.startswith(f"{API}/assets/")
        if is_asset:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        # `_request_log` is a defaultdict, so reading it for an exempt request still
        # created a permanent key: asset traffic grew the dict the exemption was
        # supposed to keep it out of. The exemption now returns before the read.
        window = _request_log[client_ip]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                        "request_id": request_id,
                    }
                },
            )
        window.append(now)

        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        return response

    return run()


app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

API = "/api/v1"
app.include_router(health.router, prefix=API)
app.include_router(teams.router, prefix=API)
app.include_router(players.router, prefix=API)
app.include_router(scenarios.router, prefix=API)
app.include_router(trades.router, prefix=API)
app.include_router(comparisons.router, prefix=API)
app.include_router(assets.router, prefix=API)


@app.get("/")
def root() -> dict:
    return {
        "name": "TradeLab API",
        "version": __version__,
        "docs": "/docs",
        "data_health": f"{API}/data-health",
    }
