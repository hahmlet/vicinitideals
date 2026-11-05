"""The rear court kept out of the rear setback in Gresham, Sandy and Troutdale
(FOLLOWUPS 150, read 2026-11-05).

Until this reading the court SHARED the rear yard in all three: the ground
behind the building's rear wall was the deeper of the court and the yard.
Each code keeps parking out of it in its own words, and the encoding is the
one Cornelius already uses (``parking_required_yard_prohibited``): the court
stands in front of the yard and the two stack.

- Gresham GDC 7.0420(B)(5)(c), the quadplex on its parent lot: parking spaces
  "in the rear yard setback when there is an alley", a closed list. The alley
  lot and the townhouse path (7.0431(B)(3)(b)(i), "located in the rear yard")
  keep the old sharing.
- Sandy SDC 17.98.50 A and Troutdale TDC 9.095 A: "Parking areas, which abut
  a residential zoning district, shall meet the setback of the most
  restrictive adjoining residential zoning district" -- read literally, with
  the stricter neighbour's yard where one adjoins.

Each test resolves the real zone from the corpus.
"""

from __future__ import annotations

import pytest
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.provenance.store import ProvenanceStore
from flats.score.paper import paper_fit
from flats.score.screen import _court_beyond_rear

pytestmark = pytest.mark.unit

FIELD = "parking_required_yard_prohibited"
STRIP = "parking_lot_line_buffer_ft"
GRESHAM = "or/multnomah/gresham"
SANDY = "or/clackamas/sandy"
TROUTDALE = "or/multnomah/troutdale"

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


class Sharing:
    """A real resolution with the rule taken out: the screen before."""

    def __init__(self, rules) -> None:
        self._rules = rules

    def get(self, name: str) -> object:
        return None if name in (FIELD, STRIP) else self._rules.get(name)

    def __getattr__(self, name: str) -> object:
        return getattr(self._rules, name)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


def quoted(value) -> str:
    return " ".join(ProvenanceStore().quote(value.prov.quote).split())


def deeper(rules) -> float:
    """How much deeper the paper lot is than when the court shared the yard."""
    return paper_fit(pod(), rules).min_depth_ft - paper_fit(pod(), Sharing(rules)).min_depth_ft


# --- Gresham --------------------------------------------------------------------


def test_gresham_cites_the_closed_list() -> None:
    from flats.rules.loader import load_rules

    held = load_rules()[GRESHAM].defaults[FIELD]
    assert held.value is True
    assert "in the rear yard setback when there is an alley" in quoted(held)


def test_a_gresham_quadplex_court_no_longer_parks_in_the_rear_setback(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", ())
    assert rules.get(FIELD) is True
    rear = float(rules.get("setback_rear_ft"))
    assert rear > 0
    assert deeper(rules) == pytest.approx(rear)
    assert _court_beyond_rear(pod(), rules) > _court_beyond_rear(pod(), Sharing(rules))


def test_a_gresham_alley_lot_keeps_todays_sharing(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", ("alley_at_rear", "abuts_alley"))
    assert rules.get(FIELD) is False
    assert deeper(rules) == pytest.approx(0)
    assert _court_beyond_rear(pod(), rules) == _court_beyond_rear(pod(), Sharing(rules))


def test_a_side_alley_does_not_open_the_gresham_rear_setback(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", ("alley_at_side", "abuts_alley"))
    assert rules.get(FIELD) is True


@pytest.mark.parametrize("conds", [("unit_lots",), ("unit_lots", "alley_at_rear", "abuts_alley")])
def test_the_gresham_townhouse_path_keeps_the_rear_yard(corpus, conds) -> None:
    rules = corpus.resolve(GRESHAM, "LDR-7", conds)
    assert rules.get(FIELD) is False
    assert not rules.ambiguous


# --- Sandy ----------------------------------------------------------------------


@pytest.mark.parametrize("zone", ["R-2", "R-3"])
def test_a_sandy_court_meets_the_rear_setback(corpus, zone: str) -> None:
    rules = corpus.resolve(SANDY, zone, ())
    assert rules.get(FIELD) is True
    assert "abut a residential zoning district" in quoted(rules.values[FIELD])
    # No stricter neighbour: the strip is the zone's own side yard, which
    # the building already keeps, and the court stacks on the 15 ft rear.
    assert rules.get(STRIP) == rules.get("setback_side_ft") == 5
    assert deeper(rules) == pytest.approx(15)


def test_a_sandy_court_beside_sfr_takes_the_sfr_rear_yard(corpus) -> None:
    rules = corpus.resolve(SANDY, "R-2", ("abuts_lower_density_zone",))
    assert rules.get(STRIP) == 20
    # The 15 ft rear stands, and the court stands 20 off the line instead.
    assert deeper(rules) == pytest.approx(20)


def test_sandy_row_houses_are_held_too(corpus) -> None:
    rules = corpus.resolve(SANDY, "R-1", ("unit_lots",))
    assert rules.get(FIELD) is True


# --- Troutdale ------------------------------------------------------------------


@pytest.mark.parametrize("zone", ["LDR-1", "LDR-2", "MDR"])
def test_a_troutdale_court_meets_the_rear_setback(corpus, zone: str) -> None:
    rules = corpus.resolve(TROUTDALE, zone, (), lot={"lot_sqft": 9000.0})
    assert rules.get(FIELD) is True
    assert "abut a residential zoning district" in quoted(rules.values[FIELD])
    assert rules.get("setback_rear_ft") == 10
    assert deeper(rules) == pytest.approx(10)


def test_a_troutdale_lot_with_no_residential_neighbour_shares(corpus) -> None:
    rules = corpus.resolve(TROUTDALE, "MU-2", ("abuts_nonresidential_zone",), lot={"lot_sqft": 9000.0})
    assert rules.get(FIELD) is False


@pytest.mark.parametrize(("zone", "strip"), [("MDR", 10), ("LDR-2", 10)])
def test_a_troutdale_quadplex_beside_ldr_takes_its_side_yard(corpus, zone: str, strip: float) -> None:
    rules = corpus.resolve(TROUTDALE, zone, ("abuts_lower_density_zone",), lot={"lot_sqft": 9000.0})
    assert rules.get(STRIP) == strip
    townhouses = corpus.resolve(
        TROUTDALE, zone, ("abuts_lower_density_zone", "unit_lots"), lot={"lot_sqft": 9000.0}
    )
    # The townhouse row prints 5 in every district: the strip is the side
    # yard already charged, so it adds nothing.
    assert townhouses.get(STRIP) == 5
    # With no stricter neighbour the strip is the zone's own quadplex side,
    # likewise already charged.
    alone = corpus.resolve(TROUTDALE, zone, (), lot={"lot_sqft": 9000.0})
    assert alone.get(STRIP) == alone.get("setback_side_ft")
