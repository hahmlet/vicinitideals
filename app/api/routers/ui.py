"""HTML UI routes — Jinja2 templates served directly from FastAPI."""

from __future__ import annotations

import asyncio
import io
import json
import time
import uuid as _uuid_mod
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from uuid import UUID

import httpx
from fastapi import APIRouter, Cookie, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app as _pkg
from app.api.deps import DBSession
from app.config import settings
from app.models.broker import Broker, Brokerage
from app.models.deal import Deal, DealModel, DealOpportunity, DealStatus, IncomeStream, IncomeStreamType, OperatingExpenseLine, OperationalInputs, ProjectType, UnitMix, UseLine, UseLinePhase
from app.models.ingestion import DedupCandidate, DedupStatus, IngestJob, RecordType, SavedSearchCriteria
from app.models.org import User
from app.models.capital import CapitalModule, DrawSource, WaterfallTier
from app.models.cashflow import OperationalOutputs
from app.models.parcel import Parcel, ProjectParcel, ProjectParcelRelationship
from app.models.portfolio import Portfolio, PortfolioProject
from app.models.milestone import DEFAULT_DURATIONS, Milestone, MilestoneType, MilestoneType as MT
from app.models.project import Opportunity, OpportunitySource, OpportunityStatus, Project, ProjectBuildingAssignment, ProjectParcelAssignment, ProjectStatus
from app.models.property import Building, BuildingStatus, OpportunityBuilding, Property
from app.models.scraped_listing import ScrapedListing
from app.models.realie_usage import RealieUsage
from app.scrapers.realie import _current_month

router = APIRouter(include_in_schema=False)

# ---------------------------------------------------------------------------
# Template setup
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(_pkg.__file__).parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _fmt_currency(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_currency_m(value: object) -> str:
    """Format as $XM (millions shorthand)."""
    if value is None:
        return "—"
    try:
        m = float(value) / 1_000_000
        return f"${m:.1f}M"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: object) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
        # Values stored as fractions (0.0–1.0) → multiply to get percentage
        if v <= 1.0:
            v *= 100
        return f"{v:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_multiple(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}×"
    except (TypeError, ValueError):
        return "—"


