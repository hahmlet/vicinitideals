"""Listings, brokers, dedup, and Crexi data-intelligence routes.

Extracted from ui.py (Phase 2a). Covers:
  /listings  /ui/listings/*
  /brokers   /ui/brokers/*
  /dedup     /ui/dedup/*
  /ui/listings/{listing_id}/realie-skip
"""
from __future__ import annotations

import html as _html
import io
import json
import uuid as _uuid_mod
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DBSession
from app.models.broker import Broker, Brokerage
from app.models.deal import Deal, Scenario
from app.models.project import Project
from app.models.ingestion import DedupCandidate, DedupStatus, RecordType
from app.models.scraped_listing import ScrapedListing
from app.api.routers.ui_helpers import (
    _as_list,
    _base_ctx,
    _get_address_issues_count,
    _get_counts,
    _get_user,
    templates,
)

router = APIRouter(include_in_schema=False)

# ---------------------------------------------------------------------------
# Address helpers
# ---------------------------------------------------------------------------

def _extract_city(address_normalized: str | None) -> str | None:
    """Extract and title-case the city portion from a normalized address."""
    if not address_normalized:
        return None
    parts = address_normalized.split(",")
    if len(parts) >= 2:
        city_part = parts[1].strip().split()[0] if parts[1].strip() else None
        return city_part.title() if city_part else None
    return None


_STATE_CLASS_LABELS: dict[str, str] = {
    "101": "Single Family", "100": "Residential (Vacant)", "541": "Manufactured Home",
    "551": "Apartment / MF", "550": "Condo / MF",
    "201": "Commercial", "200": "Commercial (Vacant)",
    "401": "Industrial", "400": "Industrial (Vacant)",
    "701": "Farm", "700": "Farm (Vacant)", "301": "Timber", "300": "Timber (Vacant)", "303": "Timber",
    "801": "Exempt", "800": "Exempt (Vacant)", "641": "Utility", "640": "Utility (Vacant)",
    "601": "Mining", "600": "Mining (Vacant)", "000": "Unknown",
}


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def _build_listing_row(listing: ScrapedListing) -> dict:
    prop = getattr(listing, "_property", None)
    broker = listing.broker
    brokerage = broker.brokerage if broker else None

    # Jurisdiction display: prefer parcel-reconciled jurisdiction over city,
    # collapse the literal "unincorporated" / county-name-as-jurisdiction
    # cases into a friendly bucket label.
    _ej = (listing.jurisdiction or listing.city or "").strip()
    _county = (listing.county or "").strip()
    _bucket = _classify_listing_uninc_bucket(_ej.lower(), _county.lower())
    if _bucket == "uninc:Clackamas":
        jurisdiction_label = "Unin. Clackamas"
    elif _bucket == "uninc:Multnomah":
        jurisdiction_label = "Unin. Multnomah"
    elif _bucket == "uninc:other":
        jurisdiction_label = "Unincorporated"
    else:
        jurisdiction_label = _ej.title() if _ej else None

    return {
        "id": str(listing.id),
        "address": listing.address_normalized or listing.address_raw or "Undisclosed",
        "jurisdiction_label": jurisdiction_label,
        "is_new": listing.is_new,
        "source": listing.source,
        "source_label": listing.source.title(),
        "source_url": listing.source_url,
        "source_id": listing.source_id,
        "asking_price": float(listing.asking_price) if listing.asking_price else None,
        "price_per_unit": float(listing.price_per_unit) if listing.price_per_unit else None,
        "units": listing.units,
        "cap_rate": float(listing.cap_rate) if listing.cap_rate else None,
        "proforma_cap_rate": float(listing.proforma_cap_rate) if listing.proforma_cap_rate else None,
        "noi": float(listing.noi) if listing.noi else None,
        "proforma_noi": float(listing.proforma_noi) if listing.proforma_noi else None,
        "building_sqft": float(listing.gba_sqft) if listing.gba_sqft else None,
        "net_rentable_sqft": float(listing.net_rentable_sqft) if listing.net_rentable_sqft else None,
        "lot_sqft": float(listing.lot_sqft) if listing.lot_sqft else None,
        "year_built": listing.year_built,
        "property_type": listing.property_type,
        "status": listing.status,
        "description": listing.description,
        "buildings": listing.buildings,
        "stories": listing.stories,
        "parking_spaces": listing.parking_spaces,
        "class_": listing.class_,
        "zoning": listing.zoning,
        "apn": listing.apn,
        "occupancy_pct": float(listing.occupancy_pct) if listing.occupancy_pct else None,
        "year_renovated": listing.year_renovated,
        "price_per_sqft": float(listing.price_per_sqft) if listing.price_per_sqft else None,
        "broker_co_op": listing.broker_co_op,
        "broker_name": f"{broker.first_name or ''} {broker.last_name or ''}".strip() if broker else None,
        "brokerage_name": brokerage.name if brokerage else None,
        "broker_phone": broker.phone if broker else None,
        "broker_email": broker.email if broker else None,
        "property_id": str(prop.id) if prop else None,
        "first_seen_fmt": listing.first_seen_at.strftime("%b %-d, %Y") if listing.first_seen_at else None,
        "last_updated_fmt": listing.updated_at_source.strftime("%b %-d, %Y") if listing.updated_at_source else None,
        "last_checked_fmt": listing.last_seen_at.strftime("%b %-d, %Y") if listing.last_seen_at else None,
        "updated_highlight": listing.updated_at_source is not None,
        "raw_json": listing.raw_json,
        "archived": listing.archived,
        "linked_opportunity_id": str(listing.id) if listing.org_id else None,
        "linked_opportunity_name": listing.name or None,
        "linked_deal_id": None,  # Resolved separately when needed (avoid N+1 on list page)
        "priority_bucket": listing.priority_bucket,
    }


