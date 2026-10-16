"""Which of the pod's two forms works on a lot (Steph 2026-10-15).

"'Townhomes' will have separate lots. If we build a 4 unit apartment
building, they would not." -- and: "I need to know which of the two works on
every lot (or if both/neither)." The screen records both forms on each
result, in ``lot_results.checks["forms"]``; what is driven here is that the
lot page says it in words, the JSON lookup carries it, and the Lots list
filters on it. The rows are the lot-page tests' three seeded lots, with a
forms record written on them as the bridge would.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsLot, FlatsLotResult, FlatsRun
from tests.api.test_ui_flats_lots import DESIGNS, _login, _seed

pytestmark = pytest.mark.asyncio

USE_BIND = {"check": "use", "source": "FMC 19.135.010 row c", "relief_tier": "unavailable"}
WIDTH_BIND = {"check": "min_lot_width_ft", "observed": 60.0, "threshold": 80.0, "shortfall": 20.0,
              "source": "FMC 19.120.040(B)"}

#: Lot A: townhomes only (red on the use table as one apartment building).
#: Lot B: both. Lot C: neither -- the apartment building on the use table,
#: the townhouses on the unit-lot width. pod80 on every lot: apartment only.
TOWNHOMES_ONLY = {"works_as": "townhomes", "kept": "townhomes",
                  "apartment": {"colour": "red", "binds": [USE_BIND], "flags": []},
                  "townhomes": {"colour": "green"}}
BOTH = {"works_as": "both", "kept": "apartment",
        "apartment": {"colour": "green"}, "townhomes": {"colour": "green"}}
NEITHER = {"works_as": "neither", "kept": "apartment",
           "apartment": {"colour": "red", "binds": [USE_BIND], "flags": []},
           "townhomes": {"colour": "red", "binds": [WIDTH_BIND], "flags": []}}
APARTMENT_ONLY = {"works_as": "apartment", "kept": "apartment",
                  "apartment": {"colour": "green"},
                  "townhomes": {"colour": "red", "binds": [WIDTH_BIND], "flags": []}}


async def _forms(session: AsyncSession, run: FlatsRun) -> None:
    rows = (await session.execute(
        select(FlatsLotResult, FlatsLot.tlid).join(FlatsLot, FlatsLot.id == FlatsLotResult.lot_id)
        .where(FlatsLotResult.run_id == run.id)
    )).all()
    pod56 = {"1S2E08BA": TOWNHOMES_ONLY, "1N1E29DD": BOTH, "11E25AB": NEITHER}
    for row, tlid in rows:
        forms = APARTMENT_ONLY if row.design_key == DESIGNS[1] else pod56[tlid.split()[0]]
        row.checks = {**row.checks, "forms": forms}
    await session.commit()


def _card(text: str, design: str) -> str:
    return text.split(f'id="forms-{design.replace("@", "-")}"', 1)[1].split("</div>\n      </div>", 1)[0]


async def test_the_lot_page_says_which_form_works_in_words(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _forms(session, await _seed(session))

    a = (await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")).text
    pod56 = _card(a, DESIGNS[0])
    assert 'data-works-as="townhomes"' in a
    assert "Works as: townhomes only -- the apartment form fails because the zone does not allow four attached homes" in pod56
    assert "the colour below is the townhouse form&#39;s" in pod56 or "the colour below is the townhouse form's" in pod56
    pod80 = _card(a, DESIGNS[1])
    assert "Works as: apartment only -- the townhomes form fails because lot narrower than the minimum" in pod80

    b = (await client.get("/flats/lots/multnomah/1N1E29DD%20%20-05600")).text
    assert "Works as: townhomes (4 lots) and apartment (1 lot)" in _card(b, DESIGNS[0])

    c = (await client.get("/flats/lots/clackamas/11E25AB%20%20-00300")).text
    neither = _card(c, DESIGNS[0])
    assert "Works as: neither" in neither
    assert "the apartment form fails because the zone does not allow four attached homes" in neither
    assert "the townhomes form fails because lot narrower than the minimum" in neither


async def test_a_run_screened_before_both_forms_says_nothing_of_them(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    page = (await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")).text
    assert 'id="forms-' not in page
    assert "Works as:" not in page


async def test_the_json_lookup_carries_the_forms(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _forms(session, await _seed(session))

    report = (await client.get("/api/flats/lot/multnomah/1S2E08BA%20%20-09500")).json()

    by_design = {d["design"]: d for d in report["designs"]}
    pod56 = by_design[DESIGNS[0]]["forms"]
    assert pod56["works_as"] == "townhomes"
    assert pod56["kept"] == "townhomes"
    assert (pod56["apartment"], pod56["townhomes"]) == ("red", "green")
    assert pod56["text"].startswith("Works as: townhomes only")
    assert by_design[DESIGNS[1]]["forms"]["works_as"] == "apartment"


@pytest.mark.parametrize(
    ("form", "shown"),
    [
        # A form works on a lot where any design comes out green in it:
        # pod80 works as an apartment building on every lot, so lot A --
        # townhomes only with pod56 -- works both ways across the two.
        ("townhomes", set()),
        ("apartment", {"10722 SE 32ND AVE"}),
        ("both", {"2833 SE 71ST AVE", "4110 NE 12TH AVE"}),
        ("neither", set()),
    ],
)
async def test_the_lots_list_filters_on_which_form_works(
    client: AsyncClient, session: AsyncSession, form: str, shown: set[str]
):
    await _login(client, session)
    await _forms(session, await _seed(session))

    page = await client.get("/flats/lots", params={"form": form})

    assert page.status_code == 200
    table = page.text.split('id="lot-table"', 1)[1]
    addresses = {"2833 SE 71ST AVE", "4110 NE 12TH AVE", "10722 SE 32ND AVE"}
    assert {a for a in addresses if a in table} == shown
    assert f'<option value="{form}" selected' in page.text


@pytest.mark.parametrize(
    ("form", "shown"),
    [
        ("townhomes", {"2833 SE 71ST AVE"}),
        ("apartment", set()),
        ("both", {"4110 NE 12TH AVE"}),
        ("neither", {"10722 SE 32ND AVE"}),
    ],
)
async def test_one_design_alone_filters_on_its_own_forms(
    client: AsyncClient, session: AsyncSession, form: str, shown: set[str]
):
    await _login(client, session)
    await _forms(session, await _seed(session))

    page = await client.get("/flats/lots", params={"form": form, "design": DESIGNS[0]})

    table = page.text.split('id="lot-table"', 1)[1]
    addresses = {"2833 SE 71ST AVE", "4110 NE 12TH AVE", "10722 SE 32ND AVE"}
    assert {a for a in addresses if a in table} == shown


async def test_the_filter_reads_only_rows_that_recorded_both_forms(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    for form in ("both", "townhomes", "apartment", "neither"):
        table = (await client.get("/flats/lots", params={"form": form})).text.split('id="lot-table"', 1)[1]
        assert "2833 SE 71ST AVE" not in table
    # And an unknown choice is no filter at all.
    table = (await client.get("/flats/lots", params={"form": "duplex"})).text.split('id="lot-table"', 1)[1]
    assert "2833 SE 71ST AVE" in table
