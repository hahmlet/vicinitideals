"""South Hillsboro's Town Center and Village Center Core Areas (FOLLOWUPS 147).

MU-VTC's minimum building height is 3 stories inside a Center Core and 2
outside (Hillsboro CDC Table 12.24.360-1), and its minimum FAR 0.5 inside and
0.4 outside. The cores are placed only by Figure 12.65.930-A, which
12.65.030.A.2 calls illustrative: "final boundaries" are set at the PUD.
Steph ruled 2026-11-04 (rulings.yaml
2026-11-04-south-hillsboro-centre-cores-traced): "Trace the centres too ...
Green with flag if outside, red with flag if inside".

What is guarded: the traced file says what it is drawn from and holds the two
cores; MU-VTC resolves 2 stories / 0.4 off a core and 3 / 0.5 on one, both on
levers; every MU-VTC lot carries HILLSBORO-CENTER-CORE-ILLUSTRATIVE whichever
side it falls; a lot outside that passes is GREEN with the flag only once the
12.65.150.A FAR doubt is answered (held YELLOW while it is not, which is every
lot today); a lot inside is RED on the 3-storey minimum; a lot the traced line
cuts is YELLOW, never GREEN.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely

from flats.encode.load import load_trusted
from flats.geom.drawn import INSIDE_SHARE, OUTSIDE_SHARE, load_area, share_inside
from flats.ingest.quadfit import observed_facts
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet, Verdict
from flats.score import relief, slack
from flats.score.configure import configure
from flats.score.flags import Colour, colour_rules, load_registry
from flats.score.screen import CENTER_CORE_ILLUSTRATIVE, LEVER_FLAGS, screen
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_round2_rulings import DESIGN, check, facts, fit

pytestmark = pytest.mark.unit

HILLSBORO = "or/washington/hillsboro"
TRACING = "or/washington/hillsboro/center-cores.geojson"
CORE = "hillsboro_center_core"
FAR = "hillsboro_far_residential_uncounted"
FLAG = "HILLSBORO-CENTER-CORE-ILLUSTRATIVE"


# --- the tracing --------------------------------------------------------------


def test_the_traced_cores_say_what_they_are_drawn_from() -> None:
    doc = json.loads((AREAS_ROOT / TRACING).read_text(encoding="utf-8"))
    src = doc["source"]
    assert src["drawn"] is True
    assert "Figure 12.65.930-A" in src["map"]
    assert src["quote"].startswith("or/washington/hillsboro/12.65/12.65.030.txt#")
    assert "illustrat" in src["illustrative"]
    assert {f["properties"]["core"] for f in doc["features"]} == {"town_center", "village_center"}
    # Each core is a few city blocks, not a district: 43 and 35 acres traced.
    for f in doc["features"]:
        assert 25 < f["properties"]["acres"] < 60


def _mu_vtc(lot) -> dict:
    return observed_facts(row(jurisdiction="hillsboro", zone="MU-VTC", lot_wkb=shapely.to_wkb(lot)), layers_())


_LAYERS: list = []


def layers_():
    if not _LAYERS:
        _LAYERS.append(load_trusted(strict=False).rules.layers)
    return _LAYERS[0]


def test_a_lot_in_each_core_is_inside_and_one_far_off_is_outside() -> None:
    area = load_area(TRACING)
    for core in area.geoms:
        assert _mu_vtc(core.representative_point().buffer(5))[CORE] is True
    minx, miny, _, _ = area.bounds
    assert _mu_vtc(shapely.box(minx - 2000, miny - 2000, minx - 1900, miny - 1900))[CORE] is False


def test_a_lot_the_core_line_cuts_is_unanswered() -> None:
    area = load_area(TRACING)
    town = max(area.geoms, key=lambda g: g.area)
    ring = list(town.exterior.coords)
    a, b = max(zip(ring, ring[1:]), key=lambda ab: shapely.Point(ab[0]).distance(shapely.Point(ab[1])))
    lot = shapely.Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2).buffer(15)
    assert OUTSIDE_SHARE < share_inside(lot, area) < INSIDE_SHARE
    assert CORE not in _mu_vtc(lot)


def test_another_zone_is_not_asked() -> None:
    p = load_area(TRACING).representative_point().buffer(5)
    got = observed_facts(row(jurisdiction="hillsboro", zone="MR-3", lot_wkb=shapely.to_wkb(p)), layers_())
    assert CORE not in got


# --- the rules ----------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def test_mu_vtc_owes_three_stories_in_a_core_and_two_outside(corpus: RuleSet) -> None:
    off = corpus.resolve(HILLSBORO, "MU-VTC", ())
    on = corpus.resolve(HILLSBORO, "MU-VTC", (CORE,))
    assert (off.get("min_building_height_stories"), off.get("min_far")) == (2, 0.4)
    assert (on.get("min_building_height_stories"), on.get("min_far")) == (3, 0.5)
    # Table 12.50.210-1, MU-C column: 200 sq ft a dwelling.
    assert off.get("open_space_min_sqft") == 800
    # The core and the 12.65.150.A doubt are levers: unanswered, no GREEN.
    assert {CORE, FAR} <= off.levers


def test_the_flag_sits_below_the_yellow_line() -> None:
    entry = load_registry()[FLAG]
    assert entry.severity < colour_rules().yellow_at_severity
    assert LEVER_FLAGS[CORE] == (FLAG, CENTER_CORE_ILLUSTRATIVE)
    # An unanswered core edge or FAR doubt is a question, above it.
    for fact in ("FACT-HILLSBORO-CENTER-CORE", "FACT-HILLSBORO-FAR-RESIDENTIAL-UNCOUNTED"):
        assert load_registry()[fact].severity >= colour_rules().yellow_at_severity


# --- the screen ---------------------------------------------------------------

#: Answered off the Active Use streets and not a flag lot, so only the core
#: and the FAR doubt are open. Inside the growth boundary, so ORS 197A.400
#: lifts MU-VTC's conditions review as it does on every South Hillsboro lot.
#: Inside the South Hillsboro Plan District, as every MU-VTC lot is: since
#: cut-district (FOLLOWUPS 188) a value gated `only_when` on the district
#: (gresham-end-glass's end-wall glass, rel8) leans on it, and an unanswered
#: district holds the lot YELLOW (rel9 assembly, 2026-11-13).
PLAIN = {
    "hillsboro_active_use_1": False,
    "hillsboro_active_use_2": False,
    "flag_lot": False,
    "south_hillsboro_plan_district": True,
}


def _screen(corpus: RuleSet, observed: dict):
    lot = facts(street_lines_ft=(80.0,), lot_sqft=9000, inside_ugb=True)
    cfg = configure(lot, DESIGN, observed={**PLAIN, **observed})
    got = corpus.resolve(HILLSBORO, "MU-VTC", cfg.conditions)
    # The colour once the corpus is signed, as the bridge reports it
    # (flats.ingest.quadfit._if_signed).
    got = dataclasses.replace(got, verdict=Verdict.trusted, untrusted=())
    return screen(
        got, lot, DESIGN, fit(), policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(), config=cfg,
    )


def _flagged(result) -> bool:
    (f,) = [f for f in result.flags if f.code == FLAG]
    return f.by == CENTER_CORE_ILLUSTRATIVE


def test_a_lot_outside_the_cores_that_passes_is_green_with_the_flag(corpus: RuleSet) -> None:
    got = _screen(corpus, {CORE: False, FAR: False})
    assert check(got, "min_stories").verdict is slack.Verdict.passes
    assert got.colour is Colour.green
    assert _flagged(got)


def test_outside_the_cores_the_far_doubt_holds_it_yellow(corpus: RuleSet) -> None:
    # Nothing answers 12.65.150.A today, so every MU-VTC lot is here.
    got = _screen(corpus, {CORE: False})
    assert got.colour is Colour.yellow
    assert "FACT-HILLSBORO-FAR-RESIDENTIAL-UNCOUNTED" in {f.code for f in got.flags}
    assert _flagged(got)


def test_a_lot_inside_a_core_is_red_with_the_flag(corpus: RuleSet) -> None:
    for answered in ({CORE: True}, {CORE: True, FAR: False}):
        got = _screen(corpus, answered)
        assert check(got, "min_stories").verdict is slack.Verdict.fails
        assert got.colour is Colour.red
        assert _flagged(got)


def test_a_lot_the_core_line_cuts_is_yellow_never_green(corpus: RuleSet) -> None:
    for answered in ({}, {FAR: False}):
        got = _screen(corpus, answered)
        assert got.colour is Colour.yellow
        assert "FACT-HILLSBORO-CENTER-CORE" in {f.code for f in got.flags}
        assert _flagged(got)
