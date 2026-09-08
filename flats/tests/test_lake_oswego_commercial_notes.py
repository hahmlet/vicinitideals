"""Lake Oswego's commercial half, and the lots it costs -- which is not 93.

Thirty-three footnotes, all of them on the two tables that govern the sixteen
zones in this city that are not residential. None of the sixteen is encoded.

This file used to pin the cost at ninety-three lots: NC/R-0 with 84, PNA with
5, NC with 4, read straight off the coverage ledger. That number died on
2026-09-08 when the ledger was rebuilt over both counties, and how it died is
worth more than the number was.

The ninety-three were 6% of one city. They came from Lake Oswego's Multnomah
slice, the only part of it a Multnomah-only parcel corpus could see. The
rebuilt ledger sees 16,300 Lake Oswego lots and gives a zone to none of them,
because `Lot Analysis/quadfit/config/rules.yaml` marks the jurisdiction
`eligible: false` and `s2_assign.py` skips the zoning join for an ineligible
jurisdiction outright. So the city arrives in the ledger as a single row --
`(unzoned in parcel data)`, 14,256 lots -- and the commercial gap has no
measured size at all.

Two separate facts wore the same number, and only one of them was about
footnotes. The gap is real and the thirty-three rulings still rest on it; what
is gone is any claim about how much land is behind it.

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

#: What the ledger reports for this city, whole. One row, no zone on it.
#: Named rather than described so that re-enabling Lake Oswego in the quadfit
#: config breaks this test and sends the reader back to the thirty-three
#: rulings that assume the commercial zones are absent.
UNZONED = "(unzoned in parcel data)"

#: The zones that carried the old ninety-three, kept because they are the
#: evidence that this city's commercial land is built on and not theoretical.
#: They are no longer observable: the corpus has stopped assigning zones here.
ONCE_OBSERVED = {"NC/R-0": 84, "PNA": 5, "NC": 4}


def test_the_layer_has_no_unread_notes_left() -> None:
    assert [n for n in notes(LAKE_OSWEGO) if n.state == "unread"] == []


def test_the_whole_city_arrives_without_a_zone_on_it() -> None:
    """Not a gap in the rules. A jurisdiction the pipeline is switched off for.

    The rulings dismiss thirty-three notes on the ground that the zone is not
    encoded. That ground is only honest if what it costs is stated somewhere a
    change would break, which is here -- and what it costs is now unknown,
    stated as unknown, at a scale nine times the slice the old figure came
    from.

    A single row is the fingerprint of the switch: `s2_assign.py` joins zoning
    only where `j.eligible`, so an ineligible city's lots all land in the one
    bucket named for having no zone. If this ever splits back into R-0, R-7.5
    and the rest, somebody re-enabled Lake Oswego, and the thirty-three rulings
    below need re-reading against a city that is suddenly being screened.
    """
    rows = [r for r in read_coverage() if r.jurisdiction == LAKE_OSWEGO]

    assert [r.zone for r in rows] == [UNZONED]
    assert rows[0].status == "zone_missing"
    assert rows[0].lots == 14256
    assert rows[0].lots > 9 * sum(ONCE_OBSERVED.values())


def test_the_zones_that_carried_the_old_figure_are_no_longer_observable() -> None:
    """The three that made this gap concrete, and why the number is retired.

    NC/R-0, PNA and NC are still where Lake Oswego's unencoded commercial land
    is built on -- that has not changed and is not in doubt. What changed is
    that nothing counts them any more, so quoting 93 would be quoting a run
    that no longer exists.
    """
    observed = {
        r.zone for r in read_coverage() if r.jurisdiction == LAKE_OSWEGO
    }

    for zone in ONCE_OBSERVED:
        assert zone not in observed, zone
    assert sum(ONCE_OBSERVED.values()) == 93


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
