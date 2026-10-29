"""Gresham's Downtown Commercial Core (DCC) and Transit Mid-Rise (DTM) as townhouses.

Table 4.1120 reads L1 for a quadplex in both -- a one-lot plex only on a small
legacy lot, two of whose gates nothing measures -- and P for a Townhouse.
Until districts chunk 5 (2026-10-29) the pod was refused in both on the L1
gates. It now opens as four townhouses on four unit lots, read as DMU was in
chunk 4 (Steph 2026-10-15, "'Townhomes' will have separate lots"): the
"Townhouse in DCC, DMU, DTM, DEM, and DCL" row of Table 4.1130, and Map
4.1140's street types, which flats.geom.street_types now answers for these
two districts as well.

What is guarded: the one-lot plex is unchanged; the townhouse plat opens
and the street-type bar shuts it again, including where the plex gates would
also hold; no set of facts leaves two variants tying; the townhouse row's own
numbers replace the plex row's under ``unit_lots``; and on a lot, a Downtown
Local frontage opens the townhouse form while an Urban Boulevard alone is RED
on the use.
"""

from __future__ import annotations

import itertools

import pytest

from flats.geom.street_types import CONDITION, SERVES, ZONES, observed_street_types
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import Colour
from flats.tests.test_gresham_townhouse_zones import _downtown
from flats.tests.test_street_types import FRONT, REAR, SIDE_E, SIDE_W, lot
from flats.tests.test_townhouse_lots import corpus, policies  # noqa: F401

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
ZONES_OPENED = ("DCC", "DTM")
BARRED = CONDITION
#: The plex gates each district's L1 note names.
GATES = {
    "DCC": ("inside_mapped_use_area", "narrow_frontage"),
    "DTM": ("narrow_frontage",),
}


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def _use(rules: RuleSet, zone: str, active: tuple[str, ...], sqft: float = 6000.0):
    got = rules.resolve(GRESHAM, zone, active, {"lot_sqft": sqft}).values[
        "quadplex_allowed"
    ]
    assert not got.ambiguous, (zone, active, got.ambiguous)
    return got


@pytest.mark.parametrize("zone", ZONES_OPENED)
def test_the_townhouse_plat_opens_and_the_one_lot_plex_does_not(rules, zone) -> None:
    assert _use(rules, zone, ()).value is False
    split = _use(rules, zone, ("unit_lots",))
    assert split.value is True
    assert BARRED in split.levers


@pytest.mark.parametrize("zone", ZONES_OPENED)
def test_the_street_type_bar_outranks_the_plex_gates(rules, zone) -> None:
    """A barring street shuts the townhouse plat even on a lot small enough,
    and gated enough, for the one-lot plex variant to fire."""
    gates = GATES[zone]
    assert _use(rules, zone, ("unit_lots", BARRED)).value is False
    assert _use(rules, zone, ("unit_lots", BARRED, *gates)).value is False
    # The plex variant itself is untouched: its gates still open one lot.
    assert _use(rules, zone, gates).value is True


FACTS = (
    "unit_lots",
    BARRED,
    "inside_mapped_use_area",
    "narrow_frontage",
    "alley_at_rear",
    "abuts_lower_density_zone",
    "corner_lot",
)


@pytest.mark.parametrize("zone", ZONES_OPENED)
def test_no_set_of_facts_leaves_two_variants_tying(zone) -> None:
    block = load_rules()[GRESHAM].zones[zone]
    for sqft in (5500.0, 9000.0):
        for n in range(len(FACTS) + 1):
            for active in itertools.combinations(FACTS, n):
                for field, value in block.values.items():
                    got = value.under(active, {"lot_sqft": sqft})
                    assert not got.ambiguous, (zone, field, active, sqft, got.ambiguous)


@pytest.mark.parametrize("zone", ZONES_OPENED)
def test_unit_lots_take_the_townhouse_row(rules, zone) -> None:
    def v(active: tuple[str, ...], field: str):
        return (
            rules.resolve(GRESHAM, zone, active, {"lot_sqft": 9000.0})
            .values[field]
            .value
        )

    th = ("unit_lots",)
    # The plex row's 20 ft garage and 6 ft alley rear stay on one lot ...
    assert v((), "setback_garage_entrance_ft") == 20
    assert v(("alley_at_rear",), "setback_rear_ft") == 6
    # ... and the townhouse row prints its own.
    assert v(th, "setback_garage_entrance_ft") == 15
    assert v(th, "setback_front_ft") == 10
    assert v(th, "setback_street_side_ft") == 10
    assert v(th, "setback_side_ft") == 5
    assert v((*th, "abuts_lower_density_zone"), "setback_side_ft") == 10
    assert v(th, "setback_rear_ft") == 10
    assert v((*th, "alley_at_rear"), "setback_rear_ft") == 3
    assert (
        v((*th, "alley_at_rear", "abuts_lower_density_zone"), "setback_rear_ft") == 10
    )
    assert v((), "orientation_constraint") == "axis_required"
    assert v(th, "orientation_constraint") == "entrance_only"
    assert v(th, "review_discretion") == "judgement"


def test_the_traced_street_types_answer_dcc_and_dtm() -> None:
    """The five districts the townhouse row names, and not the DRL pair
    (whose quadplex is P on one lot). The screening tests below show the
    answer arriving on a real lot: no FACT flag, and RED on a boulevard."""
    assert {"DCC", "DTM", "DMU", "DEM", "DCL"} == ZONES
    edges = lot(FRONT, SIDE_E, REAR, SIDE_W)
    assert observed_street_types(edges, SERVES, "DRL-1") == {}


@pytest.mark.parametrize("zone", ZONES_OPENED)
def test_a_lot_on_a_downtown_local_street_opens_as_townhouses(
    corpus, policies, zone
) -> None:  # noqa: F811
    # 30 ft north of NE 8th St's centreline: Downtown Local on Map 4.1140.
    colour, binds, codes = _downtown(corpus, policies, 7_708_700.0, 675_373.0, zone)
    assert "FACT-GRESHAM-DOWNTOWN-BARRED-STREET" not in codes
    assert "use" not in binds
    assert colour is not Colour.red
    assert "CLEAR-OBJECTIVE" in codes


@pytest.mark.parametrize("zone", ZONES_OPENED)
def test_a_lot_on_an_urban_boulevard_alone_is_red_on_the_use(
    corpus, policies, zone
) -> None:  # noqa: F811
    # 30 ft north of E Powell Blvd, no other street and no alley.
    colour, binds, _ = _downtown(corpus, policies, 7_708_000.0, 673_581.0, zone)
    assert colour is Colour.red
    assert "use" in binds
