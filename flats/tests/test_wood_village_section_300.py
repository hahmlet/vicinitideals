"""The container every use table in the city points at, opened.

"Additional regulations are listed in Section 300" is printed in all seven of
Wood Village's use sections, and Section 300 is not a chapter -- it is eleven
subsections of unrelated regulation. So the reference could not be ruled on
without reading what is in it, and it sat at the top of this jurisdiction's
cross-reference queue with eight binding mentions.

Two of the eleven reach this building.

**350** is the one that mattered. Table 350-1A is headed "Minimum Required
Parking Spaces in All Zones" and states Household Living, "1 - 4 units", at one
space per unit. Four stalls is roughly 1,300 square feet of a site that also has
to hold the pod and its access. The resolved number does not move -- the state
caps a city at one per unit and Wood Village asks exactly one -- but until now
every lot in this city was screened against a ceiling on what the city *may*
require with nothing on file about what it does.

**390** does not: 390.020 applies "to new multi-unit residential buildings
containing five or more units", and this is four. Fetched anyway, because an
absence established is a different thing from an absence assumed.

Reading the tables for the parking row surfaced a second gap. All three
residential tables print a minimum-density row -- .9, 4.6 and 8.7 dwellings per
net acre -- between the lot dimensions and the height, and none of them was
encoded. A floor is a standard a lot can fail.

Encoding it then exposed a third thing, which is the one worth keeping: `like:`
has no field list. The Town Center borrows MR2 by reference, so the day MR2
gained a density floor the Town Center silently gained one too, off a pointer to
a lot-size row, from a table that prints no density row in either column.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WOOD_VILLAGE = "or/multnomah/wood-village"
PARKING = f"{WOOD_VILLAGE}/350.045.required-spaces.txt"
WASTE = f"{WOOD_VILLAGE}/390.020.applicability.txt"

#: Every zone in the city. The parking table is stated by use category rather
#: than by district, which is why it is a layer default.
ALL_ZONES = ("LR 12", "LR 7.5", "MR 2", "MR 4", "TC", "NC", "C/I", "GM", "LM")

#: The residential tables that print a minimum-density row, and what they print
#: in the column this building takes.
FLOORS = (("LR 12", 0.9), ("LR 7.5", 4.6), ("MR 2", 8.7), ("MR 4", 8.7))


@pytest.fixture(scope="module")
def wood_village() -> Layer:
    return load_rules()[WOOD_VILLAGE]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- parking -----------------------------------------------------------------


def test_the_parking_table_is_in_the_store(store: ProvenanceStore) -> None:
    text = store.load(PARKING).text
    assert "Table 350-1A. Minimum Required Parking Spaces in All Zones" in text
    assert "Table 350-1B. Maximum Parking Ratios" in text


def test_it_is_a_layer_default_because_the_table_is_by_use_not_by_zone(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """"In All Zones", stated by use category. A value copied into nine zone
    blocks would be nine places to amend and nine chances to disagree."""
    held = wood_village.defaults["parking_min_per_unit"]
    assert held.value == 1
    quoted = store.quote(held.prov.quote)
    assert "Minimum Required Parking Spaces in All Zones" in quoted
    assert "1 – 4 units" in quoted or "1 - 4 units" in quoted
    assert "1 per unit" in quoted

    for zone in ALL_ZONES:
        assert "parking_min_per_unit" not in wood_village.zones[zone].values, zone


def test_every_zone_resolves_a_stall_per_unit(rules: RuleSet) -> None:
    """The state's ceiling is also one per unit, so the resolved figure is
    unchanged and the attribution still goes to OAR at equality. That is the
    preemption working as written -- `preempts: cap` yields only to a LOOSER
    local number -- and it is why this was invisible until somebody read the
    table."""
    for zone in ALL_ZONES:
        got = rules.resolve(WOOD_VILLAGE, zone)
        assert got.values["parking_min_per_unit"].value == 1.0, zone


def test_the_two_loosenings_in_that_table_are_recorded_not_encoded(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """An on-street credit and a conversion exemption. Both can only reduce the
    stalls required, and one of them is about converting a house rather than
    building a new one."""
    text = store.load(PARKING).text
    assert "A credit for on-street parking shall be granted" in text
    assert "no additional parking spaces shall be required for conversion" in text
    assert "The space must be a minimum of twenty-two (22) feet long" in text

    notes = wood_village.notes
    assert "twenty-two feet long" in notes
    assert "which is a conversion where this is new" in notes


def test_and_the_maximum_does_not_bind_household_living(store: ProvenanceStore) -> None:
    lines = store.load(PARKING).text.splitlines()
    row = next(l for l in lines if l.startswith("Household Living") and "maximum" in l)
    assert row.count("no maximum") == 2


# -- solid waste, which does not reach four units ----------------------------


def test_the_waste_standard_starts_at_five_units(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """Fetched to establish the absence rather than assume it, which is the
    second time in this corpus a queue-topping reference has resolved by
    naming a threshold this building sits under."""
    assert "390.020.applicability" in {doc.id for doc in wood_village.code}
    text = store.load(WASTE).text
    assert "new multi-unit residential buildings containing five or more units" in text


# -- the density floors nobody had read --------------------------------------


def test_all_three_residential_tables_print_a_floor(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    for zone, floor in FLOORS:
        held = wood_village.zones[zone].values["min_density_du_per_acre"]
        assert held.value == floor, zone
        quoted = store.quote(held.prov.quote)
        assert "Dwellings Per Net Acre" in quoted, zone


def test_no_denominator_is_stated_because_the_code_defines_none(
    wood_village: Layer,
) -> None:
    """"Net acre" appears once in the whole fetched corpus for this city -- in
    the row itself -- and the parenthesised (25%), (80%) and (.80) beside the
    figures are unexplained. Naming a `measured_on` fact here would be claiming
    a subtraction list nobody has read.

    Leaving it off is the stricter direction for a FLOOR, which is the only
    reason it is safe: a gross acre is never smaller than a net one, so the
    density computed against the lot's own area is never higher than the real
    one, and a lot that clears this measured grossly clears it measured net.
    """
    for zone, _ in FLOORS:
        held = wood_village.zones[zone].values["min_density_du_per_acre"]
        assert held.measured_on is None, zone
    assert '"Net acre" is defined nowhere in the fetched code' in wood_village.notes


# -- and what the borrow did with it -----------------------------------------


def test_the_town_center_states_its_own_answer_because_the_borrow_has_no_field_list(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """Table 235-2 hands three rows to MR2 by name and states height and the
    four setbacks for itself. It has no density row in either column. Without
    this the Town Center would have acquired 8.7 dwellings to the net acre the
    moment MR2 was encoded, from a pointer about lot size."""
    town_center = wood_village.zones["TC"]
    assert town_center.like is not None and town_center.like.zone == "MR 2"

    held = town_center.values["min_density_du_per_acre"]
    assert held.exempt is True
    assert held.value is None
    quoted = store.quote(held.prov.quote)
    assert "Table 235-2. Development Standards in Town Center Zone" in quoted
    assert "Minimum landscaping" in quoted
    assert "Dwellings Per Net Acre" not in quoted


def test_which_the_resolution_reports_as_answered_rather_than_missing(
    rules: RuleSet,
) -> None:
    got = rules.resolve(WOOD_VILLAGE, "TC")
    assert "min_density_du_per_acre" in got.exempted
    assert "min_density_du_per_acre" not in got.values
    assert got.missing_required == ()


def test_the_zones_that_borrow_nothing_gain_nothing(rules: RuleSet) -> None:
    """The commercial and manufacturing zones state their own tables and were
    never in the path of this. Named so that a later `like:` pointed at MR2
    fails this test rather than passing silently."""
    for zone in ("NC", "C/I", "GM", "LM"):
        got = rules.resolve(WOOD_VILLAGE, zone)
        assert "min_density_du_per_acre" not in got.values, zone
        assert "min_density_du_per_acre" not in got.exempted, zone


# -- the queue this emptied --------------------------------------------------


def test_the_container_and_seven_other_references_are_ruled(
    wood_village: Layer,
) -> None:
    """Eight of this city's ten binding references, settled from their own
    citing sentences: the container itself, non-conforming uses, cottage
    housing, manufactured homes, manufactured home parks, accessory dwellings,
    landscaping reached only through the five-or-more-unit table, and a variance
    available to detached single dwellings."""
    for ref in ("300", "640", "220.400", "340.010", "340.020", "395", "330", "660"):
        assert ref in wood_village.crossrefs, ref

    # 230.350, the commercial zones' own landscaping section, is unread, and an
    # unread reference stays in the queue.
    assert "230.350" not in wood_village.crossrefs

    # 450, Subdivisions and Partitions, was reserved here for a while on the
    # grounds that "Creation of new lots is subject to the regulations of
    # Section 450" is the split-plat path and this screen places it. It has
    # since been read and parked instead of closed, which says the same thing
    # in the vocabulary the ledger has: `later` means only a change to the
    # building brings it back, and the plat is part of the building.
    assert wood_village.crossrefs["450"].outcome == "later"
    assert not wood_village.crossrefs["450"].closed


def test_the_parked_plat_rulings_hold_only_while_no_pod_splits_a_lot(
    wood_village: Layer,
) -> None:
    """The guard the reservation above was really asking for.

    Three references across two cities -- WVDC 450, PCC 33.613 and 33.614 --
    are parked on one fact about the catalog rather than on anything in the
    codes: every pod sits on one lot, so no land division ever happens and a
    land-division chapter cannot reach it. Declare a pod with `plat:
    unit_lots` and all three become fetches on the same day. This fails then,
    which is the point of writing it down here rather than in a note.
    """
    from flats.designs.model import Plat, load_catalog

    assert all(d.plat is Plat.one_lot for d in load_catalog())
    assert "plat: unit_lots" in wood_village.crossrefs["450"]


def test_the_ruling_records_the_pointer_the_renumbering_broke(
    wood_village: Layer,
) -> None:
    """WVDC 230.310 footnote (5) reads "See Section 350 - Landscaping and
    Screening". After Ord. 2-2022, 350 is Parking and Loading and landscaping is
    330. The right subject and the wrong number is the shape of reference that
    looks settled when a reader arrives at the wrong chapter."""
    assert "went stale in the renumbering" in wood_village.crossrefs["300"]
    assert "Ord. 2-2022" in wood_village.crossrefs["300"]
