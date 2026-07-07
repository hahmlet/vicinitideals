"""Tests for broker-contact suggestion persistence in the email ingest task.

The LLM extraction schema has always captured broker_name/broker_email, but
until now those fields only reached the debug log. These tests cover:
- _suggestion_fields includes broker_name/broker_email in the vocabulary
- _persist_suggestions writes EmailDealSuggestion rows for broker fields
- Empty broker fields produce no rows
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.email_ingest import EmailDealSuggestion, InboundEmail
from app.tasks.email_ingest import (
    ExtractedDealInfo,
    _persist_suggestions,
    _suggestion_fields,
)
from tests.conftest import seed_org


async def _seed_inbound_email(session, org_id: uuid.UUID) -> InboundEmail:
    row = InboundEmail(
        id=uuid.uuid4(),
        org_id=org_id,
        sender_email="broker@example.com",
        status="processing",
        proforma_task_ids=[],
        attachments_meta=[],
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# _suggestion_fields — field vocabulary
# ---------------------------------------------------------------------------

class TestSuggestionFields:
    def test_broker_fields_in_vocabulary(self):
        info = ExtractedDealInfo(
            broker_name="Jane Doe",
            broker_email="jane@brokerage.com",
        )
        fields = dict((fp, val) for fp, val, _conf in _suggestion_fields(info))
        assert fields["broker_name"] == "Jane Doe"
        assert fields["broker_email"] == "jane@brokerage.com"

    def test_all_expected_field_paths_present(self):
        paths = [fp for fp, _v, _c in _suggestion_fields(ExtractedDealInfo())]
        assert paths == [
            "address",
            "acquisition_cost",
            "unit_count",
            "property_type",
            "broker_name",
            "broker_email",
        ]

    def test_empty_info_has_none_values(self):
        rows = _suggestion_fields(ExtractedDealInfo())
        assert all(value is None for _fp, value, _conf in rows)


# ---------------------------------------------------------------------------
# _persist_suggestions — DB rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_creates_broker_suggestion_rows(session):
    org, _user = await seed_org(session)
    email_row = await _seed_inbound_email(session, org.id)

    info = ExtractedDealInfo(
        address="123 Main St, Gresham, OR",
        asking_price=2_500_000.0,
        broker_name="Jane Doe",
        broker_email="Jane.Doe@Brokerage.com",
        address_confidence=0.9,
        price_confidence=0.8,
    )
    count = await _persist_suggestions(session, email_row.id, info)
    await session.commit()

    assert count == 4  # address, acquisition_cost, broker_name, broker_email

    rows = (await session.execute(
        select(EmailDealSuggestion)
        .where(EmailDealSuggestion.inbound_email_id == email_row.id)
    )).scalars().all()
    by_path = {r.field_path: r for r in rows}

    assert by_path["broker_name"].suggested_value == "Jane Doe"
    # Value is stored verbatim; normalization happens at find-or-create time.
    assert by_path["broker_email"].suggested_value == "Jane.Doe@Brokerage.com"
    for r in rows:
        assert r.source_type == "llm_extraction"
        assert r.opportunity_id is None
        assert r.accepted is None


@pytest.mark.asyncio
async def test_persist_skips_empty_broker_fields(session):
    org, _user = await seed_org(session)
    email_row = await _seed_inbound_email(session, org.id)

    info = ExtractedDealInfo(address="456 Oak Ave", address_confidence=0.9)
    count = await _persist_suggestions(session, email_row.id, info)
    await session.commit()

    assert count == 1
    rows = (await session.execute(
        select(EmailDealSuggestion)
        .where(EmailDealSuggestion.inbound_email_id == email_row.id)
    )).scalars().all()
    assert [r.field_path for r in rows] == ["address"]
