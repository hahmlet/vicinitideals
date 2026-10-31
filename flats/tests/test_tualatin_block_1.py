"""Tualatin's Central Tualatin Overlay, Block 1 (FOLLOWUPS 109 chunk 5,
2026-10-29).

Block 1 is the only CO sub-district of the overlay (TDC 58.400(2)) and the
only CO ground inside it: the north part of one lot, 2S124A003100, whose
larger CC part is Block 2 of the Residential Sub-District. Table 58-4 lets
Block 1 build townhouses, never the pod on one lot; the townhouse lots then
fail Table 50-2's 80 ft average width.

What is guarded:

* a use area (``inside_mapped_use_area``) is asked about the screened
  zone's own ground on a lot the zoning maps split, so the CC part of that
  lot reads inside the Residential Sub-District and its CO part inside
  Block 1 -- while an overlay drawn across districts is still asked about
  the whole lot;
* CO admits the pod only as townhouses inside Block 1, and they fail the
  width;
* the tracings carry their drawn provenance.
"""

from __future__ import annotations

import json

import pytest
import shapely
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom import split_zone as split_zones
from flats.geom.drawn import load_area
from flats.ingest.quadfit import observed_facts
from flats.rules import loader
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.tests.test_quadfit_bridge import row

pytestmark = pytest.mark.unit

TUALATIN = "or/clackamas/tualatin"
BLOCK_1 = "or/clackamas/tualatin/co-block-1.geojson"
SUB_DISTRICT = "or/clackamas/tualatin/residential-sub-district.geojson"
WEST_LINN_WHD = "or/clackamas/west-linn/willamette-historic-district.geojson"


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def _cc_piece():
    data = json.loads((loader.AREAS_ROOT / SUB_DISTRICT).read_text(encoding="utf-8"))
    (f,) = [f for f in data["features"] if f["properties"]["taxlots"] == ["2S124A003100"]]
    return shapely.geometry.shape(f["geometry"])


def _split(other_zone: str, other) -> str:
    return split_zones.encode(
        split_zones.Split(pieces=(split_zones.Piece(other_zone, other.area, other, 50.0),), own_sqft=1.0)
    )


def _lot_row(zone: str, other_zone: str | None, other=None) -> dict:
    cc, co = _cc_piece(), load_area(BLOCK_1)
    lot = shapely.union_all([cc, co])
    over = {"jurisdiction": "tualatin", "zone": zone, "lot_wkb": shapely.to_wkb(lot), "split_zone": True}
    if other_zone is not None:
        over[split_zones.ROW_KEY] = _split(other_zone, other)
    return row(**over)


def test_the_whole_split_lot_is_cut_by_the_sub_district_line(layers) -> None:
    """Without its pieces the lot is half in, half out: unanswered."""
    assert "inside_mapped_use_area" not in observed_facts(_lot_row("CC", None), layers)


def test_the_cc_ground_of_the_split_lot_is_inside_the_residential_sub_district(layers) -> None:
    got = observed_facts(_lot_row("CC", "CO", load_area(BLOCK_1)), layers)
    assert got["inside_mapped_use_area"] is True


def test_the_co_ground_of_the_split_lot_is_block_1(layers) -> None:
    got = observed_facts(_lot_row("CO", "CC", _cc_piece()), layers)
    assert got["inside_mapped_use_area"] is True


def test_a_co_lot_elsewhere_is_outside_block_1(layers) -> None:
    minx, miny, _, _ = load_area(BLOCK_1).bounds
    lot = box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    got = observed_facts(row(jurisdiction="tualatin", zone="CO", lot_wkb=shapely.to_wkb(lot)), layers)
    assert got["inside_mapped_use_area"] is False


