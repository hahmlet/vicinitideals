"""Auth routes — login, logout, register, profile.

These routes are mounted without the /api prefix (see main.py).
They serve HTML pages and set/clear the vd_session HttpOnly cookie.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
from app.models.org import Organization, User

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
) -> HTMLResponse | RedirectResponse:
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
    from datetime import UTC, datetime
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
) -> HTMLResponse | RedirectResponse:
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
    )
    session.add(user)
    await session.commit()

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
) -> HTMLResponse | RedirectResponse:
    user = await get_current_user(request, session)
    if user is None:
        return RedirectResponse(url="/login?next=/profile", status_code=303)
    return templates.TemplateResponse(request, "profile.html", {"user": user})
