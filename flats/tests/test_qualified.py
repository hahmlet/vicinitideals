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


@pytest.fixture(scope="module")
def rows() -> list[Qualified]:
    return qualified()


# --- the join over the corpus ------------------------------------------


def test_encoded_values_do_sit_under_unruled_footnotes(rows: list[Qualified]) -> None:
    """The finding, stated as a test so it cannot quietly stop being true:
    encoded numbers are read from lines a footnote governs, and until somebody
    rules on the footnote the number is not signable.

    The count is deliberately not pinned. It was, when the finding was new and
    nothing had been ruled on; ruling on a jurisdiction is now the ordinary
    week's work, and a test that fails as the queue drains would be measuring
    progress rather than the mechanism. What is pinned is that the join still
    reaches the corpus and that a blocked value is one whose notes are unread.
    """
    assert rows, "the join found nothing, which would mean the census broke"
    blocked = [r for r in rows if r.blocking]
    assert blocked, "no value is blocked, which would mean the register broke"
    for row in blocked:
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
    blocking every value in its region, without anybody editing those values."""
    blocked = next(r for r in rows if r.blocking)
    root = tmp_path / "footnotes"
    (root / blocked.layer).parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dispositions, "CONFIG_ROOT", root)
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
