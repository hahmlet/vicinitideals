"""Celery tasks for LoopNet RapidAPI ingest, seed experiment, and monthly refresh.

Three tasks registered in app/tasks/celery_app.py beat schedule:
  loopnet_weekly_sweep              — discover new listings inside active polygons
  loopnet_experiment_daily_refresh  — flag-gated; snapshots all captured listings daily
  loopnet_monthly_refresh           — runs only when experiment is OFF; priority-queue refresh
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.api_call_log import ApiCallLog  # noqa: F401 — ensure registered
from app.models.broker import Broker
from app.models.ingestion import IngestJob
from app.models.listing_snapshot import ListingSnapshot
from app.models.project import ScrapedListing
from app.scrapers.loopnet import (
    BudgetExhausted,
    BudgetGuard,
    bbox_search,
    classify_categories,
    classify_from_bulk,
    classify_lease_from_bulk,
    classify_multifamily,
    clip_to_polygon,
    fetch_bulk_details,
    fetch_extended_details,
    fetch_lease_details,
    fetch_sale_details,
    lease_bbox_search,
    load_polygons,
    map_lease_to_scraped_listing,
    map_to_scraped_listing,
    parse_target_ed_categories,
    polygon_bbox,
    should_fetch_extended_details,
    should_fetch_sale_details_after_bulk,
    should_ingest_lease_after_bulk,
)
from app.scrapers.loopnet_broker import (
    extract_brokers_from_sale_details,
    upsert_broker_from_loopnet,
)
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


async def _upsert_loopnet_listing(
    values: dict[str, Any],
    *,
    session: AsyncSession,
    ingest_job_id: uuid.UUID,
) -> bool:
    """Direct ON CONFLICT upsert for a LoopNet/loopnet_lease listing.

    Uses insert_factory(ScrapedListing) passing the mapped class, which
    translates our ORM attribute names (source_url, gba_sqft, cap_rate, etc.)
    to their actual DB column names (listing_url, building_sqft,
    asking_cap_rate_pct). The ON CONFLICT set_ dict is built from the actual
    column objects so stmt.excluded can reference them correctly.

    Bypasses app/tasks/scraper.py upsert_scraped_listings() because that helper
    re-parses raw_json via Crexi-shaped extractors and would overwrite our
    carefully-mapped Decimal values.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from app.models.project import ScrapedListing

    values = {**values}
    values.setdefault("ingest_job_id", ingest_job_id)
    values["id"] = values.get("id") or uuid.uuid4()
    # first_seen_at only set on insert (ON CONFLICT keeps existing value)
    values.setdefault("first_seen_at", datetime.now(UTC))
    values["last_seen_at"] = datetime.now(UTC)

    dialect = session.bind.dialect.name if session.bind is not None else "postgresql"
    insert_factory = pg_insert if dialect == "postgresql" else sqlite_insert

    stmt = insert_factory(ScrapedListing).values(**values)

    # Build set_ dict using actual DB column objects (not ORM attribute names).
    # Skip identity + insert-only columns.
    table = ScrapedListing.__table__
    skip_on_update: set[str] = {"id", "source", "source_id", "seen_at", "ingest_job_id"}
    update_cols = {}
    for col in table.columns:
        if col.name in skip_on_update:
            continue
        if col.name == "scraped_at":
            # refresh last-seen stamp on every upsert
            update_cols[col.name] = datetime.now(UTC)
            continue
        update_cols[col.name] = stmt.excluded[col.name]

    stmt = stmt.on_conflict_do_update(
        index_elements=["source", "source_id"],
        set_=update_cols,
    )
    await session.execute(stmt)
    return True


@asynccontextmanager
async def _task_session() -> "asyncio.AsyncContextManager[AsyncSession]":
    """Yield an AsyncSession backed by a task-local engine with NullPool.

    Celery workers fork a subprocess per task, and `asyncio.run()` creates a
    fresh event loop each invocation. The module-level `AsyncSessionLocal`
    engine caches connections bound to the first loop that used it, which
    causes `got Future attached to a different loop` errors on subsequent
    task runs in the same worker process. NullPool sidesteps this by opening
    a fresh connection per session and closing it on exit.
    """
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Task: weekly sweep — discover + classify + ingest new listings
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.loopnet_ingest.loopnet_weekly_sweep", bind=True)
def loopnet_weekly_sweep(self) -> dict[str, Any]:
    """Run weekly discovery sweep over all active polygons."""
    del self
    return asyncio.run(_loopnet_weekly_sweep())


