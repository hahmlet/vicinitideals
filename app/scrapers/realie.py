"""Realie.ai property data enrichment.

Performs exact address lookups (1 call per listing) and stores the complete
Realie property response as JSONB on the ScrapedListing row.

Hard call budget:
  - Monthly limit enforced before every API call (default 25/month).
  - Raise the call_limit in realie_usage for the backfill run, then reset to 25.
  - Listings with realie_enriched_at set are permanently skipped (data doesn't change).
  - 404 / no-match listings are also flagged (confidence=0.0) to avoid retry loops.
  - Listings with realie_skip=True are skipped entirely (bad address, user-flagged).
"""

from __future__ import annotations

import logging
import re as _re
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.realie_usage import RealieUsage
from app.models.scraped_listing import ScrapedListing

logger = logging.getLogger(__name__)

BASE_URL = "https://app.realie.ai/api/public/property/address/"
APN_LOOKUP_URL = "https://app.realie.ai/api/public/property/parcelId/"
_CURRENT_MONTH_FORMAT = "%Y-%m"

# ---------------------------------------------------------------------------
# Address issue detection
# ---------------------------------------------------------------------------

_BAD_ADDRESS_PATTERNS: list[tuple[_re.Pattern[str], str]] = [
    (_re.compile(r"^\D"),                       "no_street_number"),   # doesn't start with digit
    (_re.compile(r"^\d+\s*[-–]\s*\d+"),         "range_address"),      # 640-644, 7610-7640
    (_re.compile(r"\d+\s*[&/]\s*\d+"),          "multi_parcel_amp"),   # 10&12, 16 & 18
    (_re.compile(r"\("),                         "parenthetical"),      # 63 Sand Ridge (& 65) Ct
    (_re.compile(r"^(?:TL|T/L|V/L)\s", _re.I), "tl_prefix"),          # TL 200 NE Voyage Ave
]


def detect_address_issue(street: str | None) -> str | None:
    """Return issue code string if street looks problematic for Realie lookup, else None."""
    if not street or not street.strip():
        return "no_street"
    s = street.strip()
    for pattern, code in _BAD_ADDRESS_PATTERNS:
        if pattern.search(s):
            return code
    return None


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime(_CURRENT_MONTH_FORMAT)


class RealieQuotaExceeded(RuntimeError):
    """Raised (internally) when monthly call budget is exhausted."""


