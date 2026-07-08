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
    load_invite_token,
    load_password_reset_token,
    make_email_verification_token,
    make_password_reset_token,
    send_password_reset_email,
    send_verification_email,
)
from app.models.org import MembershipStatus, Organization, User

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

    # Route based on onboarding state
    if user.org_id is None:
        next = "/onboarding"
    elif user.membership_status == MembershipStatus.PENDING:
        next = "/pending-approval"

    token = create_session_token(user.id, email_verified=bool(user.email_verified))
    resp = RedirectResponse(url=next, status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
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
    session: DBSession,
    error: str = Query(default=""),
    org: str = Query(default=""),       # org slug — join via hard link
    invite: str = Query(default=""),    # invite token — join via email invite
) -> HTMLResponse:
    join_org = None
    prefill_email = ""

    if invite:
        result = load_invite_token(invite)
        if result is None:
            return templates.TemplateResponse(
                request,
                "auth_message.html",
                {
                    "title": "Invite expired",
                    "message": "This invite link has expired or is invalid. Ask your admin to send a new one.",
                    "success": False,
                },
                status_code=400,
            )
        org_id, prefill_email = result
        join_org = await session.get(Organization, org_id)
    elif org:
        join_org = (
            await session.execute(select(Organization).where(Organization.slug == org))
        ).scalar_one_or_none()
        if join_org is None:
            return templates.TemplateResponse(
                request,
                "auth_message.html",
                {
                    "title": "Organization not found",
                    "message": "This invite link is no longer valid.",
                    "success": False,
                },
                status_code=404,
            )

    return templates.TemplateResponse(
        request,
        "register.html",
        {
            "error": error,
            "join_org": join_org,
            "prefill_email": prefill_email,
            "invite_token": invite,
            "org_slug": org,
        },
    )


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
    invite_token = str(form.get("invite_token", "")).strip()
    org_slug = str(form.get("org_slug", "")).strip()

    def _err(msg: str, join_org: Organization | None = None, prefill_email: str = "") -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "register.html",
            {
                "error": msg,
                "name": name,
                "email": email,
                "join_org": join_org,
                "prefill_email": prefill_email,
                "invite_token": invite_token,
                "org_slug": org_slug,
            },
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

    # Determine if joining an existing org
    join_org: Organization | None = None
    if invite_token:
        result = load_invite_token(invite_token)
        if result is None:
            return _err("This invite link has expired. Ask your admin to send a new one.")
        org_id, invited_email = result
        if email.strip().lower() != invited_email.strip().lower():
            return _err("This invite link is for a different email address.")
        from app.models.org import OrgInvite as _OrgInvite
        invite_row = (
            await session.execute(
                select(_OrgInvite).where(_OrgInvite.token == invite_token)
            )
        ).scalar_one_or_none()
        if invite_row is not None and invite_row.accepted_at is not None:
            return _err("This invite link has already been used.")
        join_org = await session.get(Organization, org_id)
        if join_org is None:
            return _err("The organization for this invite no longer exists.")
    elif org_slug:
        join_org = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if join_org is None:
            return _err("Organization not found.")

    if join_org:
        # Joining existing org — create as pending, await admin approval
        user = User(
            id=uuid.uuid4(),
            org_id=join_org.id,
            name=name,
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            is_org_admin=False,
            membership_status=MembershipStatus.ACTIVE if invite_token else MembershipStatus.PENDING,
            email_verified=False,
        )
        session.add(user)
        await session.commit()

        # Mark invite accepted if this was a tokenized invite
        if invite_token:
            from app.models.org import OrgInvite
            invite_rec = (
                await session.execute(
                    select(OrgInvite).where(OrgInvite.token == invite_token)
                )
            ).scalar_one_or_none()
            if invite_rec and invite_rec.accepted_at is None:
                invite_rec.accepted_at = datetime.now(UTC)
                await session.commit()

        verify_token = make_email_verification_token(user.id)
        verify_url = f"{settings.app_base_url}/verify-email?token={verify_token}"
        try:
            await send_verification_email(to=email, name=name, verify_url=verify_url)
        except Exception:  # pragma: no cover
            pass

        token = create_session_token(user.id, email_verified=False)
        resp = RedirectResponse(url="/deals" if invite_token else "/pending-approval", status_code=303)
        resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_MAX_AGE, httponly=True, secure=True, samesite="lax")
        return resp
    else:
        # New user, no org yet — redirect to onboarding wizard
        user = User(
            id=uuid.uuid4(),
            org_id=None,
            name=name,
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            is_org_admin=False,
            membership_status=MembershipStatus.ACTIVE,
            email_verified=False,
        )
        session.add(user)
        await session.commit()

        verify_token = make_email_verification_token(user.id)
        verify_url = f"{settings.app_base_url}/verify-email?token={verify_token}"
        try:
            await send_verification_email(to=email, name=name, verify_url=verify_url)
        except Exception:  # pragma: no cover
            pass

        token = create_session_token(user.id, email_verified=False)
        resp = RedirectResponse(url="/onboarding", status_code=303)
        resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_MAX_AGE, httponly=True, secure=True, samesite="lax")
        return resp


