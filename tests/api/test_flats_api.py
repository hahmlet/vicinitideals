"""The FLATS agent lookup: the lot page's answer as JSON, on the lots the lot-page tests seed.

What is driven here is agreement: the colour and the facts the JSON reports
are the ones the lot page shows for the same lot, and the three routes are in
the OpenAPI schema (which is what makes them MCP tools).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.main import app
from flats import rulings
from tests.api.test_ui_flats_lots import DESIGNS, _login, _seed

pytestmark = pytest.mark.asyncio

TLID_A = "1S2E08BA  -09500"
TLID_C = "11E25AB  -00300"

REGISTER = """
- id: statewide-note
  kind: ruling
  date: 2026-10-01
  scope: {}
  question: Statewide?
  ruling: Yes.
  effect: Nothing.
  source: Steph 2026-10-01
- id: portland-r5
  kind: ruling
  date: 2026-10-14
  scope: {county: multnomah, city: portland, zones: [R5]}
  question: Which zone rules a split lot?
  ruling: The larger share.
  effect: The screen uses it.
  source: Steph 2026-10-14
- id: milwaukie-code
  kind: adopted_change
  date: 2026-08-01
  effective: 2099-01-01
  scope: {county: clackamas, city: milwaukie}
  question: New setbacks?
  ruling: Adopted.
  effect: Applies from the effective date.
  source: Ordinance 1, Exhibit A p. 3
- id: milwaukie-past
  kind: adopted_change
  date: 2020-08-01
  effective: 2021-01-01
  scope: {county: clackamas, city: milwaukie}
  question: Old change?
  ruling: In force.
  effect: Already applied.
  source: Ordinance 0
