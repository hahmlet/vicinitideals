"""A lot a traced district's line cuts is never passed on that district's rules
untested (FOLLOWUPS 188).

A traced area (``drawn_areas``) answers its fact True, False, or -- where its
line cuts through the lot -- not at all (:func:`flats.geom.drawn.observed_drawn`).
An unanswered fact holds the lot out of GREEN where some standard turns on it
(ruling 2026-10-14, split zones yellow; the conservative default), unless every
answer clears (:func:`flats.ingest.quadfit._bounded`). Two paths let a cut lot
through instead:

* a standard stated only inside the district (``only_when``) or only outside
  it (``unless``) was silent or applied with no lever recorded, so nothing
  knew the lot leaned on the fact (resolver);
* a traced-area review or record the screen applies itself
  (``AREA_REVIEWS``, ``AREA_FLAGS``) was asked only of a lot wholly inside.

Both are closed here, and both may move a lot only away from GREEN.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import shapely
from shapely.geometry import Point

from flats.encode.load import load_trusted
from flats.geom.drawn import INSIDE_SHARE, OUTSIDE_SHARE, load_area, share_inside
from flats.ingest.quadfit import _screen_lot_once, drawn_cut, lot_from_row, observed_facts
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan, relief, slack
from flats.score.configure import configure
from flats.score.screen import AREA_FLAGS, AREA_REVIEWS, LotFacts, area_review
from flats.tests.test_quadfit_bridge import X0, Y0, pod4, row
from flats.tests.test_worst_bound import OFF_PLAN_DISTRICTS

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
WASHINGTON = "or/washington/_unincorporated"
FRONTAGE_AREA = "pdx_min_site_frontage_area"
EASTERN = "pdx_eastern_pattern_area"
PLAN_REVIEW = "washington_plan_review"


@pytest.fixture(scope="module")
def trusted():
    return load_trusted(strict=False)


@pytest.fixture(scope="module")
def corpus(trusted):
    return trusted.rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


# --- the resolver: a gated standard names its gate ---------------------------------


def test_a_standard_silent_outside_its_district_still_names_the_district(corpus) -> None:
    # Portland RM2: 33.120.206's 90 ft frontage is stated only on Map 120-2's
    # sites. Outside (or unanswered) the value is silent -- and the district
    # is still a lever, so a lot that does not know which side it is on
    # leans on it.
    r = corpus.resolve(PORTLAND, "RM2")
    assert "min_frontage_ft" not in r.values
    assert {FRONTAGE_AREA, EASTERN} <= r.gate_levers
    assert {FRONTAGE_AREA, EASTERN} <= r.levers
    inside = corpus.resolve(PORTLAND, "RM2", (FRONTAGE_AREA,))
    assert inside.values["min_frontage_ft"].value == 90
    assert FRONTAGE_AREA in inside.levers


def test_a_standard_applied_unless_inside_a_district_names_the_district(corpus) -> None:
    # Washington County R-5: the parent-lot reading of CDC 302-7.1 A holds
    # unless the lot is in East Hillsboro's city-standards area, which states
    # the lot standards otherwise. Applied here, and the gate still named.
    r = corpus.resolve(WASHINGTON, "R-5")
    assert "east_hillsboro_city_standards" in r.gate_levers


def test_every_gated_district_is_traced_on_the_zones_it_gates() -> None:
    # The lever makes an unanswered fact hold the lot. A zone gated on a
    # district its layer never traces for that zone would leave every lot
    # in it unanswered -- a blanket YELLOW, not a cut. None is.
    rules = load_trusted(strict=False).rules
    layers = rules.layers
    loose = []
    for lid, layer in layers.items():
        for zone in layer.zones:
            for name in rules.resolve(lid, zone).gate_levers:
                if name not in DRAWN_CONDITIONS:
                    continue
                areas = [a for a in (layer.drawn_areas or {}).values() if a.condition == name]
                if not any(zone in a.zones for a in areas):
                    loose.append((lid, zone, name))
    assert loose == []


def test_every_gate_is_a_fact_nobody_assumes() -> None:
    # A gate on an assumed fact would turn an assumption into FACT-ASSUMED
    # wherever the gate sits; today every gate is a drawn district or a
    # design fact, and a new one should be looked at before it lands.
    rules = load_trusted(strict=False).rules
    gates = {
        name
        for lid, layer in rules.layers.items()
        for zone in layer.zones
        for name in rules.resolve(lid, zone).gate_levers
    }
    kinds = {name: (CONDITIONS[name].kind, CONDITIONS[name].assume) for name in gates}
    assert all(
        kind != "site_fact" or (name in DRAWN_CONDITIONS and assume is None)
        for name, (kind, assume) in kinds.items()
    ), kinds


def test_an_unanswered_district_is_a_fact_the_lot_leans_on(corpus) -> None:
    lot = LotFacts(lot_sqft=20_000.0, frontage_ft=86.0, lot_width_ft=86.0, lot_depth_ft=200.0)
    cut = configure(lot, pod4(), observed={EASTERN: False})
    answered = configure(lot, pod4(), observed={EASTERN: False, FRONTAGE_AREA: False})
    r = corpus.resolve(PORTLAND, "RM2", cut.conditions, lot=cut.measures)
    assert FRONTAGE_AREA in cut.leans_on(r.levers)
    assert FRONTAGE_AREA not in answered.leans_on(r.levers)


def test_a_ruleset_with_no_gate_records_none(corpus) -> None:
    assert isinstance(corpus, RuleSet)
    assert corpus.resolve(PORTLAND, "R5").gate_levers & {FRONTAGE_AREA, EASTERN} == frozenset()


# --- the bridge: both sides of the cut -----------------------------------------------


def _big(width: float, depth: float) -> dict:
    return dict(
        area_sqft=width * depth,
        frontage_ft=width,
        lot_width_ft=width,
        lot_depth_ft=depth,
        edges_json=json.dumps(
            [
                [X0, Y0, X0 + width, Y0, "F"],
                [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
                [X0 + width, Y0 + depth, X0, Y0 + depth, "R"],
                [X0, Y0 + depth, X0, Y0, "S"],
            ]
        ),
        wkb=shapely.to_wkb(shapely.box(X0 + 5, Y0 + 10, X0 + width - 5, Y0 + depth - 10)),
    )


def _rm2(corpus, policies, width: float, *, answers: dict, cut: str, bound: bool = True):
    lot = lot_from_row(row(**_big(width, 200.0), jurisdiction="portland", zone="RM2"))
    observed = {**lot.observed, **OFF_PLAN_DISTRICTS, **answers}
    observed.pop(cut, None)
    lot = dataclasses.replace(lot, observed=observed)
    (s,) = _screen_lot_once(
        lot, [pod4()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0,
        bound=bound,
    )
    return s


def _held(s) -> dict[str, int]:
    return {f.code: flag_plan.severity_of(f) for f in s.signed.flags if flag_plan.severity_of(f)}


def test_one_side_of_the_cut_fails_so_the_cut_lot_is_yellow_and_names_the_district(
    corpus, policies
) -> None:
    # 86 ft of frontage, 200 ft deep: inside Map 120-2 the site owes 90 ft
    # (no neighbour exception) and is RED; outside nothing asks it. Cut by
    # the line, the lot was screened as if outside -- untested -- and could
    # be GREEN. It is now held YELLOW, the district named.
    answers = {EASTERN: False, "pdx_site_frontage_neighbour_exception": False}
    inside = _rm2(corpus, policies, 86.0, answers={**answers, FRONTAGE_AREA: True}, cut="(none)")
    assert inside.signed.colour is flag_plan.Colour.red
    assert [b.check for b in inside.signed.binds] == ["min_frontage_ft"]
    cut = _rm2(corpus, policies, 86.0, answers=answers, cut=FRONTAGE_AREA)
    assert cut.signed.colour is flag_plan.Colour.yellow
    assert not cut.signed.binds
    assert _held(cut)["FACT-PDX-MIN-SITE-FRONTAGE-AREA"] >= flag_plan.colour_rules().yellow_at_severity


def test_every_side_of_the_cut_clears_so_the_cut_lot_answers_as_an_answered_one(
    corpus, policies
) -> None:
    # Map 120-3's Eastern Pattern Area caps vehicle area in the rear setback;
    # on a 100 x 200 lot the plan clears it inside and out, so the district's
    # flag drops to 0 and the cut lot screens exactly as an answered one.
    answers = {FRONTAGE_AREA: False}
    cut = _rm2(corpus, policies, 100.0, answers=answers, cut=EASTERN)
    outside = _rm2(corpus, policies, 100.0, answers={**answers, EASTERN: False}, cut="(none)")
    inside = _rm2(corpus, policies, 100.0, answers={**answers, EASTERN: True}, cut="(none)")
    assert cut.signed.colour == outside.signed.colour == inside.signed.colour
    assert "FACT-PDX-EASTERN-PATTERN-AREA" not in _held(cut)
    assert any(f.code == "FACT-PDX-EASTERN-PATTERN-AREA" for f in cut.signed.flags)
    assert _held(cut) == _held(outside)


def test_a_cut_nobody_bounds_is_yellow_and_names_the_district(corpus, policies) -> None:
    # Unbounded (or past BOUND_FACTS), nobody tried the other side: the lot
    # is held on the unanswered district, never let through on it.
    s = _rm2(corpus, policies, 100.0, answers={FRONTAGE_AREA: False}, cut=EASTERN, bound=False)
    assert s.signed.colour is not flag_plan.Colour.green
    assert _held(s)["FACT-PDX-EASTERN-PATTERN-AREA"] >= flag_plan.colour_rules().yellow_at_severity


# --- the screen's own traced-area reviews ----------------------------------------------


def _edge_midpoint(area) -> Point:
    geoms = getattr(area, "geoms", [area])
    ring = max(geoms, key=lambda g: g.area).exterior
    coords = list(ring.coords)
    a, b = max(zip(coords, coords[1:]), key=lambda ab: Point(ab[0]).distance(Point(ab[1])))
    return Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _review_file(layers) -> str:
    (area,) = [a for a in layers[WASHINGTON].drawn_areas.values() if a.condition == PLAN_REVIEW]
    return area.file


def test_every_screen_applied_area_but_the_active_use_streets_is_a_drawn_one() -> None:
    # The Active Use Streets are read per street line (flats.geom.active_use),
    # not traced as an area, and their record sits below the yellow line.
    assert (set(AREA_REVIEWS) | set(AREA_FLAGS)) - {"hillsboro_active_use_street"} <= set(
        DRAWN_CONDITIONS
    )


def test_a_lot_a_review_area_cuts_is_named_cut(trusted) -> None:
    layers = trusted.rules.layers
    area = load_area(_review_file(layers))
    lot = _edge_midpoint(area).buffer(10)
    assert OUTSIDE_SHARE < share_inside(lot, area) < INSIDE_SHARE
    r = row(jurisdiction="washington_unincorporated", zone="R-9", lot_wkb=shapely.to_wkb(lot))
    observed = observed_facts(r, layers)
    assert PLAN_REVIEW not in observed
    assert drawn_cut(r, layers, observed) == (PLAN_REVIEW,)


def test_a_lot_wholly_inside_or_outside_is_not_cut(trusted) -> None:
    layers = trusted.rules.layers
    area = load_area(_review_file(layers))
    geoms = getattr(area, "geoms", [area])
    inside = max(geoms, key=lambda g: g.area).representative_point().buffer(3)
    minx, miny, _, _ = area.bounds
    outside = shapely.box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    for lot, answer in ((inside, True), (outside, False)):
        r = row(jurisdiction="washington_unincorporated", zone="R-9", lot_wkb=shapely.to_wkb(lot))
        observed = observed_facts(r, layers)
        assert observed[PLAN_REVIEW] is answer
        assert drawn_cut(r, layers, observed) == ()


def test_a_cut_review_area_is_asked_as_if_inside() -> None:
    # The review only adds to what the lot is asked, so the inside reading is
    # the worse side: a closer look outside ORS 197A.400's reach, GREEN with
    # CLEAR-OBJECTIVE inside it -- as a lot wholly inside.
    lot = LotFacts(lot_sqft=10_000.0, frontage_ft=80.0, drawn_cut=(PLAN_REVIEW,))
    config = configure(lot, pod4(), observed={})
    assert PLAN_REVIEW not in config.conditions
    assert area_review(config) is None
    assert area_review(config, lot) == PLAN_REVIEW
    assert area_review(config, dataclasses.replace(lot, drawn_cut=())) is None
