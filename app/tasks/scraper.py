"""Celery tasks for scraping listing sources through LXC 134 Scrapling."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import usaddress
from celery.utils.log import get_task_logger
from sqlalchemy import case, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.broker import Broker, Brokerage
from app.models.ingestion import DedupStatus, IngestJob, SavedSearchCriteria
from app.models.org import Organization
from app.models.project import Opportunity, OpportunityStatus, OpportunitySource, ScrapedListing
from app.models.property import Building, BuildingStatus, OpportunityBuilding
from app.schemas.broker import BrokerCreate
from app.schemas.scraped_listing import ScrapedListingCreate
from app.observability import (
    begin_observation,
    build_observability_payload,
    elapsed_ms,
    log_observation,
    utc_now,
)
from app.scrapers.apn_utils import normalize_apn
from app.scrapers.crexi import CrxiScraper
from app.scrapers.dedup import deduplicate_batch
from app.scrapers.realie import detect_address_issue
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)
SUPPORTED_SOURCES = {"loopnet", "crexi"}


@celery_app.task(name="app.tasks.scraper.scrape_listings")
def scrape_listings(
    source: str,
    search_params: dict,
    triggered_by: str | None = None,
    trace_id: str | None = None,
) -> str:
    """Dispatch a scrape job via Celery's scraping queue."""
    return asyncio.run(
        _scrape_listings(
            source=source,
            search_params=search_params or {},
            triggered_by=triggered_by,
            trace_id=trace_id,
        )
    )


