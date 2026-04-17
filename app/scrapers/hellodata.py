"""HelloData.ai property data enrichment harness.

Calls four endpoints per property and stores both the raw JSON and
synthesized per-unit / per-sqft metrics on the ScrapedListing row.

Endpoints (all pay-per-call, default $0.50 each):
  - GET  /property/search            → resolve HelloData property ID by address
  - POST /property/market_rents       → unit-level rent predictions
  - POST /property/expense_benchmarks → ML-predicted OpEx line items + NOI
  - POST /property/comparables        → nearby comparable properties

Budget enforcement:
  - Monthly cost cap (cents) enforced before every call.
  - hellodata_skip listings are never called.
  - Listings with hellodata_enriched_at set are skipped (data doesn't
    change frequently; refresh is an explicit operation).
  - Portland listings are rejected per CLAUDE.md Market Coverage Policy.

Raw response JSON is preserved for audit.  Synthesized fields
(market rent, NOI, EGI, OpEx, occupancy — all per-unit and per-sqft
where applicable) are extracted once at enrichment time and feed the
KNN market comp pool directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.hellodata_usage import HelloDataUsage
from app.models.scraped_listing import ScrapedListing

logger = logging.getLogger(__name__)

_MONTH_FORMAT = "%Y-%m"

# ── Portland exclusion (CLAUDE.md Market Coverage Policy) ──────────────────
# Portland is a comp-only market. No paid data spend for Portland listings.
PORTLAND_JURISDICTION_VALUES = {"portland", "city of portland"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class EnrichmentResult:
    """Outcome of a single listing enrichment attempt."""

    listing_id: str
    enriched: bool
    calls_made: int
    cost_cents: int
    reason: str  # "success" | "skipped_portland" | "skipped_flagged" | "already_enriched" | "budget_locked" | "no_match" | "error"
    error: str | None = None


@dataclass
class BatchResult:
    """Summary of a batch enrichment run."""

    total_listings: int
    enriched: int
    skipped_portland: int
    skipped_flagged: int
    already_enriched: int
    no_match: int
    budget_locked_at: int  # index at which budget ran out (0 if never)
    errors: int
    total_cost_cents: int
    results: list[EnrichmentResult]


# ---------------------------------------------------------------------------
# Portland exclusion
# ---------------------------------------------------------------------------


def _is_portland(listing: ScrapedListing) -> bool:
    """Return True if listing is in Portland jurisdiction (paid calls excluded)."""
    # Prefer reconciled jurisdiction (authoritative); fall back to broker city.
    juris = (listing.jurisdiction or listing.city or "").strip().lower()
    return juris in PORTLAND_JURISDICTION_VALUES


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


async def _load_or_create_usage(session: AsyncSession) -> HelloDataUsage:
    month = datetime.now(UTC).strftime(_MONTH_FORMAT)
    usage = await session.get(HelloDataUsage, month)
    if usage is None:
        usage = HelloDataUsage(
            month=month,
            budget_cents=settings.hellodata_monthly_budget_cents,
        )
        session.add(usage)
        await session.flush()
    return usage


def _can_afford(usage: HelloDataUsage, num_calls: int) -> bool:
    """Return True if the usage row has budget for num_calls at the per-call rate."""
    projected_cost = usage.cost_cents + num_calls * settings.hellodata_cost_per_call_cents
    return not usage.locked and projected_cost <= usage.budget_cents


def _record_call(usage: HelloDataUsage) -> None:
    """Increment call count and cost after a successful (200) API call."""
    usage.calls_used += 1
    usage.cost_cents += settings.hellodata_cost_per_call_cents
    usage.last_call_at = datetime.now(UTC)
    if usage.cost_cents >= usage.budget_cents:
        usage.locked = True


# ---------------------------------------------------------------------------
# HelloData API client
# ---------------------------------------------------------------------------


class HelloDataClient:
    """Thin async wrapper around the four HelloData endpoints."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    async def search(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        lat: float | None = None,
        lon: float | None = None,
        state: str | None = None,
        zip_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /property/search — returns list of candidate properties."""
        params: dict[str, Any] = {"q": query}
        if lat is not None:
            params["lat"] = lat
        if lon is not None:
            params["lon"] = lon
        if state:
            params["state"] = state
        if zip_code:
            params["zip_code"] = zip_code

        resp = await client.get(
            f"{self._base_url}/property/search",
            params=params,
            headers=self._headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []) if isinstance(data, dict) else data

    async def market_rents(
        self, client: httpx.AsyncClient, subject: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /property/market_rents — unit-level rent predictions."""
        resp = await client.post(
            f"{self._base_url}/property/market_rents",
            json={"subject": subject},
            headers=self._headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def expense_benchmarks(
        self, client: httpx.AsyncClient, subject: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /property/expense_benchmarks — ML-predicted OpEx + NOI."""
        resp = await client.post(
            f"{self._base_url}/property/expense_benchmarks",
            json=subject,
            headers=self._headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def comparables(
        self,
        client: httpx.AsyncClient,
        *,
        simple_subject: dict[str, Any] | None = None,
        subject: dict[str, Any] | None = None,
        top_n: int = 10,
        max_distance: float = 3.0,
    ) -> dict[str, Any]:
        """POST /property/comparables — nearby comps with similarity breakdown."""
        body: dict[str, Any] = {}
        if subject:
            body["subject"] = subject
        if simple_subject:
            body["simple_subject"] = simple_subject
        params = {"topN": top_n, "maxDistance": max_distance}
        resp = await client.post(
            f"{self._base_url}/property/comparables",
            json=body,
            params=params,
            headers=self._headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Synthesis — extract per-unit / per-sqft metrics from raw responses
# ---------------------------------------------------------------------------


def _avg_predicted_rent(rents_response: dict[str, Any]) -> tuple[float | None, float | None]:
    """From /market_rents response, compute avg predicted_price and predicted_price_sqft.

    Response is typically a list of PricingResponse items, one per unit.
    """
    items = rents_response if isinstance(rents_response, list) else rents_response.get("data", [])
    if not items:
        return None, None
    prices = [i.get("predicted_price") for i in items if i.get("predicted_price") is not None]
    psf = [i.get("predicted_price_sqft") for i in items if i.get("predicted_price_sqft") is not None]
    avg_price = sum(prices) / len(prices) if prices else None
    avg_psf = sum(psf) / len(psf) if psf else None
    return avg_price, avg_psf


def _extract_distribution_predicted(
    expenses: dict[str, Any], field: str
) -> float | None:
    """Pull the `predicted` value from a Distribution object keyed under subject_estimate."""
    subj = expenses.get("subject_estimate") or {}
    dist = subj.get(field)
    if not isinstance(dist, dict):
        return None
    val = dist.get("predicted")
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _synthesize_metrics(
    rents_response: dict[str, Any] | None,
    expenses_response: dict[str, Any] | None,
    unit_count: int,
    building_sqft: float | None,
) -> dict[str, Decimal | None]:
    """Produce per-unit / per-sqft metrics for KNN comp pool consumption."""
    out: dict[str, Decimal | None] = {
        "market_rent_per_unit": None,
        "market_rent_per_sqft": None,
        "egi_per_unit": None,
        "noi_per_unit": None,
        "opex_per_unit": None,
        "occupancy_pct": None,
    }

    if rents_response and unit_count > 0:
        avg_rent, avg_rent_sqft = _avg_predicted_rent(rents_response)
        if avg_rent is not None:
            out["market_rent_per_unit"] = Decimal(str(round(avg_rent, 2)))
        if avg_rent_sqft is not None:
            out["market_rent_per_sqft"] = Decimal(str(round(avg_rent_sqft, 4)))

    if expenses_response and unit_count > 0:
        egi = _extract_distribution_predicted(expenses_response, "egi")
        noi = _extract_distribution_predicted(expenses_response, "noi")
        opex = _extract_distribution_predicted(expenses_response, "total_operating_expenses")
        gpr = _extract_distribution_predicted(expenses_response, "gross_potential_rent")
        vacancy = _extract_distribution_predicted(expenses_response, "vacancy_loss")

        if egi is not None:
            out["egi_per_unit"] = Decimal(str(round(egi / unit_count, 2)))
        if noi is not None:
            out["noi_per_unit"] = Decimal(str(round(noi / unit_count, 2)))
        if opex is not None:
            out["opex_per_unit"] = Decimal(str(round(opex / unit_count, 2)))

        # Occupancy = 1 - (vacancy_loss / gross_potential_rent)
        if gpr is not None and gpr > 0 and vacancy is not None:
            occ = max(0.0, min(1.0, 1.0 - (vacancy / gpr)))
            out["occupancy_pct"] = Decimal(str(round(occ, 4)))

    return out


# ---------------------------------------------------------------------------
# Subject property builder
# ---------------------------------------------------------------------------


def _listing_to_subject(listing: ScrapedListing) -> dict[str, Any]:
    """Build the HelloData subject payload from a ScrapedListing row."""
    return {
        "id": str(listing.id),
        "street_address": listing.street or listing.address_normalized or listing.address_raw or "",
        "city": listing.city or "",
        "state": listing.state_code or "OR",
        "zip_code": listing.zip_code or "",
        "lat": float(listing.lat) if listing.lat is not None else None,
        "lon": float(listing.lng) if listing.lng is not None else None,
        "number_units": listing.units,
        "year_built": listing.year_built,
        "number_stories": listing.stories,
        "is_apartment": True,
    }


# ---------------------------------------------------------------------------
# Single-listing enrichment
# ---------------------------------------------------------------------------


async def enrich_listing(
    session: AsyncSession,
    listing: ScrapedListing,
    client: httpx.AsyncClient,
    hd: HelloDataClient,
    usage: HelloDataUsage,
    *,
    fetch_comparables: bool = False,
) -> EnrichmentResult:
    """Enrich a single listing through the HelloData pipeline.

    Call budget:
      - /property/search: 1 call
      - /property/market_rents: 1 call
      - /property/expense_benchmarks: 1 call
      - /property/comparables: 1 call (optional, skipped by default)

    Default: 3 calls per listing (~$1.50).  With comparables: 4 calls (~$2.00).
    """
    lid = str(listing.id)

    if listing.hellodata_skip:
        return EnrichmentResult(lid, False, 0, 0, "skipped_flagged")
    if listing.hellodata_enriched_at is not None:
        return EnrichmentResult(lid, False, 0, 0, "already_enriched")
    if _is_portland(listing):
        return EnrichmentResult(lid, False, 0, 0, "skipped_portland")

    needed_calls = 4 if fetch_comparables else 3
    if not _can_afford(usage, needed_calls):
        return EnrichmentResult(lid, False, 0, 0, "budget_locked")

    calls_made = 0
    cost_before = usage.cost_cents

    try:
        # ── 1. Search for HelloData property ID ────────────────────────────
        query = listing.street or listing.address_normalized or ""
        if not query.strip():
            return EnrichmentResult(lid, False, 0, 0, "no_match", "no street/address")

        search_results = await hd.search(
            client,
            query=query,
            lat=float(listing.lat) if listing.lat is not None else None,
            lon=float(listing.lng) if listing.lng is not None else None,
            state=listing.state_code or "OR",
            zip_code=listing.zip_code,
        )
        _record_call(usage)
        calls_made += 1

        listing.hellodata_raw_search = {"data": search_results}

        if not search_results:
            # No property in HelloData's database — stub enrichment to avoid retries.
            listing.hellodata_enriched_at = datetime.now(UTC)
            return EnrichmentResult(lid, False, calls_made, usage.cost_cents - cost_before, "no_match")

        # Pick the closest match (first result is typically proximity-sorted).
        property_id = str(search_results[0].get("id", ""))
        listing.hellodata_property_id = property_id or None

        # Build subject from either HelloData response or our listing data.
        subject = {**search_results[0], **_listing_to_subject(listing)}

        # ── 2. Market rents ────────────────────────────────────────────────
        if not _can_afford(usage, needed_calls - calls_made):
            listing.hellodata_enriched_at = datetime.now(UTC)
            return EnrichmentResult(lid, True, calls_made, usage.cost_cents - cost_before, "budget_locked")

        rents = await hd.market_rents(client, subject)
        _record_call(usage)
        calls_made += 1
        listing.hellodata_raw_rents = rents if isinstance(rents, dict) else {"data": rents}

        # ── 3. Expense benchmarks ──────────────────────────────────────────
        if not _can_afford(usage, needed_calls - calls_made):
            listing.hellodata_enriched_at = datetime.now(UTC)
            return EnrichmentResult(lid, True, calls_made, usage.cost_cents - cost_before, "budget_locked")

        expenses = await hd.expense_benchmarks(client, subject)
        _record_call(usage)
        calls_made += 1
        listing.hellodata_raw_expenses = expenses

        # ── 4. Comparables (optional) ──────────────────────────────────────
        if fetch_comparables and _can_afford(usage, 1):
            comps = await hd.comparables(client, subject=subject)
            _record_call(usage)
            calls_made += 1
            listing.hellodata_raw_comparables = comps

        # ── Synthesize per-unit / per-sqft metrics ─────────────────────────
        unit_count = listing.units or 0
        sqft = float(listing.gba_sqft) if listing.gba_sqft is not None else None
        metrics = _synthesize_metrics(
            listing.hellodata_raw_rents,
            listing.hellodata_raw_expenses,
            unit_count,
            sqft,
        )
        listing.hellodata_market_rent_per_unit = metrics["market_rent_per_unit"]
        listing.hellodata_market_rent_per_sqft = metrics["market_rent_per_sqft"]
        listing.hellodata_egi_per_unit = metrics["egi_per_unit"]
        listing.hellodata_noi_per_unit = metrics["noi_per_unit"]
        listing.hellodata_opex_per_unit = metrics["opex_per_unit"]
        listing.hellodata_occupancy_pct = metrics["occupancy_pct"]

        listing.hellodata_enriched_at = datetime.now(UTC)
        return EnrichmentResult(lid, True, calls_made, usage.cost_cents - cost_before, "success")

    except httpx.HTTPStatusError as exc:
        logger.warning("HelloData enrichment HTTP error listing=%s status=%s", lid, exc.response.status_code)
        return EnrichmentResult(lid, False, calls_made, usage.cost_cents - cost_before, "error", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("HelloData enrichment failed listing=%s error=%s", lid, exc)
        return EnrichmentResult(lid, False, calls_made, usage.cost_cents - cost_before, "error", str(exc))


# ---------------------------------------------------------------------------
# Batch enrichment
# ---------------------------------------------------------------------------


async def enrich_batch(
    session: AsyncSession,
    listing_ids: list[str] | None = None,
    *,
    fetch_comparables: bool = False,
    dry_run: bool = False,
    max_calls: int | None = None,
) -> BatchResult:
    """Enrich a batch of listings.  Pass listing_ids=None to enrich all
    non-Portland, non-enriched, non-skipped listings.

    Args:
        dry_run: If True, skip API calls and budget deduction — just report
                 what would be enriched.
        max_calls: Cap total API calls for this batch (in addition to monthly budget).
    """
    if not settings.hellodata_api_key and not dry_run:
        raise RuntimeError(
            "HelloData enrichment requested but hellodata_api_key is not configured"
        )

    # ── Select target listings ────────────────────────────────────────────
    stmt = select(ScrapedListing).where(
        ScrapedListing.hellodata_enriched_at.is_(None),
        ScrapedListing.hellodata_skip.is_(False),
    )
    if listing_ids:
        stmt = stmt.where(ScrapedListing.id.in_(listing_ids))

    listings = list((await session.execute(stmt)).scalars().all())

    usage = await _load_or_create_usage(session)
    results: list[EnrichmentResult] = []
    calls_cap = max_calls if max_calls is not None else 10**9
    calls_made_total = 0
    budget_locked_at = 0

    if dry_run:
        for listing in listings:
            if listing.hellodata_skip:
                results.append(EnrichmentResult(str(listing.id), False, 0, 0, "skipped_flagged"))
            elif _is_portland(listing):
                results.append(EnrichmentResult(str(listing.id), False, 0, 0, "skipped_portland"))
            else:
                results.append(EnrichmentResult(str(listing.id), False, 0, 0, "would_enrich"))
        return _summarize(listings, results, 0)

    hd = HelloDataClient(settings.hellodata_api_key, settings.hellodata_base_url)
    async with httpx.AsyncClient() as client:
        for idx, listing in enumerate(listings):
            if calls_made_total >= calls_cap:
                break
            result = await enrich_listing(
                session, listing, client, hd, usage,
                fetch_comparables=fetch_comparables,
            )
            results.append(result)
            calls_made_total += result.calls_made
            if result.reason == "budget_locked" and budget_locked_at == 0:
                budget_locked_at = idx
                break

    await session.flush()
    return _summarize(listings, results, budget_locked_at)


def _summarize(
    listings: list[ScrapedListing],
    results: list[EnrichmentResult],
    budget_locked_at: int,
) -> BatchResult:
    counts = {
        "enriched": sum(1 for r in results if r.reason == "success"),
        "skipped_portland": sum(1 for r in results if r.reason == "skipped_portland"),
        "skipped_flagged": sum(1 for r in results if r.reason == "skipped_flagged"),
        "already_enriched": sum(1 for r in results if r.reason == "already_enriched"),
        "no_match": sum(1 for r in results if r.reason == "no_match"),
        "errors": sum(1 for r in results if r.reason == "error"),
    }
    total_cost = sum(r.cost_cents for r in results)
    return BatchResult(
        total_listings=len(listings),
        enriched=counts["enriched"],
        skipped_portland=counts["skipped_portland"],
        skipped_flagged=counts["skipped_flagged"],
        already_enriched=counts["already_enriched"],
        no_match=counts["no_match"],
        budget_locked_at=budget_locked_at,
        errors=counts["errors"],
        total_cost_cents=total_cost,
        results=results,
    )
