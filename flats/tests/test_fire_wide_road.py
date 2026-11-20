"""The fire route on a lot line that faces a wide road (rel10d move read,
2026-11-19).

quadfit s4 calls a lot line a street's across a right-of-way up to 150 ft
wide since 2026-11-18, and the plan is laid out fronting that line. The fire
route stands a truck only within 50 ft of a road's centre line
(:data:`flats.fit.fire.MAX_GAP_FT`), so on such a line no truck stood, the
hose was walked from the lot's other street, and 74 lots went YELLOW to RED.
The real lot here is Beaverton 1S126BC01501 on Scholls Ferry Rd, its centre
line 53.5 ft from the lot line.

The miss is not known to be one: where the route reaches with the truck on
the wide road, measured from that road's middle, the lot is held YELLOW with
FIRE-WIDE-ROAD -- never GREEN, and never from a line on a freeway, a ramp or
a railroad.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely import affinity  # noqa: E402

from flats.encode.load import load_trusted  # noqa: E402
from flats.fit import fire  # noqa: E402
from flats.ingest.quadfit import FIRE_WIDE_ROAD_REACH_FT, lot_from_row, screen_lot  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.screen import FACT_UNOBSERVED, Triage  # noqa: E402
from flats.score.slack import Verdict  # noqa: E402
from flats.tests.test_fire import check, facts, pod, run  # noqa: E402

FX = json.loads((Path(__file__).parent / "fixtures" / "fire_wide_road_lot.json").read_text(encoding="utf-8"))
OX, OY = FX["origin"]


def _world(wkt: str):
    return affinity.translate(shapely.from_wkt(wkt), OX, OY)


def _row(which: str, *, kinds: list[str | None] | None = None) -> dict[str, object]:
    """The lot as quadfit s4 cut it before (``base``) and after (``new``)
    the wide-road test."""
    cut = FX[which]
    edges = [[x1 + OX, y1 + OY, x2 + OX, y2 + OY, cls] for x1, y1, x2, y2, cls in cut["edges"]]
    return {
        "TLID": FX["tlid"],
        "jurisdiction": FX["jurisdiction"],
        "zone": FX["zone"],
        "tier": cut["tier"],
        "area_sqft": FX["area_sqft"],
        "frontage_ft": cut["frontage_ft"],
        "lot_width_ft": None,
        "lot_depth_ft": None,
        "edges_json": json.dumps(edges),
        "front_bearings_json": json.dumps(cut["fb"]),
        "street_kind_json": json.dumps(cut["kinds"] if kinds is None else kinds),
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(_world(FX["env"])),
        "lot_wkb": shapely.to_wkb(_world(FX["lot"])),
    }


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


@pytest.fixture(scope="module")
def roads():
    """The roads a truck can use near the lot: Scholls Ferry Rd, Hall Blvd
    and Washington Square Rd; never the Highway 217 ramp."""
    lines = [_world(wkt) for _, kind, _, wkt in FX["streets"] if kind in fire.TRUCK_TYPES]
    assert len(lines) == len(FX["streets"]) - 1
    return shapely.STRtree(lines), np.array(lines, dtype=object)


def _screened(corpus, policies, roads, which: str, **over):
    lot = lot_from_row(_row(which, **over), corpus.layers)
    (s,) = screen_lot(
        lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0, roads=roads
    )
    return s


def test_the_wide_road_line_is_past_the_reach_a_truck_is_stood_within(roads) -> None:
    """Scholls Ferry Rd's centre line runs 53.5 ft from the lot's long line:
    no truck on the reading the screen clears a lot on, one on the wide
    reading, its hose from the road's middle less the half road."""
    x1, y1, x2, y2, cls = FX["new"]["edges"][-1]
    assert cls == "F" and FX["base"]["edges"][-1][4] == "S"
    mid = np.array([[(x1 + x2) / 2 + OX, (y1 + y2) / 2 + OY]])
    assert not np.isfinite(fire.street_offsets(mid, *roads)).any()
    (wide,) = fire.street_offsets(mid, *roads, max_gap_ft=FIRE_WIDE_ROAD_REACH_FT)
    assert wide == pytest.approx(53.5 - fire.HALF_ROAD_FT, abs=0.5)
    strict = fire.point_offset(*roads, max_gap_ft=FIRE_WIDE_ROAD_REACH_FT)(mid)
    assert strict[0] == pytest.approx(53.5, abs=0.5)
    assert not np.isfinite(fire.point_offset(*roads)(mid)).any()


