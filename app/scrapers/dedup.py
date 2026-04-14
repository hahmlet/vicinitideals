"""Batch de-duplication helpers for scraped listings."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session

from app.models.ingestion import DedupCandidate, DedupStatus, RecordType
from app.models.project import ScrapedListing

_ADDRESS_STOP_WORDS = {
    # Directional prefixes/suffixes
    "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    # Street type suffixes
    "ST", "STREET", "RD", "ROAD", "AVE", "AVENUE", "BLVD", "BOULEVARD",
    "DR", "DRIVE", "LN", "LANE", "CT", "COURT", "PL", "PLACE",
    "HWY", "HIGHWAY", "FWY", "FREEWAY", "PKWY", "PARKWAY",
    "CIR", "CIRCLE", "TER", "TERRACE", "WAY",
    # US state abbreviations — prevent city/state/zip from inflating fuzzy score
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).upper()


def _address_tokens(value: str | None) -> set[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return set()
    return {
        token
        for token in re.findall(r"[A-Z0-9]+", normalized)
        if token not in _ADDRESS_STOP_WORDS
    }


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _extract_parcel_id(listing: ScrapedListing) -> str | None:
    raw_json = listing.raw_json or {}
    for key in ("parcel_id", "parcel_number", "parcel", "apn", "parcel_numbers"):
        value = raw_json.get(key)
        if isinstance(value, list) and value:
            value = value[0]
        if value not in (None, ""):
            return str(value).strip().upper()
    return None


def _score_pair(a: ScrapedListing, b: ScrapedListing) -> tuple[float, dict[str, Any]]:
    signals: dict[str, Any] = {
        "address_exact": False,
        "address_fuzzy": 0.0,
        "unit_count_match": False,
        "parcel_id_match": False,
        "price_overlap_within_5pct": False,
    }
    score = 0.0

    # Use street-only field when available so city/state/zip don't inflate the score.
    # Falls back to full normalized address, but city/state/zip tokens are in stop words.
    street_a = _normalize_text(a.street or a.address_normalized or a.address_raw)
    street_b = _normalize_text(b.street or b.address_normalized or b.address_raw)

    # For exact match, compare full normalized address (most authoritative)
    full_a = _normalize_text(a.address_normalized or a.address_raw)
    full_b = _normalize_text(b.address_normalized or b.address_raw)

    if full_a and full_b and full_a == full_b:
        signals["address_exact"] = True
        score = 1.0
    elif street_a and street_b:
        tokens_a = _address_tokens(street_a)
        tokens_b = _address_tokens(street_b)
        if tokens_a and tokens_b:
            overlap = len(tokens_a & tokens_b)
            union = len(tokens_a | tokens_b)
            fuzzy_score = (overlap / union) * 0.95 if union else 0.0
            signals["address_fuzzy"] = round(fuzzy_score, 4)
            score += fuzzy_score

    if a.unit_count is not None and b.unit_count is not None and a.unit_count == b.unit_count:
        signals["unit_count_match"] = True
        score += 0.15

    parcel_a = _extract_parcel_id(a)
    parcel_b = _extract_parcel_id(b)
    if parcel_a and parcel_b and parcel_a == parcel_b:
        signals["parcel_id_match"] = True
        score += 1.0

    # Tightened from 10% to 5% — price proximity alone is weak evidence
    price_a = _to_decimal(a.asking_price)
    price_b = _to_decimal(b.asking_price)
    if price_a and price_b and max(price_a, price_b) > 0:
        delta_ratio = abs(price_a - price_b) / max(price_a, price_b)
        if delta_ratio <= Decimal("0.05"):
            signals["price_overlap_within_5pct"] = True
            score += 0.05

    return min(round(score, 4), 1.0), signals


async def _resolve_candidate_listings(
    candidates: list[ScrapedListing | uuid.UUID],
    async_session: AsyncSession,
) -> list[ScrapedListing]:
    resolved: list[ScrapedListing] = []
    listing_ids: list[uuid.UUID] = []

    for candidate in candidates:
        if isinstance(candidate, ScrapedListing):
            resolved.append(candidate)
        else:
            listing_ids.append(candidate)

    if listing_ids:
        result = await async_session.execute(
            select(ScrapedListing).where(ScrapedListing.id.in_(listing_ids))
        )
        resolved.extend(list(result.scalars()))

    deduped: list[ScrapedListing] = []
    seen_ids: set[uuid.UUID] = set()
    for listing in resolved:
        if listing.id is None or listing.id in seen_ids:
            continue
        seen_ids.add(listing.id)
        deduped.append(listing)

    return deduped


async def deduplicate_batch(
    candidates: list[ScrapedListing | uuid.UUID],
    *,
    ingest_job_id: uuid.UUID | None = None,
    session: AsyncSession | None = None,
) -> list[DedupCandidate]:
    """Score likely duplicate listings and write review/merge candidates."""
    if not candidates:
        return []

    async_session = session
    if async_session is None:
        for candidate in candidates:
            if isinstance(candidate, ScrapedListing):
                async_session = async_object_session(candidate)
                if async_session is not None:
                    break

    if async_session is None:
        raise ValueError("deduplicate_batch requires an AsyncSession to persist results.")

    candidate_list = await _resolve_candidate_listings(candidates, async_session)
    if not candidate_list:
        return []

    candidate_ids = {listing.id for listing in candidate_list if listing.id is not None}
    comparison_pool = list(candidate_list)

    if candidate_ids:
        comparison_result = await async_session.execute(
            select(ScrapedListing).where(ScrapedListing.id.notin_(candidate_ids))
        )
        comparison_pool.extend(list(comparison_result.scalars()))

        existing_pairs = await async_session.execute(
            select(DedupCandidate.record_a_id, DedupCandidate.record_b_id).where(
                DedupCandidate.record_a_type == RecordType.listing,
                DedupCandidate.record_b_type == RecordType.listing,
                or_(
                    DedupCandidate.record_a_id.in_(candidate_ids),
                    DedupCandidate.record_b_id.in_(candidate_ids),
                ),
            )
        )
        seen_pairs: set[tuple[str, str]] = {
            tuple(sorted((str(record_a_id), str(record_b_id))))
            for record_a_id, record_b_id in existing_pairs.all()
        }
    else:
        seen_pairs = set()

    written: list[DedupCandidate] = []

    for listing_a in candidate_list:
        if listing_a.id is None:
            continue

        for listing_b in comparison_pool:
            if listing_b.id is None or listing_a.id == listing_b.id:
                continue
            if listing_a.listing_url == listing_b.listing_url:
                continue

            pair_key = tuple(sorted((str(listing_a.id), str(listing_b.id))))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            score, signals = _score_pair(listing_a, listing_b)
            if score < 0.60:
                continue

            resolved_ingest_job_id = ingest_job_id or listing_a.ingest_job_id or listing_b.ingest_job_id
            if resolved_ingest_job_id is None:
                continue

            record_a = listing_a
            record_b = listing_b
            if listing_a.id in candidate_ids and listing_b.id not in candidate_ids:
                record_a, record_b = listing_b, listing_a

            status = DedupStatus.merged if score >= 0.85 else DedupStatus.pending
            dedup_candidate = DedupCandidate(
                ingest_job_id=resolved_ingest_job_id,
                record_a_type=RecordType.listing,
                record_a_id=record_a.id,
                record_b_type=RecordType.listing,
                record_b_id=record_b.id,
                confidence_score=score,
                match_signals=signals,
                status=status,
            )

            if status == DedupStatus.merged:
                record_b.canonical_id = record_a.canonical_id or record_a.id
                record_b.is_new = False

            async_session.add(dedup_candidate)
            written.append(dedup_candidate)

    if written:
        await async_session.flush()

    return written
