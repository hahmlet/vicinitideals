"""Read the whole chapter, and be able to say whether you did.

Capture is the easy half. The half that matters is knowing when capture
failed, and a definitions chapter offers two independent tells: it is
alphabetical, so entries that will not sort are ones we invented; and it is
mostly definitions, so a thousand lines yielding thirty of them is a shape
nobody has taught the matcher yet. Disorder catches the first. Density catches
the second. Neither catches everything, and together they stop a chapter we
skimmed from reading as a chapter we read.
"""

from __future__ import annotations

import pytest

from flats.encode.glossary import Chapter, Entry, chapters, render
from flats.encode.glossary import _entries as entries_in
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit


def read(text: str) -> list[Entry]:
    return entries_in(text, layer="zz/test", doc="zz/test/defs.txt")


# --- the shapes an entry is set in -------------------------------------


def test_the_four_typographies_are_all_entries() -> None:
    text = "\n".join(
        [
            "Abut. Contiguous to; adjoining with a common boundary line of some kind.",
            '"Corner lot" means a lot abutting on two intersecting streets other than an alley.',
            "Lot (Corner) – A lot at the junction of and abutting two or more intersecting streets.",
            "Frontage: That portion of a lot abutting a street other than an alley or a path.",
        ]
    )
    got = read(text)
    assert [e.term for e in got] == ["Abut", "Corner lot", "Lot (Corner)", "Frontage"]
    assert all(e.shape == "inline" for e in got)


def test_a_term_alone_above_its_body_is_an_entry() -> None:
    """Milwaukie's codifier sets every entry this way. A matcher that only
    knows the inline form reads the whole chapter as prose."""
    text = "\n".join(
        [
            "Corner lot",
            "A lot abutting on two intersecting streets other than an alley.",
        ]
    )
    got = read(text)
    assert [(e.term, e.shape) for e in got] == [("Corner lot", "stacked")]
    assert got[0].text.startswith("A lot abutting")


# --- and the things set exactly like one that are not ------------------


def test_the_codifiers_apparatus_is_not_a_definition() -> None:
    """Gladstone prints "History  Ord. 1131 2, 1990; Repealed by Ord. 1323 1,
    2002." under every repealed section. Sixty perfectly formed entries about
    ordinances rather than about words -- and they wrecked the alphabetical
    check they were also invisible to."""
    text = "\n".join(
        [
            "History  Ord. 1131 2, 1990; Repealed by Ord. 1323 1, 2002. And more text here.",
            "Editor's note. The provisions of this chapter were renumbered in 2004 by staff.",
        ]
    )
    assert read(text) == []


def test_a_cross_reference_is_not_a_meaning() -> None:
    text = "Corner Lot. See Lot, types of, in Section 3.0100 of this development code."
    assert read(text) == []


def test_a_list_marker_is_not_a_term() -> None:
    """Gresham's chapter opens with "A  Overlay District Terms and
    Definitions. Section 3.0120". A, B, C and D are not words it defined."""
    text = "A  Overlay District Terms and Definitions. Section 3.0120 of the code."
    assert read(text) == []


def test_a_page_stamp_is_not_a_body() -> None:
    """A layout extraction pads a page stamp across the column, so
    "[3.0100-  2]" clears any length rule until the whitespace comes out."""
    text = "\n".join(["Approved Tree List", "[3.0100-                              2]"])
    assert read(text) == []


def test_the_next_term_is_not_this_terms_body() -> None:
    """Two headings in a row means this one's body is somewhere we did not
    look. Taking the next heading would file one term's meaning under
    another term's name, which is worse than missing it."""
    text = "\n".join(["Renewable Energy Related Terms", "Battery Charging Station"])
    assert read(text) == []


def test_a_bullet_forty_spaces_from_its_term_is_still_an_entry() -> None:
    """Portland sets a bullet at the left margin and the term most of a column
    later. A fixed-width prefix reads the whole chapter as prose -- 68 entries
    of it, including the corner-lot definition already encoded by hand."""
    text = "     " + "•" + " " * 40 + "Corner Lot. A lot that has frontage on more than one intersecting street."
    got = read(text)
    assert [e.term for e in got] == ["Corner Lot"]
    assert got[0].text.startswith("A lot that has frontage")


def test_a_body_that_is_the_next_entry_is_not_this_terms_body() -> None:
    """The misfiling this module has to be incapable of. Portland wraps long
    terms across two lines, so the line under a heading is often the next
    entry -- taking it files one term's meaning under another term's name,
    which reads as captured and is worse than missing."""
    text = "\n".join(
        [
            "Primary Structure",
            "Accessory Use. A use or activity which is a subordinate part of a primary use.",
        ]
    )
    assert [e.term for e in read(text)] == ["Accessory Use"]


def test_a_term_that_is_only_the_first_word_of_itself_is_refused() -> None:
    text = "Pedestrian\nOriented Development. Development designed with an emphasis on walking."
    assert [e.term for e in read(text)] == ["Oriented Development"]