def _fmt_number(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


templates.env.filters["currency"] = _fmt_currency
templates.env.filters["currency_m"] = _fmt_currency_m
templates.env.filters["pct"] = _fmt_pct
templates.env.filters["multiple"] = _fmt_multiple
templates.env.filters["number_fmt"] = _fmt_number
templates.env.filters["urlencode"] = quote_plus

_SETTINGS_OWNER_NAME = "Stephen Ketch"
_PACIFIC = ZoneInfo("America/Los_Angeles")
_PROXYON_STATUS_CACHE_TTL_SECONDS = 3600
_proxyon_status_lock = asyncio.Lock()
_proxyon_status_cache: dict[str, Any] = {
    "fetched_monotonic": 0.0,
    "status_label": "Not Configured",
    "connected": False,
    "remaining_gb": None,
    "checked_at": None,
}

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
# Display mappings
# ---------------------------------------------------------------------------

_STATUS_DISPLAY: dict[str, tuple[str, str]] = {
    "hypothetical": ("Evaluation", "badge-blue"),
    "active": ("Execution", "badge-green"),
    "archived": ("Archived", "badge-gray"),
    "evaluation": ("Evaluation", "badge-blue"),
    "execution": ("Execution", "badge-green"),
    "under_contract": ("Under Contract", "badge-yellow"),
    "closed": ("Closed", "badge-gray"),
}

_TYPE_DISPLAY: dict[str, str] = {
    "acquisition_minor_reno": "Acquisition",
    "acquisition_major_reno": "Value-Add",
    "acquisition_conversion": "Conversion",
    "new_construction": "New Construction",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _primary_scenario(deal: Deal) -> DealModel | None:
    """Return the active Scenario (financial plan) for a Deal."""
    active = [s for s in deal.scenarios if s.is_active]
    if active:
        return active[0]
    if deal.scenarios:
        return sorted(deal.scenarios, key=lambda s: s.version, reverse=True)[0]
    return None


def _first_opportunity(deal: Deal) -> Opportunity | None:
    """Return the first Opportunity linked to a Deal."""
    if deal.deal_opportunities:
        return deal.deal_opportunities[0].opportunity
    return None


def _deal_address(deal: Deal) -> str | None:
    opp = _first_opportunity(deal)
    if opp is None:
        return None
    for pp in opp.project_parcels:
        if pp.parcel and pp.parcel.address_normalized:
            return pp.parcel.address_normalized
    return None


def _deal_building_description(deal: Deal) -> str | None:
    """Build a short building description from parcel or scraped listing data."""
    opp = _first_opportunity(deal)
    if opp is None:
        return None
    # Try parcels first
    for pp in opp.project_parcels:
        parcel = pp.parcel
        if parcel is None:
            continue
        parts: list[str] = []
        if parcel.unit_count:
            parts.append(f"{parcel.unit_count} units")
        if parcel.building_sqft:
            sqft = int(float(parcel.building_sqft))
            parts.append(f"{sqft:,} sqft")
        if parts:
            return " · ".join(parts)
    # Fall back to scraped listings
    for listing in opp.scraped_listings:
        parts = []
        if listing.unit_count:
            parts.append(f"{listing.unit_count} units")
        if listing.gba_sqft:
            sqft = int(float(listing.gba_sqft))
            parts.append(f"{sqft:,} sqft")
        if parts:
            return " · ".join(parts)
    return None


def _build_deal_row(deal: Deal) -> dict:
    scenario = _primary_scenario(deal)
    opp = _first_opportunity(deal)
    outputs = scenario.operational_outputs if scenario else None
    status_key = str(opp.status.value if opp and hasattr(opp.status, "value") else (opp.status if opp else "active"))
    status_display, status_badge = _STATUS_DISPLAY.get(status_key, ("Unknown", "badge-gray"))
    type_key = str(scenario.project_type.value if scenario and hasattr(scenario.project_type, "value") else (scenario.project_type if scenario else ""))
    return {
        "id": str(deal.id),
        "name": deal.name,
        "status": status_key,
        "status_display": status_display,
        "status_badge": status_badge,
        "type_display": _TYPE_DISPLAY.get(type_key, "—") if scenario else "—",
        "primary_model_name": scenario.name if scenario else None,
        "primary_model_id": str(scenario.id) if scenario else None,
        "address": _deal_address(deal),
        "building_description": _deal_building_description(deal),
        "noi": float(outputs.noi_stabilized) if outputs and outputs.noi_stabilized is not None else None,
        "irr": float(outputs.project_irr_levered) if outputs and outputs.project_irr_levered is not None else None,
        "equity_multiple": None,  # TODO: load from SensitivityResult (needs join)
        "last_updated_fmt": deal.created_at.strftime("%b %-d, %Y") if deal.created_at else None,
    }


# Maps UI filter value → DB enum. Statuses not in this map (under_contract, closed)
# don't exist in the DB yet — selecting them returns 0 results intentionally.
_STATUS_DB_MAP = {
    "evaluation": OpportunityStatus.hypothetical,
    "execution": OpportunityStatus.active,
}
_VALID_STATUS_FILTERS = {"evaluation", "execution", "under_contract", "closed"}


async def _load_deals(
    session: DBSession,
    status_filter: str = "",
    type_filter: str = "",
    model_filter: str = "",
    q: str = "",
    include_archived: bool = False,
) -> list[Deal]:
    """Load Deals with their Scenarios and linked Opportunities for the deals page."""
    stmt = (
        select(Deal)
        .options(
            selectinload(Deal.scenarios).selectinload(DealModel.operational_outputs),
            selectinload(Deal.deal_opportunities)
                .selectinload(DealOpportunity.opportunity)
                .selectinload(Opportunity.project_parcels)
                .selectinload(ProjectParcel.parcel),
            selectinload(Deal.deal_opportunities)
                .selectinload(DealOpportunity.opportunity)
                .selectinload(Opportunity.scraped_listings),
        )
        .order_by(Deal.created_at.desc())
    )

    if not include_archived:
        stmt = stmt.where(Deal.status != DealStatus.archived)

    if q:
        stmt = stmt.where(Deal.name.ilike(f"%{q}%"))

    result = await session.execute(stmt)
    deals = list(result.scalars().unique())

    if status_filter:
        if status_filter in _STATUS_DB_MAP:
            target_status = _STATUS_DB_MAP[status_filter]
            deals = [d for d in deals if _first_opportunity(d) and _first_opportunity(d).status == target_status]
        elif status_filter in _VALID_STATUS_FILTERS:
            deals = []

    if model_filter == "has":
        deals = [d for d in deals if _primary_scenario(d) is not None]
    elif model_filter == "none":
        deals = [d for d in deals if _primary_scenario(d) is None]

    if type_filter:
        deals = [
            d for d in deals
            if _primary_scenario(d) and str(getattr(_primary_scenario(d).project_type, "value", _primary_scenario(d).project_type)) == type_filter
        ]

    return deals


# Phase color palette (milestone_type → CSS class)
_PHASE_COLORS: dict[str, str] = {
    "offer_made":            "gantt-phase-offer",
    "under_contract":        "gantt-phase-contract",
    "close":                 "gantt-phase-close",
    "pre_development":       "gantt-phase-predev",
    "construction":          "gantt-phase-construction",
    "operation_lease_up":    "gantt-phase-leaseup",
    "operation_stabilized":  "gantt-phase-stabilized",
    "divestment":            "gantt-phase-exit",
}

_PHASE_LABELS: dict[str, str] = {
    "offer_made":           "Offer",
    "under_contract":       "Under Contract",
    "close":                "Close",
    "pre_development":      "Pre-Dev",
    "construction":         "Construction",
    "operation_lease_up":   "Lease-Up",
    "operation_stabilized": "Stabilized",
    "divestment":           "Divestment",
}


_GANTT_DISPLAY_CAPS: dict[str, int] = {
    "operation_stabilized": 730,   # show max 2 years; actual dates still shown in tooltips
    "operation_lease_up": 365,     # show max 1 year
}


_GANTT_DISPLAY_MINS: dict[str, int] = {
    "divestment": 30,   # single-day event needs visual presence on multi-year Gantt
}


def _apply_display_positions(bars: list[dict]) -> None:
    """Add display_start_day / display_duration_days, capping long hold phases.

    Uses actual calendar positions (not sequential cursor) so concurrent
    phases render at their real dates in the per-row layout.
    Sets is_truncated=True when the bar is shorter than its real duration.
    """
    for bar in bars:
        phase = bar.get("phase_key", "")
        cap = _GANTT_DISPLAY_CAPS.get(phase, bar["duration_days"])
        display_dur = min(bar["duration_days"], cap)
        min_dur = _GANTT_DISPLAY_MINS.get(phase)
        if min_dur and display_dur < min_dur:
            display_dur = min_dur
        bar["display_duration_days"] = display_dur
        bar["display_start_day"] = bar["start_day"]
        bar["is_truncated"] = display_dur < bar["duration_days"]


_NON_STAB_PHASES: frozenset[str] = frozenset({
    "offer_made", "under_contract", "close", "pre_development",
    "construction", "operation_lease_up", "divestment",
})


def _override_stabilized_cap(raw_rows: "list[dict]") -> None:
    """Cap operation_stabilized bars to end ~3 months after the last non-stabilized phase.

    This keeps the stabilized bar short enough to be readable while still
    indicating that operations continue indefinitely (via the truncation fade).
    """
    g_max_non_stab = 0
    for row in raw_rows:
        for bar in row["bars"]:
            if bar.get("phase_key") in _NON_STAB_PHASES:
                end = bar["start_day"] + bar["duration_days"]
                if end > g_max_non_stab:
                    g_max_non_stab = end

    if g_max_non_stab == 0:
        return  # no non-stab phases; keep static cap

    _THREE_MONTHS = 91

    for row in raw_rows:
        for bar in row["bars"]:
            if bar.get("phase_key") == "operation_stabilized":
                cap = max(30, g_max_non_stab + _THREE_MONTHS - bar["start_day"])
                actual_dur = bar["duration_days"]
                bar["display_duration_days"] = min(actual_dur, cap)
                bar["is_truncated"] = bar["display_duration_days"] < actual_dur


def _extract_milestone_bars(
    project: "Project",
    shared_epoch: "date | None" = None,
    milestones: "list | None" = None,
) -> "tuple[list[dict], date | None, bool]":
    """Extract Gantt bars from a project's milestones.

    Returns (bars, epoch_used, has_dates).
    epoch_used is the date origin for start_day values (None if no dates).
    has_dates is True when at least one anchor date was resolved.
    start_day values are relative to shared_epoch when provided.
    """
    from datetime import timedelta as _td

    milestones = sorted(milestones or project.milestones, key=lambda m: m.sequence_order)
    if not milestones:
        return [], shared_epoch, False

    m_map = {m.id: m for m in milestones}
    has_dates = any(m.target_date for m in milestones)
    bars: list[dict] = []
    epoch = shared_epoch

    if has_dates:
        for m in milestones:
            start = m.computed_start(m_map)
            if start is None and m.target_date:
                start = m.target_date
            if start is None:
                continue
            end = m.computed_end(m_map)
            if epoch is None:
                epoch = start
            start_day = (start - epoch).days
            dur = m.duration_days if m.duration_days > 0 else max(1, (end - start).days if end else 1)
            end_day = start_day + dur
            m_type = m.milestone_type.value if hasattr(m.milestone_type, "value") else m.milestone_type
            bars.append({
                "phase_key": m_type,
                "label": _PHASE_LABELS.get(m_type, m_type),
                "color_class": _PHASE_COLORS.get(m_type, "gantt-phase-other"),
                "start_day": start_day,
                "duration_days": dur,
                "end_day": end_day,
                "start_fmt": start.strftime("%b %Y"),
                "end_fmt": (epoch + _td(days=end_day)).strftime("%b %Y") if epoch else "",
            })
    else:
        cursor = 0
        for m in milestones:
            dur = m.duration_days if m.duration_days > 0 else 30
            m_type = m.milestone_type.value if hasattr(m.milestone_type, "value") else m.milestone_type
            bars.append({
                "phase_key": m_type,
                "label": _PHASE_LABELS.get(m_type, m_type),
                "color_class": _PHASE_COLORS.get(m_type, "gantt-phase-other"),
                "start_day": cursor,
                "duration_days": dur,
                "end_day": cursor + dur,
                "start_fmt": "",
                "end_fmt": "",
            })
            cursor += dur

    _apply_display_positions(bars)
    return bars, epoch, has_dates


def _apply_pct_positions(rows: list[dict], global_min: int, global_max: int) -> None:
    """Mutate each bar in rows to add left_pct / width_pct using display positions."""
    total_span = max(global_max - global_min, 1)
    for row in rows:
        for bar in row["bars"]:
            start = bar.get("display_start_day", bar["start_day"])
            dur = bar.get("display_duration_days", bar["duration_days"])
            bar["left_pct"] = round(100 * (start - global_min) / total_span, 2)
            bar["width_pct"] = max(round(100 * dur / total_span, 2), 1.5)


def _compute_gantt_axis(
    epoch: "date | None",
    global_min_day: int,
    global_max_day: int,
    has_dates: bool,
) -> "tuple[list[dict], list[dict]]":
    """Return (month_ticks, year_spans) with left_pct coordinates for the Gantt time axis."""
    import datetime as _dt

    total_span = max(global_max_day - global_min_day, 1)

    def _pct(day_offset: int) -> float:
        return round(100.0 * max(0, day_offset) / total_span, 2)

    if not has_dates or epoch is None:
        # Relative mode: 30-day pseudo-months, 360-day pseudo-years
        month_ticks: list[dict] = []
        day = 30
        while day < total_span:
            is_yr = day > 0 and day % 360 == 0
            month_ticks.append({"left_pct": _pct(day), "label": f"M{day // 30 + 1}", "is_year_start": is_yr})
            day += 30
        year_spans: list[dict] = []
        y, yr = 0, 1
        while y < total_span:
            end = min(y + 360, total_span)
            year_spans.append({"label": f"Year {yr}", "left_pct": _pct(y), "width_pct": round(_pct(end) - _pct(y), 2)})
            y += 360
            yr += 1
        return month_ticks, year_spans

    # Calendar mode
    start_date = epoch + _dt.timedelta(days=global_min_day)
    end_date = epoch + _dt.timedelta(days=global_max_day)

    def _date_pct(d: "_dt.date") -> float:
        return _pct((d - epoch).days - global_min_day)

    # Month ticks: first of each calendar month within the range
    month_ticks = []
    cur = start_date.replace(day=1)
    if cur < start_date:
        cur = (cur.replace(month=cur.month + 1) if cur.month < 12 else _dt.date(cur.year + 1, 1, 1))
    while cur <= end_date:
        lp = _date_pct(cur)
        if 0 < lp < 100:
            month_ticks.append({"left_pct": lp, "label": cur.strftime("%b").upper(), "is_year_start": cur.month == 1})
        cur = (cur.replace(month=cur.month + 1) if cur.month < 12 else _dt.date(cur.year + 1, 1, 1))

    # Year spans
    year_spans = []
    for yr in range(start_date.year, end_date.year + 1):
        s = max(0.0, _date_pct(_dt.date(yr, 1, 1)))
        e = min(100.0, _date_pct(_dt.date(yr + 1, 1, 1)))
        if e <= 0 or s >= 100:
            continue
        year_spans.append({"label": str(yr), "left_pct": round(s, 2), "width_pct": round(max(0.0, e - s), 2)})

    return month_ticks, year_spans


def _gantt_apply_pct(bars: list[dict], g_min: int, g_max: int) -> None:
    """Mutate bars in-place to add left_pct / width_pct."""
    total_span = max(g_max - g_min, 1)
    for bar in bars:
        start = bar.get("display_start_day", bar["start_day"])
        dur = bar.get("display_duration_days", bar["duration_days"])
        bar["left_pct"] = round(100 * (start - g_min) / total_span, 2)
        bar["width_pct"] = max(round(100 * dur / total_span, 2), 1.5)


def _bars_to_phase_rows(bars: list[dict]) -> list[dict]:
    """Convert a list of bar dicts to phase-type rows for the Gantt v2 template."""
    return [{
        "type": "phase",
        "phase_key": b.get("phase_key", ""),
        "label": b["label"],
        "color_class": b["color_class"],
        "left_pct": b["left_pct"],
        "width_pct": b["width_pct"],
        "start_fmt": b.get("start_fmt", ""),
        "end_fmt": b.get("end_fmt", ""),
        "is_truncated": b.get("is_truncated", False),
        "duration_days": b.get("duration_days", 0),
    } for b in bars]


def _build_gantt_rows(deal: "Deal") -> "dict | None":
    """Build Gantt data for deal_detail.html (Gantt v2).

    Returns a dict with keys: has_dates, month_ticks, year_spans, rows.
    rows is a flat list of project_header and phase items.
    Returns None if no milestone data.
    """
    active_scenario = _primary_scenario(deal)
    if active_scenario is None or not active_scenario.projects:
        return None

    raw_rows: list[dict] = []
    epoch = None
    any_has_dates = False

    for project in active_scenario.projects:
        bars, epoch, hd = _extract_milestone_bars(project, epoch)
        if not bars:
            continue
        any_has_dates = any_has_dates or hd
        raw_rows.append({"project_name": project.name, "bars": bars})

    if not raw_rows:
        return None

    # Override stabilized bar length to 3 months past last non-stab phase
    _override_stabilized_cap(raw_rows)

    # Compute global extent AFTER the override (stabilized cap changes global_max)
    all_bars = [b for row in raw_rows for b in row["bars"]]
    g_min = min(b["display_start_day"] for b in all_bars)
    g_max = max(b["display_start_day"] + b["display_duration_days"] for b in all_bars)

    for row in raw_rows:
        _gantt_apply_pct(row["bars"], g_min, g_max)

    multi = len(raw_rows) > 1
    rows: list[dict] = []
    for raw_row in raw_rows:
        if multi:
            rows.append({"type": "project_header", "name": raw_row["project_name"]})
        rows.extend(_bars_to_phase_rows(raw_row["bars"]))

    month_ticks, year_spans = _compute_gantt_axis(epoch, g_min, g_max, any_has_dates)
    return {"has_dates": any_has_dates, "month_ticks": month_ticks, "year_spans": year_spans, "rows": rows}


def _build_portfolio_gantt(portfolio_entries: "list[tuple[str, str, Deal]]") -> "dict | None":
    """Build multi-deal Gantt data for portfolio_detail.html (Gantt v2).

    portfolio_entries: list of (deal_name, scenario_name, Deal) tuples.
    All deals share one global epoch so they align on the same calendar axis.
    """
    raw: list[tuple[str, list[dict]]] = []
    global_epoch = None
    any_has_dates = False

    for deal_name, scenario_name, deal in portfolio_entries:
        active_scenario = _primary_scenario(deal)
        if active_scenario is None or not active_scenario.projects:
            continue
        for project in active_scenario.projects:
            bars, global_epoch, has_dates = _extract_milestone_bars(project, global_epoch)
            if not bars:
                continue
            any_has_dates = any_has_dates or has_dates
            row_name = deal_name if len(active_scenario.projects) == 1 else f"{deal_name} / {project.name}"
            raw.append((row_name, bars))

    if not raw:
        return None

    # Wrap into raw_rows format for _override_stabilized_cap
    raw_rows = [{"project_name": name, "bars": bars} for name, bars in raw]
    _override_stabilized_cap(raw_rows)

    all_bars = [b for row in raw_rows for b in row["bars"]]
    g_min = min(b["display_start_day"] for b in all_bars)
    g_max = max(b["display_start_day"] + b["display_duration_days"] for b in all_bars)

    rows: list[dict] = []
    for row in raw_rows:
        _gantt_apply_pct(row["bars"], g_min, g_max)
        rows.append({"type": "project_header", "name": row["project_name"]})
        rows.extend(_bars_to_phase_rows(row["bars"]))

    month_ticks, year_spans = _compute_gantt_axis(global_epoch, g_min, g_max, any_has_dates)
    return {"has_dates": any_has_dates, "month_ticks": month_ticks, "year_spans": year_spans, "rows": rows}


async def _get_user(session: DBSession, request: Request) -> User | None:
    """Resolve the current user from the session cookie.

    Checks vd_session (new signed cookie) first, falls back to vd_user_id
    (legacy splash-screen cookie) so existing sessions keep working.
    """
    from app.api.auth import COOKIE_NAME, decode_session_token

    token = request.cookies.get(COOKIE_NAME)
    if token:
        uid = decode_session_token(token)
        if uid is not None:
            return await session.get(User, uid)

    # Legacy fallback — vd_user_id cookie set by the splash screen
    legacy = request.cookies.get("vd_user_id")
    if legacy:
        try:
            uid = UUID(legacy)
            return await session.get(User, uid)
        except ValueError:
            pass
    return None


async def _get_dedup_count(session: DBSession) -> int:
    try:
        result = await session.execute(
            select(func.count())
            .select_from(DedupCandidate)
            .where(DedupCandidate.status == DedupStatus.pending)
        )
        return int(result.scalar_one())
    except Exception:
        return 0


async def _get_address_issues_count(session: AsyncSession) -> int:
    try:
        result = await session.execute(
            select(func.count())
            .select_from(ScrapedListing)
            .where(
                ScrapedListing.realie_skip.is_(True),
                ScrapedListing.realie_enriched_at.is_(None),
                ScrapedListing.apn.is_(None),  # listings with a valid APN don't need address resolution
            )
        )
        return int(result.scalar_one())
    except Exception:
        return 0


def _base_ctx(user: User | None, dedup_count: int, active_nav: str, address_issues_count: int = 0) -> dict:
    initials = "??"
    if user:
        parts = user.name.split()
        initials = (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else user.name[:2].upper()
    return {
        "user_name": user.name if user else "Guest",
        "user_initials": initials,
        "user_color": (user.display_color if user else None) or "#2563EB",
        # Soft email-verification gate: templates show a banner when False.
        # None / missing is treated as verified to avoid false positives.
        "user_email_verified": bool(getattr(user, "email_verified", True)) if user else True,
        "active_nav": active_nav,
        "dedup_count": dedup_count,
        "address_issues_count": address_issues_count,
    }


def _is_settings_owner(user: User | None) -> bool:
    return bool(user and user.name.strip().lower() == _SETTINGS_OWNER_NAME.lower())


def _require_settings_owner(user: User | None) -> None:
    if not _is_settings_owner(user):
        # Hide route existence for all non-owner users.
        raise HTTPException(status_code=404, detail="Not found")


def _fmt_ts(ts: datetime | None) -> str:
    if ts is None:
        return "Never"
    return ts.astimezone(_PACIFIC).strftime("%Y-%m-%d %H:%M PT")


def _freshness_status(ts: datetime | None, stale_after_hours: int) -> str:
    if ts is None:
        return "No activity"
    age_hours = (datetime.now(UTC) - ts.astimezone(UTC)).total_seconds() / 3600
    return "Healthy" if age_hours <= stale_after_hours else "Stale"


async def _direct_live_ping(url: str, timeout_seconds: float = 8.0) -> bool:
    """Ping a URL directly without inheriting system/env proxy settings."""
    headers = {
        "User-Agent": "VicinitiDeals/1.0",
        "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    }
    timeout = httpx.Timeout(timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
            response = await client.get(url, headers=headers)
            return int(response.status_code) < 500
    except Exception:
        return False


async def _proxyon_remaining_gb(timeout_seconds: float = 8.0) -> str | None:
    """Return residential GB remaining from ProxyOn API if credentials are configured."""
    api_key = (settings.proxyon_api_key or "").strip()
    if not api_key:
        return None

    timeout = httpx.Timeout(timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
            auth = await client.post(
                "https://api.proxyon.io/v1/auth/token",
                data={"apikey": api_key},
                headers={"Accept": "application/json"},
            )
            auth.raise_for_status()
            auth_body = auth.json()
            if not auth_body.get("success"):
                return None
            token = (auth_body.get("result") or {}).get("token")
            if not token:
                return None

            stats = await client.get(
                "https://api.proxyon.io/v1/residential/stats",
                headers={"X-Session-Token": token, "Accept": "application/json"},
            )
            stats.raise_for_status()
            stats_body = stats.json()
            if not stats_body.get("success"):
                return None
            result = stats_body.get("result") or {}

            for key in ("remaining_gb", "gb_remaining", "left_gb", "remaining", "traffic_left_gb"):
                if key in result and result[key] is not None:
                    return f"{float(result[key]):,.2f} GB"

            for key in ("total_gb", "used_gb"):
                if key in result and result[key] is not None:
                    total = float(result.get("total_gb") or 0)
                    used = float(result.get("used_gb") or 0)
                    if total > 0:
                        return f"{max(total - used, 0):,.2f} GB"
    except Exception:
        return None
    return None


async def _proxyon_residential_snapshot(timeout_seconds: float = 8.0) -> dict[str, Any]:
    """Return cached (hourly) ProxyOn residential connection state and remaining GB."""
    now_monotonic = time.monotonic()
    cached_age = now_monotonic - float(_proxyon_status_cache.get("fetched_monotonic") or 0.0)
    if cached_age < _PROXYON_STATUS_CACHE_TTL_SECONDS:
        return dict(_proxyon_status_cache)

    async with _proxyon_status_lock:
        now_monotonic = time.monotonic()
        cached_age = now_monotonic - float(_proxyon_status_cache.get("fetched_monotonic") or 0.0)
        if cached_age < _PROXYON_STATUS_CACHE_TTL_SECONDS:
            return dict(_proxyon_status_cache)

        checked_at = datetime.now(UTC)
        api_key = (settings.proxyon_api_key or "").strip()
        if not api_key:
            _proxyon_status_cache.update(
                {
                    "fetched_monotonic": now_monotonic,
                    "status_label": "Not Configured",
                    "connected": False,
                    "remaining_gb": None,
                    "checked_at": None,
                }
            )
            return dict(_proxyon_status_cache)

        account_balance: str | None = None
        connected = False
        timeout = httpx.Timeout(timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                auth = await client.post(
                    "https://api.proxyon.io/v1/auth/token",
                    data={"apikey": api_key},
                    headers={"Accept": "application/json"},
                )
                auth.raise_for_status()
                auth_body = auth.json()
                if auth_body.get("success"):
                    result = auth_body.get("result") or {}
                    token = result.get("token") or result.get("sessionToken")
                    if token:
                        acct = await client.get(
                            "https://api.proxyon.io/v1/account/info",
                            headers={"X-Session-Token": token, "Accept": "application/json"},
                        )
                        acct.raise_for_status()
                        acct_body = acct.json()
                        if acct_body.get("success"):
                            connected = True
                            acct_result = acct_body.get("result") or {}
                            balance = acct_result.get("balance")
                            if balance is not None:
                                account_balance = f"${float(balance):,.2f}"
        except Exception:
            connected = False

        _proxyon_status_cache.update(
            {
                "fetched_monotonic": now_monotonic,
                "status_label": "Active (Connected)" if connected else "Configured (Disconnected)",
                "connected": connected,
                "remaining_gb": account_balance,
                "checked_at": checked_at,
            }
        )
        return dict(_proxyon_status_cache)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/deals")


@router.get("/splash", response_class=HTMLResponse)
async def splash(request: Request, session: DBSession) -> HTMLResponse:
    users = list((await session.execute(select(User).order_by(User.name))).scalars())
    return templates.TemplateResponse(request, "splash.html", {"users": users})


@router.post("/splash/select")
async def select_user(user_id: str = Form(...)) -> RedirectResponse:
    resp = RedirectResponse(url="/deals", status_code=303)
    resp.set_cookie("vd_user_id", user_id, max_age=60 * 60 * 24 * 30, httponly=True)
    return resp


@router.get("/settings/scraping-services", response_class=HTMLResponse)
async def settings_scraping_services(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = await _get_user(session, request)
    _require_settings_owner(user)
    dedup_count = await _get_dedup_count(session)
    address_issues_count = await _get_address_issues_count(session)

    loopnet_job = (await session.execute(
        select(IngestJob)
        .where(IngestJob.source == "loopnet")
        .order_by(IngestJob.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    crexi_job = (await session.execute(
        select(IngestJob)
        .where(IngestJob.source == "crexi")
        .order_by(IngestJob.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    residential_username = (settings.proxyon_residential_username or "").strip()
    residential_password = (settings.proxyon_residential_password or "").strip()
    residential_configured = bool(residential_username and residential_password)
    datacenter_count = len([p for p in (settings.proxyon_datacenter_proxies or "").split(",") if p.strip()])
    proxyon_snapshot = await _proxyon_residential_snapshot()
    residential_status = "Configured" if residential_configured else "Not Configured"
    residential_gb_remaining = proxyon_snapshot.get("remaining_gb")
    _checked_at = proxyon_snapshot.get("checked_at")
    residential_last_checked = _fmt_ts(_checked_at) if _checked_at else "API key not configured"

    services = [
        {
            "name": "LoopNet Ingest",
            "description": "Scheduled LoopNet scrape jobs that ingest and deduplicate listing inventory.",
            "status": "Disabled",
            "schedule": "Disabled",
            "proxy": "Disabled",
            "last_run": _fmt_ts(loopnet_job.started_at if loopnet_job else None),
            "last_result": "disabled",
        },
        {
            "name": "Crexi Ingest",
            "description": "Daily Crexi crawler run for refreshed multifamily listing coverage.",
            "status": _freshness_status(crexi_job.started_at if crexi_job else None, stale_after_hours=30),
            "schedule": "Daily at 06:00 PT via Celery beat",
            "proxy": "Residential (ProxyOn)" if residential_configured else "Residential (ProxyOn, not configured)",
            "last_run": _fmt_ts(crexi_job.started_at if crexi_job else None),
            "last_result": crexi_job.status if crexi_job else "never",
        },
    ]

    return templates.TemplateResponse(
        request,
        "settings_scraping_services.html",
        {
            "services": services,
            "residential_status": residential_status,
            "datacenter_count": datacenter_count,
            "residential_gb_remaining": residential_gb_remaining,
            "residential_last_checked": residential_last_checked,
            **_base_ctx(user, dedup_count, "", address_issues_count),
        },
    )


@router.get("/settings/data-sources", response_class=HTMLResponse)
async def settings_data_sources(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = await _get_user(session, request)
    _require_settings_owner(user)
    dedup_count = await _get_dedup_count(session)
    address_issues_count = await _get_address_issues_count(session)

    parcel_count = int((await session.execute(select(func.count()).select_from(Parcel))).scalar_one())

    # cache_file: path relative to /app/data/gis_cache/  (empty = not cached as file)
    # ping_host:  hostname key used to share one liveness check across all layers on that host
    def _layer(name: str, slug: str, type_: str, status: str, notes: str,
               cache_file: str = "", ping_host: str = "") -> dict:
        return {"name": name, "slug": slug, "type": type_, "status": status,
                "notes": notes, "cache_file": cache_file, "ping_host": ping_host}

    groups = [
        {
            "id": "parcel_seeding", "title": "Parcel Seeding", "provider": "",
            "layers": [
                _layer("Metro RLIS Taxlots", "tax_lots_metro_rlis", "FeatureServer", "Active",
                       f"Primary seed — ~430k features (Multnomah + Clackamas). {parcel_count:,} parcels in DB. "
                       "Polygon geometry + assessed values. Owner name stripped in public layer. Monthly refresh by Metro.",
                       cache_file="oregon/tax_lots_metro_rlis.geojson", ping_host="services2.arcgis.com"),
                _layer("Oregon Address Points", "address_points_or", "FeatureServer", "Cached",
                       "462,110 features downloaded. PARCEL_ID 0% populated by Portland/Clackamas 911 agencies — "
                       "cannot be used for parcel seeding. Retained for potential address enrichment.",
                       cache_file="oregon/address_points_or.geojson", ping_host="services8.arcgis.com"),
            ],
        },
        {
            "id": "boundary_routing", "title": "Boundary & Routing", "provider": "",
            "layers": [
                _layer("City Limits (Oregon)", "city_limits_or", "MapServer", "Active",
                       "ODOT source. Point-in-polygon routing for listings without a clean jurisdiction.",
                       cache_file="oregon/city_limits_or.geojson", ping_host="gis.odot.state.or.us"),
                _layer("County Boundaries (Oregon)", "county_boundaries_or", "FeatureServer", "Active",
                       "BLM source. County routing fallback for unincorporated parcels.",
                       cache_file="oregon/county_boundaries_or.geojson", ping_host="services1.arcgis.com"),
                _layer("Urban Growth Boundaries (Oregon)", "urban_growth_boundaries_or", "FeatureServer", "Active",
                       "DLCD source. Out-of-market screening gate — parcels outside UGB are Out of Market.",
                       cache_file="oregon/urban_growth_boundaries_or.geojson", ping_host="services8.arcgis.com"),
            ],
        },
        {
            "id": "incentive_screening", "title": "Incentive Screening", "provider": "",
            "layers": [
                _layer("Enterprise Zones (Oregon)", "enterprise_zones_or", "FeatureServer", "Active",
                       "Oregon Business Development Dept. Statewide enterprise zone polygons.",
                       cache_file="oregon/enterprise_zones_or.geojson", ping_host="services8.arcgis.com"),
                _layer("Opportunity Zones (Oregon)", "opportunity_zones_or", "FeatureServer", "Active",
                       "Filter: STATE='41'. Federal Opportunity Zone census tracts.",
                       cache_file="external/opportunity_zones_or.geojson", ping_host="services.arcgis.com"),
                _layer("NMTC Qualified Tracts", "nmtc_qualified_tracts_or", "FeatureServer", "Active",
                       "Filter: STATE_FIPS='41'. New Markets Tax Credit qualified census tracts.",
                       cache_file="external/nmtc_qualified_tracts_or.geojson", ping_host="services6.arcgis.com"),
            ],
        },
        {
            "id": "environmental", "title": "Environmental", "provider": "Oregon GEO (services8.arcgis.com)",
            "layers": [
                _layer("Wetlands — LWI", "wetlands_lwi_or", "FeatureServer", "Active",
                       "Oregon Local Wetland Inventory. Additive evidence family with NWI + MORE.",
                       cache_file="oregon/wetlands_lwi_or.geojson", ping_host="services8.arcgis.com"),
                _layer("Wetlands — NWI", "wetlands_nwi_or", "FeatureServer", "Active",
                       "USFWS National Wetland Inventory. Combined with LWI + MORE for better coverage.",
                       cache_file="oregon/wetlands_nwi_or.geojson", ping_host="services8.arcgis.com"),
                _layer("Wetlands — MORE Oregon", "wetlands_more_or", "FeatureServer", "Active",
                       "More Oregon Wetlands dataset. Third additive layer in the family.",
                       cache_file="oregon/wetlands_more_or.geojson", ping_host="services8.arcgis.com"),
            ],
        },
        {
            "id": "street_classifications", "title": "Street Classifications", "provider": "",
            "layers": [
                _layer("ODOT State Roads", "street_functional_class_state_or", "MapServer", "Active",
                       "Federal functional class for ODOT-owned roads statewide. NEW_FC_TYP: Interstate / Freeway / Arterial / Collector / Local.",
                       ping_host="gis.odot.state.or.us"),
                _layer("ODOT Non-State Roads", "street_functional_class_nonstate_or", "MapServer", "Active",
                       "Federal functional class for county/city/other roads. Covers all of Multnomah + Clackamas combined with State layer.",
                       ping_host="gis.odot.state.or.us"),
            ],
        },
        {
            "id": "reference", "title": "Reference Layers", "provider": "Oregon GEO (services8.arcgis.com)",
            "layers": [
                _layer("Building Footprints (Oregon)", "building_footprints_or", "FeatureServer", "Active",
                       "Structural screening — confirms existing building presence and approximate footprint area.",
                       cache_file="oregon/building_footprints_or.geojson", ping_host="services8.arcgis.com"),
                _layer("Oregon ZIP Reference", "oregon_zip_reference", "FeatureServer", "Active",
                       "ZIP code polygon reference for address routing.",
                       cache_file="oregon/oregon_zip_reference.geojson", ping_host="services8.arcgis.com"),
                _layer("Census Block Groups 2020", "census_block_groups_2020_or", "FeatureServer", "Active",
                       "Demographic context for NMTC / Opportunity Zone joins.",
                       cache_file="oregon/census_block_groups_2020_or.geojson", ping_host="services8.arcgis.com"),
                _layer("Census Tracts 2020", "census_tracts_2020_or", "FeatureServer", "Active",
                       "Demographic context for NMTC / Opportunity Zone joins.",
                       cache_file="oregon/census_tracts_2020_or.geojson", ping_host="services8.arcgis.com"),
            ],
        },
        {
            "id": "local_fairview", "title": "Local GIS — Fairview",
            "provider": "services5.arcgis.com · Fairview ArcGIS Online (Org: 3DoY8p7EnUTzaIE7)",
            "layers": [
                _layer("Natural Resource Protection Areas", "natural_resources_fairview", "FeatureServer", "Active",
                       "TYPE field: riparian buffers (35'/40'/55'/80'), Fairview Lake 50' buffer, platted protected areas, upland habitat, wetlands.",
                       cache_file="fairview/natural_resources_fairview.geojson", ping_host="services5.arcgis.com"),
                _layer("Fairview Lake 35ft Buffer", "fairview_lake_35ft_buffer", "FeatureServer", "Active",
                       "Additive to natural resource layer.",
                       cache_file="fairview/fairview_lake_35ft_buffer.geojson", ping_host="services5.arcgis.com"),
                _layer("Fairview Lake 50ft Buffer", "fairview_lake_50ft_buffer", "FeatureServer", "Active",
                       "Additive to natural resource layer.",
                       cache_file="fairview/fairview_lake_50ft_buffer.geojson", ping_host="services5.arcgis.com"),
                _layer("Enterprise Zone", "enterprise_zone_fairview", "FeatureServer", "Active",
                       "Columbia Cascade Enterprise Zone, ~34 parcels. Supplement to statewide EZ layer.",
                       cache_file="fairview/enterprise_zone_fairview.geojson", ping_host="services5.arcgis.com"),
                _layer("Overlay Districts", "overlay_districts_fairview", "FeatureServer", "Active",
                       "Airport Overlay, Storefront District (TCC), Four Corners Area (VMU), R/SFLD.",
                       cache_file="fairview/overlay_districts_fairview.geojson", ping_host="services5.arcgis.com"),
                _layer("Street Jurisdiction Routing", "streets_jurisdiction_fairview", "FeatureServer", "Active",
                       "OWNER field: City of Fairview / Gresham / Multnomah County / ODOT / Private.",
                       cache_file="fairview/streets_jurisdiction_fairview.geojson", ping_host="services5.arcgis.com"),
                _layer("Zoning", "—", "PDF / Manual", "Manual",
                       "No queryable GIS layer. zoning_lookup_url set on parcels at seed time. Zone Painter used for manual zoning_code assignment."),
            ],
        },
        {
            "id": "local_gresham", "title": "Local GIS — Gresham",
            "provider": "gis.greshamoregon.gov · Gresham MapServer",
            "layers": [
                _layer("East County Taxlots (RLIS+)", "tax_lots_east_county", "MapServer", "Active",
                       "Full RLIS dataset with ZONE + owner fields intact. Covers Portland, Troutdale, Fairview, Wood Village, unincorporated Multnomah — not Gresham city parcels.",
                       cache_file="gresham/tax_lots_east_county.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("City Limits", "city_limits", "MapServer", "Active",
                       "Gresham jurisdiction boundary.",
                       cache_file="gresham/city_limits.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Neighborhoods", "neighborhoods", "MapServer", "Active",
                       "Neighborhood routing layer.",
                       cache_file="gresham/neighborhoods.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Addresses", "addresses_all", "MapServer", "Active",
                       "Address-level routing.",
                       cache_file="gresham/addresses_all.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Multifamily Housing Inventory", "multifamily_housing", "MapServer", "Active",
                       "Existing MF housing stock — used for comparables context.",
                       cache_file="gresham/multifamily_housing.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Planning Overlays", "—", "MapServer", "Active",
                       "Pleasant Valley, Kelley Creek Headwaters, Springwater plan areas; Rockwood Plan District; Design Districts.",
                       cache_file="gresham/pleasant_valley_plan_area.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Street Classifications", "street_classifications", "MapServer", "Active",
                       "Local Gresham Planning dept street designations.",
                       cache_file="gresham/street_classifications.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Environmental Overlays", "—", "MapServer", "Active",
                       "Streams, other waters, environmental overlay districts.",
                       cache_file="gresham/streams.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Transit Layers", "—", "MapServer", "Active",
                       "Bike routes, MAX stops, bus stops, bus lines.",
                       cache_file="gresham/bus_stops.geojson", ping_host="gis.greshamoregon.gov"),
                _layer("Incentive Zones (6 layers)", "—", "MapServer", "Active",
                       "Incentive eligibility overlays from Gresham Incentives MapServer.",
                       cache_file="gresham/rockwood_urban_renewal_area.geojson", ping_host="gis.greshamoregon.gov"),
            ],
        },
        {
            "id": "local_wood_village", "title": "Local GIS — Wood Village",
            "provider": "services7.arcgis.com · City of Wood Village ArcGIS Online (Org: 5Loh3xXKWLd2M7xA)",
            "layers": [
                _layer("Zoning", "zoning_wood_village", "FeatureServer", "Active",
                       "Labeling (zone code), Name (description). Supports advanced queries.",
                       cache_file="wood_village/zoning_wood_village.geojson", ping_host="services7.arcgis.com"),
                _layer("Taxlots (RLIS-compatible)", "taxlots_wood_village", "FeatureServer", "Active",
                       "RLIS-compatible fields: TLID, LANDVAL, ASSESSVAL, LANDUSE, STATECLASS, YEARBUILT, BLDGSQFT, SITEADDR.",
                       cache_file="wood_village/taxlots_wood_village.geojson", ping_host="services7.arcgis.com"),
                _layer("City Limits", "city_limits_wood_village", "FeatureServer", "Active",
                       "Jurisdiction boundary.",
                       cache_file="wood_village/city_limits_wood_village.geojson", ping_host="services7.arcgis.com"),
            ],
        },
        {
            "id": "local_troutdale", "title": "Local GIS — Troutdale",
            "provider": "maps.troutdaleoregon.gov · Self-hosted ArcGIS Enterprise",
            "layers": [
                _layer("Zoning (Urban Planning Area)", "zoning_troutdale", "MapServer", "Active",
                       "ZONE field (R10, GI, etc.). supportsAdvancedQueries: true.",
                       ping_host="maps.troutdaleoregon.gov"),
                _layer("Street Centerlines", "streets_troutdale", "MapServer", "Active",
                       "CLASS (designation), OWNER, CONDTN fields.",
                       ping_host="maps.troutdaleoregon.gov"),
            ],
        },
        # ── Clackamas County cities ───────────────────────────────────────
        {
            "id": "local_happy_valley", "title": "Local GIS — Happy Valley",
            "provider": "services5.arcgis.com · ArcGIS Online (Org: fuVQ9NIPGnPhCBXp)",
            "layers": [
                _layer("Zoning", "zoning_happy_valley", "FeatureServer", "Active",
                       "Authoritative 2024 zoning. Fields: ZONE (e.g. R-1, C-1), ZOVER (overlay), ORDINANCE, DATE_.",
                       cache_file="happy_valley/zoning_happy_valley.geojson", ping_host="services5.arcgis.com"),
                _layer("City Limits", "city_limits_happy_valley", "FeatureServer", "Active",
                       "Jurisdiction boundary.",
                       cache_file="happy_valley/city_limits_happy_valley.geojson", ping_host="services5.arcgis.com"),
                _layer("Natural Resource Overlay", "natural_resources_happy_valley", "FeatureServer", "Active",
                       "Natural resource protection overlay zones.",
                       cache_file="happy_valley/natural_resources_happy_valley.geojson", ping_host="services5.arcgis.com"),
                _layer("FEMA Floodplain", "fema_floodplain_happy_valley", "FeatureServer", "Active",
                       "FEMA flood hazard zones.",
                       cache_file="happy_valley/fema_floodplain_happy_valley.geojson", ping_host="services5.arcgis.com"),
            ],
        },
        {
            "id": "local_milwaukie", "title": "Local GIS — Milwaukie",
            "provider": "services6.arcgis.com · ArcGIS Online (Org: 8e6aYcxt8yhvXvO9)",
            "layers": [
                _layer("Zoning", "zoning_milwaukie", "FeatureServer", "Active",
                       "COM_Zoning_SDE layer 11. Field: ZONE (MUTSA, BI, GMU, C-CS, DMU, C-G, NMU, SMU, OS, M, R-MD, R-HD).",
                       cache_file="milwaukie/zoning_milwaukie.geojson", ping_host="services6.arcgis.com"),
                _layer("City Limits", "city_limits_milwaukie", "FeatureServer", "Active",
                       "Jurisdiction boundary.",
                       cache_file="milwaukie/city_limits_milwaukie.geojson", ping_host="services6.arcgis.com"),
                _layer("Wetlands", "wetlands_milwaukie", "FeatureServer", "Active",
                       "Local wetland inventory. Same service also has vegetated corridors (6), habitat conservation areas (7), Willamette Greenway (8).",
                       cache_file="milwaukie/wetlands_milwaukie.geojson", ping_host="services6.arcgis.com"),
                _layer("FEMA Floodplain", "floodplain_milwaukie", "FeatureServer", "Active",
                       "FEMA flood hazard zones (COM_FEMA_Hazards service).",
                       cache_file="milwaukie/floodplain_milwaukie.geojson", ping_host="services6.arcgis.com"),
                _layer("Urban Renewal Area", "urban_renewal_milwaukie", "FeatureServer", "Active",
                       "Urban renewal district boundary (COM_URA service).",
                       cache_file="milwaukie/urban_renewal_milwaukie.geojson", ping_host="services6.arcgis.com"),
            ],
        },
        {
            "id": "local_oregon_city", "title": "Local GIS — Oregon City",
            "provider": "maps.orcity.org · Self-hosted ArcGIS Enterprise (v11.5)",
            "layers": [
                _layer("Zoning", "zoning_oregon_city", "MapServer", "Active",
                       "LandUseAndPlanning_PUBLIC layer 62. Same service: comp plan (57), enterprise zones (3, 85), opportunity zones (73), urban renewal (33), historic districts (31-32).",
                       cache_file="oregon_city/zoning_oregon_city.geojson", ping_host="maps.orcity.org"),
                _layer("City Limits", "city_limits_oregon_city", "MapServer", "Active",
                       "City boundary and annexation history.",
                       cache_file="oregon_city/city_limits_oregon_city.geojson", ping_host="maps.orcity.org"),
                _layer("Taxlots", "taxlots_oregon_city", "MapServer", "Active",
                       "Taxlot polygons. Max 50k records, min scale 1:20,000.",
                       cache_file="oregon_city/taxlots_oregon_city.geojson", ping_host="maps.orcity.org"),
                _layer("Hazards & Flood", "hazards_flood_oregon_city", "MapServer", "Active",
                       "100yr/500yr floodplain, floodway, landslides, geologic hazards, slope categories, riparian buffer zone.",
                       cache_file="oregon_city/hazards_flood_oregon_city.geojson", ping_host="maps.orcity.org"),
                _layer("Urban Renewal District", "urban_renewal_oregon_city", "MapServer", "Active",
                       "Urban renewal district boundary.",
                       cache_file="oregon_city/urban_renewal_oregon_city.geojson", ping_host="maps.orcity.org"),
                _layer("Enterprise Zones", "enterprise_zone_oregon_city", "MapServer", "Active",
                       "Enterprise zone polygons.",
                       cache_file="oregon_city/enterprise_zone_oregon_city.geojson", ping_host="maps.orcity.org"),
            ],
        },
        {
            "id": "local_gladstone", "title": "Local GIS — Gladstone",
            "provider": "maps.orcity.org · Hosted on Oregon City ArcGIS Enterprise",
            "layers": [
                _layer("Zoning", "zoning_gladstone", "MapServer", "Active",
                       "Gladstone_LandUseAndPlanning layer 7. Same service: comp plan (6), urban renewal (5), multifamily housing (3), vacant lands (2).",
                       cache_file="gladstone/zoning_gladstone.geojson", ping_host="maps.orcity.org"),
                _layer("City Limits", "city_limits_gladstone", "MapServer", "Active",
                       "Jurisdiction boundary.",
                       cache_file="gladstone/city_limits_gladstone.geojson", ping_host="maps.orcity.org"),
                _layer("Hazards & Flood", "hazards_flood_gladstone", "MapServer", "Active",
                       "FEMA floodplain, landslide, and geologic hazard layers.",
                       cache_file="gladstone/hazards_flood_gladstone.geojson", ping_host="maps.orcity.org"),
                _layer("Natural Resources", "natural_resources_gladstone", "MapServer", "Active",
                       "Streams and natural resource areas.",
                       cache_file="gladstone/natural_resources_gladstone.geojson", ping_host="maps.orcity.org"),
                _layer("Multifamily Housing", "multifamily_housing_gladstone", "MapServer", "Active",
                       "Existing MF housing stock inventory.",
                       cache_file="gladstone/multifamily_housing_gladstone.geojson", ping_host="maps.orcity.org"),
            ],
        },
        {
            "id": "local_lake_oswego", "title": "Local GIS — Lake Oswego",
            "provider": "maps.ci.oswego.or.us · Self-hosted ArcGIS Enterprise (v12)",
            "layers": [
                _layer("Zoning", "zoning_lake_oswego", "MapServer", "Active",
                       "Layers_Geocortex layer 68. Also: comp plan (69), design districts (58), neighborhood overlays (60), Willamette River Greenway mgmt district (62).",
                       cache_file="lake_oswego/zoning_lake_oswego.geojson", ping_host="maps.ci.oswego.or.us"),
                _layer("City Limits", "city_limits_lake_oswego", "MapServer", "Active",
                       "City boundary (Layers_Geocortex layer 1).",
                       cache_file="lake_oswego/city_limits_lake_oswego.geojson", ping_host="maps.ci.oswego.or.us"),
                _layer("Sensitive Lands", "sensitive_lands_lake_oswego", "MapServer", "Active",
                       "Layer 57 = Sensitive Lands polygons. Also: streams (55), wetland (200), 50ft riparian protection area (308).",
                       cache_file="lake_oswego/sensitive_lands_lake_oswego.geojson", ping_host="maps.ci.oswego.or.us"),
                _layer("FEMA Flood / Hazards", "fema_flood_lake_oswego", "MapServer", "Active",
                       "FEMA (17), 1996 flood level (18), soils (19), fault (20), shallow/deep landslide susceptibility (22-23).",
                       cache_file="lake_oswego/fema_flood_lake_oswego.geojson", ping_host="maps.ci.oswego.or.us"),
                _layer("Urban Renewal Districts", "urban_renewal_lake_oswego", "MapServer", "Active",
                       "East End URA (layer 10) and Lake Grove URA (layer 11).",
                       cache_file="lake_oswego/urban_renewal_lake_oswego.geojson", ping_host="maps.ci.oswego.or.us"),
            ],
        },
        {
            "id": "local_west_linn", "title": "Local GIS — West Linn",
            "provider": "geo.westlinnoregon.gov · Self-hosted ArcGIS Enterprise (v10.9)",
            "layers": [
                _layer("Zoning", "zoning_west_linn", "MapServer", "Active",
                       "ZoningComPlan layer 8 + comp plan (10). Max 2,000 records.",
                       cache_file="west_linn/zoning_west_linn.geojson", ping_host="geo.westlinnoregon.gov"),
                _layer("Wetland Inventory", "wetlands_west_linn", "MapServer", "Active",
                       "WetlandInventory MapServer layers 0-1.",
                       cache_file="west_linn/wetlands_west_linn.geojson", ping_host="geo.westlinnoregon.gov"),
                _layer("FEMA Flood Hazard", "fema_flood_west_linn", "MapServer", "Active",
                       "FEMA Flood Hazard Zones (2020), layer 1.",
                       cache_file="west_linn/fema_flood_west_linn.geojson", ping_host="geo.westlinnoregon.gov"),
                _layer("Habitat Conservation Area", "habitat_conservation_west_linn", "MapServer", "Active",
                       "Verified HCA polygons.",
                       cache_file="west_linn/habitat_conservation_west_linn.geojson", ping_host="geo.westlinnoregon.gov"),
                _layer("Riparian Corridor", "riparian_corridor_west_linn", "MapServer", "Active",
                       "Riparian Corridor Inventory polygons.",
                       cache_file="west_linn/riparian_corridor_west_linn.geojson", ping_host="geo.westlinnoregon.gov"),
                _layer("Regulatory Overlays", "regulatory_zones_west_linn", "MapServer", "Active",
                       "Willamette Falls Drive Commercial Design District, Willamette Historic District (local + National Register).",
                       cache_file="west_linn/regulatory_zones_west_linn.geojson", ping_host="geo.westlinnoregon.gov"),
            ],
        },
        {
            "id": "local_tualatin", "title": "Local GIS — Tualatin",
            "provider": "tualgis.ci.tualatin.or.us · Self-hosted ArcGIS Enterprise (v10.91)",
            "layers": [
                _layer("Zoning / Planning Districts", "zoning_tualatin", "MapServer", "Active",
                       "LandusePlanningExplorer layers 6-7. Zone code field: PLANDIST.CZONE (e.g. CO, RH, IN). Max 1,000 records.",
                       cache_file="tualatin/zoning_tualatin.geojson", ping_host="tualgis.ci.tualatin.or.us"),
                _layer("City Limits", "city_limits_tualatin", "MapServer", "Active",
                       "TualatinBoundaries layer 0.",
                       cache_file="tualatin/city_limits_tualatin.geojson", ping_host="tualgis.ci.tualatin.or.us"),
                _layer("Environmental Overlays", "environmental_tualatin", "MapServer", "Active",
                       "EnvironmentalExplorer: wetlands (24), 100yr floodplain (9), floodway (11), natural resources protection overlay (23), 50ft stream buffer (26), slope ≥25% (3).",
                       cache_file="tualatin/environmental_tualatin.geojson", ping_host="tualgis.ci.tualatin.or.us"),
                _layer("Urban Renewal Areas", "urban_renewal_tualatin", "MapServer", "Active",
                       "Core Opportunity and Reinvestment Area, Leveton TID, SW & Basalt Creek URAs.",
                       cache_file="tualatin/urban_renewal_tualatin.geojson", ping_host="tualgis.ci.tualatin.or.us"),
            ],
        },
        {
            "id": "local_wilsonville", "title": "Local GIS — Wilsonville",
            "provider": "gis.wilsonvillemaps.com · Self-hosted ArcGIS Enterprise (v11.5)",
            "layers": [
                _layer("Zoning", "zoning_wilsonville", "FeatureServer", "Active",
                       "Map___WilsonvilleMaps_MIL1 layer 40. ZONE_CODE field (OTR, PDC, PDI, R, V, Future Development).",
                       cache_file="wilsonville/zoning_wilsonville.geojson", ping_host="gis.wilsonvillemaps.com"),
                _layer("City Limits", "city_limits_wilsonville", "FeatureServer", "Active",
                       "Layer 2. Also: UGB (0), county boundary (1).",
                       cache_file="wilsonville/city_limits_wilsonville.geojson", ping_host="gis.wilsonvillemaps.com"),
                _layer("Taxlots", "taxlots_wilsonville", "FeatureServer", "Active",
                       "County assessor taxlots covering Clackamas + Washington County portions (layer 11).",
                       cache_file="wilsonville/taxlots_wilsonville.geojson", ping_host="gis.wilsonvillemaps.com"),
                _layer("Natural Resources / Environmental", "environmental_wilsonville", "FeatureServer", "Active",
                       "Map___NaturalResources: significant wetlands (1099), non-significant (1090), upland habitat (1080), FEMA 100yr floodplain (1107), 1996 flood inundation (1030), streams (1050-1060).",
                       cache_file="wilsonville/environmental_wilsonville.geojson", ping_host="gis.wilsonvillemaps.com"),
                _layer("SROZ — Significant Resource Overlay Zone", "sroz_wilsonville", "FeatureServer", "Active",
                       "Primary environmental overlay. Layer 60 = SROZ polygon, layer 70 = SROZ Impact Area.",
                       cache_file="wilsonville/sroz_wilsonville.geojson", ping_host="gis.wilsonvillemaps.com"),
                _layer("Urban Renewal Areas", "urban_renewal_wilsonville", "MapServer", "Active",
                       "Map___URA: URA_Coffee, URA_East, URA_TWIST, URA_West, URA_WIN.",
                       cache_file="wilsonville/urban_renewal_wilsonville.geojson", ping_host="gis.wilsonvillemaps.com"),
            ],
        },
        {
            "id": "local_canby_johnson_city", "title": "Local GIS — Canby / Johnson City",
            "provider": "DLCD statewide fallback — no public REST service",
            "layers": [
                _layer("Canby Zoning", "—", "DLCD Fallback", "Planned",
                       "No public ArcGIS REST service found. Zoning via DLCD statewide layer (ownerName='Canby'). Contact Canby Planning (503-266-7001) for direct shapefile/REST access."),
                _layer("Johnson City Zoning", "—", "DLCD Fallback", "Planned",
                       "0.07 sq mi micro-municipality (single mobile home park). No city GIS program. DLCD statewide is the only queryable source (ownerName='Johnson City')."),
            ],
        },
    ]

    # ── Parallel host liveness checks ──────────────────────────────────────
    _PING_HOST_URLS: dict[str, str] = {
        "services2.arcgis.com":     "https://services2.arcgis.com",
        "services8.arcgis.com":     "https://services8.arcgis.com",
        "services1.arcgis.com":     "https://services1.arcgis.com",
        "services.arcgis.com":      "https://services.arcgis.com",
        "services5.arcgis.com":     "https://services5.arcgis.com",
        "services6.arcgis.com":     "https://services6.arcgis.com",
        "services7.arcgis.com":     "https://services7.arcgis.com",
        "gis.odot.state.or.us":        "https://gis.odot.state.or.us",
        "gis.greshamoregon.gov":       "https://gis.greshamoregon.gov",
        "maps.troutdaleoregon.gov":    "https://maps.troutdaleoregon.gov",
        "maps.orcity.org":             "https://maps.orcity.org",
        "maps.ci.oswego.or.us":        "https://maps.ci.oswego.or.us",
        "geo.westlinnoregon.gov":      "https://geo.westlinnoregon.gov",
        "tualgis.ci.tualatin.or.us":   "https://tualgis.ci.tualatin.or.us",
        "gis.wilsonvillemaps.com":     "https://gis.wilsonvillemaps.com",
    }
    unique_hosts = {layer["ping_host"] for g in groups for layer in g["layers"] if layer["ping_host"]}

    async def _ping(host: str) -> tuple[str, bool]:
        url = _PING_HOST_URLS.get(host, f"https://{host}")
        ok = await _direct_live_ping(url, timeout_seconds=5.0)
        return host, ok

    ping_pairs = await asyncio.gather(*[_ping(h) for h in unique_hosts])
    host_ok: dict[str, bool] = dict(ping_pairs)

    # ── File mtime → last pull timestamp ───────────────────────────────────
    _CACHE_ROOT = Path("/app/data/gis_cache")
    heartbeat_ts = datetime.now(_PACIFIC).strftime("%Y-%m-%d %H:%M PT")

    for group in groups:
        for layer in group["layers"]:
            cf = layer.get("cache_file", "")
            if cf:
                fpath = _CACHE_ROOT / cf
                if fpath.exists():
                    mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=_PACIFIC)
                    layer["last_pull"] = mtime.strftime("%Y-%m-%d %H:%M PT")
                else:
                    layer["last_pull"] = "Not cached"
            else:
                layer["last_pull"] = "—"

            h = layer.get("ping_host", "")
            if h:
                layer["heartbeat_ok"] = host_ok.get(h, False)
                layer["heartbeat_ts"] = heartbeat_ts
            else:
                layer["heartbeat_ok"] = None  # no check applicable
                layer["heartbeat_ts"] = "—"

    return templates.TemplateResponse(
        request,
        "settings_data_sources.html",
        {
            "groups": groups,
            "heartbeat_ts": heartbeat_ts,
            **_base_ctx(user, dedup_count, "", address_issues_count),
        },
    )


@router.post("/ui/admin/rlis-refresh")
async def admin_rlis_refresh(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> JSONResponse:
    """
    Dispatch rlis_quarterly_refresh_task to the Celery default queue.
    Assumes rlis_delta.py has already been run (cache + sidecar are fresh).
    Returns the Celery task ID.
    """
    from app.tasks.parcel_seed import rlis_quarterly_refresh_task
    user = await _get_user(session, request)
    _require_settings_owner(user)
    result = rlis_quarterly_refresh_task.delay()
    return JSONResponse({"task_id": result.id, "status": "queued"})


@router.post("/ui/admin/seed-rlis")
async def admin_seed_rlis(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> JSONResponse:
    """Dispatch seed_rlis_task — re-seeds parcels from the cached taxlot GeoJSON."""
    from app.tasks.parcel_seed import seed_rlis_task
    user = await _get_user(session, request)
    _require_settings_owner(user)
    result = seed_rlis_task.delay()
    return JSONResponse({"task_id": result.id, "status": "queued"})


@router.post("/ui/admin/backfill-listing-buckets")
async def admin_backfill_listing_buckets(
    session: DBSession,
) -> JSONResponse:
    """Classify all ScrapedListings that have no priority_bucket yet.
    Uses zoning/county/property_type from the linked Parcel if available,
    otherwise falls back to listing fields."""
    from app.utils.priority import classify as _classify
    from app.models.parcel import Parcel

    stmt = (
        select(ScrapedListing)
        .where(ScrapedListing.priority_bucket.is_(None))
        .options(selectinload(ScrapedListing.broker))
    )
    listings = list((await session.execute(stmt)).scalars())
    updated = 0
    for listing in listings:
        parcel: Parcel | None = None
        if listing.parcel_id:
            parcel = await session.get(Parcel, listing.parcel_id)
        elif listing.apn:
            parcel = (await session.execute(
                select(Parcel).where(Parcel.apn == listing.apn.split(",")[0].strip().upper())
            )).scalar_one_or_none()

        bucket = _classify(
            zoning_code=(parcel.zoning_code if parcel else None) or listing.zoning,
            zoning_description=(parcel.zoning_description if parcel else None),
            county=(parcel.county if parcel else None) or listing.county,
            jurisdiction=(parcel.jurisdiction if parcel else None) or listing.city,
            current_use=(parcel.current_use if parcel else None),
            property_type=listing.property_type,
        )
        listing.priority_bucket = bucket.value
        updated += 1

    await session.commit()
    return JSONResponse({"updated": updated})


@router.post("/ui/admin/classify-parcels")
async def admin_classify_parcels(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> JSONResponse:
    """Dispatch classify_parcels_task — classifies parcels with data but no bucket."""
    from app.tasks.parcel_seed import classify_parcels_task
    user = await _get_user(session, request)
    _require_settings_owner(user)
    result = classify_parcels_task.delay()
    return JSONResponse({"task_id": result.id, "status": "queued"})


@router.get("/deals/new", response_class=HTMLResponse)
async def deals_new_page(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    opp_id: str = Query(default=""),
) -> HTMLResponse:
    """Full-page wizard for creating a new deal (name + type)."""
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    ctx = _base_ctx(user, dedup_count, "deals")
    # Pre-populate name and pass opp_id so the form can link to an existing opportunity.
    opp_name = ""
    if opp_id:
        try:
            _opp = await session.get(Opportunity, UUID(opp_id))
            if _opp:
                opp_name = _opp.name
        except ValueError:
            opp_id = ""
    ctx["opp_id"] = opp_id
    ctx["opp_name"] = opp_name
    return templates.TemplateResponse(request, "deals_new.html", ctx)


@router.get("/deals", response_class=HTMLResponse)
async def deals_page(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    q: str = Query(default=""),
    status: str = Query(default=""),
    type: str = Query(default=""),
    model: str = Query(default=""),
    include_archived: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)

    archived = include_archived == "1"
    loaded_deals = await _load_deals(session, status, type, model, q, archived)
    deals = [_build_deal_row(d) for d in loaded_deals]

    total_result = await session.execute(
        select(func.count()).select_from(Deal).where(Deal.status != DealStatus.archived)
    )
    total_count = int(total_result.scalar_one())

    archived_result = await session.execute(
        select(func.count()).select_from(Deal).where(Deal.status == DealStatus.archived)
    )
    archived_count = int(archived_result.scalar_one())

    irr_values = [d["irr"] for d in deals if d["irr"] is not None]
    avg_irr = sum(irr_values) / len(irr_values) if irr_values else None
    equity_values = [d["noi"] for d in deals if d.get("noi") is not None]  # use NOI as pipeline proxy
    # pipeline_value = total equity required across deals with outputs
    equity_req_values: list[float] = []
    for loaded_deal in loaded_deals:
        scenario = _primary_scenario(loaded_deal)
        if scenario and scenario.operational_outputs and scenario.operational_outputs.equity_required is not None:
            equity_req_values.append(float(scenario.operational_outputs.equity_required))
    pipeline_value = sum(equity_req_values) if equity_req_values else None

    return templates.TemplateResponse(
        request,
        "deals.html",
        {
            "deals": deals,
            "total_count": total_count,
            "archived_count": archived_count,
            "include_archived": archived,
            "q": q,
            "status": status,
            "deal_type": type,
            "model_filter": model,
            "stats": {
                "pipeline_count": total_count,
                "avg_irr": avg_irr,
                "pipeline_value": pipeline_value,
                "no_model_count": sum(1 for d in deals if not d["primary_model_name"]),
            },
            **_base_ctx(user, dedup_count, "deals"),
        },
    )


@router.get("/ui/deals/rows", response_class=HTMLResponse)
async def deals_rows(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    status: str = Query(default=""),
    type: str = Query(default=""),
    model: str = Query(default=""),
    include_archived: str = Query(default=""),
) -> HTMLResponse:
    archived = include_archived == "1"
    loaded_deals = await _load_deals(session, status, type, model, q, archived)
    deals = [_build_deal_row(d) for d in loaded_deals]
    return templates.TemplateResponse(request, "partials/deals_rows.html", {"deals": deals})


def _seed_milestones(project: Project, deal_type: ProjectType) -> list[Milestone]:
    """Return unseeded Milestone rows for a new dev Project based on deal_type defaults."""
    durations = DEFAULT_DURATIONS.get(deal_type.value, {})
    milestones = []
    for seq, (type_str, duration) in enumerate(durations.items(), start=1):
        try:
            mtype = MilestoneType(type_str)
        except ValueError:
            continue
        milestones.append(Milestone(
            project_id=project.id,
            milestone_type=mtype,
            duration_days=duration,
            sequence_order=seq,
        ))
    return milestones


@router.post("/ui/deals/create", response_class=HTMLResponse)
async def create_deal(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    new: str = Query(default=""),
) -> HTMLResponse:
    """Quick-create: Opportunity + Deal + default dev Project. Redirects to model builder.
    If opportunity_id is provided in the form, links to an existing Opportunity instead of
    creating a new one (used when coming from the opportunity detail page)."""
    form = await request.form()
    name = str(form.get("name", "")).strip()
    deal_type_raw = str(form.get("deal_type", "acquisition_minor_reno")).strip()
    org_id_raw = str(form.get("org_id", "")).strip()
    opp_id_raw = str(form.get("opportunity_id", "")).strip()

    if not name:
        return HTMLResponse("<p class='text-muted'>Deal name is required.</p>", status_code=400)

    user = await _get_user(session, request)

    # Resolve org_id: form value → user's org → first org
    org_id = None
    if org_id_raw:
        try:
            org_id = UUID(org_id_raw)
        except ValueError:
            pass
    if org_id is None and user is not None:
        org_id = user.org_id
    if org_id is None:
        from app.models.org import Organization
        first_org = (await session.execute(select(Organization).limit(1))).scalar_one_or_none()
        if first_org is None:
            return HTMLResponse("<p class='text-muted'>No organization found. Create one first.</p>", status_code=400)
        org_id = first_org.id

    try:
        deal_type = ProjectType(deal_type_raw)
    except ValueError:
        deal_type = ProjectType.acquisition_minor_reno

    # If an existing opportunity ID was passed (from opp detail page), link to it instead.
    opportunity: Opportunity | None = None
    if opp_id_raw:
        try:
            opportunity = await session.get(
                Opportunity, UUID(opp_id_raw),
                options=[
                    selectinload(Opportunity.opportunity_buildings),
                    selectinload(Opportunity.scraped_listings),
                ],
            )
        except ValueError:
            pass

    _opportunity_is_new = False
    if opportunity is None:
        _opportunity_is_new = True
        opportunity = Opportunity(
            org_id=org_id,
            name=name,
            status=OpportunityStatus.active,
            created_by_user_id=user.id if user else None,
        )
        session.add(opportunity)
        await session.flush()
    else:
        # Ensure ProjectParcel exists for any parcel linked via scraped listing.
        for _sl in opportunity.scraped_listings:
            _parcel_id = _sl.parcel_id
            if _parcel_id is None and (_sl.apn or _sl.address_normalized):
                try:
                    from app.scrapers.parcel_enrichment import enrich_parcel as _enrich
                    _p = await _enrich(session, address=_sl.address_normalized or _sl.address_raw, apn=_sl.apn)
                    if _p is not None:
                        _parcel_id = _p.id
                        _sl.parcel_id = _parcel_id
                except Exception:
                    pass
            if _parcel_id is not None:
                _existing = (await session.execute(
                    select(ProjectParcel).where(
                        ProjectParcel.project_id == opportunity.id,
                        ProjectParcel.parcel_id == _parcel_id,
                    )
                )).scalar_one_or_none()
                if _existing is None:
                    session.add(ProjectParcel(
                        project_id=opportunity.id,
                        parcel_id=_parcel_id,
                        relationship_type=ProjectParcelRelationship.unchanged,
                    ))
        await session.flush()

    # New architecture: top-level Deal → DealOpportunity link → Scenario (financial plan)
    top_deal = Deal(
        org_id=org_id,
        name=name,
        created_by_user_id=user.id if user else None,
    )
    session.add(top_deal)
    await session.flush()

    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))

    scenario = DealModel(
        deal_id=top_deal.id,
        name="Base Case",
        project_type=deal_type,
        version=1,
        is_active=True,
        created_by_user_id=user.id if user else None,
    )
    session.add(scenario)
    await session.flush()

    dev_project = Project(
        scenario_id=scenario.id,
        opportunity_id=opportunity.id,
        name="Default Project",
        deal_type=deal_type,
    )
    session.add(dev_project)
    await session.flush()

    await _auto_assign_opportunity_to_project(opportunity, dev_project, session)
    for milestone in _seed_milestones(dev_project, deal_type):
        session.add(milestone)

    # Auto-seed the Acquisition use line from the linked opportunity.
    # Price: first scraped listing's asking_price if available, else 0 (user fills in later).
    # Label: "{opportunity name} - Acquisition"
    acq_price = 0
    if not _opportunity_is_new and opportunity.scraped_listings:
        sl = opportunity.scraped_listings[0]
        if sl.asking_price is not None:
            acq_price = sl.asking_price
    session.add(UseLine(
        project_id=dev_project.id,
        label=f"{opportunity.name} - Acquisition",
        phase=UseLinePhase.acquisition,
        milestone_key="close",
        amount=acq_price,
        timing_type="first_day",
    ))

    await session.commit()

    redirect_url = f"/models/{scenario.id}/builder" + ("?new=1" if new == "1" else "")
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/deals/{deal_id}", response_class=HTMLResponse)
async def deal_detail(
    request: Request,
    deal_id: UUID,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    tab: str = Query(default="overview"),
    error: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)

    deal = await session.get(
        Deal,
        deal_id,
        options=[
            selectinload(Deal.scenarios).selectinload(DealModel.operational_outputs),
            selectinload(Deal.scenarios).selectinload(DealModel.projects).selectinload(Project.milestones),
            selectinload(Deal.deal_opportunities)
                .selectinload(DealOpportunity.opportunity)
                .selectinload(Opportunity.project_parcels)
                .selectinload(ProjectParcel.parcel),
            selectinload(Deal.deal_opportunities)
                .selectinload(DealOpportunity.opportunity)
                .selectinload(Opportunity.scraped_listings),
        ],
    )
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    opportunity = _first_opportunity(deal)

    # Collect all buildings linked via opportunity's scraped_listings
    building_ids = []
    if opportunity:
        building_ids = [l.property_id for l in opportunity.scraped_listings if l.property_id]
    buildings = []
    if building_ids:
        bldg_stmt = (
            select(Building)
            .options(
                selectinload(Building.scraped_listing)
                    .selectinload(ScrapedListing.broker)
                    .selectinload(Broker.brokerage),
                selectinload(Building.parcel),
            )
            .where(Building.id.in_(building_ids))
        )
        bldg_result = await session.execute(bldg_stmt)
        buildings = [_build_building_row(b) for b in bldg_result.scalars()]

    # Parcels linked to the primary opportunity
    parcels = []
    if opportunity:
        parcels = [_build_parcel_row(pp.parcel) for pp in opportunity.project_parcels if pp.parcel]

    # Financial models (Scenarios) for this Deal
    models = []
    for scenario in deal.scenarios:
        out = scenario.operational_outputs
        type_key = str(scenario.project_type.value if hasattr(scenario.project_type, "value") else scenario.project_type)
        first_proj = scenario.projects[0] if scenario.projects else None
        models.append({
            "id": str(scenario.id),
            "name": scenario.name,
            "version": scenario.version,
            "is_active": scenario.is_active,
            "type_display": _TYPE_DISPLAY.get(type_key, type_key),
            "project_name": first_proj.name if first_proj else "—",
            "project_id": str(first_proj.id) if first_proj else None,
            "noi": float(out.noi_stabilized) if out and out.noi_stabilized is not None else None,
            "irr": float(out.project_irr_levered) if out and out.project_irr_levered is not None else None,
            "equity_required": float(out.equity_required) if out and out.equity_required is not None else None,
            "created_at_fmt": scenario.created_at.strftime("%b %-d, %Y") if scenario.created_at else None,
        })
    models.sort(key=lambda m: (0 if m["is_active"] else 1, -m["version"]))

    # Build Gantt data from milestones across all scenarios/projects
    gantt_data = _build_gantt_rows(deal)

    # Status comes from the linked Opportunity (pipeline stage)
    status_key = str(opportunity.status.value if opportunity and hasattr(opportunity.status, "value") else (opportunity.status if opportunity else "active"))
    status_display, status_badge = _STATUS_DISPLAY.get(status_key, ("Unknown", "badge-gray"))

    return templates.TemplateResponse(
        request,
        "deal_detail.html",
        {
            "deal": deal,
            "deal_id": str(deal.id),
            "deal_name": deal.name,
            "opp": opportunity,
            "opp_id": str(opportunity.id) if opportunity else "",
            "opp_name": opportunity.name if opportunity else "",
            "status_key": status_key,
            "status_display": status_display,
            "status_badge": status_badge,
            "buildings": buildings,
            "parcels": parcels,
            "models": models,
            "gantt_data": gantt_data,
            "active_tab": tab,
            "primary_model_id": models[0]["id"] if models else None,
            "flash_error": error,
            **_base_ctx(user, dedup_count, "deals"),
        },
    )


@router.post("/ui/deals/{deal_id}/archive", response_class=HTMLResponse)
async def archive_deal(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    deal = await session.get(Deal, deal_id)
    if deal is not None:
        deal.status = DealStatus.archived
        await session.flush()
    loaded_deals = await _load_deals(session)
    deals = [_build_deal_row(d) for d in loaded_deals]
    return templates.TemplateResponse(request, "partials/deals_rows.html", {"deals": deals})


@router.post("/ui/deals/{deal_id}/update", response_class=HTMLResponse)
async def update_deal(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    form = await request.form()
    name = str(form.get("name", "")).strip()
    status_raw = str(form.get("status", "hypothetical")).strip()

    deal = await session.get(
        Deal,
        deal_id,
        options=[
            selectinload(Deal.deal_opportunities).selectinload(DealOpportunity.opportunity),
        ],
    )
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>", status_code=404)

    if name:
        deal.name = name
    # Pipeline stage is stored on the linked Opportunity
    opp = _first_opportunity(deal)
    if opp is not None:
        try:
            opp.status = OpportunityStatus(status_raw)
        except ValueError:
            pass
    await session.commit()
    return RedirectResponse(url=f"/deals/{deal_id}", status_code=303)


@router.post("/ui/deals/create-model", response_class=HTMLResponse)
async def create_model_for_deal(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    """Create a new financial model (Deal + Project) for an existing Opportunity."""
    form = await request.form()
    opp_id_raw = str(form.get("opportunity_id", "")).strip()
    name = str(form.get("name", "Base Case")).strip()
    deal_type_raw = str(form.get("deal_type", "acquisition_minor_reno")).strip()

    try:
        opp_id = UUID(opp_id_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid opportunity ID.</p>", status_code=400)

    opportunity = await session.get(Opportunity, opp_id)
    if opportunity is None:
        return HTMLResponse("<p class='text-muted'>Opportunity not found.</p>", status_code=404)

    user = await _get_user(session, request)
    try:
        deal_type = ProjectType(deal_type_raw)
    except ValueError:
        deal_type = ProjectType.acquisition_minor_reno

    # Find or create a top-level Deal for this Opportunity
    existing_top_deal = (await session.execute(
        select(Deal)
        .join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
        .where(DealOpportunity.opportunity_id == opp_id)
        .limit(1)
    )).scalar_one_or_none()

    if existing_top_deal is None:
        existing_top_deal = Deal(
            org_id=opportunity.org_id,
            name=name or "Base Case",
            created_by_user_id=user.id if user else None,
        )
        session.add(existing_top_deal)
        await session.flush()
        session.add(DealOpportunity(deal_id=existing_top_deal.id, opportunity_id=opp_id))

    # Count existing scenarios for version numbering
    existing_version = int((await session.execute(
        select(func.count()).select_from(DealModel).where(DealModel.deal_id == existing_top_deal.id)
    )).scalar_one())

    scenario = DealModel(
        deal_id=existing_top_deal.id,
        name=name or "Base Case",
        project_type=deal_type,
        version=existing_version + 1,
        is_active=True,
        created_by_user_id=user.id if user else None,
    )
    session.add(scenario)
    await session.flush()

    dev_project = Project(
        scenario_id=scenario.id,
        opportunity_id=opp_id,
        name="Default Project",
        deal_type=deal_type,
    )
    session.add(dev_project)
    await session.flush()

    for milestone in _seed_milestones(dev_project, deal_type):
        session.add(milestone)
    await session.commit()

    return RedirectResponse(url=f"/models/{scenario.id}/builder", status_code=303)


@router.post("/ui/deals/{deal_id}/link-parcel", response_class=HTMLResponse)
async def link_parcel_to_deal(
    request: Request,
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    form = await request.form()
    apn = str(form.get("apn", "")).strip()
    rel_raw = str(form.get("relationship", "unchanged")).strip()

    # Find parcel by APN
    parcel_result = await session.execute(select(Parcel).where(Parcel.apn == apn))
    parcel = parcel_result.scalar_one_or_none()
    if parcel is None:
        return RedirectResponse(
            url=f"/deals/{deal_id}?tab=parcels&error=parcel_not_found",
            status_code=303,
        )

    # Get the primary opportunity — parcels are linked to Opportunity, not Deal
    deal = await session.get(
        Deal, deal_id,
        options=[selectinload(Deal.deal_opportunities).selectinload(DealOpportunity.opportunity)],
    )
    opp = _first_opportunity(deal) if deal else None
    if opp is None:
        return RedirectResponse(url=f"/deals/{deal_id}?tab=parcels&error=no_opportunity", status_code=303)

    try:
        rel = ProjectParcelRelationship(rel_raw)
    except ValueError:
        rel = ProjectParcelRelationship.unchanged

    # Upsert: skip if already linked
    existing = await session.execute(
        select(ProjectParcel).where(
            ProjectParcel.project_id == opp.id,
            ProjectParcel.parcel_id == parcel.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        pp = ProjectParcel(
            project_id=opp.id,
            parcel_id=parcel.id,
            relationship_type=rel,
        )
        session.add(pp)
    await session.commit()

    return RedirectResponse(url=f"/deals/{deal_id}?tab=parcels", status_code=303)


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

def _build_building_row(prop: Building) -> dict:
    listing = prop.scraped_listing
    parcel = prop.parcel
    return {
        "id": str(prop.id),
        "name": prop.name,
        "address": listing.address_normalized if listing else (parcel.address_normalized if parcel else ""),
        "full_address": listing.address_normalized if listing else (parcel.address_normalized if parcel else ""),
        "sale_status": listing.status if listing else None,
        "source": listing.source if listing else None,
        "source_url": listing.source_url if listing else None,
        "unit_count": listing.units if listing else (parcel.unit_count if parcel else None),
        "building_sqft": float(listing.gba_sqft) if listing and listing.gba_sqft else (float(parcel.building_sqft) if parcel and parcel.building_sqft else None),
        "year_built": listing.year_built if listing else (parcel.year_built if parcel else None),
        "property_type": listing.property_type if listing else None,
        "asking_price": float(listing.asking_price) if listing and listing.asking_price else None,
        "cap_rate": float(listing.cap_rate) if listing and listing.cap_rate else None,
        "first_seen_at": listing.first_seen_at.strftime("%b %-d, %Y") if listing and listing.first_seen_at else None,
        "last_seen_at": listing.last_seen_at.strftime("%b %-d, %Y") if listing and listing.last_seen_at else None,
        "broker_name": f"{listing.broker.first_name} {listing.broker.last_name}".strip() if listing and listing.broker else None,
        "brokerage_name": listing.broker.brokerage.name if listing and listing.broker and listing.broker.brokerage else None,
        "broker_phone": listing.broker.phone if listing and listing.broker else None,
        "project_id": None,
        "project_name": None,
    }


# ── Opportunities ─────────────────────────────────────────────────────────────

@router.get("/opportunities", response_class=HTMLResponse)
async def opportunities_page(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    q: str = Query(default=""),
    status: str = Query(default=""),
    source: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    opps = await _query_opportunities(session, q=q, status=status, source=source)
    return templates.TemplateResponse(request, "opportunities.html", {
        "request": request, "opps": opps,
        "q": q, "status": status, "source": source,
        **_base_ctx(user, dedup_count, "opportunities"),
    })


@router.get("/ui/opportunities/rows", response_class=HTMLResponse)
async def opportunities_rows(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
    status: str = Query(default=""),
    source: str = Query(default=""),
) -> HTMLResponse:
    opps = await _query_opportunities(session, q=q, status=status, source=source)
    return templates.TemplateResponse(request, "partials/opportunities_rows.html", {
        "request": request, "opps": opps,
    })


async def _query_opportunities(
    session: AsyncSession,
    q: str = "",
    status: str = "",
    source: str = "",
) -> list:
    from sqlalchemy.orm import selectinload as _sl
    stmt = (
        select(Opportunity)
        .options(
            _sl(Opportunity.opportunity_buildings).selectinload(OpportunityBuilding.building),
            _sl(Opportunity.deal_opportunities),
        )
        .order_by(Opportunity.created_at.desc())
    )
    if status:
        stmt = stmt.where(Opportunity.status == status)
    else:
        stmt = stmt.where(Opportunity.status != OpportunityStatus.archived)
    if source:
        stmt = stmt.where(Opportunity.source == source)
    opps = list((await session.execute(stmt)).scalars().unique())
    if q:
        q_lower = q.lower()
        opps = [
            o for o in opps
            if q_lower in (o.name or "").lower()
            or any(
                q_lower in (ob.building.address_line1 or "").lower()
                or q_lower in (ob.building.city or "").lower()
                for ob in o.opportunity_buildings
            )
        ]
    return opps


# ── Opportunity creation wizard ────────────────────────────────────────────────

@router.get("/ui/opportunities/wizard", response_class=HTMLResponse)
async def opportunity_wizard_get(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    step: int = Query(default=1),
    opp_id: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    opp = None
    buildings: list[Building] = []
    if opp_id:
        try:
            opp = await session.get(Opportunity, UUID(opp_id))
            if opp:
                obs = list((await session.execute(
                    select(OpportunityBuilding)
                    .options(__import__('sqlalchemy.orm', fromlist=['selectinload']).selectinload(OpportunityBuilding.building))
                    .where(OpportunityBuilding.opportunity_id == UUID(opp_id))
                    .order_by(OpportunityBuilding.sort_order)
                )).scalars())
                buildings = [ob.building for ob in obs]
        except (ValueError, Exception):
            pass
    ctx = {
        "request": request, "step": step, "opp": opp,
        "opp_id": opp_id, "buildings": buildings,
        "deal_type": request.query_params.get("deal_type", ""),
        "opp_asking_price": "", "opp_notes": "",
        "deal_type_label": "",
        **_base_ctx(user, dedup_count, "opportunities"),
    }
    return templates.TemplateResponse(request, "opportunity_wizard.html", ctx)


@router.post("/ui/opportunities/wizard/step", response_class=HTMLResponse)
async def opportunity_wizard_step(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    form = await request.form()
    step = int(form.get("step", 1))
    opp_id_str = str(form.get("opp_id", "") or "")
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)

    _deal_type_labels = {
        "acquisition_minor_reno": "Acquisition",
        "acquisition_major_reno": "Value-Add",
        "acquisition_conversion": "Conversion",
        "new_construction": "New Construction",
    }

    if step == 1:
        # Create or update Opportunity
        name = str(form.get("name", "")).strip()
        deal_type = str(form.get("deal_type", "acquisition_major_reno"))
        opp_status = str(form.get("status", "hypothetical"))
        source = str(form.get("source", "manual"))
        asking_price_raw = str(form.get("asking_price", "") or "").replace(",", "").strip()
        notes = str(form.get("notes", "") or "").strip()

        if opp_id_str:
            try:
                opp = await session.get(Opportunity, UUID(opp_id_str))
            except ValueError:
                opp = None
        else:
            opp = None

        if opp is None:
            from app.models.org import Organization as _Org
            org = (await session.execute(select(_Org).limit(1))).scalar_one_or_none()
            if org is None:
                return HTMLResponse("No organization found", status_code=400)
            opp = Opportunity(
                org_id=org.id,
                name=name,
                status=opp_status,
                source=source,
                source_type="manual",
                created_by_user_id=user.id if user else None,
            )
            session.add(opp)
        else:
            opp.name = name
            opp.status = opp_status
            opp.source = source

        await session.commit()
        await session.refresh(opp)
        opp_id_str = str(opp.id)

        # Load buildings for step 2
        obs = list((await session.execute(
            select(OpportunityBuilding)
            .options(__import__('sqlalchemy.orm', fromlist=['selectinload']).selectinload(OpportunityBuilding.building))
            .where(OpportunityBuilding.opportunity_id == opp.id)
            .order_by(OpportunityBuilding.sort_order)
        )).scalars())
        buildings = [ob.building for ob in obs]

        return templates.TemplateResponse(request, "opportunity_wizard.html", {
            "request": request, "step": 2, "opp": opp,
            "opp_id": opp_id_str, "buildings": buildings,
            "deal_type": deal_type,
            "opp_asking_price": asking_price_raw,
            "opp_notes": notes,
            "deal_type_label": _deal_type_labels.get(deal_type, deal_type),
            **_base_ctx(user, dedup_count, "opportunities"),
        })

    elif step == 2:
        # Save buildings
        opp = await session.get(Opportunity, UUID(opp_id_str)) if opp_id_str else None
        if opp is None:
            return HTMLResponse("Opportunity not found", status_code=400)

        # Parse building index list
        idxs_raw = form.getlist("building_idx[]")
        # Remove existing OpportunityBuilding rows for clean re-save
        existing_obs = list((await session.execute(
            select(OpportunityBuilding).where(OpportunityBuilding.opportunity_id == opp.id)
        )).scalars())
        for ob in existing_obs:
            await session.delete(ob)
        await session.flush()

        buildings_saved: list[Building] = []
        for sort_i, idx in enumerate(idxs_raw):
            building_id_str = str(form.get(f"building_id_{idx}", "") or "").strip()
            address = str(form.get(f"b_address_{idx}", "") or "").strip()
            city = str(form.get(f"b_city_{idx}", "") or "").strip()
            state = str(form.get(f"b_state_{idx}", "") or "").strip()
            zip_code = str(form.get(f"b_zip_{idx}", "") or "").strip()

            def _int(v: str) -> int | None:
                try: return int(v) if v else None
                except ValueError: return None
            def _dec(v: str):
                try: return Decimal(v.replace(",", "")) if v else None
                except Exception: return None

            units = _int(str(form.get(f"b_units_{idx}", "") or ""))
            sqft = _dec(str(form.get(f"b_sqft_{idx}", "") or ""))
            year = _int(str(form.get(f"b_year_{idx}", "") or ""))
            prop_type = str(form.get(f"b_type_{idx}", "") or "").strip() or None
            cur_use = str(form.get(f"b_use_{idx}", "") or "").strip() or None
            notes = str(form.get(f"b_notes_{idx}", "") or "").strip() or None

            if not address and not units:
                continue  # skip blank rows

            # Create or update building
            b: Building | None = None
            if building_id_str:
                try:
                    b = await session.get(Building, UUID(building_id_str))
                except ValueError:
                    b = None

            if b is None:
                b = Building(
                    name=address or f"Building {sort_i + 1}",
                    created_by_user_id=user.id if user else None,
                )
                session.add(b)

            b.address_line1 = address or b.address_line1
            b.city = city or b.city
            b.state = state or b.state
            b.zip_code = zip_code or b.zip_code
            b.unit_count = units if units is not None else b.unit_count
            b.building_sqft = sqft if sqft is not None else b.building_sqft
            b.year_built = year if year is not None else b.year_built
            b.property_type = prop_type or b.property_type
            b.current_use = cur_use or b.current_use
            b.notes = notes or b.notes
            b.name = address or b.name

            await session.flush()
            buildings_saved.append(b)

            ob = OpportunityBuilding(
                opportunity_id=opp.id,
                building_id=b.id,
                sort_order=sort_i,
            )
            session.add(ob)

        await session.commit()

        deal_type = str(form.get("deal_type", "acquisition_major_reno"))
        asking_price_raw = str(form.get("asking_price", "") or "")
        opp_notes = str(form.get("notes", "") or "")

        return templates.TemplateResponse(request, "opportunity_wizard.html", {
            "request": request, "step": 3, "opp": opp,
            "opp_id": opp_id_str, "buildings": buildings_saved,
            "deal_type": deal_type,
            "opp_asking_price": asking_price_raw,
            "opp_notes": opp_notes,
            "deal_type_label": _deal_type_labels.get(deal_type, deal_type),
            **_base_ctx(user, dedup_count, "opportunities"),
        })

    return HTMLResponse("Invalid step", status_code=400)


@router.post("/ui/opportunities/wizard/complete")
async def opportunity_wizard_complete(
    request: Request,
    session: DBSession,
) -> Response:
    """Finalize opportunity creation — redirect to opportunity detail."""
    form = await request.form()
    opp_id_str = str(form.get("opp_id", "") or "")
    if not opp_id_str:
        return HTMLResponse("Missing opp_id", status_code=400)
    return RedirectResponse(url=f"/opportunities/{opp_id_str}", status_code=303)


@router.get("/opportunities/{opp_id}", response_class=HTMLResponse)
async def opportunity_detail(
    request: Request,
    opp_id: UUID,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    """Opportunity detail page — shows buildings inline."""
    from sqlalchemy.orm import selectinload as _sl
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    from app.models.parcel import Parcel as _Parcel
    opp = (await session.execute(
        select(Opportunity)
        .options(
            _sl(Opportunity.opportunity_buildings).selectinload(OpportunityBuilding.building),
            _sl(Opportunity.deal_opportunities).selectinload(DealOpportunity.deal),
            _sl(Opportunity.scraped_listings),
            _sl(Opportunity.project_parcels).selectinload(ProjectParcel.parcel),
        )
        .where(Opportunity.id == opp_id)
    )).scalar_one_or_none()
    if opp is None:
        return HTMLResponse("Not found", status_code=404)
    buildings = [ob.building for ob in opp.opportunity_buildings if ob.building]
    # Parcels with no associated Building record — prompt user to add one
    building_parcel_ids = {b.parcel_id for b in buildings if b.parcel_id}
    bare_parcels = [
        pp.parcel for pp in opp.project_parcels
        if pp.parcel and pp.parcel.id not in building_parcel_ids
    ]
    return templates.TemplateResponse(request, "opportunity_detail.html", {
        "request": request, "opp": opp,
        "buildings": buildings,
        "bare_parcels": bare_parcels,
        **_base_ctx(user, dedup_count, "opportunities"),
    })


@router.post("/ui/opportunities/{opp_id}/archive")
async def archive_opportunity(
    opp_id: UUID,
    session: DBSession,
) -> RedirectResponse:
    """Archive a manually-created opportunity (sets status=archived, keeps all data)."""
    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        return RedirectResponse("/opportunities", status_code=303)
    opp.status = OpportunityStatus.archived
    await session.commit()
    return RedirectResponse("/opportunities", status_code=303)


@router.post("/ui/opportunities/{opp_id}/dissolve")
async def dissolve_opportunity(
    opp_id: UUID,
    session: DBSession,
) -> RedirectResponse:
    """Dissolve a listing-sourced opportunity: delete the Opportunity row (and its
    DealOpportunity join rows via CASCADE). The underlying Listing/Building/Parcel
    records are left completely untouched."""
    from sqlalchemy import delete as sa_delete, update as sa_update
    from app.models.parcel import ParcelTransformation
    from app.models.portfolio import GanttEntry
    from app.models.org import ProjectVisibility
    from app.models.project import PermitStub

    opp = await session.get(Opportunity, opp_id)
    if opp is None:
        return RedirectResponse("/opportunities", status_code=303)

    # Clear FKs that lack ondelete rules before deleting the Opportunity row.
    # ScrapedListing.linked_project_id is nullable — set to NULL to preserve the listing.
    await session.execute(
        sa_update(ScrapedListing)
        .where(ScrapedListing.linked_project_id == opp_id)
        .values(linked_project_id=None)
    )
    # Join/child tables whose FKs reference opportunities.id with no ondelete — delete rows.
    await session.execute(sa_delete(ProjectParcel).where(ProjectParcel.project_id == opp_id))
    await session.execute(sa_delete(PortfolioProject).where(PortfolioProject.project_id == opp_id))
    await session.execute(sa_delete(GanttEntry).where(GanttEntry.project_id == opp_id))
    await session.execute(sa_delete(ParcelTransformation).where(ParcelTransformation.project_id == opp_id))
    await session.execute(sa_delete(ProjectVisibility).where(ProjectVisibility.project_id == opp_id))
    await session.execute(sa_delete(PermitStub).where(PermitStub.project_id == opp_id))

    await session.delete(opp)
    await session.commit()
    return RedirectResponse("/opportunities", status_code=303)


@router.get("/buildings", response_class=HTMLResponse)
async def buildings_page(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    q: str = Query(default=""),
    source: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    stmt = (
        select(Building)
        .options(
            selectinload(Building.scraped_listing).selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
            selectinload(Building.parcel),
        )
        .order_by(Building.name)
    )
    if q:
        stmt = stmt.join(Building.scraped_listing, isouter=True).where(
            or_(Building.name.ilike(f"%{q}%"), ScrapedListing.address_normalized.ilike(f"%{q}%"))
        )
    if source:
        stmt = stmt.join(Building.scraped_listing, isouter=True).where(ScrapedListing.source == source)
    props = list((await session.execute(stmt)).scalars().unique())
    total = int((await session.execute(select(func.count()).select_from(Building))).scalar_one())
    buildings = [_build_building_row(p) for p in props]
    return templates.TemplateResponse(request, "buildings.html", {
        "buildings": buildings, "total_count": total,
        **_base_ctx(user, dedup_count, "buildings"),
    })


@router.get("/ui/buildings/rows", response_class=HTMLResponse)
async def buildings_rows(
    request: Request, session: DBSession,
    q: str = Query(default=""), source: str = Query(default=""),
) -> HTMLResponse:
    stmt = (
        select(Building)
        .options(
            selectinload(Building.scraped_listing).selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
            selectinload(Building.parcel),
        )
        .order_by(Building.name)
    )
    if q:
        stmt = stmt.join(Building.scraped_listing, isouter=True).where(
            or_(Building.name.ilike(f"%{q}%"), ScrapedListing.address_normalized.ilike(f"%{q}%"))
        )
    if source:
        stmt = stmt.join(Building.scraped_listing, isouter=True).where(ScrapedListing.source == source)
    props = list((await session.execute(stmt)).scalars().unique())
    buildings = [_build_building_row(p) for p in props]
    return templates.TemplateResponse(request, "partials/buildings_rows.html", {"buildings": buildings})


@router.get("/ui/buildings/{property_id}/detail", response_class=HTMLResponse)
async def building_detail(request: Request, property_id: UUID, session: DBSession) -> HTMLResponse:
    prop = await session.get(
        Building, property_id,
        options=[
            selectinload(Building.scraped_listing).selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
            selectinload(Building.parcel),
        ]
    )
    if prop is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    b = _build_building_row(prop)
    return templates.TemplateResponse(request, "partials/building_detail.html", {"b": b})


# ---------------------------------------------------------------------------
# Parcels
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


def _build_parcel_row(p: Parcel) -> dict:
    city = _extract_city(p.address_normalized)
    return {
        "id": str(p.id),
        "apn": p.apn,
        "address": p.address_normalized or p.address_raw or "",
        "street": (p.address_normalized or "").split(",")[0] if p.address_normalized else "",
        "city_state_zip": ", ".join(
            part.strip() for part in (p.address_normalized or "").split(",")[1:]
        ) if p.address_normalized else "",
        "address_city": city,
        "jurisdiction_mismatch": False,
        "zoning_code": p.zoning_code,
        "zoning_description": p.zoning_description,
        "lot_sqft": float(p.lot_sqft) if p.lot_sqft else None,
        "gis_acres": float(p.gis_acres) if p.gis_acres else None,
        "state_class": p.state_class,
        "state_class_label": _STATE_CLASS_LABELS.get(p.state_class or "", None),
        "total_assessed_value": float(p.total_assessed_value) if p.total_assessed_value else None,
        "assessed_value_land": float(p.assessed_value_land) if p.assessed_value_land else None,
        "assessed_value_improvements": float(p.assessed_value_improvements) if p.assessed_value_improvements else None,
        "year_built": p.year_built,
        "owner_name": p.owner_name,
        "owner_mailing_address": p.owner_mailing_address,
        "current_use": p.current_use,
        "county": p.county,
        "jurisdiction": p.jurisdiction,
        "priority_bucket": p.priority_bucket,
        "overridden_fields": [],
        "scraped_at_fmt": p.scraped_at.strftime("%b %-d, %Y") if p.scraped_at else None,
    }


_PARCEL_PAGE_SIZE = 500

# Oregon DOR state class → display label mapping (grouped for filter UI)
_STATE_CLASS_GROUPS: dict[str, tuple[str, list[str]]] = {
    "residential":  ("Residential (SFR)",     ["101", "100", "541"]),
    "multifamily":  ("Multi-Family / Apt",     ["551", "550"]),
    "commercial":   ("Commercial",             ["201", "200"]),
    "industrial":   ("Industrial",             ["401", "400"]),
    "farm":         ("Farm / Timber",          ["701", "700", "301", "300", "303"]),
    "exempt":       ("Exempt / Gov / Utility", ["801", "800", "641", "640", "601", "600"]),
}


def _parcel_base_stmt(
    q: str, zoning: list[str], jurisdiction: str,
    use_group: str, min_acres: str, max_acres: str,
    min_year: str, max_year: str,
):
    stmt = select(Parcel).order_by(Parcel.apn)
    if q:
        stmt = stmt.where(or_(Parcel.apn.ilike(f"%{q}%"), Parcel.address_normalized.ilike(f"%{q}%")))
    if zoning:
        stmt = stmt.where(Parcel.zoning_code.in_(zoning))
    if jurisdiction:
        stmt = stmt.where(Parcel.jurisdiction == jurisdiction)
    if use_group and use_group in _STATE_CLASS_GROUPS:
        codes = _STATE_CLASS_GROUPS[use_group][1]
        stmt = stmt.where(Parcel.state_class.in_(codes))
    if min_acres:
        try:
            stmt = stmt.where(Parcel.gis_acres >= float(min_acres))
        except ValueError:
            pass
    if max_acres:
        try:
            stmt = stmt.where(Parcel.gis_acres <= float(max_acres))
        except ValueError:
            pass
    if min_year:
        try:
            stmt = stmt.where(Parcel.year_built >= int(min_year))
        except ValueError:
            pass
    if max_year:
        try:
            stmt = stmt.where(Parcel.year_built <= int(max_year))
        except ValueError:
            pass
    return stmt


def _parcel_filter_ctx(
    q: str, zoning: list[str], jurisdiction: str,
    use_group: str, min_acres: str, max_acres: str,
    min_year: str, max_year: str,
) -> dict:
    return {
        "q": q, "zoning": zoning, "jurisdiction": jurisdiction,
        "use_group": use_group, "min_acres": min_acres, "max_acres": max_acres,
        "min_year": min_year, "max_year": max_year,
        "use_group_options": [(k, v[0]) for k, v in _STATE_CLASS_GROUPS.items()],
    }


@router.get("/parcels", response_class=HTMLResponse)
async def parcels_page(
    request: Request, session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    q: str = Query(default=""),
    zoning: list[str] = Query(default=[]),
    jurisdiction: str = Query(default=""),
    use_group: str = Query(default=""),
    min_acres: str = Query(default=""),
    max_acres: str = Query(default=""),
    min_year: str = Query(default=""),
    max_year: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    base = _parcel_base_stmt(q, zoning, jurisdiction, use_group, min_acres, max_acres, min_year, max_year)
    filtered_count, total = await asyncio.gather(
        session.execute(select(func.count()).select_from(base.subquery())),
        session.execute(select(func.count()).select_from(Parcel)),
    )
    filtered_count = int(filtered_count.scalar_one())
    total = int(total.scalar_one())
    parcels_list = list((await session.execute(base.offset(offset).limit(_PARCEL_PAGE_SIZE))).scalars())
    zoning_codes_stmt = select(Parcel.zoning_code).where(Parcel.zoning_code.isnot(None)).distinct().order_by(Parcel.zoning_code)
    if jurisdiction:
        zoning_codes_stmt = zoning_codes_stmt.where(func.lower(Parcel.jurisdiction) == jurisdiction.lower())
    zoning_codes_result, jurisdictions_result = await asyncio.gather(
        session.execute(zoning_codes_stmt),
        session.execute(select(Parcel.jurisdiction).where(Parcel.jurisdiction.isnot(None)).distinct().order_by(Parcel.jurisdiction)),
    )
    zoning_codes = [r[0] for r in zoning_codes_result]
    jurisdictions = [r[0] for r in jurisdictions_result]
    parcels_data = [_build_parcel_row(p) for p in parcels_list]
    return templates.TemplateResponse(request, "parcels.html", {
        "parcels": parcels_data,
        "total_count": total,
        "filtered_count": filtered_count,
        "page_size": _PARCEL_PAGE_SIZE,
        "offset": offset,
        "zoning_codes": zoning_codes,
        "jurisdictions": jurisdictions,
        **_parcel_filter_ctx(q, zoning, jurisdiction, use_group, min_acres, max_acres, min_year, max_year),
        **_base_ctx(user, dedup_count, "parcels"),
    })


@router.get("/ui/parcels/rows", response_class=HTMLResponse)
async def parcels_rows(
    request: Request, session: DBSession,
    q: str = Query(default=""),
    zoning: list[str] = Query(default=[]),
    jurisdiction: str = Query(default=""),
    use_group: str = Query(default=""),
    min_acres: str = Query(default=""),
    max_acres: str = Query(default=""),
    min_year: str = Query(default=""),
    max_year: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
) -> HTMLResponse:
    base = _parcel_base_stmt(q, zoning, jurisdiction, use_group, min_acres, max_acres, min_year, max_year)
    filtered_count, total = await asyncio.gather(
        session.execute(select(func.count()).select_from(base.subquery())),
        session.execute(select(func.count()).select_from(Parcel)),
    )
    filtered_count = int(filtered_count.scalar_one())
    total = int(total.scalar_one())
    parcels_list = list((await session.execute(base.offset(offset).limit(_PARCEL_PAGE_SIZE))).scalars())
    parcels_data = [_build_parcel_row(p) for p in parcels_list]
    return templates.TemplateResponse(request, "partials/parcels_rows.html", {
        "parcels": parcels_data,
        "total_count": total,
        "filtered_count": filtered_count,
        "page_size": _PARCEL_PAGE_SIZE,
        "offset": offset,
        **_parcel_filter_ctx(q, zoning, jurisdiction, use_group, min_acres, max_acres, min_year, max_year),
    })


@router.get("/ui/parcels/{parcel_id}/detail", response_class=HTMLResponse)
async def parcel_detail(request: Request, parcel_id: UUID, session: DBSession) -> HTMLResponse:
    parcel = await session.get(Parcel, parcel_id)
    if parcel is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    return templates.TemplateResponse(request, "partials/parcel_detail.html", {"p": _build_parcel_row(parcel)})


@router.post("/ui/parcels/{parcel_id}/gis-refresh", response_class=HTMLResponse)
async def parcel_gis_refresh(request: Request, parcel_id: UUID, session: DBSession) -> HTMLResponse:
    """Pull fresh GIS data for a parcel from the appropriate county source and re-render the detail panel."""
    from app.scrapers.parcel_enrichment import enrich_parcel

    parcel = await session.get(Parcel, parcel_id)
    if parcel is None:
        return HTMLResponse("<p class='text-muted'>Parcel not found.</p>", status_code=404)

    address = parcel.address_normalized or parcel.address_raw
    updated = await enrich_parcel(session, address=address, apn=parcel.apn)
    await session.commit()

    result = updated or parcel
    return templates.TemplateResponse(request, "partials/parcel_detail.html", {"p": _build_parcel_row(result)})


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def _build_listing_row(listing: ScrapedListing) -> dict:
    prop = getattr(listing, "_property", None)
    broker = listing.broker
    brokerage = broker.brokerage if broker else None
    return {
        "id": str(listing.id),
        "address": listing.address_normalized or listing.address_raw or "Undisclosed",
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
        "linked_opportunity_id": str(listing.linked_project_id) if listing.linked_project_id else None,
        "linked_opportunity_name": getattr(getattr(listing, "linked_opportunity", None), "name", None),
        "linked_deal_id": None,  # Resolved separately when needed (avoid N+1 on list page)
        "priority_bucket": listing.priority_bucket,
    }


def _listings_base_stmt(
    q: str,
    source: str,
    is_new: str,
    property_type: str = "",
    min_units: str = "",
    max_units: str = "",
    priority_bucket: str = "",
    cities: list[str] | None = None,
):
    stmt = (
        select(ScrapedListing)
        .options(
            selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
            selectinload(ScrapedListing.linked_opportunity),
        )
        .order_by(ScrapedListing.last_seen_at.desc())
    )
    if q:
        stmt = stmt.where(or_(
            ScrapedListing.address_normalized.ilike(f"%{q}%"),
            ScrapedListing.address_raw.ilike(f"%{q}%"),
        ))
    if source:
        stmt = stmt.where(ScrapedListing.source == source)
    if is_new == "1":
        stmt = stmt.where(ScrapedListing.is_new.is_(True))
    if property_type:
        stmt = stmt.where(ScrapedListing.property_type == property_type)
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
    if priority_bucket:
        stmt = stmt.where(ScrapedListing.priority_bucket == priority_bucket)
    if cities is not None:
        stmt = _apply_jurisdiction_filter(stmt, cities)
    return stmt


def _apply_jurisdiction_filter(stmt, jurisdictions: list[str]):
    """Apply jurisdiction filter — cities and 'uninc:county' entries.

    Uses COALESCE(jurisdiction, city) so that parcel-reconciled listings
    filter by the authoritative GIS jurisdiction, while unreconciled
    listings fall back to the broker-provided city.
    """
    effective_jurisdiction = func.coalesce(ScrapedListing.jurisdiction, ScrapedListing.city)

    city_names = []
    uninc_counties = []
    for j in jurisdictions:
        if j.startswith("uninc:"):
            uninc_counties.append(j[6:])
        else:
            city_names.append(j)

    clauses = []
    if city_names:
        clauses.append(func.lower(effective_jurisdiction).in_([c.lower() for c in city_names]))
    for county in uninc_counties:
        clauses.append(
            (effective_jurisdiction.is_(None)) & (func.lower(ScrapedListing.county).like(f"{county.lower()}%"))
        )
    if clauses:
        stmt = stmt.where(or_(*clauses))
    else:
        # All deselected — show nothing
        stmt = stmt.where(ScrapedListing.id.is_(None))
    return stmt


async def _get_jurisdictions(session) -> list[dict]:
    """Return sorted list of {value, label, type} for jurisdiction filter.

    Uses COALESCE(jurisdiction, city) so parcel-reconciled listings show the
    authoritative GIS jurisdiction while unreconciled listings fall back to
    the broker-provided city.
    """
    effective_jurisdiction = func.coalesce(ScrapedListing.jurisdiction, ScrapedListing.city)

    # Distinct effective jurisdictions
    city_rows = (await session.execute(
        select(effective_jurisdiction.label("ej"), func.count())
        .where(effective_jurisdiction.isnot(None))
        .group_by(effective_jurisdiction)
        .order_by(effective_jurisdiction)
    )).all()

    # Normalize names (dedup case variants like KLAMATH FALLS vs Klamath Falls)
    seen_cities: dict[str, tuple[str, int]] = {}
    for city, cnt in city_rows:
        key = city.strip().lower()
        if key in seen_cities:
            existing_label, existing_cnt = seen_cities[key]
            seen_cities[key] = (existing_label if existing_label[0].isupper() else city.strip(), existing_cnt + cnt)
        else:
            seen_cities[key] = (city.strip(), cnt)

    jurisdictions = [
        {"value": label, "label": f"{label} ({cnt})", "type": "city"}
        for _key, (label, cnt) in sorted(seen_cities.items())
    ]

    # Unincorporated counties (listings with no jurisdiction AND no city)
    uninc_rows = (await session.execute(
        select(ScrapedListing.county, func.count())
        .where(effective_jurisdiction.is_(None), ScrapedListing.county.isnot(None))
        .group_by(ScrapedListing.county)
    )).all()
    if uninc_rows:
        seen_counties: dict[str, int] = {}
        for county, cnt in uninc_rows:
            norm = county.strip().title().replace(" County", "")
            seen_counties[norm] = seen_counties.get(norm, 0) + cnt
        for county_name, cnt in sorted(seen_counties.items()):
            jurisdictions.append({
                "value": f"uninc:{county_name}",
                "label": f"{county_name} Unincorporated ({cnt})",
                "type": "unincorporated",
            })

    return jurisdictions


def _split_listings(all_listings: list) -> tuple[list, list, list]:
    """Split into (new, promoted, archived) buckets."""
    new, promoted, archived = [], [], []
    for l in all_listings:
        if l.linked_project_id:
            promoted.append(_build_listing_row(l))
        elif l.archived:
            archived.append(_build_listing_row(l))
        else:
            new.append(_build_listing_row(l))
    return new, promoted, archived


@router.get("/listings", response_class=HTMLResponse)
async def listings_page(
    request: Request, session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    q: str = Query(default=""),
    source: str = Query(default=""),
    property_type: str = Query(default=""),
    min_units: str = Query(default=""),
    max_units: str = Query(default=""),
    priority_bucket: str = Query(default=""),
    jurisdiction: list[str] = Query(default=[]),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    cities = jurisdiction if jurisdiction else None  # empty = no filter (show all)
    all_listings = list((await session.execute(
        _listings_base_stmt(q, source, "", property_type, min_units, max_units, priority_bucket, cities=cities)
    )).scalars())
    new_listings, promoted, archived = _split_listings(all_listings)
    total = int((await session.execute(select(func.count()).select_from(ScrapedListing))).scalar_one())
    property_types = [
        row[0] for row in (await session.execute(
            select(ScrapedListing.property_type).distinct().where(ScrapedListing.property_type.isnot(None)).order_by(ScrapedListing.property_type)
        )).all()
    ]
    # Realie usage for button state
    realie_month = _current_month()
    realie_result = await session.execute(
        select(RealieUsage).where(RealieUsage.month == realie_month)
    )
    realie_usage = realie_result.scalar_one_or_none()
    realie_calls_used = realie_usage.calls_used if realie_usage else 0
    realie_call_limit = realie_usage.call_limit if realie_usage else 25
    realie_locked = realie_usage.is_locked if realie_usage else False

    jurisdictions = await _get_jurisdictions(session)
    return templates.TemplateResponse(request, "listings.html", {
        "new_listings": new_listings,
        "promoted_listings": promoted,
        "archived_listings": archived,
        "total_count": total,
        "q": q, "source": source,
        "property_type": property_type, "min_units": min_units, "max_units": max_units,
        "priority_bucket": priority_bucket,
        "property_types": property_types,
        "jurisdictions": jurisdictions,
        "selected_jurisdictions": jurisdiction,
        "realie_calls_used": realie_calls_used,
        "realie_call_limit": realie_call_limit,
        "realie_locked": realie_locked,
        **_base_ctx(user, dedup_count, "listings"),
    })


@router.get("/ui/listings/rows", response_class=HTMLResponse)
async def listings_rows(
    request: Request, session: DBSession,
    q: str = Query(default=""),
    source: str = Query(default=""),
    property_type: str = Query(default=""),
    min_units: str = Query(default=""),
    max_units: str = Query(default=""),
    priority_bucket: str = Query(default=""),
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
    source: str = Query(default=""),
    property_type: str = Query(default=""),
    min_units: str = Query(default=""),
    max_units: str = Query(default=""),
    priority_bucket: str = Query(default=""),
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
            selectinload(ScrapedListing.linked_opportunity),
        )
        .where(ScrapedListing.linked_project_id.isnot(None))
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


@router.get("/ui/map/context")
async def map_context(
    session: DBSession,
    listing_id: UUID | None = Query(default=None),
    opportunity_id: UUID | None = Query(default=None),
    project_id: UUID | None = Query(default=None),
    parcel_id: UUID | None = Query(default=None),
    parcel_ids: str | None = Query(default=None),
) -> dict:
    """
    Resolve parcels + overlay GeoJSON for the map modal.
    Accepts one context param: listing_id, opportunity_id, project_id, or comma-sep parcel_ids.
    """
    from app.utils.gis import (
        combined_envelope, bbox_to_leaflet, envelope_str,
        esri_to_geojson, is_wgs84, detect_jurisdiction,
        fetch_overlay_features, compute_overlap_assessment,
        OVERLAY_REGISTRY,
    )

    parcels: list[Parcel] = []
    context_label = "Parcels"

    if listing_id:
        listing = await session.get(ScrapedListing, listing_id)
        if listing:
            context_label = listing.address_normalized or listing.address_raw or str(listing_id)
            if listing.apn:
                apn = listing.apn.split(",")[0].split(";")[0].strip().upper()
                result = (await session.execute(
                    select(Parcel).where(Parcel.apn == apn)
                )).scalar_one_or_none()
                if result:
                    parcels = [result]
            # Fallback: listing lat/lng only — handled below via centroid

    elif opportunity_id:
        opp = await session.get(Opportunity, opportunity_id)
        if opp:
            context_label = opp.name or str(opportunity_id)
        pps = (await session.execute(
            select(ProjectParcel)
            .where(ProjectParcel.project_id == opportunity_id)
            .options(selectinload(ProjectParcel.parcel))
        )).scalars().all()
        parcels = [pp.parcel for pp in pps if pp.parcel]

    elif project_id:
        proj = await session.get(Project, project_id)
        if proj:
            context_label = proj.name or str(project_id)
            if proj.opportunity_id:
                opp = await session.get(Opportunity, proj.opportunity_id)
                if opp:
                    context_label = f"{opp.name or ''} — {proj.name or ''}".strip(" —")
        assignments = (await session.execute(
            select(ProjectParcelAssignment)
            .where(ProjectParcelAssignment.project_id == project_id)
        )).scalars().all()
        if assignments:
            parcel_id_list = [a.parcel_id for a in assignments]
            parcels = list((await session.execute(
                select(Parcel).where(Parcel.id.in_(parcel_id_list))
            )).scalars())
        else:
            # Fallback to opportunity-level parcels
            if proj and proj.opportunity_id:
                pps = (await session.execute(
                    select(ProjectParcel)
                    .where(ProjectParcel.project_id == proj.opportunity_id)
                    .options(selectinload(ProjectParcel.parcel))
                )).scalars().all()
                parcels = [pp.parcel for pp in pps if pp.parcel]

    elif parcel_id:
        result = await session.get(Parcel, parcel_id)
        if result:
            parcels = [result]

    elif parcel_ids:
        ids = [s.strip() for s in parcel_ids.replace(";", ",").split(",") if s.strip()]
        try:
            uuid_list = [UUID(i) for i in ids]
            parcels = list((await session.execute(
                select(Parcel).where(Parcel.id.in_(uuid_list))
            )).scalars())
        except ValueError:
            pass

    # --- Build parcel data ---
    parcel_data: list[dict] = []
    geometries: list[dict] = []  # raw ESRI geometries for combined envelope
    jurisdiction: str | None = None

    for parcel in parcels:
        geom_raw = parcel.geometry  # stored as ESRI rings dict
        geojson = esri_to_geojson(geom_raw) if geom_raw else None

        # Use stored jurisdiction first; fall back to address detection
        if not jurisdiction:
            jurisdiction = parcel.jurisdiction or detect_jurisdiction(
                parcel.address_normalized or parcel.address_raw,
                parcel.owner_city,
            )

        if geom_raw and is_wgs84(geom_raw):
            geometries.append(geom_raw)
        elif geojson:
            geometries.append(geom_raw)

        parcel_data.append({
            "id": str(parcel.id),
            "apn": parcel.apn,
            "address": parcel.address_normalized or parcel.address_raw or parcel.apn,
            "geojson": geojson,
            "lot_sqft": float(parcel.lot_sqft) if parcel.lot_sqft else None,
            "zoning": parcel.zoning_code,
            "has_geometry": geojson is not None,
        })

    # Lat/lng fallback from listing (no parcel geometry)
    centroid: list[float] | None = None
    if not geometries and listing_id:
        listing = await session.get(ScrapedListing, listing_id)
        if listing and listing.lat and listing.lng:
            centroid = [float(listing.lat), float(listing.lng)]

    # --- Compute envelope ---
    bbox: list[list[float]] | None = None
    overlay_data: dict = {}
    assessments: dict = {}

    if geometries:
        env_tuple = combined_envelope(geometries)
        env_str = envelope_str(env_tuple)
        bbox = bbox_to_leaflet(env_tuple)

        overlay_data = await fetch_overlay_features(env_str, jurisdiction=jurisdiction)

        # Overlap assessment per parcel × overlay
        for p_dict, parcel in zip(parcel_data, parcels):
            if not parcel.geometry:
                continue
            parcel_assessments: dict = {}
            for layer_key, layer_info in overlay_data.items():
                assessment = compute_overlap_assessment(
                    parcel.geometry,
                    layer_info.get("features") or [],
                    parcel_sqft=float(parcel.lot_sqft) if parcel.lot_sqft else None,
                )
                if assessment:
                    parcel_assessments[layer_key] = assessment
            if parcel_assessments:
                assessments[p_dict["id"]] = parcel_assessments

    elif centroid:
        # No geometry but we have a lat/lng — tiny envelope just to run overlays
        lat, lng = centroid[0], centroid[1]
        env_str = f"{lng-0.001},{lat-0.001},{lng+0.001},{lat+0.001}"
        bbox = [[lat - 0.002, lng - 0.002], [lat + 0.002, lng + 0.002]]
        overlay_data = await fetch_overlay_features(env_str, jurisdiction=jurisdiction)

    return {
        "parcels": parcel_data,
        "overlays": overlay_data,
        "assessments": assessments,
        "bbox": bbox,
        "centroid": centroid,
        "context_label": context_label,
        "jurisdiction": jurisdiction,
    }


@router.get("/ui/listings/{listing_id}/detail", response_class=HTMLResponse)
async def listing_detail(request: Request, listing_id: UUID, session: DBSession) -> HTMLResponse:
    listing = await session.get(
        ScrapedListing, listing_id,
        options=[
            selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
            selectinload(ScrapedListing.linked_opportunity),
        ]
    )
    if listing is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    l = _build_listing_row(listing)
    # Resolve linked deal if this listing is connected to an opportunity
    if listing.linked_project_id:
        deal_row = (await session.execute(
            select(Deal.id)
            .join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
            .where(DealOpportunity.opportunity_id == listing.linked_project_id)
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
    """Manually promote a listing to an Opportunity + Building."""
    from app.tasks.scraper import _promote_listing as _do_promote, _get_default_org_id  # local import avoids circular

    listing = await session.get(
        ScrapedListing, listing_id,
        options=[selectinload(ScrapedListing.broker).selectinload(Broker.brokerage)]
    )
    if listing is None:
        return HTMLResponse("<span class='text-muted text-small'>Not found</span>")

    if listing.linked_project_id:
        # Already promoted — return the promoted row snippet so the UI can move it
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

    # Reload listing to get fresh linked_opportunity relationship
    await session.refresh(listing)
    listing_with_opp = await session.get(
        ScrapedListing, listing_id,
        options=[
            selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
            selectinload(ScrapedListing.linked_opportunity),
        ]
    )
    l = _build_listing_row(listing_with_opp)
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

    if listing.linked_project_id:
        return RedirectResponse(f"/opportunities/{listing.linked_project_id}", status_code=303)

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
        options=[
            selectinload(ScrapedListing.broker).selectinload(Broker.brokerage),
            selectinload(ScrapedListing.linked_opportunity),
        ]
    )
    if listing is None:
        return HTMLResponse("<span class='text-muted text-small'>Not found</span>")

    if listing.linked_project_id:
        opp = await session.get(Opportunity, listing.linked_project_id)
        if opp is not None:
            opp.status = OpportunityStatus.archived
        listing.linked_project_id = None
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


@router.post("/ui/listings/{listing_id}/create-deal", response_class=HTMLResponse)
async def create_deal_from_listing(
    request: Request,
    listing_id: UUID,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    """Create a Deal + Scenario from a ScrapedListing. Redirects to model builder."""
    listing = await session.get(
        ScrapedListing, listing_id,
        options=[selectinload(ScrapedListing.broker)]
    )
    if listing is None:
        return HTMLResponse("<p class='text-muted'>Listing not found.</p>", status_code=404)

    form = await request.form()
    deal_type_raw = str(form.get("deal_type", "acquisition_major_reno")).strip()
    try:
        deal_type = ProjectType(deal_type_raw)
    except ValueError:
        deal_type = ProjectType.acquisition_major_reno

    user = await _get_user(session, request)
    from app.models.org import Organization
    org = (await session.execute(select(Organization).limit(1))).scalar_one_or_none()
    if org is None:
        return HTMLResponse("<p class='text-muted'>No organization found.</p>", status_code=400)
    org_id = (user.org_id if user else None) or org.id

    deal_name = listing.address_normalized or listing.address_raw or "Unnamed Listing Deal"

    # Re-use existing Opportunity if this listing was already linked
    if listing.linked_project_id:
        opportunity = await session.get(Opportunity, listing.linked_project_id)
    else:
        opportunity = Opportunity(
            org_id=org_id,
            name=deal_name,
            status=OpportunityStatus.active,
            created_by_user_id=user.id if user else None,
        )
        session.add(opportunity)
        await session.flush()
        listing.linked_project_id = opportunity.id

        # Create a Building from listing data and link it to the Opportunity,
        # same as _promote_listing does when going via the Promote flow.
        if listing.property_id:
            _bldg = await session.get(Building, listing.property_id)
        else:
            _bldg = None
        if _bldg is None:
            _bldg = Building(
                name=deal_name,
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
            session.add(_bldg)
            await session.flush()
            listing.property_id = _bldg.id
        session.add(OpportunityBuilding(
            opportunity_id=opportunity.id,
            building_id=_bldg.id,
            sort_order=0,
        ))
        await session.flush()

        # Auto-link parcel: enrich if needed, then create ProjectParcel
        parcel_id = listing.parcel_id
        if parcel_id is None and (listing.apn or listing.address_normalized):
            from app.scrapers.parcel_enrichment import enrich_parcel as _enrich
            _parcel = await _enrich(session, address=listing.address_normalized or listing.address_raw, apn=listing.apn)
            if _parcel is not None:
                parcel_id = _parcel.id
                listing.parcel_id = parcel_id
        if parcel_id is not None:
            _existing_pp = (await session.execute(
                select(ProjectParcel).where(
                    ProjectParcel.project_id == opportunity.id,
                    ProjectParcel.parcel_id == parcel_id,
                )
            )).scalar_one_or_none()
            if _existing_pp is None:
                session.add(ProjectParcel(
                    project_id=opportunity.id,
                    parcel_id=parcel_id,
                    relationship_type=ProjectParcelRelationship.unchanged,
                ))
        await session.flush()

    # Check for existing Deal linked to this Opportunity
    existing_deal = (await session.execute(
        select(Deal)
        .join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
        .where(DealOpportunity.opportunity_id == opportunity.id)
        .limit(1)
    )).scalar_one_or_none()

    if existing_deal:
        # Deal already exists — just redirect to it
        return RedirectResponse(url=f"/deals/{existing_deal.id}", status_code=303)

    top_deal = Deal(
        org_id=org_id,
        name=deal_name,
        created_by_user_id=user.id if user else None,
    )
    session.add(top_deal)
    await session.flush()
    session.add(DealOpportunity(deal_id=top_deal.id, opportunity_id=opportunity.id))

    scenario = DealModel(
        deal_id=top_deal.id,
        name="Base Case",
        project_type=deal_type,
        version=1,
        is_active=True,
        created_by_user_id=user.id if user else None,
    )
    session.add(scenario)
    await session.flush()

    dev_project = Project(
        scenario_id=scenario.id,
        opportunity_id=opportunity.id,
        name="Default Project",
        deal_type=deal_type,
    )
    session.add(dev_project)
    await session.flush()

    await _auto_assign_opportunity_to_project(opportunity, dev_project, session)
    for milestone in _seed_milestones(dev_project, deal_type):
        session.add(milestone)

    # Seed Acquisition use line from listing asking price
    if listing.asking_price:
        session.add(UseLine(
            project_id=dev_project.id,
            label="Acquisition",
            phase=UseLinePhase.acquisition,
            amount=float(listing.asking_price),
            timing_type="first_day",
            is_deferred=False,
        ))

    await session.commit()

    return RedirectResponse(url=f"/models/{scenario.id}/builder", status_code=303)


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------

def _build_broker_row(broker: Broker, listing_count: int) -> dict:
    return {
        "id": str(broker.id),
        "full_name": f"{broker.first_name or ''} {broker.last_name or ''}".strip() or "Unknown",
        "brokerage_name": broker.brokerage.name if broker.brokerage else None,
        "email": broker.email,
        "phone": broker.phone,
        "license_number": broker.license_number,
        "license_state": broker.license_state,
        "is_platinum": broker.is_platinum,
        "number_of_assets": broker.number_of_assets,
        "listing_count": listing_count,
    }


def _build_broker_detail(broker: Broker, listings: list[ScrapedListing]) -> dict:
    row = _build_broker_row(broker, len(listings))
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
    vd_user_id: str | None = Cookie(default=None),
    q: str = Query(default=""),
    company: str = Query(default=""),
    listings_op: str = Query(default=""),
    listings_val: str = Query(default=""),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    stmt = _broker_stmt(q, company, listings_op, listings_val)
    brokers_list = list((await session.execute(stmt)).scalars().unique())
    brokers_list = _apply_listings_filter(brokers_list, listings_op, listings_val)
    total = int((await session.execute(select(func.count()).select_from(Broker))).scalar_one())
    brokers_data = [_build_broker_row(b, len(b.scraped_listings)) for b in brokers_list]
    return templates.TemplateResponse(request, "brokers.html", {
        "brokers": brokers_data, "total_count": total,
        "q": q, "company": company, "listings_op": listings_op, "listings_val": listings_val,
        **_base_ctx(user, dedup_count, "brokers"),
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
        options=[selectinload(Broker.brokerage), selectinload(Broker.scraped_listings)]
    )
    if broker is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>")
    b = _build_broker_detail(broker, broker.scraped_listings)
    return templates.TemplateResponse(request, "partials/broker_detail.html", {"b": b})


# ---------------------------------------------------------------------------
# Model Builder
# ---------------------------------------------------------------------------

def _sum_amount(rows: list) -> float | None:
    if not rows:
        return None
    total = sum(float(r.amount) for r in rows)
    return total if total else None


def _sum_annual(rows: list, field: str = "annual_amount") -> float | None:
    if not rows:
        return None
    total = sum(float(getattr(r, field, 0) or 0) for r in rows)
    return total if total else None


def _income_annual(streams: list) -> float | None:
    """Effective gross annual revenue at stabilization — applies stabilized_occupancy_pct."""
    if not streams:
        return None
    total = 0.0
    for s in streams:
        occupancy = float(s.stabilized_occupancy_pct or 100) / 100.0
        if s.amount_per_unit_monthly and s.unit_count:
            total += float(s.amount_per_unit_monthly) * int(s.unit_count) * occupancy * 12
        elif s.amount_fixed_monthly:
            total += float(s.amount_fixed_monthly) * occupancy * 12
    return total if total else None


def _capital_total(modules: list) -> float | None:
    total = 0.0
    for m in modules:
        if m.source and isinstance(m.source, dict):
            if m.source.get("is_bridge"):
                continue
            amt = m.source.get("amount")
            if amt:
                total += float(amt)
    return total if total else None


# ---------------------------------------------------------------------------
# Builder form helpers
# ---------------------------------------------------------------------------

from decimal import Decimal

_ITEM_TYPE_TO_MODULE: dict[str, str] = {
    "use-lines": "sources_uses",
    "income-streams": "revenue",
    "expense-lines": "opex",
    "capital-modules": "sources_uses",
    "waterfall-tiers": "owners_profit",
    "milestones": "timeline",
    "unit-mix": "property",
}


def _fd(v: str | None) -> Decimal | None:
    """Parse an optional Decimal from a form field. Strips commas tolerantly."""
    if not v or not v.strip():
        return None
    try:
        return Decimal(v.strip().replace(",", ""))
    except Exception:
        return None


def _fi(v: str | None, default: int = 0) -> int:
    """Parse an optional int from a form field."""
    if not v or not v.strip():
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


def _fp(v: str | None, default: list[str] | None = None) -> list[str]:
    """Parse phases from a comma-separated or JSON-array form field."""
    if not v or not v.strip():
        return default or []
    v = v.strip()
    if v.startswith("["):
        try:
            return json.loads(v)
        except Exception:
            pass
    return [p.strip() for p in v.split(",") if p.strip()]


def _builder_gantt_from_milestones(project: "Project | None", milestones: list) -> "dict | None":
    """Build Gantt v2 data from pre-loaded milestones for the model builder timeline panel."""
    if not project or not milestones:
        return None
    bars, epoch, has_dates = _extract_milestone_bars(project, milestones=milestones)
    if not bars:
        return None
    # Apply the same stabilized cap used by the full gantt
    raw_rows = [{"project_name": project.name, "bars": bars}]
    _override_stabilized_cap(raw_rows)
    g_min = min(b["display_start_day"] for b in bars)
    g_max = max(b["display_start_day"] + b["display_duration_days"] for b in bars)
    _gantt_apply_pct(bars, g_min, g_max)
    bars.sort(key=lambda b: b["display_start_day"])  # chronological row order
    month_ticks, year_spans = _compute_gantt_axis(epoch, g_min, g_max, has_dates)
    return {
        "has_dates": has_dates,
        "epoch": epoch,           # exposed for source bar positioning
        "g_min": g_min,
        "g_max": g_max,
        "month_ticks": month_ticks,
        "year_spans": year_spans,
        "rows": _bars_to_phase_rows(bars),
    }


async def _load_builder_data(session: AsyncSession, model_id: UUID, project_id: UUID | None = None) -> dict:
    """Load all line-item data for the model builder page/panel.

    model_id = Deal.id.  Line items (use_lines, income_streams, expense_lines,
    operational_inputs) belong to the active Project for this Deal.
    Capital modules and waterfall tiers belong to the Deal directly.

    project_id: if provided, load data for that specific Project; else default to first.
    """
    # Load the scenario (DealModel) to access income_mode and deal_id
    _scenario = await session.get(DealModel, model_id)

    # Resolve active Project for this Scenario
    default_project = None
    if project_id is not None:
        candidate = await session.get(Project, project_id)
        if candidate and candidate.scenario_id == model_id:
            default_project = candidate
    if default_project is None:
        default_project = (await session.execute(
            select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
        )).scalar_one_or_none()
    project_id = default_project.id if default_project else None
    timeline_approved = default_project.timeline_approved if default_project else False

    inputs = None
    use_lines: list = []
    income_streams: list = []
    expense_lines: list = []
    unit_mix_rows: list = []

    if project_id is not None:
        inputs = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project_id)
        )).scalar_one_or_none()

        use_lines = list((await session.execute(
            select(UseLine).where(UseLine.project_id == project_id).order_by(UseLine.phase, UseLine.label)
        )).scalars())

        income_streams = list((await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == project_id).order_by(IncomeStream.label)
        )).scalars())

        expense_lines = list((await session.execute(
            select(OperatingExpenseLine).where(OperatingExpenseLine.project_id == project_id).order_by(OperatingExpenseLine.label)
        )).scalars())

        unit_mix_rows = list((await session.execute(
            select(UnitMix).where(UnitMix.project_id == project_id).order_by(UnitMix.label)
        )).scalars())

    outputs = (await session.execute(
        select(OperationalOutputs).where(OperationalOutputs.scenario_id == model_id)
    )).scalar_one_or_none()

    # Carrying annual = avg monthly debt service in stabilized/operations phase × 12.
    # None = never computed; 0.0 = computed but no debt service.
    from app.models.cashflow import CashFlow as _CashFlow, PeriodType as _PT
    _cf_count = (await session.execute(
        select(func.count()).select_from(_CashFlow).where(_CashFlow.scenario_id == model_id)
    )).scalar_one()
    if _cf_count:
        # Prefer stabilized phase; fall back to any operation phase; last resort = any period
        _ops_avg = (await session.execute(
            select(func.avg(_CashFlow.debt_service)).where(
                _CashFlow.scenario_id == model_id,
                _CashFlow.period_type == _PT.stabilized,
            )
        )).scalar_one_or_none()
        if _ops_avg is None:
            _ops_avg = (await session.execute(
                select(func.avg(_CashFlow.debt_service)).where(
                    _CashFlow.scenario_id == model_id,
                    _CashFlow.period_type.in_([_PT.lease_up, _PT.stabilized]),
                )
            )).scalar_one_or_none()
        if _ops_avg is None:
            _ops_avg = (await session.execute(
                select(func.avg(_CashFlow.debt_service)).where(_CashFlow.scenario_id == model_id)
            )).scalar_one_or_none()
        carrying_annual_computed: float | None = float(_ops_avg) * 12 if _ops_avg else 0.0

        # First stabilized period NCF → first-month and first-year profit metrics
        _stab_rows = list((await session.execute(
            select(_CashFlow.net_cash_flow).where(
                _CashFlow.scenario_id == model_id,
                _CashFlow.period_type == _PT.stabilized,
            ).order_by(_CashFlow.period)
        )).scalars())
        stabilized_month1_ncf: float | None = float(_stab_rows[0]) if _stab_rows else None
        stabilized_year1_ncf: float | None = float(sum(_stab_rows[:12])) if _stab_rows else None
    else:
        carrying_annual_computed = None  # not yet computed
        stabilized_month1_ncf = None
        stabilized_year1_ncf = None

    capital_modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == model_id).order_by(CapitalModule.stack_position)
    )).scalars())

    # Per-module-per-phase annual debt service for the carrying costs table rows.
    # carrying_detail[module_id_str][phase_name] = annual_amount (float)
    _DEBT_FT = {"senior_debt", "mezzanine_debt", "bridge", "soft_loan",
                "construction_loan", "bond", "permanent_debt"}

    def _annual_carry_amt(source: dict, carry_type: str) -> float:
        amount = source.get("amount")
        rate_pct = source.get("interest_rate_pct")
        if not amount or not rate_pct:
            return 0.0
        principal = float(amount)
        rate = float(rate_pct)
        if carry_type in ("io_only", "interest_reserve"):
            # True IO or pre-funded IR: annual interest cost = principal × rate
            # (IR: reserve pays it; io_only: borrower pays it — same carrying display)
            return principal * rate / 100.0
        elif carry_type == "capitalized_interest":
            # No periodic cash outflow — interest accrues to balance, paid at payoff
            return 0.0
        elif carry_type == "pi":
            r = rate / 100.0 / 12.0
            n = int(source.get("amort_term_years") or 30) * 12
            if r == 0:
                return principal / (n / 12)
            factor = (1 + r) ** n
            return (principal * r * factor / (factor - 1)) * 12
        return 0.0

    carrying_detail: dict[str, dict[str, float]] = {}
    for _cm in capital_modules:
        _ft = str(_cm.funder_type).replace("FunderType.", "")
        if _ft not in _DEBT_FT:
            continue
        _src = _cm.source or {}
        _carry = _cm.carry or {}
        _mid = str(_cm.id)
        if "phases" in _carry:
            carrying_detail[_mid] = {
                p.get("name", ""): _annual_carry_amt(_src, p.get("carry_type", "none"))
                for p in _carry["phases"]
            }
        else:
            _ct = _carry.get("carry_type", "none")
            _amt = _annual_carry_amt(_src, _ct)
            carrying_detail[_mid] = {"construction": _amt, "operation": _amt}

    waterfall_tiers = list((await session.execute(
        select(WaterfallTier).where(WaterfallTier.scenario_id == model_id).order_by(WaterfallTier.priority)
    )).scalars())

    # Milestones for the default dev Project
    milestones: list = []
    if project_id is not None:
        milestones = list((await session.execute(
            select(Milestone)
            .where(Milestone.project_id == project_id)
        )).scalars())

    # Build milestone map for trigger-chain resolution
    _PHASE_ORDER = [
        "offer_made", "under_contract", "close", "pre_development",
        "construction", "operation_lease_up", "operation_stabilized", "divestment",
    ]
    ms_map = {m.id: m for m in milestones}

    # Auto-cap operation_stabilized at 30 years when no divestment milestone exists
    _STABILIZED_AUTO_DAYS = 10950
    _has_divestment = any(
        str(m.milestone_type).replace("MilestoneType.", "") == "divestment"
        for m in milestones
    )
    if not _has_divestment:
        for _m in milestones:
            if (
                str(_m.milestone_type).replace("MilestoneType.", "") == "operation_stabilized"
                and (_m.duration_days or 0) == 0
            ):
                _m.duration_days = _STABILIZED_AUTO_DAYS
                session.add(_m)

    def _phase_idx(m):
        raw = str(m.milestone_type).replace("MilestoneType.", "")
        return next((i for i, v in enumerate(_PHASE_ORDER) if v == raw), 99)

    def _ms_sort_key(m):
        start = m.computed_start(ms_map)
        return (start is None, start or 0, _phase_idx(m))

    milestones = sorted(milestones, key=_ms_sort_key)

    exit_lines = [u for u in use_lines if getattr(u.phase, "value", str(u.phase)) == "exit"]
    deferred_uses = [u for u in use_lines if getattr(u, "is_deferred", False)]
    deferred_total = sum(float(u.amount or 0) for u in deferred_uses)
    revenue_annual = _income_annual(income_streams)
    opex_annual = _sum_annual(expense_lines, "annual_amount")
    capital_total = _capital_total(capital_modules)
    uses_total_val = sum(float(u.amount or 0) for u in use_lines)

    # Equity ownership — computed from equity-type capital modules
    _EQUITY_TYPES = {"preferred_equity", "common_equity", "owner_investment", "owner_loan"}
    equity_modules = [
        m for m in capital_modules
        if str(m.funder_type).replace("FunderType.", "") in _EQUITY_TYPES
    ]
    _total_equity = sum(
        float((m.source or {}).get("amount", 0) or 0) for m in equity_modules
    )
    equity_ownership = [
        {
            "module": m,
            "amount": float((m.source or {}).get("amount", 0) or 0),
            "pct": (float((m.source or {}).get("amount", 0) or 0) / _total_equity * 100)
                   if _total_equity > 0 else 0.0,
        }
        for m in equity_modules
    ]
    # If no equity partners defined, synthesize a 100% org-owner row
    org_owner_fallback = not equity_ownership

    # Load org name for fallback display
    org_name = "Sponsor"
    try:
        from app.models.org import Organization as _Org
        _scenario_for_org = await session.get(DealModel, model_id)
        if _scenario_for_org:
            _deal_for_org = await session.get(Deal, _scenario_for_org.deal_id)
            if _deal_for_org and _deal_for_org.org_id:
                _org = await session.get(_Org, _deal_for_org.org_id)
                if _org:
                    org_name = _org.name
    except Exception:
        pass

    # ── Phase summaries ──────────────────────────────────────────────────────
    # Four logical phases built from milestone types.
    from app.models.milestone import MilestoneType as MT
    _PRE_DEV   = {MT.offer_made, MT.under_contract, MT.close, MT.pre_development}
    _CONSTRUCT = {MT.construction}
    _OPERATION = {MT.operation_lease_up, MT.operation_stabilized}
    _DIVEST    = {MT.divestment}

    def _phase_bucket(types: set) -> list:
        return [m for m in milestones if MT(m.milestone_type) in types]

    def _bucket_summary(bucket: list) -> dict:
        starts = [m.computed_start(ms_map) for m in bucket]
        starts = [s for s in starts if s]
        ends = [m.computed_end(ms_map) for m in bucket]
        ends = [e for e in ends if e]
        if not starts:
            return {"start": None, "end": None, "duration_days": None}
        start = min(starts)
        end = max(ends) if ends else None
        duration_days = (end - start).days if end and start else None
        return {"start": start, "end": end, "duration_days": duration_days}

    pre_dev_bucket  = _phase_bucket(_PRE_DEV)
    construct_bucket = _phase_bucket(_CONSTRUCT)
    operation_bucket = _phase_bucket(_OPERATION)
    divest_bucket    = _phase_bucket(_DIVEST)

    phase_summaries = {
        "pre_dev":      _bucket_summary(pre_dev_bucket),
        "construction": _bucket_summary(construct_bucket),
        "operation":    _bucket_summary(operation_bucket),
        "divestment":   _bucket_summary(divest_bucket),
        "has_divestment": bool(divest_bucket),
    }

    # Total timeline: earliest computed start → latest computed end
    _all_starts = [m.computed_start(ms_map) for m in milestones]
    _all_ends   = [m.computed_end(ms_map)   for m in milestones]
    _all_starts = [s for s in _all_starts if s]
    _all_ends   = [e for e in _all_ends   if e]
    if _all_starts and _all_ends:
        total_timeline_days = (max(_all_ends) - min(_all_starts)).days
    else:
        total_timeline_days = sum(m.duration_days for m in milestones)

    # ── Capital module source bars for Sources & Uses Gantt ─────────────────
    # Each source bar spans active_phase_start → active_phase_end. If no end
    # phase is set the bar extends to the right edge with a fade-out (perpetuity
    # convention for equity / permanent debt). Zero-amount modules are hidden
    # unless explicitly auto-sized (placeholder dashed bar).
    #
    # Phase → (milestone_key, side) mapping:
    # - side="end": the phase begins when that milestone *completes* (e.g.
    #   "acquisition" phase starts when the Close milestone ends — money
    #   changes hands at the end of the closing process).
    # - side="start": the phase begins when that milestone *starts* (e.g.
    #   "construction" phase starts at Construction milestone start).
    _CM_PHASE_TO_MS = {
        "acquisition":          ("close", "end"),
        "pre_development":      ("close", "end"),
        "pre_construction":     ("close", "end"),
        "construction":         ("construction", "start"),
        "lease_up":             ("operation_lease_up", "start"),
        "operation_lease_up":   ("operation_lease_up", "start"),
        "stabilized":           ("operation_stabilized", "start"),
        "operation_stabilized": ("operation_stabilized", "start"),
        "exit":                 ("divestment", "start"),
        "divestment":           ("divestment", "start"),
        "perpetuity":           (None, None),  # never ends on timeline
    }
    _cm_gantt_rows: list[dict] = []
    _bgd_cm = _builder_gantt_from_milestones(default_project, milestones)
    if _bgd_cm and capital_modules:
        _epoch_cm = _bgd_cm.get("epoch")
        _g_min_cm = _bgd_cm.get("g_min", 0)
        _g_max_cm = _bgd_cm.get("g_max", 1)
        _span_cm = max(_g_max_cm - _g_min_cm, 1)
        _ms_start_map: dict = {
            str(m.milestone_type).replace("MilestoneType.", ""): m.computed_start(ms_map)
            for m in milestones
            if m.computed_start(ms_map)
        }
        _ms_end_map: dict = {
            str(m.milestone_type).replace("MilestoneType.", ""): m.computed_end(ms_map)
            for m in milestones
            if m.computed_end(ms_map)
        }

        def _phase_to_date(phase: str | None) -> date | None:
            if not phase:
                return None
            entry = _CM_PHASE_TO_MS.get(phase)
            if not entry:
                return None
            ms_key, side = entry
            if not ms_key:
                return None
            return (_ms_end_map if side == "end" else _ms_start_map).get(ms_key)

        for _cm in capital_modules:
            _src = _cm.source or {}
            _src_amount = float(_src.get("amount") or 0)
            _auto_size = bool(_src.get("auto_size"))
            # Hide $0 sources that aren't marked for auto-sizing (zero means
            # the user hasn't committed this source, so it shouldn't take up
            # a Gantt row).
            if _src_amount <= 0 and not _auto_size:
                continue
            if not _cm.active_phase_start or not _epoch_cm:
                continue
            _from_date = _phase_to_date(_cm.active_phase_start)
            if not _from_date:
                continue
            _from_day = (_from_date - _epoch_cm).days
            _left = max(0.0, round(100.0 * (_from_day - _g_min_cm) / _span_cm, 2))
            _to_date = _phase_to_date(_cm.active_phase_end) if _cm.active_phase_end else None
            if _to_date:
                _to_day = (_to_date - _epoch_cm).days
                _right = min(100.0, round(100.0 * (_to_day - _g_min_cm) / _span_cm, 2))
                _width = max(_right - _left, 1.5)
                _fade = False
            else:
                _width = max(100.0 - _left, 1.5)
                _fade = True
            _ft = str(_cm.funder_type).replace("FunderType.", "")
            _label = (_cm.label or _ft).replace(" (auto)", "").strip()
            _cm_gantt_rows.append({
                "label": _label,
                "source_type": "equity" if "equity" in _ft.lower() else "debt",
                "funder_type": _ft,
                "left_pct": _left,
                "width_pct": _width,
                "fade_right": _fade,
                "unsized": _src_amount <= 0,
            })

    return {
        "inputs": inputs,
        "outputs": outputs,
        "use_lines": use_lines,
        "income_streams": income_streams,
        "expense_lines": expense_lines,
        "unit_mix_rows": unit_mix_rows,
        "capital_modules": capital_modules,
        "waterfall_tiers": waterfall_tiers,
        "milestones": milestones,
        "milestone_rows": [
            {
                "ms": m,
                "start": m.computed_start(ms_map),
                "end": m.computed_end(ms_map),
            }
            for m in milestones
        ],
        "use_line_count": len(use_lines),
        "income_stream_count": len(income_streams),
        "expense_line_count": len(expense_lines),
        "unit_mix_count": len(unit_mix_rows),
        "total_units": sum((u.unit_count or 0) for u in unit_mix_rows),
        "capital_module_count": len(capital_modules),
        "waterfall_tier_count": len(waterfall_tiers),
        "capital_total": capital_total,
        "uses_total": uses_total_val,
        "revenue_annual": revenue_annual,
        "opex_annual": opex_annual,
        "carrying_annual": carrying_annual_computed,
        "carrying_detail": carrying_detail,
        "stabilized_month1_ncf": stabilized_month1_ncf,
        "stabilized_year1_ncf": stabilized_year1_ncf,
        "divestment_total": _sum_amount(exit_lines),
        "profit_total": float(outputs.noi_stabilized) if outputs and outputs.noi_stabilized else None,
        "equity_ownership": equity_ownership,
        "org_owner_fallback": org_owner_fallback,
        "org_name": org_name,
        "deferred_uses": deferred_uses,
        "deferred_total": deferred_total,
        "total_timeline_days": total_timeline_days,
        "total_timeline_months": round(total_timeline_days / 30.4) if total_timeline_days else 0,
        "phase_summaries": phase_summaries,
        "timeline_approved": timeline_approved,
        "deal_setup_complete": bool(getattr(inputs, "deal_setup_complete", False)) if inputs else False,
        "default_project_id": project_id,
        # Approval gate: every milestone needs a position AND a non-zero duration
        "timeline_approvable": len(milestones) > 0 and all(
            (m.target_date or m.trigger_milestone_id) and (m.duration_days or 0) > 0
            for m in milestones
        ),
        "timeline_missing_position": [
            m for m in milestones
            if not m.target_date and not m.trigger_milestone_id
        ],
        "timeline_missing_duration": [
            m for m in milestones
            if not (m.duration_days or 0) > 0
        ],
        # Gantt data for the timeline module panel (Gantt v2)
        "builder_gantt_data": _builder_gantt_from_milestones(default_project, milestones),
        "capital_module_gantt_rows": _cm_gantt_rows,
        # Wizard: show when unapproved and no milestone has a start date yet
        "wizard_needed": (not timeline_approved) and (not any(m.target_date for m in milestones)),
        "wizard_default_types": list(DEFAULT_DURATIONS.get(
            default_project.deal_type if default_project else "", {}
        ).keys()),
        "wizard_deal_type": default_project.deal_type if default_project else "",
        "wizard_deal_type_label": {
            "acquisition_minor_reno": "Acquisition",
            "acquisition_major_reno": "Value-Add",
            "acquisition_conversion": "Conversion",
            "new_construction": "New Construction",
        }.get(default_project.deal_type if default_project else "", "Project"),
        "income_mode": (_scenario.income_mode if _scenario else "revenue_opex") or "revenue_opex",
        "noi_annual": float(inputs.noi_stabilized_input) if inputs and inputs.noi_stabilized_input is not None else None,
    }


@router.post("/ui/forms/{model_id}/{item_type}", response_class=HTMLResponse)
@router.put("/ui/forms/{model_id}/{item_type}/{item_id}", response_class=HTMLResponse)
async def handle_form_create_or_update(
    request: Request,
    model_id: UUID,
    item_type: str,
    session: DBSession,
    item_id: str = "",
) -> HTMLResponse:
    """Accept form-encoded data, persist the mutation, return refreshed panel HTML."""
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    # Resolve default Project for line items that belong to Project level
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    project_id = default_project.id if default_project else None

    form = await request.form()
    module = _ITEM_TYPE_TO_MODULE.get(item_type, "uses")

    if item_type == "use-lines":
        _ms_key = form.get("milestone_key") or None
        _ms_key_to = form.get("milestone_key_to") or None
        # If "to" == "from" or blank, treat as single-point (no range)
        if _ms_key_to == _ms_key:
            _ms_key_to = None
        # Derive phase from milestone_key for backward compat with anything that reads phase
        _milestone_to_phase = {
            "close": "acquisition", "pre_development": "pre_construction",
            "construction": "construction", "renovation": "construction",
            "conversion": "construction", "operation_lease_up": "operation",
            "operation_stabilized": "operation", "divestment": "exit",
            "maturity": "other",
        }
        _phase = _milestone_to_phase.get(_ms_key or "", "") or form.get("phase", "acquisition")
        data: dict = {
            "label": form.get("label", ""),
            "phase": _phase,
            "milestone_key": _ms_key,
            "milestone_key_to": _ms_key_to,
            "amount": _fd(form.get("amount")) or Decimal("0"),
            "timing_type": form.get("timing_type") or "first_day",
            "is_deferred": form.get("is_deferred") == "true",
            "notes": form.get("notes") or None,
        }
        if item_id:
            row = await session.get(UseLine, UUID(item_id))
            if row:
                for k, v in data.items():
                    setattr(row, k, v)
        elif project_id:
            session.add(UseLine(project_id=project_id, **data))

    elif item_type == "income-streams":
        _amount_type = str(form.get("amount_type", "")).strip()
        _per_unit_val = _fd(form.get("amount_per_unit_monthly"))
        _fixed_val = _fd(form.get("amount_fixed_monthly"))
        # Clear the unused field so engine logic is unambiguous.
        if _amount_type == "flat":
            _per_unit_val = None
        elif _amount_type == "per_unit":
            _fixed_val = None
        data = {
            "label": form.get("label", ""),
            "stream_type": form.get("stream_type", "residential_rent"),
            "unit_count": _fi(form.get("unit_count")) or None,
            "amount_per_unit_monthly": _per_unit_val,
            "amount_fixed_monthly": _fixed_val,
            "stabilized_occupancy_pct": _fd(form.get("stabilized_occupancy_pct")) or Decimal("95"),
            "bad_debt_pct": _fd(form.get("bad_debt_pct")) or Decimal("0"),
            "concessions_pct": _fd(form.get("concessions_pct")) or Decimal("0"),
            "catchup_target_rent": _fd(form.get("catchup_target_rent")),
            "renovation_absorption_rate": _fd(form.get("renovation_absorption_rate")),
            "escalation_rate_pct_annual": _fd(form.get("escalation_rate_pct_annual")) or Decimal("0"),
            "active_in_phases": form.getlist("active_in_phases") or _fp(form.get("active_in_phases"), ["stabilized"]),
            "notes": form.get("notes") or None,
        }
        if item_id:
            row = await session.get(IncomeStream, UUID(item_id))
            if row:
                for k, v in data.items():
                    setattr(row, k, v)
        elif project_id:
            session.add(IncomeStream(project_id=project_id, **data))

    elif item_type == "expense-lines":
        _aip_list = form.getlist("active_in_phases")
        active_phases = _aip_list if _aip_list else _fp(form.get("active_in_phases"), ["stabilized"])
        per_type_val = form.get("per_type") or None
        per_value_val = _fd(form.get("per_value"))
        # For flat type, annual_amount mirrors per_value for backward-compat display
        # For per_unit/sqft types, annual_amount stays 0 until compute engine scales it
        if per_value_val and per_type_val in (None, "flat"):
            annual_amt = per_value_val
        else:
            annual_amt = _fd(form.get("annual_amount")) or Decimal("0")
        data = {
            "label": form.get("label", ""),
            "annual_amount": annual_amt,
            "per_value": per_value_val,
            "per_type": per_type_val,
            "scale_with_lease_up": form.get("scale_with_lease_up") == "on",
            "lease_up_floor_pct": _fd(form.get("lease_up_floor_pct")),
            "escalation_rate_pct_annual": _fd(form.get("escalation_rate_pct_annual")) or Decimal("3"),
            "active_in_phases": active_phases,
            "notes": form.get("notes") or None,
        }
        if item_id:
            row = await session.get(OperatingExpenseLine, UUID(item_id))
            if row:
                for k, v in data.items():
                    setattr(row, k, v)
        elif project_id:
            session.add(OperatingExpenseLine(project_id=project_id, **data))

    elif item_type == "capital-modules":
        source_d: dict = {}
        if src_amt := _fd(form.get("source_amount")):
            source_d["amount"] = float(src_amt)
        if src_pct := _fd(form.get("source_pct")):
            source_d["pct_of_total_cost"] = float(src_pct)
        if src_rate := _fd(form.get("source_interest_rate")):
            source_d["interest_rate_pct"] = float(src_rate)
        if cp := form.get("compounding_period"):
            source_d["compounding_period"] = cp
        if amort := _fi(form.get("amort_term_years"), None):
            source_d["amort_term_years"] = amort
        if ppct := _fd(form.get("prepay_penalty_pct")):
            source_d["prepay_penalty_pct"] = float(ppct)
        constr_carry_type = form.get("construction_carry_type", "none")
        # Carry rate: use source rate so the engine finds it in both places
        _carry_rate = _fd(form.get("source_interest_rate"))
        constr_phase: dict = {
            "name": "construction",
            "carry_type": constr_carry_type,
            "payment_frequency": form.get("construction_payment_frequency", "monthly"),
        }
        if _carry_rate is not None:
            constr_phase["io_rate_pct"] = float(_carry_rate)
        if constr_carry_type == "converts_to_permanent":
            if perm_rate := _fd(form.get("perm_rate_pct")):
                constr_phase["perm_rate_pct"] = float(perm_rate)
            if perm_term := _fi(form.get("perm_term_years"), None):
                constr_phase["perm_term_years"] = perm_term
            if perm_trig := form.get("perm_conversion_trigger"):
                constr_phase["perm_conversion_trigger"] = perm_trig
        _op_phase: dict = {
            "name": "operation",
            "carry_type": form.get("operation_carry_type", "none"),
            "payment_frequency": form.get("operation_payment_frequency", "monthly"),
        }
        if _carry_rate is not None:
            _op_phase["io_rate_pct"] = float(_carry_rate)
        carry_d = {
            "phases": [constr_phase, _op_phase],
        }
        # Exit Vehicle: "maturity" | "sale" | "<module_uuid>" (retiring source).
        # Validate: must be one of the literals OR a UUID of another module on
        # the same scenario. Fall back to "maturity" if invalid.
        _vehicle_raw = (form.get("exit_vehicle") or "").strip()
        _vehicle_value = "maturity"
        if _vehicle_raw in {"maturity", "sale"}:
            _vehicle_value = _vehicle_raw
        elif _vehicle_raw:
            try:
                _vehicle_uuid = UUID(_vehicle_raw)
                # Ensure it refers to another capital module on this scenario
                _sibling = (await session.execute(
                    select(CapitalModule.id).where(
                        CapitalModule.scenario_id == model_id,
                        CapitalModule.id == _vehicle_uuid,
                    )
                )).scalar_one_or_none()
                if _sibling is not None and (not item_id or str(_sibling) != item_id):
                    _vehicle_value = str(_sibling)
            except (ValueError, AttributeError):
                pass
        exit_d = {
            "exit_type": form.get("exit_type", "full_payoff"),
            "vehicle": _vehicle_value,
        }
        explicit_pos = _fi(form.get("stack_position"), None)
        if not item_id and (not explicit_pos or explicit_pos == 0):
            # Auto-assign: place at end of current stack
            max_pos_result = await session.execute(
                select(func.max(CapitalModule.stack_position)).where(CapitalModule.scenario_id == model_id)
            )
            max_pos = max_pos_result.scalar_one_or_none() or 0
            explicit_pos = max_pos + 1
        final_pos = explicit_pos or 1
        # Uniqueness: if another module already holds this position, shift it up to avoid conflict
        conflict_stmt = (
            select(CapitalModule)
            .where(CapitalModule.scenario_id == model_id, CapitalModule.stack_position == final_pos)
        )
        if item_id:
            conflict_stmt = conflict_stmt.where(CapitalModule.id != UUID(item_id))
        if (await session.execute(conflict_stmt)).scalars().first() is not None:
            # Auto-bump to next available position
            max_pos_result = await session.execute(
                select(func.max(CapitalModule.stack_position)).where(CapitalModule.scenario_id == model_id)
            )
            final_pos = (max_pos_result.scalar_one_or_none() or 0) + 1
        data = {
            "label": form.get("label", ""),
            "funder_type": form.get("funder_type", "senior_debt"),
            "stack_position": final_pos,
            "source": source_d,
            "carry": carry_d,
            "exit_terms": exit_d,
        }
        # Draw schedule fields from form
        _ds_from_ms = form.get("ds_active_from_milestone") or ""
        _ds_to_ms = form.get("ds_active_to_milestone") or ""
        _ds_from_offset = _fi(form.get("ds_active_from_offset_days"), 0) or 0
        _ds_to_offset = _fi(form.get("ds_active_to_offset_days"), 0) or 0
        _ds_frequency = _fi(form.get("ds_draw_every_n_months"), 1) or 1
        _ds_rate = source_d.get("interest_rate_pct", 0.0)

        if item_id:
            row = await session.get(CapitalModule, UUID(item_id))
            if row:
                # Preserve internal-only source keys (auto_size) not exposed in the UI form
                if (row.source or {}).get("auto_size"):
                    source_d["auto_size"] = True
                data["source"] = source_d
                for k, v in data.items():
                    setattr(row, k, v)
            # Update matching DrawSource (active window, offsets, frequency)
            _ds_id_raw = str(form.get("ds_id") or "").strip()
            if _ds_id_raw:
                try:
                    _ds_row = await session.get(DrawSource, UUID(_ds_id_raw))
                    if _ds_row and _ds_row.scenario_id == model_id:
                        if _ds_from_ms:
                            _ds_row.active_from_milestone = _ds_from_ms
                        if _ds_to_ms:
                            _ds_row.active_to_milestone = _ds_to_ms
                        _ds_row.active_from_offset_days = _ds_from_offset
                        _ds_row.active_to_offset_days = _ds_to_offset
                        _ds_row.draw_every_n_months = _ds_frequency
                        _ds_row.annual_interest_rate = Decimal(str(_ds_rate))
                        _ds_row.funder_type = data["funder_type"]
                        _ds_row.label = data["label"]
                except (ValueError, TypeError):
                    pass
        else:
            _cm_id = _uuid_mod.uuid4()
            cm = CapitalModule(id=_cm_id, scenario_id=model_id, **data)
            session.add(cm)
            # Auto-create linked DrawSource
            _src_type = "equity" if data["funder_type"] in (
                "common_equity", "preferred_equity", "owner_investment",
                "grant", "tax_credit",
            ) else "debt"
            # Determine sort order for new DrawSource
            _max_sort = (await session.execute(
                select(func.max(DrawSource.sort_order)).where(DrawSource.scenario_id == model_id)
            )).scalar_one_or_none() or 0
            ds = DrawSource(
                scenario_id=model_id,
                label=data["label"],
                source_type=_src_type,
                sort_order=_max_sort + 1,
                draw_every_n_months=_ds_frequency,
                annual_interest_rate=Decimal(str(_ds_rate)),
                active_from_milestone=_ds_from_ms or "construction",
                active_to_milestone=_ds_to_ms or "maturity",
                active_from_offset_days=_ds_from_offset,
                active_to_offset_days=_ds_to_offset,
                funder_type=data["funder_type"],
                capital_module_id=_cm_id,
            )
            session.add(ds)

    elif item_type == "waterfall-tiers":
        data = {
            "priority": _fi(form.get("priority"), 1),
            "tier_type": form.get("tier_type", "residual"),
            "description": form.get("description") or None,
            "lp_split_pct": _fd(form.get("lp_split_pct")) or Decimal("0"),
            "gp_split_pct": _fd(form.get("gp_split_pct")) or Decimal("0"),
            "irr_hurdle_pct": _fd(form.get("irr_hurdle_pct")),
            "max_pct_of_distributable": _fd(form.get("max_pct_of_distributable")),
            "interest_rate_pct": _fd(form.get("interest_rate_pct")),
        }
        if item_id:
            row = await session.get(WaterfallTier, UUID(item_id))
            if row:
                for k, v in data.items():
                    setattr(row, k, v)
        else:
            session.add(WaterfallTier(scenario_id=model_id, **data))

    elif item_type == "milestones":
        from datetime import date as _date
        def _parse_date(v: str | None) -> _date | None:
            if not v or not v.strip():
                return None
            try:
                return _date.fromisoformat(v.strip()[:10])
            except ValueError:
                return None

        mtype_raw = form.get("milestone_type", "construction")
        try:
            mtype = MilestoneType(mtype_raw)
        except ValueError:
            mtype = MilestoneType.construction

        trigger_raw = str(form.get("trigger_milestone_id") or "").strip()
        try:
            trigger_id = UUID(trigger_raw) if trigger_raw else None
        except ValueError:
            trigger_id = None

        data = {
            "duration_days": _fi(form.get("duration_days"), 0),
            "milestone_type": mtype,
            "trigger_milestone_id": trigger_id,
            "trigger_offset_days": _fi(form.get("trigger_offset_days"), 0),
            # anchor: keep target_date only when no trigger; clear it when trigger set
            "target_date": _parse_date(str(form.get("target_date") or "")) if not trigger_id else None,
        }
        if item_id:
            row = await session.get(Milestone, UUID(item_id))
            if row:
                for k, v in data.items():
                    setattr(row, k, v)
        elif project_id:
            session.add(Milestone(
                project_id=project_id,
                sequence_order=0,
                **data,
            ))

    elif item_type == "unit-mix":
        data = {
            "label": form.get("label", "").strip() or "Units",
            "unit_count": _fi(form.get("unit_count"), 1) or 1,
            "avg_sqft": _fd(form.get("avg_sqft")),
            "beds": _fd(form.get("beds")),
            "baths": _fd(form.get("baths")),
            "market_rent_per_unit": _fd(form.get("market_rent_per_unit")),
            "in_place_rent_per_unit": _fd(form.get("in_place_rent_per_unit")),
            "unit_strategy": form.get("unit_strategy") or None,
            "post_reno_rent_per_unit": _fd(form.get("post_reno_rent_per_unit")),
            "notes": form.get("notes") or None,
        }
        if item_id:
            row = await session.get(UnitMix, UUID(item_id))
            if row:
                for k, v in data.items():
                    setattr(row, k, v)
        elif project_id:
            session.add(UnitMix(project_id=project_id, **data))

    await session.flush()
    panel_data = await _load_builder_data(session, model_id)
    ctx = {"model": model, "active_module": module, **panel_data}
    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


@router.delete("/ui/forms/{model_id}/{item_type}/{item_id}", response_class=HTMLResponse)
async def handle_form_delete(
    request: Request,
    model_id: UUID,
    item_type: str,
    item_id: str,
    session: DBSession,
) -> HTMLResponse:
    """Delete a line item and return the refreshed panel HTML."""
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    module = _ITEM_TYPE_TO_MODULE.get(item_type, "uses")
    uid = UUID(item_id)

    row = None
    if item_type == "use-lines":
        row = await session.get(UseLine, uid)
    elif item_type == "income-streams":
        row = await session.get(IncomeStream, uid)
    elif item_type == "expense-lines":
        row = await session.get(OperatingExpenseLine, uid)
    elif item_type == "capital-modules":
        row = await session.get(CapitalModule, uid)
    elif item_type == "waterfall-tiers":
        row = await session.get(WaterfallTier, uid)
    elif item_type == "milestones":
        row = await session.get(Milestone, uid)
    elif item_type == "unit-mix":
        row = await session.get(UnitMix, uid)

    if row is not None:
        await session.delete(row)
        await session.flush()

    panel_data = await _load_builder_data(session, model_id)
    ctx = {"model": model, "active_module": module, **panel_data}
    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


@router.post("/ui/models/{model_id}/unit-mix/apply-to-revenue", response_class=HTMLResponse)
async def apply_unit_mix_to_revenue(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Auto-generate IncomeStream rows from each UnitMix row's strategy.

    Strategy mapping:
      - base_escalation:       stream at in_place rent, normal escalation
      - ltl_catchup:           stream at in_place rent, catchup_target_rent = market
      - value_add_renovation:  stream at post_reno rent, renovation_absorption_rate = 1.0

    Existing streams labeled "{unit_label} Rent" are deleted and replaced —
    this is deterministic: run the same UnitMix config, get the same streams.
    One-off streams (e.g. "Parking", "Laundry") with non-matching labels
    are preserved.
    """
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    if default_project is None:
        return HTMLResponse("<p class='text-muted'>No project.</p>", status_code=400)

    unit_mix_rows = list((await session.execute(
        select(UnitMix).where(UnitMix.project_id == default_project.id).order_by(UnitMix.label)
    )).scalars())
    if not unit_mix_rows:
        panel_data = await _load_builder_data(session, model_id)
        ctx = {"model": model, "active_module": "property", **panel_data}
        return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)

    # Collect labels we'll generate so we can purge stale auto-generated streams
    to_generate: list[dict] = []
    for u in unit_mix_rows:
        strategy = (u.unit_strategy or "base_escalation")
        label = f"{u.label} Rent"
        count = int(u.unit_count or 0)
        if count <= 0:
            continue

        ip_rent = _to_decimal_or_none(u.in_place_rent_per_unit)
        mkt_rent = _to_decimal_or_none(u.market_rent_per_unit)
        post_reno = _to_decimal_or_none(u.post_reno_rent_per_unit)

        if strategy == "value_add_renovation":
            # Post-reno rent is the target; fall back to market if unset
            base_rent = post_reno or mkt_rent or ip_rent
            stream = dict(
                label=f"{u.label} Rent (Renovated)",
                stream_type=IncomeStreamType.residential_rent,
                unit_count=count,
                amount_per_unit_monthly=base_rent,
                stabilized_occupancy_pct=Decimal("95"),
                escalation_rate_pct_annual=Decimal("3"),
                renovation_absorption_rate=Decimal("1"),
                active_in_phases=["lease_up", "stabilized"],
            )
        elif strategy == "ltl_catchup":
            stream = dict(
                label=label,
                stream_type=IncomeStreamType.residential_rent,
                unit_count=count,
                amount_per_unit_monthly=(ip_rent or mkt_rent or Decimal("0")),
                stabilized_occupancy_pct=Decimal("95"),
                catchup_target_rent=mkt_rent,
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["lease_up", "stabilized"],
            )
        else:  # base_escalation
            stream = dict(
                label=label,
                stream_type=IncomeStreamType.residential_rent,
                unit_count=count,
                amount_per_unit_monthly=(ip_rent or mkt_rent or Decimal("0")),
                stabilized_occupancy_pct=Decimal("95"),
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["lease_up", "stabilized"],
            )
        to_generate.append(stream)

    # Delete existing auto-generated streams (matching labels) to keep this idempotent
    generated_labels = {s["label"] for s in to_generate}
    if generated_labels:
        existing_to_delete = list((await session.execute(
            select(IncomeStream).where(
                IncomeStream.project_id == default_project.id,
                IncomeStream.label.in_(generated_labels),
            )
        )).scalars())
        for row in existing_to_delete:
            await session.delete(row)
        await session.flush()

    # Create fresh streams
    for data in to_generate:
        session.add(IncomeStream(project_id=default_project.id, **data))
    await session.flush()

    # Return the refreshed Property panel so the user stays oriented
    panel_data = await _load_builder_data(session, model_id)
    ctx = {"model": model, "active_module": "property", **panel_data}
    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


def _to_decimal_or_none(v) -> Decimal | None:
    """Coerce a numeric value to Decimal, or None if zero/missing."""
    if v is None:
        return None
    try:
        d = Decimal(str(v))
        return d if d != 0 else None
    except Exception:
        return None


@router.post("/ui/models/{model_id}/sensitivity/run", response_class=HTMLResponse)
async def run_sensitivity_analysis(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Run a 5x5 sensitivity compute and persist the result as JSON on
    OperationalOutputs.sensitivity_matrix. Returns the refreshed Sensitivity
    panel so the user sees results inline."""
    from app.engines.sensitivity_matrix import compute_sensitivity_matrix

    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    form = await request.form()
    axis_x = form.get("axis_x") or "noi_escalation_rate_pct"
    axis_y = form.get("axis_y") or "exit_cap_rate_pct"
    metric = form.get("metric") or "project_irr_levered"

    try:
        matrix = await compute_sensitivity_matrix(
            deal_model_id=model_id,
            session=session,
            axis_x=axis_x,
            axis_y=axis_y,
            metric=metric,
        )
    except ValueError as e:
        # Bad axis/metric combo — surface the error in the panel
        panel_data = await _load_builder_data(session, model_id)
        ctx = {"model": model, "active_module": "sensitivity", **panel_data,
               "sensitivity_error": str(e)}
        return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)

    # Persist on OperationalOutputs.sensitivity_matrix (JSON column).
    # compute_sensitivity_matrix runs a final compute_cash_flows so a fresh
    # OperationalOutputs row now exists.
    outputs = (await session.execute(
        select(OperationalOutputs).where(OperationalOutputs.scenario_id == model_id)
    )).scalar_one_or_none()
    if outputs is not None:
        outputs.sensitivity_matrix = matrix
        session.add(outputs)
        await session.flush()

    panel_data = await _load_builder_data(session, model_id)
    ctx = {"model": model, "active_module": "sensitivity", **panel_data}
    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


async def _get_missing_building_data(
    project: Project,
    session: AsyncSession,
) -> list[dict]:
    """Return list of dicts describing buildings assigned to this project that are missing
    unit_count or building_sqft. Used to gate the deal setup wizard with a data-entry step."""
    assigned_buildings = (await session.execute(
        select(Building)
        .join(ProjectBuildingAssignment, ProjectBuildingAssignment.building_id == Building.id)
        .where(ProjectBuildingAssignment.project_id == project.id)
        .order_by(ProjectBuildingAssignment.sort_order)
    )).scalars().all()
    missing = []
    for b in assigned_buildings:
        fields = []
        if not b.unit_count:
            fields.append("unit_count")
        if not b.building_sqft:
            fields.append("building_sqft")
        if fields:
            missing.append({
                "id": str(b.id),
                "label": b.address_line1 or "Building",
                "fields": fields,
                "net_rentable_sqft": float(b.net_rentable_sqft) if b.net_rentable_sqft else None,
            })
    return missing


async def _auto_assign_opportunity_to_project(
    opportunity: Opportunity,
    project: Project,
    session: AsyncSession,
) -> None:
    """Seed ProjectBuildingAssignment and ProjectParcelAssignment from an Opportunity's linked data.

    Called whenever a new Project is created so that project-scoped unit counts and parcel data
    are available immediately. A building/parcel can be assigned to multiple Projects (variants).
    """
    # Buildings via OpportunityBuilding join table
    opp_buildings = (await session.execute(
        select(OpportunityBuilding)
        .where(OpportunityBuilding.opportunity_id == opportunity.id)
        .order_by(OpportunityBuilding.sort_order)
    )).scalars().all()
    for i, ob in enumerate(opp_buildings):
        session.add(ProjectBuildingAssignment(
            project_id=project.id, building_id=ob.building_id, sort_order=i
        ))

    # Parcels via existing ProjectParcel (opportunity-level FK = opportunities.id)
    opp_parcels = (await session.execute(
        select(ProjectParcel).where(ProjectParcel.project_id == opportunity.id)
    )).scalars().all()
    for i, op in enumerate(opp_parcels):
        session.add(ProjectParcelAssignment(
            project_id=project.id, parcel_id=op.parcel_id, sort_order=i
        ))


async def _copy_project_data(
    src_proj: Project,
    dst_proj: Project,
    session: AsyncSession,
) -> None:
    """Copy milestones (with trigger remapping), use lines, income streams,
    expense lines, and operational inputs from src_proj to dst_proj.
    Caller is responsible for deleting dst_proj's existing data first."""
    # Copy milestones (preserve trigger chain with remapped IDs)
    src_milestones = list((await session.execute(
        select(Milestone).where(Milestone.project_id == src_proj.id)
    )).scalars())
    ms_id_map: dict = {}
    for ms in src_milestones:
        new_ms = Milestone(
            project_id=dst_proj.id,
            milestone_type=ms.milestone_type,
            label=ms.label,
            target_date=ms.target_date,
            duration_days=ms.duration_days,
            sequence_order=ms.sequence_order,
        )
        session.add(new_ms)
        await session.flush()
        ms_id_map[ms.id] = new_ms.id

    # Resolve trigger_milestone_id after all are created
    for ms in src_milestones:
        if ms.trigger_milestone_id and ms.trigger_milestone_id in ms_id_map:
            new_ms_obj = await session.get(Milestone, ms_id_map[ms.id])
            if new_ms_obj:
                new_ms_obj.trigger_milestone_id = ms_id_map[ms.trigger_milestone_id]
                new_ms_obj.trigger_offset_days = ms.trigger_offset_days

    # Copy Use lines
    for u in (await session.execute(
        select(UseLine).where(UseLine.project_id == src_proj.id)
    )).scalars():
        session.add(UseLine(
            project_id=dst_proj.id,
            label=u.label, phase=u.phase,
            amount=u.amount, is_deferred=u.is_deferred, notes=u.notes,
        ))

    # Copy Income streams
    for s in (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == src_proj.id)
    )).scalars():
        session.add(IncomeStream(
            project_id=dst_proj.id,
            stream_type=s.stream_type, label=s.label,
            unit_count=s.unit_count,
            amount_per_unit_monthly=s.amount_per_unit_monthly,
            amount_fixed_monthly=s.amount_fixed_monthly,
            stabilized_occupancy_pct=s.stabilized_occupancy_pct,
            escalation_rate_pct_annual=s.escalation_rate_pct_annual,
            active_in_phases=s.active_in_phases, notes=s.notes,
        ))

    # Copy Expense lines
    for e in (await session.execute(
        select(OperatingExpenseLine).where(OperatingExpenseLine.project_id == src_proj.id)
    )).scalars():
        session.add(OperatingExpenseLine(
            project_id=dst_proj.id,
            label=e.label, annual_amount=e.annual_amount,
            escalation_rate_pct_annual=e.escalation_rate_pct_annual,
            active_in_phases=e.active_in_phases, notes=e.notes,
        ))

    # Copy OperationalInputs if any
    src_inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == src_proj.id)
    )).scalar_one_or_none()
    if src_inputs:
        new_inputs = OperationalInputs(project_id=dst_proj.id)
        skip = {"id", "project_id"}
        for col in OperationalInputs.__table__.columns:
            if col.name not in skip:
                setattr(new_inputs, col.name, getattr(src_inputs, col.name, None))
        session.add(new_inputs)


@router.post("/ui/deals/{deal_id}/variant", response_class=HTMLResponse)
async def create_deal_copy(
    request: Request,
    deal_id: UUID,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    """Deep-copy a Scenario into a new Scenario with the same Projects, milestones, and line items."""
    from decimal import Decimal as _Dec
    source = await session.get(DealModel, deal_id)
    if source is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    user = await _get_user(session, request)
    form = await request.form()
    variant_name = str(form.get("name", "")).strip() or f"{source.name} (Copy)"
    selected_project_ids = set(form.getlist("project_ids"))

    # New Scenario under same top-level Deal
    new_deal = DealModel(
        deal_id=source.deal_id,
        name=variant_name,
        project_type=source.project_type,
        version=source.version + 1,
        is_active=False,
        created_by_user_id=user.id if user else None,
    )
    session.add(new_deal)
    await session.flush()

    # Copy Projects (all if none selected, otherwise only checked ones)
    source_projects = list((await session.execute(
        select(Project).where(Project.scenario_id == deal_id).order_by(Project.created_at.asc())
    )).scalars())
    if selected_project_ids:
        source_projects = [p for p in source_projects if str(p.id) in selected_project_ids]

    for src_proj in source_projects:
        new_proj = Project(
            scenario_id=new_deal.id,
            opportunity_id=src_proj.opportunity_id,
            name=src_proj.name,
            deal_type=src_proj.deal_type,
            timeline_approved=src_proj.timeline_approved,
        )
        session.add(new_proj)
        await session.flush()

        await _copy_project_data(src_proj, new_proj, session)

    # Copy Scenario-level Capital modules
    for cm in (await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == deal_id)
    )).scalars():
        session.add(CapitalModule(
            scenario_id=new_deal.id,
            label=cm.label, funder_type=cm.funder_type,
            stack_position=cm.stack_position,
            source=cm.source, carry=cm.carry, exit_terms=cm.exit_terms,
            active_phase_start=cm.active_phase_start,
            active_phase_end=cm.active_phase_end,
        ))

    # Copy Scenario-level Waterfall tiers
    for t in (await session.execute(
        select(WaterfallTier).where(WaterfallTier.scenario_id == deal_id)
    )).scalars():
        session.add(WaterfallTier(
            scenario_id=new_deal.id,
            priority=t.priority, tier_type=t.tier_type,
            irr_hurdle_pct=t.irr_hurdle_pct,
            lp_split_pct=t.lp_split_pct, gp_split_pct=t.gp_split_pct,
            description=t.description,
            max_pct_of_distributable=t.max_pct_of_distributable,
            interest_rate_pct=t.interest_rate_pct,
        ))

    await session.commit()
    return RedirectResponse(url=f"/models/{new_deal.id}/builder", status_code=303)


@router.post("/ui/deals/{deal_id}/new-project", response_class=HTMLResponse)
async def create_deal_project(
    request: Request,
    deal_id: UUID,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    """Add a new Project to an existing Scenario (max 5). Redirects to builder with timeline wizard."""
    deal = await session.get(DealModel, deal_id)
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    project_count = int((await session.execute(
        select(func.count()).select_from(Project).where(Project.scenario_id == deal_id)
    )).scalar_one())
    if project_count >= 5:
        return HTMLResponse("<p class='text-muted'>Maximum 5 projects per deal.</p>", status_code=400)

    form = await request.form()
    project_name = str(form.get("name", "")).strip() or f"Project {project_count + 1}"

    try:
        pt = ProjectType(str(form.get("deal_type", "")))
    except ValueError:
        try:
            pt = ProjectType(str(deal.project_type))
        except ValueError:
            pt = ProjectType.acquisition_minor_reno

    # Find opportunity via existing projects for this scenario
    _existing_proj = (await session.execute(
        select(Project).where(Project.scenario_id == deal_id).limit(1)
    )).scalar_one_or_none()
    _opp_id = _existing_proj.opportunity_id if _existing_proj else None

    new_proj = Project(
        scenario_id=deal_id,
        opportunity_id=_opp_id,
        name=project_name,
        deal_type=pt.value,
    )
    session.add(new_proj)
    await session.flush()

    for milestone in _seed_milestones(new_proj, pt):
        session.add(milestone)
    await session.flush()

    return RedirectResponse(
        url=f"/models/{deal_id}/builder?project={new_proj.id}", status_code=303
    )


@router.post("/ui/deals/{deal_id}/project/{project_id}/clone-from", response_class=HTMLResponse)
async def clone_project_from(
    deal_id: UUID,
    project_id: UUID,
    request: Request,
    session: DBSession,
) -> HTMLResponse:
    """Replace target project's financial data with a copy from another project in the same scenario."""
    from sqlalchemy import delete as sa_delete

    form = await request.form()
    source_project_id_raw = str(form.get("source_project_id", "")).strip()
    if not source_project_id_raw:
        return HTMLResponse("<p class='text-muted'>No source project selected.</p>", status_code=400)
    try:
        source_project_id = UUID(source_project_id_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid source project ID.</p>", status_code=400)

    target_proj = await session.get(Project, project_id)
    source_proj = await session.get(Project, source_project_id)

    if target_proj is None or source_proj is None:
        return HTMLResponse("<p class='text-muted'>Project not found.</p>", status_code=404)
    if target_proj.scenario_id != deal_id or source_proj.scenario_id != deal_id:
        return HTMLResponse("<p class='text-muted'>Projects must belong to the same scenario.</p>", status_code=400)
    if target_proj.id == source_proj.id:
        return HTMLResponse("<p class='text-muted'>Cannot clone a project onto itself.</p>", status_code=400)

    # Clear existing data on target
    await session.execute(sa_delete(Milestone).where(Milestone.project_id == project_id))
    await session.execute(sa_delete(UseLine).where(UseLine.project_id == project_id))
    await session.execute(sa_delete(IncomeStream).where(IncomeStream.project_id == project_id))
    await session.execute(sa_delete(OperatingExpenseLine).where(OperatingExpenseLine.project_id == project_id))
    await session.execute(sa_delete(UnitMix).where(UnitMix.project_id == project_id))
    await session.execute(sa_delete(OperationalInputs).where(OperationalInputs.project_id == project_id))
    await session.flush()

    # Copy from source
    await _copy_project_data(source_proj, target_proj, session)
    await session.flush()

    return RedirectResponse(url=f"/models/{deal_id}/builder?project={project_id}", status_code=303)


@router.post("/ui/deals/{deal_id}/split-projects", response_class=HTMLResponse)
async def split_multiparcel_projects(
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Split a multi-APN listing into one Project per parcel in the same Scenario."""
    import re as _re

    scenario = await session.get(DealModel, deal_id)
    if scenario is None:
        return HTMLResponse("")

    # Get existing single project
    existing_proj = (await session.execute(
        select(Project).where(Project.scenario_id == deal_id).order_by(Project.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    if existing_proj is None:
        return HTMLResponse("")

    # Find the linked listing's APN via the opportunity's scraped listings
    opp = await session.get(Opportunity, existing_proj.opportunity_id) if existing_proj.opportunity_id else None
    if opp is None:
        return HTMLResponse("")

    listing = (await session.execute(
        select(ScrapedListing)
        .where(ScrapedListing.linked_project_id == existing_proj.opportunity_id)
        .order_by(ScrapedListing.last_seen_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if listing is None or not listing.apn or not _re.search(r"[,;]", listing.apn):
        return HTMLResponse("")

    apns = [a.strip() for a in _re.split(r"[,;]", listing.apn) if a.strip()]
    if len(apns) < 2:
        return HTMLResponse("")

    try:
        pt = ProjectType(existing_proj.deal_type)
    except ValueError:
        pt = ProjectType.acquisition_minor_reno

    # Rename existing project to include first APN and seed its assignments
    existing_proj.name = f"Project 1 — {apns[0]}"
    # Ensure the first project has building/parcel assignments (may not if created pre-feature)
    existing_has_assignments = await session.scalar(
        select(func.count()).select_from(ProjectBuildingAssignment)
        .where(ProjectBuildingAssignment.project_id == existing_proj.id)
    ) or 0
    if existing_has_assignments == 0:
        await _auto_assign_opportunity_to_project(opp, existing_proj, session)

    # Parcel lookup helper: find parcel by APN for per-project scoping
    async def _parcel_for_apn(apn: str) -> "Parcel | None":
        return (await session.execute(
            select(Parcel).where(Parcel.apn == apn).limit(1)
        )).scalar_one_or_none()

    # Create one new project per remaining APN
    for i, apn in enumerate(apns[1:], start=2):
        proj_count = await session.scalar(
            select(func.count()).select_from(Project).where(Project.scenario_id == deal_id)
        ) or 0
        if proj_count >= 5:
            break
        new_proj = Project(
            scenario_id=deal_id,
            opportunity_id=existing_proj.opportunity_id,
            name=f"Project {i} — {apn}",
            deal_type=pt.value,
        )
        session.add(new_proj)
        await session.flush()
        # Assign all buildings + this project's specific parcel (if found)
        await _auto_assign_opportunity_to_project(opp, new_proj, session)
        parcel = await _parcel_for_apn(apn)
        if parcel:
            # Ensure we don't double-assign the same parcel (auto-assign adds all opportunity parcels)
            already = await session.scalar(
                select(func.count()).select_from(ProjectParcelAssignment)
                .where(ProjectParcelAssignment.project_id == new_proj.id)
                .where(ProjectParcelAssignment.parcel_id == parcel.id)
            ) or 0
            if already == 0:
                session.add(ProjectParcelAssignment(project_id=new_proj.id, parcel_id=parcel.id))
        for milestone in _seed_milestones(new_proj, pt):
            session.add(milestone)

    # Suppress banner
    opp.multi_parcel_dismissed = True
    await session.flush()

    return RedirectResponse(url=f"/models/{deal_id}/builder", status_code=303)


@router.post("/ui/deals/{deal_id}/dismiss-multiparcel", response_class=HTMLResponse)
async def dismiss_multiparcel_banner(
    deal_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Suppress the multi-parcel banner for this opportunity."""
    scenario = await session.get(DealModel, deal_id)
    if scenario is not None:
        proj = (await session.execute(
            select(Project).where(Project.scenario_id == deal_id).limit(1)
        )).scalar_one_or_none()
        if proj and proj.opportunity_id:
            opp = await session.get(Opportunity, proj.opportunity_id)
            if opp:
                opp.multi_parcel_dismissed = True
                await session.flush()
    return HTMLResponse("")  # replaces the banner with nothing


@router.post("/ui/models/{model_id}/stack-order", response_class=HTMLResponse)
async def save_stack_order(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Batch-update stack_position for all capital modules from a confirm-order form submission."""
    form = await request.form()
    modules = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == model_id)
    )).scalars())
    for m in modules:
        key = f"pos_{m.id}"
        if val := _fi(form.get(key), None):
            m.stack_position = val
    await session.flush()
    ctx = await _load_builder_data(session, model_id)
    ctx["request"] = request
    ctx["active_module"] = "sources"
    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


@router.post("/ui/models/{model_id}/capital-modules/reorder", response_class=HTMLResponse)
async def reorder_capital_modules(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Drag-reorder capital modules — receives ordered list of IDs, assigns stack_position 1..N."""
    form = await request.form()
    ordered_ids = form.getlist("order")
    for i, id_str in enumerate(ordered_ids, start=1):
        try:
            mod = await session.get(CapitalModule, UUID(id_str))
            if mod and mod.scenario_id == model_id:
                mod.stack_position = i
        except (ValueError, Exception):
            pass
    await session.flush()
    ctx = await _load_builder_data(session, model_id)
    ctx["request"] = request
    ctx["active_module"] = "sources"
    model = await session.get(DealModel, model_id)
    return templates.TemplateResponse(
        request, "partials/model_builder_panel.html",
        {"model": model, "active_module": "sources", **ctx}
    )


@router.post("/ui/models/{model_id}/settings", response_class=HTMLResponse)
async def save_model_settings(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Save model name, project type, and scalar operational inputs from the Settings drawer."""
    form = await request.form()
    name = str(form.get("name", "")).strip()
    deal_type_raw = str(form.get("deal_type", "")).strip()
    expense_growth = form.get("expense_growth_rate_pct_annual")
    exit_cap = form.get("exit_cap_rate_pct")
    hold_period = form.get("hold_period_years")
    debt_structure = str(form.get("debt_structure") or "").strip() or None
    debt_sizing_mode = str(form.get("debt_sizing_mode") or "").strip() or None
    dscr_minimum = form.get("dscr_minimum")
    operation_reserve_months = form.get("operation_reserve_months")
    perm_rate_pct = form.get("perm_rate_pct")
    construction_rate_pct = form.get("construction_rate_pct")
    perm_amort_years = form.get("perm_amort_years")

    deal = await session.get(DealModel, model_id)
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Not found.</p>", status_code=404)

    if name:
        deal.name = name
    if deal_type_raw:
        try:
            deal.project_type = ProjectType(deal_type_raw)
        except ValueError:
            pass

    await session.flush()

    # Update OperationalInputs for the default project
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    if default_project:
        if deal_type_raw:
            try:
                default_project.deal_type = deal_type_raw
            except Exception:
                pass

        inputs = (await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
        )).scalar_one_or_none()
        if inputs is None:
            inputs = OperationalInputs(project_id=default_project.id)
            session.add(inputs)

        if expense_growth is not None:
            try:
                inputs.expense_growth_rate_pct_annual = float(expense_growth)
            except (ValueError, TypeError):
                pass
        if exit_cap is not None:
            try:
                inputs.exit_cap_rate_pct = float(exit_cap)
            except (ValueError, TypeError):
                pass
        if hold_period is not None:
            try:
                hold_years = float(hold_period)
                inputs.hold_period_years = hold_years
                # Sync operation_stabilized milestone duration to match hold period
                from app.models.milestone import Milestone as _Milestone
                stabilized_ms = (await session.execute(
                    select(_Milestone).where(
                        _Milestone.project_id == default_project.id,
                        _Milestone.milestone_type == "operation_stabilized",
                    )
                )).scalar_one_or_none()
                if stabilized_ms is not None:
                    stabilized_ms.duration_days = round(hold_years * 365)
            except (ValueError, TypeError):
                pass

        if debt_structure:
            inputs.debt_structure = debt_structure
        if debt_sizing_mode:
            inputs.debt_sizing_mode = debt_sizing_mode
        if dscr_minimum:
            try:
                inputs.dscr_minimum = Decimal(dscr_minimum)
            except Exception:
                pass
        if operation_reserve_months:
            try:
                inputs.operation_reserve_months = int(operation_reserve_months)
            except Exception:
                pass
        # Update debt_terms dict if rates/amort changed
        if perm_rate_pct or construction_rate_pct or perm_amort_years:
            dt = dict(inputs.debt_terms or {})
            if perm_rate_pct:
                try:
                    dt["perm_rate_pct"] = float(perm_rate_pct)
                except Exception:
                    pass
            if construction_rate_pct:
                try:
                    dt["construction_rate_pct"] = float(construction_rate_pct)
                except Exception:
                    pass
            if perm_amort_years:
                try:
                    dt["perm_amort_years"] = int(perm_amort_years)
                except Exception:
                    pass
            inputs.debt_terms = dt
        # Sync auto-sized CapitalModules to match updated debt terms
        if any([perm_rate_pct, construction_rate_pct, perm_amort_years, debt_structure]):
            auto_mods = list((await session.execute(
                select(CapitalModule).where(CapitalModule.scenario_id == model_id)
            )).scalars())
            dt = inputs.debt_terms or {}
            for cm in auto_mods:
                src = cm.source or {}
                if not src.get("auto_size"):
                    continue
                src = dict(src)
                carry = dict(cm.carry or {})
                ft = str(cm.funder_type).replace("FunderType.", "")
                if ft in ("bond",) and perm_rate_pct:
                    src["interest_rate_pct"] = float(perm_rate_pct)
                    if "phases" in carry:
                        for ph in carry["phases"]:
                            if ph.get("name") == "operation":
                                if perm_rate_pct:
                                    ph["io_rate_pct"] = float(perm_rate_pct)
                                if perm_amort_years:
                                    ph["amort_term_years"] = int(perm_amort_years)
                            elif ph.get("name") == "construction" and construction_rate_pct:
                                ph["io_rate_pct"] = float(construction_rate_pct)
                elif ft in ("permanent_debt",) and perm_rate_pct:
                    src["interest_rate_pct"] = float(perm_rate_pct)
                    if perm_amort_years:
                        carry["amort_term_years"] = int(perm_amort_years)
                elif ft in ("construction_loan",) and construction_rate_pct:
                    src["interest_rate_pct"] = float(construction_rate_pct)
                cm.source = src
                cm.carry = carry
                session.add(cm)

    await session.commit()

    return RedirectResponse(url=f"/models/{model_id}/builder", status_code=303)


@router.post("/ui/projects/{project_id}/timeline-wizard", response_class=HTMLResponse)
async def timeline_wizard_submit(
    request: Request,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Process wizard form: clear seeded milestones, create anchor + selected milestones."""
    from sqlalchemy import delete as sa_delete
    from datetime import date as _date

    proj = await session.get(Project, project_id)
    if proj is None:
        return HTMLResponse("<p class='text-muted'>Project not found.</p>", status_code=404)

    form = await request.form()
    anchor_type_raw = str(form.get("anchor_type", ""))
    anchor_date_raw = str(form.get("anchor_date", ""))
    anchor_duration_raw = str(form.get("anchor_duration_days", "0"))
    selected_types = form.getlist("milestone_types")  # includes anchor
    new_name = str(form.get("new_name", "")).strip()
    new_deal_type_raw = str(form.get("new_deal_type", "")).strip()

    # If name/type provided (new deal wizard step 0), update deal records
    if new_name or new_deal_type_raw:
        scenario = await session.get(DealModel, proj.scenario_id)
        if scenario:
            if new_deal_type_raw:
                try:
                    new_dt = ProjectType(new_deal_type_raw)
                    proj.deal_type = new_dt
                    scenario.project_type = new_dt
                except ValueError:
                    pass
            if new_name:
                if scenario.deal_id:
                    deal_obj = await session.get(Deal, scenario.deal_id)
                    if deal_obj:
                        deal_obj.name = new_name
                if proj.opportunity_id:
                    opp_obj = await session.get(Opportunity, proj.opportunity_id)
                    if opp_obj:
                        opp_obj.name = new_name

    try:
        anchor_mt = MilestoneType(anchor_type_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid anchor type.</p>", status_code=400)

    try:
        anchor_date = _date.fromisoformat(anchor_date_raw.strip()[:10])
    except (ValueError, AttributeError):
        return HTMLResponse("<p class='text-muted'>Invalid start date.</p>", status_code=400)

    try:
        anchor_duration = max(0, int(anchor_duration_raw))
    except (ValueError, TypeError):
        anchor_duration = 0

    _STABILIZED_AUTO_DAYS = 10950  # 30 years — applied when no divestment milestone

    # Clear existing milestones for this project
    await session.execute(sa_delete(Milestone).where(Milestone.project_id == project_id))
    await session.flush()

    has_divestment = "divestment" in selected_types
    valid_types = {mt.value for mt in MilestoneType}

    # Filter + de-dupe while preserving submitted order (the canonical CRE
    # timeline order the user picked in the UI).  Unknown types are skipped.
    ordered_types: list[str] = []
    seen: set[str] = set()
    for mt_str in selected_types:
        if mt_str in valid_types and mt_str not in seen:
            ordered_types.append(mt_str)
            seen.add(mt_str)

    # Two-pass creation so we can build a trigger chain.
    # Pass 1: instantiate every milestone with its duration + target_date
    # on the anchor.  Pass 2: assign trigger_milestone_id so each non-anchor
    # milestone starts at the end of the previous one in submitted order.
    # Without the trigger chain, computed_start() returns None for non-
    # anchor milestones, _milestone_dates_from_orm skips them, and the
    # cashflow engine falls back to the legacy OperationalInputs scalar
    # fields (which are NULL on wizard-created deals) → every phase
    # defaults to 1 month and the carry-type math collapses.
    created: list[Milestone] = []
    for seq, mt_str in enumerate(ordered_types):
        mt = MilestoneType(mt_str)
        is_anchor = mt == anchor_mt

        # Per-milestone duration override via ``duration_{type}=N`` form field.
        override_raw = form.get(f"duration_{mt_str}")
        if override_raw is not None and str(override_raw).strip() != "":
            try:
                dur = max(0, int(override_raw))
            except (ValueError, TypeError):
                dur = 0
        elif mt == MilestoneType.operation_stabilized and not has_divestment:
            # Auto-cap stabilized at 30 years when no divestment
            dur = _STABILIZED_AUTO_DAYS
        elif mt == MilestoneType.divestment:
            # Divestment is a single-day event (sale closing date)
            dur = 1
        else:
            dur = anchor_duration if is_anchor else 0

        row = Milestone(
            project_id=project_id,
            milestone_type=mt,
            target_date=anchor_date if is_anchor else None,
            duration_days=dur,
            sequence_order=seq,
        )
        session.add(row)
        created.append(row)

    # Flush so every Milestone gets a primary key before we wire trigger refs.
    await session.flush()

    # Pass 2: build the trigger chain in submitted order.  Each non-anchor
    # milestone triggers off the previous one with offset=0 so its start date
    # equals the prior milestone's end date (prev.start + prev.duration_days).
    prev: Milestone | None = None
    for row in created:
        if row.milestone_type == anchor_mt:
            prev = row
            continue
        if prev is not None:
            row.trigger_milestone_id = prev.id
            row.trigger_offset_days = 0
        prev = row

    await session.commit()
    return RedirectResponse(url=f"/models/{proj.scenario_id}/builder?project={project_id}&module=timeline", status_code=303)


@router.post("/ui/projects/{project_id}/approve-timeline", response_class=HTMLResponse)
async def approve_timeline(
    request: Request,
    project_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Toggle timeline approval on the dev Project.

    Normal POST → approve (redirect to sources).
    POST with _unapprove=1 → re-open (redirect back to timeline).
    """
    proj = await session.get(Project, project_id)
    if proj is None:
        return HTMLResponse("<p class='text-muted'>Project not found.</p>", status_code=404)
    form = await request.form()
    unapprove = str(form.get("_unapprove", "")).strip() == "1"
    proj.timeline_approved = not unapprove
    await session.commit()
    if unapprove:
        return RedirectResponse(url=f"/models/{proj.scenario_id}/builder?module=timeline", status_code=303)
    return RedirectResponse(url=f"/models/{proj.scenario_id}/builder?module=sources", status_code=303)


@router.get("/ui/models/{model_id}/setup", response_class=HTMLResponse)
async def deal_setup_wizard_get(
    request: Request,
    model_id: UUID,
    session: DBSession,
    step: int = Query(default=-1),
) -> HTMLResponse:
    """Render a single wizard step fragment (used by Back buttons and direct links)."""
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
    )).scalar_one_or_none() if default_project else None

    # Detect missing building data for step 0
    missing_building_data = await _get_missing_building_data(default_project, session) if default_project else []

    # If step not explicitly requested, start at step 0 (if missing data) else step 1
    if step == -1:
        step = 0 if missing_building_data else 1

    return templates.TemplateResponse(request, "partials/deal_setup_wizard.html", {
        "request": request, "model": model, "inputs": inputs, "step": step,
        "missing_building_data": missing_building_data,
    })


async def _prefill_noi_from_listing(
    model: "DealModel",
    default_project: "Project",
    inputs: "OperationalInputs",
    session: "AsyncSession",
) -> None:
    """If the deal's opportunity has a scraped listing with NOI data, pre-fill
    OperationalInputs.noi_stabilized_input.  Does nothing if already set or no
    listing data is found.  Uses proforma_noi first, falls back to noi."""
    if inputs.noi_stabilized_input is not None:
        return  # already set — don't overwrite a previous entry
    # Resolve opportunity via DealOpportunity join
    opp_row = (await session.execute(
        select(DealOpportunity)
        .where(DealOpportunity.deal_id == model.deal_id)
        .limit(1)
    )).scalar_one_or_none()
    if opp_row is None:
        return
    listing = (await session.execute(
        select(ScrapedListing)
        .where(ScrapedListing.linked_project_id == opp_row.opportunity_id)
        .order_by(ScrapedListing.last_seen_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if listing is None:
        return
    noi_value = listing.proforma_noi if listing.proforma_noi is not None else listing.noi
    if noi_value is not None:
        inputs.noi_stabilized_input = noi_value
        session.add(inputs)


@router.post("/ui/models/{model_id}/setup/step", response_class=HTMLResponse)
async def deal_setup_wizard_step(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Save a wizard step's data and return the next step fragment."""
    form = await request.form()
    step = int(form.get("step", 1))
    # Field-level validation errors collected during the step handler.
    # Keyed by funder_type (or "_form" for cross-cutting errors).  When
    # non-empty, the same step is re-rendered instead of advancing.
    wizard_errors: dict[str, str] = {}

    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    if default_project is None:
        return HTMLResponse("No project found", status_code=400)

    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
    )).scalar_one_or_none()
    if inputs is None:
        # Auto-create a minimal OperationalInputs row so the wizard can proceed
        inputs = OperationalInputs(
            project_id=default_project.id,
        )
        session.add(inputs)
        await session.flush()

    # Save current step's data
    if step == 0:
        # Building data step — patch buildings with missing unit_count / building_sqft / net_rentable_sqft
        for key, val in form.multi_items():
            # Keys: unit_count_{id} | building_sqft_{id} | net_rentable_sqft_{id}
            for field in ("unit_count", "building_sqft", "net_rentable_sqft"):
                if key.startswith(f"{field}_") and val:
                    bldg_id_str = key[len(f"{field}_"):]
                    try:
                        bldg_id = UUID(bldg_id_str)
                    except ValueError:
                        continue
                    bldg = await session.get(Building, bldg_id)
                    if bldg:
                        if field == "unit_count":
                            bldg.unit_count = int(val)
                        elif field == "building_sqft":
                            bldg.building_sqft = int(val)
                        elif field == "net_rentable_sqft":
                            bldg.net_rentable_sqft = int(val)
        await session.flush()
        missing_building_data = await _get_missing_building_data(default_project, session)
        return templates.TemplateResponse(request, "partials/deal_setup_wizard.html", {
            "request": request, "model": model, "inputs": inputs, "step": 1,
            "missing_building_data": missing_building_data,
        })
    elif step == 1:
        # Income mode selection (new step 1)
        income_mode = str(form.get("income_mode") or "revenue_opex")
        if income_mode not in ("revenue_opex", "noi"):
            income_mode = "revenue_opex"
        model.income_mode = income_mode
        session.add(model)
        # Pre-fill NOI from linked opportunity's scraped listing
        if income_mode == "noi":
            await _prefill_noi_from_listing(model, default_project, inputs, session)
    elif step == 2:
        # Debt type checkboxes → debt_types list
        _valid_types = {
            "pre_development_loan", "acquisition_loan", "construction_loan",
            "bridge", "permanent_debt", "construction_to_perm",
        }
        selected = [t for t in form.getlist("debt_types") if t in _valid_types]
        if selected:
            inputs.debt_types = selected
    elif step == 3:
        # Per-debt milestone & retirement config
        # Validate phase sequencing: active_from must precede active_to.
        # "perpetuity" and "" are treated as "open-ended" and always valid.
        _PHASE_ORDER = {
            "pre_construction": 0, "close": 1, "acquisition": 1,
            "construction": 2, "lease_up": 3, "operation_lease_up": 3,
            "stabilized": 4, "operation_stabilized": 4, "exit": 5, "divestment": 5,
        }
        dmc: dict = {}
        for ft in (inputs.debt_types or []):
            active_from = form.get(f"{ft}_active_from") or ""
            active_to   = form.get(f"{ft}_active_to")   or ""
            retired_by  = form.get(f"{ft}_retired_by")  or ""
            if active_from and active_to and active_to not in ("perpetuity", ""):
                _from_rank = _PHASE_ORDER.get(active_from)
                _to_rank   = _PHASE_ORDER.get(active_to)
                if _from_rank is not None and _to_rank is not None and _from_rank > _to_rank:
                    wizard_errors[ft] = (
                        f"Active period is backwards: '{active_from}' comes after '{active_to}'. "
                        f"Set active_to to a later phase, or use 'perpetuity' if the loan never retires."
                    )
                    continue
            if active_from or active_to or retired_by:
                dmc[ft] = {
                    "active_from": active_from,
                    "active_to":   active_to,
                    "retired_by":  retired_by,
                }
        if wizard_errors:
            # Re-render step 3 with errors; do not advance
            pass
        elif dmc:
            inputs.debt_milestone_config = dmc
    elif step == 4:
        # Per-debt terms: loan type, rate, amort years
        # Validate with explicit try/except and range checks so bad input
        # surfaces as a field error, not a 500.
        _VALID_LOAN_TYPES = {
            "io_only", "interest_reserve", "capitalized_interest",
            "pi", "io_then_pi",
        }
        dt_terms = dict(inputs.debt_terms or {})
        for ft in (inputs.debt_types or []):
            loan_type   = form.get(f"{ft}_loan_type")
            rate_raw    = form.get(f"{ft}_rate_pct")
            amort_raw   = form.get(f"{ft}_amort_years")
            entry = dict(dt_terms.get(ft, {}))

            if loan_type:
                if loan_type not in _VALID_LOAN_TYPES:
                    wizard_errors[ft] = f"Unknown loan type: {loan_type!r}"
                    continue
                entry["loan_type"] = loan_type

            if rate_raw:
                try:
                    rate_val = float(rate_raw)
                except (TypeError, ValueError):
                    wizard_errors[ft] = f"Interest rate must be a number (got {rate_raw!r})"
                    continue
                if rate_val < 0 or rate_val > 30:
                    wizard_errors[ft] = (
                        f"Interest rate {rate_val}% is outside 0–30%. Enter a realistic rate."
                    )
                    continue
                entry["rate_pct"] = rate_val

            if amort_raw:
                try:
                    amort_val = int(amort_raw)
                except (TypeError, ValueError):
                    wizard_errors[ft] = f"Amortization must be a whole number of years (got {amort_raw!r})"
                    continue
                if amort_val < 1 or amort_val > 40:
                    wizard_errors[ft] = f"Amortization {amort_val} years is outside 1–40 years."
                    continue
                entry["amort_years"] = amort_val

            if entry:
                dt_terms[ft] = entry
        if not wizard_errors:
            inputs.debt_terms = dt_terms
    elif step == 5:
        # Per-debt sizing approach; perm gap-fill / dscr-capped mode
        dt_terms = dict(inputs.debt_terms or {})
        for ft in (inputs.debt_types or []):
            sizing_approach = form.get(f"{ft}_sizing_approach")
            ltv_pct         = form.get(f"{ft}_ltv_pct")
            fixed_amount    = form.get(f"{ft}_fixed_amount")
            if sizing_approach or ltv_pct or fixed_amount:
                entry = dict(dt_terms.get(ft, {}))
                if sizing_approach: entry["sizing_approach"] = sizing_approach
                if ltv_pct:         entry["ltv_pct"]        = float(ltv_pct)
                if fixed_amount:    entry["fixed_amount"]   = float(fixed_amount)
                dt_terms[ft] = entry
        inputs.debt_terms = dt_terms
        inputs.debt_sizing_mode = form.get("debt_sizing_mode") or inputs.debt_sizing_mode
        dscr_val = form.get("dscr_minimum")
        if dscr_val:
            inputs.dscr_minimum = Decimal(dscr_val)
    elif step == 6:
        # Reserves & Floors (renumbered from old step 5)
        cf_pct = form.get("construction_floor_pct")
        if cf_pct:
            inputs.construction_floor_pct = Decimal(cf_pct)
        or_months = form.get("operation_reserve_months")
        if or_months:
            inputs.operation_reserve_months = int(or_months)
        # Lease-up occupancy curve (linear vs s_curve + steepness)
        lu_curve = form.get("lease_up_curve")
        if lu_curve in ("linear", "s_curve"):
            inputs.lease_up_curve = lu_curve
        lu_steep = _fd(form.get("lease_up_curve_steepness"))
        if lu_steep is not None:
            inputs.lease_up_curve_steepness = lu_steep

    # If validation failed, don't persist and re-render the same step with errors
    if wizard_errors:
        missing_building_data = await _get_missing_building_data(default_project, session)
        return templates.TemplateResponse(request, "partials/deal_setup_wizard.html", {
            "request": request, "model": model, "inputs": inputs, "step": step,
            "missing_building_data": missing_building_data,
            "wizard_errors": wizard_errors,
        })

    session.add(inputs)
    await session.commit()
    await session.refresh(inputs)
    await session.refresh(model)

    next_step = step + 1
    missing_building_data = await _get_missing_building_data(default_project, session)
    return templates.TemplateResponse(request, "partials/deal_setup_wizard.html", {
        "request": request, "model": model, "inputs": inputs, "step": next_step,
        "missing_building_data": missing_building_data,
    })


@router.post("/ui/models/{model_id}/setup/complete")
async def deal_setup_wizard_complete(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> Response:
    """Finalize setup: mark complete and auto-create the primary debt CapitalModule(s)."""
    from app.models.capital import CapitalModule, FunderType

    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    if default_project is None:
        return HTMLResponse("No project", status_code=400)

    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
    )).scalar_one_or_none()
    if inputs is None:
        return HTMLResponse("No inputs", status_code=400)

    dt = inputs.debt_terms or {}
    debt_types = inputs.debt_types  # None for pre-migration deals
    debt_structure = inputs.debt_structure or "perm_only"

    # Remove any existing auto-created debt modules (clean re-run)
    existing_auto = list((await session.execute(
        select(CapitalModule).where(
            CapitalModule.scenario_id == model_id,
            CapitalModule.label.like("%(auto)%"),
        )
    )).scalars())
    for cm in existing_auto:
        await session.delete(cm)

    # Closing-cost pre-load data collected during Phase B module creation.
    # Populated in the loop below; used after both branches to write $0 Use line stubs.
    _cc_preload_modules: list[dict] = []

    if debt_types:
        # ── New multi-debt path ───────────────────────────────────────────────
        # Build one CapitalModule per selected debt type using debt_milestone_config
        # and debt_terms (per-debt dicts).  Falls back to sensible defaults if the
        # wizard steps were skipped (e.g. re-running on a backfilled deal).
        dmc = inputs.debt_milestone_config or {}

        _FT_MAP: dict[str, FunderType] = {
            "pre_development_loan": FunderType.pre_development_loan,
            "acquisition_loan":     FunderType.acquisition_loan,
            "construction_loan":    FunderType.construction_loan,
            "bridge":               FunderType.bridge,
            "permanent_debt":       FunderType.permanent_debt,
            "construction_to_perm": FunderType.bond,
        }
        _LABEL: dict[str, str] = {
            "pre_development_loan": "Pre-Development Loan",
            "acquisition_loan":     "Acquisition Loan",
            "construction_loan":    "Construction Loan",
            "bridge":               "Bridge Loan",
            "permanent_debt":       "Permanent Debt",
            "construction_to_perm": "Construction-to-Perm",
        }
        # Defaults must match deal_setup_wizard.html Step 4 (_dt_default_*).
        # Any mismatch means wizard re-runs show ghost field changes.
        _DEFAULT_RATE: dict[str, float] = {
            "pre_development_loan": 8.0,
            "acquisition_loan":     6.5,
            "construction_loan":    6.0,
            "bridge":               7.5,
            "permanent_debt":       5.0,
            "construction_to_perm": 5.0,
        }
        _DEFAULT_LOAN_TYPE: dict[str, str] = {
            "pre_development_loan": "interest_reserve",
            "acquisition_loan":     "interest_reserve",
            "construction_loan":    "interest_reserve",
            "bridge":               "interest_reserve",
            "permanent_debt":       "pi",
            "construction_to_perm": "io_then_pi",
        }
        _DEFAULT_FROM: dict[str, str] = {
            "pre_development_loan": "pre_construction",
            "acquisition_loan":     "acquisition",
            "construction_loan":    "acquisition",
            "bridge":               "lease_up",
            "permanent_debt":       "lease_up",
            "construction_to_perm": "acquisition",
        }
        _DEFAULT_TO: dict[str, str] = {
            "pre_development_loan": "acquisition",
            "acquisition_loan":     "construction",
            "construction_loan":    "lease_up",
            "bridge":               "stabilized",
            "permanent_debt":       "stabilized",
            "construction_to_perm": "stabilized",
        }

        for pos, ft_str in enumerate(debt_types, start=1):
            ft = _FT_MAP.get(ft_str)
            if ft is None:
                continue
            cfg   = dmc.get(ft_str, {})
            terms = dt.get(ft_str, {})

            rate        = float(terms.get("rate_pct") or _DEFAULT_RATE.get(ft_str, 6.0))
            loan_type   = terms.get("loan_type") or _DEFAULT_LOAN_TYPE.get(ft_str, "io_only")
            amort_years = int(terms.get("amort_years") or 30)
            active_from = cfg.get("active_from") or _DEFAULT_FROM.get(ft_str, "acquisition")
            active_to   = cfg.get("active_to")   or _DEFAULT_TO.get(ft_str, "stabilized")
            retired_by  = cfg.get("retired_by")  or ""

            if loan_type == "interest_reserve":
                carry: dict = {"carry_type": "interest_reserve", "io_rate_pct": rate}
            elif loan_type == "capitalized_interest":
                carry = {"carry_type": "capitalized_interest", "io_rate_pct": rate}
            elif loan_type == "io_only":
                carry = {"carry_type": "io_only", "io_rate_pct": rate}
            elif loan_type == "pi":
                carry = {"carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": rate}
            else:  # io_then_pi
                carry = {
                    "phases": [
                        {"name": "construction", "carry_type": "interest_reserve", "io_rate_pct": rate},
                        {"name": "operation", "carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": rate},
                    ]
                }

            if retired_by and retired_by not in ("perpetuity", ""):
                exit_trigger = _LABEL.get(retired_by, retired_by.replace("_", " "))
                exit_terms_dict: dict = {"exit_type": "full_payoff", "trigger": exit_trigger}
            else:
                exit_terms_dict = {"exit_type": "full_payoff", "trigger": "end of hold period"}

            _cm_label_for_cc = f"{_LABEL.get(ft_str, ft_str)} (auto)"
            session.add(CapitalModule(
                scenario_id=model_id,
                label=_cm_label_for_cc,
                funder_type=ft,
                stack_position=pos,
                source={"auto_size": True, "interest_rate_pct": rate},
                carry=carry,
                exit_terms=exit_terms_dict,
                active_phase_start=active_from,
                active_phase_end=active_to,
            ))
            # Track for closing-cost pre-loading below
            _cc_preload_modules.append({
                "funder_type": ft_str,
                "label": _cm_label_for_cc,
                "active_phase_start": active_from,
            })

    else:
        # ── Legacy 3-path (backward compat for pre-migration deals) ──────────
        if debt_structure == "construction_to_perm":
            construction_rate = dt.get("construction_rate_pct") or dt.get("perm_rate_pct") or 4.5
            perm_rate = dt.get("perm_rate_pct") or construction_rate
            amort_years = int(dt.get("perm_amort_years") or 30)
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Bond / Construction-to-Perm (auto)",
                funder_type=FunderType.bond,
                stack_position=1,
                source={"auto_size": True, "interest_rate_pct": perm_rate},
                carry={
                    "phases": [
                        {"name": "construction", "carry_type": "io_only", "io_rate_pct": construction_rate},
                        {"name": "operation", "carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": perm_rate},
                    ]
                },
                exit_terms={"exit_type": "full_payoff", "trigger": "end of hold period"},
                active_phase_start="pre_construction",
                active_phase_end="stabilized",
            ))

        elif debt_structure == "construction_and_perm":
            construction_rate = dt.get("construction_rate_pct") or 6.0
            perm_rate = dt.get("perm_rate_pct") or 5.0
            amort_years = int(dt.get("perm_amort_years") or 30)
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Construction Loan (auto)",
                funder_type=FunderType.construction_loan,
                stack_position=1,
                source={"auto_size": True, "interest_rate_pct": construction_rate},
                carry={"carry_type": "io_only", "io_rate_pct": construction_rate},
                exit_terms={"exit_type": "full_payoff", "trigger": "permanent_financing_close"},
                active_phase_start="pre_construction",
                active_phase_end="lease_up",
            ))
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Permanent Debt (auto)",
                funder_type=FunderType.permanent_debt,
                stack_position=2,
                source={"auto_size": True, "interest_rate_pct": perm_rate},
                carry={"carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": perm_rate},
                exit_terms={"exit_type": "full_payoff", "trigger": "end of hold period"},
                active_phase_start="lease_up",
                active_phase_end="stabilized",
            ))

        else:  # perm_only
            perm_rate = dt.get("perm_rate_pct") or 5.0
            amort_years = int(dt.get("perm_amort_years") or 30)
            session.add(CapitalModule(
                scenario_id=model_id,
                label="Permanent Debt (auto)",
                funder_type=FunderType.permanent_debt,
                stack_position=1,
                source={"auto_size": True, "interest_rate_pct": perm_rate},
                carry={"carry_type": "pi", "amort_term_years": amort_years, "io_rate_pct": perm_rate},
                exit_terms={"exit_type": "full_payoff", "trigger": "end of hold period"},
                active_phase_start="acquisition",
                active_phase_end="stabilized",
            ))

    # Sync debt_structure from debt_types for engine backward compat.
    # Phase B will generalise the engine to use debt_types directly; until then
    # the sizing function gates on debt_structure to detect construction+perm bridges.
    if debt_types:
        if "construction_to_perm" in debt_types:
            inputs.debt_structure = "construction_to_perm"
        elif "construction_loan" in debt_types and "permanent_debt" in debt_types:
            inputs.debt_structure = "construction_and_perm"
        elif debt_types == ["permanent_debt"]:
            inputs.debt_structure = "perm_only"
        # Other combinations (pre_development, acquisition, bridge) left as-is until Phase B

    # Seed default OpEx line items if none exist — consensus from CRE model
    # cross-analysis (HelloData, A.CRE, PropRise). User fills in amounts later.
    existing_opex = list((await session.execute(
        select(OperatingExpenseLine).where(
            OperatingExpenseLine.project_id == default_project.id,
        )
    )).scalars())
    if not existing_opex:
        _DEFAULT_OPEX_LINES = [
            "Real Estate Taxes",
            "Property Insurance",
            "Utilities",
            "Repairs & Maintenance",
            "Management Fee",
            "Payroll & On-Site Staff",
            "Marketing & Leasing",
            "General & Administrative",
            "Turnover / Make-Ready",
            "CapEx Reserve",
        ]
        for _label in _DEFAULT_OPEX_LINES:
            session.add(OperatingExpenseLine(
                project_id=default_project.id,
                label=_label,
                annual_amount=Decimal("0"),
                per_type="flat",
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["stabilized"],
                notes="Seeded default — set amount to customize or delete if not applicable.",
            ))

    inputs.deal_setup_complete = True
    session.add(inputs)

    # Create $0 Operating Reserve placeholder in Uses (populated at compute time)
    existing_reserve = (await session.execute(
        select(UseLine).where(
            UseLine.project_id == default_project.id,
            UseLine.label == "Operating Reserve",
        )
    )).scalar_one_or_none()
    if existing_reserve is None:
        session.add(UseLine(
            project_id=default_project.id,
            label="Operating Reserve",
            phase="operation",
            amount=Decimal("0"),
            timing_type="first_day",
            notes="Sized at compute time: max(OpEx, Debt Service) × reserve months",
        ))

    # ── Pre-load $0 closing cost Use line stubs for Phase B modules ──────────
    # Cost names match _DEFAULT_LOAN_COSTS in cashflow.py (keep in sync).
    # amount=0 → engine computes at run time; amount>0 → user override, engine skips.
    # Users see and edit these in the S&U table before running Compute.
    _CC_PRELOAD_COSTS: dict[str, list[str]] = {
        "construction_loan":    ["Origination Fee", "Lender Legal", "Title / Survey", "Environmental Phase I"],
        "permanent_debt":       ["Origination Fee", "Lender Legal", "Appraisal", "Title"],
        "pre_development_loan": ["Origination Fee", "Lender Legal"],
        "acquisition_loan":     ["Origination Fee", "Lender Legal", "Title / Survey"],
        "bridge":               ["Origination Fee", "Lender Legal"],
        "bond":                 ["Bond Issuance Fee", "Bond Counsel Legal"],
    }
    _APS_TO_PHASE: dict[str, str] = {
        "acquisition": "acquisition",      "close": "acquisition",
        "pre_construction": "pre_construction",
        "construction": "construction",
        "lease_up": "operation",           "operation_lease_up": "operation",
        "stabilized": "operation",         "operation_stabilized": "operation",
        "exit": "exit",                    "divestment": "exit",
    }
    for _cc_mod in _cc_preload_modules:
        _cc_ft_str = _cc_mod["funder_type"]
        # Map construction_to_perm → bond for cost lookup
        _cc_ft_key = "bond" if _cc_ft_str == "construction_to_perm" else _cc_ft_str
        _cost_names = _CC_PRELOAD_COSTS.get(_cc_ft_key)
        if not _cost_names:
            continue
        _cc_lbl  = _cc_mod["label"]
        _cc_phase = _APS_TO_PHASE.get(_cc_mod["active_phase_start"] or "", "pre_construction")
        for _cost_name in _cost_names:
            _full_cc_lbl = f"{_cc_lbl} — {_cost_name}"
            _existing_cc = (await session.execute(
                select(UseLine).where(
                    UseLine.project_id == default_project.id,
                    UseLine.label == _full_cc_lbl,
                )
            )).scalar_one_or_none()
            if _existing_cc is None:
                session.add(UseLine(
                    project_id=default_project.id,
                    label=_full_cc_lbl,
                    phase=_cc_phase,
                    amount=Decimal("0"),
                    timing_type="first_day",
                    notes="Auto-computed — edit to override",
                ))

    # ── UnitMix: seed from linked building(s) if none exist ─────────────────
    existing_unit_mix = list((await session.execute(
        select(UnitMix).where(UnitMix.project_id == default_project.id)
    )).scalars())

    if not existing_unit_mix:
        # Prefer assigned buildings' total unit_count; fall back to inputs.unit_count_new
        building_unit_count: int = int(inputs.unit_count_new or 0)
        # Read from per-project building assignments (new model); fall back to opportunity-level
        assigned_buildings = (await session.execute(
            select(Building)
            .join(ProjectBuildingAssignment, ProjectBuildingAssignment.building_id == Building.id)
            .where(ProjectBuildingAssignment.project_id == default_project.id)
            .order_by(ProjectBuildingAssignment.sort_order)
        )).scalars().all()
        if not assigned_buildings and default_project.opportunity_id:
            # Legacy fallback: no project-level assignments yet (pre-migration projects)
            first_ob = (await session.execute(
                select(OpportunityBuilding)
                .where(OpportunityBuilding.opportunity_id == default_project.opportunity_id)
                .order_by(OpportunityBuilding.sort_order)
                .limit(1)
            )).scalar_one_or_none()
            if first_ob:
                bldg = await session.get(Building, first_ob.building_id)
                if bldg:
                    assigned_buildings = [bldg]
        total_units = sum(b.unit_count or 0 for b in assigned_buildings)
        if total_units:
            building_unit_count = total_units
            # Keep OperationalInputs in sync
            if not inputs.unit_count_new:
                inputs.unit_count_new = building_unit_count
                session.add(inputs)

        if building_unit_count:
            session.add(UnitMix(
                project_id=default_project.id,
                label="All Units",
                unit_count=building_unit_count,
                notes="Seeded from building — break into unit types as needed",
            ))
            existing_unit_mix = []  # will be flushed; reload below via refresh

    # ── Market recommendation: KNN query for revenue/expense prefill ────────
    from app.engines.market import SubjectProperty, get_market_recommendation

    _market_rec = None
    _market_occupancy = Decimal("95")
    if assigned_buildings:
        _bldg = assigned_buildings[0]
        _subj_units = building_unit_count or int(_bldg.unit_count or 0)
        _subj_year = _bldg.year_built
        _subj_sqft = float(_bldg.building_sqft) if _bldg.building_sqft else None
        _subj_sqft_per_unit = _subj_sqft / _subj_units if _subj_sqft and _subj_units > 0 else None
        # Get jurisdiction + listing ID from linked listing's reconciled parcel data
        _subj_juris = None
        _exclude_listing_id = None
        if default_project.opportunity_id:
            _listing_for_juris = (await session.execute(
                select(ScrapedListing.id, ScrapedListing.jurisdiction, ScrapedListing.city)
                .where(ScrapedListing.linked_project_id == default_project.opportunity_id)
                .limit(1)
            )).first()
            if _listing_for_juris:
                _exclude_listing_id = str(_listing_for_juris[0])
                _subj_juris = _listing_for_juris[1] or _listing_for_juris[2]
        if _subj_units > 0 and _subj_year:
            try:
                _market_rec = await get_market_recommendation(
                    session,
                    SubjectProperty(
                        units=_subj_units,
                        year_built=_subj_year,
                        sqft_per_unit=_subj_sqft_per_unit,
                        jurisdiction=_subj_juris,
                    ),
                    exclude_listing_id=_exclude_listing_id,
                )
                if _market_rec and not _market_rec.low_confidence:
                    if _market_rec.occupancy_pct is not None:
                        _market_occupancy = Decimal(str(round(_market_rec.occupancy_pct * 100, 1)))
            except Exception:
                pass  # market recommendation failed; fall back to defaults

    # If NOI mode and no NOI prefilled from listing, use market recommendation
    if model.income_mode == "noi" and inputs.noi_stabilized_input is None and _market_rec and not _market_rec.low_confidence:
        _market_noi = Decimal(str(round(_market_rec.noi_per_unit * building_unit_count, 2)))
        inputs.noi_stabilized_input = _market_noi
        session.add(inputs)

    # ── Revenue: seed one IncomeStream per UnitMix row ──────────────────────
    # Skip entirely in NOI mode — Revenue module is not used
    # Only seed if no income streams exist yet
    existing_income = (await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == default_project.id).limit(1)
    )).scalar_one_or_none()

    if existing_income is None and model.income_mode != "noi":
        # Flush so UnitMix rows are visible
        await session.flush()
        unit_mix_rows = list((await session.execute(
            select(UnitMix).where(UnitMix.project_id == default_project.id)
        )).scalars())

        total_units = sum(row.unit_count for row in unit_mix_rows)
        for row in unit_mix_rows:
            session.add(IncomeStream(
                project_id=default_project.id,
                stream_type=IncomeStreamType.residential_rent,
                label=row.label,
                unit_count=row.unit_count,
                amount_per_unit_monthly=(row.in_place_rent_per_unit or row.market_rent_per_unit or Decimal("0")),
                stabilized_occupancy_pct=_market_occupancy,
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["lease_up", "stabilized"],
            ))

        if total_units > 0:
            session.add(IncomeStream(
                project_id=default_project.id,
                stream_type=IncomeStreamType.deposit_forfeit,
                label="Turnover on Deposit",
                unit_count=total_units,
                amount_per_unit_monthly=Decimal("0"),
                stabilized_occupancy_pct=Decimal("100"),
                escalation_rate_pct_annual=Decimal("3"),
                active_in_phases=["stabilized"],
                notes="$/unit/mo to configure — typically 4.5% annual turnover × avg rent × recovery rate / 12",
            ))

    # ── OpEx: seed 19 standard lines ────────────────────────────────────────
    # Skip entirely in NOI mode — OpEx module is not used
    # Skip individual labels that already exist (idempotent re-run)
    existing_opex_labels = set((await session.execute(
        select(OperatingExpenseLine.label).where(
            OperatingExpenseLine.project_id == default_project.id
        )
    )).scalars())

    # (label, per_type, scale_with_lease_up, lease_up_floor_pct, active_phases)
    _OPEX_SEEDS = [
        ("Property Tax",             "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Insurance",                "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Property Management",      "per_unit", True,  25.0,   ["lease_up", "stabilized"]),
        ("On-Site Staff",            "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Payroll Taxes",            "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Electric — Common Areas",  "flat",     True,  100.0,  ["lease_up", "stabilized"]),
        ("Water / Sewer",            "per_unit", True,  50.0,   ["lease_up", "stabilized"]),
        ("Gas",                      "per_unit", True,  50.0,   ["lease_up", "stabilized"]),
        ("Internet — Common",        "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Garbage / Refuse",         "flat",     True,  75.0,   ["lease_up", "stabilized"]),
        ("Repairs & Maintenance",    "per_unit", True,  25.0,   ["stabilized"]),
        ("Landscaping",              "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Replacement Reserve",      "per_unit", False, None,   ["stabilized"]),
        ("Resident Services",        "flat",     True,  25.0,   ["stabilized"]),
        ("Legal",                    "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Accounting",               "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Office / Admin",           "flat",     False, None,   ["lease_up", "stabilized"]),
        ("Advertising & Leasing",    "per_unit", True,  100.0,  ["lease_up", "stabilized"]),
        ("Unit Turnover",            "per_unit", False, None,   ["stabilized"]),
    ]

    for label, per_type, scale, floor_pct, phases in _OPEX_SEEDS:
        if label in existing_opex_labels or model.income_mode == "noi":
            continue
        session.add(OperatingExpenseLine(
            project_id=default_project.id,
            label=label,
            annual_amount=Decimal("0"),
            per_type=per_type,
            scale_with_lease_up=scale,
            lease_up_floor_pct=Decimal(str(floor_pct)) if floor_pct is not None else None,
            escalation_rate_pct_annual=Decimal("3"),
            active_in_phases=phases,
        ))

    await session.commit()

    # Redirect to builder — NOI mode lands on the NOI module first, else Uses
    _first_module = "noi" if model.income_mode == "noi" else "sources_uses"
    from starlette.responses import Response as StarletteResponse
    response = StarletteResponse(status_code=204)
    response.headers["HX-Redirect"] = f"/models/{model_id}/builder?module={_first_module}"
    return response


@router.get("/models/{model_id}/builder", response_class=HTMLResponse)
async def model_builder(
    request: Request,
    model_id: UUID,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
    module: str = Query(default=""),
    project: str = Query(default=""),  # optional Project.id to view a specific project
    new: str = Query(default=""),  # set to "1" when redirected from new deal creation
) -> HTMLResponse:
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    # `project` context var = the Opportunity (purchase target), for display in topbar
    # Find Opportunity via the first Project linked to this Scenario
    _first_proj = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).limit(1)
    )).scalar_one_or_none()
    opportunity = (
        await session.get(Opportunity, _first_proj.opportunity_id)
        if _first_proj and _first_proj.opportunity_id else None
    )
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
    address_issues_count = await _get_address_issues_count(session)

    # All Projects in this Scenario (tab row)
    deal_projects = list((await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc())
    )).scalars())

    # Resolve which project to view
    active_project_id: UUID | None = None
    if project:
        try:
            candidate_id = UUID(project)
            if any(p.id == candidate_id for p in deal_projects):
                active_project_id = candidate_id
        except ValueError:
            pass
    if active_project_id is None and deal_projects:
        active_project_id = deal_projects[0].id

    data = await _load_builder_data(session, model_id, project_id=active_project_id)

    # Sibling scenarios for the variant tab row: other Scenarios sharing the same Opportunity (via Projects)
    deal_variants: list = []
    if opportunity:
        _dv_result = await session.execute(
            select(DealModel)
            .join(Project, Project.scenario_id == DealModel.id)
            .where(Project.opportunity_id == opportunity.id)
            .order_by(DealModel.created_at)
        )
        deal_variants = list(_dv_result.scalars().unique())
    if not deal_variants:
        deal_variants = [model]

    # Resolve Deal.id for the breadcrumb (Opportunity ≠ Deal)
    parent_deal_id: UUID | None = None
    if opportunity:
        _deal_row = (await session.execute(
            select(Deal.id)
            .join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
            .where(DealOpportunity.opportunity_id == opportunity.id)
            .limit(1)
        )).scalar_one_or_none()
        parent_deal_id = _deal_row

    # Determine active module — deal_setup gates modules after timeline approval
    _inputs = data.get("inputs")
    _deal_setup_complete = bool(getattr(_inputs, "deal_setup_complete", False)) if _inputs else False
    _timeline_approved = data.get("timeline_approved", False)
    if not _timeline_approved:
        active_module = module or "timeline"
    elif not _deal_setup_complete and module not in ("timeline", "deal_setup", ""):
        # Redirect so the URL reflects where the user actually lands
        return RedirectResponse(url=f"/models/{model_id}/builder?module=deal_setup", status_code=302)
    else:
        active_module = module or ("sources_uses" if _deal_setup_complete else "deal_setup")

    # Cash flow periods — only loaded when the cashflow module is active
    cash_flow_rows: list = []
    if active_module == "cashflow":
        from app.models.cashflow import CashFlow
        cash_flow_rows = list((await session.execute(
            select(CashFlow)
            .where(CashFlow.scenario_id == model_id)
            .order_by(CashFlow.period)
        )).scalars())

    # Multi-parcel detection — show banner if listing has multiple APNs and user hasn't dismissed
    import re as _re
    multi_parcel_apns: list[str] = []
    if opportunity and not opportunity.multi_parcel_dismissed and len(deal_projects) <= 1:
        _mp_listing = (await session.execute(
            select(ScrapedListing)
            .where(ScrapedListing.linked_project_id == opportunity.id)
            .order_by(ScrapedListing.last_seen_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if _mp_listing and _mp_listing.apn and _re.search(r"[,;]", _mp_listing.apn):
            multi_parcel_apns = [a.strip() for a in _re.split(r"[,;]", _mp_listing.apn) if a.strip()]

    # Lot-size mismatch detection — flag from parcel reconciliation
    lot_size_mismatch_info: dict | None = None
    if opportunity:
        _lsm_listing = (await session.execute(
            select(ScrapedListing)
            .where(
                ScrapedListing.linked_project_id == opportunity.id,
                ScrapedListing.lot_size_mismatch.is_(True),
            )
            .limit(1)
        )).scalar_one_or_none()
        if _lsm_listing and _lsm_listing.parcel:
            _p = _lsm_listing.parcel
            _parcel_lot = float(_p.lot_sqft) if _p.lot_sqft else (float(_p.gis_acres) * 43560 if _p.gis_acres else None)
            _listing_lot = float(_lsm_listing.lot_sqft) if _lsm_listing.lot_sqft else None
            if _parcel_lot and _listing_lot:
                lot_size_mismatch_info = {
                    "listing_sqft": f"{_listing_lot:,.0f}",
                    "parcel_sqft": f"{_parcel_lot:,.0f}",
                }

    # Active project object (for Clone From drawer label)
    active_project = next((p for p in deal_projects if p.id == active_project_id), None)

    # When deal_setup is the active module, resolve wizard step and missing building data
    # so the included partials/deal_setup_wizard.html has everything it needs
    wizard_step: int = 1
    missing_building_data: list = []
    if active_module == "deal_setup" and active_project:
        missing_building_data = await _get_missing_building_data(active_project, session)
        wizard_step = 0 if missing_building_data else 1

    # Draw schedule data — loaded for draw_schedule and cashflow modules
    draw_schedule_data: dict = {}
    if active_module in ("draw_schedule", "cashflow"):
        draw_schedule_data = await _load_draw_schedule_ctx(session, model_id)
        if active_module == "cashflow":
            _sched = await _run_draw_schedule(session, model_id, writeback=False)
            if _sched:
                draw_schedule_data["schedule"] = _sched

    # Pre-render the calc-status pill so it's visible on initial page load
    # without depending on an HTMX hx-trigger="load" round-trip (which was
    # silently failing for some states, leaving the topbar empty).
    _calc_status = _compute_calc_status(data)
    calc_status_pill_html = _render_calc_status_pill_html(_calc_status, model_id)

    ctx = {
        "model": model,
        "project": opportunity,  # template uses `project.name` for the topbar breadcrumb
        "parent_deal_id": str(parent_deal_id) if parent_deal_id else None,
        "deal_variants": deal_variants,
        "deal_projects": deal_projects,
        "active_project_id": str(active_project_id) if active_project_id else None,
        "active_project": active_project,
        "active_module": active_module,
        "deal_setup_complete": _deal_setup_complete,
        "new_deal": new == "1",
        "cash_flow_rows": cash_flow_rows,
        "multi_parcel_apns": multi_parcel_apns,
        "lot_size_mismatch": lot_size_mismatch_info,
        "step": wizard_step,
        "missing_building_data": missing_building_data,
        "calc_status_pill_html": calc_status_pill_html,
        **data,
        **draw_schedule_data,
        **_base_ctx(user, dedup_count, "deals", address_issues_count),
    }
    return templates.TemplateResponse(request, "model_builder.html", ctx)


@router.get("/ui/panel/{model_id}", response_class=HTMLResponse)
async def builder_panel(
    request: Request,
    model_id: UUID,
    session: DBSession,
    module: str = Query(default="sources"),
) -> HTMLResponse:
    """HTMX endpoint — returns the panel partial after a mutation."""
    from app.models.cashflow import CashFlow

    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    data = await _load_builder_data(session, model_id)
    ctx: dict = {"model": model, "active_module": module, **data}

    # Cash flow periods — only loaded when the cashflow module is active
    if module == "cashflow":
        cf_rows = list((await session.execute(
            select(CashFlow)
            .where(CashFlow.scenario_id == model_id)
            .order_by(CashFlow.period)
        )).scalars())
        ctx["cash_flow_rows"] = cf_rows

    # Draw schedule data — loaded for draw_schedule and cashflow modules
    if module in ("draw_schedule", "cashflow"):
        ds_ctx = await _load_draw_schedule_ctx(session, model_id)
        ctx.update(ds_ctx)
        if module == "cashflow":
            _sched = await _run_draw_schedule(session, model_id, writeback=False)
            if _sched:
                ctx["schedule"] = _sched

    return templates.TemplateResponse(request, "partials/model_builder_panel.html", ctx)


def _compute_calc_status(data: dict) -> dict:
    """Produce the 3-factor calculation status: Sources=Uses, DSCR, LTV.

    Each factor returns a dict with:
      status: "ok" | "warn" | "fail" | "na"
      label: short human summary
      detail: longer explanation for the modal
      meta: structured data (numbers) for display

    Overall status rolls up to "ok" (green) only if ALL factors are ok/na.
    """
    capital_total = float(data.get("capital_total") or 0.0)
    uses_total = float(data.get("uses_total") or 0.0)
    outputs = data.get("outputs")
    inputs = data.get("inputs")
    capital_modules = data.get("capital_modules") or []

    # ── Factor 1: Sources vs Uses ──
    gap = capital_total - uses_total
    if not capital_total and not uses_total:
        su_status = {
            "status": "na",
            "label": "No sources/uses yet",
            "detail": "Add Sources and Uses to see balance check.",
            "meta": {"capital_total": 0, "uses_total": 0, "gap": 0},
        }
    elif abs(gap) < 1.0:
        su_status = {
            "status": "ok",
            "label": "Sources = Uses",
            "detail": f"Balanced at {_fmt_currency(uses_total)}.",
            "meta": {"capital_total": capital_total, "uses_total": uses_total, "gap": 0},
        }
    elif gap > 0:
        su_status = {
            "status": "warn",
            "label": f"Surplus {_fmt_currency(gap)}",
            "detail": f"Sources ({_fmt_currency(capital_total)}) exceed Uses ({_fmt_currency(uses_total)}) by {_fmt_currency(gap)}. The extra capital isn't needed — consider reducing a debt amount or equity.",
            "meta": {"capital_total": capital_total, "uses_total": uses_total, "gap": gap},
        }
    else:
        su_status = {
            "status": "fail",
            "label": f"Gap {_fmt_currency(-gap)}",
            "detail": f"Uses ({_fmt_currency(uses_total)}) exceed Sources ({_fmt_currency(capital_total)}) by {_fmt_currency(-gap)}. Either increase debt sizing (raise LTV or DSCR), reduce Uses, or add equity.",
            "meta": {"capital_total": capital_total, "uses_total": uses_total, "gap": gap},
        }

    # ── Factor 2: DSCR ──
    dscr_val = None
    dscr_min = None
    if outputs is not None and getattr(outputs, "dscr", None):
        try:
            dscr_val = float(outputs.dscr)
        except (TypeError, ValueError):
            dscr_val = None
    if inputs is not None and getattr(inputs, "dscr_minimum", None):
        try:
            dscr_min = float(inputs.dscr_minimum)
        except (TypeError, ValueError):
            dscr_min = None

    if dscr_val is None or dscr_min is None:
        dscr_status = {
            "status": "na",
            "label": "DSCR not computed",
            "detail": "Run Compute to calculate DSCR. Requires debt modules and an operational NOI.",
            "meta": {"dscr": None, "dscr_min": dscr_min},
        }
    elif dscr_val >= dscr_min:
        headroom = dscr_val - dscr_min
        dscr_status = {
            "status": "ok",
            "label": f"DSCR {dscr_val:.2f}× (min {dscr_min:.2f}×)",
            "detail": f"DSCR is {headroom:.2f}× above the minimum. The deal comfortably covers its debt service.",
            "meta": {"dscr": dscr_val, "dscr_min": dscr_min, "headroom": headroom},
        }
    else:
        shortfall = dscr_min - dscr_val
        dscr_status = {
            "status": "fail",
            "label": f"DSCR {dscr_val:.2f}× < min {dscr_min:.2f}×",
            "detail": f"DSCR is {shortfall:.2f}× below the minimum. The deal isn't producing enough NOI to cover debt service at lender requirements. Reduce debt, increase NOI, or lower the DSCR minimum if your lender allows.",
            "meta": {"dscr": dscr_val, "dscr_min": dscr_min, "shortfall": shortfall},
        }

    # ── Factor 3: LTV ──
    # Compute actual LTV = total non-bridge debt / property value (NOI / exit cap).
    # Always shown to the user as informational. Green/red treatment ONLY when
    # sizing mode is dual_constraint (because otherwise LTV isn't a constraint
    # the engine actively targets — it's just a derived number).
    sizing_mode = (getattr(inputs, "debt_sizing_mode", None) or "") if inputs else ""
    is_dual_constraint = (sizing_mode == "dual_constraint")

    # Actual LTV calculation
    _DEC_ZERO = Decimal("0")
    total_non_bridge_debt = _DEC_ZERO
    for m in capital_modules:
        src = m.source or {}
        if src.get("is_bridge"):
            continue
        ft = str(getattr(m, "funder_type", "")).replace("FunderType.", "")
        if ft in {"permanent_debt", "senior_debt", "mezzanine_debt", "construction_loan",
                  "acquisition_loan", "pre_development_loan", "bond", "bridge", "soft_loan"}:
            amt = src.get("amount")
            if amt:
                try:
                    total_non_bridge_debt += Decimal(str(amt))
                except Exception:
                    pass

    noi_dec = Decimal(str(outputs.noi_stabilized)) if (outputs and getattr(outputs, "noi_stabilized", None)) else _DEC_ZERO
    exit_cap = Decimal(str(inputs.exit_cap_rate_pct)) if (inputs and getattr(inputs, "exit_cap_rate_pct", None)) else _DEC_ZERO
    property_value = (noi_dec / (exit_cap / Decimal("100"))) if (noi_dec > 0 and exit_cap > 0) else _DEC_ZERO
    actual_ltv_pct = float(total_non_bridge_debt / property_value * Decimal("100")) if property_value > 0 and total_non_bridge_debt > 0 else None

    # Collect per-module binding info (for dual_constraint diagnostics)
    ltv_binding_modules: list[dict] = []
    any_has_ltv = False
    for m in capital_modules:
        src = m.source or {}
        if src.get("is_bridge"):
            continue
        binding = src.get("binding_constraint")
        ltv_pct_cfg = src.get("ltv_pct")
        if ltv_pct_cfg:
            any_has_ltv = True
        if binding == "ltv":
            ltv_binding_modules.append({
                "label": m.label,
                "ltv_pct": float(ltv_pct_cfg) if ltv_pct_cfg else None,
                "amount": float(src.get("amount") or 0),
            })

    # Headline LTV cap for the "max debt at X% LTV" display. Prefer the LTV
    # setting on the first non-bridge debt module with ltv_pct; fall back to
    # the engine's 65% default when dual_constraint is on; else None.
    _headline_ltv_pct: float | None = None
    for m in capital_modules:
        src = m.source or {}
        if src.get("is_bridge"):
            continue
        _cfg = src.get("ltv_pct")
        if _cfg:
            try:
                _headline_ltv_pct = float(_cfg)
                break
            except (TypeError, ValueError):
                pass
    if _headline_ltv_pct is None and is_dual_constraint:
        _headline_ltv_pct = 65.0

    max_debt_at_ltv: float | None = None
    if _headline_ltv_pct and property_value > 0:
        max_debt_at_ltv = float(property_value * Decimal(str(_headline_ltv_pct)) / Decimal("100"))

    ltv_meta = {
        "actual_ltv_pct": actual_ltv_pct,
        "total_debt": float(total_non_bridge_debt) if total_non_bridge_debt else 0,
        "property_value": float(property_value) if property_value else 0,
        "binding_modules": ltv_binding_modules,
        "headline_ltv_pct": _headline_ltv_pct,
        "max_debt_at_ltv": max_debt_at_ltv,
    }

    if actual_ltv_pct is None:
        # Diagnose exactly which input is missing so the user knows what to fix.
        _missing: list[str] = []
        if noi_dec <= 0:
            _missing.append("stabilized NOI (run Compute)")
        if exit_cap <= 0:
            _missing.append("exit cap rate (set in Settings or the Divestment module)")
        if total_non_bridge_debt <= 0:
            _missing.append("non-bridge debt (add a permanent loan source)")
        if _missing:
            _detail = "Missing: " + "; ".join(_missing) + "."
        else:
            _detail = "Derived property value came out to zero — check inputs."
        ltv_status = {
            "status": "na",
            "label": "LTV not computable",
            "detail": _detail,
            "meta": ltv_meta,
        }
    elif not is_dual_constraint:
        # Informational only — grey pill, no pass/fail
        ltv_status = {
            "status": "na",
            "label": f"LTV {actual_ltv_pct:.1f}%",
            "detail": f"Debt ${float(total_non_bridge_debt):,.0f} / property value ${float(property_value):,.0f} = {actual_ltv_pct:.1f}%. Sizing mode is '{sizing_mode or 'gap_fill'}', so LTV is a derived outcome — not an active constraint. Switch to Dual-Constraint in Deal Setup to size debt by MIN(LTV, DSCR, gap-fill).",
            "meta": ltv_meta,
        }
    elif ltv_binding_modules and gap < -1.0:
        first = ltv_binding_modules[0]
        pct = first.get("ltv_pct")
        ltv_status = {
            "status": "fail",
            "label": f"LTV {pct}% — binding with gap" if pct else "LTV binding with gap",
            "detail": (
                f"{first['label']} is sized at its LTV cap "
                f"({pct}% of $NOI/exit_cap property value)"
                if pct else
                f"{first['label']} is sized at its LTV cap"
            ) + (
                ". DSCR may have headroom, but dual-constraint sizing uses "
                "MIN(LTV, DSCR, gap-fill) — the lowest cap wins. To close "
                "the Sources gap, raise the LTV on this source (or switch "
                "to a different sizing mode)."
            ),
            "meta": ltv_meta,
        }
    elif ltv_binding_modules:
        first = ltv_binding_modules[0]
        pct = first.get("ltv_pct")
        ltv_status = {
            "status": "ok",
            "label": f"LTV {actual_ltv_pct:.1f}% (cap {pct}%)" if pct else f"LTV {actual_ltv_pct:.1f}%",
            "detail": f"{first['label']} is sized exactly at the LTV cap. Sources = Uses, so this is fine.",
            "meta": ltv_meta,
        }
    else:
        ltv_status = {
            "status": "ok",
            "label": f"LTV {actual_ltv_pct:.1f}% (slack)",
            "detail": "LTV is not the binding constraint — DSCR or gap-fill is sizing your debt. Plenty of LTV headroom.",
            "meta": ltv_meta,
        }

    # ── Overall rollup ──
    factors = [su_status, dscr_status, ltv_status]
    failing_count = sum(1 for f in factors if f["status"] in ("fail", "warn"))
    if failing_count == 0:
        overall = "ok"
    else:
        overall = "warn"

    return {
        "overall": overall,
        "failing_count": failing_count,
        "sources_uses": su_status,
        "dscr": dscr_status,
        "ltv": ltv_status,
    }


@router.get("/ui/models/{model_id}/calc-status", response_class=HTMLResponse)
def _render_calc_status_pill_html(status: dict, model_id: UUID) -> str:
    """Render the calc-status pill button HTML from a computed status dict."""
    if status["overall"] == "ok":
        label = "✓ Calculation Valid"
        cls = "ok"
    else:
        n = status["failing_count"]
        _specific: list[str] = []
        su = status.get("sources_uses", {})
        if su.get("status") in ("fail", "warn"):
            _gap = (su.get("meta") or {}).get("gap") or 0
            if _gap < 0:
                _specific.append(f"-${abs(float(_gap)):,.0f} Sources Gap")
            elif _gap > 0:
                _specific.append(f"+${float(_gap):,.0f} Sources Surplus")
        _dscr_f = status.get("dscr", {})
        if _dscr_f.get("status") in ("fail", "warn"):
            _dscr_val = (_dscr_f.get("meta") or {}).get("dscr")
            if _dscr_val is not None:
                _specific.append(f"{float(_dscr_val):.2f}× DSCR — Too Low")
            else:
                _specific.append("DSCR — Issue")
        _ltv_f = status.get("ltv", {})
        if _ltv_f.get("status") in ("fail", "warn"):
            _actual = (_ltv_f.get("meta") or {}).get("actual_ltv_pct")
            if _actual is not None:
                _specific.append(f"{float(_actual):.1f}% LTV — Too High")
            else:
                _specific.append("LTV — Too High")
        if n == 1 and _specific:
            label = f"⚠ {_specific[0]}"
        else:
            label = f"⚠ {n} issue{'s' if n != 1 else ''}"
        cls = "warn"
    return (
        f'<button type="button" class="calc-status-pill {cls}" '
        f'hx-get="/ui/models/{model_id}/calc-status/modal" '
        f'hx-target="#calc-status-modal-body" '
        f'hx-swap="innerHTML" '
        f'onclick="document.getElementById(\'calc-status-modal\').style.display=\'flex\'">'
        f'{label}</button>'
    )


async def model_calc_status_pill(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Returns the center-top calculation status pill HTML.

    Green pill = all factors clear. Yellow pill = N factors failing.
    Click opens the Calculation Status modal via HTMX.
    """
    data = await _load_builder_data(session, model_id)
    status = _compute_calc_status(data)
    return HTMLResponse(_render_calc_status_pill_html(status, model_id))


@router.get("/ui/models/{model_id}/calc-status/modal", response_class=HTMLResponse)
async def model_calc_status_modal(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Returns the modal body HTML with the 3-factor diagnostic.

    Emits an HX-Trigger response header so the topbar pill re-fetches its
    state whenever the modal opens — keeps pill and modal in lockstep.
    """
    data = await _load_builder_data(session, model_id)
    status = _compute_calc_status(data)
    response = templates.TemplateResponse(
        request,
        "partials/calc_status_modal.html",
        {"status": status, "model_id": str(model_id)},
    )
    response.headers["HX-Trigger"] = "calcStatusChanged"
    return response


@router.get("/ui/models/{model_id}/balance-bar", response_class=HTMLResponse)
async def model_balance_bar(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """DEPRECATED — kept for back-compat. Redirects to calc-status pill.
    Sidebar balance bar replaced by center-top status pill.
    """
    return await model_calc_status_pill(request, model_id, session)


@router.get("/ui/models/{model_id}/module-nav")
async def model_module_nav(
    request: Request,
    model_id: UUID,
    session: DBSession,
    module: str = "",
) -> _TemplateResponse:
    """Returns the module nav cards partial for sidebar live-refresh after mutations."""
    data = await _load_builder_data(session, model_id)
    ctx: dict[str, Any] = {
        "request": request,
        "active_module": module,
        "locked": not data.get("timeline_approved", False),
        "deal_setup_complete": data.get("deal_setup_complete", False),
        "nav_base_path": f"/models/{model_id}/builder",
        **{k: data.get(k) for k in (
            "capital_module_count", "capital_total",
            "use_line_count", "uses_total",
            "income_stream_count", "revenue_annual",
            "expense_line_count", "opex_annual",
            "carrying_annual",
            "equity_ownership", "org_owner_fallback",
            "deferred_uses", "deferred_total", "profit_total",
            "divestment_total", "phase_summaries", "outputs",
            "income_mode", "noi_annual",
            "unit_mix_count", "total_units",
        )},
    }
    return templates.TemplateResponse(request, "partials/model_builder_nav_cards.html", ctx)


@router.get("/ui/models/{model_id}/export.xlsx")
async def download_model_export(
    model_id: UUID,
    session: DBSession,
) -> StreamingResponse:
    """Download a round-trip-capable Excel workbook for this deal model."""
    from app.exporters.excel_export import export_deal_model_workbook, make_export_filename
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    workbook_bytes = await export_deal_model_workbook(model_id, session)
    filename = make_export_filename(model)
    return StreamingResponse(
        iter([workbook_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/ui/models/{model_id}/import-template.xlsx")
async def download_import_template(model_id: UUID) -> StreamingResponse:
    """Download a pre-formatted Excel template for bulk import of Uses and OpEx line items."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.Workbook()

    # ── Shared styles ──────────────────────────────────────────────────────────
    hdr_font = Font(bold=True, size=10, color="FFFFFF")
    hdr_fill_uses = PatternFill("solid", fgColor="2563EB")   # blue
    hdr_fill_opex = PatternFill("solid", fgColor="059669")   # green
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    hint_font = Font(italic=True, size=9, color="6B7280")
    hint_fill = PatternFill("solid", fgColor="F9FAFB")

    def _set_col_width(ws, col_letter, width):
        ws.column_dimensions[col_letter].width = width

    def _header_row(ws, headers, fill):
        ws.append(headers)
        for i, _ in enumerate(headers, 1):
            cell = ws.cell(row=1, column=i)
            cell.font = hdr_font
            cell.fill = fill
            cell.alignment = hdr_align
        ws.row_dimensions[1].height = 28

    def _hint_row(ws, hints):
        ws.append(hints)
        for i, _ in enumerate(hints, 1):
            cell = ws.cell(row=2, column=i)
            cell.font = hint_font
            cell.fill = hint_fill
            cell.alignment = Alignment(wrap_text=True)
        ws.row_dimensions[2].height = 36

    # ── Uses sheet ─────────────────────────────────────────────────────────────
    ws_uses = wb.active
    ws_uses.title = "Uses"
    _header_row(ws_uses, ["Label", "Phase", "Amount ($)", "Deferred Dev Fee?", "Notes"], hdr_fill_uses)
    _hint_row(ws_uses, [
        "e.g. Hard Costs, Soft Costs, Contingency",
        "acquisition | pre_development | construction | exit",
        "Dollar amount (no commas)",
        "yes / no — deferred developer fee?",
        "Optional notes",
    ])
    # Phase validation
    phase_dv = DataValidation(
        type="list",
        formula1='"acquisition,pre_development,construction,exit"',
        allow_blank=True,
    )
    ws_uses.add_data_validation(phase_dv)
    phase_dv.sqref = "B3:B500"
    # Deferred dv
    bool_dv = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    ws_uses.add_data_validation(bool_dv)
    bool_dv.sqref = "D3:D500"
    # Widths
    for col, w in zip("ABCDE", [32, 22, 16, 18, 30]):
        _set_col_width(ws_uses, col, w)
    # 3 sample rows
    for label, phase, amt in [
        ("Hard Costs", "construction", 480000),
        ("Soft Costs", "construction", 72000),
        ("Contingency (10%)", "construction", 55200),
    ]:
        ws_uses.append([label, phase, amt, "no", ""])

    # ── OpEx sheet ─────────────────────────────────────────────────────────────
    ws_opex = wb.create_sheet("OpEx")
    _header_row(ws_opex, [
        "Label", "Amount", "Per", "Escalation (%/yr)",
        "Scale w/ Lease-Up?", "Lease-Up Floor (%)", "Active Phases", "Notes",
    ], hdr_fill_opex)
    _hint_row(ws_opex, [
        "e.g. Property Tax, Insurance",
        "Dollar value",
        "flat | per_unit | per_sqft_residential | per_sqft_commercial",
        "e.g. 3.0",
        "yes / no",
        "0–100 (% of stabilized when vacant)",
        "construction, lease_up, stabilized (comma-separated)",
        "Optional",
    ])
    per_dv = DataValidation(
        type="list",
        formula1='"flat,per_unit,per_sqft_residential,per_sqft_commercial"',
        allow_blank=True,
    )
    ws_opex.add_data_validation(per_dv)
    per_dv.sqref = "C3:C500"
    ws_opex.add_data_validation(bool_dv)
    bool_dv.sqref = "E3:E500"
    for col, w in zip("ABCDEFGH", [28, 14, 22, 16, 18, 18, 30, 24]):
        _set_col_width(ws_opex, col, w)
    # 3 sample rows
    for label, amt, per, esc, scale, floor, phases in [
        ("Property Tax", 18000, "flat", 3.0, "no", "", "stabilized"),
        ("Insurance", 9600, "flat", 3.0, "no", "", "stabilized"),
        ("Property Management", 8, "per_unit", 3.0, "yes", 25, "lease_up, stabilized"),
    ]:
        ws_opex.append([label, amt, per, esc, scale, floor, phases, ""])

    # ── Stream to response ─────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=import-template.xlsx"},
    )


@router.post("/ui/models/{model_id}/noi-inputs", response_class=HTMLResponse)
async def save_noi_inputs(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Save NOI mode inputs (stabilized NOI + escalation rate) and return refreshed form."""
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("Not found", status_code=404)
    default_project = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at).limit(1)
    )).scalar_one_or_none()
    if default_project is None:
        return HTMLResponse("No project", status_code=400)
    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == default_project.id)
    )).scalar_one_or_none()
    if inputs is None:
        return HTMLResponse("No inputs", status_code=400)

    form = await request.form()
    noi_raw = str(form.get("noi_stabilized_input", "")).strip()
    esc_raw = form.get("noi_escalation_rate_pct", "3")
    # Strip any display formatting ($ and commas) before parsing.
    noi_clean = noi_raw.replace("$", "").replace(",", "").strip()
    try:
        inputs.noi_stabilized_input = Decimal(noi_clean) if noi_clean else None
    except Exception:
        inputs.noi_stabilized_input = None
    try:
        inputs.noi_escalation_rate_pct = Decimal(str(esc_raw)) if esc_raw else Decimal("3")
    except Exception:
        inputs.noi_escalation_rate_pct = Decimal("3")
    session.add(inputs)
    await session.commit()
    await session.refresh(inputs)

    _noi_val = float(inputs.noi_stabilized_input) if inputs.noi_stabilized_input else ""
    _esc_val = float(inputs.noi_escalation_rate_pct) if inputs.noi_escalation_rate_pct else 3.0
    html = f"""<form hx-post="/ui/models/{model_id}/noi-inputs"
        hx-target="this"
        hx-swap="outerHTML"
        style="max-width:480px">
    <div style="background:var(--success-faint,#f0fdf4);border:1px solid var(--success,#22c55e);border-radius:6px;padding:8px 12px;margin-bottom:16px;font-size:12px;color:var(--success,#16a34a)">
      ✓ NOI inputs saved.
    </div>
    <div class="field-group" style="margin-bottom:20px">
      <label style="display:block;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary);margin-bottom:4px">Stabilized NOI (Annual)</label>
      <input type="number" name="noi_stabilized_input" step="1000" min="0"
             value="{_noi_val}" placeholder="e.g. 500000"
             style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px;background:var(--bg);color:var(--text)">
      <div style="font-size:11px;color:var(--text-muted);margin-top:3px">Net Operating Income at stabilization — pre-debt service, post-OpEx (even though OpEx is not modeled separately).</div>
    </div>
    <div class="field-group" style="margin-bottom:20px">
      <label style="display:block;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary);margin-bottom:4px">Annual NOI Escalation Rate (%)</label>
      <input type="number" name="noi_escalation_rate_pct" step="0.25" min="0" max="20"
             value="{_esc_val}" placeholder="3.0"
             style="width:140px;box-sizing:border-box;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px;background:var(--bg);color:var(--text)">
      <div style="font-size:11px;color:var(--text-muted);margin-top:3px">Compound annual growth applied to NOI each year. Typical: 2–4%.</div>
    </div>
    <div>
      <button type="submit" class="btn btn-primary">Save NOI Inputs</button>
    </div>
  </form>"""
    return HTMLResponse(html)


@router.get("/ui/models/{model_id}/line-form", response_class=HTMLResponse)
async def model_builder_line_form(
    request: Request,
    model_id: UUID,
    session: DBSession,
    type: str = Query(default="uses"),
    id: str = Query(default=""),
    phase: str = Query(default=""),
) -> HTMLResponse:
    """Serves the add/edit form inside the line-item drawer."""
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)

    existing = None
    if id:
        try:
            eid = UUID(id)
            if type in ("use_lines", "uses"):
                existing = await session.get(UseLine, eid)
            elif type in ("income_streams", "revenue"):
                existing = await session.get(IncomeStream, eid)
            elif type in ("expense_lines", "opex"):
                existing = await session.get(OperatingExpenseLine, eid)
            elif type in ("capital_modules", "sources"):
                existing = await session.get(CapitalModule, eid)
            elif type in ("waterfall_tiers", "waterfall"):
                existing = await session.get(WaterfallTier, eid)
            elif type in ("milestones", "timeline"):
                existing = await session.get(Milestone, eid)
            elif type == "unit_mix":
                existing = await session.get(UnitMix, eid)
        except ValueError:
            pass

    # For milestone forms: load siblings + compute which would be circular triggers
    sibling_milestones = []
    circular_ids: set = set()
    trigger_end_date = None  # ISO string passed to JS for end-date preview
    default_trigger_id: str | None = None
    if type in ("milestones", "timeline"):
        default_project = (await session.execute(
            select(Project).where(Project.scenario_id == model_id).order_by(Project.created_at.asc()).limit(1)
        )).scalar_one_or_none()
        if default_project:
            all_ms = list((await session.execute(
                select(Milestone).where(Milestone.project_id == default_project.id)
            )).scalars())
            _SPHASE_ORDER = [
                "offer_made", "under_contract", "close", "pre_development",
                "construction", "operation_lease_up", "operation_stabilized", "divestment",
            ]
            def _sphase_idx(m):
                raw = str(m.milestone_type).replace("MilestoneType.", "")
                return next((i for i, v in enumerate(_SPHASE_ORDER) if v == raw), 99)
            editing_id = existing.id if existing else None
            sibling_milestones = sorted(
                [m for m in all_ms if m.id != editing_id],
                key=_sphase_idx
            )
            ms_map_local = {m.id: m for m in all_ms}
            # Detect circular: candidate Y is circular if following Y's trigger chain hits editing_id
            if editing_id:
                for candidate in sibling_milestones:
                    visited: set = set()
                    cur = candidate
                    while cur and cur.trigger_milestone_id:
                        if cur.trigger_milestone_id == editing_id:
                            circular_ids.add(candidate.id)
                            break
                        if cur.id in visited:
                            break
                        visited.add(cur.id)
                        cur = ms_map_local.get(cur.trigger_milestone_id)
            # default_trigger_id is no longer used by the template — predecessor
            # auto-selection is handled client-side by _msAutoTrigger() JS in the form.
            # Kept as a no-op so the template context key still exists.
            # Resolve trigger's end date so JS can preview end date on the form
            if existing and existing.trigger_milestone_id:
                trigger = ms_map_local.get(existing.trigger_milestone_id)
                if trigger:
                    t_end = trigger.computed_end(ms_map_local)
                    if t_end:
                        trigger_end_date = t_end.isoformat()

    # Lock duration for operation_stabilized when no divestment milestone exists
    lock_duration = False
    _STABILIZED_AUTO_DAYS = 10950
    if (
        existing
        and hasattr(existing, "milestone_type")
        and str(existing.milestone_type).replace("MilestoneType.", "") == "operation_stabilized"
    ):
        has_div = any(
            str(m.milestone_type).replace("MilestoneType.", "") == "divestment"
            for m in sibling_milestones
        )
        if not has_div:
            lock_duration = True

    _PHASE_LABELS = {
        "offer_made": "Offer Made", "under_contract": "Under Contract",
        "close": "Close / Acquisition", "pre_development": "Pre-Development",
        "construction": "Construction", "operation_lease_up": "Lease-Up",
        "operation_stabilized": "Stabilized Operations", "divestment": "Divestment / Exit",
    }

    # Phase options scoped to this deal type — prevents assigning costs to phases that don't exist
    _project_type_str = str(getattr(model, "project_type", "") or "").replace("ProjectType.", "")
    _USE_PHASES_BY_TYPE: dict[str, list[tuple[str, str]]] = {
        "acquisition_minor_reno": [
            ("acquisition", "Acquisition"),
            ("operation", "Operations"),
            ("exit", "Exit / Sale"),
            ("other", "Other"),
        ],
        "acquisition_major_reno": [
            ("acquisition", "Acquisition"),
            ("pre_construction", "Pre-Development"),
            ("construction", "Construction / Renovation"),
            ("operation", "Operations"),
            ("exit", "Exit / Sale"),
            ("other", "Other"),
        ],
        "acquisition_conversion": [
            ("acquisition", "Acquisition"),
            ("conversion", "Conversion"),
            ("operation", "Operations"),
            ("exit", "Exit / Sale"),
            ("other", "Other"),
        ],
        "new_construction": [
            ("acquisition", "Acquisition"),
            ("pre_construction", "Pre-Construction"),
            ("construction", "Construction"),
            ("operation", "Operations"),
            ("exit", "Exit / Sale"),
            ("other", "Other"),
        ],
    }
    _default_phases = [
        ("acquisition", "Acquisition"), ("pre_construction", "Pre-Construction"),
        ("construction", "Construction"), ("renovation", "Renovation"),
        ("conversion", "Conversion"), ("operation", "Operations"),
        ("exit", "Exit / Sale"), ("other", "Other"),
    ]
    valid_use_phases = _USE_PHASES_BY_TYPE.get(_project_type_str, _default_phases)

    # For capital module and use line forms: load milestones for pickers
    milestones_dated_ds: list[dict] = []
    draw_source_window = None
    if type in ("capital_modules", "sources", "use_lines", "uses"):
        from app.models.project import Project as _LFProject
        from app.models.milestone import Milestone as _LFMilestone
        _lf_proj = (await session.execute(
            select(_LFProject).where(_LFProject.scenario_id == model_id).limit(1)
        )).scalar_one_or_none()
        if _lf_proj:
            _lf_opp_ms = list((await session.execute(
                select(_LFMilestone).where(_LFMilestone.opportunity_id == _lf_proj.opportunity_id)
            )).scalars()) if _lf_proj.opportunity_id else []
            _lf_proj_ms = list((await session.execute(
                select(_LFMilestone).where(_LFMilestone.project_id == _lf_proj.id)
            )).scalars())
            _lf_all_ms = _lf_opp_ms + _lf_proj_ms
            _lf_ms_map = {m.id: m for m in _lf_all_ms}
            for m in _lf_all_ms:
                _start = m.computed_start(_lf_ms_map)
                if _start:
                    _key = m.milestone_type.value if hasattr(m.milestone_type, "value") else str(m.milestone_type)
                    milestones_dated_ds.append({"key": _key, "label": _milestone_label(_key), "date": _start})
            milestones_dated_ds.sort(key=lambda x: x["date"])
            # Append "maturity" pseudo-milestone for the Active To dropdown only
            milestones_dated_ds.append({"key": "maturity", "label": "Maturity", "date": None})
        if existing and type in ("capital_modules", "sources"):
            # Prefer lookup by capital_module_id (reliable for wizard-created sources);
            # fall back to label match for legacy sources created before the FK existed.
            _ds_q = select(DrawSource).where(
                DrawSource.scenario_id == model_id,
                DrawSource.capital_module_id == existing.id,
            ).limit(1)
            draw_source_window = (await session.execute(_ds_q)).scalar_one_or_none()
            if draw_source_window is None:
                _ds_q = select(DrawSource).where(
                    DrawSource.scenario_id == model_id,
                    DrawSource.label == existing.label,
                ).limit(1)
                draw_source_window = (await session.execute(_ds_q)).scalar_one_or_none()

    # Exit Vehicle dropdown options (capital modules only). Dynamic from the
    # current module's active_phase_end + siblings' active windows.
    exit_vehicle_options: list[dict] = []
    if type in ("capital_modules", "sources"):
        from app.engines.cashflow import (
            _APS_TO_RANK as _EXIT_APS_RANK,
            _resolve_vehicle as _exit_resolve,
        )

        siblings = list((await session.execute(
            select(CapitalModule).where(CapitalModule.scenario_id == model_id)
        )).scalars())
        others = [m for m in siblings if not existing or m.id != existing.id]
        # Build a "candidate" module stand-in for the resolve call — for new
        # modules we have no saved active_phase_end yet; default to "perpetuity"
        # (→ Maturity as the only option) to match the form's initial blank
        # state.  For existing modules we use their actual saved values.
        # New-source wizards haven't picked active_phase_end yet — so
        # eligible-by-rank gives zero results. Fall back to "all other
        # modules" so the user can pre-select a takeout target. The engine
        # re-validates at compute time and falls back to maturity if the
        # eventual active_phase_end doesn't actually overlap.
        is_new = existing is None
        if not is_new:
            candidate = existing
        else:
            class _Stub:  # minimal shim
                id = None
                active_phase_start = "acquisition"
                active_phase_end = ""
                exit_terms: dict = {}
            candidate = _Stub()

        _vehicle_now, _retirer_now = _exit_resolve(candidate, [candidate] + others)
        saved_val = ""
        if existing is not None and isinstance(existing.exit_terms, dict):
            saved_val = (existing.exit_terms.get("vehicle") or "").strip()

        # Compute eligible source retirers via same rank logic used by engine
        e_rank = _EXIT_APS_RANK.get(
            str(getattr(candidate, "active_phase_end", "") or ""), 99
        )

        def _rank(m: object, side: str) -> int:
            raw = str(getattr(m, f"active_phase_{side}", "") or "")
            if side == "end":
                return _EXIT_APS_RANK.get(raw, 99)
            return _EXIT_APS_RANK.get(raw, 0)

        if is_new:
            # No Active To yet — let the user pick from any other source.
            eligible_sources = list(others)
        elif e_rank < 99:
            eligible_sources = [
                m for m in others
                if _rank(m, "start") <= e_rank < _rank(m, "end")
            ]
        else:
            eligible_sources = []

        def _opt(value: str, label: str) -> dict:
            # If saved vehicle is present, honour it; else default to what
            # _resolve_vehicle picked.
            if saved_val:
                selected = (value == saved_val)
            elif _vehicle_now == "source" and _retirer_now is not None:
                selected = (value == str(getattr(_retirer_now, "id", "")))
            else:
                selected = (value == _vehicle_now)
            return {"value": value, "label": label, "selected": selected}

        exit_vehicle_options.append(_opt("maturity", "Maturity"))
        if e_rank >= 6:
            exit_vehicle_options.append(_opt("sale", "Sale (divestment)"))
        for m in sorted(
            eligible_sources,
            key=lambda r: (int(getattr(r, "stack_position", 0) or 0), str(r.label or "")),
        ):
            exit_vehicle_options.append(_opt(str(m.id), m.label or "(unlabeled)"))

    return templates.TemplateResponse(request, "partials/model_builder_line_form.html", {
        "model": model,
        "form_type": type,
        "existing": existing,
        "default_phase": phase or "acquisition",
        "sibling_milestones": sibling_milestones,
        "circular_ids": circular_ids,
        "trigger_end_date": trigger_end_date,
        "default_trigger_id": default_trigger_id,
        "lock_duration": lock_duration,
        "phase_labels": _PHASE_LABELS,
        "valid_use_phases": valid_use_phases,
        "milestones_dated_ds": milestones_dated_ds,
        "draw_source_window": draw_source_window,
        "exit_vehicle_options": exit_vehicle_options,
    })


# ---------------------------------------------------------------------------
# Portfolios
# ---------------------------------------------------------------------------


@router.get("/portfolios", response_class=HTMLResponse)
async def portfolios_page(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)

    portfolios_result = await session.execute(
        select(Portfolio)
        .options(
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.opportunity),
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.scenario)
                .selectinload(DealModel.operational_outputs),
        )
        .order_by(Portfolio.created_at.desc())
    )
    portfolios = list(portfolios_result.scalars().unique())

    # Build summary row per portfolio
    portfolio_rows = []
    for p in portfolios:
        deal_count = len(p.portfolio_projects)
        irr_values = [
            float(pp.scenario.operational_outputs.project_irr_levered)
            for pp in p.portfolio_projects
            if pp.scenario and pp.scenario.operational_outputs
            and pp.scenario.operational_outputs.project_irr_levered is not None
        ]
        avg_irr = sum(irr_values) / len(irr_values) if irr_values else None
        portfolio_rows.append({
            "id": str(p.id),
            "name": p.name,
            "deal_count": deal_count,
            "avg_irr": avg_irr,
            "created_at_fmt": p.created_at.strftime("%b %-d, %Y") if p.created_at else None,
        })

    return templates.TemplateResponse(
        request, "portfolios.html",
        {
            "portfolios": portfolio_rows,
            **_base_ctx(user, dedup_count, "portfolios"),
        },
    )


@router.get("/ui/deals/search", response_class=HTMLResponse)
async def deals_search(
    request: Request,
    session: DBSession,
    q: str = Query(default=""),
) -> HTMLResponse:
    """HTMX deal search — returns an <ul> of results for portfolio add-deal picker."""
    if not q or len(q) < 2:
        return HTMLResponse("")
    stmt = (
        select(Deal)
        .where(Deal.name.ilike(f"%{q}%"), Deal.status != DealStatus.archived)
        .order_by(Deal.name)
        .limit(8)
    )
    results = list((await session.execute(stmt)).scalars())
    if not results:
        return HTMLResponse('<li style="padding:8px 12px;color:var(--text-muted);font-size:13px">No deals found</li>')
    items = "".join(
        f'<li style="padding:8px 12px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border)" '
        f'onclick="document.getElementById(\'deal-id-input\').value=\'{deal.id}\'; '
        f'document.getElementById(\'deal-search-display\').value=\'{deal.name.replace(chr(39), chr(39)+chr(39))}\'; '
        f'document.getElementById(\'deal-search-results\').innerHTML=\'\'">'
        f'{deal.name}</li>'
        for deal in results
    )
    return HTMLResponse(items)


@router.post("/ui/portfolios/create", response_class=HTMLResponse)
async def create_portfolio(
    request: Request,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    form = await request.form()
    name = str(form.get("name", "")).strip()
    if not name:
        return HTMLResponse("<p class='text-muted'>Portfolio name is required.</p>", status_code=400)

    user = await _get_user(session, request)
    org_id = user.org_id if user else None
    if org_id is None:
        from app.models.org import Organization
        first_org = (await session.execute(select(Organization).limit(1))).scalar_one_or_none()
        if first_org is None:
            return HTMLResponse("<p class='text-muted'>No organization found.</p>", status_code=400)
        org_id = first_org.id

    p = Portfolio(org_id=org_id, name=name)
    session.add(p)
    await session.commit()
    return RedirectResponse(url=f"/portfolios/{p.id}", status_code=303)


@router.get("/portfolios/{portfolio_id}", response_class=HTMLResponse)
async def portfolio_detail(
    request: Request,
    portfolio_id: UUID,
    session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)

    portfolio = await session.get(
        Portfolio,
        portfolio_id,
        options=[
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.opportunity),
            selectinload(Portfolio.portfolio_projects)
                .selectinload(PortfolioProject.scenario)
                .selectinload(DealModel.operational_outputs),
        ],
    )
    if portfolio is None:
        return HTMLResponse("<p class='text-muted'>Portfolio not found.</p>", status_code=404)

    # Build deal summary rows
    deal_rows = []
    for pp in portfolio.portfolio_projects:
        out = pp.scenario.operational_outputs if pp.scenario else None
        deal_rows.append({
            "opportunity_id": str(pp.project_id),
            "opportunity_name": pp.opportunity.name if pp.opportunity else "—",
            "scenario_id": str(pp.scenario_id) if pp.scenario_id else None,
            "scenario_name": pp.scenario.name if pp.scenario else None,
            "noi": float(out.noi_stabilized) if out and out.noi_stabilized is not None else None,
            "irr": float(out.project_irr_levered) if out and out.project_irr_levered is not None else None,
            "equity_required": float(out.equity_required) if out and out.equity_required is not None else None,
        })

    # Build Gantt — we need to load Deal + milestones for each pp's scenario
    # Load all Deals that link to these opportunities via DealOpportunity
    opp_ids = [pp.project_id for pp in portfolio.portfolio_projects if pp.project_id]
    gantt_rows: list[dict] = []
    if opp_ids:
        deals_stmt = (
            select(Deal)
            .join(DealOpportunity, DealOpportunity.deal_id == Deal.id)
            .where(DealOpportunity.opportunity_id.in_(opp_ids))
            .options(
                selectinload(Deal.scenarios).selectinload(DealModel.projects).selectinload(Project.milestones),
                selectinload(Deal.deal_opportunities).selectinload(DealOpportunity.opportunity),
            )
            .distinct()
        )
        deals_for_gantt = list((await session.execute(deals_stmt)).scalars().unique())

        # Match each pp opportunity → Deal, build entries list
        entries = []
        for deal in deals_for_gantt:
            opp = _first_opportunity(deal)
            if opp is None or opp.id not in opp_ids:
                continue
            scenario = _primary_scenario(deal)
            entries.append((deal.name, scenario.name if scenario else "", deal))

        gantt_data = _build_portfolio_gantt(entries)

    # Aggregate stats
    irr_values = [r["irr"] for r in deal_rows if r["irr"] is not None]
    equity_values = [r["equity_required"] for r in deal_rows if r["equity_required"] is not None]
    noi_values = [r["noi"] for r in deal_rows if r["noi"] is not None]

    return templates.TemplateResponse(
        request, "portfolio_detail.html",
        {
            "portfolio": portfolio,
            "portfolio_id": str(portfolio.id),
            "portfolio_name": portfolio.name,
            "deal_rows": deal_rows,
            "gantt_data": gantt_data,
            "stats": {
                "deal_count": len(deal_rows),
                "avg_irr": sum(irr_values) / len(irr_values) if irr_values else None,
                "total_equity": sum(equity_values) if equity_values else None,
                "total_noi": sum(noi_values) if noi_values else None,
            },
            **_base_ctx(user, dedup_count, "portfolios"),
        },
    )


@router.post("/ui/portfolios/{portfolio_id}/add-deal", response_class=HTMLResponse)
async def portfolio_add_deal(
    request: Request,
    portfolio_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Add a deal (by Deal.id) to a portfolio."""
    form = await request.form()
    deal_id_raw = str(form.get("deal_id", "")).strip()
    try:
        deal_id = UUID(deal_id_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid deal ID.</p>", status_code=400)

    # Resolve opportunity + active scenario from the Deal
    deal = await session.get(
        Deal, deal_id,
        options=[
            selectinload(Deal.scenarios),
            selectinload(Deal.deal_opportunities),
        ],
    )
    if deal is None:
        return HTMLResponse("<p class='text-muted'>Deal not found.</p>", status_code=404)

    opp_link = deal.deal_opportunities[0] if deal.deal_opportunities else None
    if opp_link is None:
        return HTMLResponse("<p class='text-muted'>Deal has no linked opportunity.</p>", status_code=400)

    active_scenario = _primary_scenario(deal)

    # Upsert — skip if opportunity already in portfolio
    existing = (await session.execute(
        select(PortfolioProject).where(
            PortfolioProject.portfolio_id == portfolio_id,
            PortfolioProject.project_id == opp_link.opportunity_id,
        )
    )).scalar_one_or_none()

    if existing is None:
        pp = PortfolioProject(
            portfolio_id=portfolio_id,
            project_id=opp_link.opportunity_id,
            scenario_id=active_scenario.id if active_scenario else None,
        )
        session.add(pp)
    await session.commit()

    return RedirectResponse(url=f"/portfolios/{portfolio_id}", status_code=303)


@router.post("/ui/portfolios/{portfolio_id}/remove-deal", response_class=HTMLResponse)
async def portfolio_remove_deal(
    request: Request,
    portfolio_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    from sqlalchemy import delete as sa_delete
    form = await request.form()
    opp_id_raw = str(form.get("opportunity_id", "")).strip()
    try:
        opp_id = UUID(opp_id_raw)
    except ValueError:
        return HTMLResponse("<p class='text-muted'>Invalid opportunity ID.</p>", status_code=400)

    await session.execute(
        sa_delete(PortfolioProject).where(
            PortfolioProject.portfolio_id == portfolio_id,
            PortfolioProject.project_id == opp_id,
        )
    )
    await session.commit()
    return RedirectResponse(url=f"/portfolios/{portfolio_id}", status_code=303)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Data Cleanup
# ---------------------------------------------------------------------------

@router.get("/dedup", response_class=HTMLResponse)
async def dedup_page(
    request: Request, session: DBSession,
    tab: str = Query(default="pending"),
    vd_user_id: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = await _get_user(session, request)
    dedup_count = await _get_dedup_count(session)
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
        **_base_ctx(user, dedup_count, "dedup", address_issues_count),
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

    return templates.TemplateResponse(request, "partials/dedup_compare.html", {
        "request": request,
        "candidate_id": str(candidate_id),
        "src_a": src_a,
        "src_b": src_b,
        "addr_a": addr_a,
        "addr_b": addr_b,
        "conflicts": compare["conflicts"],
        "matches": compare["matches"],
    })


@router.post("/ui/dedup/{candidate_id}/keep-separate", response_class=HTMLResponse)
async def ui_dedup_keep_separate(
    request: Request, candidate_id: UUID, session: DBSession,
    vd_user_id: str | None = Cookie(default=None),
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
    vd_user_id: str | None = Cookie(default=None),
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


# ---------------------------------------------------------------------------
# Draw Schedule module
# ---------------------------------------------------------------------------

def _milestone_label(key: str) -> str:
    labels = {
        "offer_made": "Offer Made",
        "under_contract": "Under Contract",
        "close": "Close",
        "pre_development": "Pre-Development",
        "construction": "Construction",
        "operation_lease_up": "Lease-Up",
        "operation_stabilized": "Stabilized",
        "divestment": "Divestment",
    }
    return labels.get(key, key.replace("_", " ").title())


async def _run_draw_schedule(
    session: AsyncSession,
    model_id: UUID,
    *,
    writeback: bool = False,
) -> "Any | None":
    """Run the draw schedule engine; optionally write computed amounts back to DB.

    All sources are auto-sized (total_commitment=None) so the engine determines
    each source's commitment from Uses + carry. Returns the DrawSchedule, or None
    if the engine cannot run (missing milestones / sources).
    """
    from app.engines.draw_schedule import (
        DealMilestone,
        DrawScheduleCalculator,
        DrawScheduleConfig,
        DrawScheduleInputs,
        SourceDef,
        UseLineItem,
    )
    from datetime import datetime as _dt_cls

    ctx = await _load_draw_schedule_ctx(session, model_id)
    if not ctx:
        return None

    milestones_dated = ctx["milestones_dated"]
    draw_sources_db   = ctx["draw_sources"]
    use_lines_db      = ctx["use_lines_db"]

    if not milestones_dated or not draw_sources_db:
        return None

    # ── Milestones ──────────────────────────────────────────────────────────
    engine_milestones = [
        DealMilestone(
            key=m["key"],
            label=m["label"],
            date=_dt_cls.combine(m["date"], _dt_cls.min.time()),
        )
        for m in milestones_dated
    ]

    # ── Use lines ───────────────────────────────────────────────────────────
    _phase_to_ms = {
        "acquisition": "close", "pre_construction": "pre_development",
        "construction": "construction", "renovation": "construction",
        "conversion": "construction", "operation": "operation_stabilized",
        "exit": "divestment", "other": "close",
    }
    _phase_to_cat = {
        "acquisition": "land", "pre_construction": "soft_costs",
        "construction": "hard_costs", "renovation": "hard_costs",
        "conversion": "hard_costs", "operation": "reserves",
        "exit": "fees", "other": "other",
    }
    _ms_keys_set = {m["key"] for m in milestones_dated}
    _ms_date_idx  = {m["key"]: m["date"] for m in milestones_dated}
    engine_uses: list[UseLineItem] = []
    for ul in use_lines_db:
        raw_phase = str(ul.phase).replace("UseLinePhase.", "")
        ms_key = getattr(ul, "milestone_key", None) or _phase_to_ms.get(raw_phase, "close")
        if ms_key not in _ms_keys_set and _ms_keys_set:
            ms_key = next(iter(_ms_keys_set))
        raw_timing   = str(ul.timing_type).replace("UseLineTiming.", "")
        spread_months = 1
        spread_to_date = None
        if raw_timing == "spread":
            ms_key_to = getattr(ul, "milestone_key_to", None)
            if ms_key_to and ms_key_to in _ms_date_idx:
                spread_to_date = _dt_cls.combine(_ms_date_idx[ms_key_to], _dt_cls.min.time())
            else:
                for i, m in enumerate(milestones_dated):
                    if m["key"] == ms_key and i + 1 < len(milestones_dated):
                        nxt = milestones_dated[i + 1]["date"]
                        cur = m["date"]
                        diff_months = (nxt.year - cur.year) * 12 + (nxt.month - cur.month)
                        spread_months = max(1, diff_months)
                        break
        engine_uses.append(UseLineItem(
            key=str(ul.id), label=ul.label,
            category=_phase_to_cat.get(raw_phase, "other"),
            total_amount=Decimal(str(ul.amount)),
            milestone_key=ms_key, spread_months=spread_months, spread_to_date=spread_to_date,
        ))

    # ── Sources — always auto-size (total_commitment=None) ─────────────────
    _last_real_ms  = milestones_dated[-1]["key"] if milestones_dated else "operation_stabilized"
    _real_ms_keys  = {m["key"] for m in milestones_dated}
    engine_sources: list[SourceDef] = []
    for ds in draw_sources_db:
        _to  = ds.active_to_milestone   if ds.active_to_milestone   in _real_ms_keys else _last_real_ms
        _frm = ds.active_from_milestone if ds.active_from_milestone in _real_ms_keys else (
            milestones_dated[0]["key"] if milestones_dated else _to
        )
        engine_sources.append(SourceDef(
            key=str(ds.id), label=ds.label,
            source_type=ds.source_type,
            draw_every_n_months=ds.draw_every_n_months,
            annual_interest_rate=Decimal(str(ds.annual_interest_rate)),
            active_from_milestone=_frm, active_to_milestone=_to,
            active_from_offset_days=getattr(ds, "active_from_offset_days", 0) or 0,
            active_to_offset_days=getattr(ds, "active_to_offset_days", 0) or 0,
            total_commitment=None,  # auto-size always
        ))
    engine_sources.sort(key=lambda s: _ms_date_idx.get(s.active_from_milestone, _dt_cls.max))

    if not engine_sources:
        return None

    config = DrawScheduleConfig(
        min_reserve_construction=ctx["reserve_construction"],
        min_reserve_operational=ctx["reserve_operational"],
        operational_start_milestone="operation_lease_up",
    )
    try:
        schedule = DrawScheduleCalculator(DrawScheduleInputs(
            milestones=engine_milestones, uses=engine_uses,
            sources=engine_sources, config=config,
        )).calculate()
    except Exception:
        return None

    if writeback:
        _drawn_by_key = {ss.source_key: ss.total_drawn for ss in schedule.source_summaries}
        for ds in draw_sources_db:
            _drawn = _drawn_by_key.get(str(ds.id))
            if _drawn is None:
                continue
            ds.total_commitment = Decimal(str(_drawn))
            if ds.capital_module_id:
                _cm = await session.get(CapitalModule, ds.capital_module_id)
                if _cm:
                    _src = dict(_cm.source or {})
                    _src["amount"] = float(_drawn)
                    _cm.source = _src
            else:
                _cm_q = select(CapitalModule).where(
                    CapitalModule.scenario_id == model_id,
                    CapitalModule.label == ds.label,
                ).limit(1)
                _cm = (await session.execute(_cm_q)).scalar_one_or_none()
                if _cm:
                    _src = dict(_cm.source or {})
                    _src["amount"] = float(_drawn)
                    _cm.source = _src
        await session.flush()

    return schedule


async def _load_draw_schedule_ctx(
    session: AsyncSession,
    model_id: UUID,
) -> dict[str, Any]:
    """Shared context for draw schedule panel and calculate endpoint."""
    from app.models.project import Project
    from app.models.milestone import Milestone

    model = await session.get(DealModel, model_id)
    if model is None:
        return {}

    # Load draw sources ordered by sort_order
    draw_sources = list((await session.execute(
        select(DrawSource)
        .where(DrawSource.scenario_id == model_id)
        .order_by(DrawSource.sort_order)
    )).scalars())

    # Load use lines (via Project) so we can pass them to the engine
    first_proj = (await session.execute(
        select(Project).where(Project.scenario_id == model_id).limit(1)
    )).scalar_one_or_none()

    use_lines_db: list = []
    project_milestones: list = []
    if first_proj:
        use_lines_db = list((await session.execute(
            select(UseLine).where(UseLine.project_id == first_proj.id)
        )).scalars())
        # Load milestones from both opportunity and project
        opp_ms = list((await session.execute(
            select(Milestone)
            .where(Milestone.opportunity_id == first_proj.opportunity_id)
            .order_by(Milestone.sequence_order)
        )).scalars()) if first_proj.opportunity_id else []
        proj_ms = list((await session.execute(
            select(Milestone)
            .where(Milestone.project_id == first_proj.id)
            .order_by(Milestone.sequence_order)
        )).scalars())
        project_milestones = opp_ms + proj_ms

    # Build milestone map for date resolution
    ms_map = {m.id: m for m in project_milestones}
    milestones_dated = []
    for m in project_milestones:
        start = m.computed_start(ms_map)
        if start:
            milestones_dated.append({
                "key": m.milestone_type.value if hasattr(m.milestone_type, "value") else str(m.milestone_type),
                "label": m.label or _milestone_label(str(m.milestone_type.value if hasattr(m.milestone_type, "value") else m.milestone_type)),
                "date": start,
            })

    # Sort milestones by date (opp + proj may interleave in unusual order)
    milestones_dated.sort(key=lambda m: m["date"])
    milestone_keys = [m["key"] for m in milestones_dated]

    # ---------------------------------------------------------------------------
    # Auto-seed draw_sources from capital_modules when none exist yet
    # ---------------------------------------------------------------------------
    if not draw_sources:
        capital_modules = list((await session.execute(
            select(CapitalModule)
            .where(CapitalModule.scenario_id == model_id)
            .order_by(CapitalModule.stack_position)
        )).scalars())

        # Map capital module phase strings → milestone keys (best-effort)
        _phase_to_ms = {
            "offer_made": "offer_made",
            "under_contract": "under_contract",
            "acquisition": "close",
            "pre_construction": "pre_development",
            "pre_development": "pre_development",
            "construction": "construction",
            "renovation": "construction",
            "lease_up": "operation_lease_up",
            "operation_lease_up": "operation_lease_up",
            "stabilized": "operation_stabilized",
            "operation_stabilized": "operation_stabilized",
            "divestment": "divestment",
        }
        _debt_types = {
            "senior_debt", "mezzanine_debt", "bridge", "construction_loan",
            "soft_loan", "bond", "permanent_debt",
        }

        for i, cm in enumerate(capital_modules):
            raw_from = cm.active_phase_start or "close"
            raw_to = cm.active_phase_end or "operation_stabilized"
            ms_from = _phase_to_ms.get(raw_from, raw_from)
            ms_to = _phase_to_ms.get(raw_to, raw_to)
            # Fall back to first/last milestone if mapped key not in timeline
            if milestone_keys:
                if ms_from not in milestone_keys:
                    ms_from = milestone_keys[0]
                if ms_to not in milestone_keys:
                    ms_to = milestone_keys[-1]

            src = cm.source or {}
            rate_pct = src.get("interest_rate_pct") or 0.0
            annual_rate = Decimal(str(rate_pct)) / Decimal("100")

            funder_raw = str(cm.funder_type).replace("FunderType.", "")
            source_type = "debt" if funder_raw in _debt_types else "equity"
            draw_freq = 2 if source_type == "debt" else 1

            ds = DrawSource(
                id=_uuid_mod.uuid4(),
                scenario_id=model_id,
                capital_module_id=cm.id,
                sort_order=i + 1,
                label=cm.label,
                source_type=source_type,
                draw_every_n_months=draw_freq,
                annual_interest_rate=annual_rate,
                active_from_milestone=ms_from,
                active_to_milestone=ms_to,
                total_commitment=Decimal(str(src["amount"])) if src.get("amount") else None,
            )
            session.add(ds)

        if capital_modules:
            await session.flush()
            draw_sources = list((await session.execute(
                select(DrawSource)
                .where(DrawSource.scenario_id == model_id)
                .order_by(DrawSource.sort_order)
            )).scalars())

    # ---------------------------------------------------------------------------
    # Auto-populate reserve floors from computed use lines when still unset
    # ---------------------------------------------------------------------------
    reserve_construction = Decimal(str(model.min_reserve_construction or 0))
    reserve_operational = Decimal(str(model.min_reserve_operational or 0))

    if (reserve_construction == 0 or reserve_operational == 0) and use_lines_db:
        for ul in use_lines_db:
            lbl = (ul.label or "").strip()
            amt = Decimal(str(ul.amount or 0))
            if reserve_construction == 0 and lbl == "Capitalized Construction Interest":
                reserve_construction = amt
            elif reserve_operational == 0 and lbl == "Operating Reserve":
                reserve_operational = amt

    # ---------------------------------------------------------------------------
    # Build source Gantt rows using the same g2- coordinate system as the
    # timeline Gantt.  builder_gantt_data has epoch/g_min/g_max exposed.
    # ---------------------------------------------------------------------------
    import datetime as _dt
    builder_gantt_data_ds = _builder_gantt_from_milestones(first_proj, project_milestones)
    source_gantt_rows: list[dict] = []
    if builder_gantt_data_ds and draw_sources:
        epoch_d = builder_gantt_data_ds.get("epoch")
        g_min_d = builder_gantt_data_ds.get("g_min", 0)
        g_max_d = builder_gantt_data_ds.get("g_max", 1)
        total_span = max(g_max_d - g_min_d, 1)

        def _day_pct(day_offset: int) -> float:
            return round(100.0 * (day_offset - g_min_d) / total_span, 2)

        ms_date_map = {m["key"]: m["date"] for m in milestones_dated}
        for ds in draw_sources:
            from_date = ms_date_map.get(ds.active_from_milestone)
            to_date = ms_date_map.get(ds.active_to_milestone)
            fade_right = False
            if from_date and epoch_d:
                from_day = (from_date - epoch_d).days
                left = max(0.0, _day_pct(from_day))
                if ds.active_to_milestone not in ms_date_map:
                    # pseudo-milestone (e.g. "maturity"): extend to Gantt right edge, fade out
                    right = 100.0
                    fade_right = True
                elif to_date:
                    to_day = (to_date - epoch_d).days
                    right = min(100.0, _day_pct(to_day))
                else:
                    continue
                source_gantt_rows.append({
                    "label": ds.label,
                    "source_type": ds.source_type,
                    "left_pct": left,
                    "width_pct": max(right - left, 1.5),
                    "fade_right": fade_right,
                })

    # Label map used by the panel to display current active window as text (not editable here)
    milestone_label_map = {m["key"]: m["label"] for m in milestones_dated}
    milestone_label_map["maturity"] = "Maturity"

    return {
        "model": model,
        "draw_sources": draw_sources,
        "milestones_dated": milestones_dated,
        "milestone_label_map": milestone_label_map,
        "use_lines_db": use_lines_db,
        "reserve_construction": reserve_construction,
        "reserve_operational": reserve_operational,
        "milestone_keys": milestone_keys,
        "builder_gantt_data": builder_gantt_data_ds,
        "source_gantt_rows": source_gantt_rows,
    }


@router.get("/ui/models/{model_id}/draw-schedule", response_class=HTMLResponse)
async def draw_schedule_panel(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Returns the draw schedule panel partial for HTMX swap."""
    ctx = await _load_draw_schedule_ctx(session, model_id)
    if not ctx:
        return HTMLResponse("<p class='text-muted'>Model not found.</p>", status_code=404)
    ctx["request"] = request
    ctx["active_module"] = "draw_schedule"
    return templates.TemplateResponse(request, "partials/draw_schedule_panel.html", ctx)


@router.post("/ui/models/{model_id}/draw-schedule/sources", response_class=HTMLResponse)
async def add_draw_source(
    request: Request,
    model_id: UUID,
    session: DBSession,
    label: str = Form(...),
    source_type: str = Form("equity"),
    draw_every_n_months: int = Form(1),
    annual_interest_rate: str = Form("0"),
    active_from_milestone: str = Form(...),
    active_to_milestone: str = Form(...),
    total_commitment: str = Form(""),
) -> HTMLResponse:
    """Add a draw source row."""
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("Model not found", status_code=404)

    # Determine next sort_order
    max_order_row = (await session.execute(
        select(DrawSource.sort_order)
        .where(DrawSource.scenario_id == model_id)
        .order_by(DrawSource.sort_order.desc())
        .limit(1)
    )).scalar_one_or_none()
    next_order = (max_order_row or 0) + 1

    commitment = None
    if total_commitment.strip():
        try:
            commitment = Decimal(total_commitment.strip().replace(",", ""))
        except Exception:
            commitment = None

    ds = DrawSource(
        id=_uuid_mod.uuid4(),
        scenario_id=model_id,
        sort_order=next_order,
        label=label.strip(),
        source_type=source_type,
        draw_every_n_months=max(1, draw_every_n_months),
        annual_interest_rate=Decimal(annual_interest_rate.strip() or "0"),
        active_from_milestone=active_from_milestone,
        active_to_milestone=active_to_milestone,
        total_commitment=commitment,
    )
    session.add(ds)
    await session.flush()

    ctx = await _load_draw_schedule_ctx(session, model_id)
    ctx["request"] = request
    ctx["active_module"] = "draw_schedule"
    return templates.TemplateResponse(request, "partials/draw_schedule_panel.html", ctx)


@router.delete("/ui/models/{model_id}/draw-schedule/sources/{source_id}", response_class=HTMLResponse)
async def delete_draw_source(
    request: Request,
    model_id: UUID,
    source_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Delete a draw source row."""
    ds = await session.get(DrawSource, source_id)
    if ds and ds.scenario_id == model_id:
        await session.delete(ds)
        await session.flush()
    ctx = await _load_draw_schedule_ctx(session, model_id)
    ctx["request"] = request
    ctx["active_module"] = "draw_schedule"
    return templates.TemplateResponse(request, "partials/draw_schedule_panel.html", ctx)


@router.post("/ui/models/{model_id}/draw-schedule/settings", response_class=HTMLResponse)
async def update_draw_schedule_settings(
    request: Request,
    model_id: UUID,
    session: DBSession,
    min_reserve_construction: str = Form("0"),
    min_reserve_operational: str = Form("0"),
) -> HTMLResponse:
    """Update reserve floor settings on the scenario."""
    model = await session.get(DealModel, model_id)
    if model is None:
        return HTMLResponse("Model not found", status_code=404)

    def _parse_dec(val: str) -> Decimal:
        try:
            return Decimal(val.strip().replace(",", "") or "0")
        except Exception:
            return Decimal("0")

    model.min_reserve_construction = _parse_dec(min_reserve_construction)
    model.min_reserve_operational = _parse_dec(min_reserve_operational)
    await session.flush()

    ctx = await _load_draw_schedule_ctx(session, model_id)
    ctx["request"] = request
    ctx["active_module"] = "draw_schedule"
    return templates.TemplateResponse(request, "partials/draw_schedule_panel.html", ctx)


@router.post("/ui/models/{model_id}/draw-schedule/calculate", response_class=HTMLResponse)
async def calculate_draw_schedule(
    request: Request,
    model_id: UUID,
    session: DBSession,
) -> HTMLResponse:
    """Run the draw schedule engine and return the results HTML fragment."""
    ctx = await _load_draw_schedule_ctx(session, model_id)
    if not ctx:
        return HTMLResponse("Model not found", status_code=404)

    milestones_dated = ctx["milestones_dated"]
    draw_sources_db  = ctx["draw_sources"]

    if not milestones_dated:
        return HTMLResponse(
            "<div class='module-empty'><div class='module-empty-icon'>📅</div>"
            "<div class='module-empty-title'>No timeline yet</div>"
            "<div class='module-empty-desc'>Set up milestones in the Timeline module first.</div></div>"
        )
    if not draw_sources_db:
        return HTMLResponse(
            "<div class='module-empty'><div class='module-empty-icon'>💰</div>"
            "<div class='module-empty-title'>No sources defined</div>"
            "<div class='module-empty-desc'>Add at least one funding source above.</div></div>"
        )

    schedule = await _run_draw_schedule(session, model_id, writeback=True)
    if schedule is None:
        return HTMLResponse(
            "<div class='alert alert-danger' style='padding:12px;border-radius:6px;"
            "background:#fef2f2;border:1px solid #fca5a5;color:#dc2626;font-size:13px'>"
            "⚠ Engine error: check milestones and sources are configured.</div>"
        )

    # ── Detect unfunded uses ─────────────────────────────────────────────────
    from app.engines.draw_schedule import UseLineItem
    from datetime import datetime
    _ms_date_index   = {m["key"]: m["date"] for m in milestones_dated}
    _milestone_label_map = {m["key"]: m["label"] for m in milestones_dated}
    _milestone_label_map["maturity"] = "Maturity"
    _covered_ms_keys: set[str] = set()
    for ss in schedule.source_summaries:
        # Find the source's active window from ctx draw_sources_db
        _ds = next((d for d in draw_sources_db if str(d.id) == ss.source_key), None)
        if _ds:
            from_idx = next((i for i, m in enumerate(milestones_dated) if m["key"] == _ds.active_from_milestone), None)
            to_idx   = next((i for i, m in enumerate(milestones_dated) if m["key"] == _ds.active_to_milestone), None)
            if from_idx is not None and to_idx is not None:
                for i in range(from_idx, to_idx + 1):
                    _covered_ms_keys.add(milestones_dated[i]["key"])
    # Build use items for unfunded check
    _phase_to_ms = {
        "acquisition": "close", "pre_construction": "pre_development",
        "construction": "construction", "renovation": "construction",
        "conversion": "construction", "operation": "operation_stabilized",
        "exit": "divestment", "other": "close",
    }
    _ms_keys_set = {m["key"] for m in milestones_dated}
    unfunded_uses: list[dict] = []
    for ul in ctx["use_lines_db"]:
        raw_phase = str(ul.phase).replace("UseLinePhase.", "")
        ms_key = getattr(ul, "milestone_key", None) or _phase_to_ms.get(raw_phase, "close")
        if ms_key not in _ms_keys_set and _ms_keys_set:
            ms_key = next(iter(_ms_keys_set))
        if ms_key not in _covered_ms_keys and (ul.amount or 0) > 0:
            unfunded_uses.append({
                "label": ul.label,
                "amount": ul.amount,
                "milestone_key": ms_key,
                "milestone_label": _milestone_label_map.get(ms_key, ms_key),
            })

    # Filter display: hide sources with no draws and $0-commitment sources from Gantt/table
    active_labels = {ss.source_label for ss in schedule.source_summaries if ss.total_drawn > 0}
    committed_labels = {
        ds.label for ds in draw_sources_db
        if ds.total_commitment and float(ds.total_commitment) > 0
    }
    show_labels = active_labels & committed_labels
    ctx["source_gantt_rows"] = [r for r in ctx.get("source_gantt_rows", []) if r["label"] in show_labels]
    ctx["draw_sources"] = [ds for ds in ctx["draw_sources"] if ds.label in show_labels]

    ctx["schedule"] = schedule
    ctx["unfunded_uses"] = unfunded_uses
    ctx["request"] = request
    ctx["active_module"] = "draw_schedule"
    # Return the full panel (not just results) so sources table always reflects current DB state
    return templates.TemplateResponse(request, "partials/draw_schedule_panel.html", ctx)



@router.patch("/ui/models/{model_id}/draw-schedule/sources/{source_id}", response_class=HTMLResponse)
async def update_draw_source_window(
    request: Request,
    model_id: UUID,
    source_id: UUID,
    session: DBSession,
    active_from_milestone: str = Form(...),
    active_to_milestone: str = Form(...),
) -> HTMLResponse:
    """Update the active window (from/to milestone) of a draw source."""
    ds = await session.get(DrawSource, source_id)
    if ds and ds.scenario_id == model_id:
        ds.active_from_milestone = active_from_milestone
        ds.active_to_milestone = active_to_milestone
        await session.flush()
    ctx = await _load_draw_schedule_ctx(session, model_id)
    ctx["request"] = request
    ctx["active_module"] = "draw_schedule"
    return templates.TemplateResponse(request, "partials/draw_schedule_panel.html", ctx)
