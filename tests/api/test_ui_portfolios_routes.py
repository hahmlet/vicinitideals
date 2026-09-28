"""Integration tests for app/api/routers/ui_portfolios.py.

Covers every route in the router:

  - GET    /portfolios                          list page (deal count + avg IRR)
  - GET    /ui/deals/search                     add-deal picker search
  - POST   /ui/portfolios/create                new portfolio in the user's org
  - GET    /portfolios/{id}                     detail page (deal rows + stats)
  - POST   /ui/portfolios/{id}/add-deal         link a deal's opportunity
  - POST   /ui/portfolios/{id}/remove-deal      unlink it
  - GET    /api/saved-filters                   per-user filter snapshots
  - POST   /api/saved-filters                   create / overwrite by name
  - DELETE /api/saved-filters/{id}              delete own filter only

Assertions check the data that came back or the row that changed, not just
the status code.
"""

from __future__ import annotations

import html
import re
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cashflow import OperationalOutputs
from app.models.deal import Deal, DealStatus, Scenario
from app.models.org import Organization, User
from app.models.portfolio import Portfolio, PortfolioProject
from app.models.project import Opportunity, Project
from app.models.saved_filter import SavedFilter

from tests.conftest import seed_deal_model, seed_opportunity, seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_deal(
    session: AsyncSession,
    org: Organization,
    user: User,
    *,
    name: str,
    opp_name: str | None = None,
) -> tuple[Deal, Scenario, Opportunity]:
    """Deal → active Scenario → Project → Opportunity, the shape add-deal walks."""
    opp = await seed_opportunity(session, org, user, name=opp_name or f"{name} Site")
    scenario = await seed_deal_model(session, opp, user, name=name)
    session.add(Project(
        id=uuid.uuid4(), scenario_id=scenario.id, opportunity_id=opp.id, name="Main",
    ))
    await session.flush()
    deal = await session.get(Deal, scenario.deal_id)
    assert deal is not None
    return deal, scenario, opp


async def _seed_outputs(
    session: AsyncSession, scenario: Scenario, *, irr: str, noi: str, equity: str,
) -> None:
    session.add(OperationalOutputs(
        scenario_id=scenario.id,
        project_irr_levered=Decimal(irr),
        noi_stabilized=Decimal(noi),
        equity_required=Decimal(equity),
    ))
    await session.flush()


async def _commit(session: AsyncSession) -> None:
    """Commit, then detach everything. The ``client`` fixture hands the
    request this same session; without the expunge, ``session.get`` in the
    route returns the seeded instance from the identity map with its
    relationships unloaded, and the template's lazy load fails
    (MissingGreenlet) in a way production — a fresh session per request —
    never sees."""
    await session.commit()
    session.expunge_all()


async def _portfolio_rows(session: AsyncSession, portfolio_id: uuid.UUID) -> list[PortfolioProject]:
    session.expire_all()
    return list((await session.execute(
        select(PortfolioProject).where(PortfolioProject.portfolio_id == portfolio_id)
    )).scalars())


# ---------------------------------------------------------------------------
# GET /portfolios
# ---------------------------------------------------------------------------


