"""An unread footnote over a value's lines is a rung, not a footnote in a log.

The join is what makes the census and the disposition register bite. These
tests pin the scope rule it uses -- the block's whole region, deliberately
wider than the cell -- and the ladder position that stops a reviewer signing a
number while the sentence qualifying it is unread.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode import dispositions
from flats.encode.dispositions import digest
from flats.encode.qualified import Qualified, _quoted, qualified, render
from flats.encode.readiness import ACTION, STAGES, Readiness, readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

#: The layer with the most governed values, used where one will do.
GRESHAM = "or/multnomah/gresham"


@pytest.fixture(scope="module")
def rows() -> list[Qualified]:
    return qualified()


# --- the join over the corpus ------------------------------------------


def test_the_join_still_reaches_the_corpus(rows: list[Qualified]) -> None:
    """The census and the register meet over more than one city. If this
    number collapses the join has broken, whatever the blocked count says."""
    assert rows, "the join found nothing, which would mean the census broke"
    assert len({r.layer for r in rows}) >= 8


def test_no_encoded_value_sits_under_a_footnote_nobody_read(
    rows: list[Qualified],
) -> None:
    """A ratchet, and the reason it can be one.

    This began as the opposite assertion: encoded numbers *do* sit under unread
    footnotes, stated as a test so the finding could not quietly stop being
    true. It stopped being true. Every footnote governing a value this corpus
    encodes has now been ruled on -- encoded, dismissed with a reason, or
    parked against a site fact nothing measures yet.

    Turning it around is what keeps it that way. Encoding a value read from a
    region a note qualifies, without ruling on the note, is the exact shape of
    the provenance fault this project exists to avoid: a conditional standard
    written down as an unconditional one. The readiness ladder already refuses
    to sign such a value. This refuses to commit it.

    The remedy when this fails is never to delete the value. It is to rule on
    the note it names, in flats/config/footnotes/<layer>.yaml -- and `dismissed`
    with an honest reason is a ruling.
    """
    blocked = [r for r in rows if r.blocking]
    assert not blocked, chr(10).join(
        f"{r.layer} {r.zone}.{r.field} <- "
        + ", ".join(n.text[:70] for n in r.governing if n.state == "unread")
        for r in blocked[:20]
    )


def test_and_the_gate_would_still_close_if_a_register_went_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ratchet above is only worth having if zero means read rather than
    broken. Point the register at an empty directory and every governed value
    in the largest jurisdiction blocks again, each one naming unread notes."""
    monkeypatch.setattr(dispositions, "CONFIG_ROOT", tmp_path / "footnotes")

    unruled = qualified(GRESHAM)
    assert unruled, "the join found nothing for a layer that has governed values"
    assert all(r.blocking for r in unruled)
    for row in unruled:
        assert any(note.state == "unread" for note in row.governing)


def test_every_governed_value_names_the_notes_over_it(rows: list[Qualified]) -> None:
    for row in rows:
        assert row.governing
        assert all(note.doc == row.quote.split("#", 1)[0] for note in row.governing)
        assert row.clear == (not row.blocking)


def test_a_value_quoted_below_every_block_is_not_governed(rows: list[Qualified]) -> None:
    """Scope is the region above a block, so a value read from lines after the
    last notes block has no footnote over it. If this ever fails, the region
    model has been replaced by "the whole document", which would block
    everything and mean nothing."""
    quoted = [
        (identifier, zone, field)
        for identifier, layer in load_rules().items()
        for zone, field, _ in _quoted(layer)
    ]
    governed = {(r.layer, r.zone, r.field) for r in rows}
    assert governed < set(quoted), "every quoted value is governed, which is the whole document"
    assert len(quoted) > len(rows)


def test_ruling_on_the_note_clears_the_values_under_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[Qualified]
) -> None:
    """The other half of the gate: it opens. A footnote ruled on stops
    blocking every value in its region, without anybody editing those values.

    The blocked row is manufactured rather than borrowed from the backlog,
    because there is no backlog left to borrow from -- see the ratchet above."""
    root = tmp_path / "footnotes"
    monkeypatch.setattr(dispositions, "CONFIG_ROOT", root)
    blocked = next(r for r in qualified(GRESHAM) if r.blocking)
    entries = "".join(
        f"  - digest: {digest(note.text)}\n"
        "    state: dismissed\n"
        "    reason: ruled on for the purpose of this test\n"
        for note in blocked.governing
    )
    path = root / f"{blocked.layer}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("notes:\n" + entries, encoding="utf-8")

    again = next(
        r
        for r in qualified(blocked.layer)
        if (r.zone, r.field, r.quote) == (blocked.zone, blocked.field, blocked.quote)
    )
    assert again.governing
    assert not again.blocking
    assert again.clear


def test_a_citation_that_names_two_lines_still_reaches_the_gate(
    rows: list[Qualified],
) -> None:
    """The join used to read the first number of a citation with a string
    split and give up on anything that did not parse.

    ``doc.txt#L950-L951`` parsed. ``doc.txt#L950,L951`` did not, and returned
    line zero, which the join skipped. That second form is the ordinary shape
    of a citation into an extracted table -- the row label sits on one line and
    the cell under it on another -- so 583 of the corpus's 1,952 quoted values,
    thirty percent, never reached the footnote gate at all, while the report
    read as though they had passed it. Fixing it added 445 governed values and
    57 capped ones: values whose footnotes are read and waiting on data, which
    were resolving as though nothing qualified them.

    Pinned as a shape rather than a count. What matters is that a comma-form
    citation is in the join, not how many of them there are this week.
    """
    commas = [r for r in rows if "," in r.quote.partition("#")[2]]
    assert commas, "no comma-form citation is governed, which is how this broke"
    assert len({r.layer for r in commas}) > 1