"""


@pytest.fixture
def register(monkeypatch, tmp_path):
    path = tmp_path / "rulings.yaml"
    path.write_text(REGISTER, encoding="utf-8")
    monkeypatch.setattr(rulings, "PATH", path)


async def test_find_by_address_fragment(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)

    found = await client.get("/api/flats/lookup", params={"q": "71st"})

    assert found.status_code == 200
    body = found.json()
    assert body["run"]["id"] == run.id
    assert [m["tlid"] for m in body["matches"]] == [TLID_A]
    match = body["matches"][0]
    assert match["county"] == "multnomah"
    assert match["address"] == "2833 SE 71ST AVE"
    assert match["zone"] == "R5"
    assert match["colour"] == "green"
    assert match["page_url"] == "/flats/lots/multnomah/1S2E08BA%20%20-09500"


async def test_find_by_tlid_with_spaces(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)

    found = await client.get("/api/flats/lookup", params={"q": TLID_C})

    assert [(m["county"], m["tlid"], m["colour"]) for m in found.json()["matches"]] == [
        ("clackamas", TLID_C, "unknown")
    ]
    assert found.json()["matches"][0]["city"]


async def test_find_with_no_match_is_an_empty_list(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)

    assert (await client.get("/api/flats/lookup", params={"q": "nowhere"})).json()["matches"] == []


async def test_the_report_says_what_the_lot_page_says(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    run = await _seed(session)

    report = (await client.get("/api/flats/lot/multnomah/1S2E08BA%20%20-09500")).json()
    page = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")

    assert report["tlid"] == TLID_A
    assert report["address"] == "2833 SE 71ST AVE" and report["address"] in page.text
    assert report["run"]["id"] == run.id
    assert report["page_url"] == "/flats/lots/multnomah/1S2E08BA%20%20-09500"
    assert report["colour"] == "green"
    assert report["verdict"] == "unknown"
    by_design = {d["design"]: d for d in report["designs"]}
    assert set(by_design) == set(DESIGNS)
    pod56 = page.text.split('id="design-pod56x36-2"', 1)[1].split('id="design-pod80x25-2"', 1)[0]
    pod80 = page.text.split('id="design-pod80x25-2"', 1)[1].split('class="card"', 1)[0]
    assert by_design[DESIGNS[0]]["colour"] == "green" and "green" in pod56
    assert by_design[DESIGNS[1]]["colour"] == "yellow" and "yellow" in pod80
    assert by_design[DESIGNS[0]]["warnings"] and by_design[DESIGNS[0]]["tight"] is True
    assert by_design[DESIGNS[1]]["failing"] == ["fit_ft"]
    assert by_design[DESIGNS[1]]["binding_constraint"] == "fit_ft"
    assert by_design[DESIGNS[1]]["stalls_seated"] == 4 and "4 cars charged, 4 seated" in pod80
    assert by_design[DESIGNS[1]]["slack_ft"] == 12.5
    assert by_design[DESIGNS[1]]["colour_reasons"]
    assert "drawing" not in by_design[DESIGNS[1]]
    labels = {f["label"]: f["value"] for f in report["key_facts"]}
    assert labels["Frontage"] == "89 ft" and "Frontage" in page.text
    for key in ("decisions", "flag_history", "net_land", "citations", "rulings", "pending_changes"):
        assert isinstance(report[key], list)


async def test_the_report_passes_forms_through_per_design(
    client: AsyncClient, session: AsyncSession
):
    from sqlalchemy import select

    from app.models.flats import FlatsLotResult

    await _login(client, session)
    run = await _seed(session)
    forms = {"works_as": "apartment", "kept": "apartment",
             "apartment": {"colour": "green"}, "townhomes": {"colour": "red", "binds": [], "flags": []}}
    rows = (await session.execute(
        select(FlatsLotResult).where(FlatsLotResult.run_id == run.id, FlatsLotResult.design_key == DESIGNS[1])
    )).scalars().all()
    for row in rows:
        row.checks = {**row.checks, "forms": forms}
    await session.commit()

    report = (await client.get("/api/flats/lot/multnomah/1S2E08BA%20%20-09500")).json()

    by_design = {d["design"]: d for d in report["designs"]}
    assert by_design[DESIGNS[1]]["forms"]["works_as"] == "apartment"
    assert by_design[DESIGNS[1]]["forms"]["townhomes"] == "red"
    assert by_design[DESIGNS[0]].get("forms") in (None, {})


async def test_the_report_carries_decisions_and_the_rulings_that_speak_to_it(
    client: AsyncClient, session: AsyncSession, register
):
    await _login(client, session)
    await _seed(session)

    a = (await client.get("/api/flats/lot/multnomah/1S2E08BA%20%20-09500")).json()
    c = (await client.get("/api/flats/lot/clackamas/11E25AB%20%20-00300")).json()

    assert [r["id"] for r in a["rulings"]] == ["statewide-note", "portland-r5"]
    assert a["pending_changes"] == []
    assert [r["id"] for r in c["rulings"]] == ["statewide-note", "milwaukie-code", "milwaukie-past"]
    assert [r["id"] for r in c["pending_changes"]] == ["milwaukie-code"]


async def test_an_unknown_lot_is_a_json_404(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)

    missing = await client.get("/api/flats/lot/multnomah/NOPE%20%201")

    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")


async def test_rulings_filter(client: AsyncClient, session: AsyncSession, register):
    await _login(client, session)

    everything = (await client.get("/api/flats/rulings")).json()
    assert everything["count"] == 4

    clackamas = (await client.get("/api/flats/rulings", params={"county": "clackamas"})).json()
    assert [r["id"] for r in clackamas["rulings"]] == ["statewide-note", "milwaukie-code", "milwaukie-past"]

    portland = (await client.get("/api/flats/rulings", params={"city": "portland", "zone": "r5"})).json()
    assert [r["id"] for r in portland["rulings"]] == ["statewide-note", "portland-r5"]

    other_zone = (await client.get("/api/flats/rulings", params={"city": "portland", "zone": "R1"})).json()
    assert [r["id"] for r in other_zone["rulings"]] == ["statewide-note"]


async def test_the_three_tools_are_in_the_openapi_schema():
    ids = {
        op.get("operationId")
        for path in app.openapi()["paths"].values()
        for op in path.values()
    }
    assert {"flats_find_lot", "flats_lot_report", "flats_rulings"} <= ids
