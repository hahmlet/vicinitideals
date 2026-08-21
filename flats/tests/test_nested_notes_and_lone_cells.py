"""The two notes printed on the cell that permits this building, and why
neither of them could be seen.

Table 315-1 of the Clackamas ZDO is the use table for the whole chapter, and
the Quadplexes row reads ``P7,8`` in all nine districts this layer holds:
permitted, subject to note 7 and note 8. Both notes were invisible, for two
unrelated reasons that happened to compound.

*The block headed one level too deep.* Note 1 of that table ends "subject to
the following criteria:" and its criteria restart at 1. The census reads a run
by its numbering, so it took the inner list -- four sub-criteria -- for notes 1
to 4 and ended the block there, eleven notes short of note 7. Reading a
sub-list as the list is not a near miss; it is four bodies that answer nothing
and eleven that were never captured at all.

*The cell that would not admit to being one.* An HTML table puts every cell on
its own line, so the row arrives as the four characters ``P7,8``. The marker
reader asks an ungapped line to carry more than one permission code before it
believes the line is a table row, because a lone "P1" in running prose is a
design element and not a permission -- and that rule, correct where it came
from, refuses every marker in a table extracted one cell per line.

Between them: the permission itself, in nine districts, governed by a pair of
notes nobody had read, and the census reporting the block reconciled because
neither the markers nor the bodies existed to disagree.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes as dispositions
from flats.encode.footnotes import census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
ZDO = f"{CLACKAMAS}/zdo.315.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# --- a note's own criteria are more of the note --------------------------


def test_a_colon_and_a_restart_are_a_sub_list_not_a_new_block() -> None:
    text = "\n".join(
        [
            "Quadplexes",
            "P3",
            "",
            "1 The limited use is permitted subject to the following criteria:",
            "",
            "1 The use shall be allowed only in a development meeting the density.",
            "",
            "2 No outdoor storage of materials shall be allowed.",
            "",
            "2 The use shall be developed in conjunction with a primary use.",
            "",
            "3 The development of a quadplex is subject to Section 845.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    # The criteria are carried as part of note 1 rather than dropped.
    assert "No outdoor storage" in seen.bodies[0].text
    assert seen.bodies[2].text.startswith("The development of a quadplex")


def test_the_sub_list_gets_first_refusal_when_both_lists_want_the_number() -> None:
    """The hard case, and the reason the rule is not simply "a lower number
    ends the sub-list". After note 1's sub-item 1, a line marked 2 is equally
    consistent with sub-item 2 and with note 2. The sub-list takes it, because
    it is the one continuing by exactly one; the outer list gets it back at the
    first mark that falls BELOW the sub-list's highest."""
    text = "\n".join(
        [
            "Quadplexes",
            "P2",
            "",
            "1 The limited use is permitted subject to the following criteria:",
            "",
            "1 The use shall meet the minimum density.",
            "",
            "2 The floor area shall not exceed 15 percent.",
            "",
            "3 No outdoor storage shall be allowed.",
            "",
            "4 The use shall produce no odor, smoke or glare.",
            "",
            "2 The use shall be developed in conjunction with a primary use.",
            "",
            "3 The development of a quadplex is subject to Section 845.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    assert "15 percent" in seen.bodies[0].text
    assert seen.bodies[1].text.startswith("The use shall be developed in conjunction")


def test_a_short_sub_list_hands_back_at_the_number_the_outer_list_wants() -> None:
    """Note 3's criteria run 1, 2 and stop, and note 4 follows. Four is above
    the sub-list's highest, so "falls back" alone would miss it -- what settles
    it is that 4 is precisely the mark the outer list is waiting for."""
    text = "\n".join(
        [
            "Quadplexes",
            "P4",
            "",
            "1 The first note.",
            "",
            "2 The second note.",
            "",
            "3 The third note, subject to the following criteria:",
            "",
            "1 The use shall meet the minimum density.",
            "",
            "2 No outdoor storage shall be allowed.",
            "",
            "4 The fourth note.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2", "3", "4"]
    assert seen.bodies[3].text == "The fourth note."


def test_without_the_colon_a_restart_still_ends_the_block() -> None:
    """The guard that keeps this from merging two tables' notes into one. A
    restart is the next table's note 1 unless the note above it said it was
    about to list its own criteria."""
    text = "\n".join(
        [
            "Quadplexes",
            "P2",
            "",
            "1 The first note.",
            "",
            "2 The second note.",
            "",
            "3 The third note.",
            "",
            "1 The next table's first note.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert len(seen.blocks) == 1
    assert [b.mark for b in seen.blocks[0].bodies] == ["1", "2", "3"]


# --- one cell on a line of its own ---------------------------------------


def test_a_lone_cell_carrying_two_notes_is_a_row() -> None:
    """"P7,8" is four characters and no room for doubt: prose does not consist
    of a permission code, and no row is called P7,8."""
    text = "\n".join(
        [
            "Quadplexes",
            "P2,3",
            "",
            "1 A note about something else.",
            "",
            "2 Each lot of record may be developed with only one dwelling type.",
            "",
            "3 The development of a quadplex is subject to Section 845.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert sorted({m.mark for m in seen.markers}) == ["2", "3"]
    assert seen.unbodied == ()


def test_a_lone_cell_with_one_note_stands_only_where_a_note_answers_it() -> None:
    """Fairview numbers its menu of design options P1 through P8, one per line,
    and a bare "P1" cannot be told from a permission with note 1 on it. So the
    single-mark form is provisional: it is a marker where a note in the region
    defines it, and nothing where none does. Read as certain either way it
    invents forty-three orphans in two documents that print no notes at all, or
    loses a hundred real markers in the documents that do."""
    answered = "\n".join(
        [
            "Quadplexes",
            "P1",
            "",
            "1 The development is subject to Section 845.",
            "",
            "2 A second note.",
            "",
            "3 A third note.",
        ]
    )
    assert [m.mark for m in census(answered, doc="d.txt").markers] == ["1"]

    menu = "\n".join(
        [
            "Table 19.65.090(B)(2) - Menu of Options",
            "No.",
            "Design Option",
            "P1",
            "Additional Plaza Area. Provide an outdoor plaza abutting a sidewalk.",
            "P2",
            "Outdoor Recreation Area. Provide 800 square feet of common area.",
        ]
    )
    got = census(menu, doc="d.txt")
    assert got.markers == ()
    assert got.reconciled


# --- what the document behind the layer says now -------------------------


def test_the_use_table_block_reaches_the_notes_on_the_cell(store: ProvenanceStore) -> None:
    got = census(store.load(ZDO).text, layer=CLACKAMAS, doc=ZDO)
    first = got.blocks[0]
    assert first.head == 1040
    assert [b.mark for b in first.bodies] == [str(n) for n in range(1, 24)]
    seven, eight = (b for b in first.bodies if b.mark in ("7", "8"))
    assert "each lot of record may be developed with only one" in seven.text
    assert eight.text.startswith("The development of a triplex, quadplex, townhouse")


def test_and_the_cell_that_points_at_them_is_read_as_a_row(store: ProvenanceStore) -> None:
    got = census(store.load(ZDO).text, layer=CLACKAMAS, doc=ZDO)
    on_the_cell = {m.mark for m in got.markers if m.line in (296, 297)}
    assert on_the_cell == {"7", "8"}


def test_every_note_in_this_layer_is_ruled_and_none_of_them_blocks() -> None:
    """Seventy-seven, from four blocks, none left unread. The count is the
    point: the layer reported clean at zero, at fifty-seven, and again at
    seventy-seven, and only the last of those is because it is."""
    ruled = list(dispositions(CLACKAMAS))
    assert len(ruled) == 77
    assert not [n for n in ruled if n.state == "unread"]
    rows = [r for r in qualified() if r.layer == CLACKAMAS]
    assert len(rows) == 64
    assert not any(r.blocking for r in rows)


def test_and_still_not_one_encoded_number_moved() -> None:
    """Thirty-six more notes read than yesterday, and every one of them is
    about another use, another district's table, or a rule this building
    already satisfies. The two on the cell are the one-primary-building rule --
    which bars combining dwelling types, and this is one type -- and the
    pointer to Section 845, which this layer already reads."""
    from flats.rules.loader import load_rules
    from flats.rules.resolver import RuleSet

    rules = RuleSet(load_rules())
    for zone in ("R5", "R7", "R8.5", "R10", "R15", "R20", "R30", "VR57", "VR45"):
        got = rules.resolve(CLACKAMAS, zone)
        assert got.values["max_height_ft"].value == 35, zone
        assert got.values["quadplex_allowed"].value is True, zone
        assert got.values["min_lot_sqft"].value == 7000, zone
