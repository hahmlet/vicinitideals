"""The exception two zone tables cite, and the sentence beside it that they do not.

R-10 and R-5 print one line under "Minimum yard dimensions or minimum building
setbacks": *"Except as specified in CDC 25.070(C)(1) through (4) for the
Willamette Historic District."* It was the loudest thing left in West Linn's
cross-reference queue and it reads like a setback footnote.

Three findings came out of reading the chapter, and only the first is a setback.

The four subsections the row names are **looser** than the base zone everywhere
they differ -- side five feet against R-10's seven and a half, side street ten
against fifteen -- except the front yard, which 25.070(C)(1)(a) sets to "the
average of the front setbacks of adjacent homes on the block face". That is not
a number, and it could land either side of the zone's twenty feet. A qualifier
that can only loosen is read and left alone; this one moves in a direction
nothing here can bound, so it is carried as `qualified_by`.

What the row does **not** cite is 25.070(C)(8): *"No building shall exceed 35
feet in overall width."* It stands on the subsection's own applicability
sentence rather than on the zone table, and it is the first standard in this
corpus the pod fails on its own dimensions instead of on where it sits -- 56 ft
by 36 ft, over the cap on a lot of any size. Nothing in the field registry could
hold it, so `max_building_width_ft` is new.

And the relief path is not the usual one. 25.080(A) says Chapter 75, Variance,
does not apply in this chapter at all; what stands in its place is a
discretionary modification turning on historical records.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import condition
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WEST_LINN = "or/clackamas/west-linn"
CHAPTER = f"{WEST_LINN}/25.willamette-historic.txt"
DISTRICT = "willamette_historic_district"

#: The two zones whose dimensional table cites the chapter. No other West Linn
#: zone does, which is itself the reason the encoding is per zone.
CITING = ("R-10", "R-5")


@pytest.fixture(scope="module")
def west_linn() -> Layer:
    return load_rules()[WEST_LINN]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the chapter -------------------------------------------------------------


def test_the_chapter_the_setback_row_cites_is_in_the_store(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """A ruling from an unread chapter is a guess. This one is quotable."""
    assert "25.willamette-historic" in {doc.id for doc in west_linn.code}
    text = store.load(CHAPTER).text
    assert "25.070 ADDITIONAL STANDARDS APPLICABLE TO HISTORIC DISTRICTS" in text


def test_the_row_cites_four_subsections_and_they_are_the_four_yards(
    store: ProvenanceStore,
) -> None:
    """Which is what makes the width cap a separate finding rather than part of
    the same one: it is (C)(8), and the row stops at (4)."""
    for doc in ("11.r-10", "13.r-5"):
        page = store.load(f"{WEST_LINN}/{doc}.txt").text
        assert "CDC 25.070(C)(1) through (4) for the Willamette Historic District" in page

    lines = store.load(CHAPTER).text.splitlines()
    heads = [l for l in lines if l.strip()[:2] in ("1.", "2.", "3.", "4.")]
    assert any("Front yard setback" in l for l in heads)
    assert any("Side yard setback" in l for l in heads)
    assert any("Side street setback" in l for l in heads)
    assert any("Rear yard setback" in l for l in heads)


# -- the three yards that only loosen ----------------------------------------


def test_the_district_numbers_are_looser_so_the_zone_numbers_stand(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """Five, ten and twenty against seven and a half, fifteen and twenty. A
    qualifier that can only loosen is read and not encoded -- the same reading
    this layer already takes of the 0.30 floor under its FARs. Encoding it
    would trade a lot that reviews for a lot that is wrongly refused."""
    text = store.load(CHAPTER).text
    assert "Side yard setbacks shall be five feet" in text
    assert "Setbacks from side streets shall be 10 feet" in text
    assert "The rear yard setback shall be a minimum of 20 feet" in text

    r10 = west_linn.zones["R-10"].values
    assert r10["setback_side_ft"].value == 7.5
    assert r10["setback_street_side_ft"].value == 15
    assert r10["setback_rear_ft"].value == 20
    for name in ("setback_side_ft", "setback_street_side_ft", "setback_rear_ft"):
        for zone in CITING:
            assert west_linn.zones[zone].values[name].qualified_by is None, f"{zone}.{name}"


# -- the one that does not ---------------------------------------------------


def test_the_front_yard_is_an_average_of_the_block_rather_than_a_number(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    for zone in CITING:
        held = west_linn.zones[zone].values["setback_front_ft"]
        assert held.value == 20, zone
        assert held.qualified_by == DISTRICT, zone
        quoted = store.quote(held.qualified_quote)
        assert "average of the front setbacks of adjacent homes on the block face" in quoted


def test_the_fact_carries_no_assumption_because_neither_default_is_safe(
    west_linn: Layer,
) -> None:
    """Assume in the district and every West Linn lot is refused on a width cap
    almost none of them are subject to. Assume out of it and the district's lots
    certify against a standard that forbids the building outright. The fact is
    registered unassumed, which is the machinery for read-and-waiting-on-data."""
    fact = condition(DISTRICT)
    assert fact.kind == "site_fact"
    assert fact.assume is None
    assert fact.evidence


# -- the sentence the row does not cite --------------------------------------


def test_a_field_now_holds_a_width_the_code_caps(west_linn: Layer) -> None:
    """No setback can stand in for this. A setback says where a building may
    stand and this says how big it may be, so a lot with room to spare on every
    yard still fails it."""
    held = field("max_building_width_ft")
    assert held.kind == "length_ft"
    assert held.is_maximum is True
    # One jurisdiction states it, and only inside a district. A zone that is
    # silent about building width is not an incomplete zone.
    assert "max_building_width_ft" in OPTIONAL_FIELDS


def test_the_cap_is_exempt_outside_the_district_and_thirty_five_within(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """The exemption is not an assumption about silence. 25.070(C) states in
    terms that it applies only inside the district, and that is the sentence
    the exempt value cites."""
    for zone in CITING:
        held = west_linn.zones[zone].values["max_building_width_ft"]
        assert held.exempt is True, zone
        assert held.value is None, zone
        assert "applies only to" in store.quote(held.prov.quote), zone

        variant = next(v for v in held.variants if v.when == (DISTRICT,))
        assert variant.value == 35, zone
        assert "No building shall exceed 35 feet in overall width" in store.quote(
            variant.prov.quote
        ), zone


def test_and_the_pod_is_over_it_in_both_directions(west_linn: Layer) -> None:
    """56 by 36. There is no lot large enough and no orientation that helps,
    which is the difference between this standard and every other one encoded
    so far: it is a fact about the building, not about the fit."""
    pod = next(d for d in load_catalog() if d.id == "pod56x36")
    assert pod.footprint.width_ft == 56
    assert pod.footprint.depth_ft == 36
    cap = next(
        v.value
        for v in west_linn.zones["R-10"].values["max_building_width_ft"].variants
        if v.when == (DISTRICT,)
    )
    assert pod.footprint.width_ft > cap
    assert pod.footprint.depth_ft > cap


def test_the_height_cap_in_the_same_subsection_the_pod_clears(
    store: ProvenanceStore,
) -> None:
    """28 feet against 26. Recorded rather than encoded, because the zone's own
    35 is the looser of the two and this one can only tighten -- and it does not
    tighten past the design."""
    pod = next(d for d in load_catalog() if d.id == "pod56x36")
    assert pod.height_ft == 26
    assert "Residential structures are limited to 28 feet in height" in store.load(CHAPTER).text


# -- what the lot comes back as ----------------------------------------------


def test_both_zones_offer_the_district_as_a_lever(rules: RuleSet) -> None:
    """The point of the encoding. `flats/score/screen.py` reads `levers` to
    decide whether an assumption is load-bearing, so a lot in R-10 or R-5 now
    comes back naming the district instead of certifying past it.

    Note the width cap reaches this through `exempted` rather than `values` --
    an exempt standard is dropped so nothing can compare a lot against it, and
    until the resolver was fixed it took its lever with it.
    """
    for zone in CITING:
        got = rules.resolve(WEST_LINN, zone)
        assert DISTRICT in got.levers, zone
        assert "max_building_width_ft" in got.exempted, zone
        assert "max_building_width_ft" not in got.values, zone
        assert got.missing_required == (), zone


def test_and_inside_the_district_the_number_appears(rules: RuleSet) -> None:
    for zone in CITING:
        inside = rules.resolve(WEST_LINN, zone, conditions=[DISTRICT])
        assert inside.values["max_building_width_ft"].value == 35, zone
        assert "max_building_width_ft" not in inside.exempted, zone


def test_no_other_west_linn_zone_states_a_width(west_linn: Layer) -> None:
    """The district is two zones deep. Encoding it against the layer would put
    a cap on seven zones no sentence puts it on."""
    for name, zone in west_linn.zones.items():
        if name in CITING:
            continue
        assert "max_building_width_ft" not in zone.values, name


# -- the queue this emptied --------------------------------------------------


def test_the_binding_references_are_ruled_rather_than_still_asking(
    west_linn: Layer,
) -> None:
    """Five stood beside numbers the screen uses and a sixth arrived with the
    fetch. All six resolved from their own citing sentences: accessory uses, a
    conditional-use lot size for a use that is permitted outright, a declined
    variance, a road, an exemption inside a definition, and a commercial design
    district this building is the other half of."""
    for ref in ("34", "60.070", "75", "60.090", "28.040", "58"):
        assert ref in west_linn.crossrefs, ref
        assert len(west_linn.crossrefs[ref]) > 100, ref


def test_the_layer_records_what_it_read_and_did_not_encode(west_linn: Layer) -> None:
    """The three standards in the chapter no field holds, the narrative half of
    25.070, and the relief path that is not a variance. Without this the next
    reader starts from the reference again."""
    notes = west_linn.notes
    assert "25.070(C)(8)" in notes
    assert "roof pitch of at least 6:12" in notes
    assert "25.080(A)" in notes
    assert '"Standards for new construction"' in notes
