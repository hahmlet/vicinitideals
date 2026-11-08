"""Which way the front doors face (FOLLOWUPS 153).

pod80x30 has every front door on its 80 ft face (``door_face: width``). The
fit tries it with that face to the street and turned, its 30 ft end to the
street. Whether the code lets it stand turned is a per-place reading,
``entrance_faces_street``:

* ``required`` -- the doors must face the street: the fit is confined to the
  street's bearings, unflipped (:func:`flats.score.paper.faces_the_street`);
* ``alternative`` / ``not_required`` -- a turned fit stands;
* ``required_named`` -- ``required``, and the code names which of several
  streets: a corner or through lot (or one never measured) is held out of
  GREEN on ENTRANCE-STREET, never failed (round 2);
* ``unclear`` or unread -- a turned fit is held out of GREEN on
  ENTRANCE-TURNED, never failed, and the bridge also reads the lot facing
  the street, keeping the better (:func:`flats.ingest.quadfit._screen_on`).
"""

from __future__ import annotations

import dataclasses

import pytest
from shapely.geometry import box

from flats.designs.model import Orientation, load_catalog
from flats.fit.rectangle import Fit, Fitter
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.paper import (
    door_turn_deg,
    door_turned,
    entrance_street_named,
    entrance_unsettled,
    faces_the_street,
)
from flats.score.screen import ENTRANCE_STREET, ENTRANCE_TURNED, _MEASURED_FLAG, screen
from flats.tests.test_round2_rulings import facts, rules

pytestmark = pytest.mark.unit

POD = load_catalog().latest("pod80x30")
OLD = load_catalog().latest("pod56x36")


def _fit(angle: float | None, orientation: Orientation | None, *, fits: bool = True) -> Fit:
    best = 30.0 + POD.parking.court_depth_ft + 4.0
    return Fit(
        fits=fits,
        width_ft=80.0,
        depth_ft=30.0,
        best_depth_ft=best,
        slack_ft=best - 30.0,
        across_ft=max(80.0 + POD.parking.lane_width_ft, POD.court_width_ft),
        angle_deg=angle,
        orientation=orientation,
    )


def _run(fit: Fit, street: tuple[float, ...], *, corner: bool = False, through: bool = False, **values):
    return screen(
        rules(**values),
        facts(lot_sqft=12000, street_bearings=street, corner=corner, through_lot=through),
        POD,
        fit,
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )


def codes(result) -> set[str]:
    return {f.code for f in result.flags}


# --- the design and the field ---------------------------------------------------


def test_the_screened_pod_has_its_doors_on_the_wide_face() -> None:
    assert POD.door_face == "width"
    assert OLD.door_face is None


def test_required_makes_the_wide_face_face_the_street() -> None:
    assert faces_the_street(rules(entrance_faces_street="required"), POD)
    for value in ("alternative", "not_required", "unclear", None):
        assert not faces_the_street(rules(entrance_faces_street=value), POD)
    # A design with no stated door face is not confined by the doors.
    assert not faces_the_street(rules(entrance_faces_street="required"), OLD)


def test_unread_and_unclear_are_unsettled_the_rest_are_not() -> None:
    assert entrance_unsettled(rules(), POD)
    assert entrance_unsettled(rules(entrance_faces_street="unclear"), POD)
    for value in ("alternative", "not_required", "required"):
        assert not entrance_unsettled(rules(entrance_faces_street=value), POD)
    # Already facing the street for another reason: nothing to settle.
    assert not entrance_unsettled(rules(orientation_constraint="axis_required"), POD)
    assert not entrance_unsettled(rules(), OLD)


# --- which fits are turned --------------------------------------------------------


def test_the_door_face_runs_along_the_angle_when_width_facing() -> None:
    assert door_turn_deg(_fit(30.0, Orientation.width_facing), (30.0,)) == pytest.approx(0.0)
    assert door_turn_deg(_fit(30.0, Orientation.depth_facing), (30.0,)) == pytest.approx(90.0)
    assert door_turn_deg(_fit(75.0, Orientation.width_facing), (30.0,)) == pytest.approx(45.0)