async def _loopnet_weekly_sweep() -> dict[str, Any]:  # noqa: PLR0915
    # Track every Broker row touched during this run so we can auto-trigger
    # Oregon eLicense enrichment on any that have a license # OR (first +
    # last) name and haven't been enriched yet. Same pattern as the Crexi
    # ingest in app/tasks/scraper.py.
    batch_broker_ids: set[uuid.UUID] = set()
    """Sweep every active polygon; tag new listings; fetch ED per polygon-tier policy."""
    polygons = load_polygons()
    target_ed_categories = parse_target_ed_categories(
        settings.loopnet_target_ed_categories
    )

    total_new = 0
    total_ed_fetched = 0
    per_polygon: dict[str, dict[str, int]] = {}
    errors: list[str] = []

    async with _task_session() as session:
        ingest_job = IngestJob(source="loopnet", triggered_by="beat", status="running")
        session.add(ingest_job)
        await session.flush()
        ingest_job_id = ingest_job.id
        await session.commit()

        try:
            async with BudgetGuard(session) as guard:
                # Collect (listingId → (row, containing_polygons)) across all polygons,
                # so a listing matched by multiple polygons is only fetched once.
                unified: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
                for polygon in polygons:
                    name = polygon["name"]
                    points = polygon["points"]
                    bbox = polygon_bbox(points)
                    per_polygon[name] = {"bbox_rows": 0, "clipped": 0, "new": 0}

                    try:
                        rows = await bbox_search(guard, bbox)
                    except BudgetExhausted as exc:
                        errors.append(f"{name}: {exc}")
                        break

                    clipped = clip_to_polygon(rows, points)
                    per_polygon[name]["bbox_rows"] = len(rows)
                    per_polygon[name]["clipped"] = len(clipped)
                    logger.info(
                        "loopnet polygon=%s purpose=%s bbox_rows=%s clipped=%s",
                        name, polygon.get("purpose"), len(rows), len(clipped),
                    )
                    for row in clipped:
                        lid = str(row["listingId"])
                        if lid in unified:
                            unified[lid][1].append(polygon)
                        else:
                            unified[lid] = (row, [polygon])

                # Commit api_call_log entries from all bbox searches before
                # moving on — protects these from rollback if bulk/SD fails.
                await session.commit()

                existing = await _existing_loopnet_ids(session, list(unified.keys()))
                candidate_ids = [lid for lid in unified if lid not in existing]

                # Optional bulk-triage pass: classify from lean bulkDetails before
                # spending 1 SaleDetails call per listing. Cuts SD volume ~55%.
                bulk_cats: dict[str, set[str]] = {}
                if settings.loopnet_use_bulk_triage and candidate_ids:
                    try:
                        bulk_rows = await fetch_bulk_details(guard, candidate_ids)
                    except BudgetExhausted as exc:
                        errors.append(f"bulk triage: {exc}")
                        bulk_rows = []
                    for brow in bulk_rows:
                        lid = str(brow.get("listingId") or "")
                        if lid:
                            bulk_cats[lid] = classify_from_bulk(brow)

                # Commit bulk-triage api_call_log entries too
                await session.commit()

                for lid in candidate_ids:
                    row, containing_polygons = unified[lid]
                    coords = row.get("coordinations") or [[None, None]]
                    lng, lat = coords[0][0], coords[0][1]
                    polygon_purposes = {
                        p.get("purpose", "target") for p in containing_polygons
                    }
                    polygon_names = [p["name"] for p in containing_polygons]

                    # Triage gate: if we have bulk data, skip listings we'd never
                    # fetch SD for anyway. Saves the 1-SD-per-listing overhead.
                    if bulk_cats and lid in bulk_cats:
                        if not should_fetch_sale_details_after_bulk(
                            bulk_cats[lid], polygon_purposes, target_ed_categories
                        ):
                            continue

                    try:
                        sale = await fetch_sale_details(guard, lid)
                    except BudgetExhausted as exc:
                        errors.append(f"listing {lid}: {exc}")
                        break
                    if not sale:
                        continue

                    categories = classify_categories(sale)
                    ext = None
                    if should_fetch_extended_details(
                        categories, polygon_purposes, target_ed_categories
                    ):
                        try:
                            ext = await fetch_extended_details(guard, lid)
                            total_ed_fetched += 1
                        except BudgetExhausted as exc:
                            errors.append(f"listing {lid} extended: {exc}")
                            ext = None

                    mapped = map_to_scraped_listing(
                        sale, ext, listing_id=lid, lat=lat, lng=lng
                    )
                    mapped["polygon_tags"] = polygon_names

                    # Upsert brokers (free — uses inline SD.broker[*] data,
                    # no API calls). First broker becomes the listing's
                    # primary broker_id; remaining brokers get rows linked
                    # to other listings of theirs but not this one.
                    brokers = extract_brokers_from_sale_details(sale)
                    primary_broker_id = None
                    for i, b in enumerate(brokers):
                        try:
                            bid = await upsert_broker_from_loopnet(session, b)
                        except Exception as exc:  # noqa: BLE001
                            logger.exception(
                                "broker upsert failed for slug=%s on listing %s",
                                b.get("loopnet_broker_id"), lid,
                            )
                            errors.append(
                                f"broker {b.get('loopnet_broker_id')}: {exc}"
                            )
                            continue
                        if bid is not None:
                            batch_broker_ids.add(bid)
                        if i == 0 and bid is not None:
                            primary_broker_id = bid
                    if primary_broker_id is not None:
                        mapped["broker_id"] = primary_broker_id

                    try:
                        await _upsert_loopnet_listing(
                            mapped, session=session, ingest_job_id=ingest_job_id,
                        )
                        # Commit per-listing so budget log + upsert survive
                        # even if a later listing crashes or hits budget.
                        await session.commit()
                        total_new += 1
                        for pname in polygon_names:
                            if pname in per_polygon:
                                per_polygon[pname]["new"] += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("loopnet upsert failed for %s", lid)
                        errors.append(f"upsert {lid}: {exc}")
                        await session.rollback()
                        # rollback discards pending api_call_log from this listing too
                        # but budget already charged at RapidAPI — track in errors

            job = await session.get(IngestJob, ingest_job_id)
            if job is not None:
                job.records_fetched = total_new
                job.records_new = total_new
                job.status = "completed" if not errors else "partial"
                job.completed_at = datetime.now(UTC)
            await session.commit()

            # Auto-trigger Oregon eLicense enrichment for any broker in this
            # batch that has either a license_number OR a first+last name and
            # has never been enriched. Mirrors the Crexi auto-trigger in
            # app/tasks/scraper.py.
            if batch_broker_ids:
                from sqlalchemy import and_, or_  # noqa: PLC0415

                unenriched = (
                    await session.execute(
                        select(Broker.id).where(
                            Broker.id.in_(list(batch_broker_ids)),
                            or_(
                                Broker.license_number.isnot(None),
                                and_(
                                    Broker.first_name.isnot(None),
                                    Broker.last_name.isnot(None),
                                ),
                            ),
                            Broker.oregon_last_pulled_at.is_(None),
                        )
                    )
                ).scalars().all()
                if unenriched:
                    from app.tasks.oregon_elicense import enrich_broker_oregon  # noqa: PLC0415

                    for bid_oregon in unenriched:
                        enrich_broker_oregon.delay(str(bid_oregon))
                    logger.info(
                        "Queued Oregon enrichment for %d LoopNet brokers from this batch",
                        len(unenriched),
                    )
        except Exception:
            await session.rollback()
            raise

    return {
        "new_listings": total_new,
        "ed_fetched": total_ed_fetched,
        "per_polygon": per_polygon,
        "errors": errors,
    }


