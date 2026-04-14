"""Crexi multifamily scraper for Oregon apartment-building inventory."""

from __future__ import annotations

import asyncio
import re as _re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.broker import BrokerCreate
from app.schemas.scraped_listing import ScrapedListingCreate

try:  # pragma: no cover - exercised in environments with curl-cffi installed.
    from curl_cffi.requests import AsyncSession  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - lightweight local/test fallback.
    import httpx

    class AsyncSession(httpx.AsyncClient):
        def __init__(self, *args, impersonate: str | None = None, **kwargs):
            self.impersonate = impersonate
            super().__init__(*args, **kwargs)


# Oregon cities known to have Crexi multifamily listings.
# Crexi's unauthenticated API ignores pagination (skip) and caps at 50 results per query.
# Searching city-by-city keeps each slice under 50, achieving ~77% statewide coverage.
# Portland city itself still caps at 50/82 — the remaining ~32 require auth.
# Update this list when new markets appear (run _search diagnostics to find them).
_OREGON_CITIES: list[str] = [
    # Portland Metro
    "Portland", "Gresham", "Beaverton", "Hillsboro", "Lake Oswego", "Tigard",
    "Tualatin", "Sherwood", "Wilsonville", "Milwaukie", "Oregon City", "West Linn",
    "Troutdale", "Fairview", "Happy Valley", "McMinnville", "Forest Grove", "Cornelius",
    # Willamette Valley
    "Eugene", "Salem", "Corvallis", "Albany", "Springfield", "Woodburn", "Newberg",
    "Lebanon", "Sweet Home", "Dallas", "Keizer",
    # Oregon Coast
    "Astoria", "Tillamook", "Lincoln City", "Newport", "Toledo", "Waldport",
    "Florence", "North Bend", "Rockaway Beach", "Depoe Bay", "Wheeler",
    # Southern Oregon
    "Medford", "Ashland", "Grants Pass", "Klamath Falls", "Central Point",
    # Eastern / Central Oregon
    "Bend", "Redmond", "Prineville", "Madras", "The Dalles", "Pendleton", "John Day",
    # Other
    "Cottage Grove",
]

SEARCH_URL = "https://api.crexi.com/assets/search"
TOKEN_URL = "https://api.crexi.com/token"
DETAIL_URL_TEMPLATE = "https://api.crexi.com/assets/{asset_id}"
BROKERS_URL_TEMPLATE = "https://api.crexi.com/assets/{asset_id}/brokers"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.crexi.com",
    "Referer": "https://www.crexi.com/properties",
}

# Cities that require authenticated pagination to get beyond the 50-result non-auth cap.
# NOTE: Disabled — Crexi search API returns 403/timeout for authenticated requests from
# residential proxy IPs even with a valid token. Re-enable when a broker account is available.
_AUTH_CITIES: set[str] = set()


def _build_proxy_url() -> str | None:
    """Return a Proxyon residential proxy URL if credentials are configured."""
    try:
        from app.config import settings  # local import avoids circular deps in tests
        user = settings.proxyon_residential_username
        password = settings.proxyon_residential_password
        host = settings.proxyon_residential_host
        port = settings.proxyon_residential_port
    except Exception:
        return None
    if not user or not password:
        return None
    return f"http://{user}:{password}@{host}:{port}"


