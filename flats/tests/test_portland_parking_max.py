"""Portland caps parking, and until now nothing here could say so.

Every parking standard this corpus held was a floor. `parking_min_per_unit`
asks how many stalls a lot must provide, the answer across most of Oregon is
now zero, and a floor of zero binds nothing -- so parking had quietly become a
field that could not fail. It can. Portland's Table 266-2 states a *ceiling*
for Household Living, and a site plan that seats more stalls than the ceiling
allows is not a legal placement however neatly it fits.

The number that matters is 1.35 per unit, which is five stalls for a fourplex
and not six, against a catalog target of 1.5. Thirteen of Portland's
twenty-eight zones (fourteen since RICAP 11 put CI1 homes on RM1's rules,
2026-11-10) are under a cap the pod's target is over -- and since
2026-09-18 the screen charges the pod's floor of one per home, which no cap
here reaches, so what the cap does in those thirteen is stop the seat count
reported beside the colour at five.

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

#: 2026-11-10 (b): CI1 left UNCAPPED. RICAP 11 (in force 2026-11-01, codified
#: by the 11/1/26 reprint, FOLLOWUPS 165) put Household Living in CI1 under
#: "the regulations in the chapter that apply in the RM1 zone" (33.266.100.B,
#: or/multnomah/portland/33.266.txt#L38-L40), so a CI1 home takes RM1's
#: 1.35 through `like: RM1` (rulings.yaml 2026-08-06-portland-ricap11-ci1-housing).
#: It is not a member of either class Table 266-2 names; it borrows one.
LIKE_RM1 = ("CI1",)

#: Everything else Portland zones. Table 266-1 sends all of them to Standard B
#: and Standard B opens "No maximum" -- the exception reaches only the twelve
#: above, so these fourteen have no ceiling at all.
UNCAPPED = (
    "RF", "R20", "R10", "R7", "R5", "R2.5",
    "OS", "EG1", "EG2", "IG1", "IG2", "IH", "IR", "CI2",
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


def test_a_ci1_home_carries_rm1s_cap(rules: RuleSet) -> None:
    """33.266.100.B sends CI1 homes to the RM1 zone's parking rules (2026-11-10)."""
    rm1 = rules.resolve(PORTLAND, "RM1").values["parking_max_per_unit"]
    for zone in LIKE_RM1:
        got = rules.resolve(PORTLAND, zone)
        held = got.values["parking_max_per_unit"]
        assert got.borrowed_from == ("RM1",), zone
        assert (held.value, held.prov.quote) == (1.35, rm1.prov.quote), zone


def test_and_the_other_fourteen_have_no_ceiling_at_all(rules: RuleSet) -> None:
    # 2026-11-10 (b): renamed from ..._other_fifteen_...; CI1 moved to LIKE_RM1.
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

    assert set(CAPPED) | set(UNCAPPED) | set(LIKE_RM1) | {"EX"} == zones
    assert not set(CAPPED) & set(UNCAPPED)
    assert not set(LIKE_RM1) & (set(CAPPED) | set(UNCAPPED))
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


def test_the_catalog_pods_target_is_over_the_cap_in_fourteen_zones(rules: RuleSet) -> None:
    """The finding, stated as a number rather than as a worry.

    2026-11-10 (b): renamed from ..._in_thirteen_zones. CI1 joined the twelve
    at 1.35 when RICAP 11 put its homes on RM1's parking rules (LIKE_RM1
    above); the floor of one per home still reaches no cap but EX's, so no
    colour turns on it.

    Both catalog entries sell at 1.5 stalls per unit and are built with one.
    The screen charges the one (Steph, 2026-09-18: "4 is enough to sell"),
    so in twelve of the thirteen zones the cap costs no lot its colour and
    only cuts the count reported beside it to five, the floor's band. EX is
    the thirteenth and the other case: half a stall per home is two on a
    fourplex, below the floor, and a lot there fails the screen's
    ``parking_cap`` check the way the county map refuses the plan as
    ``too_few_stalls``. What this pins is that the conflict is visible at
    all, which it was not while the field did not exist.
    """
    catalog = load_catalog()
    bands = catalog.get("pod56x36@2").parking.stalls_per_unit
    assert (bands.floor, bands.target) == (1.0, 1.5)

    caps = {
        zone: held.value
        for zone in load_rules()[PORTLAND].zones
        if (held := rules.resolve(PORTLAND, zone).values.get("parking_max_per_unit"))
    }
    over = [zone for zone, cap in caps.items() if cap < bands.target]

    assert sorted(over) == sorted((*CAPPED, *LIKE_RM1, "EX"))
    assert len(over) == 14
    assert [zone for zone, cap in caps.items() if cap < bands.floor] == ["EX"]


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
