"""Shared helpers for ui.py sub-routers.

Pure utilities (formatting, display maps, deal entity helpers, auth/scope,
count queries, base template context) used across two or more of the
planned ui/ sub-routers. Import from here; never import from ui.py in a
sub-router — that would create a circular dependency.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.config import settings
from app.models.deal import Deal, DealModel, ProjectType
from app.models.ingestion import DedupCandidate, DedupStatus
from app.models.milestone import DEFAULT_DURATIONS, Milestone, MilestoneType
from app.models.opportunity import Opportunity
from app.models.org import User
from app.models.project import Project
from app.models.scraped_listing import ScrapedListing


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Display maps
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
    "acquisition": "Acquisition",
    "value_add": "Value-Add",
    "conversion": "Conversion",
    "new_construction": "New Construction",
}


# ---------------------------------------------------------------------------
# Deal entity helpers
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
    """Return the first Opportunity linked to a Deal via Scenario→Project→Opportunity."""
    for scenario in (deal.scenarios or []):
        for proj in (scenario.projects or []):
            if proj.opportunity is not None:
                return proj.opportunity
    return None


def _deal_address(deal: Deal) -> str | None:
    opp = _first_opportunity(deal)
    if opp is None:
        return None
    return opp.address_normalized or opp.address_raw


def _deal_building_description(deal: Deal) -> str | None:
    """Build a short building description from Opportunity physical attributes."""
    opp = _first_opportunity(deal)
    if opp is None:
        return None
    parts: list[str] = []
    unit_count = opp.units if opp.units is not None else None
    if unit_count:
        parts.append(f"{unit_count} units")
    sqft = opp.gba_sqft if opp.gba_sqft is not None else None
    if sqft:
        parts.append(f"{int(float(sqft)):,} sqft")
    if parts:
        return " · ".join(parts)
    return None


# ---------------------------------------------------------------------------
# Auth & scope
# ---------------------------------------------------------------------------

async def _get_user(session: DBSession, request: Request) -> User | None:
    """Resolve the current user from the signed session cookie."""
    from app.api.auth import COOKIE_NAME, decode_session_token

    token = request.cookies.get(COOKIE_NAME)
    if token:
        uid = decode_session_token(token)
        if uid is not None:
            return await session.get(User, uid)
    return None


def _apply_org_scope(stmt: Any, user: User | None, model: Any) -> Any:
    """Restrict a SELECT to rows owned by the current user's organization.

    No-op when settings.org_isolation_enabled is False. When isolation is on
    and the request has no authenticated user (or no org_id), returns an
    empty-result statement rather than leaking org data.
    """
    if not settings.org_isolation_enabled:
        return stmt
    org_id = getattr(user, "org_id", None) if user is not None else None
    if org_id is None:
        return stmt.where(literal(False))
    return stmt.where(model.org_id == org_id)


def _require_settings_owner(user: User | None) -> None:
    if not (user and user.is_admin):
        raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Badge / count queries (feed into _base_ctx)
# ---------------------------------------------------------------------------

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
                ScrapedListing.apn.is_(None),
            )
        )
        return int(result.scalar_one())
    except Exception:
        return 0


async def _get_conflicts_count(session: AsyncSession) -> int:
    """Parcel conflict queue removed (parcel decommission). Always zero."""
    return 0


async def _get_counts(session: AsyncSession) -> tuple[int, int]:
    return await _get_dedup_count(session), await _get_conflicts_count(session)


# ---------------------------------------------------------------------------
# Base template context
# ---------------------------------------------------------------------------

def _base_ctx(
    user: User | None,
    dedup_count: int,
    active_nav: str,
    address_issues_count: int = 0,
    conflicts_count: int = 0,
) -> dict:
    initials = "??"
    show_billing_settings_menu = False
    if user:
        parts = user.name.split()
        initials = (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else user.name[:2].upper()
        user_email_norm = (user.email or "").strip().lower()
        show_billing_settings_menu = user_email_norm == "stephenjketch@gmail.com"
    return {
        "user_name": user.name if user else "Guest",
        "user_initials": initials,
        "user_color": (user.display_color if user else None) or "#2563EB",
        "user_email_verified": bool(getattr(user, "email_verified", True)) if user else True,
        "is_org_admin": bool(getattr(user, "is_org_admin", False)) if user else False,
        "is_admin": bool(getattr(user, "is_admin", False)) if user else False,
        "show_billing_settings_menu": show_billing_settings_menu,
        "active_nav": active_nav,
        "dedup_count": dedup_count,
        "address_issues_count": address_issues_count,
        "conflicts_count": conflicts_count,
    }


# ---------------------------------------------------------------------------
# General form / query helpers
# ---------------------------------------------------------------------------

def _as_list(v) -> list[str]:
    """Coerce a FastAPI query-param value to a plain list of non-empty strings."""
    if isinstance(v, list):
        return [x for x in v if x]
    if isinstance(v, str) and v:
        return [v]
    return []

# ---------------------------------------------------------------------------
# Jinja2 templates — shared across all sub-routers
# ---------------------------------------------------------------------------

from pathlib import Path
from urllib.parse import quote_plus

import app as _pkg
from fastapi.templating import Jinja2Templates

_PACKAGE_DIR = Path(_pkg.__file__).parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

templates.env.filters["currency"] = _fmt_currency
templates.env.filters["currency_m"] = _fmt_currency_m
templates.env.filters["pct"] = _fmt_pct
templates.env.filters["multiple"] = _fmt_multiple
templates.env.filters["number_fmt"] = _fmt_number
templates.env.filters["urlencode"] = quote_plus


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
    # Don't skip the starting month — it may start mid-month but we still want the label
    while cur <= end_date:
        lp = _date_pct(cur)
        if 0 <= lp < 100:
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


# ---------------------------------------------------------------------------
# Model-builder shared helpers (used by model builder and model outputs)
# ---------------------------------------------------------------------------

from app.utils.form_helpers import _UMRow, _fd, _fi  # noqa: F401  re-exported for router imports


def _builder_gantt_from_milestones(project: "Project | None", milestones: list) -> "dict | None":
    """Build Gantt v2 data from pre-loaded milestones for the model builder timeline panel."""
    if not project or not milestones:
        return None
    bars, epoch, has_dates = _extract_milestone_bars(project, milestones=milestones)
    if not bars:
        return None
    raw_rows = [{"project_name": project.name, "bars": bars}]
    _override_stabilized_cap(raw_rows)
    g_min = min(b["display_start_day"] for b in bars)
    g_max = max(b["display_start_day"] + b["display_duration_days"] for b in bars)
    _gantt_apply_pct(bars, g_min, g_max)
    bars.sort(key=lambda b: b["display_start_day"])
    month_ticks, year_spans = _compute_gantt_axis(epoch, g_min, g_max, has_dates)
    return {
        "has_dates": has_dates,
        "epoch": epoch,
        "g_min": g_min,
        "g_max": g_max,
        "month_ticks": month_ticks,
        "year_spans": year_spans,
        "rows": _bars_to_phase_rows(bars),
    }


async def _active_project_from_request(
    request: Request, session: AsyncSession, model_id: UUID,
) -> UUID | None:
    """Extract the active project_id from HX-Current-URL's ``?project=`` query param."""
    _hx_url = request.headers.get("HX-Current-URL", "")
    if not _hx_url:
        return None
    from urllib.parse import urlparse, parse_qs
    _qs_proj = parse_qs(urlparse(_hx_url).query).get("project", [""])[0]
    if not _qs_proj:
        return None
    try:
        _candidate = UUID(_qs_proj)
    except ValueError:
        return None
    _candidate_proj = await session.get(Project, _candidate)
    if _candidate_proj and _candidate_proj.scenario_id == model_id:
        return _candidate_proj.id
    return None


# ---------------------------------------------------------------------------
# Cross-router helpers (used by both deals pipeline and model builder)
# ---------------------------------------------------------------------------

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


async def _auto_assign_opportunity_to_project(
    opportunity: Opportunity,
    project: Project,
    session: AsyncSession,
) -> None:
    """No-op - project<->parcel linking removed (parcel decommission)."""
    return None