async def _existing_loopnet_ids(session, candidate_ids: list[str]) -> set[str]:
    if not candidate_ids:
        return set()
    stmt = select(ScrapedListing.source_id).where(
        ScrapedListing.source == "loopnet",
        ScrapedListing.source_id.in_(candidate_ids),
    )
    result = await session.execute(stmt)
    return {row[0] for row in result}


# ---------------------------------------------------------------------------
# Task: experiment daily refresh — flag-gated; snapshots for 30-day study
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.loopnet_ingest.loopnet_experiment_daily_refresh", bind=True
)
def loopnet_experiment_daily_refresh(self) -> dict[str, Any]:
    del self
    return asyncio.run(_loopnet_experiment_daily_refresh())


def _experiment_end_date() -> date | None:
    raw = settings.loopnet_experiment_end_date
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning("Invalid LOOPNET_EXPERIMENT_END_DATE: %r", raw)
        return None


async def _loopnet_experiment_daily_refresh() -> dict[str, Any]:
    if not settings.loopnet_experiment_enabled:
        return {"skipped": "experiment disabled"}

    end_date = _experiment_end_date()
    today = datetime.now(UTC).date()
    if end_date and today > end_date:
        return {"skipped": f"past end_date {end_date.isoformat()}"}

    snapshots_taken = 0
    ext_snapshots = 0
    errors: list[str] = []

    async with _task_session() as session:
        stmt = select(ScrapedListing).where(ScrapedListing.source == "loopnet")
        result = await session.execute(stmt)
        listings: list[ScrapedListing] = list(result.scalars())

        async with BudgetGuard(session, today=today) as guard:
            for listing in listings:
                try:
                    sale = await fetch_sale_details(guard, listing.source_id)
                except BudgetExhausted as exc:
                    errors.append(str(exc))
                    break
                if not sale:
                    continue

                last_updated = sale.get("lastUpdated")
                session.add(ListingSnapshot(
                    id=uuid.uuid4(),
                    listing_id=listing.id,
                    endpoint="sale_details",
                    raw_json=sale,
                    source_last_updated=_parse_update_ts(last_updated),
                ))
                snapshots_taken += 1

                # If MF and lastUpdated changed since last snapshot, also pull ExtendedDetails
                if classify_multifamily(sale) and await _sale_changed(session, listing.id, sale):
                    try:
                        ext = await fetch_extended_details(guard, listing.source_id)
                    except BudgetExhausted as exc:
                        errors.append(str(exc))
                        break
                    if ext:
                        session.add(ListingSnapshot(
                            id=uuid.uuid4(),
                            listing_id=listing.id,
                            endpoint="extended_details",
                            raw_json=ext,
                            source_last_updated=_parse_update_ts(
                                (ext.get("saleSummary") or {}).get("lastUpdated")
                            ),
                        ))
                        ext_snapshots += 1

        await session.commit()

    return {
        "sale_snapshots": snapshots_taken,
        "extended_snapshots": ext_snapshots,
        "errors": errors,
    }


