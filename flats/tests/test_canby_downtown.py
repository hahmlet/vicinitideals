"""Canby's Downtown Canby Overlay, Transitional Commercial sub-area
(FOLLOWUPS 109 chunk 5, 2026-10-29).

C-1 refuses housing except as part of a mixed-use development (CMC 16.22.010
A). The overlay's TC sub-area -- two block rows 16.41.020 A.2 names by their
streets -- permits a multi-family dwelling on the R-2 standards (16.41.030
A), with the overlay's own standards over them (16.41.050). The sub-area is
traced (``drawn_areas`` transitional_commercial) and answers
``inside_mapped_use_area`` for C-1 lots.

What is guarded:

* the use opens only inside the tracing, and only through the review the
  ORS 197A.400 ruling reads as clear-and-objective;
* the overlay's 0.4 minimum floor area ratio (Table 3) is measured: a lot
  the pod's 4,000 sq ft of floor satisfies passes, a larger one is a FAR-MIN
  flag at YELLOW -- never a bind, never GREEN;
* "built at the minimum setback" narrows the frontage share's band to the
  0 ft line.
"""

from __future__ import annotations

import json

import pytest
import shapely
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import observed_facts, share_band
from flats.rules import loader
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as fp
from flats.score.flags import Colour
from flats.score.screen import CLOSER_LOOK_MIN_FAR, CLOSER_LOOK_MIN_DENSITY, LotFacts
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_screen import DESIGN, NO_RELIEF, rules, run

pytestmark = pytest.mark.unit

CANBY = "or/clackamas/canby"
TRACING = "or/clackamas/canby/transitional-commercial.geojson"
INSIDE = ("inside_mapped_use_area", "judgement_review")


@pytest.fixture(scope="module")
def ruleset() -> RuleSet:
    return RuleSet(load_rules())


# --- the floor area floor -------------------------------------------------------

FLOOR = DESIGN.ground_sqft * DESIGN.stories


def test_a_lot_the_pods_floor_satisfies_carries_no_far_flag() -> None:
    small = LotFacts(lot_sqft=FLOOR / 0.4 - 100, frontage_ft=60, lot_width_ft=60)
    s = run(rules(min_far=0.4), lot=small, relief=NO_RELIEF)
    assert CLOSER_LOOK_MIN_FAR not in s.reasons
    assert "FAR-MIN" not in {f.code for f in s.flags}
    assert s.colour is Colour.green


def test_a_lot_too_big_for_the_pods_floor_is_yellow_never_a_bind() -> None:
    big = LotFacts(lot_sqft=FLOOR / 0.4 + 2000, frontage_ft=90, lot_width_ft=90)
    s = run(rules(min_far=0.4), lot=big, relief=NO_RELIEF)
    assert CLOSER_LOOK_MIN_FAR in s.reasons
    assert CLOSER_LOOK_MIN_DENSITY not in s.reasons
    assert s.binds == ()
    (f,) = [f for f in s.flags if f.code == "FAR-MIN"]
    assert f.bounds is not None and f.bounds[0] < 0.4 == f.bounds[1]
    assert fp.severity_of(f) >= fp.colour_rules().yellow_at_severity
    assert s.colour is Colour.yellow


def test_a_far_shortfall_beside_a_wall_is_red() -> None:
    big = LotFacts(lot_sqft=FLOOR / 0.4 + 2000, frontage_ft=90, lot_width_ft=90)
    s = run(rules(min_far=0.4, max_height_ft=20), lot=big, relief=NO_RELIEF)
    assert s.colour is Colour.red
    assert [b.check for b in s.binds] == ["height_ft"]


# --- the band ---------------------------------------------------------------------


def test_built_at_the_minimum_setback_narrows_the_band(ruleset: RuleSet) -> None:
    tc = ruleset.resolve(CANBY, "C-1", INSIDE)
    assert tc.get("setback_front_max_ft") == 15
    assert share_band(tc) == 0.0
    # Without the narrower band the maximum bounds it, as everywhere else.
    r2 = ruleset.resolve("or/washington/beaverton", "CM-HDR", ())
    if r2.get("setback_front_max_ft") is not None:
        assert share_band(r2) == float(r2.get("setback_front_max_ft"))


# --- the rule file ------------------------------------------------------------------


def test_c1_opens_only_inside_the_sub_area_and_through_the_review(ruleset: RuleSet) -> None:
    def allowed(conds) -> bool:
        return ruleset.resolve(CANBY, "C-1", conds).values["quadplex_allowed"].value

    assert allowed(INSIDE) is True
    assert allowed(()) is False
    assert allowed(("inside_mapped_use_area",)) is False
    assert allowed(("judgement_review",)) is False


def test_the_sub_area_reads_r2_and_the_overlay_with_nothing_missing(ruleset: RuleSet) -> None:
    tc = ruleset.resolve(CANBY, "C-1", INSIDE)
    assert tc.missing_required == ()
    assert tc.get("min_far") == 0.4
    assert tc.values["min_far"].measured_on is not None
    assert tc.get("min_density_du_per_acre") == 14
    assert tc.get("parking_front_prohibited") is True
    assert (tc.get("building_frontage_min_pct"), tc.get("building_frontage_other_pct")) == (60, 60)


def test_the_tracing_carries_its_drawn_provenance() -> None:
    data = json.loads((loader.AREAS_ROOT / TRACING).read_text(encoding="utf-8"))
    src = data["source"]
    assert src["drawn"] is True
    assert src["quote"] == "or/clackamas/canby/cmc.16.41.020.txt#L3,L11"
    assert len(data["features"]) == 2


def test_canby_declares_the_sub_area_for_c1() -> None:
    layer = load_rules()[CANBY]
    area = layer.drawn_areas["transitional_commercial"]
    assert (area.condition, area.file, area.zones) == ("inside_mapped_use_area", TRACING, ("C-1",))


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


@pytest.mark.parametrize("zone", ["C-1", "C1"])
def test_a_c1_lot_inside_a_node_is_inside_and_one_outside_is_not(layers, zone: str) -> None:
    area = load_area(TRACING)
    p = max(area.geoms, key=lambda g: g.area).representative_point()

    def facts(lot) -> dict:
        return observed_facts(row(jurisdiction="canby", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers)

    assert facts(p.buffer(5))["inside_mapped_use_area"] is True
    minx, miny, _, _ = area.bounds
    assert facts(box(minx - 3000, miny - 3000, minx - 2900, miny - 2900))["inside_mapped_use_area"] is False
