"""A footnote ruling binds to the sentence, so it goes where the sentence goes.

The register looks a ruling up by the digest of the note's text. That is what
lets one decision answer the same sentence under two tables, and it is what
made Clackamas ZDO 315's note 6 answer ZDO 510's note 11 before anybody had
read Section 510 -- with the argument "a quadplex is already permitted outright
in all nine districts", which is true of Section 315 and false of Section 510.

``flats/encode/travelled.py`` asks the two questions that would have caught it,
and these tests pin both the behaviour and the corpus being clean.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import Note, Ruling
from flats.encode.travelled import audit, shadowed, shared

pytestmark = pytest.mark.unit


def _note(doc: str, text: str, reason: str, *, line: int = 1) -> Note:
    return Note(
        layer="or/test/city",
        doc=f"or/test/city/{doc}.txt",
        line=line,
        mark="1",
        text=text,
        state="dismissed",
        reason=reason,
    )


SENTENCE = "Dwellings not otherwise permitted may be built as affordable housing."


# --- the shape that was missed ---------------------------------------------


def test_a_reason_about_one_table_answering_two_is_the_finding() -> None:
    """The 2026-09-08 failure, reduced to two notes and one reason.

    The same sentence under two tables, and a reason that argues about the
    first one. It is a legitimate argument about a page and a wrong one about
    the page it also lands on, which is why `stale.py` cannot see it: nothing
    in the reason is a claim about our corpus.
    """
    reason = "Table 315-1 permits a quadplex outright in all nine districts"
    rows = audit([_note("zdo.315", SENTENCE, reason), _note("zdo.510", SENTENCE, reason)])

    assert len(rows) == 1
    assert rows[0].appears_in == ("zdo.315", "zdo.510")
    assert rows[0].names == ("zdo.315",)
    assert rows[0].silent_on == ("zdo.510",)


def test_a_reason_that_names_both_tables_is_the_repair() -> None:
    """What the four rewrites of that day were rewritten into.

    "In neither of the two use tables this sentence appears in is the marker
    printed on a dwelling row" is checkable in both places. So is a reason that
    names both by number, and that is the form this check accepts.
    """
    reason = "on the group heading in both Table 315-1 and Table 510-1, not on a quadplex cell"
    assert audit([_note("zdo.315", SENTENCE, reason), _note("zdo.510", SENTENCE, reason)]) == []


def test_a_reason_naming_no_document_at_all_is_the_shape_to_prefer() -> None:
    """An argument about what the sentence says travels correctly.

    Most reasons in the register are this, which is why the queue is small.
    Nothing here can check them and nothing here should: a reason with no
    document in it makes no claim about scope.
    """
    reason = "a permission that turns on what is developed rather than on the lot"
    assert audit([_note("zdo.315", SENTENCE, reason), _note("zdo.510", SENTENCE, reason)]) == []


def test_a_cross_reference_out_of_the_sentence_is_not_a_scope_claim() -> None:
    """"Subject to Section 846" names a chapter the sentence is not in.

    The check only ever looks at documents the sentence is actually printed
    in. A citation pointing somewhere else is evidence, not a narrowing, and
    calling it one would flag most of the register.
    """
    reason = "the affordable-housing door, subject to Section 846 and ORS 197A.445(1)"
    assert audit([_note("zdo.315", SENTENCE, reason), _note("zdo.510", SENTENCE, reason)]) == []


def test_the_gresham_shape_a_dotted_chapter_number_naming_one_of_three() -> None:
    """The second live row, kept as a fixture because the matcher is fiddly.

    Gresham numbers its whole code 4.xxxx, so a document head has to be the
    full dotted chapter ("4.0200") and never its bare first component -- "4"
    alone would match every chapter in the city and make every Gresham reason
    look like it named all of them.
    """
    reason = "a note of Section 4.0200, whose use table has one column and reads NP"
    text = "Affordable housing development is permitted. See Section 10.1700."
    rows = audit(
        [
            _note("4.0200.commercial", text, reason),
            _note("4.1400.pleasant-valley", text, reason),
            _note("4.1500.springwater", text, reason),
        ]
    )

    assert len(rows) == 1
    assert rows[0].names == ("4.0200.commercial",)
    assert rows[0].silent_on == ("4.1400.pleasant-valley", "4.1500.springwater")


def test_a_sentence_printed_once_is_never_flagged() -> None:
    """There is nowhere for a reason to travel to."""
    reason = "Table 315-1 permits a quadplex outright in all nine districts"
    assert audit([_note("zdo.315", SENTENCE, reason)]) == []


# --- the same defect from the other side -----------------------------------


def _ruling(quote: str, reason: str) -> Ruling:
    return Ruling(
        layer="or/test/city",
        digest="deadbeefcafe",
        state="dismissed",
        reason=reason,
        quote=quote,
    )


def test_two_answers_to_one_sentence_and_only_the_last_is_read() -> None:
    """``_join`` builds ``by_digest`` last-wins, so file order decides.

    Nine such pairs existed on the day this was written. In all nine the state
    agreed, so no conclusion turned on the order -- but three kept a reason
    written about one document and dropped the one written about another, and
    one kept an entry whose whole reason was "left here as a pointer only"
    over the entry that said what was encoded and why.
    """
    pairs = shadowed(
        {
            "or/test/city": [
                _ruling("a.txt#L1", "marked on the Cottage Cluster row"),
                _ruling("b.txt#L9", "left here as a pointer only"),
            ]
        }
    )

    assert len(pairs) == 1
    assert pairs[0].kept.quote == "b.txt#L9"
    assert [r.quote for r in pairs[0].dropped] == ["a.txt#L1"]


def test_two_entries_saying_the_same_thing_are_not_a_conflict() -> None:
    """A sentence printed twice is worth recording twice.

    The cure for a shadowed pair is one reason true everywhere, written into
    both entries -- not the deletion of one of them, which would lose the
    record that the codifier prints the sentence in two places.
    """
    same = "marked on the Cottage Cluster row in both tables that print it"
    assert shadowed({"or/test/city": [_ruling("a.txt#L1", same), _ruling("b.txt#L9", same)]}) == []


# --- and the corpus ---------------------------------------------------------


def test_no_reason_in_the_corpus_is_narrower_than_its_own_reach() -> None:
    """Zero, and it is a guard rather than a queue.

    Two live rows on 2026-09-08 when this was first run: Clackamas Table
    315-2's note 1, whose reason named Table 315-2 for a sentence Table 316-2
    reprints word for word, and Gresham's affordable-housing note, ruled on a
    fact about the commercial table's one-column use table and reused in
    Pleasant Valley and Springwater. Both rewritten.
    """
    rows = audit()
    assert rows == [], "\n".join(
        f"{r.layer} {r.digest}: names {r.names}, silent on {r.silent_on}" for r in rows
    )


def test_no_sentence_is_answered_twice_with_two_different_answers() -> None:
    """Zero, for the same reason: a dropped reason is a decision nobody reads."""
    pairs = shadowed()
    assert pairs == [], "\n".join(
        f"{p.layer} {p.digest}: keeps {p.kept.quote}, drops "
        + ", ".join(g.quote for g in p.dropped)
        for p in pairs
    )


def test_the_exposure_is_real_and_deliberately_not_pinned() -> None:
    """How many ruled sentences one decision answers in more than one document.

    Thirty-four on the day this was written, and it is the reason the check
    exists rather than a number to defend: it moves every time a chapter is
    fetched whose codifier reprints sentences, which is most of them. Pinning
    it would turn a healthy design into a test failure. What is pinned is that
    it is not zero -- if it ever were, the digest join would have stopped
    doing the thing these tests are about.
    """
    assert shared() > 0