def _listings_base_stmt(
    q: str,
    source,
    is_new: str,
    property_type=None,
    min_units: str = "",
    max_units: str = "",
    priority_bucket=None,
    cities: list[str] | None = None,
):
    stmt = (
        select(ScrapedListing)
        .options(
            selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
        )
        .order_by(ScrapedListing.last_seen_at.desc())
    )
    if q:
        stmt = stmt.where(or_(
            ScrapedListing.address_normalized.ilike(f"%{q}%"),
            ScrapedListing.address_raw.ilike(f"%{q}%"),
        ))
    sources = _as_list(source)
    if sources:
        stmt = stmt.where(ScrapedListing.source.in_(sources))
    if is_new == "1":
        stmt = stmt.where(ScrapedListing.is_new.is_(True))
    ptypes = _as_list(property_type)
    if ptypes:
        stmt = stmt.where(ScrapedListing.property_type.in_(ptypes))
    if min_units:
        try:
            n = int(min_units)
            if n > 0:
                stmt = stmt.where(ScrapedListing.units >= n)
        except ValueError:
            pass
    if max_units:
        try:
            stmt = stmt.where(ScrapedListing.units <= int(max_units))
        except ValueError:
            pass
    buckets = _as_list(priority_bucket)
    if buckets:
        stmt = stmt.where(ScrapedListing.priority_bucket.in_(buckets))
    if cities is not None:
        stmt = _apply_jurisdiction_filter(stmt, cities)
    return stmt


_LISTING_UNINC_TOKENS = {"uninc:Clackamas", "uninc:Multnomah", "uninc:other"}


def _classify_listing_uninc_bucket(ej_norm: str | None, county_norm: str | None) -> str | None:
    """Classify a listing into uninc:Clackamas / uninc:Multnomah / uninc:other or None.

    ej_norm: lowercased COALESCE(jurisdiction, city) string
    county_norm: lowercased county string

    Returns the bucket token, or None if the listing isn't unincorporated.
    """
    ej = (ej_norm or "").strip()
    cty = (county_norm or "").strip()
    is_unincorp_label = ej.startswith("unincorp")
    is_county_as_jur = ej in {"clackamas", "clackamas county", "multnomah", "multnomah county"}

    if not (is_unincorp_label or is_county_as_jur):
        return None

    # Pick a county hint from either ej or county.
    hints = " ".join([ej, cty])
    if "clackamas" in hints:
        return "uninc:Clackamas"
    if "multnomah" in hints:
        return "uninc:Multnomah"
    return "uninc:other"


def _apply_jurisdiction_filter(stmt, jurisdictions: list[str]):
    """Apply jurisdiction filter — cities and 'uninc:<bucket>' entries.

    Uses COALESCE(jurisdiction, city) so that parcel-reconciled listings
    filter by the authoritative GIS jurisdiction, while unreconciled
    listings fall back to the broker-provided city.

    Three unincorporated buckets are recognized:
      uninc:Clackamas, uninc:Multnomah — explicit unincorporated label or
        the county name standing in as the jurisdiction, with the county
        column matching.
      uninc:other — every other unincorporated row (other counties or
        rows with no county info).
    """
    effective_jurisdiction = func.coalesce(ScrapedListing.jurisdiction, ScrapedListing.city)
    ej_lower = func.lower(effective_jurisdiction)
    county_lower = func.lower(ScrapedListing.county)

    def _county_match(county: str):
        return county_lower.like(f"{county}%")

    def _is_uninc_label():
        return ej_lower.like("unincorp%")

    def _is_county_as_jur(county: str):
        return ej_lower.in_([county, f"{county} county"])

    def _is_clackamas_bucket():
        return or_(
            _is_county_as_jur("clackamas"),
            _is_uninc_label() & _county_match("clackamas"),
        )

    def _is_multnomah_bucket():
        return or_(
            _is_county_as_jur("multnomah"),
            _is_uninc_label() & _county_match("multnomah"),
        )

    def _is_other_uninc_bucket():
        return or_(
            _is_uninc_label() & ~(_county_match("clackamas") | _county_match("multnomah") | county_lower.is_(None)),
            _is_uninc_label() & county_lower.is_(None),
        )

    city_names = []
    selected_uninc: set[str] = set()
    for j in jurisdictions:
        if j in _LISTING_UNINC_TOKENS:
            selected_uninc.add(j)
        elif j.startswith("uninc:"):
            # Legacy uninc:<other-county> tokens — bucket as 'other'.
            selected_uninc.add("uninc:other")
        else:
            city_names.append(j)

    clauses = []
    if city_names:
        clauses.append(ej_lower.in_([c.lower() for c in city_names]))
    if "uninc:Clackamas" in selected_uninc:
        clauses.append(_is_clackamas_bucket())
    if "uninc:Multnomah" in selected_uninc:
        clauses.append(_is_multnomah_bucket())
    if "uninc:other" in selected_uninc:
        clauses.append(_is_other_uninc_bucket())
    if clauses:
        stmt = stmt.where(or_(*clauses))
    else:
        stmt = stmt.where(ScrapedListing.id.is_(None))
    return stmt


async def _get_jurisdictions(session) -> list[dict]:
    """Return sorted list of {value, label, type} for the listings jurisdiction filter.

    Cities are emitted as discrete rows. Anything that classifies as
    unincorporated (literal "unincorporated" jurisdiction, or a county name
    standing in as the jurisdiction, or a row with no jurisdiction but a
    county hint) is rolled up into one of three buckets:

      uninc:Clackamas, uninc:Multnomah, uninc:other

    so the user picks "Unin. Clackamas" without seeing a confusing raw
    "Clackamas" entry alongside actual cities.
    """
    effective_jurisdiction = func.coalesce(ScrapedListing.jurisdiction, ScrapedListing.city)

    rows = (await session.execute(
        select(effective_jurisdiction.label("ej"), ScrapedListing.county, func.count())
        .group_by(effective_jurisdiction, ScrapedListing.county)
    )).all()

    seen_cities: dict[str, tuple[str, int]] = {}
    uninc_totals: dict[str, int] = {"uninc:Clackamas": 0, "uninc:Multnomah": 0, "uninc:other": 0}

    for ej, county, cnt in rows:
        ej_norm = (ej or "").strip().lower()
        county_norm = (county or "").strip().lower()
        bucket = _classify_listing_uninc_bucket(ej_norm, county_norm)
        if bucket is not None:
            uninc_totals[bucket] += cnt
            continue
        if not ej:
            # No jurisdiction *or* city, and not classifiable as unincorp →
            # quietly bucket as 'other' so the row isn't lost.
            uninc_totals["uninc:other"] += cnt
            continue
        # Treat as a city. Dedup case variants (KLAMATH FALLS vs Klamath Falls).
        key = ej_norm
        if key in seen_cities:
            existing_label, existing_cnt = seen_cities[key]
            seen_cities[key] = (existing_label if existing_label[0].isupper() else ej.strip(), existing_cnt + cnt)
        else:
            seen_cities[key] = (ej.strip(), cnt)

    jurisdictions: list[dict] = [
        {"value": label, "label": f"{label} ({cnt})", "type": "city"}
        for _key, (label, cnt) in sorted(seen_cities.items())
    ]
    for bucket_label, bucket_value in [
        ("Unin. Clackamas", "uninc:Clackamas"),
        ("Unin. Multnomah", "uninc:Multnomah"),
        ("Unincorporated (other)", "uninc:other"),
    ]:
        if uninc_totals[bucket_value] > 0:
            jurisdictions.append({
                "value": bucket_value,
                "label": f"{bucket_label} ({uninc_totals[bucket_value]})",
                "type": "unincorporated",
            })
    return jurisdictions


