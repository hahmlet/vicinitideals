"""Dedup review endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from vicinitideals.api.deps import CurrentUserId, DBSession
from vicinitideals.models.ingestion import DedupCandidate, DedupStatus, RecordType
from vicinitideals.models.project import ScrapedListing
from vicinitideals.schemas.ingestion import DedupCandidateRead

router = APIRouter(tags=["dedup"])


def _is_listing_record(record_type: RecordType | str) -> bool:
    value = getattr(record_type, "value", str(record_type))
    return str(value) == RecordType.listing.value


@router.get("/dedup/pending", response_model=list[DedupCandidateRead])
async def list_pending_dedup_candidates(session: DBSession) -> list[DedupCandidate]:
    result = await session.execute(
        select(DedupCandidate)
        .where(DedupCandidate.status == DedupStatus.pending)
        .order_by(DedupCandidate.confidence_score.desc(), DedupCandidate.id.asc())
    )
    return list(result.scalars())


@router.patch("/dedup/{candidate_id}/merge", response_model=DedupCandidateRead)
async def merge_dedup_candidate(
    candidate_id: UUID,
    session: DBSession,
    current_user_id: CurrentUserId,
) -> DedupCandidate:
    candidate = await session.get(DedupCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Dedup candidate not found")

    candidate.status = DedupStatus.merged
    candidate.resolved_by_user_id = current_user_id
    candidate.resolved_at = datetime.now(UTC)

    if _is_listing_record(candidate.record_a_type) and _is_listing_record(candidate.record_b_type):
        record_b = await session.get(ScrapedListing, candidate.record_b_id)
        if record_b is not None:
            record_b.canonical_id = candidate.record_a_id
            record_b.is_new = False

    await session.flush()
    return candidate


@router.patch("/dedup/{candidate_id}/keep-separate", response_model=DedupCandidateRead)
async def keep_dedup_candidate_separate(
    candidate_id: UUID,
    session: DBSession,
    current_user_id: CurrentUserId,
) -> DedupCandidate:
    candidate = await session.get(DedupCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Dedup candidate not found")

    candidate.status = DedupStatus.kept_separate
    candidate.resolved_by_user_id = current_user_id
    candidate.resolved_at = datetime.now(UTC)
    await session.flush()
    return candidate


@router.patch("/dedup/{candidate_id}/swap", response_model=DedupCandidateRead)
async def swap_dedup_candidate(
    candidate_id: UUID,
    session: DBSession,
    current_user_id: CurrentUserId,
) -> DedupCandidate:
    candidate = await session.get(DedupCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Dedup candidate not found")

    candidate.status = DedupStatus.swapped
    candidate.resolved_by_user_id = current_user_id
    candidate.resolved_at = datetime.now(UTC)

    if _is_listing_record(candidate.record_a_type) and _is_listing_record(candidate.record_b_type):
        record_a = await session.get(ScrapedListing, candidate.record_a_id)
        record_b = await session.get(ScrapedListing, candidate.record_b_id)
        if record_a is not None and record_b is not None:
            record_a.canonical_id = record_b.canonical_id or record_b.id
            record_a.is_new = False
            candidate.record_a_id, candidate.record_b_id = record_b.id, record_a.id

    await session.flush()
    return candidate
