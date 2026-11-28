"""Oregon City's Thimble Creek Concept Plan area (FOLLOWUPS 222 items 1-2).

The city's boundary layer (held since the 2026-10-22 ingest) is now a drawn
area, ``oregon_city_thimble_creek``, asked of R-5 and MUC-2 lots:

* MUC-2: OCMC 17.29.080.E holds every residential use but live/work to upper
  stories over a non-residential ground floor, so the pod is refused there.
* R-5: 17.10.070.C.3 sets primary structures forty feet from the area's
  southern boundary on a lot within twenty feet of it. Nothing measures that
  distance, so the rear yard is ``qualified_by`` the fact and every R-5 lot
  inside the area stays out of GREEN, named.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely
from shapely.geometry import box

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import lot_from_row, observed_facts, screen_lot
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_utility_easement import lot_row

pytestmark = pytest.mark.unit

OC = "or/clackamas/oregon-city"
FACT = "oregon_city_thimble_creek"
FILE = "or/clackamas/oregon-city/thimble-creek-beavercreek-concept-plan.geojson"


@pytest.fixture(scope="module")
def corpus():
    return load_rules()


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def test_the_fact_is_a_drawn_site_fact_with_no_assumption() -> None:
    defn = CONDITIONS[FACT]
    assert defn.kind == "site_fact"
    assert defn.assume is None
    assert FACT in DRAWN_CONDITIONS
    assert fact_code(FACT) in flag_plan.registry().types


def test_oregon_city_declares_the_area_for_r5_and_muc2(corpus) -> None:
    (area,) = [a for a in corpus[OC].drawn_areas.values() if a.condition == FACT]
    assert area.file == FILE
    assert set(area.zones) == {"R-5", "MUC-2"}


def test_the_quoted_lines_are_the_rules() -> None:
    store = ProvenanceStore()
    setback = store.quote("or/clackamas/oregon-city/17.zoning.txt#L4427-L4430")
    assert "within twenty feet" in setback and "forty feet" in setback
    upper = store.quote("or/clackamas/oregon-city/17.zoning.txt#L7254-L7257")
    assert "upper stories only" in upper
    assert "17.16.155" not in corpus_header()


def corpus_header() -> str:
    text = (Path(__file__).parents[1] / "config/jurisdictions" / f"{OC}.yaml").read_text(
        encoding="utf-8"
    )
    return text[:3000]


def test_muc2_inside_the_area_refuses_the_pod(corpus) -> None:
    rs = RuleSet(corpus)
    assert rs.resolve(OC, "MUC-2").get("quadplex_allowed") is True
    assert rs.resolve(OC, "MUC-2", [FACT]).get("quadplex_allowed") is False


def test_r5_rear_yard_is_held_on_the_area_and_keeps_its_number(corpus) -> None:
    held = corpus[OC].zones["R-5"].values["setback_rear_ft"]
    assert held.qualified_by == FACT
    assert "17.10.070.C.3" in held.qualified_cite
    res = RuleSet(corpus).resolve(OC, "R-5")
    assert res.get("setback_rear_ft") == 20
    assert FACT in res.unencoded
    # R-3.5 prints the same table row and is not in the area's reach.
    assert FACT not in RuleSet(corpus).resolve(OC, "R-3.5").unencoded


@pytest.mark.parametrize("zone", ["R-5", "MUC-2"])
def test_a_lot_inside_is_inside_and_one_far_away_is_not(layers, zone) -> None:
    area = load_area(FILE)
    biggest = max(getattr(area, "geoms", [area]), key=lambda g: g.area)
    inside = biggest.representative_point().buffer(3)
    minx, miny, _, _ = area.bounds
    outside = shapely.box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)

    def oc(lot) -> dict:
        return observed_facts(
            row(jurisdiction="oregon_city", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers
        )

    assert oc(inside)[FACT] is True
    assert oc(outside)[FACT] is False


def test_a_lot_of_another_zone_is_not_asked(layers) -> None:
    area = load_area(FILE)
    inside = area.representative_point().buffer(3)
    got = observed_facts(
        row(jurisdiction="oregon_city", zone="R-6", lot_wkb=shapely.to_wkb(inside)), layers
    )
    assert FACT not in got


def _r5_lot(x0: float, y0: float, w: float = 100.0, d: float = 200.0) -> dict[str, object]:
    edges = [
        [x0, y0, x0 + w, y0, "F"],
        [x0 + w, y0, x0 + w, y0 + d, "S"],
        [x0 + w, y0 + d, x0, y0 + d, "R"],
        [x0, y0 + d, x0, y0, "S"],
    ]
    return lot_row(
        w,
        d,
        TLID="3S2E15A00999",
        jurisdiction="oregon_city",
        zone="R-5",
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(x0 + 5, y0 + 10, x0 + w - 5, y0 + d - 15)),
        lot_wkb=shapely.to_wkb(box(x0, y0, x0 + w, y0 + d)),
        # The other two Oregon City maps, read clear, so only the area moves.
        ovl_oregon_city_nrod_sqft=0.0,
        ovl_oregon_city_greenway=False,
    )


def _screen(corpus, row_):
    lot = lot_from_row(row_, corpus.layers)
    (s,) = screen_lot(
        lot,
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return lot, s


def test_an_r5_lot_green_outside_is_held_out_of_green_inside() -> None:
    corpus = load_trusted(strict=False).rules
    area = load_area(FILE)
    p = area.representative_point()
    minx, miny, _, _ = area.bounds

    out_lot, outside = _screen(corpus, _r5_lot(minx - 3000, miny - 3000))
    assert out_lot.observed[FACT] is False
    assert outside.signed.colour is flag_plan.Colour.green

    in_lot, inside = _screen(corpus, _r5_lot(p.x - 50, p.y - 100))
    assert in_lot.observed[FACT] is True
    assert inside.signed.colour is flag_plan.Colour.yellow
    assert fact_code(FACT) in {f.code for f in inside.signed.flags}
