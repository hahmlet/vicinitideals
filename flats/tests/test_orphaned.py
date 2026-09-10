"""One sentence in the corpus lost its number. Only one.

:mod:`flats.encode.orphaned` looks for a unit word standing where a
measurement should be -- "a height of feet", "no more than percent" -- which is
what a dropped numeral leaves behind in prose. The sentence still reads as
English, so nothing else in this pipeline notices: no number is misquoted,
because no number is there to misquote.

Like :mod:`flats.tests.test_ragged` this is a test rather than a report
because the corpus separates cleanly. Happy Valley's accessory-structure
setback is the one hit; every other candidate is a two-column line that wrapped
between the numeral and its unit, or an "of" that introduces a count.

It fails in both directions on purpose. A second orphan means a document was
fetched with a standard silently missing from it. Happy Valley's going away
means the document was re-fetched and 16.22.050 is owed a re-read.
"""

from __future__ import annotations

from flats.encode.orphaned import ORPHAN, orphans, scan

#: The one sentence known to have lost a numeral. Happy Valley 16.22.050(H),
#: detached accessory structures: "...that is 100 square feet or less in area
#: and does not exceed a height of feet." The two subsections beneath it say
#: "eight feet in height", so the word that went missing is `eight`.
#:
#: It costs this project nothing today -- the pod has no accessory structure,
#: which was put to the owner and answered on 2026-09-08 -- and it is pinned
#: here anyway, because a standard that vanished without leaving a hole is the
#: failure this corpus keeps finding and the next one may not be free.
KNOWN_ORPHAN = "or/clackamas/happy-valley/16.22.residential.txt#L1138"


def test_exactly_one_stored_sentence_lost_its_number() -> None:
    found = [o.cite for o in scan()]
    assert found == [KNOWN_ORPHAN], (
        "a unit word with no measurement in front of it is a standard that "
        "went missing on the way into the store, and it leaves no hole for any "
        f"other check to find. Orphaned now: {found}"
    )


def test_a_wrapped_line_is_not_an_orphan() -> None:
    """Gresham sets its downtown standards in two columns.

    The numeral ends one row and the unit starts the next, four times in the
    corpus, and every one of those is extracted correctly. Reading the line
    alone would report all four.
    """
    wrapped = ["uses shall be predominantly at an elevation no more than 2", "feet above or below the sidewalk elevation."]
    assert orphans(wrapped) == []
    assert ORPHAN.search(wrapped[1]) is None
    assert orphans(["something entirely unrelated", "feet above or below the sidewalk elevation."]) == []


def test_a_count_is_not_a_measurement() -> None:
    """"The number of stories" is English; "a height of feet" is a hole.

    The noun that decides which one it is may sit at the end of the line
    above, which is how Wilsonville writes it.
    """
    assert orphans(["shall not exceed the maximum number", "of stories permitted in the zone"]) == []
    assert orphans(["The ratio of the total amount", "of acres in the parcel"]) == []


def test_the_hole_itself_is_found() -> None:
    assert orphans(["and does not exceed a height of feet."]) == [1]
    assert orphans(["shall be no less than percent of the lot"]) == [1]