async def test_portfolios_page_shows_deal_count_and_average_irr(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    _d1, s1, o1 = await _seed_deal(session, org, user, name="Alder Deal")
    _d2, s2, o2 = await _seed_deal(session, org, user, name="Birch Deal")
    await _seed_outputs(session, s1, irr="10.0", noi="100000", equity="500000")
    await _seed_outputs(session, s2, irr="15.0", noi="200000", equity="700000")
    p = Portfolio(id=uuid.uuid4(), org_id=org.id, name="Eastside Fund")
    session.add(p)
    await session.flush()
    session.add_all([
        PortfolioProject(portfolio_id=p.id, project_id=o1.id, scenario_id=s1.id),
        PortfolioProject(portfolio_id=p.id, project_id=o2.id, scenario_id=s2.id),
    ])
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.get("/portfolios")

    assert resp.status_code == 200, resp.text
    assert "Eastside Fund" in resp.text
    assert f"/portfolios/{p.id}" in resp.text
    # (10.0 + 15.0) / 2
    assert "12.5%" in resp.text


# ---------------------------------------------------------------------------
# GET /ui/deals/search
# ---------------------------------------------------------------------------


async def test_deal_search_finds_own_active_deals_only(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    other_org, other_user = await seed_org(session)
    mine, _s, _o = await _seed_deal(session, org, user, name="Riverside Flats")
    archived, _s2, _o2 = await _seed_deal(session, org, user, name="Riverside Old")
    archived.status = DealStatus.archived
    theirs, _s3, _o3 = await _seed_deal(session, other_org, other_user, name="Riverside Theirs")
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.get("/ui/deals/search", params={"q": "river"})

    assert resp.status_code == 200
    assert str(mine.id) in resp.text
    assert "Riverside Flats" in resp.text
    assert str(archived.id) not in resp.text
    assert str(theirs.id) not in resp.text


async def test_deal_search_needs_two_characters(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    await _seed_deal(session, org, user, name="Riverside Flats")
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.get("/ui/deals/search", params={"q": "r"})
    assert resp.status_code == 200
    assert resp.text == ""

    none = await client.get("/ui/deals/search", params={"q": "zzz-no-match"})
    assert "No deals found" in none.text


async def test_deal_search_answers_the_parameter_the_page_sends(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The add-deal drawer's search box sends whatever field its hx-include
    names. If that is not the parameter the route reads, every search comes
    back empty and no deal can ever be added from the page."""
    org, user = await seed_org(session)
    deal, _s, _o = await _seed_deal(session, org, user, name="Maple Court")
    p = Portfolio(id=uuid.uuid4(), org_id=org.id, name="Search Fund")
    session.add(p)
    await _commit(session)
    set_client_auth(client, user.id)

    page = await client.get(f"/portfolios/{p.id}")
    assert page.status_code == 200, page.text
    included = re.search(
        r'hx-get="/ui/deals/search".*?hx-include="\[name=\'([^\']+)\'\]"', page.text, re.S
    )
    assert included, "add-deal search box not found on the portfolio page"
    param = included.group(1)

    resp = await client.get("/ui/deals/search", params={param: "maple"})

    assert str(deal.id) in resp.text, (
        f"page sends ?{param}= but the search route ignored it"
    )


async def test_deal_search_result_survives_an_apostrophe(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Picking a result runs its onclick. A name like "Tom's Place" must
    reach the page as a well-formed JS string and as escaped text."""
    org, user = await seed_org(session)
    deal, _s, _o = await _seed_deal(session, org, user, name="Tom's <Place>")
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.get("/ui/deals/search", params={"q": "tom"})

    onclick = re.search(r'onclick="([^"]*)"', resp.text)
    assert onclick, resp.text
    js = html.unescape(onclick.group(1))
    assert f"value='{deal.id}'" in js or f'value="{deal.id}"' in js
    assert '.value="Tom\'s <Place>"' in js
    assert "<Place>" not in resp.text.split(">", 1)[1]  # visible text is escaped


# ---------------------------------------------------------------------------
# POST /ui/portfolios/create
# ---------------------------------------------------------------------------


async def test_create_portfolio_in_users_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.post("/ui/portfolios/create", data={"name": "  West Fund  "})

    assert resp.status_code == 303
    rows = list((await session.execute(
        select(Portfolio).where(Portfolio.org_id == org.id)
    )).scalars())
    assert [r.name for r in rows] == ["West Fund"]
    assert resp.headers["location"] == f"/portfolios/{rows[0].id}"


async def test_create_portfolio_requires_a_name(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.post("/ui/portfolios/create", data={"name": "   "})

    assert resp.status_code == 400
    assert "required" in resp.text
    assert (await session.execute(select(Portfolio))).scalars().first() is None


# ---------------------------------------------------------------------------
# GET /portfolios/{id}
# ---------------------------------------------------------------------------


async def test_portfolio_detail_lists_deals_and_totals(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    _d1, s1, o1 = await _seed_deal(session, org, user, name="Alder Deal", opp_name="Alder Site")
    _d2, s2, o2 = await _seed_deal(session, org, user, name="Birch Deal", opp_name="Birch Site")
    await _seed_outputs(session, s1, irr="10.0", noi="100000", equity="500000")
    await _seed_outputs(session, s2, irr="14.0", noi="250000", equity="700000")
    p = Portfolio(id=uuid.uuid4(), org_id=org.id, name="Totals Fund")
    session.add(p)
    await session.flush()
    session.add_all([
        PortfolioProject(portfolio_id=p.id, project_id=o1.id, scenario_id=s1.id),
        PortfolioProject(portfolio_id=p.id, project_id=o2.id, scenario_id=s2.id),
    ])
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.get(f"/portfolios/{p.id}")

    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "Totals Fund" in body
    assert "Alder Site" in body and "Birch Site" in body
    assert f"/models/{s1.id}/builder" in body
    assert "Deals (2)" in body
    assert "12.0%" in body            # avg IRR (10 + 14) / 2
    assert "$1,200,000" in body       # total equity 500k + 700k
    assert "$350,000" in body         # total NOI 100k + 250k


async def test_empty_portfolio_detail_renders(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A portfolio fresh from Create has no deals — the page it redirects to
    must render, not 500."""
    org, user = await seed_org(session)
    p = Portfolio(id=uuid.uuid4(), org_id=org.id, name="Brand New Fund")
    session.add(p)
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.get(f"/portfolios/{p.id}")

    assert resp.status_code == 200, resp.text
    assert "Brand New Fund" in resp.text
    assert "Deals (0)" in resp.text


async def test_portfolio_detail_other_org_is_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    other_org, _other = await seed_org(session)
    p = Portfolio(id=uuid.uuid4(), org_id=other_org.id, name="Not Yours Fund")
    session.add(p)
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.get(f"/portfolios/{p.id}")

    assert resp.status_code == 404
    assert "Not Yours Fund" not in resp.text

    missing = await client.get(f"/portfolios/{uuid.uuid4()}")
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# POST /ui/portfolios/{id}/add-deal  +  /remove-deal
# ---------------------------------------------------------------------------


async def test_add_deal_links_opportunity_and_active_scenario_once(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    deal, scenario, opp = await _seed_deal(session, org, user, name="Cedar Deal")
    p = Portfolio(id=uuid.uuid4(), org_id=org.id, name="Add Fund")
    session.add(p)
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.post(f"/ui/portfolios/{p.id}/add-deal", data={"deal_id": str(deal.id)})
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/portfolios/{p.id}"

    rows = await _portfolio_rows(session, p.id)
    assert [(r.project_id, r.scenario_id) for r in rows] == [(opp.id, scenario.id)]

    # Adding the same deal again does not duplicate it
    again = await client.post(f"/ui/portfolios/{p.id}/add-deal", data={"deal_id": str(deal.id)})
    assert again.status_code == 303
    assert len(await _portfolio_rows(session, p.id)) == 1


async def test_add_deal_rejects_bad_input(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    bare = await seed_deal_model(session, opp, user, name="No Project Deal")  # no Project row
    p = Portfolio(id=uuid.uuid4(), org_id=org.id, name="Reject Fund")
    session.add(p)
    await _commit(session)
    set_client_auth(client, user.id)

    bad = await client.post(f"/ui/portfolios/{p.id}/add-deal", data={"deal_id": "not-a-uuid"})
    assert bad.status_code == 400

    missing = await client.post(f"/ui/portfolios/{p.id}/add-deal", data={"deal_id": str(uuid.uuid4())})
    assert missing.status_code == 404

    unlinked = await client.post(f"/ui/portfolios/{p.id}/add-deal", data={"deal_id": str(bare.deal_id)})
    assert unlinked.status_code == 400
    assert "no linked opportunity" in unlinked.text

    assert await _portfolio_rows(session, p.id) == []


async def test_add_deal_cannot_cross_orgs(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Neither another org's portfolio nor another org's deal may be touched."""
    org, user = await seed_org(session)
    other_org, other_user = await seed_org(session)
    my_deal, _s, _o = await _seed_deal(session, org, user, name="Mine Deal")
    their_deal, _s2, _o2 = await _seed_deal(session, other_org, other_user, name="Theirs Deal")
    mine = Portfolio(id=uuid.uuid4(), org_id=org.id, name="My Fund")
    theirs = Portfolio(id=uuid.uuid4(), org_id=other_org.id, name="Their Fund")
    session.add_all([mine, theirs])
    await _commit(session)
    set_client_auth(client, user.id)

    into_theirs = await client.post(
        f"/ui/portfolios/{theirs.id}/add-deal", data={"deal_id": str(my_deal.id)}
    )
    assert into_theirs.status_code == 404
    assert await _portfolio_rows(session, theirs.id) == []

    their_deal_into_mine = await client.post(
        f"/ui/portfolios/{mine.id}/add-deal", data={"deal_id": str(their_deal.id)}
    )
    assert their_deal_into_mine.status_code == 404
    assert await _portfolio_rows(session, mine.id) == []


async def test_remove_deal_unlinks_only_that_opportunity(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    _d1, s1, o1 = await _seed_deal(session, org, user, name="Keep Deal")
    _d2, s2, o2 = await _seed_deal(session, org, user, name="Drop Deal")
    p = Portfolio(id=uuid.uuid4(), org_id=org.id, name="Remove Fund")
    session.add(p)
    await session.flush()
    session.add_all([
        PortfolioProject(portfolio_id=p.id, project_id=o1.id, scenario_id=s1.id),
        PortfolioProject(portfolio_id=p.id, project_id=o2.id, scenario_id=s2.id),
    ])
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.post(f"/ui/portfolios/{p.id}/remove-deal", data={"opportunity_id": str(o2.id)})

    assert resp.status_code == 303
    assert [r.project_id for r in await _portfolio_rows(session, p.id)] == [o1.id]

    bad = await client.post(f"/ui/portfolios/{p.id}/remove-deal", data={"opportunity_id": "nope"})
    assert bad.status_code == 400


async def test_remove_deal_cannot_touch_another_orgs_portfolio(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    other_org, other_user = await seed_org(session)
    _d, s, o = await _seed_deal(session, other_org, other_user, name="Their Deal")
    theirs = Portfolio(id=uuid.uuid4(), org_id=other_org.id, name="Their Fund")
    session.add(theirs)
    await session.flush()
    session.add(PortfolioProject(portfolio_id=theirs.id, project_id=o.id, scenario_id=s.id))
    await _commit(session)
    set_client_auth(client, user.id)

    resp = await client.post(
        f"/ui/portfolios/{theirs.id}/remove-deal", data={"opportunity_id": str(o.id)}
    )

    assert resp.status_code == 404
    assert [r.project_id for r in await _portfolio_rows(session, theirs.id)] == [o.id]


# ---------------------------------------------------------------------------
# /api/saved-filters
# ---------------------------------------------------------------------------


async def test_saved_filter_create_list_overwrite_delete(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    await _commit(session)
    set_client_auth(client, user.id)

    created = await client.post("/api/saved-filters", data={
        "page": "deals", "name": "Big ones", "query_string": "min_units=20",
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Big ones"
    assert body["url"] == "/deals?min_units=20"

    # Same name on the same page overwrites instead of duplicating
    again = await client.post("/api/saved-filters", data={
        "page": "deals", "name": "Big ones", "query_string": "min_units=50",
    })
    assert again.json()["id"] == body["id"]

    listed = await client.get("/api/saved-filters", params={"page": "deals"})
    items = listed.json()["items"]
    assert [(i["name"], i["url"]) for i in items] == [("Big ones", "/deals?min_units=50")]

    # Other pages are separate
    assert (await client.get("/api/saved-filters", params={"page": "opportunities"})).json() == {"items": []}

    deleted = await client.delete(f"/api/saved-filters/{body['id']}")
    assert deleted.json() == {"ok": True}
    session.expire_all()
    assert (await session.execute(select(SavedFilter))).scalars().first() is None


async def test_saved_filter_validation_and_ownership(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    other = User(id=uuid.uuid4(), org_id=org.id, name="Other Person")
    session.add(other)
    await session.flush()
    theirs = SavedFilter(user_id=other.id, page="deals", name="Theirs", query_string="q=x")
    session.add(theirs)
    await _commit(session)

    # Unauthenticated: list is empty, writes are refused
    assert (await client.get("/api/saved-filters", params={"page": "deals"})).json() == {"items": []}
    anon = await client.post("/api/saved-filters", data={"page": "deals", "name": "x"})
    assert anon.status_code == 401

    set_client_auth(client, user.id)

    # Another user's filter is invisible and undeletable
    assert (await client.get("/api/saved-filters", params={"page": "deals"})).json() == {"items": []}
    denied = await client.delete(f"/api/saved-filters/{theirs.id}")
    assert denied.status_code == 404
    session.expire_all()
    assert await session.get(SavedFilter, theirs.id) is not None

    bad_page = await client.post("/api/saved-filters", data={"page": "nowhere", "name": "x"})
    assert bad_page.status_code == 400
    no_name = await client.post("/api/saved-filters", data={"page": "deals", "name": " "})
    assert no_name.status_code == 400
