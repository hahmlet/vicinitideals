"""LoopNet RapidAPI scraper — polygon-clipped bbox search + detail fetches.

Endpoints used (all POST to https://loopnet-api.p.rapidapi.com):
  /loopnet/sale/searchByBoundingBox   — body {"boundingBox":[minLng,minLat,maxLng,maxLat],"page":N}
                                         Returns [{"listingId": "<str>", "coordinations": [[lng,lat]]}]
  /loopnet/property/SaleDetails       — body {"listingId": "<string>"}
  /loopnet/property/ExtendedDetails   — body {"listingId": "<string>"}

Key gotchas discovered during probing:
  - listingId must be a STRING (integer form silently returns "No listing found").
  - Search responses omit property_type; MF filter is client-side.
  - SaleDetails uses propertyType="Multifamily" (one word); ExtendedDetails uses "Multi-Family".
    Match via case-insensitive startswith("multi").
  - LoopNet's location.city labels Gresham/Troutdale as "Portland" frequently.
    Always assign jurisdiction via lat/lng → parcel join (see app/reconciliation/matcher.py),
    never trust source-reported city.

Budget is enforced by BudgetGuard, which counts api_call_log rows for the
current billing_month and refuses to dispatch a call once the month's count
reaches (settings.loopnet_monthly_budget - safety_margin). On the final day
of the month the safety margin is released.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.api_call_log import ApiCallLog

# LoopNet RapidAPI rate limit: 1 request per second (provider-enforced).
# BudgetGuard sleeps to maintain this spacing between calls on the same guard.
MIN_CALL_INTERVAL_SECONDS: float = 1.0

logger = logging.getLogger(__name__)

SEARCH_URL_PATH = "/loopnet/sale/searchByBoundingBox"
SALE_DETAILS_PATH = "/loopnet/property/SaleDetails"
EXTENDED_DETAILS_PATH = "/loopnet/property/ExtendedDetails"
BULK_DETAILS_PATH = "/loopnet/property/bulkDetails"
LEASE_SEARCH_URL_PATH = "/loopnet/lease/searchByBoundingBox"
LEASE_DETAILS_PATH = "/loopnet/property/LeaseDetails"

# bulkDetails accepts at most 20 listingIds per call (provider-enforced).
BULK_MAX_BATCH = 20

# Subtype strings from bulkDetails shortPropertyFacts[1][0] that indicate MF.
_BULK_MF_SUBTYPES = {
    "apartments",
    "multi-family",
    "multifamily",
    "manufactured housing",
    "senior living",
    "student housing",
    "co-living",
}

# Page size observed in production: 30 listings per page is the common response
# but one probe returned 296 in a single page. Treat "< page_hint" as last page.
BBOX_PAGE_HINT = 30


# ---------------------------------------------------------------------------
# Polygon loading + point-in-polygon
# ---------------------------------------------------------------------------

def load_polygons(path: str | None = None) -> list[dict[str, Any]]:
    """Read the polygons JSON file. Returns only polygons with is_active=true."""
    p = Path(path or settings.loopnet_polygon_path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return [poly for poly in data if poly.get("is_active")]


def polygon_bbox(points: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    """Return (minLng, minLat, maxLng, maxLat) — LoopNet's boundingBox ordering."""
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]
    return (min(lngs), min(lats), max(lngs), max(lats))


def point_in_polygon(points: Sequence[Sequence[float]], lng: float, lat: float) -> bool:
    """Ray-casting point-in-polygon test. Points are [lng, lat] pairs.

    The polygon is treated as closed (first/last point equality is fine).
    """
    n = len(points)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = points[i][0], points[i][1]
        xj, yj = points[j][0], points[j][1]
        if (yi > lat) != (yj > lat):
            # Add 1e-12 to avoid div-by-zero on horizontal edges.
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
            if lng < x_intersect:
                inside = not inside
        j = i
    return inside


def clip_to_polygon(
    rows: Iterable[dict[str, Any]],
    polygon_points: Sequence[Sequence[float]],
) -> list[dict[str, Any]]:
    """Filter search-response rows whose coordinations fall inside polygon."""
    survivors = []
    for row in rows:
        coords = row.get("coordinations") or []
        if not coords:
            continue
        if any(point_in_polygon(polygon_points, c[0], c[1]) for c in coords):
            survivors.append(row)
    return survivors


