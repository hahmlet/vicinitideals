"""Celery task: parse an inbound email and create a preliminary deal.

Flow
----
1. Webhook handler creates InboundEmail row (status=pending) and queues this task.
2. Task decodes raw MIME, extracts body_text and attachments, stores body_text in DB.
3. LLM call extracts: address, asking_price, unit_count, property_type from subject+body.
4. Parcel match via enrich_parcel() (best-effort, silent fail).
5. Creates Deal + Scenario + Project + OperationalInputs (preliminary=True).
6. Creates EmailDealSuggestion rows for each extracted field.
7. Queues parse_proforma for any .xlsx attachments.
8. Updates status → opportunity_created (or failed on exception).
9. Sends notification email to org members.

Redis key schema
----------------
No Redis used beyond Celery broker — all state is PostgreSQL.
"""

from __future__ import annotations

import asyncio
import base64
import email as email_lib
import hashlib
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from celery.utils.log import get_task_logger
from pydantic import BaseModel, Field

from app.config import settings
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)

PROCESS_EMAIL_TASK = "app.tasks.email_ingest.process_inbound_email"

# ---------------------------------------------------------------------------
# LLM extraction schema
# ---------------------------------------------------------------------------

class ExtractedDealInfo(BaseModel):
    address: str | None = Field(
        default=None,
        description="Full property address including street, city, state",
    )
    asking_price: float | None = Field(
        default=None,
        description="Asking price or list price in dollars (numeric only, no $ signs)",
    )
    unit_count: int | None = Field(
        default=None,
        description="Number of residential or commercial units",
    )
    property_type: str | None = Field(
        default=None,
        description="Property type: multifamily, commercial, retail, industrial, mixed_use, land, or other",
    )
    broker_name: str | None = Field(
        default=None,
        description="Name of the listing broker or agent",
    )
    broker_email: str | None = Field(
        default=None,
        description="Email address of the listing broker or agent",
    )
    address_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confidence score 0-1 for address extraction",
    )
    price_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confidence score 0-1 for asking price extraction",
    )


# ---------------------------------------------------------------------------
# LLM client (same pattern as proforma_parse.py)
# ---------------------------------------------------------------------------

def _llm_client() -> Any:
    import instructor  # type: ignore
    from openai import OpenAI  # type: ignore

    raw = OpenAI(base_url=settings.ollama_base_url, api_key="ollama")
    return instructor.from_openai(raw, mode=instructor.Mode.JSON)


_STEP_TIMEOUT_SECONDS = 60.0
_GPU_CHECK_DELAY_SECONDS = 3.0


async def _gpu_inflight_check(
    log: list[str] | None,
    abort_event: "asyncio.Event | None" = None,
) -> None:
    """Sleep briefly, then snapshot Ollama running models to confirm GPU usage.

    Ollama's /api/ps returns each loaded model's ``size`` and ``size_vram``.
    If a loaded model has ``size_vram == 0`` the model is running on CPU
    (10-50x slower than GPU). When ``abort_event`` is passed, set it so the
    caller can fast-fail the LLM call instead of waiting out the full timeout.

    No models loaded at the check time means the model is still loading or
    queued — not aborted, just noted.
    """
    import traceback
    from datetime import UTC, datetime

    def _emit(msg: str) -> None:
        line = f"[{datetime.now(UTC).isoformat()}] {msg}"
        logger.info(line)
        if log is not None:
            log.append(line)

    try:
        await asyncio.sleep(_GPU_CHECK_DELAY_SECONDS)
        import httpx
        # ollama_base_url is the OpenAI-compatible endpoint (.../v1); the
        # /api/ps endpoint lives on the native Ollama root, so strip /v1.
        base = settings.ollama_base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/api/ps")
            if resp.status_code != 200:
                _emit(f"GPU check: /api/ps returned status {resp.status_code}")
                return
            models = (resp.json() or {}).get("models", [])
            if not models:
                _emit(
                    "GPU check: Ollama /api/ps returned no loaded models — "
                    "call may still be queued or model load in progress"
                )
                return
            cpu_only = True
            for m in models:
                name = m.get("name") or m.get("model")
                size = m.get("size") or 0
                vram = m.get("size_vram") or 0
                pct_gpu = (vram / size * 100) if size else 0
                where = "GPU" if vram > 0 else "CPU (NO GPU)"
                _emit(
                    f"GPU check: model={name} size={size:,}B vram={vram:,}B "
                    f"({pct_gpu:.0f}% on GPU) -> running_on={where}"
                )
                if vram > 0:
                    cpu_only = False
            if cpu_only and abort_event is not None:
                _emit(
                    "  >> ABORT: every loaded model is on CPU. Stopping the LLM "
                    "call immediately rather than waiting for the 60s timeout. "
                    "Fix the GPU on the Ollama host and re-trigger the email."
                )
                abort_event.set()
    except Exception as exc:
        _emit(f"GPU check: failed: {type(exc).__name__}: {exc}")
        if log is not None:
            log.append(traceback.format_exc())


