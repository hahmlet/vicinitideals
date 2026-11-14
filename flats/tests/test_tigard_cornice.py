"""Tigard flat-roof cornice (roof-ban lane, 2026-11-10).

Tigard CDC 18.280.040.J lets a rowhouse roof be flat only with a cornice at
least 12 inches tall (or a small roof deck). Steph's ruling
2026-11-10-tigard-cornice-yellow: "tigard, yellow with flag". A lot held only
by that requirement is YELLOW with ROOF-CORNICE, never RED and never GREEN.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score.flags import Colour
from flats.score.screen import CLOSER_LOOK_ROOF_CORNICE, cornice_owed
from flats.tests.test_round2_rulings import DESIGN, facts, rules, run

pytestmark = pytest.mark.unit

TIGARD = "or/washington/tigard"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def test_the_field_is_optional_and_counts_inches() -> None:
    f = field("flat_roof_cornice_min_in")
    assert f.kind == "count"
    assert "flat_roof_cornice_min_in" in OPTIONAL_FIELDS


@pytest.mark.parametrize("zone", ["RES-A", "RES-B", "RES-C", "RES-D", "RES-E", "MUR", "MUC"])
def test_each_rowhouse_zone_holds_the_printed_12_inches(corpus, zone) -> None:
    got = RuleSet(corpus).resolve(TIGARD, zone)
    assert got.get("flat_roof_cornice_min_in") == 12
    # A cornice is an alternative, not a ban: no pitch is required.
    assert got.get("min_roof_pitch_in_12") is None


@pytest.mark.parametrize("zone", ["MU-CBD", "TMU"])
def test_zones_outside_the_rowhouse_chapter_carry_no_cornice(corpus, zone) -> None:
    assert RuleSet(corpus).resolve(TIGARD, zone).get("flat_roof_cornice_min_in") is None


def test_a_flat_roof_owed_a_cornice_is_yellow_with_its_flag() -> None:
    got = run(facts(), rules(flat_roof_cornice_min_in=12))
    assert got.colour is Colour.yellow and not got.binds
    assert CLOSER_LOOK_ROOF_CORNICE in got.reasons
    (flag,) = [f for f in got.flags if f.code == "ROOF-CORNICE"]
    assert flag.bounds == (0.0, 12.0)
    kind = flag_plan.registry()["ROOF-CORNICE"]
    assert kind.severity >= flag_plan.colour_rules().yellow_at_severity


def test_no_cornice_rule_stays_green() -> None:
    got = run(facts(), rules())
    assert got.colour is Colour.green
    assert CLOSER_LOOK_ROOF_CORNICE not in got.reasons
    assert not [f for f in got.flags if f.code == "ROOF-CORNICE"]


def test_a_lot_the_use_rules_out_stays_red() -> None:
    got = run(facts(), rules(flat_roof_cornice_min_in=12, quadplex_allowed=False))
    assert got.colour is Colour.red


def test_a_pitched_pod_owes_no_cornice() -> None:
    zone = rules(flat_roof_cornice_min_in=12)
    assert cornice_owed(zone, DESIGN) == 12.0
    pitched = DESIGN.model_copy(update={"roof_pitch_in_12": 6})
    assert cornice_owed(zone, pitched) is None
    assert load_catalog().latest("pod56x36").roof_pitch_in_12 == 0
