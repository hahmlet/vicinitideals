"""Integration tests for the deals-pipeline / opportunity UI routes.

Routes covered:
    POST  /ui/deals/{deal_id}/archive
    POST  /ui/opportunities/{opp_id}/archive          (own-org path)
    PATCH /ui/opportunities/{opp_id}/favorite         (own-org + shared-pool path)
    POST  /ui/opportunities/wizard/complete
    GET   /ui/opportunities/wizard/search
    GET   /ui/deals/rows
    GET   /ui/opportunities/rows/onmarket
    GET   /ui/opportunities/rows/offmarket            (own rows render)

Cross-org refusal of the opportunity archive / favorite writes lives in the
test_bug_* files next to this one; the off-market list's cross-org leak is a
strict xfail in test_offmarket_rows_org_scope_xfail.py.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, DealStatus
from app.models.opportunity import Opportunity
from tests.conftest import seed_opportunity, seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

_HX = {"hx-request": "true"}


async def _deal(session, org, user, name) -> Deal:
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name=name, created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    return deal


def _scraped(name: str, *, org_id=None, street: str = "") -> Opportunity:
    return Opportunity(
        id=uuid.uuid4(), org_id=org_id, name=name, street=street,
        source="crexi", source_url=f"https://example.test/{uuid.uuid4().hex}",
    )


# ---------------------------------------------------------------------------
# Deal archive
# ---------------------------------------------------------------------------

async def test_archive_own_deal_sets_status_and_drops_from_rows(
    client: AsyncClient, session: AsyncSession
):
    org, user = await seed_org(session)
    keep = await _deal(session, org, user, "Keep Me Deal")
    gone = await _deal(session, org, user, "Archive Me Deal")
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post(f"/ui/deals/{gone.id}/archive", headers=_HX)
    assert resp.status_code == 200
    await session.refresh(gone)
    await session.refresh(keep)
    assert gone.status == DealStatus.archived
    assert keep.status == DealStatus.active
    # The refreshed rows partial omits the archived deal.
    assert "Keep Me Deal" in resp.text
    assert "Archive Me Deal" not in resp.text


async def test_archive_other_orgs_deal_is_refused(client: AsyncClient, session: AsyncSession):
    org_a, user_a = await seed_org(session)
    deal_a = await _deal(session, org_a, user_a, "Alpha Deal")
    _org_b, user_b = await seed_org(session)
    await session.commit()
    set_client_auth(client, user_b.id)

    resp = await client.post(f"/ui/deals/{deal_a.id}/archive", headers=_HX)
    assert resp.status_code == 200
    await session.refresh(deal_a)
    assert deal_a.status == DealStatus.active
    # And org B's refreshed rows never show org A's deal.
    assert "Alpha Deal" not in resp.text


async def test_archive_unknown_deal_writes_nothing(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    deal = await _deal(session, org, user, "Solo Deal")
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post(f"/ui/deals/{uuid.uuid4()}/archive", headers=_HX)
    assert resp.status_code == 200
    await session.refresh(deal)
    assert deal.status == DealStatus.active
    assert "Solo Deal" in resp.text


async def test_archive_deal_requires_session(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    deal = await _deal(session, org, user, "Anon Target")
    await session.commit()

    resp = await client.post(f"/ui/deals/{deal.id}/archive", headers=_HX)
    assert resp.status_code == 401
    await session.refresh(deal)
    assert deal.status == DealStatus.active


# ---------------------------------------------------------------------------
# Opportunity archive / favorite (own org)
# ---------------------------------------------------------------------------

async def test_archive_own_opportunity(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Own Opp")
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post(f"/ui/opportunities/{opp.id}/archive")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/opportunities"
    await session.refresh(opp)
    assert opp.archived is True
    assert opp.opp_status == "archived"


async def test_favorite_toggles_own_opportunity(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Star Opp")
    await session.commit()
    set_client_auth(client, user.id)

    on = await client.patch(f"/ui/opportunities/{opp.id}/favorite", headers=_HX)
    assert on.status_code == 200
    assert "★" in on.text and "Unfavorite" in on.text
    await session.refresh(opp)
    assert opp.is_favorited is True

    off = await client.patch(f"/ui/opportunities/{opp.id}/favorite", headers=_HX)
    assert off.status_code == 200
    assert "☆" in off.text
    await session.refresh(opp)
    assert opp.is_favorited is False


async def test_favorite_shared_pool_listing_stays_open(
    client: AsyncClient, session: AsyncSession
):
    """An unpromoted scraped listing (org_id NULL) is the shared pool; any
    signed-in user may star it."""
    _org, user = await seed_org(session)
    listing = _scraped("Pool Listing")
    session.add(listing)
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.patch(f"/ui/opportunities/{listing.id}/favorite", headers=_HX)
    assert resp.status_code == 200
    await session.refresh(listing)
    assert listing.is_favorited is True


async def test_favorite_unknown_opportunity_404(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    resp = await client.patch(f"/ui/opportunities/{uuid.uuid4()}/favorite", headers=_HX)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

async def test_wizard_complete_redirects(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    opp_id = str(uuid.uuid4())

    default = await client.post("/ui/opportunities/wizard/complete", data={"opp_id": opp_id})
    assert default.status_code == 303
    assert default.headers["location"] == f"/opportunities/{opp_id}"

    back = await client.post(
        "/ui/opportunities/wizard/complete",
        data={"opp_id": opp_id, "return_to": "/models/abc/builder?module=sources"},
    )
    assert back.status_code == 303
    assert back.headers["location"] == "/models/abc/builder?module=sources"

    # Off-site targets fall back to the opportunity page.
    for evil in ("https://evil.example/x", "//evil.example/x"):
        r = await client.post(
            "/ui/opportunities/wizard/complete", data={"opp_id": opp_id, "return_to": evil}
        )
        assert r.headers["location"] == f"/opportunities/{opp_id}", evil

    missing = await client.post("/ui/opportunities/wizard/complete", data={})
    assert missing.status_code == 400


async def test_wizard_search_matches_scraped_listing(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    hit = _scraped("Zyzzyva Court Apartments", street="4411 SE Zyzzyva Ct")
    session.add(hit)
    await session.commit()
    set_client_auth(client, user.id)

    found = await client.get(
        "/ui/opportunities/wizard/search", params={"q": "zyzzyva"}, headers=_HX
    )
    assert found.status_code == 200
    assert "Zyzzyva Court Apartments" in found.text
    assert str(hit.id) in found.text

    none = await client.get(
        "/ui/opportunities/wizard/search", params={"q": "no-such-street-qqq"}, headers=_HX
    )
    assert none.status_code == 200
    assert "No match found" in none.text

    short = await client.get("/ui/opportunities/wizard/search", params={"q": "zy"}, headers=_HX)
    assert short.status_code == 200 and short.text == ""


# ---------------------------------------------------------------------------
# List partials (rendering only; org scoping of lists is owned elsewhere)
# ---------------------------------------------------------------------------

async def test_deals_rows_renders_own_deals(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    await _deal(session, org, user, "Rowdy Deal One")
    archived = await _deal(session, org, user, "Rowdy Deal Archived")
    archived.status = DealStatus.archived
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.get("/ui/deals/rows", headers=_HX)
    assert resp.status_code == 200
    assert "Rowdy Deal One" in resp.text
    assert "Rowdy Deal Archived" not in resp.text

    with_arch = await client.get(
        "/ui/deals/rows", params={"include_archived": "1"}, headers=_HX
    )
    assert "Rowdy Deal Archived" in with_arch.text

    searched = await client.get("/ui/deals/rows", params={"q": "nomatchqq"}, headers=_HX)
    assert "Rowdy Deal One" not in searched.text


async def test_onmarket_rows_render_scraped_listings(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    live = _scraped("Onmarket Live Listing")
    gone = _scraped("Onmarket Archived Listing")
    gone.archived = True
    session.add_all([live, gone])
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.get("/ui/opportunities/rows/onmarket", headers=_HX)
    assert resp.status_code == 200
    assert "Onmarket Live Listing" in resp.text
    assert "Onmarket Archived Listing" not in resp.text
    assert f"/ui/opportunities/{live.id}/favorite" in resp.text


async def test_offmarket_rows_render_manual_opportunities(
    client: AsyncClient, session: AsyncSession
):
    org, user = await seed_org(session)
    manual = await seed_opportunity(session, org, user, name="Offmarket Manual Opp")
    manual.promotion_source = "manual"
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.get("/ui/opportunities/rows/offmarket", headers=_HX)
    assert resp.status_code == 200
    assert "Offmarket Manual Opp" in resp.text

    fav_only = await client.get(
        "/ui/opportunities/rows/offmarket", params={"favorited": "1"}, headers=_HX
    )
    assert "Offmarket Manual Opp" not in fav_only.text