class RealieEnricher:
    """Enriches unenriched ScrapedListings with Realie.ai property data."""

    def __init__(self) -> None:
        self.api_key = settings.realie_api_key

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def enrich_batch(self, db: AsyncSession) -> dict:
        """
        Enrich all unenriched listings up to the monthly call budget.

        Returns a summary dict:
            enriched_count, not_found_count, skipped_no_address, calls_used,
            calls_remaining, locked
        """
        usage = await self._get_or_create_usage(db)

        if usage.is_locked:
            logger.warning(
                "realie_enrichment_skipped reason=quota_locked calls_used=%d limit=%d",
                usage.calls_used,
                usage.call_limit,
            )
            return self._summary(usage, enriched=0, not_found=0, skipped=0)

        # Load unenriched listings (realie_enriched_at IS NULL), ordered for determinism
        result = await db.execute(
            select(ScrapedListing)
            .where(ScrapedListing.realie_enriched_at.is_(None))
            .order_by(ScrapedListing.last_seen_at.desc())
        )
        listings = list(result.scalars().all())

        enriched = not_found = skipped_no_address = 0

        async with httpx.AsyncClient(timeout=20.0) as client:
            for listing in listings:
                if usage.is_locked:
                    logger.info(
                        "realie_quota_hit mid_batch enriched=%d remaining=%d",
                        enriched,
                        usage.calls_remaining,
                    )
                    break

                # Skip listings flagged by user or auto-detected as bad address
                if listing.realie_skip:
                    skipped_no_address += 1
                    logger.debug("realie_skip_flagged listing_id=%s", listing.id)
                    continue

                street = self._street_for_lookup(listing)
                if not street:
                    skipped_no_address += 1
                    logger.debug("realie_skip_no_address listing_id=%s", listing.id)
                    continue

                state = listing.state_code or "OR"
                unit = self._unit_for_lookup(listing)

                try:
                    property_data = await self._lookup_address(
                        client, street, state, unit=unit
                    )
                except Exception as exc:
                    logger.error(
                        "realie_lookup_error listing_id=%s street=%r error=%s",
                        listing.id, street, exc,
                    )
                    break

                # Address lookup consumed a call (200 or 404)
                usage.calls_used += 1
                usage.last_call_at = datetime.now(timezone.utc)
                if usage.calls_used >= usage.call_limit:
                    usage.locked = True

                # APN fallback if address returned 404 and we have county + APN
                if property_data is None and listing.apn and listing.county:
                    if usage.is_locked:
                        logger.info(
                            "realie_quota_hit before_apn_fallback listing_id=%s",
                            listing.id,
                        )
                        self._apply_fields(listing, None)
                        await db.flush()
                        not_found += 1
                        break

                    try:
                        property_data = await self._lookup_by_apn(
                            client, listing.apn, state, listing.county
                        )
                    except Exception as exc:
                        logger.error(
                            "realie_apn_lookup_error listing_id=%s apn=%r error=%s",
                            listing.id, listing.apn, exc,
                        )
                        break

                    # APN call also consumed a call
                    usage.calls_used += 1
                    usage.last_call_at = datetime.now(timezone.utc)
                    if usage.calls_used >= usage.call_limit:
                        usage.locked = True

                    if property_data is not None:
                        logger.info(
                            "realie_apn_fallback_hit listing_id=%s apn=%r calls=%d/%d",
                            listing.id, listing.apn,
                            usage.calls_used, usage.call_limit,
                        )
                    else:
                        logger.info(
                            "realie_apn_fallback_miss listing_id=%s apn=%r calls=%d/%d",
                            listing.id, listing.apn,
                            usage.calls_used, usage.call_limit,
                        )

                self._apply_fields(listing, property_data)
                await db.flush()

                if property_data is not None:
                    enriched += 1
                    logger.info(
                        "realie_enriched listing_id=%s street=%r calls=%d/%d",
                        listing.id, street,
                        usage.calls_used, usage.call_limit,
                    )
                else:
                    not_found += 1
                    logger.info(
                        "realie_not_found listing_id=%s street=%r calls=%d/%d",
                        listing.id, street,
                        usage.calls_used, usage.call_limit,
                    )

        await db.commit()
        return self._summary(
            usage, enriched=enriched, not_found=not_found, skipped=skipped_no_address
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_create_usage(self, db: AsyncSession) -> RealieUsage:
        month = _current_month()
        result = await db.execute(
            select(RealieUsage).where(RealieUsage.month == month)
        )
        usage = result.scalar_one_or_none()
        if usage is None:
            usage = RealieUsage(month=month, calls_used=0, call_limit=25, locked=False)
            db.add(usage)
            await db.flush()
        return usage

    async def _lookup_address(
        self,
        client: httpx.AsyncClient,
        street: str,
        state: str = "OR",
        unit: str | None = None,
    ) -> dict | None:
        """
        GET /api/public/property/address/?state=OR&address={street}
        Returns full property dict on 200, None on 404.
        Raises httpx.HTTPStatusError for other non-200 responses.
        """
        params: dict = {"state": state, "address": street}
        if unit:
            params["unitNumberStripped"] = unit
        response = await client.get(
            BASE_URL,
            params=params,
            headers={"Authorization": self.api_key},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return data.get("property", data)

    async def _lookup_by_apn(
        self,
        client: httpx.AsyncClient,
        apn_raw: str,
        state: str,
        county: str,
    ) -> dict | None:
        """
        GET /api/public/property/parcelId/?state=OR&county=Multnomah&parcelId=R207753
        Takes first APN from comma/semicolon-separated string.
        Strips " County" suffix from county name.
        Returns full property dict on 200, None on 404.
        Raises httpx.HTTPStatusError for other non-200 responses.
        """
        apn = _re.split(r"[,;]", apn_raw)[0].strip()
        county_clean = _re.sub(r"\s+County$", "", county, flags=_re.IGNORECASE).strip()
        params = {"state": state, "county": county_clean, "parcelId": apn}
        response = await client.get(
            APN_LOOKUP_URL,
            params=params,
            headers={"Authorization": self.api_key},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return data.get("property", data)

    def _apply_fields(
        self,
        listing: ScrapedListing,
        property_data: dict | None,
    ) -> None:
        """
        Write enrichment result to listing.
        On match: store full response as realie_raw_json, fill zoning if missing,
          set realie_enriched_at so this listing is never re-enriched.
        On no-match (404): do NOT set realie_enriched_at — leave retryable.
          Set confidence=0.0 to track the attempt.
        """
        now = datetime.now(timezone.utc)

        if property_data is None:
            listing.realie_match_confidence = 0.0
            return

        listing.realie_enriched_at = now
        listing.realie_match_confidence = 1.0
        listing.realie_raw_json = property_data

        if not listing.zoning and property_data.get("zoningCode"):
            listing.zoning = property_data["zoningCode"]

    def _street_for_lookup(self, listing: ScrapedListing) -> str | None:
        """
        Return street address string suitable for Realie lookup.
        Strips periods (handles S. → S, Ave. → Ave, Blvd. → Blvd).
        """
        if listing.street and listing.street.strip():
            val = listing.street.strip()
            if "," in val:
                val = val.split(",")[0].strip()
            val = val.replace(".", "")
            return val or None
        if listing.address_raw and listing.address_raw.strip():
            val = listing.address_raw.split(",")[0].strip()
            val = val.replace(".", "")
            return val or None
        return None

    def _unit_for_lookup(self, listing: ScrapedListing) -> str | None:
        """
        Return unit number stripped of prefix per Realie's code reference docs.
        e.g. "APT 4B" → "4B", "Suite 102" → "102", "103B" → "103B"
        """
        raw = listing.street2 or ""
        if not raw.strip():
            return None
        stripped = _re.sub(
            r"(?i)^(apt\.?|apartment|suite|ste\.?|unit|#|floor|fl\.?|bldg\.?|building)\s*",
            "",
            raw.strip(),
        ).strip()
        return stripped or None

    @staticmethod
    def _summary(
        usage: RealieUsage,
        *,
        enriched: int,
        not_found: int,
        skipped: int,
    ) -> dict:
        return {
            "enriched_count": enriched,
            "not_found_count": not_found,
            "skipped_no_address": skipped,
            "calls_used": usage.calls_used,
            "call_limit": usage.call_limit,
            "calls_remaining": usage.calls_remaining,
            "locked": usage.is_locked,
            "month": usage.month,
        }
