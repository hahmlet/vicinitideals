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


async def send_invite_email(
    *, to: str, inviter_name: str, org_name: str, invite_url: str
) -> bool:
    """Send an org invite email.  Returns True on successful submit."""
    if not to:
        return False
    ctx = {
        "inviter_name": inviter_name or "Someone",
        "org_name": org_name,
        "invite_url": invite_url,
        "app_base_url": settings.app_base_url,
    }
    payload = {
        "from": _from_field(),
        "to": [to],
        "subject": f"You've been invited to join {org_name} on Viciniti Deals",
        "html": _render("invite.html", **ctx),
        "text": _render("invite.txt", **ctx),
    }
    result = await _post(payload)
    return result is not None


_EXPORT_PROFILE_LABEL: dict[str, str] = {
    "internal": "Underwriting Model",
    "lp": "Investor Package",
    "lender": "Lender Package",
    "proforma": "Pro Forma",
}
_EXPORT_PROFILE_DESC: dict[str, str] = {
    "internal": "the full underwriting workbook",
    "lp": "the LP-facing investor package",
    "lender": "the lender package",
    "proforma": "the pro forma",
}


async def send_export_ready_email(
    *,
    to: str,
    name: str,
    deal_name: str,
    scenario_name: str | None,
    filename: str,
    xlsx_bytes: bytes,
    profile: str = "internal",
) -> bool:
    """Send the rendered Excel workbook as an email attachment.

    ``profile`` controls the email subject line and body copy so each
    export type gets appropriate messaging (LP package vs lender package
    vs pro forma vs internal underwriting).

    Resend supports attachments via the ``attachments`` payload field —
    each entry is ``{"filename": str, "content": <base64 str>}``. The
    .xlsx content type is inferred from the filename extension on
    Resend's side. Returns True when the API accepts the message.
    """
    import base64

    if not to:
        return False
    _label = _EXPORT_PROFILE_LABEL.get(profile, "Export")
    _desc = _EXPORT_PROFILE_DESC.get(profile, "the export")
    ctx = {
        "name": name or "there",
        "deal_name": deal_name or "your deal",
        "scenario_name": scenario_name or "",
        "filename": filename,
        "export_label": _label,
        "export_desc": _desc,
        "app_base_url": settings.app_base_url,
    }
    payload = {
        "from": _from_field(),
        "to": [to],
        "subject": f"{_label} ready — {deal_name or 'deal'}",
        "html": _render("export_ready.html", **ctx),
        "text": _render("export_ready.txt", **ctx),
        "attachments": [
            {
                "filename": filename,
                "content": base64.b64encode(xlsx_bytes).decode("ascii"),
            }
        ],
    }
    result = await _post(payload)
    return result is not None
