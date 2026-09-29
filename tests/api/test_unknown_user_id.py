"""An X-User-ID that names no user must be refused before it reaches a column.

Every route here writes the caller's user id into a column with a foreign key
to ``users``. Before the ``VerifiedUserId`` / ``CurrentUser`` dependencies
(app/api/deps.py), a well-formed but unknown UUID in the X-User-ID header got
as far as the INSERT/UPDATE and came back as an unhandled 500 (FK violation).
Each test sends a request that would otherwise succeed, from a user id that
does not exist, and expects the clean 401 -- and checks nothing was written.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import DedupCandidate, DedupStatus, IngestJob, RecordType
from app.models.opportunity import Opportunity
from app.models.org import ProjectVisibility
from app.models.deal import Scenario
from app.models.scenario import Sensitivity
from tests.conftest import seed_deal_model, seed_opportunity, seed_org

# /api/ as an API client: X-API-Key + X-User-ID (see tests/api/test_auth_gate.py).
pytestmark = pytest.mark.usefixtures("api_key_auth")


def _unknown_user() -> dict[str, str]:
    return {"X-User-ID": str(uuid.uuid4())}


def _assert_unknown_user_refused(response) -> None:
    assert response.status_code == 401, response.text
    assert response.json()["message"] == "User not found"


async def _seed_listing_pair_candidate(session: AsyncSession) -> uuid.UUID:
    """Two scraped listings and a pending dedup candidate between them."""
    listings = []
    for source in ("crexi", "loopnet"):
        listing = Opportunity(
            id=uuid.uuid4(),
            org_id=None,
            source=source,
            source_id=uuid.uuid4().hex,
            address_raw="123 Main St, Gresham, OR",
            is_new=True,
        )
        session.add(listing)
        listings.append(listing)
    job = IngestJob(id=uuid.uuid4(), source="test", status="completed")
    session.add(job)
    await session.flush()
    candidate = DedupCandidate(
        id=uuid.uuid4(),
        ingest_job_id=job.id,
        record_a_type=RecordType.listing,
        record_a_id=listings[0].id,
        record_b_type=RecordType.listing,
        record_b_id=listings[1].id,
        confidence_score=0.9,
        status=DedupStatus.pending,
    )
    session.add(candidate)
    await session.commit()
    return candidate.id


async def _assert_candidate_untouched(session: AsyncSession, candidate_id: uuid.UUID) -> None:
    session.expire_all()
    row = await session.get(DedupCandidate, candidate_id)
    assert row.status == DedupStatus.pending
    assert row.resolved_by_user_id is None


# ---------------------------------------------------------------------------
# /api/dedup/{id}/merge | keep-separate | swap  -> dedup_candidates.resolved_by_user_id
# (merge also writes field_conflict_log.resolved_by_user_id)
# ---------------------------------------------------------------------------


async def test_dedup_merge_unknown_user_401(client: AsyncClient, session: AsyncSession) -> None:
    candidate_id = await _seed_listing_pair_candidate(session)
    response = await client.patch(f"/api/dedup/{candidate_id}/merge", headers=_unknown_user())
    _assert_unknown_user_refused(response)
    await _assert_candidate_untouched(session, candidate_id)


async def test_dedup_keep_separate_unknown_user_401(
    client: AsyncClient, session: AsyncSession
) -> None:
    candidate_id = await _seed_listing_pair_candidate(session)
    response = await client.patch(
        f"/api/dedup/{candidate_id}/keep-separate", headers=_unknown_user()
    )
    _assert_unknown_user_refused(response)
    await _assert_candidate_untouched(session, candidate_id)


async def test_dedup_swap_unknown_user_401(client: AsyncClient, session: AsyncSession) -> None:
    candidate_id = await _seed_listing_pair_candidate(session)
    response = await client.patch(f"/api/dedup/{candidate_id}/swap", headers=_unknown_user())
    _assert_unknown_user_refused(response)
    await _assert_candidate_untouched(session, candidate_id)


# ---------------------------------------------------------------------------
# POST /api/listings/{id}/convert  -> opportunities.created_by_user_id
# ---------------------------------------------------------------------------


async def test_convert_listing_unknown_user_401(
    client: AsyncClient, session: AsyncSession
) -> None:
    # An explicit org_id skipped the old user lookup entirely, so the raw
    # header went straight into created_by_user_id.
    org, _ = await seed_org(session)
    listing = Opportunity(
        id=uuid.uuid4(),
        org_id=None,
        source="crexi",
        source_id=uuid.uuid4().hex,
        address_raw="123 Main St, Gresham, OR",
        is_new=True,
    )
    session.add(listing)
    await session.commit()
    listing_id, org_id = listing.id, org.id

    response = await client.post(
        f"/api/listings/{listing_id}/convert",
        json={"org_id": str(org_id), "name": "Ghost Deal"},
        headers=_unknown_user(),
    )
    _assert_unknown_user_refused(response)

    session.expire_all()
    row = await session.get(Opportunity, listing_id)
    assert row.org_id is None
    assert row.created_by_user_id is None


# ---------------------------------------------------------------------------
# PATCH /api/projects/{id}/visibility  -> project_visibility.user_id
# ---------------------------------------------------------------------------


async def test_project_visibility_unknown_user_401(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)
    await session.commit()
    opportunity_id = opportunity.id

    response = await client.patch(
        f"/api/projects/{opportunity_id}/visibility",
        json={"hidden": True},
        headers=_unknown_user(),
    )
    _assert_unknown_user_refused(response)

    count = (await session.execute(select(func.count()).select_from(ProjectVisibility))).scalar_one()
    assert count == 0


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/models/import  -> deals / scenarios.created_by_user_id
# ---------------------------------------------------------------------------


async def test_project_model_import_unknown_user_401(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)
    await session.commit()
    opportunity_id = opportunity.id

    response = await client.post(
        f"/api/projects/{opportunity_id}/models/import",
        json={
            "schema_version": "deal-json-v1",
            "deal_model": {"name": "Ghost Import", "project_type": "acquisition"},
        },
        headers=_unknown_user(),
    )
    _assert_unknown_user_refused(response)

    count = (
        await session.execute(
            select(func.count()).select_from(Scenario).where(Scenario.name == "Ghost Import")
        )
    ).scalar_one()
    assert count == 0


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/scenarios  -> sensitivities.created_by_user_id
# ---------------------------------------------------------------------------


async def test_project_scenario_create_unknown_user_401(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(session, org, user)
    model = await seed_deal_model(session, opportunity, user)
    await session.commit()
    opportunity_id, model_id = opportunity.id, model.id

    with patch("app.api.routers.scenarios.sweep_variable.apply_async") as mocked_apply_async:
        response = await client.post(
            f"/api/projects/{opportunity_id}/scenarios",
            json={
                "scenario_id": str(model_id),
                "variable": "operational.exit_cap_rate_pct",
                "range_min": "4.5",
                "range_max": "6.0",
                "range_steps": 4,
            },
            headers=_unknown_user(),
        )
    _assert_unknown_user_refused(response)
    mocked_apply_async.assert_not_called()

    count = (await session.execute(select(func.count()).select_from(Sensitivity))).scalar_one()
    assert count == 0
