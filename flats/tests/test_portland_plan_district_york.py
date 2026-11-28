"""Portland's York plan district (33.597), FOLLOWUPS 222 (2026-11-28).

The completeness check found York never read. Only RICAP 11's amendment
exhibit of 33.597.135 is stored: "The nonresidential use requirement applies
on sites in the EX zone", and in Subdistricts B and C at least .5 sq ft of
floor area must be non-residential for each sq ft of site area. Four homes
have none. The rest of the chapter (D.2-3 included) is not stored and no
zoning layer is held to cut the outline to EX, so the whole York outline
joins the ``pdx_plan_district_unmeasured`` tracing: a held lot, never a
GREEN and never a RED on this alone.

What is guarded: the quoted lines say what the hold claims; the York outline
is in the tracing; a lot drawn inside York reads the hold true and the same
lot, unheld, is GREEN where held it is YELLOW; and the cite names 33.597.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely
from shapely.geometry import box, shape
from shapely.ops import unary_union

from flats.designs.model import load_catalog
from flats.geom.drawn import load_area
from flats.ingest.quadfit import lot_from_row, screen_lot
from flats.provenance.store import ProvenanceStore
from flats.rules import loader
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
HOLD = "pdx_plan_district_unmeasured"
TRACING = f"{PORTLAND}/plan-district-unmeasured-lots.geojson"
QUOTE = "or/multnomah/portland/amended/ricap11.txt#L3759-L3760,L3805-L3806"


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def _york():
    data = json.loads((loader.AREAS_ROOT / f"{PORTLAND}/plan-districts.geojson").read_text(encoding="utf-8"))
    return unary_union([shape(f["geometry"]) for f in data["features"] if f["properties"]["PLDIST"] == "YO"])


def test_the_quote_says_ex_and_half_a_square_foot() -> None:
    text = " ".join(ProvenanceStore().quote(QUOTE).split())
    assert "applies on sites in the EX zone" in text
    assert "at least .5 square feet of floor area must be in a non-residential use" in text
    assert "subdistricts B and C" in text


def test_the_whole_york_outline_is_in_the_tracing() -> None:
    york = _york()
    assert york.area > 40 * 43_560
    assert load_area(TRACING).buffer(1.0).contains(york)


def test_the_tracing_and_the_cites_name_york() -> None:
    src = json.loads((loader.AREAS_ROOT / TRACING).read_text(encoding="utf-8"))["source"]
    assert "York (33.597)" in src["map"] and "york" in src["inputs"]
    portland = loader.load_rules()[PORTLAND]
    (area,) = [a for a in portland.drawn_areas.values() if a.condition == HOLD]
    assert "33.597.135" in (area.cite or "") and "EX" in area.zones
    import yaml

    raw = yaml.safe_load((loader.CONFIG_ROOT / f"{PORTLAND}.yaml").read_text(encoding="utf-8"))
    assert "33.597.135" in raw["zones"]["EX"]["quadplex_allowed"]["qualified_by"]["cite"]


def _york_lot(corpus, w: float = 100.0, d: float = 200.0, zone: str = "EX"):
    pt = _york().representative_point()
    x0, y0 = pt.x - w / 2, pt.y - d / 2
    edges = [
        [x0, y0, x0 + w, y0, "F"],
        [x0 + w, y0, x0 + w, y0 + d, "S"],
        [x0 + w, y0 + d, x0, y0 + d, "R"],
        [x0, y0 + d, x0, y0, "S"],
    ]
    r = {
        "TLID": "1N1E00AA  -00100",
        "jurisdiction": "portland",
        "zone": zone,
        "tier": "A",
        "area_sqft": w * d,
        "frontage_ft": w,
        "lot_width_ft": w,
        "lot_depth_ft": d,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(box(x0 + 5, y0 + 10, x0 + w - 5, y0 + d - 15)),
        "lot_wkb": shapely.to_wkb(box(x0, y0, x0 + w, y0 + d)),
    }
    return lot_from_row(r, corpus.layers)


def _screen(corpus, lot):
    (s,) = screen_lot(
        lot,
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return s.signed


def test_an_ex_lot_in_york_reads_the_hold(corpus) -> None:
    york = _york()
    pt = york.representative_point()
    assert york.contains(box(pt.x - 50, pt.y - 100, pt.x + 50, pt.y + 100))
    assert _york_lot(corpus).observed.get(HOLD) is True


def _york_pair(corpus, zone: str):
    """The York lot with every other unanswered fact answered off: as read
    (held), and the same lot with the hold lifted."""
    lot = _york_lot(corpus, zone=zone)
    assert lot.observed.get(HOLD) is True, zone
    off = {k: False for k, v in lot.observed.items() if v is None}
    held = dataclasses.replace(lot, observed={**lot.observed, **off})
    clear = dataclasses.replace(held, observed={**held.observed, HOLD: False})
    return _screen(corpus, clear), _screen(corpus, held)


@pytest.mark.parametrize("zone", ["CM3", "RM2", "CX"])
def test_a_york_lot_green_without_the_hold_is_yellow_with_it(corpus, zone: str) -> None:
    # The outline is held whole (33.597 is not stored beyond 135), so a
    # York lot of any held zone that would open is YELLOW and names the hold.
    clear, held = _york_pair(corpus, zone)
    assert clear.colour is flag_plan.Colour.green, zone
    assert held.colour is flag_plan.Colour.yellow, zone
    assert fact_code(HOLD) in {f.code for f in held.flags}


def test_a_york_ex_lot_is_never_green(corpus) -> None:
    # EX is the zone 33.597.135.A names. This lot is RED on the parking cap
    # before the hold is asked; the hold never lifts a RED.
    _, held = _york_pair(corpus, "EX")
    assert held.colour is not flag_plan.Colour.green