def test_an_overlay_across_districts_is_still_asked_about_the_whole_lot(layers) -> None:
    """The historic district covers every zone it lists: a lot half inside
    it is unanswered whichever half its own district holds."""
    area = load_area(WEST_LINN_WHD)
    p = max(area.geoms, key=lambda g: g.area).representative_point() if hasattr(area, "geoms") else area.representative_point()
    half_in = box(p.x - 5, p.y - 5, p.x + 5, p.y + 5)
    # Find an edge: grow a box eastward until it is cut by the outline.
    lot = None
    for w in range(10, 20_000, 10):
        cand = box(p.x - 5, p.y - 5, p.x + w, p.y + 5)
        share = cand.intersection(area).area / cand.area
        if 0.3 < share < 0.7:
            lot = cand
            break
    assert lot is not None and half_in.within(area)
    inside = lot.intersection(area)
    outside = lot.difference(area)
    r = row(
        jurisdiction="west_linn",
        zone="R-10",
        lot_wkb=shapely.to_wkb(lot),
        split_zone=True,
        **{split_zones.ROW_KEY: _split("R-5", outside)},
    )
    assert "willamette_historic_district" not in observed_facts(r, layers)
    assert inside.area > 0


def test_co_admits_four_townhouses_in_block_1_and_never_the_pod_on_one_lot() -> None:
    r = RuleSet(load_rules())

    def allowed(conds) -> bool:
        return r.resolve(TUALATIN, "CO", conds).values["quadplex_allowed"].value

    assert allowed(("inside_mapped_use_area", "unit_lots")) is True
    assert allowed(("inside_mapped_use_area",)) is False
    assert allowed(("unit_lots",)) is False
    town = r.resolve(TUALATIN, "CO", ("inside_mapped_use_area", "unit_lots"))
    assert town.missing_required == ()
    assert town.get("min_lot_sqft") == 1400
    # Table 58-7 moves only the lot size to RH: the 80 ft average width
    # stands, and a townhouse lot cannot meet it.
    assert town.get("min_lot_width_ft") == 80


def test_co_base_is_table_50_2_and_the_overlay_minimums_hold_only_in_block_1() -> None:
    """FOLLOWUPS 131: Table 58-7's 25,000 sq ft and 16-25 du/ac reach CO only
    inside the overlay; Table 50-2 prints 10,000 sq ft and no density."""
    r = RuleSet(load_rules())
    base = r.resolve(TUALATIN, "CO", ())
    assert base.get("min_lot_sqft") == 10000
    assert base.values["min_lot_sqft"].prov.quote == "or/clackamas/tualatin/50/50.300.txt#L7-L8"
    for field in ("min_density_du_per_acre", "max_density_du_per_acre"):
        assert field in base.exempted
    assert r.resolve(TUALATIN, "CO", ("unit_lots",)).get("min_lot_sqft") == 10000
    block_1 = r.resolve(TUALATIN, "CO", ("inside_mapped_use_area",))
    assert block_1.get("min_lot_sqft") == 25000
    assert block_1.get("min_density_du_per_acre") == 16
    # The state lifts the ceiling off the pod on one lot (OAR
    # 660-046-0220(2)(b)); the townhouse path keeps Table 58-7's 25.
    town = r.resolve(TUALATIN, "CO", ("inside_mapped_use_area", "unit_lots"))
    assert town.get("max_density_du_per_acre") == 25


def test_the_tracings_carry_their_drawn_provenance() -> None:
    block_1 = json.loads((loader.AREAS_ROOT / BLOCK_1).read_text(encoding="utf-8"))
    assert block_1["source"]["drawn"] is True
    assert block_1["source"]["quote"] == "or/clackamas/tualatin/58/58.400.txt#L6-L7"
    assert {f["properties"]["block"] for f in block_1["features"]} == {1}
    added = json.loads((loader.AREAS_ROOT / SUB_DISTRICT).read_text(encoding="utf-8"))
    (f,) = [f for f in added["features"] if f["properties"]["taxlots"] == ["2S124A003100"]]
    assert f["properties"]["drawn"] is True and f["properties"]["block"] == 2


def test_tualatin_declares_both_areas() -> None:
    areas = load_rules()[TUALATIN].drawn_areas
    assert (areas["co_block_1"].file, areas["co_block_1"].zones) == (BLOCK_1, ("CO",))
    assert areas["residential_sub_district"].zones == ("CC",)
