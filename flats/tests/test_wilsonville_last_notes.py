"""Wilsonville's last twenty-four footnotes, and the two zones that were missing.

Three groups, three different reasons, and the uncomfortable one has closed.

**Tables 8B and 8C.** Fourteen notes on the two thirds of the RN zone this
layer does not read from. 4.127(.08)C splits RN in two -- Frog Pond West is
governed by Table 8A, Frog Pond East and South by Table 8B -- and every RN
dimension in the corpus comes off Table 8A. The notes reach nothing because
RN's quadplex row is a settled prohibition, but the prohibition itself is a
Frog Pond West sentence (4.127(.02)B.1.a.ii) applied to all three
neighbourhoods because nothing published says which one a lot is in. It errs
towards RED, which is the safe direction and not a free one. Untouched by the
2026-09-01 work: RN was always encoded.

**The Town Center Zone.** Eight notes that were dismissed on the zone being
missing, which was the Lake Oswego shape -- Wilsonville contributes no observed
lots to the coverage ledger, so no zone_missing row could raise a hand, and a
ledger that counts fields cannot see an absent zone. TC was encoded on
2026-09-01 and the eight were reopened, exactly as their ruling said they must
be. They are dismissed again on a stronger ground: 4.132(.02)'s only
residential use is Multiple-family Dwelling Units and 4.001(96) defines that
term as excluding middle housing, so the pod is not a permitted use there and
no standard in 4.132 reaches it. Note 6's 40-units-per-acre density floor would
have refused this building -- four units at 40 per acre needs a lot no larger
than 4,356 sq ft -- and now does not have to.

**Table 5.** Two notes, and reading them put Wilsonville's first parking
values on the page. The layer held no parking field at all, so a four-unit
building was screened here against neither a stall demand nor a stall ceiling,
and neither absence was recorded. Both are now cited exemptions.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes
from flats.rules.caps import caps_for
from flats.rules.ledger import read_coverage
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

WILSONVILLE = "or/clackamas/wilsonville"

#: Every zone this layer holds. R, OTR, the six planned-development
#: residential zones and V permit a quadplex; RN and TC do not.
ENCODED_ZONES = (
    "R",
    "OTR",
    "PDR1",
    "PDR2",
    "PDR3",
    "PDR4",
    "PDR5",
    "PDR6",
    "RN",
    "V",
    "TC",
)

#: The two that Chapter 4 stated and this layer did not hold until 2026-09-01.
#: Kept named rather than deleted: they are the corpus's worked example of a
#: gap no ledger could see, and the assertion below is now that they are here.
ONCE_MISSING_ZONES = ("V", "TC")


def test_the_layer_has_no_unread_notes_left() -> None:
    assert [n for n in notes(WILSONVILLE) if n.state == "unread"] == []


def test_the_zone_list_is_exactly_the_eleven_this_layer_holds() -> None:
    """A guard on the gap above, from the other side, and it did its job.

    It used to hold nine and fail the day the Village or Town Center zone was
    encoded, which was the whole point: the failure was the message telling the
    encoder to go back to the eight Town Center notes dismissed on the zone
    being absent. That happened on 2026-09-01, the eight were re-ruled on the
    prohibition instead, and the list is eleven.
    """
    zones = load_rules()[WILSONVILLE].zones
    assert set(zones) == set(ENCODED_ZONES)
    for zone in ONCE_MISSING_ZONES:
        assert zone in zones, zone

    # The point of encoding TC was that a zone screened as RED is a decision
    # and an absent zone is not. V is the opposite: 2,508 lots that reach the
    # fit stage for the first time.
    assert zones["TC"].values["quadplex_allowed"].value is False
    assert zones["V"].values["quadplex_allowed"].value is True


def test_no_town_center_ruling_still_rests_on_the_zone_being_absent() -> None:
    """The eight reopened notes, checked against the reason they were reopened.

    A ruling that says "not encoded because the zone is not" was true when it
    was written and is now the stale kind of refusal this corpus goes looking
    for. Each of the eight now names 4.132(.02) and the definition that closes
    it, so the dismissal survives on the code rather than on our reading list.
    """
    from flats.encode.dispositions import notes as _notes

    stale = [
        "zone this layer does not hold",
        "because the zone is not",
        "the zone is unencoded",
        "the Town Center Zone is not encoded",
        "the day TC is encoded",
    ]
    town_center = [
        n for n in _notes(WILSONVILLE)
        if "4.132" in (n.reason or "") or "Town Center" in (n.reason or "")
    ]
    assert len(town_center) == 8, len(town_center)
    for n in town_center:
        assert n.state == "dismissed", n.reason
        assert "4.132(.02)" in n.reason, n.reason
        for phrase in stale:
            assert phrase not in n.reason, (phrase, n.reason)


def test_no_coverage_row_can_see_the_missing_zones() -> None:
    """Which is the point, and why the gap had to be written down by hand.

    Wilsonville contributes no observed lots at all, so the ledger that finds
    a zone nobody encoded -- by joining what lots claim against what rules
    hold -- has nothing to join here. An empty result is not a clean one.
    """
    assert [r for r in read_coverage() if r.jurisdiction == WILSONVILLE] == []


def test_rn_is_a_settled_prohibition_read_off_frog_pond_west() -> None:
    """The reason fourteen notes on Tables 8B and 8C reach no number.

    Settled, not merely shut: nothing caps the use gate, so the reading ends
    there. Recorded alongside the fact that it is the West sentence governing
    all three neighbourhoods -- East and South are limited by variety
    standards at 4.127(.02)B.2, not prohibited.
    """
    rn = load_rules()[WILSONVILLE].zones["RN"]

    assert rn.values["quadplex_allowed"].value is False
    assert "quadplex_allowed" not in caps_for(WILSONVILLE, "RN")


def test_rn_holds_no_maximum_setback_and_table_8b_states_two() -> None:
    """Tables 8B and 8C both state maximum front and street side setbacks and
    none is encoded, because the Urban Form Type they vary by is not something
    this system can look up. Pinned so the absence is a decision."""
    rn = load_rules()[WILSONVILLE].zones["RN"]

    assert "setback_front_max_ft" not in rn.values
    assert "setback_front_max_ft" not in load_rules()[WILSONVILLE].defaults


def test_wilsonville_now_states_its_parking_absences_instead_of_holding_none() -> None:
    """Both directions, both cited, both exempt rather than missing.

    Table 5's middle housing row reads "No Limit" and the table has no
    auto-minimum column at all. An absence nobody has read is not the same
    object as an absence somebody has, and only the second one can be
    defended when a lot turns green with no stalls on it.
    """
    defaults = load_rules()[WILSONVILLE].defaults

    for field in ("parking_min_per_unit", "parking_max_per_unit"):
        value = defaults[field]
        assert value.exempt is True, field
        assert value.value is None, field
        assert value.prov.quote, field
        assert "4.155" in value.prov.cite, field


def test_the_exemptions_reach_every_zone() -> None:
    """They are layer defaults rather than per-zone values because Table 5
    sits in Section 4.155, General Regulations, and every zone chapter in this
    code sends its parking question there in a single sentence."""
    layer = load_rules()[WILSONVILLE]

    for zone in layer.zones.values():
        assert "parking_min_per_unit" not in zone.values, zone.zone
        assert "parking_max_per_unit" not in zone.values, zone.zone
