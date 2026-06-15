"""Shared helpers for ui.py sub-routers.

Pure utilities (formatting, display maps, deal entity helpers, auth/scope,
count queries, base template context) used across two or more of the
planned ui/ sub-routers. Import from here; never import from ui.py in a
sub-router — that would create a circular dependency.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.config import settings
from app.models.deal import Deal, DealModel
from app.models.ingestion import DedupCandidate, DedupStatus
from app.models.opportunity import Opportunity
from app.models.org import User
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
