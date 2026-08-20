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
from flats.encode.qualified import Qualified, qualified, render
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
    ungoverned = [
        (zone, field)
        for layer in load_rules().values()
        for zone, field in _quoted_fields(layer)
    ]
    assert len(ungoverned) > len(rows)


def _quoted_fields(layer) -> list[tuple[str, str]]:
    out = []
    for code, zone in layer.zones.items():
        out.extend((code, name) for name, v in zone.values.items() if v.prov.quote)
    return out


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
