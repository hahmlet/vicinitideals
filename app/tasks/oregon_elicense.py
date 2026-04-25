"""Celery tasks for Oregon eLicense (orea.elicense.micropact.com) enrichment.

Two entry points:
- ``enrich_broker_oregon(broker_id)`` — one-shot lookup for a single broker
  (called from the broker modal's "Update from Oregon" button)
- ``oregon_elicense_sweep()`` — monthly sweep over brokers whose record is
  stale (>30d) or never enriched

Persistence semantics:
- Successful lookup → write license_personal_*, license_type, license_status,
  oregon_detail_url, oregon_last_pulled_at, oregon_lookup_status='success',
  oregon_failure_count=0; on the broker's brokerage, write oregon_company_*;
  replace the broker's disciplinary_actions list.
- Not-found (no row in Oregon DB) → keep the license_number as-is (so the UI
  shows it red), set license_status='not_found', oregon_lookup_status='not_found',
  reset failure counter.
- Transport / parse error → increment oregon_failure_count, set
  oregon_lookup_status='failed', and re-raise so Celery retries (max 3).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models.broker import Broker, BrokerDisciplinaryAction
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Brokers older than this are considered stale and eligible for the monthly
# sweep. New brokers (oregon_last_pulled_at IS NULL) are always eligible.
_STALE_AFTER_DAYS = 30


@celery_app.task(
    name="app.tasks.oregon_elicense.enrich_broker_oregon",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def enrich_broker_oregon(self, broker_id: str) -> dict[str, Any]:
    """One-shot Oregon eLicense lookup for a single broker by ID."""
    try:
        return asyncio.run(_enrich_broker_oregon(broker_id))
    except Exception as exc:
        # Celery retries up to max_retries=3 with a 2-minute backoff. After
        # the final failure the task gives up; the broker is left with
        # oregon_lookup_status='failed' so the UI shows real state.
        raise self.retry(exc=exc) from exc


async def _enrich_broker_oregon(broker_id: str) -> dict[str, Any]:
    # Local import keeps the scraper out of Celery's import path until needed.
    from app.scrapers.oregon_elicense import lookup_broker  # noqa: PLC0415

    async with AsyncSessionLocal() as session:
        broker = await session.get(
            Broker,
            broker_id,
            options=[
                selectinload(Broker.brokerage),
                selectinload(Broker.disciplinary_actions),
            ],
        )
        if broker is None:
            return {"status": "missing", "broker_id": broker_id}
        if not broker.license_number:
            broker.oregon_lookup_status = "not_found"
            await session.commit()
            return {"status": "skipped", "broker_id": broker_id, "reason": "no_license"}

        try:
            record = await lookup_broker(broker.license_number)
        except Exception as exc:
            logger.warning(
                "Oregon eLicense lookup failed for broker %s (license=%s): %s",
                broker.id,
                broker.license_number,
                exc,
            )
            broker.oregon_lookup_status = "failed"
            broker.oregon_failure_count = (broker.oregon_failure_count or 0) + 1
            await session.commit()
            raise

        broker.oregon_last_pulled_at = datetime.now(timezone.utc)

        if record is None:
            # License # exists in our DB but not in Oregon's DB — color it red
            # in the UI and stop retrying. Keep the license_number as-is so
            # the user can see what was wrong and edit if they want.
            broker.license_status = "not_found"
            broker.oregon_lookup_status = "not_found"
            broker.oregon_failure_count = 0
            await session.commit()
            return {"status": "not_found", "broker_id": broker_id}

        # ---- success ----
        broker.license_state = "OR"
        broker.license_status = (record.status or "unknown").strip().lower()
        broker.license_type = record.license_type
        if record.personal_address:
            broker.license_personal_street = record.personal_address.street
            broker.license_personal_city = record.personal_address.city
            broker.license_personal_state = record.personal_address.state
            broker.license_personal_zip = record.personal_address.zip
        broker.oregon_detail_url = record.detail_url
        broker.oregon_lookup_status = "success"
        broker.oregon_failure_count = 0

        # Affiliated firm enrichment — only if the broker has a brokerage row
        # already. We don't auto-create brokerages from Oregon data; that
        # would risk creating unjoined orphans.
        if broker.brokerage and record.affiliated_firm_name:
            bg = broker.brokerage
            bg.oregon_company_name = record.affiliated_firm_name
            if record.affiliated_firm_address:
                bg.oregon_company_street = record.affiliated_firm_address.street
                bg.oregon_company_city = record.affiliated_firm_address.city
                bg.oregon_company_state = record.affiliated_firm_address.state
                bg.oregon_company_zip = record.affiliated_firm_address.zip

        # Replace disciplinary actions for this broker. Cheap and correct
        # given low volume per broker.
        for existing in list(broker.disciplinary_actions):
            await session.delete(existing)
        for action in record.disciplinary_actions:
            order_date = None
            if action.order_signed_date:
                try:
                    order_date = datetime.strptime(
                        action.order_signed_date.strip(), "%m/%d/%Y"
                    ).date()
                except ValueError:
                    order_date = None
            broker.disciplinary_actions.append(
                BrokerDisciplinaryAction(
                    case_number=(action.case_number or "").strip() or None,
                    order_signed_date=order_date,
                    resolution=(action.resolution or "").strip() or None,
                    found_issues=(action.found_issues or "").strip() or None,
                )
            )

        await session.commit()
        return {
            "status": "success",
            "broker_id": broker_id,
            "license_status": broker.license_status,
            "disciplinary_count": len(record.disciplinary_actions),
        }


@celery_app.task(
    name="app.tasks.oregon_elicense.oregon_elicense_sweep",
    bind=True,
)
def oregon_elicense_sweep(self, max_brokers: int | None = None) -> dict[str, Any]:
    """Monthly sweep — re-enrich brokers that are stale or never enriched."""
    return asyncio.run(_oregon_elicense_sweep(max_brokers))


async def _oregon_elicense_sweep(max_brokers: int | None) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_STALE_AFTER_DAYS)
    queued = 0
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Broker.id)
            .where(
                Broker.license_number.isnot(None),
                or_(
                    Broker.oregon_last_pulled_at.is_(None),
                    Broker.oregon_last_pulled_at < cutoff,
                ),
            )
            .order_by(Broker.oregon_last_pulled_at.asc().nulls_first())
        )
        if max_brokers:
            stmt = stmt.limit(max_brokers)
        broker_ids = list((await session.execute(stmt)).scalars())
        for bid in broker_ids:
            enrich_broker_oregon.delay(str(bid))
            queued += 1

    logger.info("Oregon sweep queued %d brokers for enrichment", queued)
    return {"status": "queued", "queued": queued}


__all__ = ["enrich_broker_oregon", "oregon_elicense_sweep"]