class CrxiScraper:
    """Fetch all Oregon apartment-building listings from Crexi."""

    def __init__(
        self,
        *,
        state: str = "OR",
        page_size: int = 50,
        batch_size: int = 10,
        batch_delay_seconds: float = 1.0,
        include_unpriced: bool = True,
        timeout_seconds: float = 30.0,
        session_factory: type[AsyncSession] | None = None,
        max_results: int | None = None,
        proxy_url: str | None = "auto",
        username: str | None = "auto",
        password: str | None = "auto",
    ) -> None:
        self.state = state
        self.page_size = page_size
        self.batch_size = batch_size
        self.batch_delay_seconds = batch_delay_seconds
        self.include_unpriced = include_unpriced
        self.timeout_seconds = timeout_seconds
        self.session_factory = session_factory or AsyncSession
        self.max_results = max_results
        # "auto" = read from settings; explicit str = use as-is; None = no proxy
        self.proxy_url = _build_proxy_url() if proxy_url == "auto" else proxy_url
        # "auto" = read from settings; explicit str = use as-is; None = no auth
        if username == "auto" or password == "auto":
            try:
                from app.config import settings
                self.username: str | None = settings.crexi_username or None
                self.password: str | None = settings.crexi_password or None
            except Exception:
                self.username = None
                self.password = None
        else:
            self.username = username
            self.password = password
        self._access_token: str | None = None  # cached for the session

    async def fetch_all(self) -> tuple[list[ScrapedListingCreate], list[BrokerCreate], int]:
        """Return (listings, brokers, source_total) where source_total is Crexi's reported count."""
        listings: list[ScrapedListingCreate] = []
        deduped_brokers: dict[str, BrokerCreate] = {}

        session_kwargs: dict = {
            "impersonate": "chrome136",
            "headers": DEFAULT_HEADERS,
            "timeout": self.timeout_seconds,
        }
        if self.proxy_url:
            session_kwargs["proxies"] = {
                "http": self.proxy_url,
                "https": self.proxy_url,
            }

        async with self.session_factory(**session_kwargs) as session:
            search_hits, source_total = await self._search(session)
            if self.max_results is not None:
                search_hits = search_hits[: self.max_results]

            for offset in range(0, len(search_hits), self.batch_size):
                batch = search_hits[offset : offset + self.batch_size]
                results = await asyncio.gather(
                    *(self._fetch_listing_bundle(session, item) for item in batch)
                )

                for detail_payload, broker_payloads in results:
                    listing = _build_listing(detail_payload, broker_payloads)
                    listings.append(listing)

                    for broker_payload in broker_payloads:
                        broker = _build_broker(broker_payload)
                        if broker is None:
                            continue
                        deduped_brokers.setdefault(_broker_key(broker_payload), broker)

                if offset + self.batch_size < len(search_hits):
                    await asyncio.sleep(self.batch_delay_seconds)

        return listings, list(deduped_brokers.values()), source_total

    async def _authenticate(self) -> str | None:
        """Obtain a Bearer token from Crexi via proxy + browser impersonation.

        Uses a fresh curl_cffi session with no conflicting session-level headers.
        Returns None if credentials not set or auth fails — caller falls back to non-auth.
        """
        if not self.username or not self.password:
            return None
        if self._access_token:
            return self._access_token
        import logging
        _log = logging.getLogger(__name__)
        _log.warning("crexi_auth_start: authenticating as %s", self.username)
        try:
            session_kwargs: dict = {
                "impersonate": "chrome136",
                "timeout": self.timeout_seconds,
            }
            if self.proxy_url:
                session_kwargs["proxies"] = {
                    "http": self.proxy_url,
                    "https": self.proxy_url,
                }
            async with self.session_factory(**session_kwargs) as auth_session:
                response = await auth_session.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "password",
                        "username": self.username,
                        "password": self.password,
                    },
                    headers={
                        "content-type": "application/x-www-form-urlencoded",
                        "client-timezone-offset": "-7",
                        "x-skip-interceptor": "true",
                        "accept": "application/json, text/plain, */*",
                        "origin": "https://www.crexi.com",
                        "referer": "https://www.crexi.com/",
                    },
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            token = response.json().get("access_token")
            if token:
                self._access_token = token
                _log.warning("crexi_auth_ok: token acquired for %s", self.username)
            return token
        except Exception as exc:
            _log.warning("crexi_auth_failed: %s — Portland will be limited to 50 results", exc)
            return None

    async def _search(self, session: AsyncSession) -> tuple[list[dict[str, Any]], int]:
        """Search by city slices to work around Crexi's 50-result unauthenticated cap.

        Non-auth cities: MultiFamily + MixedUse, city-by-city slice, skip=0.
        Auth cities (Portland): MultiFamily + MixedUse, paginate with skip until exhausted.
        Falls back to non-auth (50 results) if credentials are not set or auth fails.
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.warning("crexi_search_start: %d cities", len(_OREGON_CITIES))
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        source_total = 0

        # Attempt auth once for cities that need pagination (uses plain httpx, no proxy/impersonation)
        token = await self._authenticate()
        # Merge auth header into session defaults so curl_cffi doesn't drop Accept/Content-Type
        auth_headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}"} if token else DEFAULT_HEADERS

        search_types = ["MultiFamily"]

        for city in _OREGON_CITIES:
            use_auth = bool(token) and city in _AUTH_CITIES

            if use_auth:
                # Paginate until exhausted
                skip = 0
                city_total_set = False
                while True:
                    try:
                        response = await session.post(
                            SEARCH_URL,
                            json={
                                "types": search_types,
                                "subtypes": ["Apartment Building"],
                                "includeUnpriced": self.include_unpriced,
                                "states": [self.state],
                                "cities": [city],
                                "take": self.page_size,
                                "skip": skip,
                            },
                            headers=auth_headers,
                            timeout=self.timeout_seconds,
                        )
                    except Exception as exc:
                        logger.warning(
                            "crexi_portland_error: city=%s skip=%d error=%s — falling back to non-auth",
                            city, skip, exc,
                        )
                        use_auth = False
                        break
                    if not response.ok:
                        logger.warning(
                            "crexi_portland_skip: city=%s skip=%d status=%d — falling back to non-auth",
                            city, skip, response.status_code,
                        )
                        use_auth = False
                        break

                    payload = response.json() or {}
                    page = payload.get("data") or []
                    if not isinstance(page, list) or not page:
                        break

                    if not city_total_set:
                        city_total = int(payload.get("totalCount") or 0)
                        source_total += city_total
                        city_total_set = True
                        logger.info("crexi_portland_auth: totalCount=%d", city_total)

                    new_on_page = 0
                    for item in page:
                        if not isinstance(item, dict):
                            continue
                        item_id = str(item.get("id", ""))
                        if item_id and item_id not in seen:
                            seen.add(item_id)
                            deduped.append(item)
                            new_on_page += 1

                    logger.debug("crexi_portland_page: skip=%d fetched=%d new=%d", skip, len(page), new_on_page)

                    if len(page) < self.page_size:
                        break  # last page
                    skip += self.page_size
                    await asyncio.sleep(self.batch_delay_seconds)

            if not use_auth:
                # Non-auth city slice — single request, skip=0 (also fallback if auth path failed)
                response = await session.post(
                    SEARCH_URL,
                    json={
                        "types": search_types,
                        "subtypes": ["Apartment Building"],
                        "includeUnpriced": self.include_unpriced,
                        "states": [self.state],
                        "cities": [city],
                        "take": self.page_size,
                        "skip": 0,
                    },
                    timeout=self.timeout_seconds,
                )
                if not response.ok:
                    logger.warning("crexi_city_skip: city=%s status=%d", city, response.status_code)
                    continue

                payload = response.json() or {}
                page = payload.get("data") or []
                if not isinstance(page, list):
                    continue

                city_total = int(payload.get("totalCount") or 0)
                source_total += city_total

                for item in page:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id", ""))
                    if item_id and item_id not in seen:
                        seen.add(item_id)
                        deduped.append(item)

                await asyncio.sleep(self.batch_delay_seconds)

        return deduped, source_total

    async def _fetch_listing_bundle(
        self,
        session: AsyncSession,
        listing_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        asset_id = listing_payload.get("id")
        if asset_id in (None, ""):
            raise ValueError("Crexi search result is missing an id")

        detail_response, broker_response = await asyncio.gather(
            session.get(DETAIL_URL_TEMPLATE.format(asset_id=asset_id)),
            session.get(BROKERS_URL_TEMPLATE.format(asset_id=asset_id)),
        )
        detail_response.raise_for_status()
        broker_response.raise_for_status()

        detail_payload = detail_response.json() or {}
        broker_payloads = broker_response.json() or []
        if not isinstance(detail_payload, dict):
            raise ValueError("Crexi detail response was not a JSON object")
        if not isinstance(broker_payloads, list):
            raise ValueError("Crexi broker response was not a JSON list")

        detail_payload.setdefault("urlSlug", listing_payload.get("urlSlug"))
        detail_payload.setdefault("id", asset_id)
        return detail_payload, [item for item in broker_payloads if isinstance(item, dict)]


def _strip_html(value: Any) -> str | None:
    """Convert HTML marketing description to clean plain text."""
    if value in (None, ""):
        return None
    text = str(value)
    # Block-level elements → newline
    text = _re.sub(r"<(?:p|br|li|div|h[1-6])[^>]*>", "\n", text, flags=_re.IGNORECASE)
    # Strip all remaining tags
    text = _re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&nbsp;", " ").replace("&#8203;", "").replace("\u200b", "")
    # Collapse runs of blank lines to a single blank line
    text = _re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text or None


def _sqft_or_none(value: Any) -> Decimal | None:
    """Like _to_decimal but nulls out implausible placeholder values (< 10 sqft)."""
    d = _to_decimal(value)
    if d is None:
        return None
    return None if d < Decimal("10") else d


def _build_listing(detail_payload: dict[str, Any], broker_payloads: list[dict[str, Any]]) -> ScrapedListingCreate:
    summary = _parse_summary_details(detail_payload.get("summaryDetails"))
    location = _extract_primary_location(detail_payload)

    address = _string_or_none(location.get("address") or location.get("street") or location.get("line1"))
    street2 = _string_or_none(location.get("street2") or location.get("address2") or location.get("line2"))
    city = _string_or_none(location.get("city") or location.get("municipality"))
    county = _string_or_none(location.get("county"))
    state_raw = location.get("state") or location.get("stateCode")
    if isinstance(state_raw, dict):
        state_code = _string_or_none(state_raw.get("code") or state_raw.get("abbreviation") or state_raw.get("name"))
    else:
        state_code = _string_or_none(state_raw)
    zip_code = _string_or_none(location.get("zip") or location.get("zipCode") or location.get("postalCode"))
    address_raw = _compose_full_address(address, city, state_code, zip_code) or address

    raw_json = dict(detail_payload)
    raw_json["brokers"] = broker_payloads

    return ScrapedListingCreate(
        source="crexi",
        source_id=str(detail_payload.get("id")),
        source_url=_build_source_url(detail_payload),
        listing_name=_string_or_none(detail_payload.get("name") or detail_payload.get("title")),
        description=_strip_html(
            detail_payload.get("marketingDescription") or detail_payload.get("description")
        ),
        status=_string_or_none(detail_payload.get("status")),
        address_raw=address_raw,
        address_normalized=address_raw,
        street=address,
        street2=street2,
        city=city,
        county=county,
        state_code=state_code,
        zip_code=zip_code,
        lat=_to_decimal(location.get("lat") or location.get("latitude")),
        lng=_to_decimal(location.get("lng") or location.get("lon") or location.get("longitude")),
        property_type=_string_or_none(
            detail_payload.get("propertyType") or detail_payload.get("property_type")
            or ", ".join(_to_string_list(detail_payload.get("types")) or [])
            or None
        ),
        sub_type=_to_string_list(
            detail_payload.get("propertySubType") or detail_payload.get("sub_type")
            or detail_payload.get("subtypes") or detail_payload.get("customSubtypes")
            or summary.get("SubType")
        ),
        investment_type=_string_or_none(detail_payload.get("investmentType") or detail_payload.get("investment_type")),
        investment_sub_type=_string_or_none(
            detail_payload.get("investmentSubType") or detail_payload.get("investment_sub_type")
        ),
        asking_price=_to_decimal(
            summary.get("AskingPrice") or summary.get("Price")
            or detail_payload.get("askingPrice") or detail_payload.get("price")
        ),
        price_per_sqft=_to_decimal(summary.get("PricePerSqFt") or summary.get("PriceSqFt")),
        price_per_unit=_to_decimal(summary.get("PricePerItem") or summary.get("PricePerUnit")) or (
            _to_decimal(
                summary.get("AskingPrice") or summary.get("Price")
                or detail_payload.get("askingPrice") or detail_payload.get("price")
            ) / _to_decimal(
                summary.get("Units") or detail_payload.get("units") or detail_payload.get("numberOfUnits")
            )
            if (summary.get("Units") or detail_payload.get("units") or detail_payload.get("numberOfUnits"))
            and (summary.get("AskingPrice") or summary.get("Price") or detail_payload.get("askingPrice") or detail_payload.get("price"))
            else None
        ),
        price_per_sqft_land=_to_decimal(summary.get("PriceSqFtLand")),
        building_sqft=_sqft_or_none(summary.get("SquareFootage") or summary.get("GrossBuildingArea") or detail_payload.get("buildingSizeSqft")),
        net_rentable_sqft=_to_decimal(summary.get("NetRentableArea")),
        lot_sqft=_to_sqft(summary.get("LotSize") or detail_payload.get("lotSize") or detail_payload.get("lotSizeSqft")),
        year_built=_to_int(summary.get("YearBuilt") or detail_payload.get("yearBuilt") or detail_payload.get("built")),
        year_renovated=_to_int(summary.get("YearsRenovated") or summary.get("YearRenovated")),
        units=_to_int(summary.get("Units") or detail_payload.get("units") or detail_payload.get("numberOfUnits")),
        buildings=_to_int(summary.get("Buildings") or summary.get("NumberOfBuildings")),
        stories=_to_int(summary.get("Stories")),
        parking_spaces=_to_int(summary.get("ParkingSpots") or summary.get("ParkingSpaces")),
        pads=_to_int(summary.get("Pads")),
        number_of_keys=_to_int(summary.get("NumberOfKeys") or summary.get("Keys")),
        class_=_string_or_none(summary.get("Class")),
        zoning=_string_or_none(summary.get("PermittedZoning") or summary.get("Zoning")),
        apn=_string_or_none(summary.get("Apn") or summary.get("APN")),
        occupancy_pct=_to_decimal(summary.get("Occupancy")),
        occupancy_date=_to_datetime(summary.get("OccupancyDate")),
        tenancy=_string_or_none(summary.get("Tenancy")),
        cap_rate=_to_decimal(summary.get("CapRate") or detail_payload.get("capRate")),
        proforma_cap_rate=_to_decimal(summary.get("ProformaCapRate")),
        noi=_to_decimal(summary.get("NOI") or summary.get("NetOperatingIncome")),
        proforma_noi=_to_decimal(summary.get("ProformaNOI")),
        lease_term=_to_decimal(summary.get("LeaseTerm")),
        lease_commencement=_to_datetime(summary.get("LeaseCommencement")),
        lease_expiration=_to_datetime(summary.get("LeaseExpiration")),
        remaining_term=_to_decimal(summary.get("RemainingTerm")),
        rent_bumps=_stringify(summary.get("RentBumps")),
        sale_condition=_string_or_none(summary.get("SaleCondition")),
        broker_co_op=bool(_to_bool(summary.get("BrokerCoOp"))),
        ownership=_string_or_none(summary.get("Ownership")),
        is_in_opportunity_zone=_to_bool(summary.get("OpportunityZone") or summary.get("IsInOpportunityZone")),
        raw_json=raw_json,
    )


def _build_broker(broker_payload: dict[str, Any]) -> BrokerCreate | None:
    broker_id = _to_int(broker_payload.get("id"))
    global_id = _string_or_none(broker_payload.get("globalId"))
    first_name = _string_or_none(broker_payload.get("firstName"))
    last_name = _string_or_none(broker_payload.get("lastName"))
    if broker_id is None and global_id is None and first_name is None and last_name is None:
        return None

    return BrokerCreate(
        crexi_broker_id=broker_id,
        crexi_global_id=global_id,
        first_name=first_name,
        last_name=last_name,
        brokerage_name=_string_or_none((broker_payload.get("brokerage") or {}).get("name")),
        thumbnail_url=_string_or_none(broker_payload.get("thumbnailUrl")),
        is_platinum=bool(broker_payload.get("isPlatinum", False)),
        number_of_assets=_to_int(broker_payload.get("numberOfAssets")),
    )


def _broker_key(broker_payload: dict[str, Any]) -> str:
    if broker_payload.get("id") not in (None, ""):
        return f"crexi:{broker_payload['id']}"
    if broker_payload.get("globalId") not in (None, ""):
        return f"crexi-global:{broker_payload['globalId']}"

    pieces = [
        _string_or_none(broker_payload.get("firstName")),
        _string_or_none(broker_payload.get("lastName")),
        _string_or_none((broker_payload.get("brokerage") or {}).get("name")),
    ]
    fallback = "|".join(piece for piece in pieces if piece)
    return f"crexi-name:{fallback or 'unknown'}"


def _parse_summary_details(summary_details: Any) -> dict[str, Any]:
    if isinstance(summary_details, dict):
        return {str(key): value for key, value in summary_details.items()}

    parsed: dict[str, Any] = {}
    if not isinstance(summary_details, list):
        return parsed

    for item in summary_details:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("label") or item.get("title") or item.get("name")
        if key in (None, ""):
            continue
        raw_value = item.get("value")
        if raw_value in (None, ""):
            raw_value = item.get("formattedValue") or item.get("displayValue") or item.get("values")
        value_type = str(item.get("valueType") or "Text")
        label_lower = str(item.get("label") or "").lower()
        if "acre" in label_lower and raw_value not in (None, ""):
            try:
                parsed[str(key)] = Decimal(str(raw_value)) * Decimal("43560")
            except (InvalidOperation, ValueError):
                parsed[str(key)] = _parse_summary_value(str(key), raw_value, value_type)
        else:
            parsed[str(key)] = _parse_summary_value(str(key), raw_value, value_type)
    return parsed


def _parse_summary_value(key: str, value: Any, value_type: str) -> Any:
    kind = value_type.strip().lower()
    if kind == "money":
        return _to_decimal(value)
    if kind == "percentage":
        return _to_fractional_decimal(value)
    if kind == "integertype":
        return _to_int(value)
    if kind == "array":
        return _to_string_list(value) or []
    if kind == "date":
        return _to_datetime(value)
    if kind == "range":
        return _to_midpoint_decimal(value)

    if key.lower() == "brokercoop":
        return _to_bool(value)
    return _string_or_none(value)


def _extract_primary_location(detail_payload: dict[str, Any]) -> dict[str, Any]:
    locations = detail_payload.get("locations")
    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict):
                return item
    location = detail_payload.get("location")
    return location if isinstance(location, dict) else {}


def _build_source_url(detail_payload: dict[str, Any]) -> str:
    asset_id = detail_payload.get("id")
    slug = _string_or_none(detail_payload.get("urlSlug") or detail_payload.get("slug"))
    if slug and asset_id:
        return f"https://www.crexi.com/properties/{asset_id}/{slug}"
    if slug:
        return f"https://www.crexi.com/properties/{slug}"
    return f"https://www.crexi.com/properties/{asset_id}"


def _compose_full_address(
    address: str | None,
    city: str | None,
    state_code: str | None,
    zip_code: str | None,
) -> str | None:
    if address and city and state_code and zip_code:
        return f"{address}, {city}, {state_code} {zip_code}"
    parts = [part for part in [address, city, state_code, zip_code] if part]
    return ", ".join(parts) if parts else None


def _extract_numbers(value: Any) -> list[Decimal]:
    if value in (None, ""):
        return []
    if isinstance(value, Decimal):
        return [value]
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [Decimal(str(value))]
    if isinstance(value, dict):
        numbers: list[Decimal] = []
        for nested in value.values():
            numbers.extend(_extract_numbers(nested))
        return numbers
    if isinstance(value, list):
        numbers: list[Decimal] = []
        for nested in value:
            numbers.extend(_extract_numbers(nested))
        return numbers

    import re

    matches = re.findall(r"(?<!\d)-?\d+(?:,\d{3})*(?:\.\d+)?", str(value))
    return [Decimal(match.replace(",", "")) for match in matches]


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = str(value).strip().replace(",", "").replace("$", "")
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
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

    text = str(value).strip().lower()
    if "%" in text or decimal_value > Decimal("1"):
        return decimal_value / Decimal("100")
    return decimal_value


def _to_int(value: Any) -> int | None:
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
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or None
    if isinstance(value, str):
        pieces = [piece.strip() for piece in value.replace(";", ",").split(",") if piece.strip()]
        return pieces or None
    return [str(value).strip()]


def _to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _to_sqft(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    decimal_value = _to_midpoint_decimal(value)
    if decimal_value is None:
        return None

    text = str(value).strip().lower()
    if "ac" in text:
        decimal_value *= Decimal("43560")
    return decimal_value.quantize(Decimal("0.000001"))


def _stringify(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip()) or None
    return _string_or_none(value)


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


__all__ = ["CrxiScraper", "_broker_key", "_parse_summary_details"]
