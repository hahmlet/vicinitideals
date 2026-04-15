"""Auth routes — login, logout, register, profile.

These routes are mounted without the /api prefix (see main.py).
They serve HTML pages and set/clear the vd_session HttpOnly cookie.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

import app as _pkg
from app.api.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.api.deps import DBSession
from app.api.rate_limit import check_rate_limit
from app.config import settings
from app.emails import (
    load_email_verification_token,
    load_password_reset_token,
    make_email_verification_token,
    make_password_reset_token,
    send_password_reset_email,
    send_verification_email,
)
from app.models.org import Organization, User

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

_TEMPLATES_DIR = Path(_pkg.__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# GET /login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_get(
    request: Request,
    error: str = Query(default=""),
    next: str = Query(default="/deals"),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error, "next": next},
    )


# ---------------------------------------------------------------------------
# POST /login
# ---------------------------------------------------------------------------

@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    session: DBSession,
    next: str = Query(default="/deals"),
) -> Response:
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))

    if not email or not password:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Email and password are required.", "next": next},
            status_code=400,
        )

    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if user is None or not user.hashed_password:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password.", "next": next},
            status_code=401,
        )

    if not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password.", "next": next},
            status_code=401,
        )

    if not user.is_active:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Account is disabled. Contact your administrator.", "next": next},
            status_code=403,
        )

    # Update last_login
    user.last_login = datetime.now(UTC)
    await session.commit()

    token = create_session_token(user.id)
    resp = RedirectResponse(url=next, status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return resp


# ---------------------------------------------------------------------------
# POST /logout
# ---------------------------------------------------------------------------

@router.get("/logout")
@router.post("/logout")
async def logout() -> RedirectResponse:
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ---------------------------------------------------------------------------
# GET /register
# ---------------------------------------------------------------------------

@router.get("/register", response_class=HTMLResponse)
async def register_get(
    request: Request,
    error: str = Query(default=""),
) -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {"error": error})


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------

@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    session: DBSession,
) -> Response:
    form = await request.form()
    name = str(form.get("name", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    password_confirm = str(form.get("password_confirm", ""))

    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": msg, "name": name, "email": email},
            status_code=400,
        )

    if not name or not email or not password:
        return _err("All fields are required.")

    if password != password_confirm:
        return _err("Passwords do not match.")

    if len(password) < 8:
        return _err("Password must be at least 8 characters.")

    # Check email uniqueness
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        return _err("An account with that email already exists.")

    # Resolve org — use first org or create one
    org = (
        await session.execute(select(Organization).order_by(Organization.created_at))
    ).scalars().first()
    if org is None:
        org = Organization(
            id=uuid.uuid4(),
            name="Default Organization",
            slug=f"org-{uuid.uuid4().hex[:8]}",
        )
        session.add(org)
        await session.flush()

    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name=name,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
        email_verified=False,
    )
    session.add(user)
    await session.commit()

    # Fire-and-forget verification email — delivery failure does NOT block
    # registration; the user can always hit "Resend verification" later.
    verify_token = make_email_verification_token(user.id)
    verify_url = f"{settings.app_base_url}/verify-email?token={verify_token}"
    try:
        await send_verification_email(to=email, name=name, verify_url=verify_url)
    except Exception:  # pragma: no cover — logged inside sender
        pass

    # Soft gate: user is logged in immediately and sees an "unverified" banner
    # until they click the link.  Verification is required only for flows
    # that explicitly check user.email_verified.
    token = create_session_token(user.id)
    resp = RedirectResponse(url="/deals", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return resp


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------

@router.get("/profile", response_class=HTMLResponse)
async def profile_get(
    request: Request,
    session: DBSession,
) -> Response:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login?next=/profile", status_code=303)
    return templates.TemplateResponse(request, "profile.html", {"user": user})


# ===========================================================================
# Email verification
# ===========================================================================

# ---------------------------------------------------------------------------
# GET /verify-email?token=...
# ---------------------------------------------------------------------------

@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_get(
    request: Request,
    session: DBSession,
    token: str = Query(default=""),
) -> Response:
    """Land the user from an email verification link.

    Idempotent: clicking the link twice just shows the already-verified page.
    """
    if not token:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Missing token",
                "message": "This verification link is missing its token.",
                "success": False,
            },
            status_code=400,
        )

    user_id = load_email_verification_token(token)
    if user_id is None:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Link expired or invalid",
                "message": (
                    "This verification link is invalid or has expired. "
                    "Log in and click 'Resend verification' to get a new one."
                ),
                "success": False,
            },
            status_code=400,
        )

    user = await session.get(User, user_id)
    if user is None:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Account not found",
                "message": "No account found for this verification link.",
                "success": False,
            },
            status_code=404,
        )

    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.now(UTC)
        await session.commit()

    return templates.TemplateResponse(
        request,
        "auth_message.html",
        {
            "title": "Email verified",
            "message": (
                f"Thanks, {user.name}. Your email is verified — "
                "you can close this tab or continue to the app."
            ),
            "success": True,
            "next_url": "/deals",
            "next_label": "Go to deals",
        },
    )


# ---------------------------------------------------------------------------
# POST /resend-verification
# ---------------------------------------------------------------------------

@router.post("/resend-verification")
async def resend_verification_post(
    request: Request,
    session: DBSession,
) -> Response:
    """Re-send the verification email for the currently-logged-in user."""
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    if user.email_verified:
        return RedirectResponse(url="/profile?verified=1", status_code=303)

    if not user.email:
        return RedirectResponse(url="/profile?error=no-email", status_code=303)

    verify_token = make_email_verification_token(user.id)
    verify_url = f"{settings.app_base_url}/verify-email?token={verify_token}"
    try:
        await send_verification_email(
            to=user.email, name=user.name, verify_url=verify_url
        )
    except Exception:  # pragma: no cover — logged in sender
        pass

    return RedirectResponse(url="/profile?verification_sent=1", status_code=303)


# ===========================================================================
# Password reset
# ===========================================================================

# ---------------------------------------------------------------------------
# GET /forgot-password
# ---------------------------------------------------------------------------

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_get(
    request: Request,
    sent: int = Query(default=0),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        {"sent": bool(sent)},
    )


# ---------------------------------------------------------------------------
# POST /forgot-password
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    """Best-effort client IP, trusting X-Forwarded-For from the NGINX proxy."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# Rate limit policy: 5 requests per IP per 15 min + 3 per email per hour.
# Both checks must pass; the tighter per-email window protects individual
# mailboxes from being spammed, and the per-IP window protects the sender
# reputation / Resend bill from a single attacker.
_RL_IP_MAX = 5
_RL_IP_WINDOW = 15 * 60       # 15 min
_RL_EMAIL_MAX = 3
_RL_EMAIL_WINDOW = 60 * 60    # 1 hour


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    session: DBSession,
) -> Response:
    """Send a password reset link.

    Always returns the same "we sent a link if the account exists" message
    regardless of whether the email matched a real account, to prevent
    enumeration attacks.  Misses are logged server-side at INFO level so
    the admin can see them in the container logs.

    Rate-limited per IP (5/15min) and per email (3/hour).  On limit
    exceeded the user gets the same confirmation — the attacker cannot
    distinguish "rate limited" from "email exists".
    """
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    ip = _client_ip(request)

    # ── Rate limit: per-IP window ────────────────────────────────────────
    ip_allowed = await check_rate_limit(
        key=f"forgot_pw:ip:{ip}",
        max_count=_RL_IP_MAX,
        window_seconds=_RL_IP_WINDOW,
    )
    if not ip_allowed:
        logger.warning(
            "forgot_password rate-limited ip=%s email=%s (per-IP bucket exceeded)",
            ip, email or "(empty)"
        )
        return RedirectResponse(url="/forgot-password?sent=1", status_code=303)

    # ── Rate limit: per-email window (only if email non-empty) ───────────
    if email:
        email_allowed = await check_rate_limit(
            key=f"forgot_pw:email:{email}",
            max_count=_RL_EMAIL_MAX,
            window_seconds=_RL_EMAIL_WINDOW,
        )
        if not email_allowed:
            logger.warning(
                "forgot_password rate-limited ip=%s email=%s (per-email bucket exceeded)",
                ip, email
            )
            return RedirectResponse(url="/forgot-password?sent=1", status_code=303)

    # ── Actual lookup + send ─────────────────────────────────────────────
    # Note: we log misses at WARNING level (not INFO) so they surface in
    # default container log output without needing a logging config change.
    # Successful sends are intentionally NOT logged — success is the
    # boring common case and clutters the log.
    if email:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is not None and user.hashed_password and user.is_active:
            reset_token = make_password_reset_token(user.id, user.hashed_password)
            reset_url = f"{settings.app_base_url}/reset-password?token={reset_token}"
            try:
                await send_password_reset_email(
                    to=user.email or email,
                    name=user.name,
                    reset_url=reset_url,
                )
            except Exception:  # pragma: no cover — logged in sender
                pass
        else:
            # Server-side miss logging — user sees the same confirmation
            # regardless, but we as admins can see failed attempts in the
            # container logs for debugging (e.g. typos, unknown accounts).
            reason = (
                "user_not_found" if user is None
                else "no_password_set" if not user.hashed_password
                else "account_disabled"
            )
            logger.warning("forgot_password miss ip=%s email=%s reason=%s", ip, email, reason)
    else:
        logger.warning("forgot_password: empty email submitted ip=%s", ip)

    # Always show the same confirmation regardless of whether the email existed
    return RedirectResponse(url="/forgot-password?sent=1", status_code=303)


