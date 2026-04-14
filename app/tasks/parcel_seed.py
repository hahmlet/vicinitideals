"""Parcel seeding, bulk classification, and background enrichment tasks.

Four responsibilities:
1. seed_parcels_from_rlis            — reads the cached Metro RLIS taxlots
   GeoJSON and bulk-upserts Parcel records with polygon geometry + assessed
   values for ~430k Multnomah + Clackamas parcels.
2. seed_parcels_from_address_points  — reads the cached Oregon Address Points
   GeoJSON and bulk-inserts Parcel stubs for any APN not yet in the DB.
   NOTE: PARCEL_ID is 0% populated by Multnomah/Clackamas 911 agencies, so
   this source is useful only for address enrichment on existing records.
3. classify_unclassified_parcels     — classifies parcels that have
   zoning/county data but no priority_bucket yet.
4. enrich_prime_target_parcels       — Celery beat task that drip-enriches
   Prime and Target parcels via the county GIS scrapers, rate-limited so we
   don't hammer external APIs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from celery.utils.log import get_task_logger
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import AsyncSessionLocal
from app.models.parcel import Parcel
from app.tasks.celery_app import celery_app
from app.utils.priority import PriorityBucket, classify

logger = get_task_logger(__name__)

# Path to cached GeoJSON files (written by cache_layers.py)
_CACHE_ROOT = Path(__file__).resolve().parents[2] / "data" / "gis_cache"
ADDRESS_POINTS_PATH = _CACHE_ROOT / "oregon" / "address_points_or.geojson"
RLIS_TAXLOTS_PATH = _CACHE_ROOT / "oregon" / "tax_lots_metro_rlis.geojson"

# RLIS county code → full name
_RLIS_COUNTY: dict[str, str] = {
    "M": "Multnomah",
    "C": "Clackamas",
    "W": "Washington",
}

# Enrichment queue settings
ENRICH_BATCH_SIZE = 500         # parcels per beat tick
ENRICH_STALE_DAYS = 90          # re-enrich if scraped_at older than this


# ---------------------------------------------------------------------------
# Celery task wrappers
# ---------------------------------------------------------------------------


@celery_app.task(name="app.tasks.parcel_seed.seed_rlis_task", queue="default")
def seed_rlis_task() -> dict[str, int]:
    """Celery task: upsert Parcel records from the cached Metro RLIS taxlots."""
    return asyncio.get_event_loop().run_until_complete(_seed_parcels_from_rlis())


@celery_app.task(name="app.tasks.parcel_seed.seed_parcels_task", queue="default")
def seed_parcels_task() -> dict[str, int]:
    """Celery task: seed Parcel stubs from the cached Oregon Address Points."""
    return asyncio.get_event_loop().run_until_complete(_seed_parcels())


@celery_app.task(name="app.tasks.parcel_seed.classify_parcels_task", queue="default")
def classify_parcels_task() -> int:
    """Celery task: classify any parcels that have data but no bucket yet."""
    return asyncio.get_event_loop().run_until_complete(_classify_unclassified())


@celery_app.task(name="app.tasks.parcel_seed.enrich_prime_target_parcels", queue="default")
def enrich_prime_target_parcels() -> int:
    """Celery beat task: drip-enrich Prime/Target parcels from county GIS."""
    return asyncio.get_event_loop().run_until_complete(_enrich_batch())


@celery_app.task(name="app.tasks.parcel_seed.rlis_quarterly_refresh_task", queue="default")
def rlis_quarterly_refresh_task() -> dict[str, Any]:
    """
    Quarterly RLIS DB integration task — dispatched by rlis_delta.py after the
    cache is refreshed.

    Steps:
      1. Read rlis_delta_changes.json sidecar for DELETED TLIDs
      2. Purge deleted parcels from DB (skip any with project associations)
      3. Re-seed all parcels from the refreshed taxlot GeoJSON (upsert)
      4. Classify any newly-seeded parcels with no priority_bucket
    """
    return asyncio.get_event_loop().run_until_complete(_rlis_quarterly_refresh())


# ---------------------------------------------------------------------------
# Core async implementations
# ---------------------------------------------------------------------------


async def _rlis_quarterly_refresh() -> dict[str, Any]:
    """Coordinate the quarterly RLIS DB integration pipeline."""
    sidecar_path = _CACHE_ROOT / "oregon" / "rlis_delta_changes.json"

    deleted_tlids: list[str] = []
    sidecar_meta: dict[str, Any] = {}
    if sidecar_path.exists():
        try:
            sidecar_meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
            deleted_tlids = sidecar_meta.get("deleted_tlids", [])
            logger.info(
                "Sidecar loaded: %d deleted TLIDs, added_count=%s, applied_at=%s",
                len(deleted_tlids),
                sidecar_meta.get("added_count"),
                sidecar_meta.get("applied_at"),
            )
        except Exception as exc:
            logger.warning("Could not read rlis_delta_changes.json: %s", exc)
    else:
        logger.warning("rlis_delta_changes.json not found at %s — skipping purge step", sidecar_path)

    # Step 1: purge deleted parcels
    purged = await _purge_deleted_parcels(deleted_tlids)

    # Step 2: full upsert from refreshed GeoJSON (handles ADDs + CHANGEs)
    seed_result = await _seed_parcels_from_rlis()

    # Step 3: classify any newly-seeded parcels missing a bucket
    classified = await _classify_unclassified()

    result = {
        "purged": purged,
        "seed": seed_result,
        "classified": classified,
        "sidecar_applied_at": sidecar_meta.get("applied_at"),
        "change_stats": sidecar_meta.get("change_stats", {}),
    }
    logger.info("RLIS quarterly refresh complete: %s", result)
    return result


async def _purge_deleted_parcels(deleted_tlids: list[str]) -> int:
    """
    Remove parcels whose TLID appeared as DELETED in taxlot_change.
    Skips parcels with project associations (project_parcels FK) — flags them
    as deleted instead so a human can review.
    Returns count of rows actually deleted.
    """
    if not deleted_tlids:
        return 0

    from app.models.parcel import ProjectParcel

    purged = 0
    # Process in chunks to avoid massive IN clauses
    chunk_size = 500
    async with AsyncSessionLocal() as session:
        for i in range(0, len(deleted_tlids), chunk_size):
            chunk = deleted_tlids[i: i + chunk_size]

            # Find parcels for these APNs that have NO project associations
            subq = (
                select(ProjectParcel.parcel_id)
                .join(Parcel, Parcel.id == ProjectParcel.parcel_id)
                .where(Parcel.apn.in_(chunk))
            )
            stmt = (
                delete(Parcel)
                .where(Parcel.apn.in_(chunk))
                .where(Parcel.id.not_in(subq))
                .returning(Parcel.id)
            )
            result = await session.execute(stmt)
            purged += len(result.fetchall())

            # For parcels with project associations, log a warning — don't delete
            protected = list((await session.execute(
                select(Parcel.apn, Parcel.id)
                .where(Parcel.apn.in_(chunk))
            )).all())
            if protected:
                for apn, pid in protected:
                    logger.warning(
                        "RLIS DELETED taxlot %s (parcel %s) has project associations — not purged",
                        apn, pid,
                    )

        await session.commit()

    logger.info("Purged %d deleted parcels (%d TLIDs had project associations)", purged, len(deleted_tlids) - purged)
    return purged


async def _seed_parcels_from_rlis() -> dict[str, int]:
    """Read tax_lots_metro_rlis.geojson and upsert Parcel records.

    RLIS provides polygon geometry + assessed values + land use for ~430k
    Multnomah + Clackamas taxlots. Uses ON CONFLICT (apn) DO UPDATE so that
    subsequent runs refresh assessor data without clobbering owner/zoning
    fields populated by county enrichment scrapers.
    """
    if not RLIS_TAXLOTS_PATH.exists():
        logger.warning("RLIS taxlots cache not found at %s — run cache_layers.py --only tax_lots_metro_rlis first", RLIS_TAXLOTS_PATH)
        return {"upserted": 0, "skipped": 0, "errors": 0, "missing_cache": 1}

    logger.info("Loading RLIS taxlots from %s", RLIS_TAXLOTS_PATH)
    geojson = json.loads(RLIS_TAXLOTS_PATH.read_text(encoding="utf-8"))
    features = geojson.get("features") or []
    logger.info("Loaded %d RLIS features", len(features))

    upserted = skipped = errors = 0
    batch: list[dict[str, Any]] = []

    async with AsyncSessionLocal() as session:
        for feature in features:
            try:
                props = feature.get("properties") or {}
                apn = _str(props.get("TLID"))
                if not apn:
                    skipped += 1
                    continue

                county_code = _str(props.get("COUNTY")) or ""
                county = _RLIS_COUNTY.get(county_code.upper())

                geometry = feature.get("geometry")

                stub = {
                    "id": uuid4(),
                    "apn": apn,
                    "address_raw": _str(props.get("SITEADDR")),
                    "address_normalized": _str(props.get("SITEADDR")),
                    "county": county,
                    "jurisdiction": _str(props.get("JURIS_CITY", "")).lower() or None,
                    "postal_city": _title(props.get("SITECITY")),
                    "zip_code": _str(props.get("SITEZIP")),
                    "geometry": geometry,
                    # Assessed values
                    "assessed_value_land": _numeric(props.get("LANDVAL")),
                    "assessed_value_improvements": _numeric(props.get("BLDGVAL")),
                    "total_assessed_value": _numeric(props.get("ASSESSVAL")),
                    # Physical attributes
                    "building_sqft": _numeric(props.get("BLDGSQFT")),
                    "gis_acres": _numeric(props.get("GIS_ACRES")),
                    "year_built": int(props["YEARBUILT"]) if props.get("YEARBUILT") else None,
                    "tax_code": _str(props.get("TAXCODE")),
                    # RLIS-specific fields
                    "sale_price": int(props["SALEPRICE"]) if props.get("SALEPRICE") else None,
                    "sale_date": _str(props.get("SALEDATE")),
                    "state_class": _str(props.get("STATECLASS")),
                    "ortaxlot": _str(props.get("ORTAXLOT")),
                    "primary_account_num": _str(props.get("PRIMACCNUM")),
                    "alt_account_num": _str(props.get("ALTACCNUM")),
                    "rlis_land_use": _str(props.get("LANDUSE")),
                    "rlis_taxcode": _str(props.get("TAXCODE")),
                }
                batch.append(stub)

                if len(batch) >= 500:
                    n = await _bulk_upsert_rlis(session, batch)
                    upserted += n
                    skipped += len(batch) - n
                    batch = []

            except Exception as exc:  # noqa: BLE001
                logger.warning("Error processing RLIS feature: %s", exc)
                errors += 1

        if batch:
            n = await _bulk_upsert_rlis(session, batch)
            upserted += n
            skipped += len(batch) - n

        await session.commit()

    logger.info("RLIS seed complete: upserted=%d skipped=%d errors=%d", upserted, skipped, errors)
    return {"upserted": upserted, "skipped": skipped, "errors": errors}


async def _bulk_upsert_rlis(session: Any, stubs: list[dict[str, Any]]) -> int:
    """Upsert RLIS stubs — on conflict update assessor + geometry fields, preserve owner/zoning."""
    update_cols = {
        "address_raw": pg_insert(Parcel).excluded.address_raw,
        "address_normalized": pg_insert(Parcel).excluded.address_normalized,
        "county": pg_insert(Parcel).excluded.county,
        "jurisdiction": pg_insert(Parcel).excluded.jurisdiction,
        "postal_city": pg_insert(Parcel).excluded.postal_city,
        "zip_code": pg_insert(Parcel).excluded.zip_code,
        "geometry": pg_insert(Parcel).excluded.geometry,
        "assessed_value_land": pg_insert(Parcel).excluded.assessed_value_land,
        "assessed_value_improvements": pg_insert(Parcel).excluded.assessed_value_improvements,
        "total_assessed_value": pg_insert(Parcel).excluded.total_assessed_value,
        "building_sqft": pg_insert(Parcel).excluded.building_sqft,
        "gis_acres": pg_insert(Parcel).excluded.gis_acres,
        "year_built": pg_insert(Parcel).excluded.year_built,
        "tax_code": pg_insert(Parcel).excluded.tax_code,
        "sale_price": pg_insert(Parcel).excluded.sale_price,
        "sale_date": pg_insert(Parcel).excluded.sale_date,
        "state_class": pg_insert(Parcel).excluded.state_class,
        "ortaxlot": pg_insert(Parcel).excluded.ortaxlot,
        "primary_account_num": pg_insert(Parcel).excluded.primary_account_num,
        "alt_account_num": pg_insert(Parcel).excluded.alt_account_num,
        "rlis_land_use": pg_insert(Parcel).excluded.rlis_land_use,
        "rlis_taxcode": pg_insert(Parcel).excluded.rlis_taxcode,
    }
    stmt = (
        pg_insert(Parcel)
        .values(stubs)
        .on_conflict_do_update(index_elements=["apn"], set_=update_cols)
        .returning(Parcel.id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return len(result.fetchall())


async def _seed_parcels() -> dict[str, int]:
    """Read address_points_or.geojson and upsert Parcel stubs (no-overwrite)."""
    if not ADDRESS_POINTS_PATH.exists():
        logger.warning("Address points cache not found at %s — run cache_layers.py first", ADDRESS_POINTS_PATH)
        return {"created": 0, "skipped": 0, "errors": 0, "missing_cache": 1}

    logger.info("Loading address points from %s", ADDRESS_POINTS_PATH)
    geojson = json.loads(ADDRESS_POINTS_PATH.read_text(encoding="utf-8"))
    features = geojson.get("features") or []
    logger.info("Loaded %d address point features", len(features))

    created = skipped = errors = 0
    batch: list[dict[str, Any]] = []

    async with AsyncSessionLocal() as session:
        for feature in features:
            try:
                props = feature.get("properties") or {}
                apn = _str(props.get("PARCEL_ID"))
                if not apn:
                    skipped += 1
                    continue

                lat = props.get("Latitude")
                lon = props.get("Longitude")
                post_code = _str(props.get("Post_Code"))
                post_code_ex = _str(props.get("PostCodeEx"))
                zip_code = f"{post_code}-{post_code_ex}" if post_code and post_code_ex else post_code

                stub = {
                    "id": uuid4(),
                    "apn": apn,
                    "address_normalized": _str(props.get("ADDRESS_FULL")),
                    "address_raw": _str(props.get("ADDRESS_FULL")),
                    "county": _county_name(props.get("County")),
                    "jurisdiction": _str(props.get("Inc_Muni", "")).lower() or None,
                    # Coordinates
                    "latitude": float(lat) if lat is not None else None,
                    "longitude": float(lon) if lon is not None else None,
                    # Geometry point stub from coordinates
                    "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]} if lat is not None and lon is not None else None,
                    # Address components
                    "postal_city": _title(props.get("Post_Comm")),
                    "zip_code": zip_code,
                    "unincorporated_community": _title(props.get("Uninc_Comm")),
                    "neighborhood": _title(props.get("Nbrhd_Comm")),
                    "address_unit": _str(props.get("SUBADDRESS_FULL")),
                    "building_id": _str(props.get("BUILDING_ID")),
                    "street_full_name": _str(props.get("STREET_NAME_FULL")),
                    "street_number": int(props["Add_Number"]) if props.get("Add_Number") else None,
                    # Flags
                    "is_residential": _yn_bool(props.get("RESIDENTIAL")),
                    "is_mailable": _yn_bool(props.get("MAIL")),
                    # Metadata
                    "address_stage": _str(props.get("STAGE")),
                    "place_type": _str(props.get("Place_Type")),
                    "landmark_name": _str(props.get("LandmkName")),
                    "address_placement": _str(props.get("Placement")),
                    "elevation_ft": int(props["Elevation"]) if props.get("Elevation") is not None else None,
                    "address_source_updated_at": _epoch_ms(props.get("DateUpdate")),
                    "address_effective_at": _epoch_ms(props.get("Effective")),
                    "address_expires_at": _epoch_ms(props.get("Expire")),
                    "nguid": _str(props.get("NGUID")),
                    "discrepancy_agency_id": _str(props.get("DiscrpAgID")),
                    "esn": _str(props.get("ESN")),
                    "msag_community": _str(props.get("MSAGComm")),
                }
                batch.append(stub)

                if len(batch) >= 500:
                    n = await _bulk_insert_stubs(session, batch)
                    created += n
                    skipped += len(batch) - n
                    batch = []

            except Exception as exc:  # noqa: BLE001
                logger.warning("Error processing feature: %s", exc)
                errors += 1

        if batch:
            n = await _bulk_insert_stubs(session, batch)
            created += n
            skipped += len(batch) - n

        await session.commit()

    logger.info("Seed complete: created=%d skipped=%d errors=%d", created, skipped, errors)
    return {"created": created, "skipped": skipped, "errors": errors}


async def _bulk_insert_stubs(session: Any, stubs: list[dict[str, Any]]) -> int:
    """INSERT stubs ON CONFLICT DO NOTHING — returns count actually inserted."""
    stmt = (
        pg_insert(Parcel)
        .values(stubs)
        .on_conflict_do_nothing(index_elements=["apn"])
        .returning(Parcel.id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return len(result.fetchall())


async def _classify_unclassified() -> int:
    """Classify parcels that have zoning/county data but no bucket."""
    updated = 0
    async with AsyncSessionLocal() as session:
        # Process in batches to avoid loading millions of rows
        offset = 0
        batch_size = 1000
        while True:
            parcels = list((await session.execute(
                select(Parcel)
                .where(Parcel.priority_bucket.is_(None))
                .order_by(Parcel.apn)
                .offset(offset)
                .limit(batch_size)
            )).scalars())

            if not parcels:
                break

            for parcel in parcels:
                bucket = classify(
                    zoning_code=parcel.zoning_code,
                    zoning_description=parcel.zoning_description,
                    county=parcel.county,
                    jurisdiction=parcel.jurisdiction,
                    current_use=parcel.current_use,
                    property_type=None,
                )
                parcel.priority_bucket = bucket.value
                updated += 1

            await session.flush()
            offset += batch_size

        await session.commit()

    logger.info("Classified %d parcels", updated)
    return updated


async def _enrich_batch() -> int:
    """Enrich up to ENRICH_BATCH_SIZE Prime/Target parcels that are stale."""
    from app.scrapers.parcel_enrichment import enrich_parcel

    stale_before = datetime.now(UTC) - timedelta(days=ENRICH_STALE_DAYS)
    enriched = 0

    async with AsyncSessionLocal() as session:
        parcels = list((await session.execute(
            select(Parcel)
            .where(
                Parcel.priority_bucket.in_([PriorityBucket.prime.value, PriorityBucket.target.value]),
                (Parcel.scraped_at.is_(None)) | (Parcel.scraped_at < stale_before),
            )
            .order_by(
                # Prime first, then Target
                Parcel.priority_bucket.asc(),
                Parcel.scraped_at.asc().nullsfirst(),
            )
            .limit(ENRICH_BATCH_SIZE)
        )).scalars())

        for parcel in parcels:
            try:
                address = parcel.address_normalized or parcel.address_raw
                await enrich_parcel(session, address=address, apn=parcel.apn)
                enriched += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Enrichment failed for parcel %s (%s): %s", parcel.apn, parcel.id, exc)

        await session.commit()

    logger.info("Enriched %d parcels in this batch", enriched)
    return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _title(value: Any) -> str | None:
    s = _str(value)
    return s.title() if s else None


def _county_name(value: Any) -> str | None:
    """Strip trailing ' County' suffix so stored value matches routing expectations.

    Oregon Address Points returns 'Multnomah County'; routing logic compares
    against 'multnomah' / 'clackamas'.
    """
    s = _title(value)
    if s and s.lower().endswith(" county"):
        s = s[: -len(" county")]
    return s or None


def _yn_bool(value: Any) -> bool | None:
    """Convert Y/N string to bool, None if absent."""
    if value is None:
        return None
    return str(value).strip().upper() == "Y"


def _numeric(value: Any) -> float | None:
    """Convert a numeric value to float, None if absent or zero."""
    if value is None:
        return None
    try:
        return float(value) or None
    except (TypeError, ValueError):
        return None


def _epoch_ms(value: Any) -> datetime | None:
    """Convert ArcGIS epoch-milliseconds timestamp to UTC datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


__all__ = [
    "seed_rlis_task",
    "seed_parcels_task",
    "classify_parcels_task",
    "enrich_prime_target_parcels",
    "rlis_quarterly_refresh_task",
]
