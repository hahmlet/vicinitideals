"""Central parcel enrichment pipeline.

Resolves an address (and optional APN) to a fully-populated Parcel row by
routing to the appropriate county/city GIS scraper, normalising the result,
and upserting it into the database.

Usage
-----
>>> parcel = await enrich_parcel(session, address="123 Main St, Gresham OR 97030")

The function never raises — on any lookup failure it logs a warning and returns
None so callers can fall back gracefully.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.models.parcel import Parcel
from app.reconciliation.matcher import normalize_apn
from app.schemas.parcel import (
    ClackamasParcelResult,
    OregonCityParcelResult,
    PortlandParcelResult,
)
from app.utils.gis import detect_jurisdiction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enrich_parcel(
    session: Any,
    *,
    address: str | None,
    apn: str | None = None,
) -> Parcel | None:
    """Look up parcel data from the appropriate county GIS and upsert to DB.

    Returns the upserted Parcel on success, None if lookup fails or no
    address/APN is available.
    """
    if not address and not apn:
        return None

    jurisdiction = detect_jurisdiction(address or "", owner_city=None)
    record: dict[str, Any] | None = None

    try:
        if jurisdiction == "gresham":
            record = await _enrich_gresham(address=address, apn=apn)
        elif jurisdiction in ("clackamas", "lake_oswego", "oregon_city"):
            if jurisdiction == "oregon_city":
                record = await _enrich_oregoncity(address or "")
            else:
                record = await _enrich_clackamas(address or "")
        elif jurisdiction == "portland":
            record = await _enrich_portland(address or "")
        else:
            # Unknown / statewide — create a minimal stub from what we know
            record = _stub_record(apn=apn, address=address)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Parcel enrichment failed for %r (jurisdiction=%s): %s", address, jurisdiction, exc)
        record = _stub_record(apn=apn, address=address)

    if not record or not record.get("apn"):
        # Can't upsert without an APN
        if apn:
            record = _stub_record(apn=apn, address=address)
        else:
            return None

    return await _upsert_parcel(session, record)


# ---------------------------------------------------------------------------
# Per-scraper helpers
# ---------------------------------------------------------------------------


async def _enrich_gresham(*, address: str | None, apn: str | None) -> dict[str, Any] | None:
    from app.scrapers.arcgis import ArcGISLookupError, lookup_gresham_parcels

    results = await lookup_gresham_parcels(apn=apn, address=address)
    if not results:
        return None
    # lookup_gresham_parcels returns a list of GreshamLookupResult
    for result in results:
        parcels = getattr(result, "parcels", [])
        if parcels:
            return _normalize_gresham(parcels[0])
    return None


async def _enrich_clackamas(address: str) -> dict[str, Any] | None:
    from app.scrapers.clackamas import ClackamasLookupError, lookup_clackamas_parcel

    result = await lookup_clackamas_parcel(address)
    if result.match_status != "single_match":
        return None
    return _normalize_clackamas(result)


async def _enrich_oregoncity(address: str) -> dict[str, Any] | None:
    from app.scrapers.oregoncity import OregonCityLookupError, lookup_oregoncity_parcel

    result = await lookup_oregoncity_parcel(address)
    if result.match_status != "single_match":
        return None
    return _normalize_oregoncity(result)


async def _enrich_portland(address: str) -> dict[str, Any] | None:
    from app.scrapers.portlandmaps import PortlandMapsLookupError, lookup_portland_parcel

    result = await lookup_portland_parcel(address)
    if result.match_status not in ("single_match",):
        return None
    return _normalize_portland(result)


# ---------------------------------------------------------------------------
# Normalizers — convert each scraper's result type to the common Parcel dict
# ---------------------------------------------------------------------------


def _normalize_gresham(parcel: Any) -> dict[str, Any]:
    """Convert a GreshamParcelMatch dataclass to the Parcel field dict."""
    data = parcel.__dict__ if hasattr(parcel, "__dict__") else {}
    owner_parts = [data.get("owner_street"), data.get("owner_city"), data.get("owner_state"), data.get("owner_zip")]
    owner_mailing = ", ".join(
        str(p).strip() for p in owner_parts if p not in (None, "") and str(p).strip()
    ) or None
    return {
        "apn": data.get("rno"),
        "state_id": data.get("state_id"),
        "address_normalized": data.get("site_address"),
        "address_raw": data.get("site_address"),
        "owner_name": data.get("owner_name"),
        "owner_mailing_address": owner_mailing,
        "owner_street": data.get("owner_street"),
        "owner_city": data.get("owner_city"),
        "owner_state": data.get("owner_state"),
        "owner_zip": data.get("owner_zip"),
        "lot_sqft": data.get("sqft"),
        "gis_acres": data.get("gis_acres"),
        "zoning_code": data.get("zone"),
        "zoning_description": data.get("zone"),
        "current_use": data.get("land_use"),
        "assessed_value_land": data.get("land_value"),
        "assessed_value_improvements": data.get("building_value"),
        "total_assessed_value": data.get("total_value"),
        "tax_code": data.get("tax_code"),
        "legal_description": data.get("legal_description"),
        "year_built": data.get("year_built"),
        "building_sqft": data.get("building_sqft"),
        "geometry": data.get("geometry"),
        # Routing metadata — Gresham is always Multnomah County
        "county": "Multnomah",
        "jurisdiction": "gresham",
    }


def _normalize_clackamas(result: ClackamasParcelResult) -> dict[str, Any]:
    """Clackamas Jericho API result → Parcel field dict.

    The Jericho API does not return owner info, assessed values, or geometry —
    those fields are left None.  The APN is the parcel_number field.
    """
    return {
        "apn": result.parcel_number,
        "address_normalized": result.primary_address,
        "address_raw": result.primary_address,
        "zoning_code": result.zoning_value,
        "zoning_description": result.zoning_label,
        "current_use": result.landclass,
        # Routing metadata
        "county": "Clackamas",
        "jurisdiction": (result.jurisdiction or "clackamas").lower(),
        # Clackamas does not provide these:
        "owner_name": None,
        "lot_sqft": None,
        "gis_acres": None,
        "assessed_value_land": None,
        "assessed_value_improvements": None,
        "total_assessed_value": None,
        "year_built": None,
        "building_sqft": None,
        "geometry": None,
    }


def _normalize_oregoncity(result: OregonCityParcelResult) -> dict[str, Any]:
    return {
        "apn": result.apn,
        "address_normalized": result.situs_address,
        "address_raw": result.situs_address,
        "zoning_code": result.zoning_code,
        "zoning_description": result.comp_plan,
        "gis_acres": result.gis_acres,
        "year_built": result.year_built,
        "building_sqft": result.living_area_sqft,
        "total_assessed_value": result.total_assessed_value,
        # Routing metadata — Oregon City is in Clackamas County
        "county": "Clackamas",
        "jurisdiction": "oregon_city",
        # Oregon City does not provide these:
        "owner_name": None,
        "lot_sqft": None,
        "assessed_value_land": None,
        "assessed_value_improvements": None,
        "geometry": None,
    }


def _normalize_portland(result: PortlandParcelResult) -> dict[str, Any]:
    ids = result.parcel_ids
    mail = result.mailing_address
    lot = result.lot_metrics
    val = result.valuation
    zon = result.zoning
    bld = result.building_details

    owner_parts = [
        mail.street if mail else None,
        mail.city if mail else None,
        mail.state if mail else None,
        mail.zip_code if mail else None,
    ]
    owner_mailing = ", ".join(
        str(p).strip() for p in owner_parts if p not in (None, "") and str(p).strip()
    ) or None

    return {
        "apn": ids.county_property_id if ids else None,
        "state_id": ids.state_id if ids else None,
        "address_normalized": result.address_match,
        "address_raw": result.address_match,
        "owner_name": result.owner,
        "owner_mailing_address": owner_mailing,
        "owner_street": mail.street if mail else None,
        "owner_city": mail.city if mail else None,
        "owner_state": mail.state if mail else None,
        "owner_zip": mail.zip_code if mail else None,
        "legal_description": result.legal_description,
        "lot_sqft": lot.lot_sqft if lot else None,
        "gis_acres": lot.acreage if lot else None,
        "zoning_code": zon.code if zon else None,
        "zoning_description": zon.description if zon else None,
        "assessed_value_land": val.land if val else None,
        "assessed_value_improvements": val.improvements if val else None,
        "total_assessed_value": val.total if val else None,
        "year_built": bld.year_built if bld else None,
        "building_sqft": bld.sqft if bld else None,
        "geometry": None,  # Portland scraper does not return parcel geometry
        # Routing metadata — Portland is Multnomah County, Portland jurisdiction
        "county": "Multnomah",
        "jurisdiction": "portland",
    }


def _stub_record(*, apn: str | None, address: str | None) -> dict[str, Any] | None:
    if not apn:
        return None
    return {
        "apn": apn,
        "address_normalized": address,
        "address_raw": address,
    }


# ---------------------------------------------------------------------------
# DB upsert (shared with parcels router via import)
# ---------------------------------------------------------------------------


async def _upsert_parcel(session: Any, parcel_data: dict[str, Any]) -> Parcel:
    """Insert or update a Parcel row by APN, then re-classify priority bucket."""
    from app.utils.priority import classify

    parcel = (
        await session.execute(select(Parcel).where(Parcel.apn == parcel_data["apn"]))
    ).scalar_one_or_none()

    if parcel is None:
        parcel = Parcel(apn=parcel_data["apn"])
        session.add(parcel)

    for field, value in parcel_data.items():
        if value is not None:  # don't overwrite existing data with None from partial scrapers
            setattr(parcel, field, value)

    parcel.apn_normalized = normalize_apn(parcel.apn)
    parcel.scraped_at = datetime.now(UTC)

    # Recompute priority bucket whenever parcel data changes
    bucket = classify(
        zoning_code=parcel.zoning_code,
        zoning_description=parcel.zoning_description,
        county=parcel.county,
        jurisdiction=parcel.jurisdiction,
        current_use=parcel.current_use,
        property_type=None,
    )
    parcel.priority_bucket = bucket.value

    await session.flush()
    await session.refresh(parcel)
    return parcel


__all__ = ["enrich_parcel"]
