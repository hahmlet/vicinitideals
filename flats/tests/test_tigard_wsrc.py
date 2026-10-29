"""Tigard's Washington Square Regional Center and Bridgeport Village, drawn.

Metro's zoning layer prints MUR and MUC. Whether a lot sits in the Washington
Square Regional Center (TDC 18.670), in its Apartment Subdistrict, or in
Bridgeport Village (18.620) is drawn elsewhere: the plan districts on the
city's Community Plan Areas layer, the subdistricts on Map 18.670.A alone.
Until districts chunk 5 (2026-10-29) ``inside_mapped_use_area`` was unknown on
every MUR and MUC lot, so all of them screened UNKNOWN.

What is guarded: MUR's lever is answered by the traced Apartment
Subdistrict, MUC's by the WSRC plan district, and Bridgeport by its own
condition; inside each refusing area the pod is RED on the use; outside it the
lever no longer holds the lot; Bridgeport's figures are read, so its one big
lot does not screen GREEN on MUC's blank cells; and no set of facts leaves two
variants tying.
"""

from __future__ import annotations

import itertools
import json

import pytest
import shapely
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom.drawn import INSIDE_SHARE, load_area, share_inside
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

TIGARD = "or/washington/tigard"
APT = "or/washington/tigard/wsrc-apartment-subdistrict.geojson"
WSRC = "or/washington/tigard/wsrc-plan-district.geojson"
BRIDGEPORT = "or/washington/tigard/bridgeport-village.geojson"
MAPPED = "inside_mapped_use_area"
BV = "tigard_bridgeport_village"
FAR = (7_560_000.0, 600_000.0)  # well west of Tigard, in no area


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def _value(corpus, zone: str, field: str, *active: str):
    got = corpus[TIGARD].zones[zone].values[field].under(active)
    assert not got.ambiguous, (zone, field, active, got.ambiguous)
    return "exempt" if got.exempt else got.value


def _deep_point(file: str):
    """A point far enough inside the area that a 150 x 200 ft lot around it
    lies wholly inside."""
    return load_area(file).buffer(-130).representative_point()


# --- the areas ------------------------------------------------------------------


def test_each_area_answers_its_lever_for_its_zone_only(corpus) -> None:
    assert BV in DRAWN_CONDITIONS
    got = {
        (a.condition, a.file): set(a.zones) for a in corpus[TIGARD].drawn_areas.values()
    }
    assert got == {
        (MAPPED, APT): {"MUR"},
        (MAPPED, WSRC): {"MUC"},
        (BV, BRIDGEPORT): {"MUC"},
    }


def test_the_apartment_subdistrict_lies_inside_the_plan_district() -> None:
    apt, wsrc = load_area(APT), load_area(WSRC)
    assert apt.difference(wsrc).area / apt.area < 0.02
    # A subdistrict, not the district: a small share of it.
    assert apt.area < 0.1 * wsrc.area


def test_a_lot_is_answered_by_where_it_lies(layers) -> None:
    def tigard(lot, zone: str) -> dict:
        return observed_facts(
            plain_row(jurisdiction="tigard", zone=zone, lot_wkb=shapely.to_wkb(lot)),
            layers,
        )

    apt = _deep_point(APT).buffer(5)
    assert tigard(apt, "MUR")[MAPPED] is True
    wsrc_only = (
        load_area(WSRC)
        .buffer(-120)
        .difference(load_area(APT).buffer(200))
        .representative_point()
        .buffer(5)
    )
    assert tigard(wsrc_only, "MUR")[MAPPED] is False
    assert tigard(wsrc_only, "MUC")[MAPPED] is True
    bp = load_area(BRIDGEPORT).buffer(-100).representative_point().buffer(5)
    assert tigard(bp, "MUC")[BV] is True
    assert tigard(bp, "MUC")[MAPPED] is False
    far = box(FAR[0], FAR[1], FAR[0] + 100, FAR[1] + 100)
    assert tigard(far, "MUC")[MAPPED] is False
    assert tigard(far, "MUC")[BV] is False


# --- the values -----------------------------------------------------------------


