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

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal, engine
from app.models.broker import Broker, BrokerDisciplinaryAction, Brokerage
from app.services.broker_normalize import normalize_name
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
    try:
        return await _enrich_broker_oregon_inner(broker_id)
    finally:
        # Dispose pooled DB connections while the event loop is still alive.
        # asyncio.run() will close the loop on return, and any pooled connection
        # left behind tries to clean itself up against the closed loop, which
        # fails with "Event loop is closed". Forcing dispose here keeps every
        # task self-contained.
        await engine.dispose()


async def _enrich_broker_oregon_inner(broker_id: str) -> dict[str, Any]:
    # Local import keeps the scraper out of Celery's import path until needed.
    from app.scrapers.oregon_elicense import (  # noqa: PLC0415
        lookup_broker,
        lookup_broker_by_name,
    )

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

        # Two enrichment paths:
        #   1. Broker has a license_number → look up by number (primary)
        #   2. Broker has no license but does have first+last name → try
        #      name-based lookup; only accept a result if it's unambiguous
        #      (Oregon returns exactly 1 match). Multiple matches are flagged
        #      ``ambiguous`` and left untouched.
        try:
            if broker.license_number:
                record = await lookup_broker(broker.license_number)
            elif broker.first_name and broker.last_name:
                record, name_status = await lookup_broker_by_name(
                    broker.first_name, broker.last_name
                )
                if name_status == "ambiguous":
                    broker.oregon_lookup_status = "ambiguous"
                    broker.oregon_last_pulled_at = datetime.now(timezone.utc)
                    broker.oregon_failure_count = 0
                    await session.commit()
                    return {"status": "ambiguous", "broker_id": broker_id}
                # If name lookup found a unique match, persist the discovered
                # license_number so future enrichments use the (faster, more
                # reliable) license-based path.
                if record is not None and record.license_number:
                    broker.license_number = record.license_number
            else:
                broker.oregon_lookup_status = "not_found"
                await session.commit()
                return {
                    "status": "skipped",
                    "broker_id": broker_id,
                    "reason": "no_license_or_name",
                }
        except Exception as exc:
            logger.warning(
                "Oregon eLicense lookup failed for broker %s (license=%s, name=%s %s): %s",
                broker.id,
                broker.license_number,
                broker.first_name,
                broker.last_name,
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

        # Affiliated firm enrichment. Two paths:
        #   - Broker already has a brokerage row → just update oregon_company_*
        #     fields (don't touch the canonical .name; that's Crexi-sourced).
        #   - Broker has no brokerage but Oregon found one → look up an
        #     existing brokerage by case-insensitive name match, or create a
        #     new one. This handles brokers that came in from Crexi without
        #     firm info but whose Oregon record exposes their firm.
        if record.affiliated_firm_name:
            firm_name_normalized = (
                normalize_name(record.affiliated_firm_name)
                or record.affiliated_firm_name.strip()
            )
            bg = broker.brokerage
            if bg is None and firm_name_normalized:
                existing_id = (
                    await session.execute(
                        select(Brokerage.id).where(
                            func.lower(Brokerage.name) == firm_name_normalized.lower()
                        )
                    )
                ).scalar_one_or_none()
                if existing_id is not None:
                    bg = await session.get(Brokerage, existing_id)
                else:
                    bg = Brokerage(name=firm_name_normalized)
                    session.add(bg)
                    await session.flush()  # populate bg.id before we link
                broker.brokerage_id = bg.id
                broker.brokerage = bg
            if bg is not None:
                bg.oregon_company_name = record.affiliated_firm_name
                if record.affiliated_firm_address:
                    bg.oregon_company_street = record.affiliated_firm_address.street
                    bg.oregon_company_city = record.affiliated_firm_address.city
                    bg.oregon_company_state = record.affiliated_firm_address.state
                    bg.oregon_company_zip = record.affiliated_firm_address.zip

        # Replace disciplinary actions for this broker. Cheap and correct
        # given low volume per broker.
        #
        # The flush() between delete and insert is load-bearing: the
        # ``uq_broker_disciplinary_actions_broker_case`` unique constraint
        # would otherwise blow up when the existing case row and a freshly
        # re-pulled record for the same case live in the same flush, and
        # SQLAlchemy emits the INSERT before the DELETE has hit the DB.
        for existing in list(broker.disciplinary_actions):
            await session.delete(existing)
        await session.flush()
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
    try:
        return await _oregon_elicense_sweep_inner(max_brokers)
    finally:
        await engine.dispose()


async def _oregon_elicense_sweep_inner(max_brokers: int | None) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_STALE_AFTER_DAYS)
    queued = 0
    async with AsyncSessionLocal() as session:
        # Eligible brokers: have either a license_number OR (first_name AND
        # last_name), and are stale or never enriched. The task itself picks
        # the right lookup path (license preferred, name as fallback).
        stmt = (
            select(Broker.id)
            .where(
                or_(
                    Broker.license_number.isnot(None),
                    and_(
                        Broker.first_name.isnot(None),
                        Broker.last_name.isnot(None),
                    ),
                ),
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


@celery_app.task(
    name="app.tasks.oregon_elicense.broker_dedup_sweep",
    bind=True,
    max_retries=2,
)
def broker_dedup_sweep(self) -> dict[str, Any]:  # type: ignore[override]
    """Cross-source Broker dedup. Idempotent. Runs after Oregon enrichment so
    license-based grouping has the freshest legal-name data."""
    del self
    return asyncio.run(_broker_dedup_sweep())


async def _broker_dedup_sweep() -> dict[str, Any]:
    from app.services.broker_dedup import merge_duplicate_brokers
    try:
        async with AsyncSessionLocal() as session:
            report = await merge_duplicate_brokers(session)
            await session.commit()
        logger.info(
            "broker dedup sweep: license_merged=%d name_merged=%d "
            "listings_reassigned=%d brokers_deleted=%d skipped_name=%d",
            report.license_groups_merged,
            report.name_groups_merged,
            report.listings_reassigned,
            report.brokers_deleted,
            report.license_groups_skipped_name_mismatch,
        )
        return {
            "license_groups": report.license_groups,
            "license_groups_merged": report.license_groups_merged,
            "name_groups_merged": report.name_groups_merged,
            "listings_reassigned": report.listings_reassigned,
            "brokers_deleted": report.brokers_deleted,
            "skipped_name_mismatch": report.license_groups_skipped_name_mismatch,
            "skipped_groups": report.skipped_groups,
        }
    finally:
        await engine.dispose()


__all__ = ["enrich_broker_oregon", "oregon_elicense_sweep", "broker_dedup_sweep"]