def test_the_lot_reached_the_building_before_the_wide_road_line_was_a_street_line(
    corpus, policies, roads
) -> None:
    s = _screened(corpus, policies, roads, "base")
    assert s.facts.fire_route_tried and s.facts.fire_route_ft <= 150.0
    assert s.facts.fire_route_wide_ft is None
    assert check(s.screening, "fire_access_ft").verdict is Verdict.passes


def test_a_plan_the_hose_misses_only_for_want_of_a_truck_on_the_wide_road_is_held(
    corpus, policies, roads
) -> None:
    """The plan fronting Scholls Ferry Rd: the hose from the lot's other
    street misses, the hose from Scholls Ferry reaches. Held, flagged, and
    neither RED on the fire route nor GREEN."""
    s = _screened(corpus, policies, roads, "new")
    assert s.facts.fire_route_tried and s.facts.fire_route_ft > 150.0
    assert s.facts.fire_route_wide_ft is not None and s.facts.fire_route_wide_ft <= 150.0
    for result in (s.screening, s.signed):
        assert check(result, "fire_access_ft") is None
        assert result.triage is not Triage.green
    # The colour the map shows (the zone's rules are unsigned, so today's
    # screen stops at RULE_UNVERIFIED before its reasons).
    assert FACT_UNOBSERVED in s.signed.reasons
    assert "FIRE-WIDE-ROAD" in {f.code for f in s.signed.flags}


@pytest.mark.parametrize("kind", ["freeway", "limited", "rail", "drive_off_lot", None])
def test_no_truck_is_stood_off_a_line_that_is_not_a_public_street(corpus, policies, roads, kind) -> None:
    """The same line facing a freeway, a ramp, a railroad or a drive: the
    wide reading is not taken, and the miss stands."""
    kinds = [*FX["new"]["kinds"][:-1], kind]
    s = _screened(corpus, policies, roads, "new", kinds=kinds)
    assert s.facts.fire_route_wide_ft is None
    if s.facts.fire_route_tried:
        assert s.facts.fire_route_ft is None or s.facts.fire_route_ft > 150.0
        assert "FIRE-WIDE-ROAD" not in {f.code for f in s.signed.flags}
    assert s.signed.triage is not Triage.green


def test_the_screen_holds_a_lot_reached_only_from_a_wide_road_yellow() -> None:
    result = run(facts(fire_route_ft=208.0, fire_route_tried=True, fire_route_wide_ft=130.0))
    assert check(result, "fire_access_ft") is None
    assert FACT_UNOBSERVED in result.reasons
    assert result.triage not in (Triage.green, Triage.red)
    codes = {f.code for f in result.flags}
    assert "FIRE-WIDE-ROAD" in codes
    # Missed from the wide road too: RED, as before.
    result = run(facts(fire_route_ft=208.0, fire_route_tried=True, fire_route_wide_ft=170.0))
    assert result.triage is Triage.red
    assert check(result, "fire_access_ft").verdict is Verdict.fails
    # Reached on the code's reading: the wide reading is never read.
    result = run(facts(fire_route_ft=120.0, fire_route_tried=True, fire_route_wide_ft=100.0))
    assert result.triage is Triage.green
    assert "FIRE-WIDE-ROAD" not in {f.code for f in result.flags}
    # A route never found, found from the wide road: still not a pass.
    result = run(facts(fire_route_ft=None, fire_route_tried=True, fire_route_wide_ft=120.0))
    assert result.triage not in (Triage.green, Triage.red)
    # The dead end's and the narrow street's questions come first.
    result = run(
        facts(fire_route_ft=208.0, fire_route_tried=True, fire_route_freed_ft=120.0, fire_route_wide_ft=110.0)
    )
    codes = {f.code for f in result.flags}
    assert "FIRE-DEAD-END" in codes and "FIRE-WIDE-ROAD" not in codes