def _extract_deal_info_sync(
    subject: str | None,
    body: str | None,
    log: list[str] | None = None,
) -> ExtractedDealInfo:
    """Call local Ollama LLM to extract deal fields from email subject+body.

    Appends diagnostic entries to ``log`` (caller-owned list) so failures
    can be surfaced to the UI as a downloadable .txt file.
    """
    import time
    import traceback
    from datetime import UTC, datetime

    def _emit(msg: str) -> None:
        line = f"[{datetime.now(UTC).isoformat()}] {msg}"
        logger.info(line)
        if log is not None:
            log.append(line)

    text = f"Subject: {subject or ''}\n\n{(body or '')[:2000]}"
    _emit("LLM extraction: start")
    _emit(f"  ollama_base_url={settings.ollama_base_url!r}")
    _emit(f"  ollama_model={settings.ollama_model!r}")
    _emit(f"  prompt_chars={len(text)}")
    _emit(f"  subject={subject!r}")

    t0 = time.monotonic()
    try:
        client = _llm_client()
        _emit("  client constructed (instructor + OpenAI shim)")
    except Exception as exc:
        _emit(f"FAIL: client construction error: {type(exc).__name__}: {exc}")
        if log is not None:
            log.append(traceback.format_exc())
        return ExtractedDealInfo()

    try:
        result = client.chat.completions.create(
            model=settings.ollama_model,
            response_model=ExtractedDealInfo,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a commercial real estate data extractor. "
                        "Extract structured deal information from broker emails. "
                        "Return null for any field you cannot find with reasonable confidence."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Extract deal information from this broker email:\n\n{text}"
                    ),
                },
            ],
            max_retries=2,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        _emit(f"OK: LLM extraction succeeded in {elapsed_ms:.0f}ms")
        _emit(f"  address={result.address!r} (conf={result.address_confidence})")
        _emit(f"  asking_price={result.asking_price!r} (conf={result.price_confidence})")
        _emit(f"  unit_count={result.unit_count!r}")
        _emit(f"  property_type={result.property_type!r}")
        _emit(f"  broker={result.broker_name!r} <{result.broker_email!r}>")
        return result
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        cause = type(exc).__name__
        _emit(f"FAIL: LLM extraction error after {elapsed_ms:.0f}ms: {cause}: {exc}")
        # Classify common failure modes for the user
        msg = str(exc).lower()
        if "connection" in msg or "refused" in msg or "unreachable" in msg:
            _emit("  >> classification: cannot reach Ollama service")
        elif "timeout" in msg or "timed out" in msg:
            _emit("  >> classification: request timed out")
        elif "model" in msg and ("not found" in msg or "404" in msg):
            _emit("  >> classification: model not pulled/registered on Ollama")
        elif "validation" in msg or "parse" in msg:
            _emit("  >> classification: model returned malformed JSON (instructor parse)")
        else:
            _emit("  >> classification: other (see traceback below)")
        if log is not None:
            log.append(traceback.format_exc())
        return ExtractedDealInfo()