def test_turned_means_more_than_45_degrees_off_every_street() -> None:
    assert not door_turned(POD, _fit(30.0, Orientation.width_facing), (30.0,))
    assert not door_turned(POD, _fit(75.0, Orientation.width_facing), (30.0,))
    assert door_turned(POD, _fit(80.0, Orientation.width_facing), (30.0,))
    assert door_turned(POD, _fit(30.0, Orientation.depth_facing), (30.0,))
    # A corner: facing either street counts.
    assert not door_turned(POD, _fit(30.0, Orientation.depth_facing), (30.0, 120.0))


def test_with_no_angle_or_streets_the_orientation_alone_decides() -> None:
    assert door_turned(POD, _fit(None, Orientation.depth_facing), ())
    assert not door_turned(POD, _fit(None, Orientation.width_facing), ())
    assert not door_turned(POD, _fit(30.0, Orientation.depth_facing, fits=False), (30.0,))
    assert not door_turned(OLD, _fit(30.0, Orientation.depth_facing), (30.0,))


# --- the screen's hold -------------------------------------------------------------


def test_a_turned_fit_under_an_unread_rule_is_held_never_failed() -> None:
    assert _MEASURED_FLAG[ENTRANCE_TURNED] == "ENTRANCE-TURNED"
    got = _run(_fit(0.0, Orientation.depth_facing), (0.0,))
    assert "ENTRANCE-TURNED" in codes(got)
    assert got.colour is not Colour.green
    assert not any(c.check == ENTRANCE_TURNED for c in got.checks)


def test_a_turned_fit_stands_where_the_code_allows_it() -> None:
    for value in ("alternative", "not_required"):
        got = _run(_fit(0.0, Orientation.depth_facing), (0.0,), entrance_faces_street=value)
        assert "ENTRANCE-TURNED" not in codes(got)


def test_a_facing_fit_is_never_held() -> None:
    got = _run(_fit(0.0, Orientation.width_facing), (0.0,))
    assert "ENTRANCE-TURNED" not in codes(got)
    unclear = _run(_fit(0.0, Orientation.width_facing), (0.0,), entrance_faces_street="unclear")
    assert "ENTRANCE-TURNED" not in codes(unclear)


def test_the_hold_alone_moves_green_to_yellow() -> None:
    facing = _run(_fit(0.0, Orientation.width_facing), (0.0,))
    turned = _run(_fit(0.0, Orientation.depth_facing), (0.0,))
    if facing.colour is Colour.green:
        assert turned.colour is Colour.yellow


# --- the confined search -------------------------------------------------------------


def test_only_confines_the_search_to_the_street_bearings() -> None:
    lot = box(0, 0, 120, 120)
    free = Fitter(lot, (0.0, 30.0, 90.0))
    facing = free.only((30.0,))
    assert facing.angles == (30.0,)
    assert {g.angle_deg for g in facing.grids} == {30.0}
    assert free.angles == (0.0, 30.0, 90.0)
    assert free.only((45.0,)).empty


# --- the readings, per place ------------------------------------------------------------


@pytest.fixture(scope="module")
def rule_set() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize(
    ("where", "zone", "value"),
    [
        ("or/multnomah/wood-village", "LR 7.5", "required_named"),
        ("or/multnomah/wood-village", "MR 4", "required_named"),
        ("or/clackamas/estacada", "D", "required_named"),
        ("or/clackamas/oregon-city", "R-6", "required"),
        ("or/multnomah/portland", "CM2", "required"),
        ("or/multnomah/portland", "RM2", "required"),
        ("or/multnomah/portland", "R5", "required"),
        ("or/multnomah/portland", "R20", "not_required"),
        ("or/multnomah/gresham", "LDR-7", "required"),
        ("or/clackamas/milwaukie", "DMU", "required"),
        ("or/clackamas/_unincorporated", "R7", "required"),
        ("or/washington/hillsboro", "R-7", "required"),
        ("or/washington/_unincorporated", "R-6 NB", "unclear"),
        ("or/washington/beaverton", "RC-OT", "required"),
        ("or/clackamas/tualatin", "RL", "not_required"),
    ],
)
def test_each_place_reads_its_own_rule(rule_set: RuleSet, where: str, zone: str, value: str) -> None:
    got = rule_set.resolve(where, zone)
    assert got.get("entrance_faces_street") == value
    assert got.values["entrance_faces_street"].prov.quote.startswith(where + "/")