def test_a_pointer_is_not_a_term() -> None:
    """"See also Auto-Accommodating Development" is the tail of the entry
    above, set on its own line by the extraction."""
    text = "See also Auto-Accommodating Development. Development which accommodates cars first."
    assert read(text) == []


# --- knowing when the reading failed -----------------------------------


def chapter(terms: list[str], *, lines: int = 1000) -> Chapter:
    made = [
        Entry(layer="zz", doc="zz/d.txt", line=i + 1, term=t, text="x" * 50)
        for i, t in enumerate(terms)
    ]
    from flats.encode.glossary import _disorder

    return Chapter(
        layer="zz", doc="zz/d.txt", entries=tuple(made), disorder=tuple(_disorder(made)), lines=lines
    )


def test_one_stray_heading_does_not_condemn_the_entries_after_it() -> None:
    """Front matter sits above the entries, so the naive rule -- flag anything
    sorting under the highest key so far -- reports every real entry from A to
    F as broken. The measure is the *fewest* entries whose removal leaves the
    chapter in order, and here that is one."""
    got = chapter(["General provisions", "Abut", "Access", "Adjacent", "Alley", "Building"])
    assert [e.term for e in got.disorder] == ["General provisions"]
    assert got.orderly


def test_a_chapter_may_hold_more_than_one_alphabet() -> None:
    """Gresham restarts for overlay districts, renewable energy, trees and
    temporary uses -- four more alphabets under one chapter number. Measured
    as a single sequence each restart reads as a hundred broken entries, which
    measures our reading rather than theirs."""
    got = chapter(
        ["Abut", "Building", "Street", "Zone"]
        + ["Access", "Battery", "Charging", "Solar", "Wind"]
    )
    assert got.disorder == ()
    assert got.orderly


def test_a_chapter_of_noise_is_not_orderly() -> None:
    got = chapter(["Zebra", "Apple", "Yak", "Bee", "Xylophone", "Cat", "Walrus", "Dog"])
    assert len(got.disorder) > 2
    assert not got.orderly


def test_too_few_entries_for_the_size_of_the_chapter_is_thin() -> None:
    """The other direction, and the one disorder cannot see: a chapter set in
    a shape the matcher does not know yields a handful of perfectly ordered
    entries and looks like success."""
    assert chapter(["Abut", "Building"], lines=1300).thin
    assert not chapter([f"Term {i:03d}" for i in range(200)], lines=1300).thin
    # A short chapter is not thin. Some definitions sections are ten entries.
    assert not chapter(["Abut"], lines=40).thin


# --- over the corpus ---------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> list[Chapter]:
    return chapters()


def test_every_held_definitions_chapter_is_read(corpus: list[Chapter]) -> None:
    assert len(corpus) >= 11
    assert sum(len(c.entries) for c in corpus) > 2000
    assert all(c.entries for c in corpus)


def test_the_chapters_we_have_not_really_read_are_named(corpus: list[Chapter]) -> None:
    """Multnomah County's chapter is a two-column PDF whose entries are set in
    a shape this matcher does not know: 1,300 lines and 28 entries. It reports
    thin rather than reporting done."""
    thin = [c.layer for c in corpus if not c.read_whole]
    assert "or/multnomah/_unincorporated" in thin
    # And the rest are read, or this test is measuring nothing.
    assert len(thin) < len(corpus) // 2


def test_an_encoded_definition_lands_on_a_captured_entry(corpus: list[Chapter]) -> None:
    """The cross-check between the two subsystems, and it is two-sided.

    Every corner-lot definition we encoded by hand cites a line; the glossary
    reads the same chapters mechanically. Where both looked at the same
    chapter they have to agree -- or, where they do not, the chapter is
    already on the list of chapters we did not really read. A disagreement
    nobody is told about is the only outcome ruled out.
    """
    by_layer = {c.layer: c for c in corpus}
    agreed, disagreed = 0, []
    for layer_id, layer in load_rules().items():
        defn = layer.definitions.get("corner_lot")
        chapter_read = by_layer.get(layer_id)
        if defn is None or chapter_read is None:
            continue
        doc, _, ref = defn.quote.partition("#L")
        if doc != chapter_read.doc:
            continue
        line = int(ref.split("-")[0])
        if any(abs(e.line - line) <= 2 for e in chapter_read.entries):
            agreed += 1
        else:
            disagreed.append((layer_id, chapter_read.read_whole))
    assert agreed >= 5, "the cross-check ran against too little to mean anything"
    assert all(not read_whole for _, read_whole in disagreed), (
        f"a hand-encoded definition the glossary missed in a chapter it "
        f"reported as fully read: {disagreed}"
    )


def test_the_report_says_which_chapters_are_doubtful(corpus: list[Chapter]) -> None:
    text = render(corpus)
    assert "read_whole=" in text
    assert "/100 lines" in text
