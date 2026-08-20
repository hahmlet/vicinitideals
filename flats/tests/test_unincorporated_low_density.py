"""LR-5 and LR-10 -- the county's urban residential zones either side of LR-7.

Two articles of MCC Chapter 39 with the same shape and one line of difference.
LR-5's conditional-use list prints "(C) A multiplex dwelling structure"; LR-10's
prints nothing in that position and tops out at a two-unit dwelling. So one is
a real encoding and the other is a refusal, and the pair is the check that the
refusal was read rather than assumed.

LR-5 is also where two rules meet and say something neither says alone.
39.4828(A) lets an approved multiplex sit only on a corner lot, a flag lot, or
a lot reached by an accessway or a newly created street; 39.4830(H) exception
(4) caps a multiplex on a flag lot at 25 feet. The pod is 26. One of the two
doors this zone can see is shut by the zone's own height exception, and
arithmetic is what shuts it.

Both zones carry an unresolved preemption question in their notes, and it is
the same one LR-7 answers the other way. That disagreement is deliberate and
visible: LR-7 reads `true` on a statute nobody has stored, these two read
`false` on text that is stored, and the note says where the fix belongs.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

UNINC = "or/multnomah/_unincorporated"
POD = ("multi_story", "attached_wall")
#: 26 feet, from the catalog entry this whole corpus is screened against.
POD_HEIGHT_FT = 26


@pytest.fixture(scope="module")
def uninc() -> Layer:
    return load_rules()[UNINC]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_neither_zone_opens_without_an_application(rules: RuleSet) -> None:
    for zone in ("LR5", "LR10"):
        res = rules.resolve(UNINC, zone, POD)
        assert res.values["quadplex_allowed"].value is False, zone
        assert res.missing_required == (), zone


def test_the_permit_alone_does_not_open_the_smaller_zone(rules: RuleSet) -> None:
    """A conditional use is half the ask in LR-5.

    39.4828(A) says an approved multiplex "may be located only on" one of four
    kinds of lot. A screen that granted the permit and ignored the location
    would open every interior lot in the zone, which is the outcome the
    sentence exists to prevent.
    """
    with_permit = rules.resolve(UNINC, "LR5", (*POD, "conditional_use"))
    assert with_permit.values["quadplex_allowed"].value is False


def test_a_corner_lot_and_a_permit_open_it(rules: RuleSet) -> None:
    opened = rules.resolve(UNINC, "LR5", (*POD, "conditional_use", "corner_lot"))
    assert opened.values["quadplex_allowed"].value is True


def test_the_flag_lot_door_is_shut_by_the_zone_own_height_exception(
    rules: RuleSet,
) -> None:
    """The use rule opens it and the height rule closes it.

    39.4828(A)(2) lists a flag lot as a place a multiplex may go. 39.4830(H)
    exception (4) caps "a single family, duplex or multiplex dwelling on a flag
    lot" at 25 feet. The pod is 26, so the permission survives and the building
    does not -- and the reason is arithmetic on two quoted numbers rather than
    an assumption about anything.
    """
    flagged = rules.resolve(UNINC, "LR5", (*POD, "conditional_use", "flag_lot"))
    assert flagged.values["quadplex_allowed"].value is True
    assert flagged.values["max_height_ft"].value == 25
    assert POD_HEIGHT_FT > flagged.values["max_height_ft"].value

    cornered = rules.resolve(UNINC, "LR5", (*POD, "conditional_use", "corner_lot"))
    assert cornered.values["max_height_ft"].value == 35


def test_the_locational_rule_is_quoted_with_the_permission(uninc: Layer) -> None:
    """Both variants cite 39.4826(C) and 39.4828(A) together.

    The conditional-use line alone would read as a general permission. The
    locational line alone would read as a restriction on something nobody had
    established was allowed. Neither is the rule.
    """
    store = ProvenanceStore()
    variants = uninc.zones["LR5"].values["quadplex_allowed"].variants
    assert len(variants) == 2

    for variant in variants:
        text = store.quote(variant.prov.quote)
        assert "A multiplex dwelling structure under the" in text
        assert "may be located only on" in text

    assert {frozenset(v.when) for v in variants} == {
        frozenset({"conditional_use", "corner_lot"}),
        frozenset({"conditional_use", "flag_lot"}),
    }


def test_the_two_paths_nobody_can_see_are_recorded_not_assumed(
    uninc: Layer,
) -> None:
    """Accessway access and a newly created street are the other two doors.

    One needs a private-access layer nobody holds; the other needs a count of
    multiplex units already built within 250 feet. A lot on either path screens
    refused here and should not, which is a direction this file is wrong in and
    therefore has to say so.
    """
    notes = uninc.zones["LR5"].notes or ""
    assert "accessway approved under MCC 39.9000" in notes
    assert "250 feet" in notes
    assert "six dwelling units" in notes


def test_the_smaller_zone_states_its_lot_size_per_dwelling(uninc: Layer) -> None:
    """4,500 square feet for each unit, so 18,000 for the pod, and the article
    prints 18,000 nowhere -- the same bargain LR-7 strikes with its 5,000."""
    held = uninc.zones["LR5"].values["min_lot_sqft"]
    assert held.per_dwelling == 4500
    assert held.value == 18000

    text = ProvenanceStore().quote(held.prov.quote)
    assert "4,500 square feet for" in text
    assert "18,000" not in text


def test_the_lot_width_that_binds_is_the_corner_one(uninc: Layer, rules: RuleSet) -> None:
    """45 feet interior, 50 on a corner -- and a corner is where the pod goes.

    The base is the number that can almost never apply to this building in this
    zone, and the variant is the one that nearly always will. Encoding only the
    base would have shaved five feet off the requirement on exactly the lots
    the use rule sends the pod to.
    """
    held = uninc.zones["LR5"].values["min_lot_width_ft"]
    assert held.value == 45
    assert [v.value for v in held.variants] == [50]

    opened = rules.resolve(UNINC, "LR5", (*POD, "conditional_use", "corner_lot"))
    assert opened.values["min_lot_width_ft"].value == 50


def test_the_larger_zone_tops_out_at_two_units(uninc: Layer) -> None:
    """LR-10 prints no multiplex line anywhere.

    Its conditional list runs to community service uses, the generic Part 7
    conditional uses, farm sales and home occupations. Where LR-5 prints "(C) A
    multiplex dwelling structure", this article prints wholesale farm sales.
    """
    held = uninc.zones["LR10"].values["quadplex_allowed"]
    assert held.value is False
    assert held.variants == ()

    text = ProvenanceStore().quote(held.prov.quote)
    assert "Single family detached dwelling" in text
    assert "multiplex" not in text.lower()
    assert "Wholesale or retail sales of farm" in text


def test_the_larger_zone_owes_the_use_flag_and_nothing_else(uninc: Layer) -> None:
    assert set(uninc.zones["LR10"].values) == {"quadplex_allowed"}

    notes = uninc.zones["LR10"].notes or ""
    assert "10,000 square feet" in notes
    assert "Part 7" in notes


def test_the_preemption_disagreement_is_written_down_in_both_zones(
    uninc: Layer,
) -> None:
    """LR-7 says true on an unstored statute; these two say false on stored text.

    Somebody has to reconcile that, and the reconciliation belongs on the state
    layer where one rule reaches all three zones rather than in three zone
    blocks disagreeing with each other. Until then the disagreement is a note,
    not a silence.
    """
    for zone in ("LR5", "LR10"):
        notes = uninc.zones[zone].notes or ""
        assert "197A.420" in notes, zone
        assert "LR-7" in notes, zone


def test_the_low_density_citations_all_point_at_their_own_sentence(
    uninc: Layer,
) -> None:
    ready = readiness_for(uninc, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
