"""Email ingest routes: webhook endpoint, inbox list, side-by-side review UI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.api.deps import DBSession, CurrentUserId
from app.config import settings

# Reject webhooks with timestamps more than 5 minutes off (Svix default)
_WEBHOOK_TOLERANCE_SECONDS = 300

# Debug-log download is gated to a single hardcoded operator email — feature only
# meaningful for the person triaging AI extraction failures.
_DEBUG_LOG_ALLOWED_EMAIL = "stephenjketch@gmail.com"

# ---------------------------------------------------------------------------
# Template setup (same dir as ui.py)
# ---------------------------------------------------------------------------
_PACKAGE_DIR = Path(__file__).resolve().parent.parent.parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ---------------------------------------------------------------------------
# Two routers: api_router gets /api prefix via ROUTERS; ui_router has no prefix
# ---------------------------------------------------------------------------
router = APIRouter(tags=["email-ingest"], include_in_schema=False)
ui_router = APIRouter(include_in_schema=False)


# ===========================================================================
# API routes (mounted at /api/...)
# ===========================================================================

@router.post("/email-ingest", status_code=status.HTTP_200_OK)
async def receive_inbound_email(
    request: Request,
    session: DBSession,
) -> dict[str, Any]:
    """Resend inbound webhook. Verifies Svix signature, stores email metadata, queues Celery task to fetch full content."""
    raw_body = await request.body()
    _verify_svix_signature(request, raw_body)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    if payload.get("type") != "email.received":
        return {"status": "ignored", "reason": "event type not email.received"}

    data = payload.get("data") or {}
    resend_email_id = data.get("email_id")
    if not resend_email_id:
        raise HTTPException(status_code=400, detail="Missing email_id")

    from app.models.email_ingest import InboundEmail, InboundEmailStatus
    from app.models.org import Organization

    org_result = await session.execute(select(Organization).limit(1))
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=500, detail="No organization configured")

    email_row = InboundEmail(
        id=uuid.uuid4(),
        org_id=org.id,
        sender_email=str(data.get("from") or ""),
        subject=data.get("subject") or None,
        raw_mime_b64=None,  # Fetched by Celery task via Resend API
        status=InboundEmailStatus.pending.value,
        proforma_task_ids=[],
        attachments_meta=data.get("attachments") or [],
    )
    session.add(email_row)
    await session.commit()
    await session.refresh(email_row)

    from app.tasks.email_ingest import process_inbound_email  # noqa: PLC0415
    process_inbound_email.delay(str(email_row.id), resend_email_id)

    return {"status": "accepted", "id": str(email_row.id)}


def _verify_svix_signature(request: Request, body: bytes) -> None:
    """Verify Resend (Svix) webhook signature using HMAC-SHA256.

    Raises 403 if signature invalid, secret unset, or timestamp out of tolerance.
    """
    secret = settings.resend_webhook_secret
    if not secret:
        raise HTTPException(status_code=403, detail="Webhook secret not configured")

    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")
    if not (svix_id and svix_timestamp and svix_signature):
        raise HTTPException(status_code=403, detail="Missing Svix headers")

    try:
        ts = int(svix_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid timestamp") from exc
    if abs(time.time() - ts) > _WEBHOOK_TOLERANCE_SECONDS:
        raise HTTPException(status_code=403, detail="Timestamp out of tolerance")

    # Strip "whsec_" prefix if present, then base64-decode the key
    secret_key = secret.removeprefix("whsec_")
    try:
        key_bytes = base64.b64decode(secret_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Malformed webhook secret") from exc

    signed_payload = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected_sig = base64.b64encode(
        hmac.new(key_bytes, signed_payload, hashlib.sha256).digest()
    ).decode()

    # Header format: "v1,sig1 v1,sig2" — any version-prefixed match wins
    provided_sigs = [s.split(",", 1)[1] for s in svix_signature.split() if "," in s]
    if not any(hmac.compare_digest(expected_sig, sig) for sig in provided_sigs):
        raise HTTPException(status_code=403, detail="Invalid signature")


@router.post("/email-suggestions/{suggestion_id}/accept")
async def accept_suggestion(
    suggestion_id: uuid.UUID,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> HTMLResponse:
    """Mark a suggestion as accepted. Returns updated suggestion row HTML."""
    return await _set_suggestion(suggestion_id, True, current_user_id, session)


@router.post("/email-suggestions/{suggestion_id}/reject")
async def reject_suggestion(
    suggestion_id: uuid.UUID,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> HTMLResponse:
    """Mark a suggestion as rejected. Returns updated suggestion row HTML."""
    return await _set_suggestion(suggestion_id, False, current_user_id, session)


async def _set_suggestion(
    suggestion_id: uuid.UUID,
    accepted: bool,
    current_user_id: uuid.UUID,
    session: Any,
) -> HTMLResponse:
    from app.models.email_ingest import EmailDealSuggestion, InboundEmail

    suggestion = await session.get(EmailDealSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    email_row = await session.get(InboundEmail, suggestion.inbound_email_id)
    user_org = await _get_user_org(session, current_user_id)
    if email_row is None or email_row.org_id != user_org:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion.accepted = accepted
    await session.commit()

    accepted_class = "active" if accepted else ""
    return HTMLResponse(
        f'<div class="suggestion-row" id="suggestion-{suggestion_id}" '
        f'style="opacity:{0.6 if not accepted else 1}">'
        f'<div class="suggestion-label">{suggestion.field_path.replace("_", " ").title()}</div>'
        f'<div class="suggestion-value">{suggestion.suggested_value or "—"}</div>'
        f'<div class="suggestion-actions">'
        f'<span class="chip chip-accept {accepted_class}">{"✓ Accepted" if accepted else "✓ Accept"}</span>'
        f'</div></div>'
    )


# ===========================================================================
# UI routes (no /api prefix)
# ===========================================================================

@ui_router.get("/ui/email-inbox", response_class=HTMLResponse)
async def email_inbox(
    request: Request,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> HTMLResponse:
    """Email inbox — lists all inbound emails for the org."""
    from app.api.routers.ui import _base_ctx, _get_counts  # noqa: PLC0415
    from app.models.email_ingest import InboundEmail
    from app.models.org import User

    user = await session.get(User, current_user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    dedup_count, conflicts_count = await _get_counts(session)

    result = await session.execute(
        select(InboundEmail)
        .where(InboundEmail.org_id == user.org_id)
        .order_by(InboundEmail.received_at.desc())
        .limit(100)
    )
    emails = result.scalars().all()

    ctx = _base_ctx(user, dedup_count, "email_inbox", conflicts_count=conflicts_count)
    ctx.update({
        "emails": emails,
        "can_view_debug_log": (user.email or "").lower() == _DEBUG_LOG_ALLOWED_EMAIL,
    })

    return templates.TemplateResponse(request, "email_inbox.html", ctx)


@ui_router.get("/ui/deals/email/{inbound_email_id}/review", response_class=HTMLResponse)
async def email_deal_review(
    request: Request,
    inbound_email_id: uuid.UUID,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> HTMLResponse:
    """Side-by-side review: source email on left, extracted deal fields on right."""
    from app.api.routers.ui import _base_ctx, _get_counts  # noqa: PLC0415
    from app.models.email_ingest import EmailDealSuggestion, InboundEmail
    from app.models.opportunity import Opportunity
    from app.models.org import User

    user = await session.get(User, current_user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    email_row = await session.get(InboundEmail, inbound_email_id)
    if email_row is None or email_row.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Email not found")

    dedup_count, conflicts_count = await _get_counts(session)

    suggestions_result = await session.execute(
        select(EmailDealSuggestion)
        .where(EmailDealSuggestion.inbound_email_id == inbound_email_id)
        .order_by(EmailDealSuggestion.field_path)
    )
    suggestions = suggestions_result.scalars().all()

    opportunity = None
    if email_row.opportunity_id:
        opportunity = await session.get(Opportunity, email_row.opportunity_id)

    ctx = _base_ctx(user, dedup_count, "email_inbox", conflicts_count=conflicts_count)
    ctx.update({
        "email": email_row,
        "opportunity": opportunity,
        "suggestions": suggestions,
        "can_view_debug_log": (user.email or "").lower() == _DEBUG_LOG_ALLOWED_EMAIL,
    })

    return templates.TemplateResponse(request, "email_deal_review.html", ctx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_org(session: Any, user_id: uuid.UUID) -> uuid.UUID | None:
    from app.models.org import User
    user = await session.get(User, user_id)
    return user.org_id if user else None


@ui_router.get("/ui/email-inbox/{inbound_email_id}/debug-log.txt")
async def email_debug_log(
    inbound_email_id: uuid.UUID,
    current_user_id: CurrentUserId,
    session: DBSession,
) -> Any:
    """Return AI processing debug log as plain text. Hardcoded to a single operator email."""
    from fastapi.responses import PlainTextResponse  # noqa: PLC0415

    from app.models.email_ingest import InboundEmail
    from app.models.org import User

    user = await session.get(User, current_user_id)
    if user is None or (user.email or "").lower() != _DEBUG_LOG_ALLOWED_EMAIL:
        raise HTTPException(status_code=404, detail="Not found")

    email_row = await session.get(InboundEmail, inbound_email_id)
    if email_row is None or email_row.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Email not found")

    body = email_row.debug_log or "(no debug log captured for this email)"
    header = (
        f"# Email ingest debug log\n"
        f"# inbound_email_id: {email_row.id}\n"
        f"# received_at: {email_row.received_at}\n"
        f"# status: {email_row.status}\n"
        f"# sender: {email_row.sender_email}\n"
        f"# subject: {email_row.subject}\n"
        f"# error_message: {email_row.error_message or '(none)'}\n"
        f"#" + ("-" * 60) + "\n\n"
    )
    return PlainTextResponse(
        header + body,
        headers={
            "Content-Disposition": f'attachment; filename="email-{email_row.id}-debug.txt"'
        },
    )
