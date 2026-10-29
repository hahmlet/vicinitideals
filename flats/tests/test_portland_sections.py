"""Portland cut into sections (FOLLOWUPS 73, batch 6): the reading rules the
cut needed so no footnote, note marker or glossary term came loose.

Each test is a shape Portland's readable text takes that the proof copy did
not: a table caption and its title on one line, a use table's limitations in
one section file and the table in the next, a table note opening its own
line, and the glossary's en-dash sub-terms.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import _borrowed, _caption, census
from flats.encode.glossary import _entries
from flats.provenance.readable import clean

pytestmark = pytest.mark.unit

LONG = "The purpose of this zone is to provide housing for the people who live in the town and"


# --- a caption and its title on one line ---------------------------------


def test_a_caption_with_its_title_behind_a_space_is_a_caption() -> None:
    assert _caption("Table 130-1 Commercial/Mixed Use Zone Primary Uses") == ("130", "1")
    assert _caption("Table 140-1 Uses in Manufacturing Zones") == ("140", "1")
    assert _caption("Table 110-1") == ("110", "1")
    assert _caption("Table 120-3: Development Standards") == ("120", "3")


def test_a_sentence_that_starts_with_a_table_number_is_not() -> None:
    """The title's own case is what keeps a sentence out now that a space may
    stand where the full stop was."""
    assert _caption("Table 110-1. Uses that are allowed if approved through a review") is None
    assert _caption("Table 140-1 that have a [3]. This regulation applies") is None
    assert _caption("Table 40-2 lists housing types") is None


# --- limitations in one section, their table in the next -----------------


TABLE = [
    "99.100.110 Accessory Uses",
    "Table 99-1 Zone Primary Uses",
    "Use Categories",
    "Household Living                          Y",
    "Retail Sales And Service                  CU [1]",
    "Agriculture                               L [2]",
]

LIMITS = [
    "99.100.100 Primary Uses",
    "B.  Limited uses. The paragraphs below correspond with the footnote",
    "numbers from Table 99-1.",
    "1.  Retail Sales And Service. This regulation applies to all parts of",
    "Table 99-1 that have a [1]. Retail uses are conditional uses only when",
    "they are associated with a Park And Open Areas use.",
    "2.  Agriculture. This regulation applies to all parts of Table 99-1 that",
    "have a [2]. Agriculture is an allowed use.",
    "C.  Conditional uses.",
]

LAYER = "zz/portland"


def _survey(texts: dict[str, str]):
    borrowed, lent = _borrowed(texts, LAYER)
    return {
        doc: census(text, layer=LAYER, doc=doc, borrowed=borrowed.get(doc, ()), lent=lent.get(doc, ()))
        for doc, text in texts.items()
    }


def test_a_table_cut_away_from_its_limitations_still_finds_them() -> None:
    """Cut, the limitations and the table are two files; without the borrow
    every marker in the table is an orphan and every limitation a note
    nobody points at -- the false-GREEN path."""
    limits, table = f"{LAYER}/99.100/99.100.100.txt", f"{LAYER}/99.100/99.100.110.txt"
    seen = _survey({limits: "\n".join(LIMITS), table: "\n".join(TABLE)})
    got = seen[table]
    assert [b.mark for b in got.bodies] == ["1", "2"]
    # the bodies keep the file and line they are printed on
    assert {b.doc for b in got.bodies} == {limits}
    assert [b.line for b in got.bodies] == [4, 7]
    assert got.reconciled
    # and the file that lent them reads its declarations as declarations
    assert seen[limits].markers == ()


def test_two_sections_printing_the_table_borrow_nothing() -> None:
    limits = f"{LAYER}/99.100/99.100.100.txt"
    texts = {
        limits: "\n".join(LIMITS),
        f"{LAYER}/99.100/99.100.110.txt": "\n".join(TABLE),
        f"{LAYER}/99.100/99.100.120.txt": "\n".join(TABLE),
    }
    seen = _survey(texts)
    assert all(c.bodies == () for c in seen.values())


def test_a_whole_document_at_the_top_of_the_layer_is_never_searched() -> None:
    """A chapter left whole is one document; its siblings are other chapters."""
    seen = _survey({f"{LAYER}/99.100.txt": "\n".join(LIMITS), f"{LAYER}/99.200.txt": "\n".join(TABLE)})
    assert all(c.bodies == () for c in seen.values())


# --- a table note opening its own line -----------------------------------


def test_a_bracketed_note_opening_a_line_is_not_joined_to_the_line_above() -> None:
    lines = [LONG, "[2] For sites in the RM2 zone the setback is 10 feet."]
    assert len(clean(lines).lines) == 2
    # a bracketed number inside a sentence still carries the sentence on
    assert len(clean([LONG, "[2] and the rest of the sentence."]).lines) == 1


# --- glossary sub-terms --------------------------------------------------


def _terms(text: str) -> list[str]:
    return [e.term for e in _entries(text, layer="zz", doc="zz/d.txt")]


def test_an_en_dash_sub_term_and_a_hyphenated_term_are_entries() -> None:
    text = "\n".join(
        [
            "Manufactured Dwelling.",
            "A dwelling unit constructed off site and moved onto the lot.",
            "– Manufactured Home.",
            "A manufactured dwelling built to the federal standards.",
            "• Off-site Mitigation.",
            "Mitigation carried out on a site other than the one disturbed.",
        ]
    )
    got = _terms(text)
    assert "Manufactured Home" in got
    assert "Off-site Mitigation" in got


def test_a_dash_before_see_is_a_pointer_not_a_term() -> None:
    text = "\n".join(['"Story"', "– See Oregon Residential Specialty Code."])
    assert not any(t.startswith("See") for t in _terms(text))


def test_a_see_pointer_on_its_own_line_stays_in_the_body() -> None:
    """Portland's Corner Lot ends "See Figure 910-4." over "A corner lot may
    also be a through lot."; a capitalised line closed by a full stop has a
    stacked term's shape, and the body stopped at the pointer."""
    from flats.encode.glossary import _whole

    lines = ["See Figure 910-4.", "A corner lot may also be a through lot.", "• Flag Lot."]
    body = _whole(lines, 0, "A lot that has frontage on more than one intersecting street.")
    assert body.endswith("A corner lot may also be a through lot.")
