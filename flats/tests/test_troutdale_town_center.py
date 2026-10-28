"""Troutdale's Town Center columns, read from the city's Town Center layer.

TDC 3.120 and 3.130 print six columns: LDR-1, LDR-2, MDR, MDR (TC), HDR,
HDR (TC). The zoning layer carries only MDR and HDR, so until the Town Center
was held every HDR lot was read in the HDR column -- Quadplex N -- and every
MDR lot in the MDR column's bare ten-foot front. The layer now draws the
Town Center (``drawn_areas``) and answers ``troutdale_town_center`` from each
lot's share inside it (districts chunk 4, 2026-10-28).

What is guarded: the area is declared for MDR and HDR only; inside it HDR
permits the quadplex and both zones charge the 20 ft front a front driveway
brings (3.130.B note 1, 3.130.C note 2); outside it nothing moves; no pair of
facts the pod can carry leaves two variants tying; and on a lot the HDR
quadplex screens GREEN inside the area and RED on the use table outside it.
"""

from __future__ import annotations

import itertools
import json

import pytest
import shapely
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import lot_from_row, observed_facts, screen_lot
from flats.rules.conditions import DRAWN_CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.tests.test_fire import bridge_row, pod
from flats.tests.test_quadfit_bridge import row as plain_row
from flats.tests.test_townhouse_lots import NO_OVERLAYS

pytestmark = pytest.mark.unit

TROUTDALE = "or/multnomah/troutdale"
AREA = "or/multnomah/troutdale/town-center.geojson"
TC = "troutdale_town_center"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def _value(corpus, zone: str, field: str, *active: str):
    got = corpus[TROUTDALE].zones[zone].values[field].under(active)
    assert not got.ambiguous, (zone, field, active, got.ambiguous)
    return "exempt" if got.exempt else got.value


# --- the area -----------------------------------------------------------------


def test_the_town_center_is_a_drawn_area_for_mdr_and_hdr(corpus) -> None:
    assert TC in DRAWN_CONDITIONS
    (area,) = corpus[TROUTDALE].drawn_areas.values()
    assert (area.condition, area.file) == (TC, AREA)
    assert set(area.zones) == {"MDR", "HDR"}


def test_a_lot_inside_the_town_center_is_inside_and_one_far_off_is_not(layers) -> None:
    inside = load_area(AREA).representative_point().buffer(5)

    def troutdale(lot, zone="HDR") -> dict:
        return observed_facts(plain_row(jurisdiction="troutdale", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers)

    assert troutdale(inside)[TC] is True
    assert troutdale(inside, "MDR")[TC] is True
    far = box(7_760_000, 700_000, 7_760_100, 700_100)
    assert troutdale(far)[TC] is False


# --- the columns ----------------------------------------------------------------


def test_hdr_permits_the_quadplex_only_inside_the_town_center(corpus) -> None:
    assert _value(corpus, "HDR", "quadplex_allowed") is False
    assert _value(corpus, "HDR", "quadplex_allowed", TC) is True
    assert _value(corpus, "HDR", "quadplex_allowed", "unit_lots") is True
    assert _value(corpus, "HDR", "quadplex_allowed", "unit_lots", TC) is True


@pytest.mark.parametrize("zone", ["MDR", "HDR"])
def test_a_front_driveway_in_the_town_center_owes_twenty_feet(corpus, zone) -> None:
    assert _value(corpus, zone, "setback_front_ft", TC) == 20
    assert _value(corpus, zone, "setback_front_ft", TC, "alley_at_rear") == 10
    assert _value(corpus, zone, "setback_front_ft", "unit_lots", TC) == 20


def test_outside_the_town_center_the_mdr_front_is_unchanged(corpus) -> None:
    assert _value(corpus, "MDR", "setback_front_ft") == 10
    assert _value(corpus, "MDR", "min_frontage_ft") == 20
    assert _value(corpus, "MDR", "min_frontage_ft", TC) == 16


def test_hdr_tc_reads_the_quadplex_column(corpus) -> None:
    assert _value(corpus, "HDR", "min_lot_width_ft", TC) == 20
    assert _value(corpus, "HDR", "min_lot_depth_ft", TC) == 70
    assert _value(corpus, "HDR", "min_frontage_ft", TC) == 20
    assert _value(corpus, "HDR", "setback_side_ft", TC) == 5
    assert _value(corpus, "HDR", "setback_side_ft", TC, "attached_wall") == 0
    assert _value(corpus, "HDR", "setback_street_side_ft", TC) == 20
    assert _value(corpus, "HDR", "setback_rear_ft", TC, "multi_story") == 20
    assert _value(corpus, "HDR", "setback_rear_ft", TC, "multi_story", "alley_at_rear") == 5
    assert _value(corpus, "HDR", "max_height_ft", TC) == 35
    # The townhouse plat keeps the townhouse column's "none".
    assert _value(corpus, "HDR", "min_lot_width_ft", "unit_lots", TC) == "exempt"
    assert _value(corpus, "HDR", "setback_rear_ft", "unit_lots", TC, "multi_story") == 10


FACTS = (TC, "unit_lots", "multi_story", "alley_at_rear", "abuts_alley", "attached_wall", "access_easement")


@pytest.mark.parametrize("zone", ["MDR", "HDR"])
def test_no_set_of_facts_leaves_two_variants_tying(corpus, zone) -> None:
    """The model refuses a tie and routes the lot UNKNOWN, so every pairing
    the Town Center adds is spelled out one condition deeper."""
    block = corpus[TROUTDALE].zones[zone]
    for n in range(len(FACTS) + 1):
        for active in itertools.combinations(FACTS, n):
            if "alley_at_rear" in active and "abuts_alley" not in active:
                continue  # alley_at_rear carries abuts_alley
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


def _row(zone: str, x0: float, y0: float, width: float = 100.0, depth: float = 140.0) -> dict:
    edges = [
        [x0, y0, x0 + width, y0, "F"],
        [x0 + width, y0, x0 + width, y0 + depth, "S"],
        [x0 + width, y0 + depth, x0, y0 + depth, "R"],
        [x0, y0 + depth, x0, y0, "S"],
    ]
    return bridge_row(
        jurisdiction="troutdale",
        zone=zone,
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


def _screen(rules, policies, r: dict):
    lot = lot_from_row(r, rules.layers)
    (got,) = screen_lot(lot, [pod()], rules=rules, policy=policies[0], relief=policies[1], step_deg=30.0)
    return got


def test_an_hdr_lot_opens_inside_the_town_center_and_stays_red_outside(rules, policies) -> None:
    pt = load_area(AREA).representative_point()
    inside = _screen(rules, policies, _row("HDR", pt.x - 50, pt.y - 70))
    assert inside.signed.colour is Colour.green
    assert inside.forms["works_as"] == "apartment"

    outside = _screen(rules, policies, _row("HDR", pt.x + 50_000, pt.y + 50_000))
    assert outside.signed.colour is Colour.red
    assert "use" in {b.check for b in outside.signed.binds}
