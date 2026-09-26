"""The lot pages: what the screen said, lot by lot.

The county run lands in ``flats.lots`` / ``flats.lot_results`` and these two
pages are the first thing that reads it. What is driven here is the shape of
the answer rather than its content: the verdict the screen can stand behind
comes first and the colour it would take once the rules are signed sits
beside it, never in its place; the counts on the list are the same numbers a
person was told about the run; and the older screen's colour is kept next to
ours so the two can be compared.

The rows are seeded by hand. Three lots, two designs, one run -- enough for
every colour to appear once and for "either design" to differ from one design
alone. Every lot row belongs to a county-copy snapshot, and the pages carry
the copy's failure-state warning (HUMAN_TODO 20): red when the copy is stale
or a source moved, a footer naming the copy when nothing is wrong.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import (
    FlatsDesign,
    FlatsLot,
    FlatsLotResult,
    FlatsProbe,
    FlatsRun,
    FlatsSnapshot,
)
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

DESIGNS = ("pod56x36@2", "pod80x25@2")


def _today() -> date:
    """The banner's clock runs on UTC dates; so do the rows seeded here."""
    return datetime.now(timezone.utc).date()

#: A box in EPSG:2913 feet, as EWKT, so the geometry column is exercised.
def _box(x: float, y: float, w: float, d: float) -> str:
    return (
        f"SRID=2913;MULTIPOLYGON((({x} {y}, {x + w} {y}, {x + w} {y + d}, "
        f"{x} {y + d}, {x} {y})))"
    )


def _checks(colour: str, *, head: str | None = None, seated: int = 8, band: str = "preferred",
            colour_reasons: list[str] | None = None, unknown: list[str] | None = None,
            tight: bool = False) -> dict:
    return {
        "verdict": "unknown",
        "if_signed": colour,
        "reasons": ["RULE_UNVERIFIED"],
        "if_signed_reasons": colour_reasons or [],
        "head": head,
        "failing": [head] if head else [],
        "unchecked": ["far", "max_units"],
        "ask": "as_of_right" if colour == "green" else "adjustment",
        "fits": colour != "red",
        "fit": {"slack_ft": 12.5, "best_depth_ft": 48.5, "required_ft": 36.0, "across_ft": 68.0,
                "angle_deg": 88.0, "orientation": "width_facing", "tight": tight},
        "stalls": {"charged": 4, "seated": seated, "band": band},
        "leaning": {"assumed": [], "unknown": unknown or []},
        "search": {"angles": 181, "step_deg": 1.0},
        "rule_verdict": "unverified",
    }


async def _snapshot(
    session: AsyncSession,
    *,
    taken: date | None = None,
    status: str = "current",
    manifest: dict | None = None,
    registered: datetime | None = None,
    new_zones: dict | None = None,
) -> FlatsSnapshot:
    """A county copy for lot rows to belong to; fresh and complete unless told otherwise."""
    snap = FlatsSnapshot(
        snapshot_date=taken or (_today() - timedelta(days=1)),
        host="137",
        status=status,
        rlis_release="2026_08",
        manifest=manifest if manifest is not None else {"datasets": {"rlis_taxlots": {"status": "acquired"}}},
        counts={"lots": 3, **({"new_zones": new_zones} if new_zones else {})},
    )
    if registered is not None:
        snap.registered_at = registered
    session.add(snap)
    await session.flush()
    return snap


