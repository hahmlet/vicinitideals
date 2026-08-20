"""Fairview's four village zones, and the word that decides all of them.

VMU, VC, VA and VO -- 74 lots. Three of the four print a `P` on a row reading
"Multi-unit dwellings", and none of those P's belongs to this building, because
FMC 19.13 defines a multi-unit dwelling as "a building containing five or more
dwelling units". A quadplex is four. Read the P as the permission and every
village zone in this city screens green on a standard that does not apply.

What does reach the pod is the row under it -- "Attached single-unit dwellings"
in VC and VMU, "townhouses" in VA's one-line conditional list -- and it is a
conditional use in all three. The variants therefore ask for the permit, and
for the land division as well: on four lots the units are unambiguously
attached single-unit dwellings, and on one lot they are a quadplex, which this
code defines separately and puts on no village list at all.

The four zones then diverge on everything else. VMU is told to be occupied by
townhomes; VC is told every first floor belongs to commerce; VA is the one
zone in the city with a density FLOOR; VO has no residential use anywhere on
its list and no relief at all. VC and VMU share a chapter, a use table and
three dimensions and still do not share an answer.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

FAIRVIEW = "or/multnomah/fairview"
POD = ("multi_story", "attached_wall")
VILLAGE = ("VMU", "VC", "VA", "VO")
#: The three the conditional-use door is open in. VO is not one of them.
CONDITIONAL = ("VMU", "VC", "VA")


@pytest.fixture(scope="module")
def fairview() -> Layer:
    return load_rules()[FAIRVIEW]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_every_village_zone_refuses_the_pod_outright(rules: RuleSet) -> None:
    for zone in VILLAGE:
        res = rules.resolve(FAIRVIEW, zone, POD)
        assert res.values["quadplex_allowed"].value is False, zone
        assert res.missing_required == (), zone


def test_the_permission_row_counts_to_five_and_the_pod_is_four(
    fairview: Layer,
) -> None:
    """The whole slice turns on this definition.

    "Multi-unit dwelling" means five or more units here, so the P on that row
    is not this building's P. Three zones print it and a screen that matched
    the mark would open all three.
    """
    text = ProvenanceStore().quote(
        "or/multnomah/fairview/19.13.definitions.txt#L383,L465,L515"
    )
    assert "five or more dwelling units" in text
    assert "four dwelling units on a lot or parcel" in text
    assert "common end-walls" in text

    for zone in ("VMU", "VC"):
        cited = ProvenanceStore().quote(
            fairview.zones[zone].values["quadplex_allowed"].prov.quote
        )
        assert "Multi-unit dwellings" in cited, zone
        assert "Attached single-unit dwellings" in cited, zone


def test_the_door_asks_for_a_land_division_as_well_as_a_permit(
    fairview: Layer, rules: RuleSet,
) -> None:
    """`unit_lots` is in every village variant on purpose.

    On four lots the pod is attached single-unit dwellings and the answer is a
    conditional use. On one lot it is a quadplex -- a term this code defines
    separately and gives its own table row in the TCC chapter -- and no village
    list mentions it. Asking for the division is the conservative of the two
    readings.
    """
    for zone in CONDITIONAL:
        variants = fairview.zones[zone].values["quadplex_allowed"].variants
        assert len(variants) == 1, zone
        assert "unit_lots" in variants[0].when, zone
        assert "conditional_use" in variants[0].when, zone

    opened = rules.resolve(FAIRVIEW, "VMU", (*POD, "unit_lots", "conditional_use"))
    assert opened.values["quadplex_allowed"].value is True


def test_village_office_is_the_one_refusal_with_no_way_out(
    fairview: Layer,
) -> None:
    """No residential use anywhere on a closed list, and no similar-use door.

    19.130.030 is one sentence -- "Other uses when found similar to those above
    by planning commission" -- and a four-unit townhome is not similar to an
    office. So this zone owns the use flag and nothing else, while VC next door
    carries a relief nobody can reach.
    """
    held = fairview.zones["VO"].values["quadplex_allowed"]
    assert held.value is False
    assert held.variants == ()
    assert set(fairview.zones["VO"].values) == {"quadplex_allowed"}

    text = ProvenanceStore().quote(held.prov.quote)
    assert "permitted in a VO zone" in text
    assert "found similar to those above" in text


def test_the_loosest_dimensions_in_the_city_belong_to_a_closed_zone(
    fairview: Layer,
) -> None:
    """55 feet of height and "no setback requirements in the VO zone".

    Encoding those would make the district look answerable and generous. It is
    neither: the use list closes it, and a screen that reached the dimensions
    before the list would find nothing there to stop the building.
    """
    notes = fairview.zones["VO"].notes or ""
    assert "no setback requirements in the VO zone" in notes
    assert "55 feet" in notes


def test_two_zones_share_a_table_and_do_not_share_an_answer(
    fairview: Layer,
) -> None:
    """VC and VMU are one chapter, one use table, three identical dimensions.

    They part on 19.135.030(A): VMU "shall be occupied by townhomes and
    commercial uses", VC requires every first floor to be "occupied
    exclusively by commercial/office uses". Only VC's citation reaches that
    sentence, and only VC's relief needs the mapped flex area where the code
    lets residential onto the ground floor.
    """
    vc = fairview.zones["VC"]
    vmu = fairview.zones["VMU"]

    assert vc.values["max_height_ft"].value == vmu.values["max_height_ft"].value == 45
    assert vc.values["max_coverage_pct"].value == vmu.values["max_coverage_pct"].value

    vc_text = ProvenanceStore().quote(vc.values["quadplex_allowed"].prov.quote)
    assert "occupied exclusively by commercial/office uses" in vc_text
    assert "VC flex" in vc_text

    assert "inside_mapped_use_area" in vc.values["quadplex_allowed"].variants[0].when
    assert (
        "inside_mapped_use_area" not in vmu.values["quadplex_allowed"].variants[0].when
    )


def test_the_apartment_zone_is_the_only_one_with_a_density_floor(
    fairview: Layer,
) -> None:
    """Twenty units per net acre, and on a small site the floor is what binds.

    Four units may not spread over more than 8,712 square feet, while the
    thirty-unit ceiling asks for at least 5,808. A quadplex fits VA only
    between those two numbers -- the one place in this city where a lot can be
    too BIG for the building.
    """
    va = fairview.zones["VA"]
    assert va.values["min_density_du_per_acre"].value == 20
    assert va.values["max_density_du_per_acre"].value == 30

    for field in ("min_density_du_per_acre", "max_density_du_per_acre"):
        assert va.values[field].measured_on == "net_developable_area", field


def test_the_density_denominator_is_the_one_this_code_defines(
    fairview: Layer,
) -> None:
    """"Net site area" means the land less street right-of-way, and nothing else.

    Seven cities in this corpus mean seven different things by a net acre.
    Fairview's subtraction list is one item long, which is unusually generous
    and is worth citing rather than assuming.
    """
    held = fairview.zones["VA"].values["max_density_du_per_acre"]
    text = ProvenanceStore().quote(held.measured_on_quote)
    assert "does not include land devoted to street right-of-way" in text
    assert "after subtracting street right-of-way" in text


def test_a_setback_stated_only_against_neighbours_is_charged_everywhere(
    fairview: Layer,
) -> None:
    """VMU asks five feet from lines abutting residential areas and states no
    other setback. That is not a stated zero for every other line -- the code
    never prints one -- so the five is charged on every side and rear line.

    Encoding the relief would have meant citing a sentence for a number the
    sentence does not contain, which is the failure mode this corpus checks
    for by name.
    """
    vmu = fairview.zones["VMU"]
    for field in ("setback_side_ft", "setback_rear_ft"):
        held = vmu.values[field]
        assert held.value == 5, field
        assert held.variants == (), field

    text = ProvenanceStore().quote(vmu.values["setback_side_ft"].prov.quote)
    assert "at least five feet from property lines abutting residential" in text


def test_the_front_setback_menus_are_read_at_their_strictest(
    fairview: Layer,
) -> None:
    """Both village zones with a front number take it from a Halsey exception.

    VA's own sentence offers zero, ten or fifteen feet and then puts twenty on
    "the Halsey Street frontage"; VC asks twenty from the Halsey right-of-way
    for all building facades. Which street a lot fronts is not a fact this
    system holds, so twenty is the base in both and the menu is in the notes.
    """
    assert fairview.zones["VA"].values["setback_front_ft"].value == 20
    assert fairview.zones["VC"].values["setback_front_ft"].value == 20

    notes = fairview.zones["VA"].notes or ""
    assert "zero feet or 10 feet or 15 feet" in notes


def test_the_apartment_zone_states_no_side_or_rear_setback_at_all(
    fairview: Layer,
) -> None:
    va = fairview.zones["VA"]
    for field in ("setback_side_ft", "setback_rear_ft"):
        assert va.values[field].exempt is True, field

    text = ProvenanceStore().quote(va.values["setback_side_ft"].prov.quote)
    assert "no setback requirements for side and rear facades" in text


def test_the_standards_that_describe_the_building_are_handed_back(
    fairview: Layer,
) -> None:
    """A pod is a fixed design and VA has opinions about designs.

    19.145.040 requires a hipped, gambrel or gabled roof at 4:12 or steeper and
    does not permit flat roofs; 19.145.020 wants primary entries reached
    directly from the street and a front porch on every other unit. No lot
    geometry answers either -- they decide whether the catalog entry qualifies
    at all -- so they are recorded rather than encoded.
    """
    notes = fairview.zones["VA"].notes or ""
    assert "4:12" in notes
    assert "front porch" in notes


def test_no_village_zone_is_missing_a_required_field(rules: RuleSet) -> None:
    for zone in VILLAGE:
        assert rules.resolve(FAIRVIEW, zone, POD).missing_required == (), zone


def test_the_village_citations_all_point_at_their_own_sentence(
    fairview: Layer,
) -> None:
    ready = readiness_for(fairview, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