# ---------------------------------------------------------------------------
# Budget guard
# ---------------------------------------------------------------------------

def _billing_month_of(d: date) -> date:
    return date(d.year, d.month, 1)


def _is_last_day_of_month(d: date) -> bool:
    # next day is either day 1 of next month or still same month
    next_d = date(d.year + (1 if d.month == 12 else 0),
                  1 if d.month == 12 else d.month + 1,
                  1)
    return (next_d - d).days == 1


class BudgetExhausted(RuntimeError):
    """Raised when BudgetGuard refuses to dispatch a call."""


class BudgetGuard:
    """Async context-managed LoopNet call dispatcher with monthly budget enforcement.

    Usage:
        async with BudgetGuard(session) as guard:
            data = await guard.call(SALE_DETAILS_PATH, {"listingId": "38985870"})

    Every call() logs an api_call_log row (even on HTTP errors — they still count
    against the RapidAPI quota). When the month's count reaches the cap minus
    safety margin, subsequent call()s raise BudgetExhausted.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        monthly_budget: int | None = None,
        safety_margin: int | None = None,
        today: date | None = None,
        min_call_interval: float = MIN_CALL_INTERVAL_SECONDS,
    ) -> None:
        self.session = session
        self.monthly_budget = (
            monthly_budget if monthly_budget is not None else settings.loopnet_monthly_budget
        )
        self.safety_margin = (
            safety_margin
            if safety_margin is not None
            else settings.loopnet_budget_safety_margin
        )
        self.today = today or datetime.now(UTC).date()
        self.min_call_interval = min_call_interval
        self._client: httpx.AsyncClient | None = None
        self._calls_used: int | None = None
        self._last_call_monotonic: float | None = None
        # Inter-call lock so concurrent awaiters can't jump the 1s window.
        self._call_lock = asyncio.Lock()

    @property
    def effective_cap(self) -> int:
        """Budget minus safety margin (margin is released on the final day)."""
        if _is_last_day_of_month(self.today):
            return self.monthly_budget
        return max(0, self.monthly_budget - self.safety_margin)

    async def _load_calls_used(self) -> int:
        stmt = select(func.count(ApiCallLog.id)).where(
            ApiCallLog.source == "loopnet",
            ApiCallLog.billing_month == _billing_month_of(self.today),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def __aenter__(self) -> "BudgetGuard":
        self._client = httpx.AsyncClient(
            base_url=f"https://{settings.loopnet_rapidapi_host}",
            headers={
                "x-rapidapi-host": settings.loopnet_rapidapi_host,
                "x-rapidapi-key": settings.rapidapi_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._calls_used = await self._load_calls_used()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        listing_source_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a POST to path, log the call, return parsed JSON body.

        Raises BudgetExhausted if the budget is spent.
        Raises httpx.HTTPStatusError on non-2xx responses (after logging the call).
        """
        if self._client is None:
            raise RuntimeError("BudgetGuard must be used as an async context manager")

        assert self._calls_used is not None
        if self._calls_used >= self.effective_cap:
            raise BudgetExhausted(
                f"LoopNet budget exhausted: {self._calls_used}/{self.effective_cap} "
                f"calls used this month (cap={self.monthly_budget}, "
                f"margin={self.safety_margin}, today={self.today.isoformat()})"
            )

        endpoint_name = path.rsplit("/", 1)[-1]
        status_code: int | None = None
        async with self._call_lock:
            # Enforce the 1-req/sec provider rate limit by sleeping off the
            # remainder of the window since the previous dispatched call.
            if self._last_call_monotonic is not None:
                elapsed = time.monotonic() - self._last_call_monotonic
                wait = self.min_call_interval - elapsed
                if wait > 0:
                    await asyncio.sleep(wait)
            try:
                response = await self._client.post(path, json=payload)
                status_code = response.status_code
                response.raise_for_status()
                return response.json()
            finally:
                self._last_call_monotonic = time.monotonic()
                self._calls_used += 1
                self.session.add(ApiCallLog(
                    source="loopnet",
                    endpoint=endpoint_name,
                    listing_source_id=listing_source_id,
                    status_code=status_code,
                    billing_month=_billing_month_of(self.today),
                ))
                await self.session.flush()

    @property
    def calls_used(self) -> int:
        return self._calls_used or 0

    @property
    def remaining(self) -> int:
        return max(0, self.effective_cap - self.calls_used)


