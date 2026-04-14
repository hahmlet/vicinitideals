"""IngestJob, DedupCandidate, SavedSearchCriteria schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.ingestion import DedupStatus, RecordType


# ---------------------------------------------------------------------------
# IngestJob
# ---------------------------------------------------------------------------

class IngestJobBase(BaseModel):
    source: str
    triggered_by: str | None = None
    status: str = "pending"
    records_fetched: int = 0
    records_new: int = 0
    records_duplicate_exact: int = 0
    records_flagged_review: int = 0
    records_rejected: int = 0


class IngestJobCreate(IngestJobBase):
    pass


class IngestJobRead(IngestJobBase):
    id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DedupCandidate
# ---------------------------------------------------------------------------

class DedupCandidateBase(BaseModel):
    record_a_type: RecordType
    record_a_id: uuid.UUID
    record_b_type: RecordType
    record_b_id: uuid.UUID
    confidence_score: float
    match_signals: dict | None = None
    status: DedupStatus = DedupStatus.pending
    resolved_by_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None


class DedupCandidateCreate(DedupCandidateBase):
    ingest_job_id: uuid.UUID


class DedupCandidateRead(DedupCandidateBase):
    id: uuid.UUID
    ingest_job_id: uuid.UUID

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# SavedSearchCriteria
# ---------------------------------------------------------------------------

class SavedSearchCriteriaBase(BaseModel):
    name: str
    min_units: int | None = None
    max_units: int | None = None
    max_price: Decimal | None = None
    zip_codes: list[str] | None = None
    property_types: list[str] | None = None
    sources: list[str] | None = None
    active: bool = True


class SavedSearchCriteriaCreate(SavedSearchCriteriaBase):
    user_id: uuid.UUID


class SavedSearchCriteriaRead(SavedSearchCriteriaBase):
    id: uuid.UUID
    user_id: uuid.UUID

    model_config = {"from_attributes": True}