@celery_app.task(
    name="app.tasks.scraper.scrape_crexi",
    bind=True,
    max_retries=3,
)
def scrape_crexi(
    self,
    triggered_by: str | None = None,
    trace_id: str | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    """Run the dedicated Crexi ingestion flow on the scraping queue."""
    del self
    return asyncio.run(_scrape_crexi(triggered_by=triggered_by, trace_id=trace_id, max_results=max_results))


@celery_app.task(
    name="app.tasks.scraper.scrape_loopnet",
    bind=True,
    max_retries=3,
)
def scrape_loopnet(
    self,
    search_params: dict[str, Any] | None = None,
    triggered_by: str | None = None,
    trace_id: str | None = None,
) -> str:
    """Run the dedicated LoopNet ingestion flow on the scraping queue."""
    del self
    return asyncio.run(
        _scrape_listings(
            source="loopnet",
            search_params=search_params or {},
            triggered_by=triggered_by,
            trace_id=trace_id,
        )
    )


async def _scrape_crexi(
    triggered_by: str | None = None,
    trace_id: str | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    trace_id, started_at, started_at_monotonic = begin_observation(trace_id)
    scraper = CrxiScraper(max_results=max_results if max_results is not None else None)

    async with AsyncSessionLocal() as session:
        ingest_job = IngestJob(
            source="crexi",
            triggered_by=triggered_by,
            status="running",
        )
        session.add(ingest_job)
        await session.flush()
        ingest_job_id = ingest_job.id
        await session.commit()
        log_observation(
            logger,
            "ingest_run_started",
            trace_id=trace_id,
            source="crexi",
            ingest_job_id=ingest_job_id,
            triggered_by=triggered_by,
        )

        try:
            listings, brokers, source_total = await scraper.fetch_all()
            broker_id_map = await upsert_brokers(brokers, session)
            upserted, skipped = await upsert_scraped_listings(
                listings,
                broker_id_map=broker_id_map,
                session=session,
                ingest_job_id=ingest_job_id,
            )
            current_listings = list(
                (
                    await session.execute(
                        select(ScrapedListing).where(ScrapedListing.ingest_job_id == ingest_job_id)
                    )
                ).scalars()
            )
            await _flag_saved_search_matches(current_listings, session=session)
            # Auto-promote disabled — manual promotion only via UI
            # await _auto_promote_listings(current_listings, session=session)
            for listing in current_listings:
                if not listing.is_new:
                    await _sync_listing_to_building(listing, session)
            current_listing_ids = [listing.id for listing in current_listings if listing.id is not None]
            dedup_rows = await deduplicate_batch(
                current_listing_ids,
                ingest_job_id=ingest_job_id,
                session=session,
            )
            pending_review_count = sum(
                1 for row in dedup_rows if row.status == DedupStatus.pending
            )

            completed_job = await session.get(IngestJob, ingest_job_id)
            if completed_job is not None:
                completed_job.records_fetched = len(listings)
                completed_job.records_new = upserted
                completed_job.records_duplicate_exact = skipped
                completed_job.records_flagged_review = pending_review_count
                completed_job.records_rejected = 0
                completed_job.source_total = source_total
                completed_job.status = "completed"
                completed_job.completed_at = datetime.now(UTC)
            await session.commit()

            completed_at = utc_now()
            duration_ms = elapsed_ms(started_at_monotonic)
            log_observation(
                logger,
                "ingest_run_completed",
                trace_id=trace_id,
                source="crexi",
                ingest_job_id=ingest_job_id,
                triggered_by=triggered_by,
                duration_ms=duration_ms,
                records_fetched=len(listings),
                records_new=upserted,
                records_duplicate_exact=skipped,
                records_flagged_review=pending_review_count,
                brokers=len(broker_id_map),
            )
            return {
                "ingest_job_id": str(ingest_job_id),
                "upserted": upserted,
                "skipped": skipped,
                "brokers": len(broker_id_map),
                "source": "crexi",
                "triggered_by": triggered_by,
                "records_fetched": len(listings),
                "records_flagged_review": pending_review_count,
                **build_observability_payload(
                    trace_id=trace_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                ),
            }
        except Exception as exc:
            await session.rollback()
            failed_job = await session.get(IngestJob, ingest_job_id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.completed_at = datetime.now(UTC)
                await session.commit()

            log_observation(
                logger,
                "ingest_run_failed",
                trace_id=trace_id,
                source="crexi",
                ingest_job_id=ingest_job_id,
                triggered_by=triggered_by,
                duration_ms=elapsed_ms(started_at_monotonic),
                error=str(exc),
            )
            logger.exception("Crexi scrape job %s failed: %s", ingest_job_id, exc)
            raise


async def upsert_brokers(
    brokers: list[BrokerCreate],
    session,
) -> dict[int, Any]:
    """Insert or refresh Crexi brokers and return a map of Crexi broker IDs to internal UUIDs."""
    if not brokers:
        return {}

    dialect_name = session.bind.dialect.name if session.bind is not None else "postgresql"
    insert_factory = sqlite_insert if dialect_name == "sqlite" else pg_insert
    broker_id_map: dict[int, Any] = {}

    for broker in brokers:
        payload = broker.model_dump(mode="python", exclude_none=True)
        crexi_broker_id = payload.get("crexi_broker_id")
        if crexi_broker_id is None:
            continue

        brokerage_name = str(payload.pop("brokerage_name", "")).strip() or None
        if brokerage_name:
            brokerage_stmt = (
                insert_factory(Brokerage)
                .values(name=brokerage_name, crexi_name=brokerage_name)
                .on_conflict_do_update(
                    index_elements=[Brokerage.name],
                    set_={
                        Brokerage.crexi_name: brokerage_name,
                    },
                )
                .returning(Brokerage.id)
            )
            payload["brokerage_id"] = (await session.execute(brokerage_stmt)).scalar_one()

        stmt = (
            insert_factory(Broker)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=[Broker.crexi_broker_id],
                set_={
                    Broker.crexi_global_id: payload.get("crexi_global_id"),
                    Broker.first_name: payload.get("first_name"),
                    Broker.last_name: payload.get("last_name"),
                    Broker.thumbnail_url: payload.get("thumbnail_url"),
                    Broker.is_platinum: payload.get("is_platinum", False),
                    Broker.number_of_assets: payload.get("number_of_assets"),
                    Broker.brokerage_id: payload.get("brokerage_id"),
                    Broker.email: payload.get("email"),
                    Broker.phone: payload.get("phone"),
                    Broker.license_number: payload.get("license_number"),
                    Broker.license_state: payload.get("license_state"),
                },
            )
            .returning(Broker.id, Broker.crexi_broker_id)
        )
        row = (await session.execute(stmt)).one()
        if row.crexi_broker_id is not None:
            broker_id_map[int(row.crexi_broker_id)] = row.id

    await session.flush()
    return broker_id_map


async def upsert_scraped_listings(
    listings: list[ScrapedListingCreate],
    *,
    broker_id_map: dict[int, Any],
    session,
    ingest_job_id: Any,
) -> tuple[int, int]:
    """Insert new Crexi listings and refresh matching rows without resetting first-seen timestamps."""
    if not listings:
        return 0, 0

    dialect_name = session.bind.dialect.name if session.bind is not None else "postgresql"
    upserted = 0
    skipped = 0

    # Track newly-inserted listings that need parcel auto-linking:
    # (listing_id, apn, address_normalized, county, city, zoning, property_type)
    new_listing_ids: list[tuple[Any, str | None, str | None, str | None, str | None, str | None, str | None]] = []

    for listing in listings:
        payload = listing.raw_json if isinstance(listing.raw_json, dict) else listing.model_dump(mode="python")
        values = _build_listing_values(
            source=(listing.source or "crexi").strip().lower(),
            ingest_job_id=ingest_job_id,
            listing_payload=payload,
        )
        values["broker_id"] = _resolve_listing_broker_id(payload, broker_id_map)
        values["linked_project_id"] = listing.linked_project_id
        values["parcel_id"] = listing.parcel_id
        values["property_id"] = listing.property_id

        upsert_stmt = _build_upsert_statement(
            dialect_name=dialect_name,
            values=values,
            ingest_job_id=ingest_job_id,
            source=(listing.source or "crexi").strip().lower(),
        )
        row = (await session.execute(upsert_stmt)).one()
        if row.inserted:
            upserted += 1
            if not listing.parcel_id:
                new_listing_ids.append((
                    row.id,
                    values.get("apn"),
                    values.get("address_normalized"),
                    values.get("county"),
                    values.get("city"),
                    values.get("zoning"),
                    values.get("property_type"),
                ))
        else:
            skipped += 1

    await session.flush()

    # Auto-link or create parcels for newly-inserted listings
    if new_listing_ids:
        await _auto_link_parcels(session, new_listing_ids)
        await session.flush()

    return upserted, skipped


async def _auto_link_parcels(
    session: Any,
    new_listing_ids: list[tuple[Any, str | None, str | None, str | None, str | None, str | None, str | None]],
) -> None:
    """For each newly-inserted listing, match to a Parcel via three-tier cascade, classify, and reconcile."""
    from datetime import UTC, datetime as _dt
    from app.reconciliation.matcher import (
        apply_reconciliation,
        reconcile_listing_to_parcel,
    )
    from app.utils.priority import classify as _classify

    for listing_id, apn, address, county, city, zoning, property_type in new_listing_ids:
        try:
            listing = await session.get(ScrapedListing, listing_id)
            if listing is None:
                continue

            parcel, strategy, confidence = await reconcile_listing_to_parcel(session, listing)

            if parcel is not None:
                await apply_reconciliation(session, listing, parcel, strategy, confidence)

            # Classify the listing from whatever data we have (listing fields may differ from parcel)
            # Prefer parcel fields if available, fall back to listing fields
            bucket = _classify(
                zoning_code=(parcel.zoning_code if parcel else None) or zoning,
                zoning_description=(parcel.zoning_description if parcel else None),
                county=(parcel.county if parcel else None) or county,
                jurisdiction=(parcel.jurisdiction if parcel else None) or city,
                current_use=(parcel.current_use if parcel else None),
                property_type=property_type,
            )
            listing.priority_bucket = bucket.value
            listing.priority_bucket_at = _dt.now(UTC)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Parcel auto-link failed for listing %s: %s", listing_id, exc)


async def _flag_saved_search_matches(
    listings: list[ScrapedListing],
    *,
    session,
) -> int:
    new_listings = [listing for listing in listings if listing.is_new]
    if not new_listings:
        return 0

    active_criteria = list(
        (
            await session.execute(
                select(SavedSearchCriteria).where(SavedSearchCriteria.active.is_(True))
            )
        ).scalars()
    )
    if not active_criteria:
        return 0

    matched_count = 0
    for listing in new_listings:
        if listing.matches_saved_criteria:
            matched_count += 1
            continue
        if any(_matches_criteria(listing, criteria) for criteria in active_criteria):
            listing.matches_saved_criteria = True
            matched_count += 1

    if matched_count:
        await session.flush()
    return matched_count


def _matches_criteria(listing: ScrapedListing, criteria: SavedSearchCriteria) -> bool:
    unit_count = listing.unit_count
    if criteria.min_units is not None and (unit_count is None or unit_count < criteria.min_units):
        return False
    if criteria.max_units is not None and (unit_count is None or unit_count > criteria.max_units):
        return False

    if criteria.max_price is not None:
        asking_price = _to_decimal(listing.asking_price)
        max_price = _to_decimal(criteria.max_price)
        if asking_price is None or max_price is None or asking_price > max_price:
            return False

    zip_codes = {str(value).strip() for value in (criteria.zip_codes or []) if str(value).strip()}
    if zip_codes:
        listing_zip = str(listing.zip_code or "").strip()
        if not listing_zip or listing_zip not in zip_codes:
            return False

    property_types = {
        str(value).strip().lower()
        for value in (criteria.property_types or [])
        if str(value).strip()
    }
    if property_types:
        listing_property_type = str(listing.property_type or "").strip().lower()
        if not listing_property_type or listing_property_type not in property_types:
            return False

    sources = {
        str(value).strip().lower()
        for value in (criteria.sources or [])
        if str(value).strip()
    }
    if sources:
        listing_source = str(listing.source or "").strip().lower()
        if listing_source not in sources:
            return False

    return True


async def _get_default_org_id(session) -> "uuid.UUID | None":
    """Return the first organisation id found (single-org deployment)."""
    result = await session.execute(select(Organization.id).limit(1))
    return result.scalar_one_or_none()


async def _promote_listing(
    listing: ScrapedListing,
    session,
    *,
    promotion_source: str,
    ruleset_id: "uuid.UUID | None" = None,
    org_id: "uuid.UUID | None" = None,
) -> Opportunity | None:
    """Create an Opportunity + Building from a listing and link them together.

    Returns the new Opportunity, or None if a link already exists.
    """
    if listing.linked_project_id is not None:
        return None  # already promoted

    if org_id is None:
        org_id = await _get_default_org_id(session)
    if org_id is None:
        logger.warning("Cannot promote listing %s: no organisation found", listing.id)
        return None

    # Determine the source enum value
    source_str = (listing.source or "").lower()
    try:
        opp_source = OpportunitySource(source_str)
    except ValueError:
        opp_source = None

    address_display = (
        listing.address_normalized or listing.address_raw or listing.listing_name or "Unnamed"
    )

    opp = Opportunity(
        org_id=org_id,
        name=address_display,
        status=OpportunityStatus.hypothetical,
        source=opp_source,
        source_type="scraped",
        promotion_source=promotion_source,
        promotion_ruleset_id=ruleset_id,
    )
    session.add(opp)
    await session.flush()  # get opp.id

    # Build or reuse a Building for this listing
    building: Building | None = None
    if listing.property_id:
        building = await session.get(Building, listing.property_id)

    if building is None:
        building = Building(
            name=address_display,
            address_line1=listing.street,
            city=listing.city,
            state=listing.state_code,
            zip_code=listing.zip_code,
            unit_count=listing.units,
            building_sqft=float(listing.gba_sqft) if listing.gba_sqft else None,
            net_rentable_sqft=float(listing.net_rentable_sqft) if listing.net_rentable_sqft else None,
            lot_sqft=float(listing.lot_sqft) if listing.lot_sqft else None,
            year_built=listing.year_built,
            stories=listing.stories,
            property_type=listing.property_type,
            asking_price=float(listing.asking_price) if listing.asking_price else None,
            asking_cap_rate_pct=float(listing.cap_rate) if listing.cap_rate else None,
            status=BuildingStatus.existing,
            scraped_listing_id=listing.id,
        )
        session.add(building)
        await session.flush()
        listing.property_id = building.id

    ob = OpportunityBuilding(
        opportunity_id=opp.id,
        building_id=building.id,
        sort_order=0,
    )
    session.add(ob)

    listing.linked_project_id = opp.id
    await session.flush()

    log_observation(
        logger,
        "listing_promoted",
        listing_id=str(listing.id),
        opportunity_id=str(opp.id),
        building_id=str(building.id),
        promotion_source=promotion_source,
        ruleset_id=str(ruleset_id) if ruleset_id else None,
    )
    return opp


async def _sync_listing_to_building(listing: ScrapedListing, session) -> None:
    """Propagate updated listing fields to the linked Building (if any).

    Called when a listing is refreshed (not new) and has a linked building.
    Only overwrites fields that are non-null in the listing — preserves manual
    edits to fields the listing no longer carries.
    """
    if not listing.property_id:
        return
    building = await session.get(Building, listing.property_id)
    if building is None:
        return

    def _maybe(field, value):
        if value is not None:
            setattr(building, field, value)

    addr_line1 = listing.street
    _maybe("address_line1", addr_line1)
    _maybe("city", listing.city)
    _maybe("state", listing.state_code)
    _maybe("zip_code", listing.zip_code)
    _maybe("unit_count", listing.units)
    if listing.gba_sqft is not None:
        building.building_sqft = float(listing.gba_sqft)
    if listing.lot_sqft is not None:
        building.lot_sqft = float(listing.lot_sqft)
    _maybe("year_built", listing.year_built)
    _maybe("stories", listing.stories)
    _maybe("property_type", listing.property_type)
    if listing.asking_price is not None:
        building.asking_price = float(listing.asking_price)
    if listing.cap_rate is not None:
        building.asking_cap_rate_pct = float(listing.cap_rate)
    # Update the building name if we have a better address now
    new_name = listing.address_normalized or listing.address_raw
    if new_name:
        building.name = new_name
    await session.flush()


async def _auto_promote_listings(
    listings: list[ScrapedListing],
    *,
    session,
    org_id: "uuid.UUID | None" = None,
) -> int:
    """Promote every new listing to an Opportunity.

    For each new listing that has no existing Opportunity link:
    - If it matches an auto_promote=True SavedSearchCriteria ruleset, records that ruleset.
    - Otherwise promotes anyway (all listings are valid) with promotion_source="auto".

    Returns the count of new promotions created.
    """
    new_listings = [l for l in listings if l.is_new and l.linked_project_id is None]
    if not new_listings:
        return 0

    if org_id is None:
        org_id = await _get_default_org_id(session)
    if org_id is None:
        return 0

    active_rulesets = list(
        (
            await session.execute(
                select(SavedSearchCriteria).where(
                    SavedSearchCriteria.active.is_(True),
                    SavedSearchCriteria.auto_promote.is_(True),
                )
            )
        ).scalars()
    )

    promoted = 0
    for listing in new_listings:
        matched_ruleset_id = None
        for criteria in active_rulesets:
            if _matches_criteria(listing, criteria):
                matched_ruleset_id = criteria.id
                break

        opp = await _promote_listing(
            listing,
            session,
            promotion_source="auto",
            ruleset_id=matched_ruleset_id,
            org_id=org_id,
        )
        if opp is not None:
            promoted += 1

    return promoted


async def _scrape_listings(
    source: str,
    search_params: dict,
    triggered_by: str | None = None,
    trace_id: str | None = None,
) -> str:
    trace_id, _, started_at_monotonic = begin_observation(trace_id)
    source_normalized = source.strip().lower()
    if source_normalized not in SUPPORTED_SOURCES:
        raise ValueError(f"Unsupported source '{source}'. Expected one of {sorted(SUPPORTED_SOURCES)}")

    async with AsyncSessionLocal() as session:
        ingest_job = IngestJob(
            source=source_normalized,
            triggered_by=triggered_by,
            status="running",
        )
        session.add(ingest_job)
        await session.flush()
        ingest_job_id = ingest_job.id
        await session.commit()
        log_observation(
            logger,
            "ingest_run_started",
            trace_id=trace_id,
            source=source_normalized,
            ingest_job_id=ingest_job_id,
            triggered_by=triggered_by,
        )

        records_fetched = 0
        records_new = 0
        records_duplicate_exact = 0

        try:
            proxy_config = _build_proxy_config()
            payload: dict[str, Any] = {
                "source": source_normalized,
                "search_params": search_params or {},
            }
            if proxy_config:
                payload["proxy"] = proxy_config

            listings = await _fetch_from_scrapling(payload)
            records_fetched = len(listings)

            dialect_name = session.bind.dialect.name if session.bind is not None else "postgresql"
            for listing in listings:
                values = _build_listing_values(
                    source=source_normalized,
                    ingest_job_id=ingest_job_id,
                    listing_payload=listing,
                )
                upsert_stmt = _build_upsert_statement(
                    dialect_name=dialect_name,
                    values=values,
                    ingest_job_id=ingest_job_id,
                    source=source_normalized,
                )
                row = (await session.execute(upsert_stmt)).one()
                if row.inserted:
                    records_new += 1
                else:
                    records_duplicate_exact += 1

            persisted_listings = list(
                (
                    await session.execute(
                        select(ScrapedListing).where(ScrapedListing.ingest_job_id == ingest_job_id)
                    )
                ).scalars()
            )

            # Auto-link unlinked listings to parcels (mirrors Crexi path)
            unlinked = [
                (
                    sl.id, sl.apn, sl.address_normalized or sl.address_raw,
                    sl.county, sl.city, sl.zoning, sl.property_type,
                )
                for sl in persisted_listings
                if sl.parcel_id is None
            ]
            if unlinked:
                await _auto_link_parcels(session, unlinked)
                await session.flush()

            await _flag_saved_search_matches(persisted_listings, session=session)
            # Auto-promote disabled — manual promotion only via UI
            # await _auto_promote_listings(persisted_listings, session=session)
            for listing in persisted_listings:
                if not listing.is_new:
                    await _sync_listing_to_building(listing, session)
            dedup_rows = await deduplicate_batch(
                persisted_listings,
                ingest_job_id=ingest_job_id,
                session=session,
            )
            pending_review_count = sum(
                1 for row in dedup_rows if row.status == DedupStatus.pending
            )

            ingest_job.records_fetched = records_fetched
            ingest_job.records_new = records_new
            ingest_job.records_duplicate_exact = records_duplicate_exact
            ingest_job.records_flagged_review = pending_review_count
            ingest_job.records_rejected = 0
            ingest_job.status = "completed"
            ingest_job.completed_at = datetime.now(UTC)
            await session.commit()

            log_observation(
                logger,
                "ingest_run_completed",
                trace_id=trace_id,
                source=source_normalized,
                ingest_job_id=ingest_job_id,
                triggered_by=triggered_by,
                duration_ms=elapsed_ms(started_at_monotonic),
                records_fetched=records_fetched,
                records_new=records_new,
                records_duplicate_exact=records_duplicate_exact,
                records_flagged_review=pending_review_count,
            )
            return str(ingest_job_id)
        except Exception as exc:
            await session.rollback()
            failed_job = await session.get(IngestJob, ingest_job_id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.records_fetched = records_fetched
                failed_job.records_new = records_new
                failed_job.records_duplicate_exact = records_duplicate_exact
                failed_job.completed_at = datetime.now(UTC)
                await session.commit()

            log_observation(
                logger,
                "ingest_run_failed",
                trace_id=trace_id,
                source=source_normalized,
                ingest_job_id=ingest_job_id,
                triggered_by=triggered_by,
                duration_ms=elapsed_ms(started_at_monotonic),
                records_fetched=records_fetched,
                records_new=records_new,
                records_duplicate_exact=records_duplicate_exact,
                error=str(exc),
            )
            logger.exception("Scrape job %s failed for %s: %s", ingest_job_id, source_normalized, exc)
            raise


async def _fetch_from_scrapling(payload: dict[str, Any]) -> list[dict[str, Any]]:
    endpoint = f"{settings.lxc134_scrapling_url.rstrip('/')}/scrape"
    timeout = httpx.Timeout(120.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, json=payload)
        response.raise_for_status()

    body = response.json()
    if not isinstance(body, list):
        raise ValueError("Expected Scrapling to return a JSON array of listings.")
    return body


def _build_proxy_config() -> dict[str, str] | None:
    username = (settings.proxyon_residential_username or "").strip()
    if not username:
        return None

    password = settings.proxyon_residential_password or ""
    host = settings.proxyon_residential_host
    port = settings.proxyon_residential_port
    proxy_url = f"http://{username}:{password}@{host}:{port}"
    return {"http": proxy_url, "https": proxy_url}


def _build_upsert_statement(
    *,
    dialect_name: str,
    values: dict[str, Any],
    ingest_job_id: Any,
    source: str,
):
    insert_factory = sqlite_insert if dialect_name == "sqlite" else pg_insert
    table = ScrapedListing.__table__
    return (
        insert_factory(ScrapedListing)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[ScrapedListing.source, ScrapedListing.source_id],
            set_={
                table.c.ingest_job_id: ingest_job_id,
                table.c.source: source,
                table.c.listing_url: values["source_url"],
                table.c.raw_json: values["raw_json"],
                table.c.address_raw: values["address_raw"],
                table.c.address_normalized: values["address_normalized"],
                table.c.street: values["street"],
                table.c.street2: values["street2"],
                table.c.city: values["city"],
                table.c.county: values["county"],
                table.c.state_code: values["state_code"],
                table.c.zip_code: values["zip_code"],
                table.c.lat: values["lat"],
                table.c.lng: values["lng"],
                table.c.property_type: values["property_type"],
                table.c.sub_type: values["sub_type"],
                table.c.investment_type: values["investment_type"],
                table.c.investment_sub_type: values["investment_sub_type"],
                table.c.asking_price: values["asking_price"],
                table.c.price_per_sqft: values["price_per_sqft"],
                table.c.price_per_unit: values["price_per_unit"],
                table.c.price_per_sqft_land: values["price_per_sqft_land"],
                table.c.building_sqft: values["gba_sqft"],
                table.c.net_rentable_sqft: values["net_rentable_sqft"],
                table.c.lot_sqft: values["lot_sqft"],
                table.c.year_built: values["year_built"],
                table.c.year_renovated: values["year_renovated"],
                table.c.unit_count: values["units"],
                table.c.buildings: values["buildings"],
                table.c.stories: values["stories"],
                table.c.parking_spaces: values["parking_spaces"],
                table.c.pads: values["pads"],
                table.c.number_of_keys: values["number_of_keys"],
                table.c.class_: values["class_"],
                table.c.zoning: values["zoning"],
                table.c.apn: values["apn"],
                table.c.apn_normalized: values.get("apn_normalized"),
                table.c.occupancy_pct: values["occupancy_pct"],
                table.c.occupancy_date: values["occupancy_date"],
                table.c.tenancy: values["tenancy"],
                table.c.asking_cap_rate_pct: values["cap_rate"],
                table.c.proforma_cap_rate: values["proforma_cap_rate"],
                table.c.noi: values["noi"],
                table.c.proforma_noi: values["proforma_noi"],
                table.c.lease_term: values["lease_term"],
                table.c.lease_commencement: values["lease_commencement"],
                table.c.lease_expiration: values["lease_expiration"],
                table.c.remaining_term: values["remaining_term"],
                table.c.rent_bumps: values["rent_bumps"],
                table.c.sale_condition: values["sale_condition"],
                table.c.broker_co_op: values["broker_co_op"],
                table.c.ownership: values["ownership"],
                table.c.is_in_opportunity_zone: values["is_in_opportunity_zone"],
                table.c.listing_name: values["listing_name"],
                table.c.description: values["description"],
                table.c.parsed_description: values["parsed_description"],
                table.c.status: values["status"],
                table.c.listed_at: values["listed_at"],
                table.c.updated_at_source: values["updated_at_source"],
                table.c.broker_id: values.get("broker_id"),
                table.c.parcel_id: values.get("parcel_id"),
                table.c.property_id: values.get("property_id"),
                table.c.linked_project_id: func.coalesce(table.c.linked_project_id, values.get("linked_project_id")),
                table.c.matches_saved_criteria: values["matches_saved_criteria"],
                table.c.scraped_at: func.now(),
                # is_new is NOT cleared on re-scrape — only user actions (promote/archive) clear it
                table.c.is_new: table.c.is_new,
                # archived is preserved — user-set, never overwritten by scraper
                table.c.archived: table.c.archived,
                # realie_skip: preserve existing flag UNLESS the incoming record now has an APN,
                # in which case clear it — parcel is resolvable regardless of address quality.
                table.c.realie_skip: case(
                    (values["apn"] != None, False),  # noqa: E711
                    else_=table.c.realie_skip,
                ),
            },
        )
        .returning(
            ScrapedListing.id,
            # xmax = 0 means the row was freshly inserted (not updated)
            literal_column("(xmax = '0')").label("inserted"),
        )
    )


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_numbers(value: Any) -> list[Decimal]:
    if value in (None, ""):
        return []
    if isinstance(value, Decimal):
        return [value]
    if isinstance(value, (int, float)):
        return [Decimal(str(value))]

    matches = re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?", str(value))
    return [Decimal(match.replace(",", "")) for match in matches]


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _to_midpoint_decimal(value: Any) -> Decimal | None:
    numbers = _extract_numbers(value)
    if not numbers:
        return _to_decimal(value)
    if len(numbers) == 1:
        return numbers[0]
    return sum(numbers) / Decimal(len(numbers))


def _to_fractional_decimal(value: Any) -> Decimal | None:
    decimal_value = _to_midpoint_decimal(value)
    if decimal_value is None:
        return None
    raw_text = str(value).strip().lower()
    if "%" in raw_text or decimal_value > Decimal("1"):
        return decimal_value / Decimal("100")
    return decimal_value


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    decimal_value = _to_midpoint_decimal(value)
    if decimal_value is None:
        return None
    return int(decimal_value)


def _to_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    return None


def _to_string_list(value: Any) -> list[str] | None:
    if value in (None, ""):
        return None
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return [piece.strip() for piece in re.split(r"[,;/]", text) if piece.strip()]
    return [str(value).strip()]


def _strip_html(value: Any) -> str | None:
    """Convert HTML marketing description to clean plain text."""
    if value in (None, ""):
        return None
    text = str(value)
    text = re.sub(r"<(?:p|br|li|div|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&nbsp;", " ").replace("&#8203;", "").replace("\u200b", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text or None


def _sqft_or_none(value: Any) -> Decimal | None:
    """Like _to_decimal but nulls out implausible placeholder values (< 10 sqft)."""
    d = _to_decimal(value)
    if d is None:
        return None
    return None if d < Decimal("10") else d


def _to_sqft(value: Any) -> Decimal | None:
    decimal_value = _to_midpoint_decimal(value)
    if decimal_value is None:
        return None

    text = str(value).strip().lower()
    if "ac" in text:
        decimal_value *= Decimal("43560")
    return decimal_value.quantize(Decimal("0.000001"))


def _to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _extract_summary_details(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summaryDetails") or payload.get("summary_details") or {}
    if isinstance(summary, dict):
        return summary

    extracted: dict[str, Any] = {}
    if isinstance(summary, list):
        for item in summary:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("label") or item.get("title") or item.get("name")
            if key in (None, ""):
                continue
            value = item.get("value")
            if value in (None, ""):
                value = item.get("formattedValue") or item.get("displayValue") or item.get("values")
            label_lower = str(item.get("label") or "").lower()
            if "acre" in label_lower and value not in (None, ""):
                try:
                    extracted[str(key)] = Decimal(str(value)) * Decimal("43560")
                except Exception:
                    extracted[str(key)] = value
            else:
                extracted[str(key)] = value
    return extracted


def _summary_value(summary: dict[str, Any], *keys: str) -> Any:
    lower_lookup = {str(key).lower(): value for key, value in summary.items()}
    for key in keys:
        if key in summary and summary[key] not in (None, ""):
            return summary[key]
        lowered = key.lower()
        if lowered in lower_lookup and lower_lookup[lowered] not in (None, ""):
            return lower_lookup[lowered]
    return None


def _extract_location(payload: dict[str, Any]) -> dict[str, Any]:
    locations = payload.get("locations")
    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict):
                return item
    location = payload.get("location")
    return location if isinstance(location, dict) else {}


def _compose_full_address(address: str | None, city: str | None, state_code: str | None, zip_code: str | None) -> str | None:
    pieces = [piece.strip() for piece in [address, city, state_code, zip_code] if piece not in (None, "")]
    if not pieces:
        return None
    if address and city and state_code and zip_code:
        return f"{address.strip()}, {city.strip()}, {state_code.strip()} {zip_code.strip()}"
    return ", ".join(pieces)


def _normalize_address(address_raw: str | None) -> str | None:
    if address_raw in (None, ""):
        return None

    try:
        tagged, _ = usaddress.tag(str(address_raw))
    except Exception:
        return str(address_raw).strip()

    ordered_keys = (
        "AddressNumber",
        "StreetNamePreDirectional",
        "StreetName",
        "StreetNamePostType",
        "OccupancyType",
        "OccupancyIdentifier",
        "PlaceName",
        "StateName",
        "ZipCode",
    )
    parts = [str(tagged[key]).strip() for key in ordered_keys if tagged.get(key)]
    normalized = " ".join(part for part in parts if part)
    return normalized or str(address_raw).strip()


def _build_source_url(source: str, listing_payload: dict[str, Any], source_id: str | None) -> str | None:
    # Prefer explicit stored URL fields; skip raw "url" which Crexi may set to a brokerage page
    direct_url = _first_present(listing_payload, "source_url", "listing_url")
    if direct_url not in (None, ""):
        return str(direct_url)

    slug = _first_present(listing_payload, "urlSlug", "url_slug", "slug")
    if slug not in (None, ""):
        if source == "crexi":
            # Crexi canonical URL is /properties/{id}/{slug}
            if source_id not in (None, ""):
                return f"https://www.crexi.com/properties/{source_id}/{slug}"
            return f"https://www.crexi.com/properties/{slug}"
        return str(slug)

    return source_id


def _resolve_listing_broker_id(
    listing_payload: dict[str, Any],
    broker_id_map: dict[int, Any],
) -> Any:
    raw_brokers = listing_payload.get("brokers") or listing_payload.get("broker") or []
    if isinstance(raw_brokers, dict):
        raw_brokers = [raw_brokers]

    if isinstance(raw_brokers, list):
        for broker in raw_brokers:
            if not isinstance(broker, dict):
                continue
            crexi_broker_id = _to_int(_first_present(broker, "crexi_broker_id", "id"))
            if crexi_broker_id is not None and crexi_broker_id in broker_id_map:
                return broker_id_map[crexi_broker_id]

    crexi_broker_id = _to_int(_first_present(listing_payload, "crexi_broker_id", "broker_id"))
    if crexi_broker_id is not None:
        return broker_id_map.get(crexi_broker_id)
    return None


def _build_listing_values(
    *,
    source: str,
    ingest_job_id: Any,
    listing_payload: dict[str, Any],
) -> dict[str, Any]:
    summary = _extract_summary_details(listing_payload)
    location = _extract_location(listing_payload)

    source_id = _first_present(
        listing_payload,
        "source_id",
        "sourceId",
        "listing_id",
        "listingId",
        "id",
    )
    listing_url = _build_source_url(source, listing_payload, str(source_id) if source_id not in (None, "") else None)
    if listing_url in (None, ""):
        raise ValueError("Scraped listing payload is missing a source URL or urlSlug/listing identifier.")

    if source_id in (None, ""):
        source_id = listing_url

    address = _first_present(location, "address", "street", "line1")
    city = _first_present(location, "city", "municipality")
    county = _first_present(location, "county")
    _state_raw = _first_present(location, "state", "stateCode")
    if isinstance(_state_raw, dict):
        state_code = _state_raw.get("code") or _state_raw.get("abbreviation") or _state_raw.get("name")
    else:
        state_code = _state_raw
    zip_code = _first_present(location, "zip", "zipCode", "postalCode")
    full_address = _first_present(location, "fullAddress", "full_address") or _compose_full_address(
        str(address) if address not in (None, "") else None,
        str(city) if city not in (None, "") else None,
        str(state_code) if state_code not in (None, "") else None,
        str(zip_code) if zip_code not in (None, "") else None,
    )

    address_raw = _first_present(
        listing_payload,
        "address_raw",
        "address",
        "property_address",
        "location",
    )
    if address_raw in (None, ""):
        address_raw = full_address or address

    return {
        "ingest_job_id": ingest_job_id,
        "source": source,
        "source_id": str(source_id),
        "source_url": str(listing_url),
        "address_raw": str(address_raw).strip() if address_raw not in (None, "") else None,
        "address_normalized": _normalize_address(str(full_address or address_raw)) if (full_address or address_raw) not in (None, "") else None,
        "street": str(address).strip() if address not in (None, "") else None,
        "street2": str(_first_present(location, "street2", "address2", "line2")).strip() if _first_present(location, "street2", "address2", "line2") not in (None, "") else None,
        "city": str(city).strip() if city not in (None, "") else None,
        "county": str(county).strip() if county not in (None, "") else None,
        "state_code": str(state_code).strip() if state_code not in (None, "") else None,
        "zip_code": str(zip_code).strip() if zip_code not in (None, "") else None,
        "lat": _to_decimal(_first_present(location, "lat", "latitude")),
        "lng": _to_decimal(_first_present(location, "lng", "lon", "longitude")),
        "property_type": _first_present(listing_payload, "propertyType", "property_type")
            or (_to_string_list(_first_present(listing_payload, "types")) or [None])[0],
        "sub_type": _to_string_list(
            _first_present(listing_payload, "propertySubType", "sub_type", "subtypes", "customSubtypes")
            or _summary_value(summary, "SubType")
        ),
        "investment_type": _first_present(listing_payload, "investmentType", "investment_type"),
        "investment_sub_type": _first_present(listing_payload, "investmentSubType", "investment_sub_type"),
        "asking_price": _to_decimal(
            _first_present(listing_payload, "asking_price", "price", "askingPrice")
            or _summary_value(summary, "AskingPrice", "Price")
        ),
        "price_per_sqft": _to_decimal(_summary_value(summary, "PricePerSqFt", "PriceSqFt")),
        "price_per_unit": _to_decimal(_summary_value(summary, "PricePerItem", "PricePerUnit")) or (
            lambda p, u: (p / u) if (p is not None and u is not None and u != 0) else None
        )(
            _to_decimal(_summary_value(summary, "AskingPrice", "Price") or _first_present(listing_payload, "asking_price", "price", "askingPrice")),
            _to_decimal(_summary_value(summary, "Units") or _first_present(listing_payload, "unit_count", "units", "number_of_units")),
        ),
        "price_per_sqft_land": _to_midpoint_decimal(_summary_value(summary, "PriceSqFtLand")),
        "gba_sqft": _sqft_or_none(
            _first_present(listing_payload, "building_sqft", "building_size_sqft", "buildingSizeSqft")
            or _summary_value(summary, "SquareFootage", "GrossBuildingArea")
        ),
        "net_rentable_sqft": _to_decimal(_summary_value(summary, "NetRentableArea")),
        "lot_sqft": _to_sqft(
            _first_present(listing_payload, "lot_sqft", "lot_size_sqft", "lotSizeSqft")
            or _summary_value(summary, "LotSize")
        ),
        "year_built": _to_int(
            _first_present(listing_payload, "year_built", "built", "yearBuilt")
            or _summary_value(summary, "YearBuilt")
        ),
        "year_renovated": _to_int(_summary_value(summary, "YearsRenovated", "YearRenovated")),
        "units": _to_int(
            _first_present(listing_payload, "unit_count", "units", "number_of_units")
            or _summary_value(summary, "Units", "NumberOfUnits")
        ),
        "buildings": _to_int(_summary_value(summary, "Buildings", "NumberOfBuildings")),
        "stories": _to_int(_summary_value(summary, "Stories")),
        "parking_spaces": _to_int(_summary_value(summary, "ParkingSpots", "ParkingSpaces")),
        "pads": _to_int(_summary_value(summary, "Pads")),
        "number_of_keys": _to_int(_summary_value(summary, "NumberOfKeys", "Keys")),
        "class_": _summary_value(summary, "Class"),
        "zoning": _summary_value(summary, "PermittedZoning", "Zoning"),
        "apn": _summary_value(summary, "Apn", "APN"),
        "apn_normalized": normalize_apn(_summary_value(summary, "Apn", "APN")),
        "occupancy_pct": _to_fractional_decimal(_summary_value(summary, "Occupancy")),
        "occupancy_date": _to_datetime(_summary_value(summary, "OccupancyDate")),
        "tenancy": _summary_value(summary, "Tenancy"),
        "cap_rate": _to_fractional_decimal(
            _first_present(listing_payload, "asking_cap_rate_pct", "cap_rate_pct", "capRate")
            or _summary_value(summary, "CapRate")
        ),
        "proforma_cap_rate": _to_fractional_decimal(_summary_value(summary, "ProformaCapRate")),
        "noi": _to_decimal(_summary_value(summary, "NOI", "NetOperatingIncome")),
        "proforma_noi": _to_decimal(_summary_value(summary, "ProformaNOI")),
        "lease_term": _to_decimal(_summary_value(summary, "LeaseTerm")),
        "lease_commencement": _to_datetime(_summary_value(summary, "LeaseCommencement")),
        "lease_expiration": _to_datetime(_summary_value(summary, "LeaseExpiration")),
        "remaining_term": _to_decimal(_summary_value(summary, "RemainingTerm")),
        "rent_bumps": _summary_value(summary, "RentBumps"),
        "sale_condition": _summary_value(summary, "SaleCondition"),
        "broker_co_op": _to_bool(_summary_value(summary, "BrokerCoOp")) or False,
        "ownership": _summary_value(summary, "Ownership"),
        "is_in_opportunity_zone": _to_bool(_summary_value(summary, "OpportunityZone", "IsInOpportunityZone")),
        "listing_name": _first_present(listing_payload, "listing_name", "name", "title"),
        "description": _strip_html(_first_present(listing_payload, "marketingDescription", "description")),
        "parsed_description": None,
        "status": _first_present(listing_payload, "status"),
        "listed_at": _to_datetime(_first_present(listing_payload, "activatedOn", "listed_at", "createdAt")),
        "updated_at_source": _to_datetime(_first_present(listing_payload, "updatedOn", "updated_at_source", "updatedAt")),
        "raw_json": listing_payload,
        "is_new": True,
        "first_seen_at": func.now(),
        "matches_saved_criteria": bool(listing_payload.get("matches_saved_criteria", False)),
        "canonical_id": None,
        "last_seen_at": func.now(),
        "broker_id": None,
        "parcel_id": None,
        "property_id": None,
        "linked_project_id": None,
        "realie_skip": detect_address_issue(
            str(address).strip() if address not in (None, "") else None
        ) is not None,
    }


__all__ = [
    "scrape_crexi",
    "scrape_loopnet",
    "scrape_listings",
    "upsert_brokers",
    "upsert_scraped_listings",
    "_scrape_crexi",
]