def test_wood_village_confines_the_pod_to_the_street(rule_set: RuleSet) -> None:
    got = rule_set.resolve("or/multnomah/wood-village", "LR 7.5")
    assert faces_the_street(got, POD)
    assert not entrance_unsettled(got, POD)


# --- round 2: the named street, the mapped sub-areas -------------------------------


def test_a_named_street_holds_a_corner_or_through_lot_never_fails_it() -> None:
    assert _MEASURED_FLAG[ENTRANCE_STREET] == "ENTRANCE-STREET"
    facing = _fit(0.0, Orientation.width_facing)
    for kw in ({"corner": True}, {"through": True}):
        got = _run(facing, (0.0,), entrance_faces_street="required_named", **kw)
        assert "ENTRANCE-STREET" in codes(got)
        assert got.colour is not Colour.green
        assert not any(c.check == ENTRANCE_STREET for c in got.checks)
        plain = _run(facing, (0.0,), entrance_faces_street="required", **kw)
        if plain.colour is Colour.green:
            assert got.colour is Colour.yellow


def test_a_named_street_on_a_one_street_lot_is_not_held() -> None:
    got = _run(_fit(0.0, Orientation.width_facing), (0.0,), entrance_faces_street="required_named")
    assert "ENTRANCE-STREET" not in codes(got)


def test_a_named_street_on_an_unmeasured_lot_is_held() -> None:
    got = _run(_fit(0.0, Orientation.width_facing), (), entrance_faces_street="required_named")
    assert "ENTRANCE-STREET" in codes(got)


def test_plain_required_does_not_ask_which_street() -> None:
    got = _run(_fit(0.0, Orientation.width_facing), (0.0,), corner=True, entrance_faces_street="required")
    assert "ENTRANCE-STREET" not in codes(got)


def test_required_named_also_confines_the_pod_to_the_street(rule_set: RuleSet) -> None:
    for where, zone in (("or/multnomah/wood-village", "MR 2"), ("or/clackamas/estacada", "D")):
        got = rule_set.resolve(where, zone)
        assert faces_the_street(got, POD)
        assert entrance_street_named(got, POD)
        assert not entrance_unsettled(got, POD)
        assert not entrance_street_named(got, POD.model_copy(update={"door_face": None}))


@pytest.mark.parametrize(
    ("where", "zones", "condition", "value"),
    [
        ("or/clackamas/oregon-city", ("R-10", "R-8", "R-6", "R-5", "R-3.5", "R-2"), "oregon_city_park_place", "required"),
        ("or/clackamas/oregon-city", ("R-10", "R-5", "R-2"), "oregon_city_south_end", "required"),
        ("or/multnomah/portland", ("CR", "CM1", "CM2", "CM3", "CE", "CX"), "pdx_hayden_island", "required_named"),
        ("or/multnomah/portland", ("RM2",), "pdx_lombard_subdistrict_a", "required"),
    ],
)
def test_a_mapped_sub_area_takes_its_own_rule(
    rule_set: RuleSet, where: str, zones: tuple[str, ...], condition: str, value: str
) -> None:
    for zone in zones:
        inside = rule_set.resolve(where, zone, conditions=(condition,))
        assert inside.get("entrance_faces_street") == value, zone
        outside = rule_set.resolve(where, zone)
        # Round 3 (rulings.yaml 2026-11-08-no-porch-end-door): the base rule is
        # required too, so outside the sub-area only the named street differs.
        assert outside.get("entrance_faces_street") == "required", zone