async def _checked(session: AsyncSession, *, ran: datetime | None = None, findings: list[dict] | None = None) -> FlatsProbe:
    """A monthly source check that found nothing, unless told otherwise."""
    row = FlatsProbe(
        ran_at=ran or datetime.now(timezone.utc),
        status="warn" if findings else "ok",
        findings=findings or [{"key": "rlis_taxlots", "finding": "ok", "detail": "release 2026_08"}],
        seconds=3.2,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed(
    session: AsyncSession,
    *,
    run_id: int = 1,
    finished: str = "2026-09-18T17:51:00+00:00",
    snapshot: FlatsSnapshot | None = None,
    status: str = "complete",
    checked: bool = True,
) -> FlatsRun:
    """One run, two designs, three lots, six results -- on a fresh, checked county copy."""
    if snapshot is None:
        snapshot = await _snapshot(session)
    if checked:
        await _checked(session)
    run = FlatsRun(
        id=run_id,
        started_at=datetime(2026, 9, 18, 10, 51, tzinfo=timezone.utc),
        finished_at=datetime.fromisoformat(finished),
        status=status,
        code_version="9b045c40deadbeef",
        rules_version="13aec434",
        design_keys=list(DESIGNS),
        counties=["multnomah", "clackamas"],
        params={"counts": {"lots": 3}},
        notes="seeded",
        snapshot_id=snapshot.id,
    )
    session.add(run)
    for key in DESIGNS:
        if await session.get(FlatsDesign, key) is None:
            design_id, version = key.split("@")
            session.add(
                FlatsDesign(
                    key=key, design_id=design_id, version=int(version), label=design_id,
                    typology="pod", width_ft=56, depth_ft=36, units=4, stories=2, height_ft=28,
                )
            )
    await session.flush()

    lots = [
        FlatsLot(
            tlid="1S2E08BA  -09500", county="multnomah", jurisdiction="or/multnomah/portland",
            zone_raw="R5", zone="R5", site_address="2833 SE 71ST AVE", area_sqft=13973,
            geom=_box(7_650_000, 680_000, 89, 157), centroid="SRID=4326;POINT(-122.5903 45.5019)",
            condo_verdict="land",
            facts={"source": "quadfit", "frontage_ft": 89.0, "lot_width_ft": 89.0, "lot_depth_ft": 157.0,
                   "geometry_tier": "A", "observed": {"corner_lot": False, "abuts_alley": False, "public_sewer": True},
                   "slope": {"mean_pct": 3.5, "p85_pct": 5.7, "max_pct": 16.1, "source": "dem_1m"},
                   "quadfit": {"triage": "green", "binding_constraint": None, "policy_exclusion": None,
                               "parking_tier": "preferred", "stalls_provided": 8, "layout_method": "townhome_rear_court"}},
            first_seen_run_id=run.id, updated_run_id=run.id, snapshot_id=snapshot.id,
        ),
        FlatsLot(
            tlid="1N1E29DD  -05600", county="multnomah", jurisdiction="or/multnomah/portland",
            zone_raw="R2.5a", zone="R2.5", site_address="4110 NE 12TH AVE", area_sqft=5000,
            geom=_box(7_640_000, 690_000, 50, 100), centroid="SRID=4326;POINT(-122.6535 45.5535)",
            condo_verdict="land",
            facts={"source": "quadfit", "frontage_ft": 50.0, "lot_width_ft": 50.0, "lot_depth_ft": 100.0,
                   "geometry_tier": "A", "observed": {"abuts_alley": True, "alley_at_rear": True}, "alley_width_ft": 20.0,
                   "quadfit": {"triage": "red", "binding_constraint": "siteplan_no_layout", "policy_exclusion": None,
                               "parking_tier": None, "stalls_provided": 0, "layout_method": None}},
            first_seen_run_id=run.id, updated_run_id=run.id, snapshot_id=snapshot.id,
        ),
        FlatsLot(
            tlid="11E25AB  -00300", county="clackamas", jurisdiction="or/clackamas/milwaukie",
            zone_raw="R-7", zone="R-7", site_address="10722 SE 32ND AVE", area_sqft=7200,
            geom=_box(7_660_000, 640_000, 60, 120), centroid="SRID=4326;POINT(-122.6338 45.4321)",
            condo_verdict="land",
            facts={"source": "quadfit", "frontage_ft": 60.0, "geometry_tier": "B", "observed": {},
                   "quadfit": {"triage": "review", "binding_constraint": "slope", "policy_exclusion": None,
                               "parking_tier": "minimum", "stalls_provided": 4, "layout_method": "townhome_front"}},
            first_seen_run_id=run.id, updated_run_id=run.id, snapshot_id=snapshot.id,
        ),
    ]
    session.add_all(lots)
    await session.flush()
    a, b, c = lots

    answers = [
        (a, DESIGNS[0], _checks("green", tight=True)),
        (a, DESIGNS[1], _checks("yellow", head="fit_ft", seated=4, band="minimum", colour_reasons=["RELIEF_UNCONFIRMED"])),
        (b, DESIGNS[0], _checks("yellow", head="fit_ft", seated=4, band="minimum", colour_reasons=["RELIEF_UNCONFIRMED"])),
        (b, DESIGNS[1], _checks("yellow", head="coverage_pct", seated=4, band="minimum", colour_reasons=["RELIEF_UNCONFIRMED"])),
        (c, DESIGNS[0], _checks("unknown", colour_reasons=["FACT_UNOBSERVED"], unknown=["local_street"])),
        (c, DESIGNS[1], _checks("unknown", colour_reasons=["FACT_UNOBSERVED"], unknown=["local_street"])),
    ]
    for lot, key, checks in answers:
        session.add(
            FlatsLotResult(
                lot_id=lot.id, design_key=key, run_id=run.id, tier="unknown",
                slack_ft=checks["fit"]["slack_ft"], binding=checks["failing"], checks=checks,
            )
        )
    await session.commit()
    return run


async def _login(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    return user


# --- the list ------------------------------------------------------------


async def test_the_list_counts_lots_by_verdict_and_by_signed_colour(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    page = await client.get("/flats/lots")

    assert page.status_code == 200
    counts = page.text.split('id="lot-counts"', 1)[1].split('id="lot-table"', 1)[0]
    # The verdict is "unknown" on every lot: no rule is signed. That number is
    # printed first, and it is the whole population.
    assert "Verdict today" in counts
    assert "unknown 3" in counts
    # The colour the lots would take once signed: one of each, and the
    # "either design" rule gives lot A its green even though its second
    # design is yellow.
    assert counts.index("Verdict today") < counts.index("If signed as read")
    for words in ("green 1", "yellow 1", "unknown 1", "red 0"):
        assert words in " ".join(counts.split())
    for tlid in ("1S2E08BA  -09500", "1N1E29DD  -05600", "11E25AB  -00300"):
        assert tlid in page.text


async def test_a_colour_filter_keeps_the_counts_and_narrows_the_rows(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    page = await client.get("/flats/lots", params={"colour": "green"})

    assert page.status_code == 200
    table = page.text.split('id="lot-table"', 1)[1]
    assert "2833 SE 71ST AVE" in table
    assert "4110 NE 12TH AVE" not in table
    assert "10722 SE 32ND AVE" not in table
    # The counts above the table do not narrow with the colour: they are how
    # the filter is chosen, so they must still show the other colours.
    counts = " ".join(page.text.split('id="lot-counts"', 1)[1].split('id="lot-table"', 1)[0].split())
    assert "yellow 1" in counts


async def test_one_design_alone_is_not_the_better_of_two(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    page = await client.get("/flats/lots", params={"design": DESIGNS[1]})

    assert page.status_code == 200
    counts = " ".join(page.text.split('id="lot-counts"', 1)[1].split('id="lot-table"', 1)[0].split())
    # Under pod80 alone lot A is yellow, so there is no green lot at all.
    assert "green 0" in counts
    assert "yellow 2" in counts
    assert "unknown 1" in counts
    # And the per-design column shows only the design asked for.
    table = page.text.split('id="lot-table"', 1)[1].split("</table>", 1)[0]
    assert DESIGNS[1] in table
    assert DESIGNS[0] not in table


async def test_the_city_and_zone_filters_narrow_and_the_zones_are_offered(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    city = await client.get("/flats/lots", params={"jurisdiction": "or/clackamas/milwaukie"})
    zone = await client.get(
        "/flats/lots", params={"jurisdiction": "or/multnomah/portland", "zone": "R2.5"}
    )

    assert city.status_code == 200
    assert "10722 SE 32ND AVE" in city.text
    assert "2833 SE 71ST AVE" not in city.text.split('id="lot-table"', 1)[1]
    assert '<option value="R-7"' in city.text
    assert zone.status_code == 200
    table = zone.text.split('id="lot-table"', 1)[1]
    assert "4110 NE 12TH AVE" in table
    assert "2833 SE 71ST AVE" not in table


async def test_the_search_finds_a_lot_by_address_or_by_number(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    by_address = await client.get("/flats/lots", params={"q": "71st"})
    by_number = await client.get("/flats/lots", params={"q": "1N1E29DD"})

    assert "2833 SE 71ST AVE" in by_address.text.split('id="lot-table"', 1)[1]
    assert "4110 NE 12TH AVE" not in by_address.text.split('id="lot-table"', 1)[1]
    assert "4110 NE 12TH AVE" in by_number.text.split('id="lot-table"', 1)[1]


async def test_lots_is_not_swallowed_by_the_layer_route(
    client: AsyncClient, session: AsyncSession
):
    # /flats/{layer_id:path} matches "lots" happily and would 404 it as a
    # jurisdiction. Registration order is the only thing keeping this route.
    await _login(client, session)

    page = await client.get("/flats/lots")

    assert page.status_code == 200
    assert "No rule layer" not in page.text
    assert "No completed run has been loaded" in page.text


async def test_the_newest_run_is_the_default_and_an_older_one_is_reachable(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session, run_id=1, finished="2026-09-18T03:00:00+00:00")
    # A second run over the same lots, in which everything is red.
    copy = (await session.execute(select(FlatsSnapshot))).scalar_one()
    newer = FlatsRun(
        id=2, started_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 19, 7, tzinfo=timezone.utc), status="complete",
        code_version="abcdef01", rules_version="x", design_keys=list(DESIGNS), counties=["multnomah"],
        params={}, notes="", snapshot_id=copy.id,
    )
    session.add(newer)
    await session.flush()
    lots = (await session.execute(select(FlatsLot))).scalars().all()
    for lot in lots:
        for key in DESIGNS:
            session.add(FlatsLotResult(lot_id=lot.id, design_key=key, run_id=2, tier="unknown",
                                       binding=["min_lot_area_sqft"], checks=_checks("red", head="min_lot_area_sqft")))
    await session.commit()

    default = await client.get("/flats/lots")
    older = await client.get("/flats/lots", params={"run": 1})

    newest = " ".join(default.text.split('id="lot-counts"', 1)[1].split('id="lot-table"', 1)[0].split())
    assert "red 3" in newest
    assert "Run 2" in default.text
    first = " ".join(older.text.split('id="lot-counts"', 1)[1].split('id="lot-table"', 1)[0].split())
    assert "green 1" in first
    assert "Run 1" in older.text


# --- the county copy and its warning ----------------------------------------


def _banner(text: str, which: str) -> str:
    marker = f'id="county-copy-{which}"' if which != "footer" else 'id="county-copy"'
    if marker not in text:
        return ""
    return " ".join(text.split(marker, 1)[1].split("</div>", 1)[0].split())


async def test_a_fresh_checked_copy_shows_only_the_footer(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)
    taken = (_today() - timedelta(days=1)).isoformat()

    for url in ("/flats/lots", "/flats/lots/multnomah/1S2E08BA%20%20-09500"):
        page = await client.get(url)

        assert page.status_code == 200
        assert _banner(page.text, "red") == ""
        assert _banner(page.text, "amber") == ""
        footer = _banner(page.text, "footer")
        assert f"County map copy: RLIS 2026_08 + ArcGIS layers, taken {taken}" in footer
        assert f"sources checked {_today().isoformat()}" in footer


async def test_a_stale_copy_is_a_red_bar_on_both_pages(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    old = await _snapshot(session, taken=_today() - timedelta(days=200))
    await _seed(session, snapshot=old)

    for url in ("/flats/lots", "/flats/lots/multnomah/1S2E08BA%20%20-09500"):
        page = await client.get(url)

        assert page.status_code == 200
        red = _banner(page.text, "red")
        assert "200 days old" in red and "A refresh is due" in red
        assert 'data-code="stale"' in red
        # The lots are still shown: the warning is about the copy, not a gate on it.
        assert "2833 SE 71ST AVE" in page.text


async def test_a_source_that_moved_is_red_and_an_unanswered_one_is_amber(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session, checked=False)
    await _checked(
        session,
        findings=[
            {"key": "util_sewer_wood_village", "finding": "moved", "detail": "Invalid URL"},
            {"key": "zoning_portland", "finding": "unreachable", "detail": "ConnectError"},
        ],
    )
    await session.commit()

    page = await client.get("/flats/lots")

    red = _banner(page.text, "red")
    assert "util_sewer_wood_village" in red and "changed on its own side" in red
    amber = _banner(page.text, "amber")
    assert "zoning_portland" in amber and "did not answer" in amber


async def test_a_zone_code_nobody_ruled_on_is_named_in_amber_on_both_pages(
    client: AsyncClient, session: AsyncSession
):
    """Steph 2026-09-22: a code nobody has ruled on no longer holds the refresh
    back, so the banner is what keeps it from going unseen. It names the code,
    the city and the lots waiting, and the county is shown as usual."""
    await _login(client, session)
    snap = await _snapshot(session, new_zones={"or/multnomah/gresham": {"CX": 312}})
    await _seed(session, snapshot=snap)

    for url in ("/flats/lots", "/flats/lots/multnomah/1S2E08BA%20%20-09500"):
        page = await client.get(url)

        assert page.status_code == 200
        amber = _banner(page.text, "amber")
        assert 'data-code="unruled_zones"' in amber
        assert "CX in Gresham (312 lots)" in amber and "never green, never red" in amber
        assert _banner(page.text, "red") == ""
    assert "2833 SE 71ST AVE" in (await client.get("/flats/lots")).text, "the rest of the county is shown"


async def test_no_copy_recorded_is_said_in_red(client: AsyncClient, session: AsyncSession):
    await _login(client, session)

    page = await client.get("/flats/lots")

    assert page.status_code == 200
    assert "No county map copy has been recorded" in _banner(page.text, "red")
    assert "County map copy: none recorded." in _banner(page.text, "footer")


async def test_a_candidate_run_is_hidden_by_default_and_reachable_by_run(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session, run_id=1)
    # A refreshed copy, registered three weeks ago and still waiting: its own
    # lot rows under the same numbers, one address corrected, screened by a
    # candidate run.
    fresh = await _snapshot(
        session,
        taken=_today(),
        status="candidate",
        registered=datetime.now(timezone.utc) - timedelta(days=21),
    )
    candidate = FlatsRun(
        id=3, started_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 20, 7, tzinfo=timezone.utc), status="candidate",
        code_version="abcdef01", rules_version="x", design_keys=list(DESIGNS), counties=["multnomah"],
        params={"counts": {"lots": 1}}, notes="", snapshot_id=fresh.id,
    )
    session.add(candidate)
    await session.flush()
    moved = FlatsLot(
        tlid="1S2E08BA  -09500", county="multnomah", jurisdiction="or/multnomah/portland",
        zone_raw="R5", zone="R5", site_address="2833 SE 71ST AVE (RENUMBERED)", area_sqft=13973,
        geom=_box(7_650_000, 680_000, 89, 157), centroid="SRID=4326;POINT(-122.5903 45.5019)",
        condo_verdict="land", facts={"source": "snapshot"}, first_seen_run_id=1, updated_run_id=3,
        snapshot_id=fresh.id,
    )
    session.add(moved)
    await session.flush()
    session.add(FlatsLotResult(lot_id=moved.id, design_key=DESIGNS[0], run_id=3, tier="unknown",
                               binding=[], checks=_checks("red", head="min_lot_area_sqft")))
    await session.commit()

    default = await client.get("/flats/lots")
    asked = await client.get("/flats/lots", params={"run": 3})
    lot_default = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")
    lot_asked = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500", params={"run": 3})

    # The default is the newest complete run, not the newest run.
    assert "Run 1" in default.text and "(RENUMBERED)" not in default.text
    assert 'href="/flats/lots?run=3">3 (2026-09-20 07:00 UTC) candidate</a>' in " ".join(default.text.split())
    # Asked for, the candidate is shown and says what it is.
    assert "Run 3" in asked.text and "waiting for review" in asked.text
    assert "(RENUMBERED)" in asked.text
    # The lot page reads the row of the copy the chosen run screened.
    assert "(RENUMBERED)" not in lot_default.text
    assert "(RENUMBERED)" in lot_asked.text
    # And the banner says a refreshed copy has been waiting.
    amber = _banner(default.text, "amber")
    assert "waiting for review for 21 days" in amber


# --- one lot ---------------------------------------------------------------


async def test_the_lot_page_puts_the_verdict_first_and_the_colour_beside_it(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    page = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")

    assert page.status_code == 200
    assert "2833 SE 71ST AVE" in page.text
    head = page.text.split('id="lot-verdict"', 1)[1].split("</div>", 1)[0]
    # The verdict, in words a person can act on, before the colour.
    assert "Verdict today" in head
    assert "unknown" in head
    assert "not signed" in head
    body = page.text.split('id="lot-verdict"', 1)[1]
    assert body.index("Verdict today") < body.index("If signed as read")
    # Both designs, each with its own verdict / colour pair, and the stalls
    # reported beside the colour rather than folded into it.
    assert 'id="design-pod56x36-2"' in page.text
    assert 'id="design-pod80x25-2"' in page.text
    pod80 = page.text.split('id="design-pod80x25-2"', 1)[1].split('class="card"', 1)[0]
    assert "yellow" in pod80
    assert "4 cars charged, 4 seated" in pod80
    assert "fit_ft" in pod80
    assert "the exception it would ask for has not been read" in pod80
    pod56 = page.text.split('id="design-pod56x36-2"', 1)[1].split('id="design-pod80x25-2"', 1)[0]
    assert "green" in pod56
    assert "4 cars charged, 8 seated" in pod56
    assert "a rule this rests on has not been signed" in pod56


async def test_a_tight_fit_is_flagged_on_the_list_and_explained_on_the_lot_page(
    client: AsyncClient, session: AsyncSession
):
    # Steph 2026-09-25: a fit within 6 inches either way is green, with a
    # flag the acquisition review sees. Lot A's pod56x36 is one; its pod80x25
    # and every other answer are not.
    await _login(client, session)
    await _seed(session)

    listed = await client.get("/flats/lots?colour=green")
    row = listed.text.split("1S2E08BA  -09500", 1)[1].split("</tr>", 1)[0]
    assert row.count("tight fit") >= 1
    assert "tight fit" not in (await client.get("/flats/lots?colour=unknown")).text.split('id="lot-table"', 1)[1]

    page = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")
    assert 'id="tight-pod56x36-2"' in page.text
    assert 'id="tight-pod80x25-2"' not in page.text
    tight = page.text.split('id="tight-pod56x36-2"', 1)[1].split("</tr>", 1)[0]
    assert "6 inches or less" in tight and "survey" in tight

    # "Only tight fits" narrows the list, the counts with it, and survives
    # the colour buttons; one design alone is asked of that design.
    only = await client.get("/flats/lots?tight=1")
    table = only.text.split('id="lot-table"', 1)[1]
    assert "1S2E08BA  -09500" in table
    assert "1N1E29DD  -05600" not in table and "11E25AB  -00300" not in table
    assert "green 1" in " ".join(only.text.split('id="lot-counts"', 1)[1].split('id="lot-table"', 1)[0].split())
    assert re.search(r"tight=1(&amp;|&)colour=green", only.text)
    other = await client.get("/flats/lots?tight=1&design=pod80x25@2")
    assert "1S2E08BA  -09500" not in other.text.split('id="lot-table"', 1)[1]


async def test_the_county_map_colour_sits_beside_ours_not_in_its_place(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    page = await client.get("/flats/lots/multnomah/1N1E29DD%20%20-05600")

    assert page.status_code == 200
    head = page.text.split('id="lot-verdict"', 1)[1].split('class="card"', 1)[0]
    assert "County map says" in head
    assert "siteplan_no_layout" in head
    # Ours is yellow; the county map's red is shown as the county map's,
    # after ours, and does not change ours.
    assert head.index("If signed as read") < head.index("County map says")
    ours = head.split("If signed as read", 1)[1].split("County map says", 1)[0]
    assert "yellow" in ours
    assert "red" not in ours


async def test_the_lot_page_lists_the_facts_the_screen_read(
    client: AsyncClient, session: AsyncSession
):
    await _login(client, session)
    await _seed(session)

    page = await client.get("/flats/lots/multnomah/1N1E29DD%20%20-05600")

    facts = page.text.split('id="lot-facts"', 1)[1]
    assert "Frontage" in facts and "50 ft" in facts
    assert "Alley at the rear" in facts
    assert "Alley width" in facts and "20 ft" in facts
    # The outline is drawn from the geometry, and sized.
    assert "<polygon" in page.text
    assert "50 ft east–west" in page.text
    assert "100 ft north–south" in page.text
    # And the fact the seeded lot lacks is left out, not printed as None.
    assert "None" not in facts


async def test_a_lot_the_map_holds_but_nobody_measured_says_why_and_shows_the_roll(
    client: AsyncClient, session: AsyncSession
):
    """A snapshot-fed run carries every lot; one quadfit skipped is ``unknown``
    with the county copy's reason, its roll values shown, and no check or fit
    claimed that was never run."""
    await _login(client, session)
    run = await _seed(session)
    lot = FlatsLot(
        tlid="1S2E08BA  -09600", county="multnomah", jurisdiction="or/multnomah/portland",
        zone_raw="R5", zone="R5", site_address="2841 SE 71ST AVE", area_sqft=800,
        geom=_box(7_650_100, 680_000, 20, 40), centroid="SRID=4326;POINT(-122.5901 45.5019)",
        condo_verdict="suspect",
        facts={
            "source": "snapshot",
            "unmeasured": {"reason": "NOT_MEASURED", "quadfit_step": "sliver_area"},
            "juris_city": "PO", "split_zone": False, "zone_frac": 1.0, "inside_ugb": True,
            "stack_count": 1, "part_count": 1, "observed": {},
            "assessor": {"land_value": 250000.0, "building_value": 180000.0, "total_value": 430000.0,
                         "assessed_value": 310500.0, "year_built": 1948, "building_sqft": 1250.0,
                         "sale_date": "20210615", "sale_price": 415000.0, "prop_code": "101",
                         "state_class": "101", "land_use": "SFR"},
            "condo": {"verdict": "suspect", "reason": "stacked"},
            "snapshot_zone": {"raw": "R5", "zone": "R5", "gate": None},
        },
        first_seen_run_id=run.id, updated_run_id=run.id, snapshot_id=run.snapshot_id,
    )
    session.add(lot)
    await session.flush()
    for key in DESIGNS:
        session.add(
            FlatsLotResult(
                lot_id=lot.id, design_key=key, run_id=run.id, tier="unknown", slack_ft=None, binding=[],
                checks={"verdict": "unknown", "if_signed": "unknown",
                        "reasons": ["NOT_MEASURED", "quadfit:sliver_area"],
                        "if_signed_reasons": ["NOT_MEASURED", "quadfit:sliver_area"],
                        "head": None, "failing": [], "unchecked": [], "ask": None, "rule_verdict": None,
                        "screened": False, "fits": False,
                        "fit": {"slack_ft": None, "best_depth_ft": None, "required_ft": None, "across_ft": None,
                                "angle_deg": None, "orientation": None},
                        "stalls": {"charged": None, "seated": None, "band": None},
                        "leaning": {"assumed": [], "unknown": []}, "search": {"angles": None, "step_deg": None}},
            )
        )
    await session.commit()

    page = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09600")

    assert page.status_code == 200
    body = page.text.split('id="lot-verdict"', 1)[1]
    # (the apostrophe in "map's" is HTML-escaped; assert past it)
    assert "measurement never reached this lot" in body
    assert "measurement skipped it: under 1,000 sq ft" in body
    assert 'id="not-screened-pod56x36-2"' in body and "Not screened" in body
    assert "none failing" not in body and "does not fit" not in body and "cars charged" not in body
    facts = page.text.split('id="lot-facts"', 1)[1]
    assert "Not measured" in facts
    assert "Assessed value" in facts and "$310,500" in facts
    assert "$250,000 / $180,000 / $430,000" in facts
    assert "Year built" in facts and "1948" in facts
    assert "1,250 sf" in facts
    assert "$415,000 on 2021-06-15" in facts
    assert "suspect (stacked)" in facts
    assert "SFR" in facts
    assert "None" not in facts
    assert "Facts read from snapshot" in page.text
    # The list page carries it too, as unknown, without a fit it never had.
    listing = await client.get("/flats/lots?q=2841")
    assert "2841 SE 71ST AVE" in listing.text


async def test_a_lot_in_a_city_no_layer_holds_names_the_city_and_says_why(
    client: AsyncClient, session: AsyncSession
):
    """Canby is on the Clackamas roll and in no layer the rules hold. The
    loader keeps the map's city name as ``juris_city:canby`` (the column is
    never blank); the page reads it as the city, marked as unencoded, and
    the reason the lot has no verdict is the county copy's."""
    await _login(client, session)
    run = await _seed(session)
    lot = FlatsLot(
        tlid="24E01  03900", county="clackamas", jurisdiction="juris_city:canby",
        zone_raw=None, zone=None, site_address="14450 BAUMBACK RD", area_sqft=138687.7,
        geom=_box(7_660_000, 600_000, 300, 462), centroid="SRID=4326;POINT(-122.6919 45.2705)",
        condo_verdict="land",
        facts={
            "source": "snapshot",
            "unmeasured": {"reason": "JURISDICTION_NOT_ENCODED", "quadfit_step": None},
            "juris_city": "CANBY", "split_zone": False, "zone_frac": None, "inside_ugb": False,
            "stack_count": 1, "part_count": 1, "observed": {},
            "condo": {"verdict": "land", "reason": None},
            "snapshot_zone": {"raw": None, "zone": None, "gate": "JURISDICTION_NOT_ENCODED"},
        },
        first_seen_run_id=run.id, updated_run_id=run.id, snapshot_id=run.snapshot_id,
    )
    session.add(lot)
    await session.flush()
    for key in DESIGNS:
        session.add(
            FlatsLotResult(
                lot_id=lot.id, design_key=key, run_id=run.id, tier="unknown", slack_ft=None, binding=[],
                checks={"verdict": "unknown", "if_signed": "unknown",
                        "reasons": ["JURISDICTION_NOT_ENCODED"], "if_signed_reasons": ["JURISDICTION_NOT_ENCODED"],
                        "head": None, "failing": [], "unchecked": [], "ask": None, "rule_verdict": None,
                        "screened": False, "fits": False,
                        "fit": {"slack_ft": None, "best_depth_ft": None, "required_ft": None, "across_ft": None,
                                "angle_deg": None, "orientation": None},
                        "stalls": {"charged": None, "seated": None, "band": None},
                        "leaning": {"assumed": [], "unknown": []}, "search": {"angles": None, "step_deg": None}},
            )
        )
    await session.commit()

    page = await client.get("/flats/lots/clackamas/24E01%20%2003900")

    assert page.status_code == 200
    assert "Canby (no rules encoded)" in page.text
    assert "juris_city:canby" not in page.text.split("<body", 1)[1].replace("/flats/juris_city:canby", ""), "the prefix is the loader's, not the reader's"
    body = page.text.split('id="lot-verdict"', 1)[1]
    assert "Not screened" in body
    assert "None" not in page.text.split('id="lot-facts"', 1)[1]
    # The city link a lot header always carries reaches a page, not an error.
    city = await client.get("/flats/juris_city:canby")
    assert city.status_code < 500
    listing = await client.get("/flats/lots?q=BAUMBACK")
    assert "14450 BAUMBACK RD" in listing.text and "Canby (no rules encoded)" in listing.text


async def test_a_lot_nobody_loaded_says_so(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)

    page = await client.get("/flats/lots/multnomah/NOPE")

    assert page.status_code == 404
    assert "No lot called" in page.text


async def test_the_lot_pages_require_a_session(client: AsyncClient):
    for url in ("/flats/lots", "/flats/lots/multnomah/1S2E08BA%20%20-09500"):
        response = await client.get(url, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"].startswith("/login")


async def test_no_lot_page_prints_a_python_object(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)

    for url in ("/flats/lots", "/flats/lots/multnomah/1S2E08BA%20%20-09500"):
        page = await client.get(url)

        assert page.status_code == 200
        assert "built-in method" not in page.text
        assert "object at 0x" not in page.text


async def test_the_lot_page_shows_a_persons_decision_and_the_look_again_mark(
    client: AsyncClient, session: AsyncSession
):
    """A standing decision is printed under the verdict; one that promotion
    marked "look again" (the ground under it split, merged, or was rezoned)
    says so beside it; a superseded one is history and is not shown."""
    from app.models.flats import FlatsReviewDecision

    await _login(client, session)
    run = await _seed(session)
    snapshot_id = run.snapshot_id
    session.add_all(
        [
            FlatsReviewDecision(
                county="multnomah", tlid="1S2E08BA  -09500", design_key="", check_code="lot",
                verdict="green", reason="walked it; the alley is paved",
            ),
            FlatsReviewDecision(
                county="multnomah", tlid="1S2E08BA  -09500", design_key="pod80x25@2", check_code="fit_ft",
                verdict="red", reason="the neighbour's garage sits on the line",
                needs_rereview_snapshot_id=snapshot_id, needs_rereview_reason="split parent; zone R5 -> R2.5",
            ),
            FlatsReviewDecision(
                county="multnomah", tlid="1S2E08BA  -09500", design_key="", check_code="lot",
                verdict="red", reason="old and withdrawn", superseded_at=datetime.now(timezone.utc),
            ),
        ]
    )
    await session.commit()

    page = await client.get("/flats/lots/multnomah/1S2E08BA%20%20-09500")

    assert page.status_code == 200
    block = page.text.split('id="lot-decisions"', 1)[1].split('id="lot-facts"', 1)[0]
    assert "Decided by a person" in block
    assert "walked it; the alley is paved" in block
    assert "either design" in block
    assert "old and withdrawn" not in block
    # The marked decision says why it is in doubt, and the unmarked one does not.
    marked = block.split("the neighbour", 1)[1]
    assert "Look again:" in marked
    assert f"the county copy {snapshot_id} shows this ground split parent; zone R5 -&gt; R2.5" in marked
    assert block.count("Look again:") == 1
    # A lot with no decision shows no block at all.
    other = await client.get("/flats/lots/clackamas/11E25AB%20%20-00300")
    assert 'id="lot-decisions"' not in other.text