# ---------------------------------------------------------------------------
# Search + detail fetches
# ---------------------------------------------------------------------------

async def bbox_search(
    guard: BudgetGuard,
    bbox: tuple[float, float, float, float],
    *,
    max_pages: int = 40,
) -> list[dict[str, Any]]:
    """Page through bbox search and return all rows.

    Returns rows shaped {"listingId": str, "coordinations": [[lng,lat], ...]}.
    Stops when a page returns zero rows OR fewer than BBOX_PAGE_HINT rows.
    """
    all_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for page in range(1, max_pages + 1):
        body = await guard.call(SEARCH_URL_PATH, {"boundingBox": list(bbox), "page": page})
        rows = body.get("data") or []
        if not rows:
            break
        for row in rows:
            lid = str(row.get("listingId") or "")
            if lid and lid not in seen_ids:
                seen_ids.add(lid)
                all_rows.append(row)
        if len(rows) < BBOX_PAGE_HINT:
            break
    return all_rows


async def fetch_sale_details(
    guard: BudgetGuard, listing_id: str
) -> dict[str, Any] | None:
    """POST /loopnet/property/SaleDetails. Returns the first data[] element or None."""
    body = await guard.call(
        SALE_DETAILS_PATH, {"listingId": str(listing_id)}, listing_source_id=listing_id
    )
    data = body.get("data") or []
    return data[0] if data else None


async def fetch_extended_details(
    guard: BudgetGuard, listing_id: str
) -> dict[str, Any] | None:
    """POST /loopnet/property/ExtendedDetails. Returns the first data[] element or None."""
    body = await guard.call(
        EXTENDED_DETAILS_PATH, {"listingId": str(listing_id)}, listing_source_id=listing_id
    )
    data = body.get("data") or []
    return data[0] if data else None


async def fetch_bulk_details(
    guard: BudgetGuard, listing_ids: Sequence[str]
) -> list[dict[str, Any]]:
    """POST /loopnet/property/bulkDetails in batches of BULK_MAX_BATCH.

    Each call returns lean listing-index data (title, listingType, subtype,
    price, broker, photo — NO propertyFacts/zoning/apn/capRate/yearBuilt).
    Meant for cheap triage before spending SaleDetails + ExtendedDetails calls.

    Counts as one API call per batch (caller should batch as tight as possible).
    """
    all_rows: list[dict[str, Any]] = []
    ids = [str(x) for x in listing_ids if x]
    for i in range(0, len(ids), BULK_MAX_BATCH):
        chunk = ids[i : i + BULK_MAX_BATCH]
        body = await guard.call(BULK_DETAILS_PATH, {"listingIds": chunk})
        data = body.get("data") or []
        all_rows.extend(data)
    return all_rows


def classify_lease_from_bulk(bulk_row: dict[str, Any]) -> set[str]:
    """Lease-side variant of classify_from_bulk.

    Lease listingTypes look like 'PropertyDirectSpaceForLease',
    'ShoppingCenterDirectSpaceForLease', 'BuildingParkDirectSpaceLease' — the
    listingType is not useful for category. All signal comes from the subtype.
    Returns tag set for MF + mixed-use detection (zoning is unavailable here,
    so subtype is the only mixed_use signal for lease bulk).

    Tags: multifamily, mixed_use, retail, office, industrial, healthcare,
          hospitality, flex, other.
    """
    tags: set[str] = set()
    spf = bulk_row.get("shortPropertyFacts") or []
    structured = spf[1] if len(spf) > 1 else []
    subtype_raw = ""
    if structured and isinstance(structured[0], list) and structured[0]:
        subtype_raw = str(structured[0][0]).strip().lower()

    if "apartment" in subtype_raw or "multi-family" in subtype_raw or subtype_raw == "multifamily":
        tags.add("multifamily")
    if "residential" in subtype_raw or "mixed" in subtype_raw:
        tags.add("mixed_use")
    if "office" in subtype_raw:
        tags.add("office")
    if "retail" in subtype_raw or "storefront" in subtype_raw or "shopping center" in subtype_raw or "strip center" in subtype_raw or "restaurant" in subtype_raw:
        tags.add("retail")
    if "warehouse" in subtype_raw or "manufactur" in subtype_raw or "industrial" in subtype_raw:
        tags.add("industrial")
    if "flex" in subtype_raw:
        tags.add("flex")
    if "medical" in subtype_raw or "hospital" in subtype_raw:
        tags.add("healthcare")
    if "hotel" in subtype_raw or "motel" in subtype_raw or "hospitality" in subtype_raw:
        tags.add("hospitality")
    if not tags:
        tags.add("other")
    return tags