def _split_listings(all_listings: list) -> tuple[list, list, list]:
    """Split into (new, promoted, archived) buckets. Promoted = org_id set."""
    new, promoted, archived = [], [], []
    for l in all_listings:
        if l.org_id:
            promoted.append(_build_listing_row(l))
        elif l.archived:
            archived.append(_build_listing_row(l))
        else:
            new.append(_build_listing_row(l))
    return new, promoted, archived


@router.get("/listings", response_class=HTMLResponse)
async def listings_page(request: Request) -> Response:
    """Listings page merged into Opportunities — redirect permanently."""
    return RedirectResponse(url="/opportunities", status_code=302)


@router.get("/ui/listings/rows", response_class=HTMLResponse)
async def listings_rows(
    request: Request, session: DBSession,
    q: str = Query(default=""),
    source: list[str] = Query(default=[]),
    property_type: list[str] = Query(default=[]),
    min_units: str = Query(default=""),
    max_units: str = Query(default=""),
    priority_bucket: list[str] = Query(default=[]),
    jurisdiction: list[str] = Query(default=[]),
) -> HTMLResponse:
    cities = jurisdiction if jurisdiction else None
    all_listings = list((await session.execute(
        _listings_base_stmt(q, source, "", property_type, min_units, max_units, priority_bucket, cities=cities)
    )).scalars())
    new_listings, promoted, archived = _split_listings(all_listings)
    return templates.TemplateResponse(request, "partials/listings_rows.html", {
        "new_listings": new_listings,
        "promoted_listings": promoted,
        "archived_listings": archived,
        "oob": True,
    })


@router.get("/ui/listings/export.csv")
async def listings_export_csv(
    session: DBSession,
    q: str = Query(default=""),
    source: list[str] = Query(default=[]),
    property_type: list[str] = Query(default=[]),
    min_units: str = Query(default=""),
    max_units: str = Query(default=""),
    priority_bucket: list[str] = Query(default=[]),
    jurisdiction: list[str] = Query(default=[]),
) -> StreamingResponse:
    """Export filtered listings as CSV (address, units, asking price, city, county, property type)."""
    cities = jurisdiction if jurisdiction else None
    all_listings = list((await session.execute(
        _listings_base_stmt(q, source, "", property_type, min_units, max_units, priority_bucket, cities=cities)
    )).scalars())

    import csv as _csv

    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(["Address", "City", "County", "Units", "Asking Price", "Property Type", "Cap Rate", "Year Built", "Source"])
    for l in all_listings:
        addr = l.address_normalized or l.address_raw or "Undisclosed"
        price = float(l.asking_price) if l.asking_price else ""
        cap = f"{float(l.cap_rate):.2f}%" if l.cap_rate else ""
        writer.writerow([addr, l.city or "", l.county or "", l.units or "", price, l.property_type or "", cap, l.year_built or "", l.source or ""])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=listings_export.csv"},
    )


@router.get("/ui/listings/promoted/rows", response_class=HTMLResponse)
async def listings_promoted_rows(
    request: Request, session: DBSession,
    q_promoted: str = Query(default=""),
    promoted_source: str = Query(default=""),
    promoted_property_type: str = Query(default=""),
    promoted_min_units: str = Query(default=""),
    promoted_max_units: str = Query(default=""),
) -> HTMLResponse:
    stmt = (
        select(ScrapedListing)
        .options(
            selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
        )
        .where(ScrapedListing.org_id.isnot(None))
        .order_by(ScrapedListing.last_seen_at.desc())
    )
    if q_promoted:
        stmt = stmt.where(or_(
            ScrapedListing.address_normalized.ilike(f"%{q_promoted}%"),
            ScrapedListing.address_raw.ilike(f"%{q_promoted}%"),
        ))
    if promoted_source:
        stmt = stmt.where(ScrapedListing.source == promoted_source)
    if promoted_property_type:
        stmt = stmt.where(ScrapedListing.property_type == promoted_property_type)
    if promoted_min_units:
        try:
            n = int(promoted_min_units)
            if n > 0:
                stmt = stmt.where(ScrapedListing.units >= n)
        except ValueError:
            pass
    if promoted_max_units:
        try:
            stmt = stmt.where(ScrapedListing.units <= int(promoted_max_units))
        except ValueError:
            pass
    promoted = [_build_listing_row(l) for l in (await session.execute(stmt)).scalars()]
    return templates.TemplateResponse(request, "partials/listings_promoted_rows.html", {
        "promoted_listings": promoted,
    })


@router.get("/ui/listings/{listing_id}/raw", response_class=PlainTextResponse)
async def listing_raw_json(listing_id: UUID, session: DBSession) -> PlainTextResponse:
    listing = await session.get(ScrapedListing, listing_id)
    if listing is None:
        return PlainTextResponse('{"error": "not found"}')
    data = listing.raw_json or {
        "id": str(listing.id),
        "source": listing.source,
        "source_id": listing.source_id,
        "address": listing.address_normalized,
        "asking_price": float(listing.asking_price) if listing.asking_price else None,
        "units": listing.units,
        "year_built": listing.year_built,
        "cap_rate": float(listing.cap_rate) if listing.cap_rate else None,
        "status": listing.status,
        "scraped_at": listing.last_seen_at.isoformat() if listing.last_seen_at else None,
    }
    return PlainTextResponse(json.dumps(data, indent=2, default=str))