def test_a_quote_that_straddles_a_notes_block_takes_both_regions(
    rows: list[Qualified],
) -> None:
    """A value cited to its table cell *and* to the footnote body under it
    names lines on both sides of a notes block. Both regions govern it: a
    footnote over any line a value was read from qualifies that value, and
    taking only the first line's region would drop half the evidence.

    Happy Valley's party-wall zero is the case in hand -- it quotes the row,
    the cell, and note 5 that explains what the zero is for.
    """
    straddling = next(
        r
        for r in rows
        if r.layer == "or/clackamas/happy-valley"
        and r.field.startswith("setback_side_ft [")
        and r.zone == "SFA"
    )
    assert "L1022" in straddling.quote
    assert straddling.governing


# --- the narrowing, where the region was wider than the subject ---------


def test_a_narrowed_note_still_governs_but_stops_capping(
    rows: list[Qualified],
) -> None:
    """Both halves matter, and they say different things.

    It goes on *governing*, because it is still a sentence in the region this
    number was read from and a reviewer working the card should see it. It
    stops *capping*, because somebody read it and wrote down that it speaks
    about another column. Collapsing the two would either hide the note or
    keep the cap, and the point of a recorded narrowing is neither.
    """
    use = next(
        r
        for r in rows
        if (r.layer, r.zone, r.field) == (GRESHAM, "CC", "quadplex_allowed")
    )
    narrowed = [n for n in use.governing if n.zones]
    assert narrowed, "Table 4.0420 note 2 is no longer over the CC use cell"
    assert all(not n.governs("CC") for n in narrowed)
    assert not use.capping, "a note about CMF is capping a CC standard"


def test_and_it_goes_on_capping_the_column_it_was_written_about(
    rows: list[Qualified],
) -> None:
    """The other side of the same edit. Narrowing is not deleting: CMF's own
    use permission still turns on a corridor nothing maps."""
    use = next(
        r
        for r in rows
        if (r.layer, r.zone, r.field) == (GRESHAM, "CMF", "quadplex_allowed")
    )
    assert [n.fact for n in use.capping] == ["civic_corridor"]


def test_a_narrowing_naming_a_zone_the_layer_lacks_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure this guard exists for is silent and points the wrong way.

    A misspelled zone code narrows the note to nothing, and a note that reaches
    no value looks in every report exactly like a note that never qualified
    one -- a cap cancelled by a typo, in the loosening direction.
    """
    root = tmp_path / "footnotes"
    path = root / f"{GRESHAM}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    governed = next(r for r in qualified(GRESHAM) if r.governing)
    path.write_text(
        "notes:" + chr(10)
        + f"  - digest: {digest(governed.governing[0].text)}" + chr(10)
        + "    state: unmeasured" + chr(10)
        + "    fact: civic_corridor" + chr(10)
        + "    reason: written against a zone code that does not exist" + chr(10)
        + "    zones: [CMFF]" + chr(10),
        encoding="utf-8",
    )
    monkeypatch.setattr(dispositions, "CONFIG_ROOT", root)
    with pytest.raises(dispositions.DispositionError, match="CMFF"):
        qualified(GRESHAM)


def test_the_report_counts_what_is_blocked(rows: list[Qualified]) -> None:
    text = render(rows, blocking_only=True)
    assert "qualified_values=" in text
    assert "blocked=" in text


# --- and the rung it produces ------------------------------------------


def test_the_rung_sits_between_a_bad_quote_and_a_signature() -> None:
    """Ordering is the product. A quote that does not resolve outranks a
    footnote nobody read -- there is nothing to read yet -- and both outrank
    waiting for a signature, because signing under an unread qualifier is how
    a conditional standard gets encoded as an unconditional one."""
    assert STAGES.index("misquoted") < STAGES.index("footnoted") < STAGES.index("unsigned")


def test_the_action_names_the_file_to_write_the_ruling_in() -> None:
    action = ACTION["footnoted"].format(layer="or/multnomah/gresham", doc="x")
    assert "flats/config/footnotes/or/multnomah/gresham.yaml" in action
    assert "--blocking" in action


def test_a_jurisdiction_with_unread_footnotes_is_not_waiting_on_a_reviewer(
    tmp_path: Path,
) -> None:
    layer = next(iter(load_rules().values()))
    store = ProvenanceStore(tmp_path)
    report = readiness_for(layer, store=store, footnoted=[("R5", "setback_front_ft")])
    assert isinstance(report, Readiness)
    assert report.footnoted == (("R5", "setback_front_ft"),)


def test_nothing_footnoted_leaves_the_ladder_where_it_was(tmp_path: Path) -> None:
    layer = next(iter(load_rules().values()))
    store = ProvenanceStore(tmp_path)
    assert readiness_for(layer, store=store).footnoted == ()