@pytest.mark.parametrize("zone", ["MUR", "MUC"])
def test_the_refusing_area_refuses_the_use(corpus, zone) -> None:
    assert _value(corpus, zone, "quadplex_allowed") is True
    assert _value(corpus, zone, "quadplex_allowed", MAPPED) is False


def test_bridgeport_reads_its_own_figures(corpus) -> None:
    assert _value(corpus, "MUC", "min_density_du_per_acre") == "exempt"
    assert _value(corpus, "MUC", "min_density_du_per_acre", BV) == 25
    assert _value(corpus, "MUC", "setback_front_max_ft", BV) == 20
    assert _value(corpus, "MUC", "max_height_ft", BV) == 70
    assert _value(corpus, "MUC", "max_impervious_pct", BV) == 90
    assert _value(corpus, "MUC", "min_landscaped_pct", BV) == 10
    assert _value(corpus, "MUC", "parking_front_prohibited", BV) is True
    assert _value(corpus, "MUC", "parking_front_prohibited") == "exempt"


FACTS = (MAPPED, BV, "unit_lots", "alley_at_rear", "abuts_alley", "attached_wall")


@pytest.mark.parametrize("zone", ["MUR", "MUC"])
def test_no_set_of_facts_leaves_two_variants_tying(corpus, zone) -> None:
    block = corpus[TIGARD].zones[zone]
    for n in range(len(FACTS) + 1):
        for active in itertools.combinations(FACTS, n):
            if "alley_at_rear" in active and "abuts_alley" not in active:
                continue
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


def _row(
    zone: str, x0: float, y0: float, width: float = 150.0, depth: float = 200.0
) -> dict:
    edges = [
        [x0, y0, x0 + width, y0, "F"],
        [x0 + width, y0, x0 + width, y0 + depth, "S"],
        [x0 + width, y0 + depth, x0, y0 + depth, "R"],
        [x0, y0 + depth, x0, y0, "S"],
    ]
    return bridge_row(
        jurisdiction="tigard",
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
    (got,) = screen_lot(
        lot, [pod()], rules=rules, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    return got


def _at(rules, policies, zone: str, pt):
    return _screen(rules, policies, _row(zone, pt.x - 75, pt.y - 100))


def test_mur_is_red_in_the_apartment_subdistrict_and_open_outside_it(
    rules, policies
) -> None:
    inside = _at(rules, policies, "MUR", _deep_point(APT))
    assert inside.signed.colour is Colour.red
    assert "use" in {b.check for b in inside.signed.binds}

    wsrc_only = (
        load_area(WSRC)
        .buffer(-120)
        .difference(load_area(APT).buffer(200))
        .representative_point()
    )
    outside = _at(rules, policies, "MUR", wsrc_only)
    assert outside.signed.colour is Colour.green


def test_muc_is_red_in_wsrc_and_open_outside_it(rules, policies) -> None:
    inside = _at(rules, policies, "MUC", _deep_point(WSRC))
    assert inside.signed.colour is Colour.red
    assert "use" in {b.check for b in inside.signed.binds}

    outside = _screen(rules, policies, _row("MUC", *FAR))
    assert outside.signed.colour is Colour.green


def test_a_large_bridgeport_lot_is_not_green(rules, policies) -> None:
    """Two acres at four homes is far under 25 a net acre: MUC's blank cells
    alone would have read it GREEN, as they still do the same lot elsewhere.
    The district is a strip about 1,200 by 300 ft, so the lot is wide."""
    area = load_area(BRIDGEPORT)
    pt = area.buffer(-100).representative_point()
    x0, y0, w, d = pt.x - 200, pt.y - 100, 400.0, 200.0
    assert share_inside(box(x0, y0, x0 + w, y0 + d), area) >= INSIDE_SHARE
    got = _screen(rules, policies, _row("MUC", x0, y0, width=w, depth=d))
    density = {c.check: c for c in got.signed.checks}["min_density_du_per_acre"]
    assert (density.threshold, density.verdict.value) == (25, "fail")
    assert got.signed.triage.value != "green"
    elsewhere = _screen(rules, policies, _row("MUC", FAR[0], FAR[1], width=w, depth=d))
    assert "min_density_du_per_acre" not in {c.check for c in elsewhere.signed.checks}
    assert elsewhere.signed.triage.value == "green"
