from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.ingestion import DedupCandidate, DedupStatus, IngestJob
from app.models.scraped_listing import ScrapedListing
from app.scrapers.dedup import _score_pair, deduplicate_batch


async def _create_ingest_job(session) -> IngestJob:
    ingest_job = IngestJob(
        source="loopnet",
        triggered_by="pytest",
        status="running",
    )
    session.add(ingest_job)
    await session.flush()
    return ingest_job


def _make_listing(
    *,
    ingest_job_id,
    address_normalized: str,
    listing_url: str | None = None,
    asking_price: Decimal | None = None,
    unit_count: int | None = None,
    raw_json: dict | None = None,
) -> ScrapedListing:
    return ScrapedListing(
        id=uuid4(),
        ingest_job_id=ingest_job_id,
        source="loopnet",
        listing_url=listing_url or f"https://example.com/listings/{uuid4().hex}",
        address_normalized=address_normalized,
        address_raw=address_normalized,
        asking_price=asking_price,
        unit_count=unit_count,
        raw_json=raw_json or {},
        is_new=True,
        matches_saved_criteria=False,
    )


def test_score_pair_exact_address_match_caps_at_one() -> None:
    listing_a = _make_listing(
        ingest_job_id=uuid4(),
        address_normalized="123 MAIN ST GRESHAM OR 97030",
        asking_price=Decimal("1000000"),
        unit_count=8,
    )
    listing_b = _make_listing(
        ingest_job_id=uuid4(),
        address_normalized="123 MAIN ST GRESHAM OR 97030",
        asking_price=Decimal("1040000"),
        unit_count=8,
    )

    score, signals = _score_pair(listing_a, listing_b)

    assert score == 1.0
    assert signals["address_exact"] is True
    assert signals["unit_count_match"] is True
    # Price signal tightened from 10% to 5% overlap; 4% delta still qualifies.
    assert signals["price_overlap_within_5pct"] is True


def test_score_pair_fuzzy_address_scoring() -> None:
    listing_a = _make_listing(
        ingest_job_id=uuid4(),
        address_normalized="123 MAIN ST",
    )
    listing_b = _make_listing(
        ingest_job_id=uuid4(),
        address_normalized="123 MAIN AVE",
    )

    score, signals = _score_pair(listing_a, listing_b)

    assert score == pytest.approx(0.95, rel=1e-6)
    assert signals["address_exact"] is False
    assert signals["address_fuzzy"] == pytest.approx(0.95, rel=1e-6)


@pytest.mark.asyncio
async def test_deduplicate_batch_auto_merges_high_confidence_pairs(session) -> None:
    ingest_job = await _create_ingest_job(session)
    listing_a = _make_listing(
        ingest_job_id=ingest_job.id,
        address_normalized="123 MAIN ST",
        listing_url="https://example.com/a",
    )
    listing_b = _make_listing(
        ingest_job_id=ingest_job.id,
        address_normalized="123 MAIN AVE",
        listing_url="https://example.com/b",
    )
    session.add_all([listing_a, listing_b])
    await session.flush()

    written = await deduplicate_batch(
        [listing_a, listing_b],
        ingest_job_id=ingest_job.id,
        session=session,
    )

    assert len(written) == 1
    assert written[0].status == DedupStatus.merged
    assert written[0].confidence_score == pytest.approx(0.95, rel=1e-6)
    assert written[0].match_signals["address_fuzzy"] == pytest.approx(0.95, rel=1e-6)
    assert listing_b.is_new is False
    assert listing_b.canonical_id == listing_a.id


@pytest.mark.asyncio
async def test_deduplicate_batch_flags_pending_medium_confidence_pairs(session) -> None:
    ingest_job = await _create_ingest_job(session)
    listing_a = _make_listing(
        ingest_job_id=ingest_job.id,
        address_normalized="123 MAIN ST",
        listing_url="https://example.com/c",
    )
    listing_b = _make_listing(
        ingest_job_id=ingest_job.id,
        address_normalized="123 MAIN OAK ST",
        listing_url="https://example.com/d",
    )
    session.add_all([listing_a, listing_b])
    await session.flush()

    written = await deduplicate_batch(
        [listing_a, listing_b],
        ingest_job_id=ingest_job.id,
        session=session,
    )

    assert len(written) == 1
    assert written[0].status == DedupStatus.pending
    assert written[0].confidence_score == pytest.approx(0.6333, rel=1e-4)
    assert listing_b.is_new is True
    assert listing_b.canonical_id is None


@pytest.mark.asyncio
async def test_deduplicate_batch_skips_low_confidence_pairs(session) -> None:
    ingest_job = await _create_ingest_job(session)
    listing_a = _make_listing(
        ingest_job_id=ingest_job.id,
        address_normalized="123 MAIN ST",
        listing_url="https://example.com/e",
    )
    listing_b = _make_listing(
        ingest_job_id=ingest_job.id,
        address_normalized="999 OAK AVE",
        listing_url="https://example.com/f",
    )
    session.add_all([listing_a, listing_b])
    await session.flush()

    written = await deduplicate_batch(
        [listing_a, listing_b],
        ingest_job_id=ingest_job.id,
        session=session,
    )

    rows = list((await session.execute(select(DedupCandidate))).scalars())

    assert written == []
    assert rows == []
    assert listing_b.is_new is True
    assert listing_b.canonical_id is None