async def _extract_deal_info(
    subject: str | None,
    body: str | None,
    log: list[str] | None = None,
) -> ExtractedDealInfo:
    """Async wrapper: run the LLM extraction with a 60s timeout and a parallel GPU check.

    The sync ``_extract_deal_info_sync`` is dispatched to a worker thread so we
    can enforce the timeout cooperatively. The GPU check runs as a sibling task
    so it lands in the same debug log regardless of whether the LLM call
    succeeded, failed, or hung.
    """
    import traceback
    from datetime import UTC, datetime

    def _emit(msg: str) -> None:
        line = f"[{datetime.now(UTC).isoformat()}] {msg}"
        logger.info(line)
        if log is not None:
            log.append(line)

    abort_event = asyncio.Event()
    gpu_task = asyncio.create_task(_gpu_inflight_check(log, abort_event=abort_event))
    llm_task = asyncio.create_task(
        asyncio.to_thread(_extract_deal_info_sync, subject, body, log)
    )
    abort_waiter = asyncio.create_task(abort_event.wait())

    try:
        done, _pending = await asyncio.wait(
            {llm_task, abort_waiter},
            timeout=_STEP_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if llm_task in done:
            return llm_task.result()

        if abort_waiter in done:
            _emit(
                "ABORTED: GPU check detected CPU-only execution; LLM call "
                "abandoned. The worker thread will finish in the background "
                "but its result is discarded."
            )
            # Cancel the asyncio handle — the underlying thread keeps running
            # (Python limitation) but the Celery task returns immediately.
            llm_task.cancel()
            return ExtractedDealInfo()

        # Neither completed -> timeout fired
        _emit(
            f"FAIL: LLM extraction exceeded {_STEP_TIMEOUT_SECONDS:.0f}s timeout. "
            "Common causes: model running on CPU (see GPU check above), "
            "Ollama process unresponsive, or request stuck waiting on model load."
        )
        llm_task.cancel()
        return ExtractedDealInfo()
    except Exception as exc:
        _emit(f"FAIL: LLM extraction wrapper error: {type(exc).__name__}: {exc}")
        if log is not None:
            log.append(traceback.format_exc())
        return ExtractedDealInfo()
    finally:
        if not abort_waiter.done():
            abort_waiter.cancel()
        # Give the GPU check a moment to flush its lines into the log
        try:
            await asyncio.wait_for(gpu_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            if not gpu_task.done():
                gpu_task.cancel()


# ---------------------------------------------------------------------------
# MIME parsing
# ---------------------------------------------------------------------------

def _parse_mime(raw_mime_b64: str | None) -> tuple[str | None, list[dict]]:
    """Return (body_text, attachments_meta) from base64-encoded raw MIME."""
    if not raw_mime_b64:
        return None, []

    try:
        raw_bytes = base64.b64decode(raw_mime_b64)
        msg = email_lib.message_from_bytes(raw_bytes)
    except Exception as exc:
        logger.warning("MIME decode failed: %s", exc)
        return None, []

    body_parts: list[str] = []
    attachments: list[dict] = []

    for part in msg.walk():
        content_type = part.get_content_type()
        disposition = str(part.get("Content-Disposition", ""))

        if "attachment" in disposition or part.get_filename():
            filename = part.get_filename() or "attachment"
            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0
            attachments.append({
                "filename": filename,
                "content_type": content_type,
                "size_bytes": size,
                "payload_b64": base64.b64encode(payload).decode() if payload else None,
            })
        elif content_type == "text/plain" and "attachment" not in disposition:
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                try:
                    body_parts.append(payload.decode(charset, errors="replace"))
                except Exception:
                    body_parts.append(payload.decode("utf-8", errors="replace"))

    body_text = "\n\n".join(body_parts) if body_parts else None
    return body_text, attachments


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------

async def _fetch_resend_raw_mime(
    resend_email_id: str,
    log: list[str] | None = None,
) -> str | None:
    """Fetch raw MIME from Resend received-email API. Returns base64-encoded bytes or None on failure."""
    import time
    import traceback
    from datetime import UTC, datetime

    def _emit(msg: str) -> None:
        line = f"[{datetime.now(UTC).isoformat()}] {msg}"
        logger.info(line)
        if log is not None:
            log.append(line)

    if not settings.resend_api_key:
        _emit("FAIL: resend_api_key not configured")
        return None

    _emit(f"Resend MIME fetch: start (email_id={resend_email_id})")
    t0 = time.monotonic()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            meta_resp = await client.get(
                f"https://api.resend.com/emails/receiving/{resend_email_id}",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
            _emit(f"  metadata GET status={meta_resp.status_code}")
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            raw_obj = meta.get("raw") or {}
            download_url = raw_obj.get("download_url")
            if not download_url:
                _emit("FAIL: response missing raw.download_url")
                return None

            raw_resp = await client.get(download_url)
            _emit(f"  raw MIME GET status={raw_resp.status_code} bytes={len(raw_resp.content)}")
            raw_resp.raise_for_status()
            elapsed_ms = (time.monotonic() - t0) * 1000
            _emit(f"OK: raw MIME fetched in {elapsed_ms:.0f}ms")
            return base64.b64encode(raw_resp.content).decode()
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        _emit(f"FAIL: Resend MIME fetch after {elapsed_ms:.0f}ms: {type(exc).__name__}: {exc}")
        if log is not None:
            log.append(traceback.format_exc())
        return None


async def _process_async(inbound_email_id: str, resend_email_id: str) -> None:
    from decimal import Decimal

    from app.db import AsyncSessionLocal
    from app.models.email_ingest import (
        EmailDealSuggestion,
        InboundEmail,
        InboundEmailStatus,
        SuggestionSourceType,
    )
    from app.models.opportunity import Opportunity, OpportunityStatus

    email_uuid = UUID(inbound_email_id)
    debug_log: list[str] = []

    async with AsyncSessionLocal() as session:
        email_row = await session.get(InboundEmail, email_uuid)
        if email_row is None:
            logger.error("InboundEmail %s not found", inbound_email_id)
            return

        try:
            email_row.status = InboundEmailStatus.processing.value
            await session.commit()

            debug_log.append(f"inbound_email_id={inbound_email_id}")
            debug_log.append(f"resend_email_id={resend_email_id}")

            # --- Fetch raw MIME from Resend (60s ceiling) ---
            try:
                raw_mime_b64 = await asyncio.wait_for(
                    _fetch_resend_raw_mime(resend_email_id, log=debug_log),
                    timeout=_STEP_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                raw_mime_b64 = None
                debug_log.append(
                    f"FAIL: Resend MIME fetch exceeded {_STEP_TIMEOUT_SECONDS:.0f}s timeout"
                )
            email_row.raw_mime_b64 = raw_mime_b64

            # --- Parse MIME ---
            body_text, attachments = _parse_mime(raw_mime_b64)
            debug_log.append(
                f"MIME parse: body_chars={len(body_text or '')}, attachments={len(attachments)}"
            )
            email_row.body_text = body_text
            # Strip raw MIME after parsing (72h retention not needed at task time)
            email_row.raw_mime_b64 = None

            # --- Stage proforma attachments in Redis before flushing meta ---
            # Each .xlsx/.pdf gets a task_id so the deal-setup wizard can load
            # it directly from Redis without re-upload (feature parity with
            # manual upload flow). payload_b64 is kept in `attachments` but
            # stripped from attachments_meta stored to the DB.
            import os as _os
            import redis as _redis  # type: ignore
            _PROFORMA_TTL = 7 * 86_400  # 7 days, same as manual upload
            _PROFORMA_EXTS = {"xlsx", "xlsm", "xlsb", "pdf"}
            _r = _redis.from_url(settings.redis_url, decode_responses=False)

            attachments_meta: list[dict] = []
            for att in attachments:
                meta: dict = {k: v for k, v in att.items() if k != "payload_b64"}
                ext = _os.path.splitext(att.get("filename") or "")[1].lower().lstrip(".")
                if ext in _PROFORMA_EXTS and att.get("payload_b64"):
                    task_id = str(__import__("uuid").uuid4())
                    file_bytes = base64.b64decode(att["payload_b64"])
                    file_kind = "xlsx" if ext in {"xlsx", "xlsm", "xlsb"} else "doc"
                    file_hash = hashlib.sha256(file_bytes).hexdigest()
                    _r.set(f"proforma:{task_id}:file", file_bytes, ex=_PROFORMA_TTL)
                    _r.set(f"proforma:{task_id}:filename", att["filename"].encode(), ex=_PROFORMA_TTL)
                    _r.set(f"proforma:{task_id}:kind", file_kind.encode(), ex=_PROFORMA_TTL)
                    _r.set(f"proforma:{task_id}:file_hash", file_hash.encode(), ex=_PROFORMA_TTL)
                    _r.set(f"proforma:{task_id}:org_id", str(email_row.org_id).encode(), ex=_PROFORMA_TTL)
                    meta["proforma_task_id"] = task_id
                    debug_log.append(
                        f"Staged proforma: {att['filename']!r} task_id={task_id} kind={file_kind}"
                    )
                attachments_meta.append(meta)

            email_row.attachments_meta = attachments_meta
            await session.commit()

            # --- LLM extraction (60s timeout + parallel GPU usage check) ---
            info = await _extract_deal_info(email_row.subject, body_text, log=debug_log)

            # --- Resolve org ---
            from app.models.org import Organization
            org = await session.get(Organization, email_row.org_id)
            if org is None:
                raise ValueError(f"Org {email_row.org_id} not found")

            # --- Parcel match (best-effort) ---
            parcel_id = None
            if info.address:
                try:
                    from app.scrapers.parcel_enrichment import enrich_parcel
                    parcel = await enrich_parcel(session, address=info.address)
                    if parcel is not None:
                        parcel_id = parcel.id
                except Exception as exc:
                    logger.debug("Parcel match failed for %s: %s", info.address, exc)

            asking_price_dec = None
            if info.asking_price and info.asking_price > 0:
                asking_price_dec = Decimal(str(info.asking_price))

            # --- Create one Opportunity per staged proforma attachment ------
            # Each attachment that was staged in Redis becomes its own stub
            # deal so the user can configure and parse each file independently.
            # Non-proforma attachments (images, PDFs not for proforma, etc.)
            # don't create Opportunities — they're display-only in the review.
            #
            # source_id is hashed per-attachment (sender+subject+received_at+
            # filename) so multiple attachments in one email produce distinct,
            # non-colliding Opportunities.
            proforma_metas = [m for m in attachments_meta if m.get("proforma_task_id")]
            if not proforma_metas:
                # No stageable attachments — create a single Opportunity from
                # the email metadata alone (original behavior).
                proforma_metas = [{}]

            opp_name_base = info.address or (email_row.subject or "Email Deal")[:255]
            email_base_id = f"{email_row.sender_email}|{email_row.subject}|{email_row.received_at}"
            first_opportunity: Opportunity | None = None
            all_task_ids: list[str] = []

            for idx, att_meta in enumerate(proforma_metas):
                suffix = att_meta.get("filename") or str(idx)
                source_id = hashlib.sha256(
                    f"{email_base_id}|{suffix}".encode()
                ).hexdigest()[:32]

                opp_name = opp_name_base
                if len(proforma_metas) > 1 and att_meta.get("filename"):
                    # Disambiguate name when multiple attachments
                    bare = _os.path.splitext(att_meta["filename"])[0]
                    opp_name = f"{opp_name_base} — {bare}"

                opportunity = Opportunity(
                    org_id=email_row.org_id,
                    name=opp_name[:255],
                    opp_status=OpportunityStatus.active.value,
                    source="email",
                    source_id=source_id,
                    source_url="",
                    promotion_source="email",
                    parcel_id=parcel_id,
                    address_raw=info.address,
                    asking_price=asking_price_dec,
                    units=info.unit_count,
                )
                session.add(opportunity)
                await session.flush()

                if att_meta.get("proforma_task_id"):
                    att_meta["opportunity_id"] = str(opportunity.id)
                    all_task_ids.append(att_meta["proforma_task_id"])

                if first_opportunity is None:
                    first_opportunity = opportunity

                # Create suggestions on every Opportunity (same LLM extraction
                # shared across all attachments in this email).
                src = SuggestionSourceType.llm_extraction.value
                for field_path, value, conf in [
                    ("address",          info.address,       info.address_confidence),
                    ("acquisition_cost", str(info.asking_price) if info.asking_price else None, info.price_confidence),
                    ("unit_count",       str(info.unit_count) if info.unit_count else None,     0.8),
                    ("property_type",    info.property_type, 0.7),
                ]:
                    if value:
                        session.add(EmailDealSuggestion(
                            inbound_email_id=email_row.id,
                            opportunity_id=opportunity.id,
                            field_path=field_path,
                            suggested_value=value,
                            confidence=conf,
                            source_type=src,
                        ))

                debug_log.append(
                    f"Created Opportunity {opportunity.id} name={opp_name!r} "
                    f"task_id={att_meta.get('proforma_task_id') or 'none'}"
                )

            # Persist the updated attachments_meta (now has opportunity_id per entry)
            email_row.attachments_meta = attachments_meta
            email_row.opportunity_id = first_opportunity.id if first_opportunity else None
            email_row.proforma_task_ids = all_task_ids
            await session.flush()

            email_row.status = InboundEmailStatus.opportunity_created.value
            debug_log.append(
                f"OK: pipeline complete, {len(proforma_metas)} opportunit{'y' if len(proforma_metas)==1 else 'ies'} created"
            )
            email_row.debug_log = "\n".join(debug_log)[-50000:]
            await session.commit()

            # --- Notification email ---
            await _notify_org(org, email_row, first_opportunity or opportunity, info)

        except Exception as exc:
            import traceback
            logger.exception("process_inbound_email failed for %s", inbound_email_id)
            debug_log.append(f"FAIL: pipeline exception {type(exc).__name__}: {exc}")
            debug_log.append(traceback.format_exc())
            try:
                email_row.status = InboundEmailStatus.failed.value
                email_row.error_message = str(exc)[:500]
                email_row.debug_log = "\n".join(debug_log)[-50000:]
                await session.commit()
            except Exception:
                pass


async def _notify_org(
    org: Any,
    email_row: Any,
    opportunity: Any,
    info: "ExtractedDealInfo",
) -> None:
    """Send notification email to org admins when an opportunity is created from an inbound email."""
    if not settings.resend_api_key:
        return

    try:
        import httpx
        from sqlalchemy import select

        from app.db import AsyncSessionLocal
        from app.models.org import User

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User)
                .where(User.org_id == org.id, User.is_active == True)  # noqa: E712
                .limit(5)
            )
            users = result.scalars().all()

        for user in users:
            if not user.email:
                continue
            subject = f"New opportunity from email: {email_row.subject or email_row.sender_email}"
            body = (
                f"A new opportunity was created from an inbound email.\n\n"
                f"From: {email_row.sender_email}\n"
                f"Subject: {email_row.subject or '(no subject)'}\n"
                f"Address: {info.address or '(not detected)'}\n"
                f"Asking Price: {'${:,.0f}'.format(info.asking_price) if info.asking_price else '(not detected)'}\n\n"
                f"Review extracted fields and finish deal creation at:\n"
                f"{settings.app_base_url}/ui/deals/email/{email_row.id}/review"
            )
            payload = {
                "from": f"{settings.email_from_name} <{settings.email_from}>",
                "to": [user.email],
                "subject": subject,
                "text": body,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    "https://api.resend.com/emails",
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                )
    except Exception as exc:
        logger.warning("Notification email failed: %s", exc)


# ---------------------------------------------------------------------------
# Celery task entry point
# ---------------------------------------------------------------------------

async def _with_fresh_loop(fn, *args):
    """Dispose the shared async engine at start and end of each task so its
    asyncpg connection pool stays aligned with the current asyncio.run() loop.

    See ``app/tasks/export.py`` for the same pattern. Celery's prefork worker
    reuses processes; without dispose, a second task in the same process
    crashes with "Future attached to a different loop" because pooled
    connections hold transport futures bound to the previous (now-closed) loop.
    """
    from app.db import engine as _db_engine  # noqa: PLC0415
    try:
        await _db_engine.dispose()
        return await fn(*args)
    finally:
        await _db_engine.dispose()


@celery_app.task(bind=True, name=PROCESS_EMAIL_TASK)
def process_inbound_email(self, inbound_email_id: str, resend_email_id: str) -> None:
    """Parse inbound email, extract deal data, create preliminary deal."""
    asyncio.run(_with_fresh_loop(_process_async, inbound_email_id, resend_email_id))
