"""Lake Oswego's commercial half, and the ninety-three lots it costs.

Thirty-three footnotes, all of them on the two tables that govern the sixteen
zones in this city that are not residential. None of the sixteen is encoded.
Three of them carry observed lots -- NC/R-0 with 84, PNA with 5, NC with 4 --
so unlike Gresham's unbuilt sub-districts and unlike Wilsonville's Town Center
this gap is visible in the ledger, has a size, and is pinned here.

**The tables resolve, and the notes are what resolve them.** Both extract as a
header block followed by a flat run of cells with no column attached, and a
row with fewer cells than columns has invisible blanks in it. The commercial
dimensional table has eleven columns and its height row prints ten cells. Four
of its notes name their own zone -- [18] is FMU State Street Height, [11]
points at the section headed CR&D Zone Height Measurement, [13] at the one
headed MC Zone Height Measurement, and the fifth cell is a bare
cross-reference to the one headed EC Zone Height Measurement. Line those up
and the row reads with a single blank, at the column whose header already says
to look elsewhere. The left edge is anchored independently in the use table,
where three separate rows put note [10] -- expressly a GC note -- second.

That makes NC readable, and NC is where the lots are. It is still not encoded,
because encoding a zone is a different act from ruling a footnote and because
the use gate needs LOC 50.03.003.2, which this corpus has not fetched. The
tail of both tables stays ambiguous and stays unencoded with it.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes
from flats.rules.ledger import read_coverage
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

LAKE_OSWEGO = "or/clackamas/lake-oswego"

#: Every column of Table 50.03.002-2, the commercial, mixed use, industrial
#: and special purpose use table. None is encoded.
COMMERCIAL_ZONES = (
    "NC",
    "GC",
    "HC",
    "OC",
    "EC",
    "CR&D",
    "MC",
    "WLG OC",
    "WLG RMU",
    "WLG R-2.5",
    "FMU",
    "I",
    "IP",
    "CI",
    "PF",
    "PNA",
)

#: Zones observed on real lots that this layer does not hold, with the lot
#: count the coverage ledger reports for each.
ZONE_MISSING = {"NC/R-0": 84, "PNA": 5, "NC": 4}


def test_the_layer_has_no_unread_notes_left() -> None:
    assert [n for n in notes(LAKE_OSWEGO) if n.state == "unread"] == []


def test_the_gap_has_the_size_the_rulings_claim() -> None:
    """Ninety-three lots reporting zone_missing.

    The rulings dismiss thirty-three notes on the ground that the zone is not
    encoded. That ground is only honest if the size of what it costs is stated
    somewhere a change would break, which is here.
    """
    missing = {
        row.zone: row.lots
        for row in read_coverage()
        if row.jurisdiction == LAKE_OSWEGO and row.status == "zone_missing"
    }

    for zone, lots in ZONE_MISSING.items():
        assert missing.get(zone) == lots, zone
    assert sum(ZONE_MISSING.values()) == 93


def test_no_commercial_zone_is_encoded() -> None:
    """All sixteen, so that encoding any one of them fails this test and sends
    the encoder back to the thirty-three rulings that assume it is absent."""
    encoded = set(load_rules()[LAKE_OSWEGO].zones)

    for zone in COMMERCIAL_ZONES:
        assert zone not in encoded, zone


def test_the_zones_this_layer_does_hold_are_all_residential() -> None:
    """Ten of them, every one an R-something. The split is not an accident of
    encoding order: the residential use table and the commercial use table are
    two different tables in the code, and only the first has been read."""
    encoded = sorted(load_rules()[LAKE_OSWEGO].zones)

    assert encoded == [
        "R-0",
        "R-10",
        "R-15",
        "R-2",
        "R-3",
        "R-5",
        "R-6",
        "R-7.5",
        "R-DD",
        "R-W",
    ]


def test_the_split_zone_note_is_one_ruling_over_two_printings() -> None:
    """The same sentence is note 3 of the residential use table and note 8 of
    the commercial one, so a single ruling covers both -- the disposition join
    is on the text, not the line. Worth pinning because the second printing is
    what reaches NC/R-0, the largest missing row in the jurisdiction."""
    split = [
        n
        for n in notes(LAKE_OSWEGO)
        if n.state == "unmeasured" and n.fact == "split_zone"
    ]

    assert len(split) == 2
    assert {n.quote for n in split} == {
        "or/clackamas/lake-oswego/50.03.002.use-table.txt#L491",
        "or/clackamas/lake-oswego/50.03.002.use-table.txt#L1281",
    }