def should_ingest_lease_after_bulk(categories: set[str]) -> bool:
    """Lease seed filter: only ingest LeaseDetails for MF or mixed-use listings.

    Commercial lease data (pure retail, office, industrial) is low-value for
    our MF income underwriting. Mixed-use is included because ground-floor
    retail rents in MF buildings inform mixed-use property valuations.
    """
    return bool(categories & {"multifamily", "mixed_use"})


def classify_from_bulk(bulk_row: dict[str, Any]) -> set[str]:
    """Derive category tags from a bulkDetails row (no propertyFacts available).

    Looks at listingType + shortPropertyFacts[1][0] (the subtype label) to produce
    the same canonical tag set as classify_categories(). Cannot detect mixed_use
    via zoning — that requires SaleDetails. Callers that need zoning-based
    mixed_use should fetch SaleDetails for listings this returns as "other" in
    target polygons.
    """
    tags: set[str] = set()
    lt = str(bulk_row.get("listingType") or "").strip()
    if lt == "LandForSale":
        tags.add("land")

    # shortPropertyFacts has 2 blocks: [display-text-array, structured-kv-array]
    # The first inner array of the structured block holds the subtype label.
    spf = bulk_row.get("shortPropertyFacts") or []
    structured = spf[1] if len(spf) > 1 else []
    subtype_raw = ""
    if structured and isinstance(structured[0], list) and structured[0]:
        subtype_raw = str(structured[0][0]).strip().lower()

    if subtype_raw in _BULK_MF_SUBTYPES:
        tags.add("multifamily")
    elif lt == "PropertyForSale":
        # Derive primary category from subtype string
        if "office" in subtype_raw:
            tags.add("office")
        elif "retail" in subtype_raw or "storefront" in subtype_raw or "restaurant" in subtype_raw:
            tags.add("retail")
        elif "warehouse" in subtype_raw or "manufactur" in subtype_raw or "industrial" in subtype_raw:
            tags.add("industrial")
        elif "flex" in subtype_raw:
            tags.add("flex")
        elif "hospital" in subtype_raw or "medical" in subtype_raw:
            tags.add("healthcare")
        elif "hotel" in subtype_raw or "motel" in subtype_raw or "hospitality" in subtype_raw:
            tags.add("hospitality")
        elif subtype_raw:
            tags.add("other")

    if not tags:
        tags.add("other")
    return tags


def should_fetch_sale_details_after_bulk(
    categories_from_bulk: set[str],
    polygon_purposes: set[str],
    target_ed_categories: set[str],
) -> bool:
    """Decide whether to spend a SaleDetails call after bulk triage.

    Always fetch SD when ED would be fetched (SD is a prerequisite for map_to_scraped_listing).
    Additionally fetch SD for target-polygon "other" listings so we can check
    zoning for mixed-use signal (which bulk cannot see).
    """
    if should_fetch_extended_details(
        categories_from_bulk, polygon_purposes, target_ed_categories
    ):
        return True
    # Target polygon + uncategorized → still pull SD to check zoning for MU
    if "target" in polygon_purposes and "mixed_use" in target_ed_categories:
        if "other" in categories_from_bulk and not categories_from_bulk - {"other"}:
            return True
        # Retail/Office within target polygon might be MU via zoning
        if categories_from_bulk & {"retail", "office"}:
            return True
    return False


async def lease_bbox_search(
    guard: BudgetGuard,
    bbox: tuple[float, float, float, float],
    *,
    max_pages: int = 40,
) -> list[dict[str, Any]]:
    """Page through LEASE bbox search; same shape as sale bbox search."""
    all_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for page in range(1, max_pages + 1):
        body = await guard.call(
            LEASE_SEARCH_URL_PATH, {"boundingBox": list(bbox), "page": page}
        )
        rows = body.get("data") or []
        if not rows:
            break
        for row in rows:
            lid = str(row.get("listingId") or "")
            if lid and lid not in seen_ids:
                seen_ids.add(lid)
                all_rows.append(row)
        if len(rows) < BBOX_PAGE_HINT:
            break
    return all_rows


