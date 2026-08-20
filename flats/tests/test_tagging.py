"""Marking the city's own words, and refusing to guess the ones we skipped.

Two things are being pinned here and they pull in opposite directions. The
marking has to be generous -- a reviewer wants every defined word in the
sentence in front of them, including the ordinary-looking ones, because
"street" and "lot" are exactly the words a code redefines. The gate has to be
mean -- it fires only where FLATS must *evaluate* a term on a real parcel,
because a gate that fires on every defined word fires on everything.
"""

from __future__ import annotations

import pytest

from flats.encode.glossary import Chapter, Entry
from flats.encode.readiness import ACTION, STAGES, readiness_for
from flats.encode.tagging import (
    Gap,
    Index,
    blocked,
    gaps,
    index,
    normal,
    render_gaps,
    spellings,
    tagged,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"


def entry(term: str, *, line: int = 1) -> Entry:
    return Entry(
        layer="zz/test",
        doc="zz/test/defs.txt",
        line=line,
        term=term,
        text="a definition long enough to be one, stated in the city's own words",
    )


# --- how a term is spelled where it is used ----------------------------


def test_a_term_indexed_backwards_is_matched_forwards() -> None:
    """Codes headline "Lot, Corner" and then write "corner lot" in the
    standard. An index built only from the entry's own spelling marks nothing
    where the marking would do any good."""
    assert "corner lot" in spellings(entry("Lot, Corner"))
    assert "lot corner" in spellings(entry("Lot, Corner"))
    assert "corner lot" in spellings(entry("Lot (Corner)"))


def test_marking_ignores_case_and_punctuation() -> None:
    assert normal("Lot-Related Definitions") == "lot related definitions"


def test_the_longest_defined_phrase_wins() -> None:
    """"Corner lot" is one defined word, not "lot" with an adjective in front
    of it. Marking the short one would send the reviewer to the wrong entry."""
    marks = Index(_chapter([entry("Lot"), entry("Corner lot", line=9)])).marks(
        "The setback applies on a corner lot."
    )
    assert [m.term for m in marks] == ["Corner lot"]
    assert marks[0].defined_at == "zz/test/defs.txt#L9"


def test_a_defined_word_inside_a_longer_word_is_not_a_mark() -> None:
    marks = Index(_chapter([entry("tree")])).marks("Measured from the street centerline.")
    assert marks == ()


def _chapter(entries: list[Entry]):
    from flats.encode.glossary import Chapter

    return Chapter(layer="zz/test", doc="zz/test/defs.txt", entries=tuple(entries), disorder=())


# --- over the corpus ---------------------------------------------------


def test_encoded_values_are_written_in_their_cities_own_words() -> None:
    rows = tagged()
    assert rows, "no encoded value's evidence used a word its city defined"
    assert len({r.layer for r in rows}) >= 5
    for row in rows:
        assert row.marks
        for mark in row.marks:
            assert mark.defined_at.startswith(row.layer)


def test_gresham_setbacks_carry_greshams_meaning_of_setback() -> None:
    """The one that shows the point. Gresham's setback numbers are marked with
    Gresham's definition of setback, not a general one, and the mark carries
    the line a reviewer opens."""
    rows = [r for r in tagged("or/multnomah/gresham") if r.field.startswith("setback_")]
    assert rows
    marked = {m.term.lower() for row in rows for m in row.marks}
    assert "setback" in marked


# --- and the gate, which is narrow on purpose --------------------------


def test_the_gate_is_quiet_where_the_work_was_done() -> None:
    """Thirteen of these jurisdictions have their corner lot captured with a
    quote, and one is silent about it in a chapter the glossary read whole.
    Neither is a gap, and a gate that flagged them would be noise."""
    assert gaps() == []


def test_a_term_the_city_defines_and_we_skipped_is_a_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure it exists for: geometry still has to decide whether a
    parcel is a corner lot, so with no captured definition it decides by
    somebody else's code and nothing in the file records the substitution."""
    layer = load_rules()["or/multnomah/gresham"]
    stripped = layer.model_copy(update={"definitions": {}})
    monkeypatch.setattr(
        "flats.encode.tagging.load_rules", lambda: {"or/multnomah/gresham": stripped}
    )
    rows = gaps()
    assert [g.term for g in rows] == ["corner_lot"]
    assert rows[0].kind == "uncaptured"
    assert rows[0].detail.startswith("or/multnomah/gresham/")
    assert rows[0].affected, "the gap names no values, so it blocks nothing"


def test_silence_is_only_evidence_if_the_chapter_was_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same gap wearing its other face. Their code saying nothing and our
    matcher finding nothing produce the same empty result and license opposite
    conclusions; only one of them is a finding about the code.

    Both halves are held false here on purpose: the layer captures no
    definition, and the chapter it would have been read from is thin. Every
    chapter in the corpus reads whole today, so this rung has no live example
    -- which is the point of pinning it, since the day one stops is the day it
    has to fire without anyone having remembered it exists."""
    layer = load_rules()[GRESHAM]
    stripped = layer.model_copy(update={"definitions": {}})
    unread = Chapter(
        layer=GRESHAM,
        doc=f"{GRESHAM}/3.definitions.txt",
        entries=(entry("Abut"), entry("Building", line=9)),
        disorder=(),
        lines=1300,
    )
    assert not unread.read_whole, "the chapter this test rests on reads whole"

    monkeypatch.setattr("flats.encode.tagging.load_rules", lambda: {GRESHAM: stripped})
    monkeypatch.setattr("flats.encode.tagging.index", lambda _layer: Index(unread))

    rows = gaps()
    assert [(g.term, g.kind) for g in rows] == [("corner_lot", "unread")]
    assert "/100 lines" in rows[0].detail
    assert rows[0].affected, "the gap names no values, so it blocks nothing"


def test_the_gate_reports_which_values_it_blocks() -> None:
    rows = [
        Gap(
            layer="or/x",
            term="corner_lot",
            kind="uncaptured",
            detail="or/x/defs.txt#L10",
            affected=(("R5", "setback_front_ft"), ("R5", "setback_front_ft")),
        )
    ]
    assert blocked(rows) == {"or/x": (("R5", "setback_front_ft"),)}
    text = render_gaps(rows)
    assert "uncaptured=1" in text


# --- and its rung ------------------------------------------------------


def test_the_rung_sits_between_a_bad_quote_and_an_unread_footnote() -> None:
    """Ordering is by what blocks what. A quote that does not resolve outranks
    it -- there is no text to read the word in yet -- and it outranks the
    footnote rung, because the footnote is written in the same vocabulary."""
    assert STAGES.index("misquoted") < STAGES.index("undefined") < STAGES.index("footnoted")


def test_the_action_names_the_command_and_the_place_to_write_the_answer() -> None:
    action = ACTION["undefined"].format(layer="or/multnomah/gresham", doc="x")
    assert "--gaps" in action
    assert "definitions:" in action


def test_a_jurisdiction_missing_a_meaning_is_not_waiting_on_a_reviewer(tmp_path) -> None:
    layer = next(iter(load_rules().values()))
    store = ProvenanceStore(tmp_path)
    report = readiness_for(layer, store=store, undefined=[("R5", "setback_front_ft")])
    assert report.undefined == (("R5", "setback_front_ft"),)


def test_the_index_is_read_once_per_jurisdiction() -> None:
    assert index("or/multnomah/gresham") is index("or/multnomah/gresham")
