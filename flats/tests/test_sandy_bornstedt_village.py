"""Sandy's Bornstedt Village Overlay, traced from the 2026 zoning map
(FOLLOWUPS 109 chunk 9, 2026-10-31).

SDC 17.54.60 applies the overlay to land "as shown on the City of Sandy
Zoning Map", which marks it with a hatched border and a letter S (17.54.00
E). The city publishes no layer and the map is a raster, so the hatched area
is traced, registered to the county taxlots and grown 30 ft outward. Inside
it row houses owe 17.54.80's lot widths (30 ft average in R-1, 20 in R-2 and
R-3, 20 at the building line).

What is guarded: the tracing carries its drawn provenance and the stored
map's sha; a lot clearly inside reads True, one far off reads False, one the
line cuts is unanswered; the widths bind only home lots inside, and only
ever tighten the zone's "No minimum".
"""

from __future__ import annotations

import hashlib
import json

import pytest
import shapely
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import observed_facts
from flats.provenance.store import STORE_ROOT as DOCS_ROOT
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import fact_code
from flats.tests.test_quadfit_bridge import row as plain_row

pytestmark = pytest.mark.unit

SANDY = "or/clackamas/sandy"
AREA = "or/clackamas/sandy/bornstedt-village-overlay.geojson"
MAP = "or/clackamas/sandy/zoning-map-2026.map-only"
BVO = "sandy_bornstedt_village"
TABLE = "or/clackamas/sandy/17.54/17.54.80.txt"


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def _line(quote_path: str, n: int) -> str:
    return (DOCS_ROOT / quote_path).read_text(encoding="utf-8").splitlines()[n - 1]


def test_the_overlay_is_traced_from_the_stored_2026_zoning_map() -> None:
    source = json.loads((AREAS_ROOT / AREA).read_text(encoding="utf-8"))["source"]
    assert source["drawn"] is True
    assert source["quote"] == "or/clackamas/sandy/17.54/17.54.60.txt#L4"
    assert source["says"] in _line("or/clackamas/sandy/17.54/17.54.60.txt", 4)
    meta = json.loads((AREAS_ROOT / f"{MAP}.json").read_text(encoding="utf-8"))
    pdf = (AREAS_ROOT / f"{MAP}.pdf").read_bytes()
    assert hashlib.sha256(pdf).hexdigest() == meta["sha256"]
    assert meta["sha256"] in source["map"]
    assert 'letter "S"' in _line("or/clackamas/sandy/17.54/17.54.00.txt", 28)


def test_the_area_is_declared_with_a_flag_for_the_unanswered_lot() -> None:
    areas = {a.condition: a for a in load_rules()[SANDY].drawn_areas.values()}
    assert (areas[BVO].file, set(areas[BVO].zones)) == (AREA, {"R-1", "R-2", "R-3"})
    assert BVO in DRAWN_CONDITIONS and CONDITIONS[BVO].assume is None
    flags = (AREAS_ROOT.parent / "flags.yaml").read_text(encoding="utf-8")
    assert f"  {fact_code(BVO)}:\n    description: \"Bornstedt Village edge unconfirmed" in flags


def _facts(layers, lot, zone="R-1") -> dict:
    return observed_facts(
        plain_row(jurisdiction="sandy", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers
    )


def test_inside_outside_and_cut(layers) -> None:
    area = load_area(AREA)
    assert _facts(layers, area.buffer(-80).representative_point().buffer(25))[BVO] is True
    minx, miny, _, _ = area.bounds
    assert _facts(layers, box(minx - 5300, miny - 5300, minx - 5200, miny - 5200))[BVO] is False
    p = (area.exterior if hasattr(area, "exterior") else area.geoms[0].exterior).coords[0]
    cut = box(p[0] - 30, p[1] - 50, p[0] + 30, p[1] + 50)
    share = cut.intersection(area).area / cut.area
    assert 0.1 < share < 0.9
    assert BVO not in _facts(layers, cut)


@pytest.mark.parametrize("zone,average", [("R-1", 30), ("R-2", 20), ("R-3", 20)])
def test_row_house_widths_bind_home_lots_inside_only(rules, zone, average) -> None:
    out = rules.resolve(SANDY, zone, ("unit_lots",))
    inside = rules.resolve(SANDY, zone, ("unit_lots", BVO))
    for name in ("min_lot_width_ft", "min_average_lot_width_ft"):
        assert out.get(name) is None and name in out.exempted, name
    assert inside.get("min_lot_width_ft") == 20
    assert inside.get("min_average_lot_width_ft") == average
    # The single-lot path is not a row house and owes neither.
    plain = rules.resolve(SANDY, zone, (BVO,))
    assert plain.get("min_average_lot_width_ft") is None
    # The overlay's looser yards are not taken: the zone's 20 ft front stands.
    assert inside.get("setback_front_ft") == out.get("setback_front_ft")
    assert "30 ft. row house" in _line(TABLE, 7) and "20 ft. row house" in _line(TABLE, 8)