# ---------------------------------------------------------------------------
# GET /reset-password?token=...
# ---------------------------------------------------------------------------

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_get(
    request: Request,
    session: DBSession,
    token: str = Query(default=""),
) -> Response:
    """Show the new-password form if the token is valid, else an error page."""
    if not token:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Missing token",
                "message": "This password reset link is missing its token.",
                "success": False,
            },
            status_code=400,
        )

    # We can't fully validate without loading the user's current password
    # hash (the token is bound to it), so decode without the hash check first
    # just to extract the user id.  The full validation happens in POST.
    try:
        from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
        signer = URLSafeTimedSerializer(settings.secret_key, salt="password-reset")
        raw = signer.loads(
            token,
            max_age=settings.password_reset_token_max_age_seconds,
        )
    except (SignatureExpired, BadSignature):
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Link expired",
                "message": (
                    "This password reset link has expired or is invalid. "
                    "Request a new one from the forgot-password page."
                ),
                "success": False,
                "next_url": "/forgot-password",
                "next_label": "Request new link",
            },
            status_code=400,
        )

    # Token is signature-valid; render the form (final hash-bind check happens on POST)
    return templates.TemplateResponse(
        request,
        "reset_password.html",
        {"token": token, "error": ""},
    )


# ---------------------------------------------------------------------------
# POST /reset-password
# ---------------------------------------------------------------------------

