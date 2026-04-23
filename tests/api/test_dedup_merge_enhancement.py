"""Tests for dedup merge endpoint enhancement — field fill + conflict logging."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.field_conflict_log import FieldConflictAction, FieldConflictLog
from app.models.ingestion import DedupCandidate, DedupStatus, IngestJob, RecordType
from app.models.project import ScrapedListing
from app.scrapers.merge_enhancement import apply_enhancement, diff_fields


async def _mk_listing(
    session,
    *,
    source: str,
    source_id: str,
    apn: str | None = None,
    asking_price: Decimal | None = None,
    cap_rate: Decimal | None = None,
    description: str | None = None,
    gba_sqft: Decimal | None = None,
) -> ScrapedListing:
    listing = ScrapedListing(
        id=uuid.uuid4(),
        source=source,
        source_id=source_id,
        source_url=f"https://{source}.example/{source_id}",
        apn=apn,
        asking_price=asking_price,
        cap_rate=cap_rate,
        description=description,
        gba_sqft=gba_sqft,
    )
    session.add(listing)
    await session.flush()
    return listing


async def _mk_candidate(
    session, canonical: ScrapedListing, loser: ScrapedListing
) -> DedupCandidate:
    job = IngestJob(id=uuid.uuid4(), source="test", status="completed")
    session.add(job)
    await session.flush()
    cand = DedupCandidate(
        id=uuid.uuid4(),
        ingest_job_id=job.id,
        record_a_type=RecordType.listing,
        record_a_id=canonical.id,
        record_b_type=RecordType.listing,
        record_b_id=loser.id,
        confidence_score=0.9,
        status=DedupStatus.pending,
    )
    session.add(cand)
    await session.flush()
    return cand


@pytest.mark.asyncio
async def test_apply_enhancement_fills_null_fields(session) -> None:
    canonical = await _mk_listing(
        session, source="crexi", source_id="c1",
        apn=None, asking_price=Decimal("1000000"),
    )
    loser = await _mk_listing(
        session, source="loopnet", source_id="l1",
        apn="R12345", asking_price=Decimal("1000000"), cap_rate=Decimal("7"),
    )

    log_rows = apply_enhancement(
        canonical, loser,
        merge_candidate_id=None, resolved_by_user_id=None,
    )

    # apn was NULL on canonical → filled
    assert canonical.apn == "R12345"
    # cap_rate was NULL on canonical → filled
    assert canonical.cap_rate == Decimal("7")
    # asking_price matched → no change, no log
    assert canonical.asking_price == Decimal("1000000")

    fills = [r for r in log_rows if r.action == FieldConflictAction.fill.value]
    assert len(fills) == 2
    assert {r.field_name for r in fills} == {"apn", "cap_rate"}


@pytest.mark.asyncio
async def test_apply_enhancement_logs_conflict_without_mutating(session) -> None:
    canonical = await _mk_listing(
        session, source="crexi", source_id="c1",
        asking_price=Decimal("1000000"),
    )
    loser = await _mk_listing(
        session, source="loopnet", source_id="l1",
        asking_price=Decimal("1200000"),  # 20% disagreement — beyond tolerance
    )
    log_rows = apply_enhancement(
        canonical, loser, merge_candidate_id=None, resolved_by_user_id=None,
    )
    assert canonical.asking_price == Decimal("1000000")  # canonical unchanged

    conflicts = [r for r in log_rows if r.action == FieldConflictAction.conflict.value]
    assert any(r.field_name == "asking_price" for r in conflicts)


@pytest.mark.asyncio
async def test_apply_enhancement_tolerates_small_numeric_diff(session) -> None:
    canonical = await _mk_listing(
        session, source="crexi", source_id="c1",
        cap_rate=Decimal("7.00"),
    )
    loser = await _mk_listing(
        session, source="loopnet", source_id="l1",
        cap_rate=Decimal("7.005"),  # 0.07% diff — within 1% tolerance
    )
    log_rows = apply_enhancement(
        canonical, loser, merge_candidate_id=None, resolved_by_user_id=None,
    )
    assert all(r.field_name != "cap_rate" for r in log_rows)


@pytest.mark.asyncio
async def test_diff_fields_preview_matches_enhancement(session) -> None:
    canonical = await _mk_listing(
        session, source="crexi", source_id="c1",
        apn=None, asking_price=Decimal("1000000"),
    )
    loser = await _mk_listing(
        session, source="loopnet", source_id="l1",
        apn="R12345", asking_price=Decimal("1200000"),
    )
    preview = diff_fields(canonical, loser)
    assert any(f["field_name"] == "apn" for f in preview["fills"])
    assert any(c["field_name"] == "asking_price" for c in preview["conflicts"])

    # Ensure preview did NOT mutate canonical
    assert canonical.apn is None
    assert canonical.asking_price == Decimal("1000000")


@pytest.mark.asyncio
async def test_merge_endpoint_emits_conflict_log_rows(session, client, auth_headers) -> None:
    canonical = await _mk_listing(
        session, source="crexi", source_id="c2",
        apn=None, description=None,
    )
    loser = await _mk_listing(
        session, source="loopnet", source_id="l2",
        apn="R99999", description="Broker notes from LoopNet",
    )
    cand = await _mk_candidate(session, canonical, loser)
    await session.commit()

    # Call the merge endpoint
    response = await client.patch(f"/api/dedup/{cand.id}/merge", headers=auth_headers)
    assert response.status_code == 200, response.text

    # The test 'session' fixture is rolled back, but the client uses the same session.
    # Read log rows through the session we have.
    result = await session.execute(
        select(FieldConflictLog).where(
            FieldConflictLog.canonical_listing_id == canonical.id
        )
    )
    rows = list(result.scalars())
    field_names = {r.field_name for r in rows}
    assert "apn" in field_names
    assert "description" in field_names
    assert all(r.action == FieldConflictAction.fill.value for r in rows)

    # Canonical enriched in place
    await session.refresh(canonical)
    assert canonical.apn == "R99999"
    assert canonical.description == "Broker notes from LoopNet"

    # Loser now points at canonical
    await session.refresh(loser)
    assert loser.canonical_id == canonical.id
    assert loser.is_new is False


@pytest.mark.asyncio
async def test_preview_endpoint_returns_diff_without_mutation(session, client, auth_headers) -> None:
    canonical = await _mk_listing(
        session, source="crexi", source_id="c3",
        apn=None, cap_rate=None,
    )
    loser = await _mk_listing(
        session, source="loopnet", source_id="l3",
        apn="R77777", cap_rate=Decimal("6.5"),
    )
    cand = await _mk_candidate(session, canonical, loser)
    await session.commit()

    response = await client.get(f"/api/dedup/{cand.id}/preview", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    field_names = {f["field_name"] for f in body["fills"]}
    assert {"apn", "cap_rate"} <= field_names

    # No mutation happened
    await session.refresh(canonical)
    assert canonical.apn is None
    assert canonical.cap_rate is None