# ---------------------------------------------------------------------------
# GET /pending-approval
# ---------------------------------------------------------------------------

@router.get("/pending-approval", response_class=HTMLResponse)
async def pending_approval_get(
    request: Request,
    session: DBSession,
) -> Response:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.membership_status != MembershipStatus.PENDING:
        return RedirectResponse(url="/deals", status_code=303)
    org = await session.get(Organization, user.org_id) if user.org_id else None
    return templates.TemplateResponse(
        request,
        "pending_approval.html",
        {"user": user, "org": org},
    )


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

    resp = templates.TemplateResponse(
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
    # Re-issue the session cookie with the verified claim so the user
    # passes the middleware gate without needing to log in again.
    resp.set_cookie(
        COOKIE_NAME,
        create_session_token(user.id, email_verified=True),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return resp


# ---------------------------------------------------------------------------
# GET /verify-email-required
# ---------------------------------------------------------------------------

@router.get("/verify-email-required", response_class=HTMLResponse)
async def verify_email_required_get(
    request: Request,
    next: str = Query(default="/deals"),
) -> HTMLResponse:
    """Recovery page for logged-in users blocked by the verification gate."""
    return templates.TemplateResponse(
        request,
        "auth_message.html",
        {
            "title": "Verify your email to continue",
            "message": (
                "Your account is signed in, but email verification is required "
                "before you can access the app. Check your inbox (and spam folder), "
                "then click the verification link."
            ),
            "success": False,
            "next_url": "/profile?from=verify-gate&next=" + next,
            "next_label": "Go to profile",
        },
        status_code=403,
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
    """Best-effort client IP. Prefers CF-Connecting-IP (set by Cloudflare proxy)
    over X-Forwarded-For so the rate limiter buckets on the real visitor IP
    rather than a proxy or SNAT address."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
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

    # Log them in and redirect. Reset link click proves mailbox ownership,
    # so the session is issued with the verified claim.
    session_token = create_session_token(user.id, email_verified=True)
    resp = RedirectResponse(url="/deals", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return resp


# ===========================================================================
# Onboarding wizard (create org + invite teammates)
#
# Restored 2026-07-07: these routes shipped in a9ffca9 but were accidentally
# deleted by 71781d0 (a security fix committed from a stale ui.py), leaving
# the /onboarding templates and the onboarding_guard middleware pointing at
# 404s. Adapted from the pre-71781d0 ui.py to live with the other auth-flow
# routes.
# ===========================================================================

def _slugify(text: str) -> str:
    """Convert org name to URL-safe slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:100]


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_get(request: Request, session: DBSession) -> Response:
    """Entry point for new-user onboarding wizard (create org + invite)."""
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.org_id is not None:
        return RedirectResponse(url="/deals", status_code=303)
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {"user": user, "_step": 1, "inputs": {}},
    )


@router.post("/ui/onboarding/step", response_class=HTMLResponse)
async def onboarding_step_post(request: Request, session: DBSession) -> Response:
    """HTMX step handler — returns next wizard step (outerHTML swap)."""
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.org_id is not None:
        return RedirectResponse(url="/deals", status_code=303)

    form = await request.form()
    current_step = int(form.get("_step", "1"))
    inputs: dict = {k: str(v) for k, v in form.items() if k != "_step"}

    if current_step == 1:
        org_name = inputs.get("org_name", "").strip()
        org_slug = inputs.get("org_slug", "").strip()

        if not org_name:
            return templates.TemplateResponse(
                request, "partials/onboarding_wizard.html",
                {"user": user, "_step": 1, "inputs": inputs, "error": "Organization name is required."},
            )
        if not org_slug:
            org_slug = _slugify(org_name)
            inputs["org_slug"] = org_slug

        # Validate slug uniqueness
        taken = (
            await session.execute(select(Organization).where(Organization.slug == org_slug))
        ).scalar_one_or_none()
        if taken is not None:
            return templates.TemplateResponse(
                request, "partials/onboarding_wizard.html",
                {"user": user, "_step": 1, "inputs": inputs, "error": "That slug is already taken. Choose another."},
            )
        inputs["org_name"] = org_name
        inputs["org_slug"] = org_slug
        return templates.TemplateResponse(
            request, "partials/onboarding_wizard.html",
            {"user": user, "_step": 2, "inputs": inputs},
        )

    return templates.TemplateResponse(
        request, "partials/onboarding_wizard.html",
        {"user": user, "_step": current_step, "inputs": inputs},
    )


@router.get("/ui/onboarding/check-slug", response_class=HTMLResponse)
async def onboarding_check_slug(
    request: Request, session: DBSession, slug: str = Query(default="")
) -> HTMLResponse:
    """HTMX inline slug availability check. Returns a small indicator fragment."""
    if not slug:
        return HTMLResponse("")
    normalized = _slugify(slug)
    taken = (
        await session.execute(select(Organization).where(Organization.slug == normalized))
    ).scalar_one_or_none()
    if taken:
        return HTMLResponse(
            '<span style="color:var(--danger);font-size:12px;">✗ Already taken</span>'
        )
    return HTMLResponse(
        '<span style="color:var(--success,#16a34a);font-size:12px;">✓ Available</span>'
    )


_ONBOARDING_INVITE_MAX = 5
_ONBOARDING_INVITE_WINDOW = 5 * 60  # 5 minutes


@router.post("/ui/onboarding/complete", response_class=HTMLResponse)
async def onboarding_complete_post(request: Request, session: DBSession) -> Response:
    """Finalize onboarding: create org, assign to user, send invites."""
    from datetime import timedelta

    from app.api.rate_limit import check_rate_limit
    from app.emails import make_invite_token, send_invite_email
    from app.models.org import OrgInvite

    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.org_id is not None:
        return RedirectResponse(url="/deals", status_code=303)

    form = await request.form()
    org_name = str(form.get("org_name", "")).strip()
    org_slug = str(form.get("org_slug", "")).strip()
    invite_emails = [
        str(form.get(f"invite_email_{i}", "")).strip().lower()
        for i in range(1, 6)
        if str(form.get(f"invite_email_{i}", "")).strip()
    ]

    if not org_name or not org_slug:
        return templates.TemplateResponse(
            request, "partials/onboarding_wizard.html",
            {"user": user, "_step": 1, "inputs": dict(form), "error": "Organization name and slug are required."},
        )

    # Verify slug still unique at commit time
    taken = (
        await session.execute(select(Organization).where(Organization.slug == org_slug))
    ).scalar_one_or_none()
    if taken is not None:
        return templates.TemplateResponse(
            request, "partials/onboarding_wizard.html",
            {"user": user, "_step": 1, "inputs": dict(form), "error": "That slug is already taken. Choose another."},
        )

    # Create org
    org = Organization(id=uuid.uuid4(), name=org_name, slug=org_slug)
    session.add(org)
    await session.flush()

    # Assign user to org as admin
    user.org_id = org.id
    user.is_org_admin = True
    user.membership_status = MembershipStatus.ACTIVE
    await session.commit()

    # Send invites (rate-limited)
    if invite_emails:
        allowed = await check_rate_limit(
            key=f"invite_send:{user.id}",
            max_count=_ONBOARDING_INVITE_MAX,
            window_seconds=_ONBOARDING_INVITE_WINDOW,
        )
        if allowed:
            expires = datetime.now(UTC) + timedelta(seconds=settings.invite_token_max_age_seconds)
            for email in invite_emails[:5]:
                if not email:
                    continue
                token = make_invite_token(org.id, email)
                invite_rec = OrgInvite(
                    id=uuid.uuid4(),
                    org_id=org.id,
                    invited_by_id=user.id,
                    email=email,
                    token=token,
                    expires_at=expires,
                )
                session.add(invite_rec)
                invite_url = f"{settings.app_base_url}/register?invite={token}"
                try:
                    await send_invite_email(
                        to=email,
                        inviter_name=user.name,
                        org_name=org.name,
                        invite_url=invite_url,
                    )
                except Exception:  # pragma: no cover
                    pass
            await session.commit()

    return HTMLResponse("", status_code=200, headers={"HX-Redirect": "/deals"})
