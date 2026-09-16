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

import pytest
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.encode.port_quadfit import layer_id_for
from flats.geom.alley import (
    ALLEY_FACTS,
    alley_facts_from_quadfit,
    alley_lines,
    entailed,
    observed_alley,
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
    })
    path = tmp_path / "s4_lots.parquet"
    frame.to_parquet(path)
    got = alley_facts_from_quadfit(path)
    assert got["1N1E27AB  100"] == {"abuts_alley": True, "alley_at_rear": True, "alley_at_side": False}
    assert got["1N1E27AB  200"] == {"abuts_alley": True, "alley_at_rear": False, "alley_at_side": True}
    assert got["1N1E27AB  300"] == {"abuts_alley": False, "alley_at_rear": False, "alley_at_side": False}


# --- the registry ---------------------------------------------------------


def test_the_three_facts_are_registered_as_measured_site_facts() -> None:
    for name in ALLEY_FACTS:
        defn = CONDITIONS[name]
        assert defn.kind == "site_fact", name
        assert defn.assume is False, name
        assert "quadfit" in defn.evidence, name
    assert ENTAILS == {"alley_at_rear": ("abuts_alley",), "alley_at_side": ("abuts_alley",)}


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
