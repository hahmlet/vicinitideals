"""Integration tests for app/api/routers/ui_data_intel.py — listings, brokers,
dedup (Data Cleanup) and the Realie-skip toggle.

Every route in the router is covered:

  Listings   GET  /listings (redirect)            GET  /ui/listings/rows
             GET  /ui/listings/export.csv         GET  /ui/listings/promoted/rows
             GET  /ui/listings/{id}/raw           GET  /ui/listings/{id}/detail
             POST /ui/listings/{id}/promote       POST /ui/listings/{id}/promote-redirect
             POST /ui/listings/{id}/revert        POST /ui/listings/{id}/archive
             POST /ui/listings/{id}/unarchive     POST /ui/listings/{id}/realie-skip
  Brokers    GET  /brokers                        GET  /ui/brokers/rows
             GET  /ui/brokers/{id}/detail         POST /ui/brokers/{id}/license
             POST /ui/brokers/{id}/oregon-update  GET  /ui/brokers/quick-create-form
             POST /ui/brokers/quick-create
  Dedup      GET  /dedup (3 tabs)                 GET  /ui/dedup/{id}/compare
             POST /ui/dedup/{id}/keep-separate    POST /ui/dedup/{id}/resolve

Assertions check the data in the response, or the row the route changed.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker, BrokerDisciplinaryAction, Brokerage
from app.models.ingestion import DedupCandidate, DedupStatus, IngestJob, RecordType
from app.models.opportunity import Opportunity

from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def client(client: AsyncClient) -> AsyncClient:
    """The listing/broker/dedup fragments are HTMX requests in production."""
    client.headers["hx-request"] = "true"
    return client


async def _login(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    return org, user


async def _commit(session: AsyncSession) -> None:
    """Commit and detach. The ``client`` fixture shares this session with the
    route; detaching makes the route load rows (and their relationships)
    fresh, as it does in production."""
    await session.commit()
    session.expunge_all()


async def _reload(session: AsyncSession, model, row_id):
    """Read the row as the database now has it, then detach it again so the
    next request loads it fresh too."""
    session.expunge_all()
    row = await session.get(model, row_id)
    session.expunge_all()
    return row


def _listing(**kw) -> Opportunity:
    fields = dict(
        id=uuid.uuid4(),
        org_id=None,
        source="crexi",
        source_id=uuid.uuid4().hex,
        address_raw="123 Main St, Gresham, OR",
        address_normalized="123 MAIN ST, GRESHAM, OR 97030",
        city="Gresham",
        county="Multnomah",
        is_new=True,
        archived=False,
    )
    fields.update(kw)
    return Opportunity(**fields)


def _broker(first: str, last: str, **kw) -> Broker:
    return Broker(id=uuid.uuid4(), first_name=first, last_name=last, **kw)


# ===========================================================================
# Listings
# ===========================================================================


async def test_listings_page_redirects_to_opportunities(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    resp = await client.get("/listings")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/opportunities"


async def test_listing_rows_split_new_promoted_archived_and_filter(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await _login(client, session)
    new = _listing(address_normalized="10 NEW ST, GRESHAM, OR", units=12, asking_price=Decimal("2400000"))
    small = _listing(address_normalized="20 SMALL ST, GRESHAM, OR", units=2)
    archived = _listing(address_normalized="30 GONE ST, GRESHAM, OR", archived=True, is_new=False, units=12)
    promoted = _listing(address_normalized="40 KEPT ST, GRESHAM, OR", org_id=org.id, units=12)
    salem = _listing(address_normalized="50 FAR ST, SALEM, OR", city="Salem", county="Marion", units=12)
    session.add_all([new, small, archived, promoted, salem])
    await _commit(session)

    resp = await client.get("/ui/listings/rows", params={"min_units": "5", "jurisdiction": "Gresham"})

    assert resp.status_code == 200, resp.text
    body = resp.text
    new_part, _, oob = body.partition('id="promoted-tbody"')
    promoted_part, _, archived_part = oob.partition('id="archived-tbody"')
    assert "10 NEW ST" in new_part
    assert "$2,400,000" in new_part
    assert "40 KEPT ST" in promoted_part
    assert "30 GONE ST" in archived_part
    assert "20 SMALL ST" not in body     # below min_units
    assert "50 FAR ST" not in body       # other jurisdiction


async def test_listing_rows_search_by_address(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    session.add_all([
        _listing(address_normalized="1 ALDER WAY, GRESHAM, OR"),
        _listing(address_normalized="2 BIRCH WAY, GRESHAM, OR"),
    ])
    await _commit(session)

    resp = await client.get("/ui/listings/rows", params={"q": "alder"})

    assert "1 ALDER WAY" in resp.text
    assert "2 BIRCH WAY" not in resp.text


async def test_listings_export_csv_follows_filters(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    session.add_all([
        _listing(address_normalized="7 BIG ST, GRESHAM, OR", units=24, asking_price=Decimal("3100000"),
                 cap_rate=Decimal("5.25"), property_type="Multifamily", year_built=1978),
        _listing(address_normalized="8 TINY ST, GRESHAM, OR", units=1),
    ])
    await _commit(session)

    resp = await client.get("/ui/listings/export.csv", params={"min_units": "10"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "listings_export.csv" in resp.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows[0][:5] == ["Address", "City", "County", "Units", "Asking Price"]
    assert rows[1:] == [[
        "7 BIG ST, GRESHAM, OR", "Gresham", "Multnomah", "24", "3100000.0",
        "Multifamily", "5.25%", "1978", "crexi",
    ]]


async def test_promoted_rows_only_promoted_and_filtered(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await _login(client, session)
    session.add_all([
        _listing(address_normalized="1 PROMO ST, GRESHAM, OR", org_id=org.id, source="loopnet"),
        _listing(address_normalized="2 PROMO ST, GRESHAM, OR", org_id=org.id, source="crexi"),
        _listing(address_normalized="3 RAW ST, GRESHAM, OR", source="loopnet"),
    ])
    await _commit(session)

    resp = await client.get("/ui/listings/promoted/rows", params={"promoted_source": "loopnet"})

    assert resp.status_code == 200
    assert "1 PROMO ST" in resp.text
    assert "2 PROMO ST" not in resp.text   # other source
    assert "3 RAW ST" not in resp.text     # not promoted


async def test_listing_raw_json(client: AsyncClient, session: AsyncSession) -> None:
    await _login(client, session)
    with_raw = _listing(raw_json={"crexi": {"id": 991, "name": "Raw Plaza"}})
    without = _listing(address_normalized="9 PLAIN ST", units=6, asking_price=Decimal("900000"))
    session.add_all([with_raw, without])
    await _commit(session)

    raw = await client.get(f"/ui/listings/{with_raw.id}/raw")
    assert json.loads(raw.text) == {"crexi": {"id": 991, "name": "Raw Plaza"}}

    fallback = json.loads((await client.get(f"/ui/listings/{without.id}/raw")).text)
    assert fallback["id"] == str(without.id)
    assert fallback["address"] == "9 PLAIN ST"
    assert fallback["units"] == 6
    assert fallback["asking_price"] == 900000.0

    missing = await client.get(f"/ui/listings/{uuid.uuid4()}/raw")
    assert json.loads(missing.text) == {"error": "not found"}


async def test_listing_detail_shows_facts_and_broker(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    firm = Brokerage(id=uuid.uuid4(), name="Rose City Realty")
    broker = _broker("Dana", "Fir", brokerage_id=firm.id, email="dana@rosecity.test")
    session.add_all([firm, broker])
    await session.flush()
    listing = _listing(zoning="RM2", apn="R123456", asking_price=Decimal("1750000"), broker_id=broker.id)
    session.add(listing)
    await _commit(session)

    resp = await client.get(f"/ui/listings/{listing.id}/detail")

    assert resp.status_code == 200, resp.text
    assert "RM2" in resp.text
    assert "R123456" in resp.text
    assert "$1,750,000" in resp.text
    assert "Dana Fir" in resp.text
    assert f"/ui/listings/{listing.id}/promote-redirect" in resp.text  # not promoted yet

    missing = await client.get(f"/ui/listings/{uuid.uuid4()}/detail")
    assert "Not found" in missing.text


async def test_promote_listing_sets_org_and_returns_promoted_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await _login(client, session)
    listing = _listing(address_normalized="5 PROMOTE AVE, GRESHAM, OR")
    session.add(listing)
    await _commit(session)

    resp = await client.post(f"/ui/listings/{listing.id}/promote")

    assert resp.status_code == 200, resp.text
    assert f"/opportunities/{listing.id}" in resp.text
    row = await _reload(session, Opportunity, listing.id)
    assert row.org_id == org.id
    assert row.promotion_source == "manual"
    assert row.name == "5 PROMOTE AVE, GRESHAM, OR"

    # Promoting again is a no-op that still returns the promoted row
    again = await client.post(f"/ui/listings/{listing.id}/promote")
    assert f"/opportunities/{listing.id}" in again.text


async def test_promote_redirect_goes_to_the_opportunity(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await _login(client, session)
    listing = _listing()
    session.add(listing)
    await _commit(session)

    resp = await client.post(f"/ui/listings/{listing.id}/promote-redirect")

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/opportunities/{listing.id}"
    assert (await _reload(session, Opportunity, listing.id)).org_id == org.id

    missing = await client.post(f"/ui/listings/{uuid.uuid4()}/promote-redirect")
    assert missing.status_code == 303
    assert missing.headers["location"] == "/listings"


async def test_revert_archive_unarchive_move_the_listing(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await _login(client, session)
    listing = _listing(address_normalized="6 CYCLE ST, GRESHAM, OR", org_id=org.id, is_new=False,
                       opp_status="hypothetical")
    session.add(listing)
    await _commit(session)
    lid = listing.id

    reverted = await client.post(f"/ui/listings/{lid}/revert")
    assert reverted.status_code == 200
    assert f"/ui/listings/{lid}/archive" in reverted.text      # rendered as a New row
    row = await _reload(session, Opportunity, lid)
    assert (row.org_id, row.opp_status, row.is_new, row.archived) == (None, None, True, False)

    archived = await client.post(f"/ui/listings/{lid}/archive")
    assert f"/ui/listings/{lid}/unarchive" in archived.text    # rendered as an Archived row
    row = await _reload(session, Opportunity, lid)
    assert (row.is_new, row.archived) == (False, True)

    restored = await client.post(f"/ui/listings/{lid}/unarchive")
    assert f"/ui/listings/{lid}/archive" in restored.text
    row = await _reload(session, Opportunity, lid)
    assert (row.is_new, row.archived) == (True, False)

    for action in ("archive", "unarchive"):
        assert (await client.post(f"/ui/listings/{uuid.uuid4()}/{action}")).text == ""


async def test_realie_skip_toggles_and_labels_the_next_action(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    listing = _listing(realie_skip=False)
    session.add(listing)
    await _commit(session)

    on = await client.post(f"/ui/listings/{listing.id}/realie-skip")
    assert ">Enable Realie</button>" in on.text
    assert (await _reload(session, Opportunity, listing.id)).realie_skip is True

    off = await client.post(f"/ui/listings/{listing.id}/realie-skip")
    assert ">Skip Realie</button>" in off.text
    assert (await _reload(session, Opportunity, listing.id)).realie_skip is False


# ===========================================================================
# Brokers
# ===========================================================================


async def _seed_brokers(session: AsyncSession) -> tuple[Broker, Broker]:
    firm = Brokerage(id=uuid.uuid4(), name="Cascade Commercial")
    other_firm = Brokerage(id=uuid.uuid4(), name="Willamette Partners")
    busy = _broker("Avery", "Ash", brokerage_id=firm.id, email="avery@cascade.test",
                   license_number="201234567", license_state="OR")
    quiet = _broker("Blake", "Birch", brokerage_id=other_firm.id)
    session.add_all([firm, other_firm, busy, quiet])
    await session.flush()
    session.add_all([
        _listing(address_normalized="1 ASH ST", broker_id=busy.id),
        _listing(address_normalized="2 ASH ST", broker_id=busy.id),
    ])
    await session.flush()
    return busy, quiet


async def test_brokers_page_lists_brokers_with_listing_counts(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    busy, quiet = await _seed_brokers(session)
    await _commit(session)
    del client.headers["hx-request"]   # full page

    resp = await client.get("/brokers")

    assert resp.status_code == 200, resp.text
    assert "Avery Ash" in resp.text and "Blake Birch" in resp.text
    assert "avery@cascade.test" in resp.text
    assert "201234567 (OR)" in resp.text

    by_firm = await client.get("/brokers", params={"company": "willamette"})
    assert "Blake Birch" in by_firm.text
    assert "Avery Ash" not in by_firm.text


async def test_broker_rows_filter_by_name_and_listing_count(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    await _seed_brokers(session)
    await _commit(session)

    by_name = await client.get("/ui/brokers/rows", params={"q": "blake"})
    assert "Blake Birch" in by_name.text and "Avery Ash" not in by_name.text

    by_firm_name = await client.get("/ui/brokers/rows", params={"q": "cascade"})
    assert "Avery Ash" in by_firm_name.text and "Blake Birch" not in by_firm_name.text

    two_plus = await client.get("/ui/brokers/rows", params={"listings_op": "gte", "listings_val": "2"})
    assert "Avery Ash" in two_plus.text and "Blake Birch" not in two_plus.text

    none_found = await client.get("/ui/brokers/rows", params={"q": "nobody-here"})
    assert "No brokers yet" in none_found.text


async def test_broker_detail_shows_listings_and_discipline(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    busy, _quiet = await _seed_brokers(session)
    session.add(BrokerDisciplinaryAction(
        broker_id=busy.id, case_number="2019-0042", order_signed_date=date(2019, 6, 1),
        resolution="Reprimand",
    ))
    await _commit(session)

    resp = await client.get(f"/ui/brokers/{busy.id}/detail")

    assert resp.status_code == 200, resp.text
    assert "Avery Ash" in resp.text
    assert "Listings (2)" in resp.text
    assert "1 ASH ST" in resp.text and "2 ASH ST" in resp.text
    assert "Disciplinary Actions (1)" in resp.text
    assert "2019-0042" in resp.text

    assert "Not found" in (await client.get(f"/ui/brokers/{uuid.uuid4()}/detail")).text


async def test_broker_license_update_locks_and_clears(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    _busy, quiet = await _seed_brokers(session)
    await _commit(session)

    resp = await client.post(
        f"/ui/brokers/{quiet.id}/license",
        data={"license_number": " 200999888 ", "license_state": "or"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["HX-Trigger"] == "brokerSaved"
    assert 'value="200999888"' in resp.text
    row = await _reload(session, Broker, quiet.id)
    assert (row.license_number, row.license_state, row.license_number_locked) == ("200999888", "OR", True)

    cleared = await client.post(f"/ui/brokers/{quiet.id}/license", data={"license_number": "", "license_state": ""})
    assert cleared.status_code == 200
    row = await _reload(session, Broker, quiet.id)
    assert (row.license_number, row.license_state, row.license_number_locked) == (None, None, False)


async def test_broker_oregon_update_marks_pending_and_queues(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    busy, _quiet = await _seed_brokers(session)
    await _commit(session)

    with patch("app.tasks.oregon_elicense.enrich_broker_oregon.delay") as delay:
        resp = await client.post(f"/ui/brokers/{busy.id}/oregon-update")

    assert resp.status_code == 200, resp.text
    delay.assert_called_once_with(str(busy.id))
    row = await _reload(session, Broker, busy.id)
    assert row.oregon_lookup_status == "pending"
    assert row.license_number_locked is False   # enrichment does not touch the lock


async def test_broker_quick_create_form(client: AsyncClient, session: AsyncSession) -> None:
    await _login(client, session)
    resp = await client.get("/ui/brokers/quick-create-form")
    assert resp.status_code == 200
    assert 'hx-post="/ui/brokers/quick-create"' in resp.text
    assert 'name="first_name"' in resp.text and 'name="brokerage_name"' in resp.text


async def test_broker_quick_create_reuses_firm_and_selects_new_broker(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    firm = Brokerage(id=uuid.uuid4(), name="Cascade Commercial")
    session.add(firm)
    await _commit(session)

    resp = await client.post("/ui/brokers/quick-create", data={
        "first_name": "Casey", "last_name": "Cedar",
        "email": "casey@cascade.test", "brokerage_name": "  cascade COMMERCIAL ",
    })

    assert resp.status_code == 200, resp.text
    session.expunge_all()
    new = (await session.execute(select(Broker).where(Broker.last_name == "Cedar"))).scalar_one()
    assert new.brokerage_id == firm.id   # matched case-insensitively, not duplicated
    assert new.email == "casey@cascade.test"
    assert len((await session.execute(select(Brokerage))).scalars().all()) == 1
    assert f'<option value="{new.id}" selected>Cedar, Casey · Cascade Commercial</option>' in resp.text

    brand_new = await client.post("/ui/brokers/quick-create", data={
        "first_name": "Dev", "last_name": "Dogwood", "brokerage_name": "New Firm LLC",
    })
    assert brand_new.status_code == 200
    session.expunge_all()
    names = sorted(b.name for b in (await session.execute(select(Brokerage))).scalars())
    assert names == ["Cascade Commercial", "New Firm LLC"]


# ===========================================================================
# Dedup (Data Cleanup)
# ===========================================================================


async def _seed_dedup(session: AsyncSession, **cand_kw) -> tuple[DedupCandidate, Opportunity, Opportunity]:
    job = IngestJob(source="crexi", triggered_by="pytest", status="completed")
    session.add(job)
    await session.flush()
    a = _listing(ingest_job_id=job.id, source="crexi", address_raw="77 Oak St, Gresham, OR",
                 source_url="https://crexi.test/77", asking_price=Decimal("1500000"), units=8)
    b = _listing(ingest_job_id=job.id, source="loopnet", address_raw="77 Oak Street, Gresham, OR",
                 source_url="https://loopnet.test/77", asking_price=Decimal("1450000"), units=8)
    session.add_all([a, b])
    await session.flush()
    fields = dict(
        ingest_job_id=job.id,
        record_a_type=RecordType.listing, record_a_id=a.id,
        record_b_type=RecordType.listing, record_b_id=b.id,
        confidence_score=0.91, match_signals={"address_fuzzy": 0.91},
        status=DedupStatus.pending,
    )
    fields.update(cand_kw)
    cand = DedupCandidate(**fields)
    session.add(cand)
    await session.flush()
    return cand, a, b


async def test_dedup_page_tabs(client: AsyncClient, session: AsyncSession) -> None:
    await _login(client, session)
    pending, _a, _b = await _seed_dedup(session)
    done, _c, _d = await _seed_dedup(session, status=DedupStatus.kept_separate, confidence_score=0.62)
    skipped = _listing(street="TL 1500 Unknown Rd", city="Estacada", realie_skip=True, apn=None)
    session.add(skipped)
    await _commit(session)
    del client.headers["hx-request"]   # full page

    page = await client.get("/dedup")
    assert page.status_code == 200, page.text
    assert f'id="dedup-row-{pending.id}"' in page.text
    assert f'id="dedup-row-{done.id}"' not in page.text
    assert "91%" in page.text
    assert "77 Oak St, Gresham, OR" in page.text and "77 Oak Street, Gresham, OR" in page.text
    assert "address fuzzy" in page.text

    resolved = await client.get("/dedup", params={"tab": "resolved"})
    assert f'id="dedup-row-{done.id}"' in resolved.text
    assert f'id="dedup-row-{pending.id}"' not in resolved.text
    assert "kept separate" in resolved.text

    issues = await client.get("/dedup", params={"tab": "address_issues"})
    assert "TL 1500 Unknown Rd" in issues.text
    assert "1 address issues" in issues.text


async def test_address_issue_button_names_the_action_it_takes(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Every row on the Address Issues tab is already skipped. Its button
    must offer what clicking does — the toggle route turns skipping OFF and
    labels that state "Enable Realie" — not repeat "Skip Realie"."""
    await _login(client, session)
    skipped = _listing(street="V/L Hwy 26", city="Sandy", realie_skip=True, apn=None)
    session.add(skipped)
    await _commit(session)
    del client.headers["hx-request"]

    page = await client.get("/dedup", params={"tab": "address_issues"})
    start = page.text.index(f'id="skip-btn-{skipped.id}"')
    button = page.text[start:page.text.index("</button>", start)]
    assert "Enable Realie" in button, button


