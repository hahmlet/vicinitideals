"""FastAPI app entrypoint for the re-modeling CRUD and compute API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app as _pkg
from app.api.routers import ROUTERS

_PROCESS_STARTED_AT = __import__("time").time()
from app.config import settings
from app.observability import (
    PROCESS_TIME_HEADER,
    TRACE_HEADER,
    begin_observation,
    elapsed_ms,
    log_observation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths that don't require an API key (UI pages, static assets, health)
# ---------------------------------------------------------------------------
_UI_PATH_PREFIXES = (
    "/static/",
    "/deals",
    "/models/",
    "/buildings",
    "/opportunities",
    "/parcels",
    "/listings",
    "/portfolios",
    "/brokers",
    "/dedup",
    "/settings",
    "/ui/",
    "/ui/panel/",
    "/health",
    "/api/",  # HTMX calls from browser templates don't carry an API key
    "/tools/",
    "/login",
    "/logout",
    "/register",
    "/profile",
)

# Paths that don't require an authenticated session (public)
_AUTH_EXEMPT_PATHS = (
    "/static/",
    "/health",
    "/login",
    "/logout",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/api/",
)

STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    500: "internal_server_error",
}


def _payload(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


def _resolve_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client is not None:
        return request.client.host
    return None


def _is_ui_path(path: str) -> bool:
    """Return True if the path should be served without an API key."""
    return path == "/" or any(path.startswith(p) for p in _UI_PATH_PREFIXES)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    from app.sentry_setup import init_sentry
    init_sentry()

    _static_dir = Path(_pkg.__file__).parent / "static"

    app = FastAPI(
        title="re-modeling API",
        version="0.1.0",
        summary="CRUD and compute endpoints for real estate deal modeling.",
    )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_payload(
                "internal_server_error",
                "An unexpected server error occurred.",
                None,
            ),
        )

    @app.exception_handler(FastAPIHTTPException)
    async def handle_http_exception(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(exc.status_code)
        if code is None:
            code = "client_error" if exc.status_code < 500 else "server_error"

        message = exc.detail if isinstance(exc.detail, str) else str(exc.status_code)
        detail = exc.detail if not isinstance(exc.detail, str) else None
        return JSONResponse(status_code=exc.status_code, content=_payload(code, message, detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"][1:]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_payload("validation_error", "Request validation failed", errors),
        )

    @app.middleware("http")
    async def validate_user_id_header(request: Request, call_next):
        if request.headers.get("X-API-Key") != settings.vicinitideals_api_key:
            return await call_next(request)
        if _is_ui_path(request.url.path):
            return await call_next(request)

        header_value = request.headers.get("X-User-ID")
        if not header_value:
            return JSONResponse(
                status_code=400,
                content=_payload("bad_request", "Missing X-User-ID header", None),
            )

        try:
            request.state.user_id = str(UUID(header_value))
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=_payload("bad_request", "Invalid X-User-ID header", None),
            )

        return await call_next(request)

    @app.middleware("http")
    async def validate_api_key_header(request: Request, call_next):
        if _is_ui_path(request.url.path):
            return await call_next(request)
        api_key = request.headers.get("X-API-Key")
        if api_key != settings.vicinitideals_api_key:
            return JSONResponse(
                status_code=403,
                content=_payload("forbidden", "Invalid API key", None),
            )
        return await call_next(request)

    @app.middleware("http")
    async def attach_observability_headers(request: Request, call_next):
        trace_id, _, started_at_monotonic = begin_observation(request.headers.get(TRACE_HEADER))
        request.state.trace_id = trace_id
        client_ip = _resolve_client_ip(request)
        user_id = request.headers.get("X-User-ID")

        log_observation(
            logger,
            "api_request_started",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
            user_id=user_id,
        )

        response = await call_next(request)

        duration_ms = elapsed_ms(started_at_monotonic)
        response.headers[TRACE_HEADER] = trace_id
        response.headers[PROCESS_TIME_HEADER] = str(duration_ms)
        log_observation(
            logger,
            "api_request_completed",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=client_ip,
            user_id=getattr(request.state, "user_id", None) or user_id,
        )
        return response

    @app.get("/health")
    async def healthcheck() -> dict[str, Any]:
        return _payload("ok", "re-modeling API is healthy", {
            "status": "ok",
            "started_at": _PROCESS_STARTED_AT,
            "version": _pkg.__version__ if hasattr(_pkg, "__version__") else "0.1.0",
        })

    @app.middleware("http")
    async def require_auth_for_ui(request: Request, call_next):
        """Redirect unauthenticated browser requests to /login.

        Exempts: auth pages, static assets, /health, /api/* (HTMX calls carry
        the session cookie from the browser context so they're fine).
        HTMX fragment requests (hx-request header) are allowed through so
        partial swaps don't redirect mid-page.
        """
        path = request.url.path
        is_exempt = any(path.startswith(p) for p in _AUTH_EXEMPT_PATHS) or path == "/"
        is_htmx = request.headers.get("hx-request") == "true"
        if is_exempt or is_htmx:
            return await call_next(request)

        from app.api.auth import decode_session_token, COOKIE_NAME
        token = request.cookies.get(COOKIE_NAME)
        # Also accept legacy vd_user_id cookie so existing sessions aren't broken
        if token and decode_session_token(token) is not None:
            return await call_next(request)
        if request.cookies.get("vd_user_id"):
            return await call_next(request)

        from fastapi.responses import RedirectResponse as _RR
        return _RR(url=f"/login?next={request.url.path}", status_code=303)

    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    # Auth router — login, logout, register, profile
    from app.api.routers.auth_routes import router as auth_router
    app.include_router(auth_router)

    # UI router — HTML pages, no API key required
    from app.api.routers.ui import router as ui_router
    app.include_router(ui_router)

    # Tools router — internal tooling pages (zone painter, etc.), no /api prefix
    from app.api.routers.tools import router as tools_router
    app.include_router(tools_router)

    # Static files (CSS, etc.) — must be mounted after routes
    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    return app


app = create_app()

__all__ = ["app", "create_app"]