def _parse_update_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


async def _sale_changed(session, listing_id: uuid.UUID, sale: dict[str, Any]) -> bool:
    """Compare current lastUpdated against the most recent prior snapshot."""
    current_ts = _parse_update_ts(sale.get("lastUpdated"))
    if current_ts is None:
        return True  # Unknown — err on side of refreshing
    stmt = (
        select(ListingSnapshot.source_last_updated)
        .where(
            ListingSnapshot.listing_id == listing_id,
            ListingSnapshot.endpoint == "sale_details",
        )
        .order_by(ListingSnapshot.captured_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    prior = result.scalar_one_or_none()
    return prior != current_ts


# ---------------------------------------------------------------------------
# Task: monthly refresh — priority queue, budget-aware
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.loopnet_ingest.loopnet_monthly_refresh", bind=True)
def loopnet_monthly_refresh(self) -> dict[str, Any]:
    del self
    return asyncio.run(_loopnet_monthly_refresh())


# ---------------------------------------------------------------------------
# Task: one-off lease comp seed (manual invocation during seed month)
# ---------------------------------------------------------------------------

@celery_app.task(name="app.tasks.loopnet_ingest.loopnet_seed_lease_comps", bind=True)
def loopnet_seed_lease_comps(self) -> dict[str, Any]:
    """Manual one-off: scrape lease listings in every active polygon + ingest as
    source='loopnet_lease'. Not on the beat schedule — invoke via:

        celery -A app.tasks.celery_app call app.tasks.loopnet_ingest.loopnet_seed_lease_comps
    """
    del self
    return asyncio.run(_loopnet_seed_lease_comps())


async def _loopnet_seed_lease_comps() -> dict[str, Any]:
    polygons = load_polygons()
    total_new = 0
    per_polygon: dict[str, dict[str, int]] = {}
    errors: list[str] = []

    async with _task_session() as session:
        ingest_job = IngestJob(
            source="loopnet_lease", triggered_by="manual", status="running"
        )
        session.add(ingest_job)
        await session.flush()
        ingest_job_id = ingest_job.id
        await session.commit()

        try:
            async with BudgetGuard(session) as guard:
                unified: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
                for polygon in polygons:
                    name = polygon["name"]
                    points = polygon["points"]
                    bbox = polygon_bbox(points)
                    per_polygon[name] = {"bbox_rows": 0, "clipped": 0, "new": 0}

                    try:
                        rows = await lease_bbox_search(guard, bbox)
                    except BudgetExhausted as exc:
                        errors.append(f"{name} (lease bbox): {exc}")
                        break

                    clipped = clip_to_polygon(rows, points)
                    per_polygon[name]["bbox_rows"] = len(rows)
                    per_polygon[name]["clipped"] = len(clipped)
                    for row in clipped:
                        lid = str(row["listingId"])
                        if lid in unified:
                            unified[lid][1].append(polygon)
                        else:
                            unified[lid] = (row, [polygon])

                existing = await _existing_lease_ids(session, list(unified.keys()))
                candidate_ids = [lid for lid in unified if lid not in existing]

                # Bulk-triage lease candidates — only pay for LeaseDetails on
                # MF + mixed-use leases (commercial lease data is low-value
                # for our MF income underwriting).
                triage_keepers: list[str] = []
                skipped_by_triage = 0
                if settings.loopnet_use_bulk_triage and candidate_ids:
                    try:
                        bulk_rows = await fetch_bulk_details(guard, candidate_ids)
                    except BudgetExhausted as exc:
                        errors.append(f"lease bulk triage: {exc}")
                        bulk_rows = []
                    keep_set: set[str] = set()
                    for brow in bulk_rows:
                        lid = str(brow.get("listingId") or "")
                        cats = classify_lease_from_bulk(brow)
                        if should_ingest_lease_after_bulk(cats):
                            keep_set.add(lid)
                    triage_keepers = [c for c in candidate_ids if c in keep_set]
                    skipped_by_triage = len(candidate_ids) - len(triage_keepers)
                    logger.info(
                        "loopnet lease bulk triage: kept %s of %s "
                        "(skipped %s non-MF/non-mixed)",
                        len(triage_keepers), len(candidate_ids), skipped_by_triage,
                    )
                else:
                    triage_keepers = candidate_ids

                for lid in triage_keepers:
                    row, containing_polygons = unified[lid]
                    coords = row.get("coordinations") or [[None, None]]
                    lng, lat = coords[0][0], coords[0][1]

                    try:
                        lease = await fetch_lease_details(guard, lid)
                    except BudgetExhausted as exc:
                        errors.append(f"lease {lid}: {exc}")
                        break
                    if not lease:
                        continue

                    mapped = map_lease_to_scraped_listing(
                        lease, listing_id=lid, lat=lat, lng=lng
                    )
                    mapped["polygon_tags"] = [p["name"] for p in containing_polygons]
                    try:
                        await _upsert_loopnet_listing(
                            mapped, session=session, ingest_job_id=ingest_job_id,
                        )
                        await session.commit()
                        total_new += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("loopnet_lease upsert failed for %s", lid)
                        errors.append(f"upsert {lid}: {exc}")
                        await session.rollback()
                    for p in containing_polygons:
                        if p["name"] in per_polygon:
                            per_polygon[p["name"]]["new"] += 1

            job = await session.get(IngestJob, ingest_job_id)
            if job is not None:
                job.records_fetched = total_new
                job.records_new = total_new
                job.status = "completed" if not errors else "partial"
                job.completed_at = datetime.now(UTC)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "new_lease_listings": total_new,
        "per_polygon": per_polygon,
        "errors": errors,
    }


async def _existing_lease_ids(session, candidate_ids: list[str]) -> set[str]:
    if not candidate_ids:
        return set()
    stmt = select(ScrapedListing.source_id).where(
        ScrapedListing.source == "loopnet_lease",
        ScrapedListing.source_id.in_(candidate_ids),
    )
    result = await session.execute(stmt)
    return {row[0] for row in result}


async def _loopnet_monthly_refresh() -> dict[str, Any]:
    if settings.loopnet_experiment_enabled:
        end_date = _experiment_end_date()
        today = datetime.now(UTC).date()
        if end_date is None or today <= end_date:
            return {"skipped": "experiment active — daily task covers refresh"}

    refreshed = 0
    errors: list[str] = []

    async with _task_session() as session:
        stmt = (
            select(ScrapedListing)
            .where(ScrapedListing.source == "loopnet")
            # Prioritize listings attached to an active opportunity first
            .order_by(
                ScrapedListing.linked_project_id.is_(None),
                ScrapedListing.last_seen_at.asc(),
            )
        )
        result = await session.execute(stmt)
        listings: list[ScrapedListing] = list(result.scalars())

        async with BudgetGuard(session) as guard:
            for listing in listings:
                if guard.remaining <= 0:
                    break
                try:
                    sale = await fetch_sale_details(guard, listing.source_id)
                except BudgetExhausted as exc:
                    errors.append(str(exc))
                    break
                if not sale:
                    continue
                # Lightweight: update raw_json + updated_at_source without re-running dedup
                listing.updated_at_source = _parse_update_ts(sale.get("lastUpdated"))
                listing.last_seen_at = datetime.now(UTC)
                refreshed += 1

        await session.commit()

    return {"refreshed": refreshed, "errors": errors}
