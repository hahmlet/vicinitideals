"""Clackamas unincorporated pitched roof (clackamas-roof lane, 2026-11-11).

ZDO 1005.03(F)(4): one- and two-story multifamily dwellings and middle housing
(except middle housing developed under Section 845) take hipped, gambrel or
gabled roofs; a flat roof only under mechanical equipment or as a roof garden
or other outdoor space. Steph's ruling 2026-11-11-clackamas-pitched-roof-yellow:
"Yellow + flag". A lot held only by that is YELLOW with ROOF-GARDEN, never RED
and never GREEN.
"""

from __future__ import annotations

import pytest

from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score.flags import Colour
from flats.score.screen import CLOSER_LOOK_ROOF_GARDEN, roof_garden_owed
from flats.tests.test_round2_rulings import DESIGN, facts, rules, run

pytestmark = pytest.mark.unit

COUNTY = "or/clackamas/_unincorporated"
#: Districts permitting a quadplex outside Section 845's reach (Table 315-1 and
#: Table 510-1 quadplex rows carry no note naming 845; Table 1001-1 applies
#: Section 1005 to middle housing outside R-5..R-30 and VR).
REACHED = ["PMD", "MR1", "MR2", "HDR", "SHD", "RCHDR", "SCMU", "RTL", "CC", "C3", "OC", "RCC", "RCO"]
#: Middle housing here is developed under Section 845 (Table 315-1 note [9]),
#: which 1005.03(F) excepts, and Table 1001-1 does not apply Section 1005.
EXCEPTED = ["R5", "R7", "R8.5", "R10", "R15", "R20", "R30", "VR57", "VR45"]


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def test_the_field_is_optional_and_counts_stories() -> None:
    f = field("flat_roof_outdoor_use_max_stories")
    assert f.kind == "count"
    assert "flat_roof_outdoor_use_max_stories" in OPTIONAL_FIELDS


@pytest.mark.parametrize("zone", REACHED)
def test_each_reached_district_holds_the_printed_two_stories(corpus, zone) -> None:
    got = RuleSet(corpus).resolve(COUNTY, zone)
    assert got.get("flat_roof_outdoor_use_max_stories") == 2
    assert "1005.03(F)(4)" in got.values["flat_roof_outdoor_use_max_stories"].prov.cite
    # A roof garden is a way out, not a ban: no pitch is required.
    assert got.get("min_roof_pitch_in_12") is None


@pytest.mark.parametrize("zone", EXCEPTED)
def test_section_845_districts_carry_no_roof_garden_rule(corpus, zone) -> None:
    assert RuleSet(corpus).resolve(COUNTY, zone).get("flat_roof_outdoor_use_max_stories") is None


def test_va_stays_red_on_its_own_flat_roof_ban(corpus) -> None:
    got = RuleSet(corpus).resolve(COUNTY, "VA")
    assert got.get("min_roof_pitch_in_12") == 1


def test_a_flat_two_story_pod_is_yellow_with_its_flag() -> None:
    got = run(facts(), rules(flat_roof_outdoor_use_max_stories=2))
    assert got.colour is Colour.yellow and not got.binds
    assert CLOSER_LOOK_ROOF_GARDEN in got.reasons
    assert [f.code for f in got.flags if f.code == "ROOF-GARDEN"] == ["ROOF-GARDEN"]
    kind = flag_plan.registry()["ROOF-GARDEN"]
    assert kind.severity >= flag_plan.colour_rules().yellow_at_severity


def test_no_roof_garden_rule_stays_green() -> None:
    got = run(facts(), rules())
    assert got.colour is Colour.green
    assert CLOSER_LOOK_ROOF_GARDEN not in got.reasons
    assert not [f for f in got.flags if f.code == "ROOF-GARDEN"]


def test_a_lot_the_use_rules_out_stays_red() -> None:
    got = run(facts(), rules(flat_roof_outdoor_use_max_stories=2, quadplex_allowed=False))
    assert got.colour is Colour.red


def test_a_pitched_or_taller_pod_owes_no_roof_garden() -> None:
    zone = rules(flat_roof_outdoor_use_max_stories=2)
    assert DESIGN.stories == 2 and DESIGN.roof_pitch_in_12 == 0
    assert roof_garden_owed(zone, DESIGN) == 2
    assert roof_garden_owed(zone, DESIGN.model_copy(update={"roof_pitch_in_12": 6})) is None
    assert roof_garden_owed(zone, DESIGN.model_copy(update={"stories": 3})) is None
