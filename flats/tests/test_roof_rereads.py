"""Roof re-reads (roof-rereads lane, FOLLOWUPS 181(b), 2026-11-11).

Two of the four uncertain roof readings the roof-ban lane left change the
screen:

* Tualatin TDC 73A.030(1)(b) asks the street face for at least three of
  73A.040's six Residential Roof Design Elements. Half the menu needs a
  pitched roof; a flat roof reaches three only with add-ons (eaves, an
  overhang, roof planes at different heights) the pod's catalog does not
  show. A flat roof allowed with a design add-on is YELLOW with a flag
  (rulings.yaml 2026-11-10-tigard-cornice-yellow): ROOF-ELEMENTS.
* Wilsonville WC 4.125(.23)(C) binds middle housing in the Village zone to
  the Villebois Architectural Pattern Book's Architectural Styles, a book the
  corpus does not hold. Unread is held YELLOW: ROOF-STYLE-BOOK-UNREAD.

Hillsboro's Downtown Plan District trace is tested with the other design
districts (test_design_district_building.py).
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score.flags import Colour
from flats.score.screen import (
    CLOSER_LOOK_ROOF_BOOK,
    CLOSER_LOOK_ROOF_ELEMENTS,
    roof_book_unread,
    roof_elements_owed,
)
from flats.tests.test_round2_rulings import DESIGN, facts, rules, run

pytestmark = pytest.mark.unit

TUALATIN = "or/clackamas/tualatin"
WILSONVILLE = "or/clackamas/wilsonville"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def test_the_fields_are_optional() -> None:
    assert field("roof_design_elements_min").kind == "count"
    assert field("roof_style_book_unread").kind == "bool"
    assert {"roof_design_elements_min", "roof_style_book_unread"} <= set(OPTIONAL_FIELDS)


def test_the_pod_roof_is_flat() -> None:
    assert load_catalog().latest("pod56x36").roof_pitch_in_12 == 0


# --- Tualatin ---------------------------------------------------------------


@pytest.mark.parametrize("zone", ["RL", "RML", "RMH", "RH"])
def test_tualatin_residential_zones_ask_three_roof_elements(corpus, zone) -> None:
    got = RuleSet(corpus).resolve(TUALATIN, zone)
    assert got.get("roof_design_elements_min") == 3
    # A menu with flat-roof options, not a ban: no pitch is required.
    assert got.get("min_roof_pitch_in_12") is None


def test_a_flat_roof_owed_roof_elements_is_yellow_with_its_flag() -> None:
    got = run(facts(), rules(roof_design_elements_min=3))
    assert got.colour is Colour.yellow and not got.binds
    assert CLOSER_LOOK_ROOF_ELEMENTS in got.reasons
    (flag,) = [f for f in got.flags if f.code == "ROOF-ELEMENTS"]
    assert flag.bounds == (0.0, 3.0)
    kind = flag_plan.registry()["ROOF-ELEMENTS"]
    assert kind.severity >= flag_plan.colour_rules().yellow_at_severity


def test_a_pitched_pod_owes_no_roof_elements() -> None:
    zone = rules(roof_design_elements_min=3)
    assert roof_elements_owed(zone, DESIGN) == 3
    pitched = DESIGN.model_copy(update={"roof_pitch_in_12": 6})
    assert roof_elements_owed(zone, pitched) is None


def test_roof_elements_never_lift_a_red() -> None:
    got = run(facts(), rules(roof_design_elements_min=3, quadplex_allowed=False))
    assert got.colour is Colour.red


# --- Wilsonville Villebois ------------------------------------------------------


def test_villebois_holds_the_unread_style_book(corpus) -> None:
    got = RuleSet(corpus).resolve(WILSONVILLE, "V")
    assert got.get("roof_style_book_unread") is True
    # The rest of Wilsonville is not bound to the book.
    assert RuleSet(corpus).resolve(WILSONVILLE, "R").get("roof_style_book_unread") is None


def test_an_unread_style_book_is_yellow_with_its_flag() -> None:
    got = run(facts(), rules(roof_style_book_unread=True))
    assert got.colour is Colour.yellow and not got.binds
    assert CLOSER_LOOK_ROOF_BOOK in got.reasons
    assert [f for f in got.flags if f.code == "ROOF-STYLE-BOOK-UNREAD"]
    kind = flag_plan.registry()["ROOF-STYLE-BOOK-UNREAD"]
    assert kind.severity >= flag_plan.colour_rules().yellow_at_severity


def test_no_book_stays_green() -> None:
    got = run(facts(), rules())
    assert got.colour is Colour.green
    assert CLOSER_LOOK_ROOF_BOOK not in got.reasons


def test_a_pitched_pod_is_not_held_by_the_book() -> None:
    zone = rules(roof_style_book_unread=True)
    assert roof_book_unread(zone, DESIGN)
    assert not roof_book_unread(zone, DESIGN.model_copy(update={"roof_pitch_in_12": 6}))
