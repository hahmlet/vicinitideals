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
    "/favicon.ico",
    "/deals",
    "/models/",
    "/opportunities",
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
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/resend-verification",
    "/mock/",
    "/onboarding",
    "/pending-approval",
)

# Paths that don't require an authenticated session (public)
_AUTH_EXEMPT_PATHS = (
    "/static/",
    "/favicon.ico",
    "/health",
    "/login",
    "/logout",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/api/",
)

# Paths an authenticated-but-unverified user may still access so they
# can complete verification, finish onboarding, or sign out. Anything
# outside this list (and not already in _AUTH_EXEMPT_PATHS) is gated.
_EMAIL_VERIFICATION_EXEMPT_PATHS = (
    "/verify-email",
    "/verify-email-required",
    "/resend-verification",
    "/profile",
    "/logout",
    "/onboarding",
    "/pending-approval",
    "/invites/",
)

STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_server_error",
}


def _payload(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


def _resolve_client_ip(request: Request) -> str | None:
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client is not None:
        return request.client.host
    return None


def _is_ui_path(path: str) -> bool:
    """Return True if the path should be served without an API key."""
    return path == "/" or any(path.startswith(p) for p in _UI_PATH_PREFIXES)


class _NoCacheHTMLMiddleware:
    """ASGI middleware: add Cache-Control: no-store to all HTML page responses.

    Prevents browsers from serving stale authenticated page content from cache
    after logout (back-button attack).  Intercepts at the raw ASGI
    http.response.start event so the header is reliably injected before any
    bytes reach the client, regardless of how many BaseHTTPMiddleware layers
    surround this middleware.

    HTMX fragment requests are exempt — they are ephemeral partials, not
    full-page snapshots that a browser would cache and replay.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_htmx = any(
            name.lower() == b"hx-request" and value == b"true"
            for name, value in scope.get("headers", [])
        )

        if is_htmx:
            await self.app(scope, receive, send)
            return

        async def send_with_no_cache(message: Any) -> None:
            if message["type"] == "http.response.start":
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                content_type = next(
                    (v.decode() for n, v in raw_headers if n.lower() == b"content-type"),
                    "",
                )
                if "text/html" in content_type:
                    raw_headers = [
                        (n, v) for n, v in raw_headers
                        if n.lower() not in (b"cache-control", b"pragma")
                    ]
                    raw_headers.append((b"cache-control", b"no-store"))
                    raw_headers.append((b"pragma", b"no-cache"))
                    message = {**message, "headers": raw_headers}
            await send(message)

        await self.app(scope, receive, send_with_no_cache)


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

        from app.api.auth import COOKIE_NAME, decode_session_email_verified, decode_session_token
        token = request.cookies.get(COOKIE_NAME)
        # Also accept legacy vd_user_id cookie so existing sessions aren't broken
        if token and decode_session_token(token) is not None:
            # Hard email-verification gate. Legacy UUID-only tokens have no
            # claim → bypass (back-compat). Modern signed sessions with
            # ev=False are bounced to the recovery page unless the path is
            # in the verification-exempt list.
            email_verified_claim = decode_session_email_verified(token)
            if email_verified_claim is False and not any(
                path.startswith(p) for p in _EMAIL_VERIFICATION_EXEMPT_PATHS
            ):
                from urllib.parse import quote

                requested_path = request.url.path
                if request.url.query:
                    requested_path = f"{requested_path}?{request.url.query}"
                next_url = quote(requested_path, safe="")
                from fastapi.responses import RedirectResponse as _RR
                return _RR(
                    url=f"/verify-email-required?next={next_url}",
                    status_code=303,
                )
            return await call_next(request)
        if request.cookies.get("vd_user_id"):
            return await call_next(request)

        from fastapi.responses import RedirectResponse as _RR
        return _RR(url=f"/login?next={request.url.path}", status_code=303)

    app.add_middleware(_NoCacheHTMLMiddleware)

    # -----------------------------------------------------------------------
    # Onboarding guard — redirect authenticated users who haven't finished
    # org setup or are pending approval to the appropriate page.
    # -----------------------------------------------------------------------
    _ONBOARDING_GUARD_EXEMPT = (
        "/static/",
        "/favicon.ico",
        "/health",
        "/login",
        "/logout",
        "/register",
        "/forgot-password",
        "/reset-password",
        "/verify-email",
        "/resend-verification",
        "/onboarding",
        "/pending-approval",
        "/api/",
        "/ui/onboarding",
    )

    @app.middleware("http")
    async def onboarding_guard(request: Request, call_next):
        path = request.url.path
        is_exempt = any(path.startswith(p) for p in _ONBOARDING_GUARD_EXEMPT) or path == "/"
        is_htmx = request.headers.get("hx-request") == "true"
        if is_exempt or is_htmx:
            return await call_next(request)

        from app.api.auth import decode_session_token, COOKIE_NAME
        from fastapi.responses import RedirectResponse as _RR

        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return await call_next(request)
        user_id = decode_session_token(token)
        if user_id is None:
            return await call_next(request)

        from app.db import AsyncSessionLocal
        from app.models.org import MembershipStatus, User as _User
        async with AsyncSessionLocal() as db:
            user = await db.get(_User, user_id)

        if user is None or not user.is_active:
            return await call_next(request)
        if user.org_id is None:
            return _RR(url="/onboarding", status_code=303)
        if user.membership_status == MembershipStatus.PENDING:
            return _RR(url="/pending-approval", status_code=303)

        return await call_next(request)

    # -----------------------------------------------------------------------
    # CSRF protection — validates X-CSRF-Token on all state-mutating requests
    # except auth-flow paths (login, register, forgot-password, etc.).
    # Sets request.state.csrf_token so templates can inject the token into
    # HTMX's hx-headers attribute on the <body> tag.
    # NOTE: intentionally does NOT exempt /api/ — HTMX routes under /api/ are
    # the primary surface this protection covers.
    # -----------------------------------------------------------------------
    _CSRF_EXEMPT_PATHS = (
        "/static/",
        "/favicon.ico",
        "/health",
        "/login",
        "/logout",
        "/register",
        "/forgot-password",
        "/reset-password",
        "/verify-email",
        "/resend-verification",
    )
    _MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    @app.middleware("http")
    async def csrf_protection(request: Request, call_next):
        from app.api.auth import decode_session_token, COOKIE_NAME
        from app.api.csrf import make_csrf_token, validate_csrf_token, CSRF_HEADER

        # Resolve the authenticated user ID (if any) from the session cookie.
        # Also accepts the legacy vd_user_id cookie so existing sessions still work.
        import uuid as _uuid
        token = request.cookies.get(COOKIE_NAME)
        user_id = decode_session_token(token) if token else None
        if user_id is None:
            legacy = request.cookies.get("vd_user_id")
            if legacy:
                try:
                    user_id = _uuid.UUID(legacy)
                except ValueError:
                    pass
        user_id_str = str(user_id) if user_id else None

        # Always expose the token to templates (empty string when unauthenticated).
        request.state.csrf_token = make_csrf_token(user_id_str) if user_id_str else ""

        # Validate CSRF token on HTMX-initiated mutating requests only.
        # Plain form POSTs and vanilla fetch calls from non-HTMX code are
        # protected by SameSite=Lax session cookies (cross-site POSTs can't
        # carry the session cookie).  HTMX requests carry hx-request:true,
        # a custom header that cross-site attackers cannot set (blocked by
        # CORS preflight), giving us a second CSRF signal.
        is_htmx = request.headers.get("hx-request") == "true"
        path = request.url.path
        is_exempt = any(path.startswith(p) for p in _CSRF_EXEMPT_PATHS) or path == "/"
        if is_htmx and request.method in _MUTATING and not is_exempt:
            if user_id_str is None:
                # Unauthenticated mutating request — let downstream auth handle it.
                return await call_next(request)
            presented = request.headers.get(CSRF_HEADER)
            if not validate_csrf_token(presented, user_id_str):
                return JSONResponse(
                    status_code=403,
                    content=_payload("forbidden", "CSRF token invalid or missing", None),
                )

        return await call_next(request)

    # -----------------------------------------------------------------------
    # Write rate limiting — caps POST/PUT/PATCH/DELETE per user (or IP when
    # unauthenticated) to prevent automated abuse.
    #   Authenticated:   200 writes / minute per user
    #   Unauthenticated: 30 writes / minute per IP
    # -----------------------------------------------------------------------
    @app.middleware("http")
    async def write_rate_limit(request: Request, call_next):
        if request.method not in _MUTATING:
            return await call_next(request)

        from app.api.auth import decode_session_token, COOKIE_NAME
        from app.api.rate_limit import check_rate_limit

        token = request.cookies.get(COOKIE_NAME)
        user_id = decode_session_token(token) if token else None

        if user_id:
            rl_key = f"write_rl:user:{user_id}"
            allowed = await check_rate_limit(rl_key, max_count=200, window_seconds=60)
        else:
            client_ip = _resolve_client_ip(request) or "unknown"
            rl_key = f"write_rl:ip:{client_ip}"
            allowed = await check_rate_limit(rl_key, max_count=30, window_seconds=60)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content=_payload("too_many_requests", "Too many requests — slow down and try again.", None),
                headers={"Retry-After": "60"},
            )

        return await call_next(request)

    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    # Auth router — login, logout, register, profile
    from app.api.routers.auth_routes import router as auth_router
    app.include_router(auth_router)

    # UI router — HTML pages, no API key required
    from app.api.routers.ui import router as ui_router
    app.include_router(ui_router)

    # Settings/billing/vehicle sub-router (Phase 2a split)
    from app.api.routers.ui_settings import router as ui_settings_router
    app.include_router(ui_settings_router)

    # Listings/brokers/dedup sub-router (Phase 2a split)
    from app.api.routers.ui_data_intel import router as ui_data_intel_router
    app.include_router(ui_data_intel_router)

    # Portfolios + saved-filters sub-router (Phase 2a split)
    from app.api.routers.ui_portfolios import router as ui_portfolios_router
    app.include_router(ui_portfolios_router)

    # Deals pipeline + opportunities sub-router (Phase 2a split)
    from app.api.routers.ui_deals_pipeline import router as ui_deals_pipeline_router
    app.include_router(ui_deals_pipeline_router)

    # Model outputs sub-router (Phase 2a split)
    from app.api.routers.ui_model_outputs import router as ui_model_outputs_router
    app.include_router(ui_model_outputs_router)

    # Email ingest UI router — inbox and review pages, no /api prefix
    from app.api.routers.email_ingest import ui_router as email_ingest_ui_router
    app.include_router(email_ingest_ui_router)

    # Static files (CSS, etc.) — must be mounted after routes
    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    return app


app = create_app()

__all__ = ["app", "create_app"]