async def fetch_lease_details(
    guard: BudgetGuard, listing_id: str
) -> dict[str, Any] | None:
    """POST /loopnet/property/LeaseDetails. Returns the first data[] element or None."""
    body = await guard.call(
        LEASE_DETAILS_PATH, {"listingId": str(listing_id)}, listing_source_id=listing_id
    )
    data = body.get("data") or []
    return data[0] if data else None


def map_lease_to_scraped_listing(
    lease_details: dict[str, Any],
    *,
    listing_id: str,
    lat: float | None,
    lng: float | None,
) -> dict[str, Any]:
    """Map LeaseDetails → ScrapedListingCreate-compatible dict.

    Lease listings have a `spaces[]` array with per-space rent (sfPerYear). We
    store the full LeaseDetails in raw_json and surface a representative
    price_per_sqft (first space's sfPerYear) for quick comp queries.
    """
    loc = lease_details.get("location") or {}
    spaces = lease_details.get("spaces") or []
    first_space = spaces[0] if spaces else {}
    first_sf_per_year = first_space.get("sfPerYear") if isinstance(first_space, dict) else None

    listing_url = (
        f"https://www.loopnet.com/Listing/{listing_id}/"
        if listing_id
        else "https://www.loopnet.com/"
    )

    return {
        "source": "loopnet_lease",
        "source_id": str(listing_id),
        "source_url": listing_url,
        "listing_url": listing_url,
        "raw_json": {"lease_details": lease_details},
        "address_raw": loc.get("streetAddress") or lease_details.get("title"),
        "street": loc.get("streetAddress"),
        "city": loc.get("addressLocality") or loc.get("city"),
        "state_code": loc.get("addressRegion") or loc.get("state"),
        "zip_code": loc.get("zipCode"),
        "lat": Decimal(str(lat)) if lat is not None else None,
        "lng": Decimal(str(lng)) if lng is not None else None,
        "property_type": lease_details.get("category"),
        "investment_type": "Lease",
        "listing_name": lease_details.get("title"),
        "description": lease_details.get("description")
            or lease_details.get("overview")
            or lease_details.get("summary"),
        "price_per_sqft": _parse_decimal(first_sf_per_year),
        "status": lease_details.get("status"),
    }


# ---------------------------------------------------------------------------
# Category classification
# ---------------------------------------------------------------------------

import re

# Raw property-type values → our canonical category tag
_PRIMARY_CATEGORY_MAP = {
    "multifamily": "multifamily",
    "multi-family": "multifamily",
    "land": "land",
    "retail": "retail",
    "office": "office",
    "industrial": "industrial",
    "flex": "flex",
    "hospitality": "hospitality",
    "health care": "healthcare",
    "healthcare": "healthcare",
    "specialty": "specialty",
}

# Zoning strings containing any of these → mixed_use tag. Per user direction,
# subtype-based mixed-use detection is intentionally excluded — subtypes like
# "Storefront Retail/Residential" are noisy and misclassify many single-use
# retail buildings with a 2nd-floor apartment as mixed-use. Zoning is the
# authoritative legal signal.
_MIXED_USE_ZONING_RE = re.compile(
    r"(?:mixed[-\s]?use|\bmu[-/]|\bmu\d|-mu[-/]?)", re.IGNORECASE,
)


def classify_multifamily(sale_details: dict[str, Any]) -> bool:
    """True if this is a Multifamily/Multi-Family listing. Case-insensitive prefix match.

    Kept for backwards compatibility with existing call sites; prefer
    classify_categories() for multi-category decisions.
    """
    return "multifamily" in classify_categories(sale_details)


def classify_categories(sale_details: dict[str, Any]) -> set[str]:
    """Derive category tags from SaleDetails. Returns a set; a listing can be
    multiple categories (e.g. a Retail/Residential building returns
    {"retail", "mixed_use"}).

    Tags: multifamily, land, retail, office, industrial, flex, hospitality,
          healthcare, specialty, mixed_use, other.
    """
    tags: set[str] = set()
    pf = sale_details.get("propertyFacts") or {}
    pt_raw = str(pf.get("propertyType") or sale_details.get("category") or "").strip().lower()

    # Primary category
    primary = _PRIMARY_CATEGORY_MAP.get(pt_raw)
    if primary:
        tags.add(primary)
    elif pt_raw.startswith("multi"):
        tags.add("multifamily")
    elif pt_raw:
        tags.add("other")

    # Mixed-use signals (zoning-only, per user direction — subtype excluded)
    zoning = str(pf.get("zoning") or "")
    if zoning and _MIXED_USE_ZONING_RE.search(zoning):
        tags.add("mixed_use")
    # Rare but explicit: propertyType = "Mixed-Use"
    if "mixed" in pt_raw and "use" in pt_raw:
        tags.add("mixed_use")

    if not tags:
        tags.add("other")
    return tags