@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_post(
    request: Request,
    session: DBSession,
) -> Response:
    form = await request.form()
    token = str(form.get("token", ""))
    password = str(form.get("password", ""))
    password_confirm = str(form.get("password_confirm", ""))

    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {"token": token, "error": msg},
            status_code=400,
        )

    if not token:
        return _err("Missing reset token.")

    if not password or not password_confirm:
        return _err("Both password fields are required.")

    if password != password_confirm:
        return _err("Passwords do not match.")

    if len(password) < 8:
        return _err("Password must be at least 8 characters.")

    # Decode the token's user_id first (unbinding from password hash) so we
    # can look up the user, then do the bound validation.
    try:
        from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
        signer = URLSafeTimedSerializer(settings.secret_key, salt="password-reset")
        raw = signer.loads(
            token,
            max_age=settings.password_reset_token_max_age_seconds,
        )
    except (SignatureExpired, BadSignature):
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Link expired",
                "message": "This password reset link has expired. Request a new one.",
                "success": False,
                "next_url": "/forgot-password",
                "next_label": "Request new link",
            },
            status_code=400,
        )

    if ":" not in raw:
        return _err("Invalid token.")
    user_id_str, _prefix = raw.split(":", 1)
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        return _err("Invalid token.")

    user = await session.get(User, user_id)
    if user is None or not user.hashed_password:
        return _err("Account not found.")

    # Now do the full bound validation against the current password hash
    bound_id = load_password_reset_token(token, user.hashed_password)
    if bound_id != user.id:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Link already used",
                "message": (
                    "This reset link has already been used or the password "
                    "has been changed since it was issued. Request a new "
                    "link to reset again."
                ),
                "success": False,
                "next_url": "/forgot-password",
                "next_label": "Request new link",
            },
            status_code=400,
        )

    # Apply the new password + also mark email verified if it wasn't already
    # (clicking a reset link proves the user owns the mailbox).
    user.hashed_password = hash_password(password)
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = datetime.now(UTC)
    await session.commit()

    # Log them in and redirect
    session_token = create_session_token(user.id)
    resp = RedirectResponse(url="/deals", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return resp