@router.get("/ui/listings/{listing_id}/detail", response_class=HTMLResponse)
async def listing_detail(request: Request, listing_id: UUID, session: DBSession) -> HTMLResponse:
    listing = await session.get(
        ScrapedListing, listing_id,
        options=[
            selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
        ]
    )
    if listing is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    l = _build_listing_row(listing)
    # Resolve linked deal — listing IS the opportunity; find deal via Scenario→Project path
    if listing.org_id:
        deal_row = (await session.execute(
            select(Deal.id)
            .join(Scenario, Scenario.deal_id == Deal.id)
            .join(Project, Project.scenario_id == Scenario.id)
            .where(Project.opportunity_id == listing.id)
            .limit(1)
        )).scalar_one_or_none()
        if deal_row:
            l["linked_deal_id"] = str(deal_row)
    return templates.TemplateResponse(request, "partials/listing_detail.html", {"l": l})


@router.post("/ui/listings/{listing_id}/promote", response_class=HTMLResponse)
async def promote_listing(
    request: Request,
    listing_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Manually promote a listing to an Opportunity (set org_id on listing row)."""
    from app.tasks.scraper import _promote_listing as _do_promote, _get_default_org_id  # local import avoids circular

    listing = await session.get(
        ScrapedListing, listing_id,
        options=[selectinload(ScrapedListing.broker).selectinload(Broker.brokerage)]
    )
    if listing is None:
        return HTMLResponse("<span class='text-muted text-small'>Not found</span>")

    if listing.org_id:
        # Already promoted
        l = _build_listing_row(listing)
        return templates.TemplateResponse(request, "partials/listings_promoted_row.html", {"l": l})

    org_id = await _get_default_org_id(session)
    opp = await _do_promote(
        listing, session,
        promotion_source="manual",
        ruleset_id=None,
        org_id=org_id,
    )
    await session.commit()

    if opp is None:
        return HTMLResponse("<span class='text-muted text-small'>Promotion failed</span>")

    await session.refresh(listing)
    l = _build_listing_row(listing)
    return templates.TemplateResponse(request, "partials/listings_promoted_row.html", {"l": l})


@router.post("/ui/listings/{listing_id}/promote-redirect")
async def promote_listing_redirect(
    listing_id: UUID,
    session: DBSession,
) -> RedirectResponse:
    """Promote listing to Opportunity (or reuse existing), then redirect to opportunity detail."""
    from app.tasks.scraper import _promote_listing as _do_promote, _get_default_org_id

    listing = await session.get(ScrapedListing, listing_id)
    if listing is None:
        return RedirectResponse("/listings", status_code=303)

    if listing.org_id:
        return RedirectResponse(f"/opportunities/{listing.id}", status_code=303)

    org_id = await _get_default_org_id(session)
    opp = await _do_promote(listing, session, promotion_source="manual", ruleset_id=None, org_id=org_id)
    await session.commit()

    if opp is None:
        return RedirectResponse("/listings", status_code=303)

    return RedirectResponse(f"/opportunities/{opp.id}", status_code=303)


@router.post("/ui/listings/{listing_id}/revert", response_class=HTMLResponse)
async def revert_listing(
    request: Request,
    listing_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Revert a promoted listing back to unpromoted: archives the Opportunity and clears the link."""
    listing = await session.get(
        ScrapedListing, listing_id,
        options=[selectinload(ScrapedListing.broker).selectinload(Broker.brokerage)]
    )
    if listing is None:
        return HTMLResponse("<span class='text-muted text-small'>Not found</span>")

    if listing.org_id:
        # Demote: clear org_id and set opp_status to archived
        listing.org_id = None
        listing.opp_status = None
        await session.commit()

    # Reload and return as a New row (revert = back to New, not archived)
    listing_reloaded = await session.get(
        ScrapedListing, listing_id,
        options=[selectinload(ScrapedListing.broker).selectinload(Broker.brokerage)]
    )
    if listing_reloaded:
        listing_reloaded.is_new = True
        listing_reloaded.archived = False
        await session.commit()
        await session.refresh(listing_reloaded)
    l = _build_listing_row(listing_reloaded)
    return templates.TemplateResponse(request, "partials/listings_new_row.html", {"l": l})


@router.post("/ui/listings/{listing_id}/archive", response_class=HTMLResponse)
async def archive_listing(
    request: Request,
    listing_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Move a listing from New to Archived."""
    listing = await session.get(
        ScrapedListing, listing_id,
        options=[selectinload(ScrapedListing.broker).selectinload(Broker.brokerage)]
    )
    if listing is None:
        return HTMLResponse("")
    listing.archived = True
    listing.is_new = False
    await session.commit()
    await session.refresh(listing)
    l = _build_listing_row(listing)
    return templates.TemplateResponse(request, "partials/listings_archived_row.html", {"l": l})


@router.post("/ui/listings/{listing_id}/unarchive", response_class=HTMLResponse)
async def unarchive_listing(
    request: Request,
    listing_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Restore an archived listing back to New."""
    listing = await session.get(
        ScrapedListing, listing_id,
        options=[selectinload(ScrapedListing.broker).selectinload(Broker.brokerage)]
    )
    if listing is None:
        return HTMLResponse("")
    listing.archived = False
    listing.is_new = True
    await session.commit()
    await session.refresh(listing)
    l = _build_listing_row(listing)
    return templates.TemplateResponse(request, "partials/listings_new_row.html", {"l": l})


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------

def _build_broker_row(broker: Broker, listing_count: int) -> dict:
    bg = broker.brokerage
    return {
        "id": str(broker.id),
        "full_name": f"{broker.first_name or ''} {broker.last_name or ''}".strip() or "Unknown",
        "brokerage_name": bg.name if bg else None,
        "brokerage_status": (bg.firm_scrape_status if bg else None) or "unknown",
        "email": broker.email,
        "phone": broker.phone,
        "license_number": broker.license_number,
        "license_state": broker.license_state,
        "is_platinum": broker.is_platinum,
        "number_of_assets": broker.number_of_assets,
        "listing_count": listing_count,
    }


def _join_address(*parts: str | None) -> str | None:
    """Join non-empty address parts with separators suitable for inline display."""
    cleaned = [str(p).strip() for p in parts if p]
    if not cleaned:
        return None
    # street, street2, city, state, zip → "street, street2, city, state zip"
    if len(cleaned) >= 4:
        head = ", ".join(cleaned[:-2])
        tail = " ".join(cleaned[-2:])
        return f"{head}, {tail}"
    return ", ".join(cleaned)


def _build_broker_detail(broker: Broker, listings: list[ScrapedListing]) -> dict:
    row = _build_broker_row(broker, len(listings))
    bg = broker.brokerage
    row.update(
        {
            "license_number_locked": bool(broker.license_number_locked),
            "license_personal_address": _join_address(
                broker.license_personal_street,
                broker.license_personal_street2,
                broker.license_personal_city,
                broker.license_personal_state,
                broker.license_personal_zip,
            ),
            "license_type": broker.license_type,
            "license_status": broker.license_status or "unknown",
            "oregon_last_pulled_at": broker.oregon_last_pulled_at.isoformat()
            if broker.oregon_last_pulled_at else None,
            "oregon_lookup_status": broker.oregon_lookup_status,
            "oregon_failure_count": int(broker.oregon_failure_count or 0),
            "oregon_detail_url": broker.oregon_detail_url,
            "brokerage_id": str(bg.id) if bg else None,
            "firm_scrape_status": (bg.firm_scrape_status if bg else None) or "unknown",
            "firm_scrape_domain": bg.firm_scrape_domain if bg else None,
            "oregon_company_name": bg.oregon_company_name if bg else None,
            "oregon_company_address": _join_address(
                bg.oregon_company_street,
                bg.oregon_company_street2,
                bg.oregon_company_city,
                bg.oregon_company_state,
                bg.oregon_company_zip,
            ) if bg else None,
            "disciplinary_actions": [
                {
                    "case_number": d.case_number,
                    "order_signed_date": d.order_signed_date.isoformat()
                    if d.order_signed_date else None,
                    "resolution": d.resolution,
                    "found_issues": d.found_issues,
                }
                for d in (broker.disciplinary_actions or [])
            ],
        }
    )
    row["listings"] = [
        {
            "address": l.address_normalized or l.address_raw or "Unknown",
            "source": l.source,
            "asking_price": float(l.asking_price) if l.asking_price else None,
        }
        for l in listings
    ]
    return row


def _broker_stmt(q: str = "", company: str = "", listings_op: str = "", listings_val: str = ""):
    stmt = (
        select(Broker)
        .options(selectinload(Broker.brokerage), selectinload(Broker.scraped_listings))
        .order_by(Broker.last_name, Broker.first_name)
    )
    needs_brokerage_join = bool(q or company)
    if needs_brokerage_join:
        stmt = stmt.outerjoin(Broker.brokerage)
    if q:
        stmt = stmt.where(or_(
            Broker.first_name.ilike(f"%{q}%"),
            Broker.last_name.ilike(f"%{q}%"),
            (Broker.first_name + " " + Broker.last_name).ilike(f"%{q}%"),
            Brokerage.name.ilike(f"%{q}%"),
        ))
    if company:
        stmt = stmt.where(Brokerage.name.ilike(f"%{company}%"))
    return stmt


def _apply_listings_filter(brokers_list: list, listings_op: str, listings_val: str) -> list:
    if not listings_op or not listings_val:
        return brokers_list
    try:
        val = int(listings_val)
    except (ValueError, TypeError):
        return brokers_list
    if listings_op == "gte":
        return [b for b in brokers_list if len(b.scraped_listings) >= val]
    if listings_op == "lte":
        return [b for b in brokers_list if len(b.scraped_listings) <= val]
    if listings_op == "eq":
        return [b for b in brokers_list if len(b.scraped_listings) == val]
    return brokers_list


@router.get("/brokers", response_class=HTMLResponse)
async def brokers_page(
    request: Request, session: DBSession,
    q: str = Query(default=""),
    company: str = Query(default=""),
    listings_op: str = Query(default=""),
    listings_val: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    stmt = _broker_stmt(q, company, listings_op, listings_val)
    brokers_list = list((await session.execute(stmt)).scalars().unique())
    brokers_list = _apply_listings_filter(brokers_list, listings_op, listings_val)
    total = int((await session.execute(select(func.count()).select_from(Broker))).scalar_one())
    brokers_data = [_build_broker_row(b, len(b.scraped_listings)) for b in brokers_list]
    return templates.TemplateResponse(request, "brokers.html", {
        "brokers": brokers_data, "total_count": total,
        "q": q, "company": company, "listings_op": listings_op, "listings_val": listings_val,
        **_base_ctx(user, dedup_count, "brokers", conflicts_count=conflicts_count),
    })


@router.get("/ui/brokers/rows", response_class=HTMLResponse)
async def brokers_rows(
    request: Request, session: DBSession,
    q: str = Query(default=""),
    company: str = Query(default=""),
    listings_op: str = Query(default=""),
    listings_val: str = Query(default=""),
) -> HTMLResponse:
    stmt = _broker_stmt(q, company, listings_op, listings_val)
    brokers_list = list((await session.execute(stmt)).scalars().unique())
    brokers_list = _apply_listings_filter(brokers_list, listings_op, listings_val)
    brokers_data = [_build_broker_row(b, len(b.scraped_listings)) for b in brokers_list]
    return templates.TemplateResponse(request, "partials/brokers_rows.html", {"brokers": brokers_data})


@router.get("/ui/brokers/{broker_id}/detail", response_class=HTMLResponse)
async def broker_detail(request: Request, broker_id: UUID, session: DBSession) -> HTMLResponse:
    broker = await session.get(
        Broker, broker_id,
        options=[
            selectinload(Broker.brokerage),
            selectinload(Broker.scraped_listings),
            selectinload(Broker.disciplinary_actions),
        ],
    )
    if broker is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    b = _build_broker_detail(broker, broker.scraped_listings)
    return templates.TemplateResponse(request, "partials/broker_detail.html", {"b": b})


@router.post("/ui/brokers/{broker_id}/license", response_class=HTMLResponse)
async def broker_license_update(
    request: Request,
    broker_id: UUID,
    session: DBSession,
    license_number: str = Form(default=""),
    license_state: str = Form(default=""),
) -> HTMLResponse:
    """Manually set a broker's license number. Sets license_number_locked=True
    so listing scrapers won't overwrite it. The user does this specifically to
    align the license with the Oregon database; subsequent Oregon enrichment
    runs against this value."""
    broker = await session.get(
        Broker, broker_id,
        options=[
            selectinload(Broker.brokerage),
            selectinload(Broker.scraped_listings),
            selectinload(Broker.disciplinary_actions),
        ],
    )
    if broker is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    cleaned_number = (license_number or "").strip() or None
    cleaned_state = (license_state or "").strip().upper() or None
    broker.license_number = cleaned_number
    broker.license_state = cleaned_state
    broker.license_number_locked = cleaned_number is not None
    await session.commit()
    await session.refresh(broker)
    b = _build_broker_detail(broker, broker.scraped_listings)
    resp = templates.TemplateResponse(request, "partials/broker_detail.html", {"b": b})
    resp.headers["HX-Trigger"] = "brokerSaved"
    return resp


@router.post("/ui/brokers/{broker_id}/oregon-update", response_class=HTMLResponse)
async def broker_oregon_update(
    request: Request, broker_id: UUID, session: DBSession,
) -> HTMLResponse:
    """Queue a one-shot Oregon eLicense enrichment for a single broker. Does
    not affect license_number_locked — manual lock and Oregon enrichment are
    independent (lock blocks listing-source scrapers, not Oregon)."""
    broker = await session.get(
        Broker, broker_id,
        options=[
            selectinload(Broker.brokerage),
            selectinload(Broker.scraped_listings),
            selectinload(Broker.disciplinary_actions),
        ],
    )
    if broker is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    broker.oregon_lookup_status = "pending"
    await session.commit()
    # Local import keeps Celery out of the router import path in unit tests
    # that don't load celery_app.
    from app.tasks.oregon_elicense import enrich_broker_oregon  # noqa: PLC0415

    enrich_broker_oregon.delay(str(broker_id))
    await session.refresh(broker)
    b = _build_broker_detail(broker, broker.scraped_listings)
    return templates.TemplateResponse(request, "partials/broker_detail.html", {"b": b})


@router.get("/ui/brokers/quick-create-form", response_class=HTMLResponse)
async def broker_quick_create_form(request: Request) -> HTMLResponse:
    """Inline form for creating a new broker from the opportunity wizard."""
    return HTMLResponse("""
<div style="margin-top:10px;border:1px solid var(--border);border-radius:6px;padding:14px;background:var(--surface)">
  <div style="font-size:13px;font-weight:600;margin-bottom:10px">New Broker</div>
  <form hx-post="/ui/brokers/quick-create" hx-target="#wizard-broker-select-wrap" hx-swap="outerHTML">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
      <div>
        <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px">First Name *</label>
        <input type="text" name="first_name" required style="width:100%">
      </div>
      <div>
        <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px">Last Name *</label>
        <input type="text" name="last_name" required style="width:100%">
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
      <div>
        <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px">Email</label>
        <input type="email" name="email" style="width:100%">
      </div>
      <div>
        <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px">Brokerage</label>
        <input type="text" name="brokerage_name" placeholder="Firm name" style="width:100%">
      </div>
    </div>
    <div style="display:flex;gap:6px">
      <button type="submit" class="btn btn-sm btn-primary">Create</button>
      <button type="button" class="btn btn-sm btn-ghost"
              onclick="document.getElementById('broker-quick-create-modal').innerHTML=''">Cancel</button>
    </div>
  </form>
</div>
""")


@router.post("/ui/brokers/quick-create", response_class=HTMLResponse)
async def broker_quick_create(
    request: Request,
    session: DBSession,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(default=""),
    brokerage_name: str = Form(default=""),
) -> HTMLResponse:
    """Create a broker inline from the opportunity wizard; returns OOB swap updating the select."""
    brokerage_id = None
    if brokerage_name.strip():
        existing_brkg = (await session.execute(
            select(Brokerage).where(func.lower(Brokerage.name) == brokerage_name.strip().lower())
        )).scalar_one_or_none()
        if existing_brkg:
            brokerage_id = existing_brkg.id
        else:
            new_brkg = Brokerage(name=brokerage_name.strip())
            session.add(new_brkg)
            await session.flush()
            brokerage_id = new_brkg.id

    broker = Broker(
        first_name=first_name.strip() or None,
        last_name=last_name.strip() or None,
        email=email.strip() or None,
        brokerage_id=brokerage_id,
    )
    session.add(broker)
    await session.commit()
    await session.refresh(broker)

    rows = (await session.execute(
        select(Broker)
        .options(selectinload(Broker.brokerage))
        .order_by(Broker.last_name, Broker.first_name)
    )).scalars().unique().all()

    opts = ['<option value="">— None —</option>']
    for b in rows:
        full = f"{b.last_name or ''}, {b.first_name or ''}".strip(", ").strip() or "Unknown"
        firm = b.brokerage.name if b.brokerage else None
        label = _html.escape(f"{full} · {firm}" if firm else full)
        sel = " selected" if b.id == broker.id else ""
        opts.append(f'<option value="{b.id}"{sel}>{label}</option>')

    new_btn = ('<button type="button" class="btn btn-sm btn-secondary"'
               ' hx-get="/ui/brokers/quick-create-form"'
               ' hx-target="#broker-quick-create-modal"'
               ' hx-swap="innerHTML">+ New</button>')

    html = (
        '<div id="wizard-broker-select-wrap" style="display:flex;gap:6px;align-items:center">'
        f'<select name="broker_id" style="flex:1">{"".join(opts)}</select>'
        f'{new_btn}'
        '</div>'
        '<div id="broker-quick-create-modal" hx-swap-oob="innerHTML"></div>'
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Data Cleanup (Dedup + Conflict Resolution) helpers
# ---------------------------------------------------------------------------

# Fields shown in the side-by-side listing comparison.
# Keys are ScrapedListing ORM attribute names (not column names).
_LISTING_COMPARE_FIELDS: list[tuple[str, str]] = [
    ("address_raw",        "Address"),
    ("zip_code",           "ZIP Code"),
    ("asking_price",       "Asking Price"),
    ("units",              "Units"),
    ("gba_sqft",           "Bldg SqFt"),
    ("lot_sqft",           "Lot SqFt"),
    ("year_built",         "Year Built"),
    ("year_renovated",     "Year Renovated"),
    ("cap_rate",           "Cap Rate"),
    ("noi",                "NOI"),
    ("proforma_cap_rate",  "Cap Rate (Pro Forma)"),
    ("proforma_noi",       "NOI (Pro Forma)"),
    ("property_type",      "Property Type"),
    ("zoning",             "Zoning"),
    ("apn",                "APN"),
    ("occupancy_pct",      "Occupancy %"),
    ("price_per_unit",     "Price/Unit"),
    ("price_per_sqft",     "Price/SqFt"),
    ("class_",             "Class"),
    ("stories",            "Stories"),
    ("buildings",          "Buildings"),
    ("status",             "Listing Status"),
    ("source",             "Source"),
]

_ALLOWED_OVERRIDE_FIELDS: frozenset[str] = frozenset(f for f, _ in _LISTING_COMPARE_FIELDS)


def _fmt_cmp(val: Any) -> str:
    """Format a field value for the comparison table."""
    if val is None:
        return "—"
    if isinstance(val, Decimal):
        f = float(val)
        if f >= 10_000:
            return f"${f:,.0f}"
        if f >= 1:
            return f"{f:,.2f}"
        return f"{f:.4f}"
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    return str(val)


def _build_listing_compare(
    a: ScrapedListing, b: ScrapedListing
) -> dict[str, list[dict[str, str]]]:
    conflicts: list[dict[str, str]] = []
    matches:   list[dict[str, str]] = []
    for field, label in _LISTING_COMPARE_FIELDS:
        val_a = getattr(a, field, None)
        val_b = getattr(b, field, None)
        fmt_a = _fmt_cmp(val_a)
        fmt_b = _fmt_cmp(val_b)
        entry = {"field": field, "label": label, "val_a": fmt_a, "val_b": fmt_b}
        if fmt_a != fmt_b and not (fmt_a == "—" and fmt_b == "—"):
            conflicts.append(entry)
        else:
            matches.append(entry)
    return {"conflicts": conflicts, "matches": matches}


def _record_type_str(rt: Any) -> str:
    return str(getattr(rt, "value", rt))


async def _load_listings_for_candidates(
    candidates: list[DedupCandidate], session: AsyncSession
) -> dict[_uuid_mod.UUID, ScrapedListing]:
    ids: set[_uuid_mod.UUID] = set()
    for c in candidates:
        if _record_type_str(c.record_a_type) == RecordType.listing.value:
            ids.add(c.record_a_id)
        if _record_type_str(c.record_b_type) == RecordType.listing.value:
            ids.add(c.record_b_id)
    if not ids:
        return {}
    rows = (await session.execute(
        select(ScrapedListing).where(ScrapedListing.id.in_(ids))
    )).scalars()
    return {l.id: l for l in rows}


def _candidate_row(
    c: DedupCandidate,
    listings_by_id: dict[_uuid_mod.UUID, ScrapedListing],
) -> dict[str, Any]:
    def record_label(rt: str, rid: _uuid_mod.UUID) -> tuple[str, str]:
        if rt == RecordType.listing.value:
            l = listings_by_id.get(rid)
            if l:
                addr = l.address_raw or l.full_address or "Unknown address"
                return addr, l.source.title()
        return f"{rt} …{str(rid)[-6:]}", rt.title()

    a_type = _record_type_str(c.record_a_type)
    b_type = _record_type_str(c.record_b_type)
    addr_a, src_a = record_label(a_type, c.record_a_id)
    addr_b, src_b = record_label(b_type, c.record_b_id)
    score = c.confidence_score
    tier = "high" if score >= 0.85 else "mid" if score >= 0.60 else "low"
    return {
        "id": str(c.id),
        "confidence": score,
        "tier": tier,
        "conflict_type": f"{a_type.title()} × {b_type.title()}",
        "record_a_address": addr_a,
        "record_a_source": src_a,
        "record_b_address": addr_b,
        "record_b_source": src_b,
        "match_signals": c.match_signals or {},
        "status": _record_type_str(c.status),
        "resolved_at": c.resolved_at,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Data Cleanup (Dedup) + Realie-skip
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Data Cleanup
# ---------------------------------------------------------------------------

@router.get("/dedup", response_class=HTMLResponse)
async def dedup_page(
    request: Request, session: DBSession,
    tab: str = Query(default="pending"),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count, conflicts_count = await _get_counts(session)
    address_issues_count = await _get_address_issues_count(session)

    address_issues: list[ScrapedListing] = []
    candidates: list[Any] = []

    if tab == "address_issues":
        ai_result = await session.execute(
            select(ScrapedListing)
            .where(
                ScrapedListing.realie_skip.is_(True),
                ScrapedListing.realie_enriched_at.is_(None),
                ScrapedListing.apn.is_(None),
            )
            .order_by(ScrapedListing.city.asc(), ScrapedListing.street.asc())
        )
        address_issues = list(ai_result.scalars())
    elif tab == "resolved":
        result = await session.execute(
            select(DedupCandidate)
            .where(DedupCandidate.status != DedupStatus.pending)
            .order_by(DedupCandidate.resolved_at.desc())
            .limit(200)
        )
        candidates = list(result.scalars())
    else:
        result = await session.execute(
            select(DedupCandidate)
            .where(DedupCandidate.status == DedupStatus.pending)
            .order_by(DedupCandidate.confidence_score.desc())
        )
        candidates = list(result.scalars())

    listings_map = await _load_listings_for_candidates(candidates, session)
    rows = [_candidate_row(c, listings_map) for c in candidates]

    return templates.TemplateResponse(request, "dedup.html", {
        "request": request,
        "tab": tab,
        "candidates": rows,
        "address_issues": address_issues,
        **_base_ctx(user, dedup_count, "dedup", address_issues_count, conflicts_count=conflicts_count),
    })


@router.get("/ui/dedup/{candidate_id}/compare", response_class=HTMLResponse)
async def dedup_compare(
    request: Request, candidate_id: UUID, session: DBSession,
) -> HTMLResponse:
    candidate = await session.get(DedupCandidate, candidate_id)
    if candidate is None:
        return HTMLResponse("<div class='text-muted text-small'>Candidate not found.</div>")

    a_type = _record_type_str(candidate.record_a_type)
    b_type = _record_type_str(candidate.record_b_type)
    compare: dict[str, Any] = {"conflicts": [], "matches": []}
    record_a: ScrapedListing | None = None
    record_b: ScrapedListing | None = None

    if a_type == RecordType.listing.value and b_type == RecordType.listing.value:
        record_a = await session.get(ScrapedListing, candidate.record_a_id)
        record_b = await session.get(ScrapedListing, candidate.record_b_id)
        if record_a and record_b:
            compare = _build_listing_compare(record_a, record_b)

    src_a = (record_a.source.title() if record_a else a_type.title())
    src_b = (record_b.source.title() if record_b else b_type.title())
    addr_a = (record_a.address_raw or record_a.full_address or "—") if record_a else "—"
    addr_b = (record_b.address_raw or record_b.full_address or "—") if record_b else "—"
    url_a = getattr(record_a, "source_url", None) if record_a else None
    url_b = getattr(record_b, "source_url", None) if record_b else None

    return templates.TemplateResponse(request, "partials/dedup_compare.html", {
        "request": request,
        "candidate_id": str(candidate_id),
        "src_a": src_a,
        "src_b": src_b,
        "addr_a": addr_a,
        "addr_b": addr_b,
        "url_a": url_a,
        "url_b": url_b,
        "conflicts": compare["conflicts"],
        "matches": compare["matches"],
    })


@router.post("/ui/dedup/{candidate_id}/keep-separate", response_class=HTMLResponse)
async def ui_dedup_keep_separate(
    request: Request, candidate_id: UUID, session: DBSession,
) -> HTMLResponse:
    candidate = await session.get(DedupCandidate, candidate_id)
    if candidate is None:
        return HTMLResponse("")
    user = await _get_user(session, request)
    candidate.status = DedupStatus.kept_separate
    candidate.resolved_by_user_id = user.id if user else None
    candidate.resolved_at = datetime.now(UTC)
    await session.flush()
    return HTMLResponse(
        f'<tr id="dedup-row-{candidate_id}" class="text-muted" style="opacity:.4">'
        f'<td colspan="6" style="padding:10px 12px;font-size:12px">✓ Marked as separate records</td>'
        f'</tr>'
    )


@router.post("/ui/dedup/{candidate_id}/resolve", response_class=HTMLResponse)
async def ui_dedup_resolve(
    request: Request, candidate_id: UUID, session: DBSession,
) -> HTMLResponse:
    candidate = await session.get(DedupCandidate, candidate_id)
    if candidate is None:
        return HTMLResponse("")

    form = await request.form()
    action = str(form.get("action", "keep_separate"))
    winner = str(form.get("winner", "a"))
    user = await _get_user(session, request)

    if action == "keep_separate":
        candidate.status = DedupStatus.kept_separate
        candidate.resolved_by_user_id = user.id if user else None
        candidate.resolved_at = datetime.now(UTC)
        await session.flush()
        return HTMLResponse(
            f'<tr id="dedup-row-{candidate_id}" class="text-muted" style="opacity:.4">'
            f'<td colspan="6" style="padding:10px 12px;font-size:12px">✓ Kept as separate records</td>'
            f'</tr>'
        )

    # merge: apply field choices, mark loser as duplicate of winner
    a_type = _record_type_str(candidate.record_a_type)
    b_type = _record_type_str(candidate.record_b_type)

    if a_type == RecordType.listing.value and b_type == RecordType.listing.value:
        rec_a = await session.get(ScrapedListing, candidate.record_a_id)
        rec_b = await session.get(ScrapedListing, candidate.record_b_id)
        if rec_a and rec_b:
            winner_rec = rec_a if winner == "a" else rec_b
            loser_rec  = rec_b if winner == "a" else rec_a
            loser_source_key = "b" if winner == "a" else "a"

            # Apply per-field choices: if user picked the loser's source for a field,
            # copy that value onto the winner record
            for key, val in form.items():
                if not key.startswith("field_"):
                    continue
                field_name = key[6:]
                if field_name not in _ALLOWED_OVERRIDE_FIELDS:
                    continue
                if str(val) == loser_source_key:
                    setattr(winner_rec, field_name, getattr(loser_rec, field_name, None))

            loser_rec.canonical_id = winner_rec.id
            loser_rec.is_new = False
            loser_rec.archived = True

    candidate.status = DedupStatus.merged if winner == "a" else DedupStatus.swapped
    candidate.resolved_by_user_id = user.id if user else None
    candidate.resolved_at = datetime.now(UTC)
    await session.flush()

    label = "merged into primary" if winner == "a" else "merged (B preferred)"
    return HTMLResponse(
        f'<tr id="dedup-row-{candidate_id}" class="text-muted" style="opacity:.4">'
        f'<td colspan="6" style="padding:10px 12px;font-size:12px">✓ Records {label}</td>'
        f'</tr>'
    )


@router.post("/ui/listings/{listing_id}/realie-skip", response_class=HTMLResponse)
async def ui_toggle_realie_skip(
    listing_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Toggle realie_skip on a listing. Returns updated toggle button HTML."""
    listing = await session.get(ScrapedListing, listing_id)
    if listing is None:
        return HTMLResponse("")
    listing.realie_skip = not listing.realie_skip
    await session.flush()
    label = "Enable Realie" if listing.realie_skip else "Skip Realie"
    style = "color:var(--warning,#f59e0b)" if listing.realie_skip else ""
    return HTMLResponse(
        f'<button id="skip-btn-{listing_id}" style="{style}"'
        f' hx-post="/ui/listings/{listing_id}/realie-skip"'
        f' hx-swap="outerHTML" hx-target="#skip-btn-{listing_id}"'
        f' class="btn btn-sm btn-secondary">{label}</button>'
    )


