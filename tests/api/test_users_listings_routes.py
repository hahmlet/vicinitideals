"""Integration tests for routers with zero coverage: users.py and listings.py.

Covers:
  - GET  /api/users                       — all users, sorted by name
  - GET  /api/orgs/{org_id}/users         — org-scoped users, 404 unknown org
  - GET  /api/listings                    — scraped-listing list + is_new filter
  - POST /api/listings/{id}/convert       — promote scraped listing to opportunity
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.org import User

from tests.conftest import seed_org, seed_opportunity

pytestmark = pytest.mark.asyncio


async def _seed_scraped_listing(session: AsyncSession, **overrides) -> Opportunity:
    """Un-promoted scraped listing: org_id=None, source=crexi."""
    listing = Opportunity(
        id=uuid.uuid4(),
        org_id=None,
        source="crexi",
        source_id=uuid.uuid4().hex,
        address_raw="123 Main St, Gresham, OR",
        address_normalized="123 main st gresham or",
        is_new=True,
    )
    for k, v in overrides.items():
        setattr(listing, k, v)
    session.add(listing)
    await session.flush()
    return listing


# ---------------------------------------------------------------------------
# GET /api/users
# ---------------------------------------------------------------------------


async def test_list_all_users_returns_all_sorted_by_name(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user_a = await seed_org(session)
    user_a.name = "Alice"
    user_b = User(id=uuid.uuid4(), org_id=org.id, name="Bob")
    session.add(user_b)
    await session.flush()

    resp = await client.get("/api/users")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = [u["name"] for u in body]
    assert names == sorted(names)
    ids = {u["id"] for u in body}
    assert str(user_a.id) in ids
    assert str(user_b.id) in ids


# ---------------------------------------------------------------------------
# GET /api/orgs/{org_id}/users
# ---------------------------------------------------------------------------


async def test_list_org_users_scoped_to_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    org1, user1 = await seed_org(session)
    org2, user2 = await seed_org(session)
    org1_id, user1_id, user2_id = org1.id, user1.id, user2.id

    resp = await client.get(f"/api/orgs/{org1_id}/users")
    assert resp.status_code == 200, resp.text
    ids = {u["id"] for u in resp.json()}
    assert str(user1_id) in ids
    assert str(user2_id) not in ids


async def test_list_org_users_unknown_org_404(client: AsyncClient) -> None:
    resp = await client.get(f"/api/orgs/{uuid.uuid4()}/users")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/listings
# ---------------------------------------------------------------------------


async def test_list_listings_returns_seeded_rows(
    client: AsyncClient, session: AsyncSession
) -> None:
    fresh = await _seed_scraped_listing(session)
    stale = await _seed_scraped_listing(session, is_new=False)
    fresh_id, stale_id = fresh.id, stale.id

    resp = await client.get("/api/listings")
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert str(fresh_id) in ids
    assert str(stale_id) in ids


async def test_list_listings_is_new_filter(
    client: AsyncClient, session: AsyncSession
) -> None:
    fresh = await _seed_scraped_listing(session)
    stale = await _seed_scraped_listing(session, is_new=False)
    fresh_id, stale_id = fresh.id, stale.id

    resp = await client.get("/api/listings", params={"is_new": "true"})
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert str(fresh_id) in ids
    assert str(stale_id) not in ids


async def test_list_listings_matches_criteria_filter(
    client: AsyncClient, session: AsyncSession
) -> None:
    match = await _seed_scraped_listing(session, matches_saved_criteria=True)
    nomatch = await _seed_scraped_listing(session)
    match_id, nomatch_id = match.id, nomatch.id

    resp = await client.get("/api/listings", params={"matches_criteria": "true"})
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert str(match_id) in ids
    assert str(nomatch_id) not in ids


# ---------------------------------------------------------------------------
# POST /api/listings/{listing_id}/convert
# ---------------------------------------------------------------------------


async def test_convert_listing_promotes_to_opportunity(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    listing = await _seed_scraped_listing(session)
    org_id, user_id, listing_id = org.id, user.id, listing.id

    client.headers["X-User-ID"] = str(user_id)
    resp = await client.post(
        f"/api/listings/{listing_id}/convert",
        json={"name": "Gresham Deal"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(listing_id)
    assert body["name"] == "Gresham Deal"

    session.expire_all()
    row = await session.get(Opportunity, listing_id)
    assert row.org_id == org_id
    assert row.created_by_user_id == user_id
    assert row.is_new is False
    assert row.opp_status == "hypothetical"
    assert row.project_category == "proposed"
    assert row.promotion_source == "manual"


async def test_convert_listing_defaults_name_from_address(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, user = await seed_org(session)
    listing = await _seed_scraped_listing(session)
    listing_id, user_id = listing.id, user.id

    client.headers["X-User-ID"] = str(user_id)
    resp = await client.post(f"/api/listings/{listing_id}/convert", json={})
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "123 main st gresham or"


async def test_convert_already_promoted_listing_is_noop(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    opp_id, org_id, user_id, opp_name = opp.id, org.id, user.id, opp.name

    client.headers["X-User-ID"] = str(user_id)
    resp = await client.post(
        f"/api/listings/{opp_id}/convert",
        json={"name": "Should Be Ignored"},
    )
    assert resp.status_code == 201, resp.text
    # Already promoted (org_id set) — returned unchanged
    assert resp.json()["name"] == opp_name

    session.expire_all()
    row = await session.get(Opportunity, opp_id)
    assert row.org_id == org_id
    assert row.name == opp_name


async def test_convert_unknown_listing_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, user = await seed_org(session)
    client.headers["X-User-ID"] = str(user.id)
    resp = await client.post(f"/api/listings/{uuid.uuid4()}/convert", json={})
    assert resp.status_code == 404
