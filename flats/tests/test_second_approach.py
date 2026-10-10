"""Oregon City 16.12.035.F: one driveway approach for every two townhouses.

Steph ruled 2026-09-30 that the sentence is a REQUIREMENT, so the four-unit
pod needs two approaches where the plan draws one shared drive. Nothing holds
a second approach's geometry (FOLLOWUPS 25), so the screen asks a closer look
(``CLOSER_LOOK_SECOND_APPROACH`` / ``DRIVEWAY-SECOND-APPROACH``): never GREEN,
never a miss, and only where the code states the requirement.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import load_catalog  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
from flats.rules.fields import FIELDS, OPTIONAL_FIELDS  # noqa: E402
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved, ZoneResolution  # noqa: E402
from flats.rules.resolver import Verdict as RuleVerdict  # noqa: E402
from flats.score import flags as flag_plan  # noqa: E402
from flats.score import screen as screen_module  # noqa: E402
from flats.score.paper import court_across  # noqa: E402
from flats.score.screen import (  # noqa: E402
    CLOSER_LOOK_SECOND_APPROACH,
    LotFacts,
    Triage,
    approaches_missing,
    screen,
)
from flats.score.slack import SlackPolicy  # noqa: E402

pytestmark = pytest.mark.unit

WHERE = "or/clackamas/oregon-city"
PROV = Provenance(cite="OCMC 16.12.035.F", url="https://example.invalid", retrieved=date(2026, 10, 10))
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})
DESIGN = load_catalog().latest("pod56x36")

CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "setback_front_ft": 10,
    "setback_rear_ft": 10,
    "setback_side_ft": 5,
    "min_frontage_ft": 20,
    "min_lot_width_ft": 20,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 60,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}


def rules(**overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R-6",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name, value=value, status=Status.verified, prov=PROV,
                layer=WHERE, origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit(lane: float, depth_ft: float = 36.0) -> Fit:
    best = depth_ft + DESIGN.parking.court_depth_ft + 4.0
    return Fit(
        fits=True, width_ft=56.0, depth_ft=depth_ft, best_depth_ft=best,
        slack_ft=best - depth_ft,
        across_ft=max(56.0 + lane, DESIGN.court_width_ft),
    )


def run(zone: ZoneResolution, *, lot_sqft: float = 12000.0, frontage: float = 80.0):
    lane = court_across(DESIGN, zone).lane_ft
    return screen(
        zone,
        LotFacts(lot_sqft=lot_sqft, frontage_ft=frontage, lot_width_ft=frontage),
        DESIGN, fit(lane), policy=POLICY,
    )


def test_the_four_unit_pod_needs_two_approaches_at_one_per_two_units() -> None:
    assert DESIGN.units == 4
    assert approaches_missing(rules(driveway_units_per_approach=2), DESIGN) == 1


def test_a_plan_that_holds_the_approaches_the_code_asks_is_unchanged() -> None:
    # One approach for every four units is the one drive the plan draws.
    zone = rules(driveway_units_per_approach=4)
    assert approaches_missing(zone, DESIGN) == 0
    got = run(zone)
    assert got.triage is Triage.green and got.reasons == ()
    assert not [f for f in got.flags if f.code == "DRIVEWAY-SECOND-APPROACH"]


def test_a_plan_that_draws_two_approaches_clears_the_question(monkeypatch) -> None:
    monkeypatch.setattr(screen_module, "PLAN_APPROACHES", 2)
    got = run(rules(driveway_units_per_approach=2))
    assert got.triage is Triage.green and got.reasons == ()


def test_a_second_approach_nobody_can_show_fits_is_never_green() -> None:
    got = run(rules(driveway_units_per_approach=2))
    assert got.triage is Triage.yellow
    assert got.reasons == (CLOSER_LOOK_SECOND_APPROACH,)
    (flag,) = [f for f in got.flags if f.code == "DRIVEWAY-SECOND-APPROACH"]
    assert flag.bounds == (1, 2)
    assert flag.source == "OCMC 16.12.035.F"
    kind = flag_plan.registry()["DRIVEWAY-SECOND-APPROACH"]
    assert kind.severity >= flag_plan.colour_rules().yellow_at_severity
    assert got.colour is flag_plan.Colour.yellow and not got.binds


def test_a_lot_the_use_rules_out_stays_red() -> None:
    got = run(rules(driveway_units_per_approach=2, quadplex_allowed=False))
    assert got.triage is Triage.red
    assert got.colour is flag_plan.Colour.red
    assert CLOSER_LOOK_SECOND_APPROACH not in got.reasons


def test_a_city_that_states_no_requirement_is_untouched() -> None:
    zone = rules()
    assert approaches_missing(zone, DESIGN) == 0
    got = run(zone)
    assert got.triage is Triage.green and got.reasons == ()
    assert not [f for f in got.flags if f.code == "DRIVEWAY-SECOND-APPROACH"]


def test_the_field_is_optional_so_no_other_city_goes_unchecked() -> None:
    assert "driveway_units_per_approach" in FIELDS
    assert "driveway_units_per_approach" in OPTIONAL_FIELDS


def test_only_oregon_city_states_the_requirement_and_cites_the_sentence() -> None:
    layers = load_rules()
    holders = {
        name
        for name, layer in layers.items()
        if "driveway_units_per_approach" in layer.defaults
        or any("driveway_units_per_approach" in z.values for z in layer.zones.values())
    }
    assert holders == {WHERE}
    value = layers[WHERE].defaults["driveway_units_per_approach"]
    assert value.value == 2
    assert "16.12.035.F" in value.prov.cite
