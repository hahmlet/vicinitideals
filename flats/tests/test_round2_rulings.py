"""Steph's rulings of 2026-10-14 on the round-2 false-GREEN sample.

Two of them change what the screen measures:

* **The review rule** (FOLLOWUPS 53/69/79): "if it's a clear and measurable
  standard, green. If it's otherwise clear and measurable, but there is a
  'may add conditions', yellow. If it's clear that everything is a one-off
  arbitrary decision, red." A zone whose path is a review that may add
  conditions, or that weighs judgement words beside measurable ones, carries
  ``review_discretion`` and raises REVIEW-CONDITIONS; Washington County's
  middle-housing Type I/Type II split is three gates read off the lot.
* **Any street frontage** (FOLLOWUPS 80(a)): "I read this as 'any' street
  frontage. So front, back, side streets if they exist." The half-the-
  frontage parking cap is measured on every street the lot has
  (:mod:`flats.fit.frontage`); a court behind the building on a lot with no
  street behind it is not reached.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
import shapely
from shapely.geometry import box

from flats.designs.model import load_catalog
from flats.fit.frontage import parking_share_pct, street_chains, street_shares
from flats.fit.rectangle import Fit
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.rules.loader import load_rules
from flats.rules.model import Provenance, Status
from flats.rules.resolver import Resolved, RuleSet, ZoneResolution
from flats.rules.resolver import Verdict as RuleVerdict
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import (
    CHECK_FIELD,
    CLOSER_LOOK_REVIEW_CONDITIONS,
    LotFacts,
    review_with_conditions,
    screen,
)
from flats.score.slack import Verdict

pytestmark = pytest.mark.unit

WHERE = "or/test/round2"
PROV = Provenance(
    cite="Test Code 1.1",
    url="https://example.invalid/code",
    retrieved=date(2026, 10, 14),
)
DESIGN = load_catalog().latest("pod56x36")

CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 60,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}


def rules(**overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R5",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=PROV,
                layer=WHERE,
                origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit() -> Fit:
    depth_ft = 36.0
    best = depth_ft + DESIGN.parking.court_depth_ft + 4.0
    return Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best,
        slack_ft=best - depth_ft,
        across_ft=max(56.0 + DESIGN.parking.lane_width_ft, DESIGN.court_width_ft),
    )


def run(lot: LotFacts, rule_set: ZoneResolution):
    return screen(
        rule_set,
        lot,
        DESIGN,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )


def facts(**over) -> LotFacts:
    return LotFacts(lot_sqft=over.pop("lot_sqft", 6000), frontage_ft=60, lot_width_ft=60, **over)


def check(result, name: str):
    return next((c for c in result.checks if c.check == name), None)


# --- the review rule --------------------------------------------------------


def test_a_review_that_may_add_conditions_is_yellow_and_names_why() -> None:
    plain = run(facts(), rules())
    assert plain.colour is Colour.green
    for how in ("conditions", "judgement"):
        got = run(facts(), rules(review_discretion=how))
        assert CLOSER_LOOK_REVIEW_CONDITIONS in got.reasons
        flag = next(f for f in got.flags if f.code == "REVIEW-CONDITIONS")
        assert how in flag.key
        assert got.colour is Colour.yellow
        assert not got.binds


def test_washington_type_i_is_green_inside_either_gate_and_yellow_outside() -> None:
    gates = {"type_i_max_buildable_sqft": 10000, "type_i_density_escape_du_per_acre": 12}
    # Within the buildable-area gate: Type I.
    assert review_with_conditions(rules(**gates), facts(lot_sqft=9000), DESIGN) is None
    # Past it, but four homes on 12,000 sq ft is 14.5 a net acre: Type I.
    assert review_with_conditions(rules(**gates), facts(lot_sqft=12000), DESIGN) is None
    # Past both: 4 homes on 20,000 sq ft is 8.7 an acre, under 12. Type II.
    assert review_with_conditions(rules(**gates), facts(lot_sqft=20000), DESIGN) == "buildable_area"
    # The Type I plat clause: a land division turns Type I into Type II.
    plat = {**gates, "type_i_standard_plat_required": True}
    assert review_with_conditions(rules(**plat), facts(lot_sqft=9000), DESIGN) == "standard_plat"
    # The unit-free reading of a zone with no gates at all: no review.
    assert review_with_conditions(rules(), facts(lot_sqft=20000), DESIGN) is None


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules())


def test_the_washington_gates_are_encoded_from_the_zone_chapters(corpus: RuleSet) -> None:
    w = "or/washington/_unincorporated"
    got = {z: corpus.resolve(w, z).values for z in ("R-5", "R-9", "R-9 NB", "R-15 NB", "NMU")}
    assert got["R-5"]["type_i_max_buildable_sqft"].value == 16500
    assert got["R-5"]["type_i_density_escape_du_per_acre"].value == 4
    assert got["R-9"]["type_i_standard_plat_required"].value is True
    assert got["R-9 NB"]["review_discretion"].value == "conditions"
    # R-15 NB inherits R-15 and overrides its plat clause: 390-10.2 K has none.
    assert got["R-15 NB"]["type_i_standard_plat_required"].value is False
    assert got["NMU"]["review_discretion"].value == "conditions"


@pytest.mark.parametrize(
    ("layer", "zone", "how"),
    [
        ("or/washington/hillsboro", "MR-2", "conditions"),
        ("or/clackamas/_unincorporated", "MR1", "judgement"),
        ("or/clackamas/sandy", "R-2", "conditions"),
    ],
)
def test_the_re_ruled_zones_admit_the_pod_with_the_review_flagged(
    corpus: RuleSet, layer: str, zone: str, how: str
) -> None:
    got = corpus.resolve(layer, zone).values
    assert got["quadplex_allowed"].value is True
    assert got["review_discretion"].value == how


@pytest.mark.parametrize("zone", ["R-1.5", "R-2", "C-R"])
def test_canbys_one_off_review_is_a_judgement_path(corpus: RuleSet, zone: str) -> None:
    # The Board's Type III review judges "compatible" and "the INTENT"; a
    # townhouse group is not the exempt "single family" (16.04.190: detached).
    # RED by the 2026-10-14 rule; since 2026-10-15 ORS 197A.400 reduces the
    # review to the clear and objective standards inside a UGB, so it is a
    # `judgement_review` path the screen clears there (GREEN with a flag).
    got = corpus.resolve("or/clackamas/canby", zone).values
    assert got["quadplex_allowed"].value is False
    assert "review_discretion" not in got
    assert any(v is True and "judgement_review" in when for when, v, _ in got["quadplex_allowed"].relief)
    opened = corpus.resolve("or/clackamas/canby", zone, ("judgement_review",)).values
    assert opened["quadplex_allowed"].value is True
    notes = corpus.layers["or/clackamas/canby"].zones[zone].notes
    assert notes.startswith("OPENED 2026-10-15 BY ORS 197A.400")
    assert "RED, RE-CHECKED 2026-10-14 under Steph's review rule" in notes


# --- any street frontage: the measure ---------------------------------------


def _edges(lines: list[tuple[float, float, float, float, EdgeClass]], bearings) -> LotEdges:
    edges = tuple(
        Edge(
            x1=x1, y1=y1, x2=x2, y2=y2,
            length_ft=float(shapely.LineString([(x1, y1), (x2, y2)]).length),
            bearing_deg=bearing_deg(x1, y1, x2, y2),
            cls=cls,
        )
        for x1, y1, x2, y2, cls in lines
    )
    return LotEdges(
        tier=Tier.corner if len(bearings) > 1 else Tier.clean,
        edges=edges,
        front_bearings=tuple(bearings),
        frontage_ft=sum(e.length_ft for e in edges if e.cls in (EdgeClass.front, EdgeClass.street_side)),
        convexity=1.0,
    )


F, S, R, SS = EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.street_side
LOT = box(0, 0, 80, 120)
#: The pod at the front (y from 20), its court behind it across 40 ft.
BUILDING = box(4, 20, 60, 56)
ROW = box(4, 60, 44, 102)


def test_one_street_is_one_chain_and_a_rear_court_faces_none_of_it() -> None:
    interior = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0])
    assert len(street_chains(interior)) == 1
    assert street_shares(LOT, interior, ROW, BUILDING) == (0.0,)


def test_a_through_lot_court_faces_the_far_street_across_its_width() -> None:
    # The far end as the street it is (a reading may have renamed it rear).
    through = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, F), (0, 120, 0, 0, S)], [0.0])
    assert len(street_chains(through)) == 2
    near, far = street_shares(LOT, through, ROW, BUILDING)
    assert near == 0.0
    assert far == pytest.approx(100.0 * 40 / 80, abs=2.0)


def test_a_corner_lot_court_faces_the_side_street_across_its_depth() -> None:
    corner = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, SS), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0, 90.0])
    assert len(street_chains(corner)) == 2
    # The row stands against the side street: x from 36 to 76.
    row = box(36, 60, 76, 102)
    front, side = street_shares(LOT, corner, row, BUILDING)
    assert front == 0.0
    assert side == pytest.approx(100.0 * 42 / 120, abs=2.0)
    # Hidden behind the building from the side street, it counts nothing.
    behind = box(4, 22, 40, 54)
    assert street_shares(LOT, corner, behind, BUILDING)[1] == 0.0


def test_a_street_that_wraps_past_the_ring_start_is_one_street() -> None:
    ring = _edges(
        [(40, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, R), (0, 120, 0, 0, S), (0, 0, 40, 0, F)],
        [0.0],
    )
    assert [len(c) for c in street_chains(ring)] == [2]


def test_a_street_that_bends_short_of_a_corner_is_one_street() -> None:
    # Two directions 30 degrees apart: one street bending (or a cul-de-sac
    # bulb), not two -- the corner test's angle decides, as it does for the
    # corner_lot fact.
    bend = _edges(
        [(0, 0, 40, 0, F), (40, 0, 80, 23, F), (80, 23, 80, 120, S), (80, 120, 0, 120, R), (0, 120, 0, 0, S)],
        [0.0, 30.0],
    )
    assert [len(c) for c in street_chains(bend)] == [2]


def test_a_jog_in_one_frontage_is_one_street() -> None:
    # Two runs of front line 10 ft apart across the street: a step in one
    # frontage, not a through lot's two ends (those are 120 ft apart above).
    jog = _edges(
        [(0, 0, 40, 0, F), (40, 0, 40, 10, S), (40, 10, 80, 10, F), (80, 10, 80, 120, S),
         (80, 120, 0, 120, R), (0, 120, 0, 0, S)],
        [0.0],
    )
    assert [len(c) for c in street_chains(jog)] == [2]


def test_the_best_way_to_stand_the_row_is_kept() -> None:
    corner = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, SS), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0, 90.0])
    away = box(4, 60, 44, 102)
    against = box(36, 60, 76, 102)
    assert parking_share_pct(LOT, corner, [against, away], BUILDING) == pytest.approx(
        min(max(street_shares(LOT, corner, r, BUILDING)) for r in (against, away))
    )
    assert parking_share_pct(LOT, corner, [], BUILDING) is None


# --- any street frontage: the check -----------------------------------------


CAP = {"parking_area_max_frontage_pct": 50, "parking_area_frontage_any_street": True}


def test_the_cap_binds_on_the_worst_street() -> None:
    assert CHECK_FIELD["parking_frontage_share"] == "parking_area_max_frontage_pct"
    over = run(facts(parking_frontage_share_pct=62.5), rules(**CAP))
    assert check(over, "parking_frontage_share").verdict is not Verdict.passes
    assert over.colour is Colour.red
    under = run(facts(parking_frontage_share_pct=35.0), rules(**CAP))
    assert check(under, "parking_frontage_share").verdict is Verdict.passes
    assert under.colour is Colour.green


def test_unmeasured_is_unrun_and_a_cap_on_the_front_alone_is_not_asked() -> None:
    got = run(facts(), rules(**CAP))
    assert check(got, "parking_frontage_share") is None
    assert "parking_frontage_share" in got.unchecked
    front_only = run(facts(parking_frontage_share_pct=90.0), rules(parking_area_max_frontage_pct=50))
    assert check(front_only, "parking_frontage_share") is None
    assert "parking_frontage_share" not in front_only.unchecked


@pytest.mark.parametrize(
    "layer",
    [
        "or/clackamas/wilsonville",
        "or/washington/hillsboro",
        "or/clackamas/_unincorporated",
    ],
)
def test_the_four_cities_read_the_cap_on_any_street(corpus: RuleSet, layer: str) -> None:
    zone = next(iter(corpus.layers[layer].zones))
    got = corpus.resolve(layer, zone).values
    assert got["parking_area_frontage_any_street"].value is True
    assert got["parking_area_max_frontage_pct"].value == 50


def test_beaverton_reads_it_where_s11_states_it_and_not_on_the_35_percent_line(corpus: RuleSet) -> None:
    layer = corpus.layers["or/washington/beaverton"]
    for zone in layer.zones:
        got = corpus.resolve("or/washington/beaverton", zone).values
        cap = got.get("parking_area_max_frontage_pct")
        any_street = got.get("parking_area_frontage_any_street")
        # The 35 percent line (60.05.15.6.C) is the driveway inside the
        # ten-foot strip, `driveway_max_frontage_pct` (FOLLOWUPS 84;
        # flats/tests/test_frontage_caps.py), not a parking cap.
        assert cap is None or cap.value != 35, zone
        if any_street is not None:
            assert cap is not None and cap.value == 50, zone


# --- any street frontage: the bridge ----------------------------------------

X0, Y0 = 7_650_000.0, 680_000.0


def test_the_bridge_measures_the_share_on_a_through_lot(corpus: RuleSet) -> None:
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.tests.test_fire import bridge_row

    depth = 200.0
    edges = [
        [X0, Y0, X0 + 70, Y0, "F"],
        [X0 + 70, Y0, X0 + 70, Y0 + depth, "S"],
        [X0 + 70, Y0 + depth, X0, Y0 + depth, "F"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    row = bridge_row(
        jurisdiction="hillsboro",
        zone="R-7",
        edges_json=json.dumps(edges),
        front_bearings_json="[0.0, 180.0]",
        frontage_ft=140.0,
        lot_width_ft=70.0,
        lot_depth_ft=depth,
        area_sqft=70 * depth,
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + 65, Y0 + depth - 10)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + 70, Y0 + depth)),
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(
        lot, [DESIGN], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy(), step_deg=30.0
    )
    share = s.facts.parking_frontage_share_pct
    assert share is not None and share > 0.0
    got = check(s.screening, "parking_frontage_share")
    assert got is not None and got.observed == pytest.approx(share)
