"""Kenton plan district Map 538-4, traced (FOLLOWUPS 185, 2026-11-13).

PCC 33.538.230: on the site frontages shown on Map 538-4 buildings stand at
the street lot line and "Exterior walls of buildings designed to meet these
requirements must be at least 25 feet high"; multi-dwelling zoned sites are
exempt. The pod measures 19 ft 1 in. On 2026-11-12 every Kenton CM2/CM3 lot
was held YELLOW until the map was traced; now:

* a lot a Map 538-4 frontage plainly overlaps (``pdx_kenton_building_line``,
  ``kenton-required-building-lines.geojson``) takes min_building_height_ft
  25 in CM2, CM3 and CE, and is RED;
* a lot the frontage only touches, a lot partly multi-dwelling zoned, and a
  lot on a Map 538-6 frontage (no driveway through it, 33.538.250) stay in
  the plan-district hold (YELLOW);
* a Kenton lot clearly off both maps leaves the hold.

Probe points are run-124 lot representative points (flats.lots, EPSG:2913).
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import screen_lot
from flats.provenance.store import ProvenanceStore
from flats.rules import loader
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.loader import load_rules
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.tests.test_portland_plan_districts_2 import (
    FILES,
    HOLD,
    _answered,
    _clear,
    _facts,
    _resolve,
)

pytestmark = pytest.mark.unit

KENTON = "pdx_kenton_building_line"
KENTON_FILE = "or/multnomah/portland/kenton-required-building-lines.geojson"
QUOTE = "or/multnomah/portland/33.538.txt#L110-L114"

#: On Map 538-4: zero-setback frontages on N Denver Ave (west side, east side)
#: and the pedestrian-amenities frontage on N Interstate Pl.
ON = {
    "1N1E09DA  -04800": (7642358.4, 706208.1),
    "1N1E09DB  -08600": (7642159.5, 705668.9),
    "1N1E09DA  -00900": (7642554.4, 706574.2),
}
#: Kenton CM2/CM3 lots clearly off Maps 538-4 and 538-6 (at least 50 ft from
#: a frontage, 60 ft from a 538-6 line): they leave the hold.
OFF = {
    "1N1E09DB  -01100": (7642002.3, 706452.7),
    "1N1E09DA  -01100": (7642721.3, 706593.5),
    "1N1E09AC  -00400": (7642000.2, 706891.8),
}
#: In doubt, held: a frontage touches -01000 at a corner without overlapping
#: it; -02200 is a third RM zoned (230.B exempts multi-dwelling sites); -02700
#: has a Map 538-6 frontage on N Interstate Pl.
DOUBT = {
    "1N1E09DA  -01000": (7642621.4, 706596.2),
    "1N1E09DB  -02200": (7642152.3, 706359.0),
    "1N1E09DA  -02700": (7642558.0, 706333.2),
}


def _probe(xy):
    return shapely.Point(*xy).buffer(5)


def test_the_fact_is_a_drawn_site_fact_never_assumed() -> None:
    assert KENTON in DRAWN_CONDITIONS
    assert CONDITIONS[KENTON].kind == "site_fact"
    assert CONDITIONS[KENTON].assume is None


def test_the_area_is_the_citys_map_538_4_layer_and_the_code_says_25_feet() -> None:
    data = json.loads((loader.AREAS_ROOT / KENTON_FILE).read_text(encoding="utf-8"))
    assert "BPS_Zoning_Code_Layers/MapServer/72" in data["source"]["map"]
    assert "538-kenton-pd_1.pdf" in data["source"]["sheet"]
    assert data["source"]["quote"] == QUOTE
    text = ProvenanceStore().quote(QUOTE)
    assert "site frontages shown on" in text and "Map 538-4" in text
    assert "must be at least 25 feet high" in text
    assert "Multi-dwelling zoned sites are exempt" in text
    assert shapely.is_valid(load_area(KENTON_FILE))


def test_only_the_commercial_zones_carry_the_25_ft_walls() -> None:
    (area,) = [a for a in load_rules()["or/multnomah/portland"].drawn_areas.values() if a.condition == KENTON]
    assert area.file == KENTON_FILE
    assert set(area.zones) == {"CM2", "CM3", "CE"}
    for zone in ("CM2", "CM3", "CE"):
        assert _resolve(zone, KENTON).get("min_building_height_ft") == 25
        assert _resolve(zone).get("min_building_height_ft") is None
    assert _resolve("RM1", KENTON).get("min_building_height_ft") is None


@pytest.mark.parametrize("tlid", ON)
def test_a_lot_on_map_538_4_takes_the_rule(tlid: str) -> None:
    facts = _facts("CM2", _probe(ON[tlid]))
    assert facts[KENTON] is True


@pytest.mark.parametrize("tlid", OFF)
def test_a_kenton_lot_off_the_maps_leaves_the_hold(tlid: str) -> None:
    facts = _facts("CM2", _probe(OFF[tlid]))
    assert facts[KENTON] is False
    assert facts[HOLD] is False


@pytest.mark.parametrize("tlid", DOUBT)
def test_a_kenton_lot_in_doubt_stays_held(tlid: str) -> None:
    facts = _facts("CM2", _probe(DOUBT[tlid]))
    assert facts[KENTON] is False
    assert facts[HOLD] is True


def test_the_multi_dwelling_lot_on_a_frontage_is_not_asked() -> None:
    # 1N1E09DB  -13600, RM1 under a Denver Ave frontage: exempt by 230.B, and
    # held for its Map 538-6 frontage.
    facts = _facts("RM1", _probe((7642156.5, 705569.0)))
    assert KENTON not in facts
    assert facts[HOLD] is True


def test_the_hold_no_longer_takes_kenton_commercial_ground_whole() -> None:
    hold = load_area(FILES[HOLD])
    for xy in OFF.values():
        assert not hold.intersects(_probe(xy))


def _screen(corpus, lot):
    (s,) = screen_lot(
        lot,
        [load_catalog().latest("pod80x25")],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return s


def _without(lot, fact: str):
    return dataclasses.replace(lot, observed={k: v for k, v in lot.observed.items() if k != fact})


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


def _height(screened):
    return [c for c in screened.signed.checks if c.check == "min_height_ft"]


def test_on_the_map_red_off_unasked_cut_yellow(corpus) -> None:
    # A 100 x 200 CM2 lot is YELLOW on its own (four homes sit under the
    # 1,450 sq ft per unit minimum density, a discretionary miss), and no
    # CM2 lot under 5,800 sq ft holds the pod: so "off the map" is read as
    # "the wall rule is not asked", not as GREEN.
    lot = _clear(corpus, "CM2")
    off = _screen(corpus, _answered(lot, **{KENTON: False}))
    assert off.signed.colour is not flag_plan.Colour.red
    assert _height(off) == []
    on = _screen(corpus, _answered(lot, **{KENTON: True}))
    assert on.signed.colour is flag_plan.Colour.red
    (wall,) = _height(on)
    assert wall.threshold == 25 and wall.observed < 20 and wall.verdict is slack.Verdict.fails
    cut = _screen(corpus, _without(lot, KENTON))
    assert cut.signed.colour is flag_plan.Colour.yellow


def test_the_flag_reads_in_plain_english() -> None:
    flag = flag_plan.registry().types[fact_code(KENTON)]
    assert "Map 538-4" in flag.description and "25 feet" in flag.description
    assert flag.severity >= flag_plan.colour_rules().yellow_at_severity
