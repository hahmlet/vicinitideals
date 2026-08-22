"""Wilsonville's last twenty-four footnotes, and the two zones nobody encoded.

Three groups, three different reasons, and only one of them is comfortable.

**Tables 8B and 8C.** Fourteen notes on the two thirds of the RN zone this
layer does not read from. 4.127(.08)C splits RN in two -- Frog Pond West is
governed by Table 8A, Frog Pond East and South by Table 8B -- and every RN
dimension in the corpus comes off Table 8A. The notes reach nothing because
RN's quadplex row is a settled prohibition, but the prohibition itself is a
Frog Pond West sentence (4.127(.02)B.1.a.ii) applied to all three
neighbourhoods because nothing published says which one a lot is in. It errs
towards RED, which is the safe direction and not a free one.

**The Town Center Zone.** Eight notes on a zone that is missing. Wilsonville
contributes no observed lots to the coverage ledger, so there is no
zone_missing row to raise a hand -- this is the Lake Oswego shape, where a
ledger that counts fields cannot see an absent zone. Gresham's four unheld
districts were safe because no lot claimed them; that check cannot be run
here. TC permits housing and sets a minimum density of 40 units per acre.

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

#: Every zone this layer holds. R, OTR and the six planned-development
#: residential zones permit a quadplex; RN does not.
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
)

#: Zones Chapter 4 states and this layer does not hold, both of which permit
#: housing. Named so the gap is a fact in the test suite rather than a
#: sentence in a comment.
UNENCODED_ZONES = ("V", "TC")


def test_the_layer_has_no_unread_notes_left() -> None:
    assert [n for n in notes(WILSONVILLE) if n.state == "unread"] == []


def test_the_zone_list_is_exactly_the_nine_this_layer_holds() -> None:
    """A guard on the gap above, from the other side.

    If the Village or Town Center zone is ever encoded, this test fails and
    sends the encoder back to the fourteen Table 8B notes and the eight Town
    Center notes, all of which are dismissed on the zone being absent.
    """
    assert set(load_rules()[WILSONVILLE].zones) == set(ENCODED_ZONES)
    for zone in UNENCODED_ZONES:
        assert zone not in load_rules()[WILSONVILLE].zones, zone


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