def polygon_tags_for_point(
    polygons: list[dict[str, Any]], lng: float | None, lat: float | None
) -> list[str]:
    """Return names of all polygons whose shape contains (lng, lat).

    Useful for tagging a scraped listing at ingest time with every polygon
    classification that applies.
    """
    if lng is None or lat is None:
        return []
    matches: list[str] = []
    for poly in polygons:
        if not poly.get("is_active"):
            continue
        if point_in_polygon(poly["points"], float(lng), float(lat)):
            matches.append(poly["name"])
    return matches


def should_fetch_extended_details(
    categories: set[str],
    polygon_purposes: set[str],
    target_ed_categories: set[str],
) -> bool:
    """Policy: fetch ED when (target polygon AND category in allowlist)
                              OR (comp-only polygon AND category is multifamily).

    A listing in BOTH tiers gets ED if either rule fires.
    """
    if "target" in polygon_purposes and categories & target_ed_categories:
        return True
    if "comp_only" in polygon_purposes and "multifamily" in categories:
        return True
    return False


def parse_target_ed_categories(raw: str) -> set[str]:
    """Parse 'multifamily,land,mixed_use' → {'multifamily','land','mixed_use'}."""
    return {c.strip().lower() for c in (raw or "").split(",") if c.strip()}


# ---------------------------------------------------------------------------
# Field mapping: LoopNet → ScrapedListing column dict
# ---------------------------------------------------------------------------

_NUMERIC_CLEAN = str.maketrans({"$": "", ",": "", " ": ""})


def _parse_decimal(raw: Any) -> Decimal | None:
    """Parse '$1,240,000' / '7%' / '3,020 SF' / '0.12 AC' → Decimal, or None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float, Decimal)):
        try:
            return Decimal(str(raw))
        except InvalidOperation:
            return None
    s = str(raw).translate(_NUMERIC_CLEAN).strip()
    # Strip known trailing units
    for suffix in ("%", "SF", "AC", "sf", "ac"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_int(raw: Any) -> int | None:
    d = _parse_decimal(raw)
    if d is None:
        return None
    try:
        return int(d)
    except (ValueError, InvalidOperation):
        return None


def _parse_year_pair(raw: Any) -> tuple[int | None, int | None]:
    """'1956/2014' → (1956, 2014). '1956' → (1956, None). Bad/empty → (None, None)."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    parts = [p.strip() for p in s.split("/") if p.strip()]
    years: list[int] = []
    for part in parts:
        try:
            y = int(part)
            if 1700 <= y <= 2200:
                years.append(y)
        except ValueError:
            continue
    built = years[0] if years else None
    renov = years[1] if len(years) >= 2 else None
    return built, renov


_ACRES_TO_SQFT = Decimal("43560")


