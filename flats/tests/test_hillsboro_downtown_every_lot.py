"""Hillsboro's downtown roof rule reaches every lot inside the traced line
(rel8 hold, FOLLOWUPS 193; Steph 2026-11-14, rulings.yaml
2026-11-14-hillsboro-downtown-roof-every-lot).

CDC 12.61.200 lists five zones in the Downtown Plan District, but 12.61.800
A.1 and B bind new residential construction "within the boundaries shown on
Figure 12.61.200-A", and the traced figure takes in R-7 and MR-1 ground the
zone list leaves out. Steph: the rule reaches every lot inside the line,
whatever its zoning. So an R-7 or MR-1 lot inside is RED on the flat roof,
one the line cuts stays off GREEN, one outside owes nothing; the SCR zones
read as before.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import observed_facts
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet, Verdict as RuleVerdict
from flats.score.configure import Configuration
from flats.score.flags import Colour
from flats.score.screen import FACT_UNOBSERVED
from flats.tests.test_crossref_round2 import _run
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_round2_rulings import facts

pytestmark = pytest.mark.unit

HILLSBORO = "or/washington/hillsboro"
FACT = "hillsboro_downtown_plan_district"
FLAG = "FACT-HILLSBORO-DOWNTOWN-PLAN-DISTRICT"
TRACE = "or/washington/hillsboro/downtown-plan-district.geojson"


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def _lots() -> dict[str, shapely.Geometry]:
    """A 100 ft square well inside the trace, one straddling its edge (about
    half inside), and one far outside."""
    area = load_area(TRACE)
    biggest = max(getattr(area, "geoms", [area]), key=lambda g: g.area)
    inside = biggest.representative_point()
    # Shrink until the square sits wholly inside.
    half = 50.0
    box_in = shapely.box(inside.x - half, inside.y - half, inside.x + half, inside.y + half)
    assert biggest.contains(box_in)
    # A point on the edge: the square around it is cut by the line.
    edge = biggest.exterior.interpolate(0.37, normalized=True)
    box_cut = shapely.box(edge.x - half, edge.y - half, edge.x + half, edge.y + half)
    minx, miny, _, _ = area.bounds
    box_out = shapely.box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    return {"inside": box_in, "cut": box_cut, "outside": box_out}


@pytest.mark.parametrize("zone", ["R-7", "MR-1"])
def test_the_trace_is_asked_of_r7_and_mr1_lots(layers, zone) -> None:
    lots = _lots()

    def asked(lot) -> dict:
        return observed_facts(row(jurisdiction="hillsboro", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers)

    assert asked(lots["inside"])[FACT] is True
    assert asked(lots["outside"])[FACT] is False
    # The line cuts it: unanswered, as for an SCR lot.
    assert FACT not in asked(lots["cut"])


def test_a_zone_the_trace_does_not_reach_is_not_asked(layers) -> None:
    lot = _lots()["inside"]
    got = observed_facts(row(jurisdiction="hillsboro", zone="R-6", lot_wkb=shapely.to_wkb(lot)), layers)
    assert FACT not in got


@pytest.mark.parametrize("zone", ["R-7", "MR-1"])
def test_an_r7_or_mr1_lot_inside_the_line_is_red_on_the_flat_roof(corpus, zone) -> None:
    assert corpus.resolve(HILLSBORO, zone, ()).get("min_roof_pitch_in_12") is None
    inside = replace(corpus.resolve(HILLSBORO, zone, (FACT,)), verdict=RuleVerdict.trusted)
    assert inside.get("min_roof_pitch_in_12") == 4
    got = _run(inside, facts(street_lines_ft=(80.0,)), Configuration(conditions=(FACT,)))
    assert got.colour is Colour.red
    roof = next(c for c in got.checks if c.check == "roof_pitch")
    assert roof.observed == 0 and roof.threshold == 4


@pytest.mark.parametrize("zone", ["R-7", "MR-1"])
def test_an_r7_or_mr1_lot_the_line_cuts_is_never_green(corpus, zone) -> None:
    assert FACT in corpus.resolve(HILLSBORO, zone, ()).levers
    resolved = replace(corpus.resolve(HILLSBORO, zone, ()), verdict=RuleVerdict.trusted)
    got = _run(resolved, facts(street_lines_ft=(80.0,)), Configuration(unknown=(FACT,)))
    assert got.colour is not Colour.green
    assert FACT_UNOBSERVED in got.reasons
    assert [f for f in got.flags if f.code == FLAG]


@pytest.mark.parametrize("zone", ["SCR-LD", "SCR-MD", "SCR-HD"])
def test_the_scr_zones_read_as_before(corpus, layers, zone) -> None:
    assert corpus.resolve(HILLSBORO, zone, ()).get("min_roof_pitch_in_12") is None
    assert corpus.resolve(HILLSBORO, zone, (FACT,)).get("min_roof_pitch_in_12") == 4
    lots = _lots()
    got = observed_facts(row(jurisdiction="hillsboro", zone=zone, lot_wkb=shapely.to_wkb(lots["inside"])), layers)
    assert got[FACT] is True