async def test_dedup_compare_lists_conflicts_and_matches(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    cand, _a, _b = await _seed_dedup(session)
    await _commit(session)

    resp = await client.get(f"/ui/dedup/{cand.id}/compare")

    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "Crexi" in body and "Loopnet" in body
    assert "https://crexi.test/77" in body
    assert 'name="field_asking_price"' in body          # prices differ -> conflict radio
    assert "$1,500,000" in body and "$1,450,000" in body
    assert 'name="field_units"' not in body             # same units -> a match, no radio
    assert f'hx-post="/ui/dedup/{cand.id}/resolve"' in body

    assert "Candidate not found" in (await client.get(f"/ui/dedup/{uuid.uuid4()}/compare")).text


async def test_dedup_keep_separate_records_resolver(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await _login(client, session)
    cand, _a, _b = await _seed_dedup(session)
    await _commit(session)

    resp = await client.post(f"/ui/dedup/{cand.id}/keep-separate")

    assert "Marked as separate records" in resp.text
    row = await _reload(session, DedupCandidate, cand.id)
    assert row.status == DedupStatus.kept_separate
    assert row.resolved_by_user_id == user.id
    assert row.resolved_at is not None


async def test_dedup_resolve_keep_separate(client: AsyncClient, session: AsyncSession) -> None:
    await _login(client, session)
    cand, a, b = await _seed_dedup(session)
    await _commit(session)

    resp = await client.post(f"/ui/dedup/{cand.id}/resolve", data={"action": "keep_separate"})

    assert "Kept as separate records" in resp.text
    assert (await _reload(session, DedupCandidate, cand.id)).status == DedupStatus.kept_separate
    assert (await _reload(session, Opportunity, b.id)).canonical_id is None


async def test_dedup_resolve_merge_takes_chosen_fields_from_the_loser(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await _login(client, session)
    cand, a, b = await _seed_dedup(session)
    await _commit(session)

    resp = await client.post(f"/ui/dedup/{cand.id}/resolve", data={
        "action": "merge", "winner": "a",
        "field_asking_price": "b",      # take B's price onto A
        "field_units": "a",
        "field_org_id": "b",            # not an allowed field: ignored
    })

    assert "merged into primary" in resp.text
    winner = await _reload(session, Opportunity, a.id)
    loser = await _reload(session, Opportunity, b.id)
    assert Decimal(winner.asking_price) == Decimal("1450000")
    assert (loser.canonical_id, loser.archived, loser.is_new) == (a.id, True, False)
    cand_row = await _reload(session, DedupCandidate, cand.id)
    assert cand_row.status == DedupStatus.merged
    assert cand_row.resolved_by_user_id == user.id


async def test_dedup_resolve_merge_with_b_as_primary_is_a_swap(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _login(client, session)
    cand, a, b = await _seed_dedup(session)
    await _commit(session)

    resp = await client.post(f"/ui/dedup/{cand.id}/resolve", data={"action": "merge", "winner": "b"})

    assert "merged (B preferred)" in resp.text
    assert (await _reload(session, Opportunity, a.id)).canonical_id == b.id
    assert Decimal((await _reload(session, Opportunity, b.id)).asking_price) == Decimal("1450000")
    assert (await _reload(session, DedupCandidate, cand.id)).status == DedupStatus.swapped

    assert (await client.post(f"/ui/dedup/{uuid.uuid4()}/resolve", data={"action": "merge"})).text == ""
