"""Fairview TCC -- the one district that permits the pod, encoded as a refusal.

Table 19.65.020(A) reads `h. Quadplexes P`. No other commercial or industrial
district in this city admits the building at all, and the base value here is
still false, because 19.65.030 draws a Halsey Street storefront district
INSIDE the zone and requires every development in it to include a
nonresidential use. The boundary is Figure 19.65.030(B) -- a map -- so whether
a given TCC lot sits inside the subarea is unmeasured, and the conservative
reading is that it does.

`mixed_use` alone reopens it. Wood Village's NC zone across the city line
needs a conditional use as well, because its table never permits the building
outright; the two cities are running the same programme -- 19.65.030(A) says
the storefront concept "is applied to multiple areas on Halsey Street across
Fairview, Wood Village, and Troutdale" -- and arrive at the same answer from
opposite directions.

The other half of this zone is what it does not say. There is no minimum lot
size, no density standard, no floor area ratio and no coverage limit;
19.65.100(A)(1) hands density to floor area and height instead. A screen that
treats a missing lot-size row as unread holds the zone open forever waiting
for a number the code does not have, which is why `min_lot_sqft` is `exempt`
and not absent.
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


@pytest.fixture(scope="module")
def fairview() -> Layer:
    return load_rules()[FAIRVIEW]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_only_outright_permission_in_the_city_still_reads_false(
    fairview: Layer,
) -> None:
    held = fairview.zones["TCC"].values["quadplex_allowed"]
    assert held.value is False
    assert {v.when for v in held.variants} == {("mixed_use",)}


def test_the_mixed_use_election_is_what_reopens_it(rules: RuleSet) -> None:
    """One elective, not two.

    Quadplexes are P here, so nothing needs a conditional use permit; what
    the storefront district asks for is a nonresidential use on the site. Get
    that wrong in either direction and the zone is misread -- demanding a CU
    closes 47 lots that are open, and dropping the mixed use opens lots that
    are closed.
    """
    assert rules.resolve(FAIRVIEW, "TCC", POD).values["quadplex_allowed"].value is False
    with_mixed = rules.resolve(FAIRVIEW, "TCC", (*POD, "mixed_use"))
    assert with_mixed.values["quadplex_allowed"].value is True


def test_the_permission_and_the_limit_are_quoted_together(fairview: Layer) -> None:
    """The table row alone would be a false green on 47 lots.

    Row h says P and 19.65.030(D)(1) says "Residential uses shall be permitted
    only when part of a mixed use development". Both sentences are inside the
    citation, so a reader who disagrees with the conservative reading can see
    exactly what it rests on.
    """
    text = ProvenanceStore().quote(
        fairview.zones["TCC"].values["quadplex_allowed"].prov.quote
    )
    assert "Quadplexes" in text
    assert "subarea of the TCC zone" in text
    assert "only when part of a mixed use development" in text


def test_the_ways_out_of_the_mixed_use_requirement_are_recorded(
    fairview: Layer,
) -> None:
    """19.65.030(E) is unusually generous and the notes have to say so.

    1,000 square feet of enclosed commercial space, a food cart pod of four or
    more carts, or a micro retail pod of three retailers in prefabricated
    buildings under 600 square feet each. That is what `mixed_use` costs on
    these lots, and it is a different price from the same election elsewhere.
    """
    notes = fairview.zones["TCC"].notes or ""
    assert "1,000 square feet" in notes
    assert "food cart pod" in notes
    assert "micro retail pod" in notes


def test_a_zone_with_no_lot_size_is_exempt_rather_than_unread(
    fairview: Layer,
    rules: RuleSet,
) -> None:
    held = fairview.zones["TCC"].values["min_lot_sqft"]
    assert held.exempt is True
    assert rules.resolve(FAIRVIEW, "TCC", POD).missing_required == ()

    text = ProvenanceStore().quote(held.prov.quote)
    assert "no minimum or maximum residential density standard" in text


def test_the_binding_front_number_is_the_maximum_not_the_minimum(
    fairview: Layer,
) -> None:
    """A storefront zone pushes buildings at the street.

    The minimum front setback is zero and the maximum is ten feet, with at
    least half the ground level street-facing facade required to sit within
    it. That is the reverse of every residential district in this corpus, and
    a pod placed comfortably back from the street fails a zone it fits.
    """
    zone = fairview.zones["TCC"]
    assert zone.values["setback_front_ft"].value == 0
    assert zone.values["setback_front_max_ft"].value == 10


def test_the_side_and_rear_lines_take_the_neighbours_reading(
    fairview: Layer,
) -> None:
    """Zero against another commercial lot, fifteen against a residential one.

    Which applies is the neighbour's zoning, which this system does not hold,
    so fifteen is the base and zero is a relief that cannot fire. Reading it
    the other way is how a lot with houses behind it screens as buildable to
    its own rear line.
    """
    zone = fairview.zones["TCC"]
    for field in ("setback_side_ft", "setback_rear_ft"):
        held = zone.values[field]
        assert held.value == 15, field
        assert ("abuts_nonresidential_zone",) in {v.when for v in held.variants}, field

    rear = zone.values["setback_rear_ft"]
    assert {v.value for v in rear.variants} == {0, 8}


def test_the_alley_step_is_kept_even_though_it_cannot_fire(
    fairview: Layer,
    rules: RuleSet,
) -> None:
    """Eight feet on an alley-access lot, so a car can park behind.

    Both facts it needs are unheld, so the resolved value stays at fifteen.
    Recording it anyway is what makes the number checkable when the geometry
    layer can see an alley.
    """
    resolved = rules.resolve(FAIRVIEW, "TCC", POD).values["setback_rear_ft"]
    assert resolved.value == 15

    eight = [
        v
        for v in fairview.zones["TCC"].values["setback_rear_ft"].variants
        if v.value == 8
    ]
    assert len(eight) == 1
    assert set(eight[0].when) == {"abuts_nonresidential_zone", "abuts_alley"}


def test_the_height_step_downs_cannot_reach_a_twenty_six_foot_pod(
    fairview: Layer,
) -> None:
    """45 feet base, stepping to 35 within 25 feet of an R, R-7.5, R-10 or VSF site.

    The step-down is unmeasured adjacency and it still does not matter here,
    which is worth pinning: the reason this zone is not capped is arithmetic,
    not an assumption.
    """
    height = fairview.zones["TCC"].values["max_height_ft"]
    assert height.value == 45

    text = ProvenanceStore().quote(height.prov.quote)
    assert "45 feet" in text
    assert "step-down height limit is 35 feet" in text


def test_the_design_standards_reach_unit_lots_and_not_this_building(
    fairview: Layer,
) -> None:
    """19.65.090 applies to townhomes on their own lots and to developments
    with more than one building. A single four-unit building on a single lot
    is neither, so its five-foot ground-floor setback and eight-foot entrance
    setback are read and left out -- and would all bind the moment the same
    four units were divided onto unit lots.
    """
    notes = fairview.zones["TCC"].notes or ""
    assert "19.65.090" in notes
    assert "unit lots" in notes


def test_the_parking_siting_rule_is_handed_to_the_geometry_layer(
    fairview: Layer,
) -> None:
    """19.65.100(A)(2) is a rule about where the stalls go, not how many.

    Oriented to an alley, underground, above the ground floor, or behind or
    beside the building, and never in a corner side yard. Nothing in the
    value model can hold that; the note is the handoff.
    """
    assert "19.65.100(A)(2)" in (fairview.zones["TCC"].notes or "")


def test_the_town_center_citations_all_point_at_their_own_sentence(
    fairview: Layer,
) -> None:
    ready = readiness_for(fairview, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
