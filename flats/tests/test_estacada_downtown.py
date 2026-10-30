"""Estacada's Downtown (D) zone, opened on its back streets.

EMC 16.26.020 (D)(4) permits a fourplex in D only where ground floor
residential does not front Broadway Street, Main Street or OR 224, never south
of OR 224, at sixteen units an acre and with the access standards of
16.26.040 (H) met. Until districts chunk 5 (2026-10-29) the zone refused the
pod everywhere, because no fact said which lots front which streets. The
layer now builds that area from the taxlots and answers
``inside_mapped_use_area`` with it.

What is guarded: the area answers D's lever and only D's; inside it the
fourplex is open and the townhouse-lot path stays shut (the chapter lists no
commonwall dwelling); outside it the pod is RED on the use; the committee
design review is the judgement tier, so a lot that fits is GREEN with the
CLEAR-OBJECTIVE flag; a lot too big for four homes to reach sixteen an acre is
held out of GREEN; and the area was built with no lot that fronts a named
street.
"""

from __future__ import annotations

import itertools
import json

import pytest
import shapely
from shapely.geometry import box

from flats.geom.drawn import INSIDE_SHARE, load_area, share_inside
from flats.ingest.quadfit import lot_from_row, screen_lot
from flats.rules.loader import AREAS_ROOT, load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.tests.test_fire import bridge_row, pod
from flats.tests.test_townhouse_lots import NO_OVERLAYS

pytestmark = pytest.mark.unit

ESTACADA = "or/clackamas/estacada"
AREA = "or/clackamas/estacada/downtown-back-streets.geojson"
MAPPED = "inside_mapped_use_area"
FAR = (7_560_000.0, 600_000.0)  # well west of Estacada, in no area


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def _value(corpus, field: str, *active: str):
    got = corpus[ESTACADA].zones["D"].values[field].under(active)
    assert not got.ambiguous, (field, active, got.ambiguous)
    return "exempt" if got.exempt else got.value


# --- the area -------------------------------------------------------------------


def test_the_area_answers_ds_lever_only(corpus) -> None:
    got = {
        (a.condition, a.file): set(a.zones)
        for a in corpus[ESTACADA].drawn_areas.values()
    }
    assert got == {(MAPPED, AREA): {"D"}}


def test_the_area_was_built_with_no_lot_on_a_named_street() -> None:
    """The file records how each D lot was decided; the rule that keeps a
    lot must have dropped every lot that reached a barred street."""
    data = json.loads((AREAS_ROOT / AREA).read_text(encoding="utf-8"))
    src = data["source"]
    assert src["drawn"] is True
    assert src["quote"].startswith("or/clackamas/estacada/16.26/16.26.020.txt#")
    for word in ("Broadway", "Main", "OR 224", "Currin", "Acacia"):
        assert word in src["how"], word
    counts = src["counts"]
    assert counts["kept"] + sum(counts["dropped"].values()) == counts["D_lots"]
    (feature,) = data["features"]
    assert len(feature["properties"]["taxlots"]) == counts["kept"]


# --- the values -----------------------------------------------------------------


def test_the_back_streets_open_the_fourplex_and_not_the_townhouse_lots(corpus) -> None:
    assert _value(corpus, "quadplex_allowed") is False
    assert _value(corpus, "quadplex_allowed", MAPPED) is True
    assert _value(corpus, "quadplex_allowed", MAPPED, "unit_lots") is False
    assert _value(corpus, "quadplex_allowed", "unit_lots") is False


def test_the_figures_are_the_printed_ones(corpus) -> None:
    assert _value(corpus, "min_density_du_per_acre") == 16
    assert _value(corpus, "max_height_ft") == 65
    assert _value(corpus, "min_building_height_ft") == 17
    assert _value(corpus, "setback_front_ft") == 5
    assert _value(corpus, "setback_front_max_ft") == 5
    assert _value(corpus, "setback_side_ft") == 10
    assert _value(corpus, "setback_rear_ft") == 10
    assert _value(corpus, "min_landscaped_pct") == 5
    assert _value(corpus, "parking_front_prohibited") is True
    assert _value(corpus, "review_discretion") == "judgement"
    assert _value(corpus, "min_lot_sqft") == "exempt"


FACTS = (MAPPED, "unit_lots", "alley_at_rear", "abuts_alley", "attached_wall")


def test_no_set_of_facts_leaves_two_variants_tying(corpus) -> None:
    block = corpus[ESTACADA].zones["D"]
    for n in range(len(FACTS) + 1):
        for active in itertools.combinations(FACTS, n):
            for field, value in block.values.items():
                got = value.under(active)
                assert not got.ambiguous, (field, active, got.ambiguous)


# --- on a lot -------------------------------------------------------------------


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _row(x0: float, y0: float, width: float, depth: float) -> dict:
    edges = [
        [x0, y0, x0 + width, y0, "F"],
        [x0 + width, y0, x0 + width, y0 + depth, "S"],
        [x0 + width, y0 + depth, x0, y0 + depth, "R"],
        [x0, y0 + depth, x0, y0, "S"],
    ]
    return bridge_row(
        jurisdiction="estacada",
        zone="D",
        inside_ugb=True,
        area_sqft=width * depth,
        frontage_ft=width,
        lot_width_ft=width,
        lot_depth_ft=depth,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(x0 + 5, y0 + 10, x0 + width - 5, y0 + depth - 5)),
        lot_wkb=shapely.to_wkb(box(x0, y0, x0 + width, y0 + depth)),
        **NO_OVERLAYS,
    )


def _screen(rules, policies, x0: float, y0: float, width: float, depth: float):
    lot = lot_from_row(_row(x0, y0, width, depth), rules.layers)
    (got,) = screen_lot(
        lot, [pod()], rules=rules, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    return got


def _inside(width: float, depth: float) -> tuple[float, float]:
    """A corner for a lot of this size wholly inside the area's largest block."""
    area = load_area(AREA)
    block = max(area.geoms, key=lambda p: p.area)
    pt = block.buffer(-55).representative_point()
    x0, y0 = pt.x - width / 2, pt.y - depth / 2
    assert share_inside(box(x0, y0, x0 + width, y0 + depth), area) >= INSIDE_SHARE
    return x0, y0


def test_a_back_street_lot_that_fits_is_green_with_the_review_flag(
    rules, policies
) -> None:
    # 10,500 sq ft: four homes is 16.6 an acre, over the floor.
    got = _screen(rules, policies, *_inside(100, 105), 100, 105)
    assert got.signed.colour is Colour.green
    assert got.signed.triage.value == "green"
    assert "CLEAR-OBJECTIVE" in {f.code for f in got.signed.flags}


def test_the_same_lot_off_the_back_streets_is_red_on_the_use(rules, policies) -> None:
    got = _screen(rules, policies, *FAR, 100, 105)
    assert got.signed.colour is Colour.red
    assert "use" in {b.check for b in got.signed.binds}


def test_a_lot_too_big_for_sixteen_an_acre_is_not_green(rules, policies) -> None:
    """A 22,000 sq ft lot holds four homes at under eight an acre."""
    got = _screen(rules, policies, *_inside(110, 200), 110, 200)
    density = {c.check: c for c in got.signed.checks}["min_density_du_per_acre"]
    assert (density.threshold, density.verdict.value) == (16, "fail")
    assert got.signed.triage.value != "green"