def test_the_sub_area_outlines_are_held_for_their_zones() -> None:
    layers = load_rules()
    pdx = layers["or/multnomah/portland"].drawn_areas
    assert pdx["hayden_island"].condition == "pdx_hayden_island"
    assert set(pdx["hayden_island"].zones) == {"CR", "CM1", "CM2", "CM3", "CE", "CX"}
    assert pdx["lombard_subdistrict_a"].condition == "pdx_lombard_subdistrict_a"
    assert set(pdx["lombard_subdistrict_a"].zones) == {"RM2"}


def test_a_turned_fit_can_carry_the_lot_facts_bearings() -> None:
    lot = dataclasses.replace(facts(), street_bearings=(12.5,))
    assert lot.street_bearings == (12.5,)


# --- the bridge: the lot read facing the street too ----------------------------------


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _bridge(corpus, policies, wide: float, deep: float):
    import json

    import shapely

    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.tests.test_fire import X0, Y0, bridge_row

    edges = [
        [X0, Y0, X0 + wide, Y0, "F"],
        [X0 + wide, Y0, X0 + wide, Y0 + deep, "S"],
        [X0 + wide, Y0 + deep, X0, Y0 + deep, "R"],
        [X0, Y0 + deep, X0, Y0, "S"],
    ]
    row = bridge_row(
        TLID="1S2E20AA  -99153",
        zone="R5",
        area_sqft=wide * deep,
        lot_depth_ft=deep,
        frontage_ft=wide,
        lot_width_ft=wide,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + wide - 5, Y0 + deep - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + wide, Y0 + deep)),
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(lot, [POD], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    return s


def test_where_the_rule_is_unsettled_the_bridge_reads_the_building_facing_the_street(
    corpus, policies, monkeypatch
) -> None:
    from flats.ingest import quadfit

    # Portland R5 reads `alternative`; force the bridge's unsettled branch and
    # call every free fit turned, so the facing reading is always tried, and
    # watch it come back and win the tie (it carries no hold).
    monkeypatch.setattr(quadfit, "entrance_unsettled", lambda rules, design: True)
    monkeypatch.setattr(quadfit, "door_turned", lambda design, fit, bearings: True)
    tried = []
    real = quadfit._facing_reading

    def spy(*args, **kwargs):
        got = real(*args, **kwargs)
        tried.append(got)
        return got

    monkeypatch.setattr(quadfit, "_facing_reading", spy)
    s = _bridge(corpus, policies, 140.0, 140.0)
    assert tried and all(t is not None for t in tried)
    assert s.fit.fits
    assert s.fit.orientation is Orientation.width_facing
    assert any(abs(s.fit.angle_deg - b) < 1e-6 for b in s.lot.front_bearings)


def test_where_only_the_turned_building_fits_and_the_doors_must_face_the_street_it_fails(
    corpus, policies
) -> None:
    # Portland R5 is `required` since round 3 (rulings.yaml
    # 2026-11-08-no-porch-end-door): 95 ft of lot, 85 ft of envelope, and the
    # pod stands only end-on -- which the code no longer lets it.
    s = _bridge(corpus, policies, 95.0, 200.0)
    assert not s.fit.fits


def test_where_only_the_turned_building_fits_the_turned_fit_stands(corpus, policies, monkeypatch) -> None:
    from flats.ingest import quadfit
    from flats.score import screen as screen_mod

    # An unsettled rule (as Hillsboro's was before round 3): the turned fit is
    # kept, and held out of GREEN.
    monkeypatch.setattr(quadfit, "entrance_unsettled", lambda rules, design: True)
    monkeypatch.setattr(quadfit, "faces_the_street", lambda rules, design: False)
    monkeypatch.setattr(screen_mod, "faces_the_street", lambda rules, design: False)
    # 95 ft of lot, 85 ft of envelope: the pod stands only end-on.
    s = _bridge(corpus, policies, 95.0, 200.0)
    assert s.fit.fits
    assert door_turned(POD, s.fit, s.lot.front_bearings)
