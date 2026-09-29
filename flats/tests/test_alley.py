"""The alley, named by the line it touches.

`abuts_alley` sat in the registry from the day Portland's garage waiver was
encoded until 2026-09-13 with nothing filling it. quadfit's s4 measures the
alley now (RLIS centreline within reach, 8 to 40 ft of alley across the
taxlot fabric on three of five rays) and records the edge as class ``A``;
:mod:`flats.geom.alley` reads that record and answers three facts, not one,
because the sentence the corpus holds is about a LINE: "No side, rear, or
garage entrance setback is required from a lot line abutting an alley."

What these tests hold to: the bridge names the line the way s4 and
:mod:`flats.geom.edges` name every other line (within 30 degrees of the
frontage is the rear, else a side); a per-line fact carries the lot-level
one and a parent answered False answers the children; no rear-setback
variant anywhere in the corpus is keyed to the lot-level fact; and the four
cities whose codes send the driveway to the alley say so in the corpus,
pinned to the site plan's own switch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.encode.port_quadfit import layer_id_for
from flats.geom.alley import (
    ALLEY_FACTS,
    alley_facts_from_quadfit,
    alley_lines,
    cover_stretches,
    entailed,
    observed_alley,
    rear_alley_along,
    rear_cover_runs,
    registry_alley,
    side_alley_along,
    usable_run_ft,
)
from flats.rules.conditions import CONDITIONS, ENTAILS, close_entailed
from flats.rules.resolver import RuleSet
from flats.score.configure import configure
from flats.score.screen import LotFacts

pytestmark = pytest.mark.unit

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


# A 50 x 100 interior lot, street along the south (y = 0), alley along the
# north (y = 100): the platted Portland shape. s4's record is
# [x1, y1, x2, y2, cls] per boundary segment, frontage bearings in degrees
# on [0, 180).
REAR_ALLEY = [
    [0, 0, 50, 0, "F"],
    [50, 0, 50, 100, "S"],
    [50, 100, 0, 100, "A"],
    [0, 100, 0, 0, "S"],
]
# The same lot with the alley down its east side instead.
SIDE_ALLEY = [
    [0, 0, 50, 0, "F"],
    [50, 0, 50, 100, "A"],
    [50, 100, 0, 100, "R"],
    [0, 100, 0, 0, "S"],
]
FRONT_EW = [0.0]


# --- naming the line -----------------------------------------------------


def test_an_alley_parallel_to_the_frontage_is_the_rear_line() -> None:
    assert alley_lines(REAR_ALLEY, FRONT_EW) == ("rear",)
    assert observed_alley(REAR_ALLEY, FRONT_EW) == {
        "abuts_alley": True, "alley_at_rear": True, "alley_at_side": False,
    }


def test_an_alley_across_the_frontage_is_a_side_line() -> None:
    assert alley_lines(SIDE_ALLEY, FRONT_EW) == ("side",)
    assert observed_alley(SIDE_ALLEY, FRONT_EW) == {
        "abuts_alley": True, "alley_at_rear": False, "alley_at_side": True,
    }


def test_the_thirty_degree_rule_is_the_one_every_other_line_gets() -> None:
    # A rear line skewed 29 degrees off the street is still the rear; 31 is
    # a side. Same tolerance as flats.geom.edges and quadfit's s4, so the
    # bridge never names an alley edge differently from its neighbours.
    import math

    def skewed(deg: float) -> list:
        dx, dy = 50 * math.cos(math.radians(deg)), 50 * math.sin(math.radians(deg))
        return [[0, 0, 50, 0, "F"], [0, 100, dx, 100 + dy, "A"]]

    assert alley_lines(skewed(29), FRONT_EW) == ("rear",)
    assert alley_lines(skewed(31), FRONT_EW) == ("side",)


def test_a_lot_with_no_alley_edge_answers_false_not_silence() -> None:
    # Every key present: the bridge asked the question and the answer is no,
    # which configure treats differently from a question nobody asked.
    plain = [[0, 0, 50, 0, "F"], [50, 0, 50, 100, "S"], [50, 100, 0, 100, "R"], [0, 100, 0, 0, "S"]]
    got = observed_alley(plain, FRONT_EW)
    assert set(got) == set(ALLEY_FACTS)
    assert not any(got.values())


def test_a_lot_between_two_alleys_holds_both_lines() -> None:
    both = [[0, 0, 50, 0, "F"], [50, 0, 50, 100, "A"], [50, 100, 0, 100, "A"], [0, 100, 0, 0, "S"]]
    assert alley_lines(both, FRONT_EW) == ("side", "rear")
    assert observed_alley(both, FRONT_EW) == {
        "abuts_alley": True, "alley_at_rear": True, "alley_at_side": True,
    }


def test_a_corner_lot_names_the_alley_against_either_frontage() -> None:
    # Two street directions: an alley parallel to EITHER is a rear line,
    # which is how s4 classes the non-alley edges of the same corner.
    corner = [[0, 0, 50, 0, "F"], [50, 0, 50, 100, "F"], [50, 100, 0, 100, "A"], [0, 100, 0, 0, "S"]]
    assert alley_lines(corner, [0.0, 90.0]) == ("rear",)
    corner_side = [[0, 0, 50, 0, "F"], [50, 0, 50, 100, "F"], [50, 100, 0, 100, "S"], [0, 100, 0, 0, "A"]]
    assert alley_lines(corner_side, [0.0, 90.0]) == ("rear",)


def test_the_bridge_reads_s4s_own_record(tmp_path) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    frame = pd.DataFrame({
        "TLID": ["1N1E27AB  100", "1N1E27AB  200", "1N1E27AB  300"],
        "edges_json": [json.dumps(REAR_ALLEY), json.dumps(SIDE_ALLEY),
                       json.dumps([[0, 0, 50, 0, "F"], [50, 0, 50, 100, "S"],
                                   [50, 100, 0, 100, "R"], [0, 100, 0, 0, "S"]])],
        "front_bearings_json": [json.dumps(FRONT_EW)] * 3,
        "jurisdiction": ["portland"] * 3,
        "alley_cover_json": [json.dumps([None, None, "1" * 10, None]),
                             json.dumps([None, "1" * 20, None, None]),
                             json.dumps([None] * 4)],
    })
    path = tmp_path / "s4_lots.parquet"
    frame.to_parquet(path)
    got = alley_facts_from_quadfit(path)
    assert got["1N1E27AB  100"] == {"abuts_alley": True, "alley_at_rear": True, "alley_at_side": False}
    assert got["1N1E27AB  200"] == {"abuts_alley": True, "alley_at_rear": False, "alley_at_side": True}
    assert got["1N1E27AB  300"] == {"abuts_alley": False, "alley_at_rear": False, "alley_at_side": False}
    # s4 before the cover column: nothing says the alley runs the rear line
    # (FOLLOWUPS 3(e)), so the rules get no rear alley line. The lot still
    # abuts one.
    old = tmp_path / "s4_old.parquet"
    frame.drop(columns=["alley_cover_json"]).to_parquet(old)
    assert alley_facts_from_quadfit(old)["1N1E27AB  100"] == {
        "abuts_alley": True, "alley_at_rear": False, "alley_at_side": False,
    }


# --- how much of the side line the alley runs ------------------------------
#
# FOLLOWUPS 3(c). s4 classes a line A when three of five rays find the
# alley, so a line can be A with the alley along 40% of it. The court the
# screen parks beside a side alley can sit anywhere along the side line
# (the fit is placed at any angle, not at a spot), so the screen parks
# there only when s4's cover says the alley runs the WHOLE line.
#
# 1N1E25DD -09400, NE Portland, s4's own record (EPSG:2913, feet): the
# alley behind the lot turns north about 8 ft short of the lot's NE corner, so
# the last two of twenty rays leave it. Its front bearings are two
# (a through lot), so the A line is named a side.
REAL_EDGES = [
    [7658563.26, 688589.09, 7658560.87, 688500.08, "R"],
    [7658560.87, 688500.08, 7658459.35, 688443.93, "F"],
    [7658459.35, 688443.93, 7658463.31, 688591.76, "F"],
    [7658463.31, 688591.76, 7658563.26, 688589.09, "A"],
]
REAL_FB = [88.47, 28.94]


def test_the_real_alley_that_turns_away_is_not_a_side_court_alley() -> None:
    assert alley_lines(REAL_EDGES, REAL_FB) == ("side",)
    assert observed_alley(REAL_EDGES, REAL_FB)["alley_at_side"] is True
    # s4's measured cover, west to east: the last two rays off the alley.
    assert side_alley_along(REAL_EDGES, REAL_FB, [None, None, None, "1" * 18 + "0" * 2]) is False
    # The same line with the alley along all of it parks the court there.
    assert side_alley_along(REAL_EDGES, REAL_FB, [None, None, None, "1" * 20]) is True


# 1S2E05AB -11900, Portland R5, at real coordinates (EPSG:2913; fixture
# Lot Analysis/quadfit/tests/fixtures/alley_stops_short_1S2E05AB_11900.json).
# The street is east; the 13 ft alley behind the lot is drawn only as far
# north as the lot's south-west corner, so the 88.7 ft rear line is A on
# three rays of five while ten of its eighteen cover rays, from the south,
# find the alley. Green on run 35 with the whole rear line as the court's
# aisle and the whole rear yard waived (FOLLOWUPS 3(d)/(e)).
STUB_EDGES = [
    [7667288.85, 682083.46, 7667286.58, 681994.75, "F"],
    [7667286.58, 681994.75, 7667186.62, 681997.77, "S"],
    [7667186.62, 681997.77, 7667188.88, 682086.49, "A"],
    [7667188.88, 682086.49, 7667288.85, 682083.46, "S"],
]
STUB_FB = [88.54]
STUB_COVER = [None, None, "1" * 10 + "0" * 8, None]


def test_the_real_rear_alley_that_stops_short_is_not_the_whole_rear_line() -> None:
    assert alley_lines(STUB_EDGES, STUB_FB) == ("rear",)
    # s4's three-of-five reading still puts the alley at the rear ...
    assert observed_alley(STUB_EDGES, STUB_FB)["alley_at_rear"] is True
    # ... but the alley runs only the southern half of the line.
    assert rear_alley_along(STUB_EDGES, STUB_FB, STUB_COVER) is False
    assert registry_alley(STUB_EDGES, STUB_FB, STUB_COVER)["alley_at_rear"] is False
    assert registry_alley(STUB_EDGES, STUB_FB, STUB_COVER)["abuts_alley"] is True
    # The same line with the alley along all of it keeps the waiver.
    whole = [None, None, "1" * 18, None]
    assert rear_alley_along(STUB_EDGES, STUB_FB, whole) is True
    assert registry_alley(STUB_EDGES, STUB_FB, whole)["alley_at_rear"] is True
    # Nothing on record is never the whole line.
    assert rear_alley_along(STUB_EDGES, STUB_FB, None) is False
    assert rear_alley_along(STUB_EDGES, STUB_FB, [None, None, "", None]) is False


def test_the_stretch_the_real_stub_covers_runs_from_the_south_corner() -> None:
    length = 88.73
    ((start, end),) = cover_stretches(length, STUB_COVER[2])
    assert start == 0.0
    # The tenth ray of eighteen, 2.5 ft in and evenly spaced: about 46.8 ft.
    assert end == pytest.approx(2.5 + (length - 5.0) * 9 / 17, abs=0.01)
    assert cover_stretches(length, "1" * 18) == ((0.0, length),)
    assert cover_stretches(length, "") == ()


def test_the_run_behind_the_real_stub_stops_at_the_side_yard_and_the_alleys_end() -> None:
    # Steph's ruling 2026-09-28: the stretch is the court's aisle only if it
    # is long enough, with the envelope behind it. The stub's 46.8 ft from
    # the south corner loses the 5 ft side yard at that corner: 41.8 ft.
    import shapely

    lot = shapely.Polygon([(e[0], e[1]) for e in STUB_EDGES])
    envelope = lot.buffer(-5, join_style="mitre")
    (line,) = rear_cover_runs(STUB_EDGES, STUB_FB, STUB_COVER)
    assert len(line) == 1
    stub_end = 2.5 + (88.73 - 5.0) * 9 / 17
    assert usable_run_ft((line,), lot, envelope, 5.0) == pytest.approx(stub_end - 5.0, abs=0.6)
    # The whole line: its length less both side yards.
    whole = rear_cover_runs(STUB_EDGES, STUB_FB, [None, None, "1" * 18, None])
    assert usable_run_ft(whole, lot, envelope, 5.0) == pytest.approx(88.73 - 10.0, abs=0.6)
    # Nothing on record, no envelope, or no lot: no run.
    assert rear_cover_runs(STUB_EDGES, STUB_FB, None) == ()
    assert usable_run_ft((line,), lot, None, 5.0) == 0.0
    assert usable_run_ft((line,), None, envelope, 5.0) == 0.0
    # A notch in the envelope behind the stretch breaks the run.
    notched = envelope.difference(shapely.box(7667180, 682015, 7667200, 682020))
    assert usable_run_ft((line,), lot, notched, 5.0) < stub_end - 5.0 - 10.0


def test_no_cover_measured_is_no_side_alley_court() -> None:
    whole = [None, None, None, "1" * 20]
    assert side_alley_along(REAL_EDGES, REAL_FB, None) is False
    assert side_alley_along(REAL_EDGES, REAL_FB, whole[:3]) is False  # wrong length
    assert side_alley_along(REAL_EDGES, REAL_FB, [None, None, None, None]) is False
    assert side_alley_along(REAL_EDGES, REAL_FB, [None, None, None, ""]) is False


def test_a_rear_alley_is_not_a_side_one_however_well_covered() -> None:
    assert side_alley_along(REAR_ALLEY, FRONT_EW, [None, None, "1" * 20, None]) is False
    assert side_alley_along(SIDE_ALLEY, FRONT_EW, [None, "1" * 20, None, None]) is True


def test_a_side_line_half_street_half_alley_is_not_on_the_alley() -> None:
    # The east line split in two collinear pieces: the south half S, the
    # north half A. Whole cover on the A half is still half the line.
    split = [
        [0, 0, 50, 0, "F"],
        [50, 0, 50, 50, "S"],
        [50, 50, 50, 100, "A"],
        [50, 100, 0, 100, "R"],
        [0, 100, 0, 0, "S"],
    ]
    assert side_alley_along(split, FRONT_EW, [None, None, "1" * 10, None, None]) is False
    # Two A pieces on one line, both whole: the line is on the alley.
    both = [e[:4] + ["A"] if i in (1, 2) else e for i, e in enumerate(split)]
    assert side_alley_along(both, FRONT_EW, [None, "1" * 10, "1" * 10, None, None]) is True
    assert side_alley_along(both, FRONT_EW, [None, "1" * 10, "1" * 9 + "0", None, None]) is False


def test_a_bend_in_the_side_starts_a_new_line() -> None:
    # A wedge: frontage south, then a side leg S running north-east, then an
    # A leg bending 45 degrees back north-west to the rear point. The legs
    # are two lines, and the A leg covered end to end is a side alley on
    # its own.
    wedge = [
        [0, 0, 60, 0, "F"],
        [60, 0, 80, 50, "S"],
        [80, 50, 40, 100, "A"],
        [40, 100, 0, 0, "S"],
    ]
    assert alley_lines(wedge, FRONT_EW) == ("side",)
    assert side_alley_along(wedge, FRONT_EW, [None, None, "1" * 13, None]) is True


# --- the registry ---------------------------------------------------------


def test_the_three_facts_are_registered_as_measured_site_facts() -> None:
    for name in ALLEY_FACTS:
        defn = CONDITIONS[name]
        assert defn.kind == "site_fact", name
        assert defn.assume is False, name
        assert "quadfit" in defn.evidence, name
    assert {k: v for k, v in ENTAILS.items() if k in ALLEY_FACTS} == {
        "alley_at_rear": ("abuts_alley",),
        "alley_at_side": ("abuts_alley",),
    }


def test_a_line_fact_carries_the_lot_fact() -> None:
    assert close_entailed({"alley_at_rear": True}) == {"alley_at_rear": True, "abuts_alley": True}
    assert entailed({"alley_at_side": True}) == {"alley_at_side": True, "abuts_alley": True}


def test_no_alley_on_the_lot_answers_both_lines() -> None:
    assert close_entailed({"abuts_alley": False}) == {
        "abuts_alley": False, "alley_at_rear": False, "alley_at_side": False,
    }


def test_a_line_fact_true_against_the_lot_fact_false_is_refused() -> None:
    with pytest.raises(ValueError, match="alley_at_rear observed True but abuts_alley"):
        close_entailed({"abuts_alley": False, "alley_at_rear": True})


def test_a_stated_child_is_not_overwritten_by_the_parent() -> None:
    # abuts_alley False with alley_at_side already False: nothing to add,
    # nothing to argue with.
    assert close_entailed({"abuts_alley": False, "alley_at_side": False}) == {
        "abuts_alley": False, "alley_at_side": False, "alley_at_rear": False,
    }


# --- configure --------------------------------------------------------------


def test_configure_holds_the_parent_when_a_line_is_observed() -> None:
    got = configure(LotFacts(lot_sqft=5000), pod(), observed={"alley_at_rear": True})
    assert {"alley_at_rear", "abuts_alley"} <= set(got.conditions)
    assert "alley_at_side" not in got.conditions
    # abuts_alley was answered by entailment, not assumed
    assert "abuts_alley" not in got.assumed
    assert "alley_at_rear" not in got.assumed
    # the other line was never observed and falls to the registry's False
    assert "alley_at_side" in got.assumed


def test_configure_settles_both_lines_from_a_lot_observed_without_an_alley() -> None:
    got = configure(LotFacts(lot_sqft=5000), pod(), observed={"abuts_alley": False})
    assert not {"abuts_alley", "alley_at_rear", "alley_at_side"} & set(got.conditions)
    assert not {"abuts_alley", "alley_at_rear", "alley_at_side"} & set(got.assumed)


def test_configure_refuses_a_contradiction() -> None:
    with pytest.raises(ValueError, match="holding alley_at_side is holding abuts_alley"):
        configure(LotFacts(lot_sqft=5000), pod(),
                  observed={"abuts_alley": False, "alley_at_side": True})


def test_the_bridge_output_configures_without_a_single_assumption_about_alleys() -> None:
    got = configure(LotFacts(lot_sqft=5000), pod(), observed=observed_alley(REAR_ALLEY, FRONT_EW))
    assert not set(ALLEY_FACTS) & set(got.assumed)
    assert got.leans_on(ALLEY_FACTS) == ()


# --- the corpus -------------------------------------------------------------


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).layers


def test_no_rear_setback_anywhere_is_switched_by_the_lot_level_fact(layers) -> None:
    """The pattern lock. A rear waiver keyed to `abuts_alley` opens the rear
    yard of a lot whose alley is beside it; the line fact is the only key a
    rear variant may take. 28 variants were re-keyed on 2026-09-13 (Gresham
    22, Troutdale 5, Fairview 1) and 19 exemptions added (Portland 14 across
    12 zones, the county 5)."""
    keyed_to_lot: list[str] = []
    keyed_to_line = 0
    for lid, layer in layers.items():
        for zname, zone in layer.zones.items():
            held = zone.values.get("setback_rear_ft")
            if held is None:
                continue
            for v in held.variants:
                if "abuts_alley" in (v.when or ()):
                    keyed_to_lot.append(f"{lid}/{zname}")
                if "alley_at_rear" in (v.when or ()):
                    keyed_to_line += 1
    assert keyed_to_lot == []
    assert keyed_to_line == 28 + 19


def test_the_side_half_lives_on_the_line_not_on_the_shared_number(layers) -> None:
    """`setback_side_ft` is one number for both side lines, so a waiver on
    it switched by `alley_at_side` would open the far side yard: the
    false-GREEN direction, and the reason the side half was refused from
    2026-09-13 to 2026-09-15. It is held now on `setback_alley_side_ft`,
    the side setback on the one line abutting the alley, and the envelope
    reads that for the alley edge alone. So: nothing anywhere keys a
    variant to `alley_at_side` -- the per-line field needs no switch -- and
    every zone that holds the garage half of Portland's sentence holds the
    side half as an exemption on the per-line field, quoting the sentence."""
    held_on_the_line: set[tuple[str, str]] = set()
    for lid, layer in layers.items():
        for zname, zone in layer.zones.items():
            for fname, held in zone.values.items():
                for v in held.variants:
                    assert "alley_at_side" not in (v.when or ()), (lid, zname, fname)
            side_line = zone.values.get("setback_alley_side_ft")
            if side_line is not None:
                assert side_line.exempt and side_line.value is None, (lid, zname)
                assert "abutting an" in side_line.prov.quote or any(
                    tag in side_line.prov.quote for tag in ("#L746", "#L1053")
                ), (lid, zname, side_line.prov.quote)
                held_on_the_line.add((lid, zname))
            # The garage half is Portland's sentence only in the two layers
            # that quote 33.110 / 33.120; Oregon City's alley garage row is a
            # different code with no side clause.
            garage = zone.values.get("setback_garage_entrance_ft")
            if lid.startswith("or/multnomah/") and garage is not None and any(
                "abuts_alley" in (v.when or ()) for v in garage.variants
            ):
                assert side_line is not None, (lid, zname, "garage half without the side half")
    # Twelve Portland zones and the county's five Portland-administered ones.
    assert len(held_on_the_line) == 17, sorted(held_on_the_line)
    assert {lid for lid, _ in held_on_the_line} == {
        "or/multnomah/portland", "or/multnomah/_unincorporated",
    }


def test_the_side_waiver_resolves_on_the_lot_and_leaves_the_far_yard(layers) -> None:
    """On a Portland R5 lot with the alley down its side, the resolver hands
    the screen an exempted `setback_alley_side_ft` and the full 5 ft
    `setback_side_ft` -- the far yard is untouched -- and the rear waiver
    does not fire, because `alley_at_side` is not `alley_at_rear`."""
    ruleset = RuleSet(layers)
    got = ruleset.resolve(
        "or/multnomah/portland", "R5",
        conditions={"alley_at_side", "abuts_alley", "multi_story"},
    )
    assert "setback_alley_side_ft" in got.exempted
    assert got.get("setback_side_ft") == 5
    assert got.get("setback_rear_ft") == 5
    # ... and with no alley at all the per-line field is exempt still -- the
    # field is only ever read for an edge that IS the alley line, so a
    # lot-level resolution of it says nothing about a lot without one.
    plain = ruleset.resolve("or/multnomah/portland", "R5", conditions={"multi_story"})
    assert plain.get("setback_side_ft") == 5


def test_portlands_rear_waiver_reaches_every_zone_with_the_garage_one(layers) -> None:
    """33.110.220.D.9 and 33.120.220.B.3.g waive the rear setback from a lot
    line abutting an alley in the same breath as the garage entrance. Every
    Portland and county zone holding the garage exemption holds the rear one,
    and the rear one is on the line, not the lot."""
    for lid in ("or/multnomah/portland", "or/multnomah/_unincorporated"):
        for zname, zone in layers[lid].zones.items():
            garage = zone.values.get("setback_garage_entrance_ft")
            if garage is None or not any("abuts_alley" in (v.when or ()) for v in garage.variants):
                continue
            rear = zone.values["setback_rear_ft"]
            waived = [v for v in rear.variants if "alley_at_rear" in (v.when or ())]
            assert waived and all(v.exempt for v in waived), (lid, zname)
            # and resolving with the bridge's own answer reaches it
            eff = rear.under({"alley_at_rear", "abuts_alley", "multi_story"})
            assert eff.exempt, (lid, zname)
            # ... while a side alley does not
            assert not rear.under({"alley_at_side", "abuts_alley", "multi_story"}).exempt, (lid, zname)


def test_rm3_and_rm4_do_not_tie_on_a_low_rise_alley_lot(layers) -> None:
    # Both zones already carry a `low_rise` variant on the rear setback; the
    # waiver is spelled out against it so the two do not tie at equal depth.
    for zname in ("RM3", "RM4"):
        rear = layers["or/multnomah/portland"].zones[zname].values["setback_rear_ft"]
        eff = rear.under({"low_rise", "alley_at_rear", "abuts_alley", "multi_story"})
        assert eff.exempt and not eff.ambiguous, zname


def test_four_cities_send_the_driveway_to_the_alley_in_the_corpus(layers) -> None:
    """The sentence quadfit's site plan has drawn from since 2026-09-12 is a
    value in the corpus now, in the same four cities, and nowhere else."""
    rules = RuleSet(layers)
    says_true = set()
    for lid, layer in layers.items():
        held = layer.defaults.get("parking_alley_access_required")
        if held is not None and held.value is True:
            says_true.add(lid)
    assert says_true == {
        layer_id_for("portland"), layer_id_for("gresham"),
        layer_id_for("wilsonville"), layer_id_for("west_linn"),
    }
    # Milwaukie's alley sentence places a stall; it does not route the drive.
    assert layers[layer_id_for("milwaukie")].defaults.get("parking_alley_access_required") is None
    # Every one carries its sentence.
    for lid in says_true:
        assert layers[lid].defaults["parking_alley_access_required"].prov.quote, lid
    # and the lot-level fact is the one the screen reads it under
    res = rules.resolve(layer_id_for("portland"), "R5", conditions=("abuts_alley", "multi_story"))
    assert res.values["parking_alley_access_required"].value is True


def _portland_doc(name: str) -> list[str]:
    root = Path(__file__).resolve().parents[1] / "provenance/docs/or/multnomah/portland"
    return (root / name).read_text(encoding="utf-8").splitlines()


def _yard(block, field: str):
    held = block.values.get(field)
    if held is None:
        return None
    return (
        held.exempt,
        held.value,
        sorted((v.exempt, str(v.value), tuple(sorted(v.when or ()))) for v in held.variants),
    )


def test_a_portland_side_alley_without_its_own_field_takes_the_one_number_the_code_sets() -> None:
    """FOLLOWUPS 12(c). Portland's commercial, employment and industrial
    chapters state no alley setback; an alley line there is "a lot line
    that is not a street lot line" and 33.130.215.B.2 sets it by the zone
    abutted -- the side/rear pair, one number. The screen cuts a side alley
    at max(side, rear), which is that number only while the two agree. So
    wherever a pod can be allowed and the field is absent, side and rear
    must resolve alike, variants and all; a zone that splits them needs
    the field (or a fresh reading) before the max() stands."""
    from flats.rules.loader import load_rules

    portland = load_rules()["or/multnomah/portland"]
    unheld, split = [], []
    for name, block in sorted(portland.zones.items()):
        if "setback_alley_side_ft" in block.values:
            continue
        use = block.values.get("quadplex_allowed")
        if use is None or (use.value is False and not use.variants):
            continue
        unheld.append(name)
        if _yard(block, "setback_side_ft") != _yard(block, "setback_rear_ft"):
            split.append(name)
    assert unheld, "the mechanism has no zone to hold"
    assert split == []


def test_the_portland_side_alley_ruling_quotes_lines_that_say_what_it_says() -> None:
    """The ruling rests on three readings: an alley is not a street, an
    alley line is not a street lot line, and the commercial chapter names
    the alley only in its step-down HEIGHT rule; EX, CI2/IR and OS never
    name it at all."""
    defs = _portland_doc("33.910.definitions.txt")
    assert "Street lot line does" in defs[765]
    assert "not include lot lines that abut an alley" in defs[766]
    assert "street does not include alleys" in defs[1374]
    c130 = _portland_doc("33.130.txt")
    assert "alley from" in c130[551] and "residential zone" in c130[551]
    assert sum("alley" in ln.lower() for ln in c130) == 2
    for chapter in ("33.140.txt", "33.150.txt", "33.100.txt"):
        assert not any("alley" in ln.lower() for ln in _portland_doc(chapter)), chapter
    yaml_text = (
        Path(__file__).resolve().parents[1] / "config/jurisdictions/or/multnomah/portland.yaml"
    ).read_text(encoding="utf-8")
    assert "33.910.definitions.txt#L766-L767" in yaml_text
    assert "33.130.txt#L552-L556" in yaml_text