def _parse_lot_size(raw: Any) -> Decimal | None:
    """'0.12 AC' / '2.17 AC' → Decimal sqft. '5,000 SF' → Decimal sqft. None otherwise."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    upper = s.upper()
    value = _parse_decimal(s)
    if value is None:
        return None
    if "AC" in upper and "SF" not in upper:
        return value * _ACRES_TO_SQFT
    return value  # assume already SF


def _parse_last_updated(raw: Any) -> datetime | None:
    """Parse LoopNet's 'M/D/YYYY' lastUpdated or ISO-8601 createdAt → UTC datetime."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Try ISO-8601 first
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        pass
    # Fall through to M/D/YYYY
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def map_to_scraped_listing(
    sale_details: dict[str, Any],
    extended_details: dict[str, Any] | None,
    *,
    listing_id: str,
    lat: float | None,
    lng: float | None,
) -> dict[str, Any]:
    """Build a ScrapedListingCreate-compatible dict from LoopNet response bodies.

    Does NOT perform parcel-linking or jurisdiction assignment — leave those to
    the existing reconciliation cascade that runs during upsert.
    """
    pf = sale_details.get("propertyFacts") or {}
    loc = sale_details.get("location") or {}
    ext = extended_details or {}
    sale_summary = ext.get("saleSummary") or {}

    year_built, year_renovated = _parse_year_pair(pf.get("yearBuiltRenovated"))
    # ExtendedDetails exposes a numeric yearBuilt on saleSummary — fall back to it
    # when SaleDetails' combined string field was absent (observed empirically
    # on ~60% of live samples).
    if year_built is None and sale_summary.get("yearBuilt") is not None:
        try:
            year_built = int(sale_summary["yearBuilt"])
        except (TypeError, ValueError):
            year_built = None
    if year_renovated is None and sale_summary.get("yearRenovated") is not None:
        try:
            year_renovated = int(sale_summary["yearRenovated"])
        except (TypeError, ValueError):
            year_renovated = None

    # ExtendedDetails may carry a standalone lastUpdated in "M/D/YYYY".
    source_updated = _parse_last_updated(sale_summary.get("lastUpdated"))
    listed_at = _parse_last_updated(sale_summary.get("createdAt"))

    subtype_raw = pf.get("propertySubtype") or sale_summary.get("propGroupSubType")
    sub_type_list: list[str] | None
    if subtype_raw:
        sub_type_list = [str(subtype_raw)]
    elif sale_summary.get("propertySubtypes"):
        sub_type_list = [str(s) for s in sale_summary["propertySubtypes"] if s]
    else:
        sub_type_list = None

    listing_url = (
        f"https://www.loopnet.com/Listing/{listing_id}/"
        if listing_id
        else "https://www.loopnet.com/"
    )

    return {
        # Identity
        "source": "loopnet",
        "source_id": str(listing_id),
        "source_url": listing_url,
        "listing_url": listing_url,
        "raw_json": {"sale_details": sale_details, "extended_details": extended_details},

        # Location (note: city/state from source are unreliable — kept for
        # reference but parcel-linking is authoritative for jurisdiction)
        "address_raw": loc.get("streetAddress") or sale_details.get("title"),
        "street": loc.get("streetAddress"),
        "city": loc.get("addressLocality") or loc.get("city"),
        "state_code": loc.get("addressRegion") or loc.get("state"),
        "zip_code": loc.get("zipCode"),
        "lat": Decimal(str(lat)) if lat is not None else None,
        "lng": Decimal(str(lng)) if lng is not None else None,

        # Property facts
        "property_type": pf.get("propertyType") or sale_summary.get("propertyType"),
        "sub_type": sub_type_list,
        "investment_type": pf.get("saleType"),
        "asking_price": _parse_decimal(pf.get("price")),
        "price_per_sqft": _parse_decimal(pf.get("pricePer")),
        "gba_sqft": _parse_decimal(pf.get("buildingSize") or sale_summary.get("buildingSize")),
        "lot_sqft": _parse_lot_size(
            pf.get("landArea") or sale_summary.get("lotSize")
        ),
        "year_built": year_built,
        "year_renovated": year_renovated,
        "stories": _parse_int(pf.get("buildingHeight") or sale_summary.get("numberOfStories")),
        "parking_spaces": _parse_int(pf.get("parking") or sale_summary.get("parkingSpaceCount")),
        "class_": pf.get("buildingClass") or sale_summary.get("buildingClass"),
        "zoning": pf.get("zoning") or sale_summary.get("zoningDescription"),
        "apn": sale_summary.get("apn"),
        "occupancy_pct": _parse_decimal(pf.get("occupancyPercentage") or pf.get("percentLeased")),
        "tenancy": pf.get("tenancy") or sale_summary.get("tenancy"),
        "cap_rate": _parse_decimal(pf.get("capRate") or sale_summary.get("capRate")),
        "noi": _parse_decimal(pf.get("nOI") or sale_summary.get("yearOneNOI")),
        "is_in_opportunity_zone": bool(sale_summary.get("opportunityZone"))
        if sale_summary.get("opportunityZone") is not None
        else None,

        # Listing metadata
        "listing_name": sale_details.get("title") or pf.get("title"),
        "description": sale_details.get("description") or sale_details.get("summary"),
        "status": sale_details.get("status"),
        "listed_at": listed_at,
        "updated_at_source": source_updated,
    }
