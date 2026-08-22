"""Portland caps parking, and until now nothing here could say so.

Every parking standard this corpus held was a floor. `parking_min_per_unit`
asks how many stalls a lot must provide, the answer across most of Oregon is
now zero, and a floor of zero binds nothing -- so parking had quietly become a
field that could not fail. It can. Portland's Table 266-2 states a *ceiling*
for Household Living, and a site plan that seats more stalls than the ceiling
allows is not a legal placement however neatly it fits.

The number that matters is 1.35 per unit, which is five stalls for a fourplex
and not six, against a catalog target of 1.5. Thirteen of Portland's
twenty-eight zones are under a cap the pod as specified is over.

Two readings decide which zone gets which number, and both are one sentence
each in a different chapter: 33.120.020 lists the six multi-dwelling zones and
33.130.020 lists the six commercial/mixed use zones. Table 266-2's exception
names those two classes and nothing else, so the lists are load-bearing and
are pinned here against the chapters rather than retyped from memory.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.encode.dispositions import notes
from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"

#: 33.120.020 -- "When this Title refers to the multi-dwelling zones, it is
#: referring to the six zones listed here."
MULTI_DWELLING = ("RM1", "RM2", "RM3", "RM4", "RX", "RMP")
#: 33.130.020 -- the same sentence for the commercial/mixed use zones.
COMMERCIAL = ("CR", "CM1", "CM2", "CM3", "CE", "CX")
CAPPED = MULTI_DWELLING + COMMERCIAL

#: Everything else Portland zones. Table 266-1 sends all of them to Standard B
#: and Standard B opens "No maximum" -- the exception reaches only the twelve
#: above, so these fifteen have no ceiling at all.
UNCAPPED = (
    "RF", "R20", "R10", "R7", "R5", "R2.5",
    "OS", "EG1", "EG2", "IG1", "IG2", "IH", "IR", "CI1", "CI2",
)


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_a_ceiling_is_a_different_field_from_a_floor() -> None:
    """Not a spelling of `parking_min_per_unit`. The two bind opposite ways,
    and a city states either without the other: Portland states no minimum
    anywhere in its limits and a maximum in thirteen of its zones."""
    assert FIELDS["parking_max_per_unit"].is_maximum is True
    assert FIELDS["parking_min_per_unit"].is_maximum is False


def test_the_twelve_zones_inside_the_exception_carry_it(rules: RuleSet) -> None:
    for zone in CAPPED:
        held = rules.resolve(PORTLAND, zone).values["parking_max_per_unit"]
        assert held.value == 1.35, zone


def test_and_the_other_fifteen_have_no_ceiling_at_all(rules: RuleSet) -> None:
    """Exempt, not absent. The layer default states it once with the sentence
    that says so, and an exempt value does not appear in a resolution -- the
    same way a zone with no density cap carries none."""
    layer = load_rules()[PORTLAND]

    assert layer.defaults["parking_max_per_unit"].exempt is True
    for zone in UNCAPPED:
        assert "parking_max_per_unit" not in rules.resolve(PORTLAND, zone).values, zone


def test_the_zone_lists_are_the_chapters_own(rules: RuleSet) -> None:
    """Table 266-2's exception names two zone classes and never lists their
    members, so the membership is read from 33.120.020 and 33.130.020. If a
    zone is ever added to this layer without being placed in one of the three
    buckets, this is what says so."""
    zones = set(load_rules()[PORTLAND].zones)

    assert set(CAPPED) | set(UNCAPPED) | {"EX"} == zones
    assert not set(CAPPED) & set(UNCAPPED)
    assert "EX" not in set(CAPPED) | set(UNCAPPED)


def test_ex_is_the_tightest_cap_in_the_corpus(rules: RuleSet) -> None:
    """"1 per 2 units" -- two stalls for the pod. And EX allows the building
    outright, so this is not a cap on land the screen was going to refuse."""
    held = rules.resolve(PORTLAND, "EX").values["parking_max_per_unit"]

    assert held.value == 0.5
    assert rules.resolve(PORTLAND, "EX").values["quadplex_allowed"].value is True


def test_the_file_states_the_denominator_and_not_the_rate() -> None:
    """Table 266-2 prints 1 and prints 2 and prints 0.5 nowhere. The file says
    2, the loader does the division, and the citation check reads a figure a
    reader will actually find on the page -- which is the same bargain
    `sqft_per_unit` and `per_dwelling` already strike."""
    held = load_rules()[PORTLAND].zones["EX"].values["parking_max_per_unit"]

    assert held.per_units == 2
    assert held.value == 0.5


def test_splitting_the_pod_onto_unit_lots_lifts_the_1_35() -> None:
    """"Houses, attached houses and duplexes are exempt." Four townhouses on
    four unit lots are four attached houses; the same building on one lot is a
    fourplex, which that sentence does not name. So the plat decides whether
    the ceiling exists -- and it decides it only for Standard B, because the
    exemption is written into Standard B's cell and nowhere else."""
    layer = load_rules()[PORTLAND]
    for zone in CAPPED:
        held = layer.zones[zone].values["parking_max_per_unit"]
        assert [(v.exempt, v.when) for v in held.variants] == [
            (True, ("unit_lots",))
        ], zone

    assert layer.zones["EX"].values["parking_max_per_unit"].variants == ()


def test_the_catalog_pod_is_over_the_cap_in_thirteen_zones(rules: RuleSet) -> None:
    """The finding, stated as a number rather than as a worry.

    Both catalog entries ask 1.5 stalls per unit. Nothing in this test decides
    what the screen should do about that -- the design's figure is a
    marketability target and the zone's is law, and reconciling them is the
    site-plan stage's job. What this pins is that the conflict is now visible
    at all, which it was not while the field did not exist.
    """
    catalog = load_catalog()
    target = catalog.get("pod56x36@1").parking.stalls_per_unit
    assert target == 1.5

    over = [
        zone
        for zone in load_rules()[PORTLAND].zones
        if (held := rules.resolve(PORTLAND, zone).values.get("parking_max_per_unit"))
        and held.value < target
    ]

    assert sorted(over) == sorted((*CAPPED, "EX"))
    assert len(over) == 13


def test_the_parking_chapter_has_no_unread_notes_left() -> None:
    """Thirteen were read to get here and none of them reaches a four-unit
    building. Two of the three reasons are traps rather than shrugs: 33.266.130
    excludes residential vehicle areas by its own applicability sentence, and
    Table 266-6's Household Living row starts at five units on site. Both look
    like live constraints until you find the sentence."""
    unread = [n for n in notes(PORTLAND) if n.state == "unread"]

    assert unread == []


def test_the_new_numbers_are_where_the_file_says_they_are() -> None:
    """The whole point of a carrier like `per_units` is that it keeps this
    check honest instead of silencing it."""
    report = readiness_for(load_rules()[PORTLAND], store=ProvenanceStore())

    assert report.misquoted == ()
    assert report.no_evidence == ()
    assert report.unquoted == ()
