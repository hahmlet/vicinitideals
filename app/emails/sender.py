"""Async Resend REST wrapper + transactional email senders.

We use Resend's plain HTTP API rather than the Python SDK to avoid a new
dependency (httpx is already in the stack).  The ``_post`` helper is the
single network boundary — everything else is pure template rendering.

If ``settings.resend_api_key`` is empty the sender logs the outbound
message instead of transmitting.  This keeps local dev friction-free
and makes tests trivially stubbable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_TEMPLATE_DIR = Path(__file__).parent / "templates"

_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ── Core Resend POST ─────────────────────────────────────────────────────────

async def _post(payload: dict[str, Any]) -> dict[str, Any] | None:
    """POST to Resend.  Returns the parsed response body on success, else None.

    Never raises — callers get None and the failure is logged.  We treat
    email delivery as best-effort: a failed verify email should not break
    registration.  The user can always hit "Resend verification" later.
    """
    if not settings.resend_api_key:
        logger.warning(
            "Resend API key not configured — email NOT sent. "
            "Would have sent: to=%s subject=%s",
            payload.get("to"),
            payload.get("subject"),
        )
        return None

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_RESEND_API_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("Resend HTTP error: %s", exc)
        return None

    if resp.status_code >= 400:
        logger.error(
            "Resend API returned %d: %s",
            resp.status_code,
            resp.text[:500],
        )
        return None

    try:
        return resp.json()
    except Exception:
        return None


# ── Template rendering ───────────────────────────────────────────────────────

def _render(template_name: str, **ctx: Any) -> str:
    return _jinja.get_template(template_name).render(**ctx)


def _from_field() -> str:
    """Build the RFC-2822 From header from config (name <address>)."""
    name = settings.email_from_name.strip()
    addr = settings.email_from.strip()
    if name:
        return f"{name} <{addr}>"
    return addr


# ── High-level senders ───────────────────────────────────────────────────────

async def send_verification_email(
    *, to: str, name: str, verify_url: str
) -> bool:
    """Send an email-verification link.  Returns True on successful submit."""
    if not to:
        return False
    ctx = {
        "name": name or "there",
        "verify_url": verify_url,
        "app_base_url": settings.app_base_url,
    }
    payload = {
        "from": _from_field(),
        "to": [to],
        "subject": "Verify your Viciniti Deals email",
        "html": _render("verify_email.html", **ctx),
        "text": _render("verify_email.txt", **ctx),
    }
    result = await _post(payload)
    return result is not None


async def send_password_reset_email(
    *, to: str, name: str, reset_url: str
) -> bool:
    """Send a password-reset link.  Returns True on successful submit."""
    if not to:
        return False
    ctx = {
        "name": name or "there",
        "reset_url": reset_url,
        "app_base_url": settings.app_base_url,
        "expire_minutes": settings.password_reset_token_max_age_seconds // 60,
    }
    payload = {
        "from": _from_field(),
        "to": [to],
        "subject": "Reset your Viciniti Deals password",
        "html": _render("reset_password.html", **ctx),
        "text": _render("reset_password.txt", **ctx),
    }
    result = await _post(payload)
    return result is not None
