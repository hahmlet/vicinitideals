"""A footnote nobody ruled on blocks, and a ruling does not outlive its words.

The default is the load-bearing part. Everything else here exists to keep it
from being quietly weakened: by a dismissal with no reason, by an "encoded"
that names nothing, by a ruling that goes on applying after the codifier
rewrote the sentence it was written against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode import dispositions
from flats.rules.conditions import condition
from flats.encode.dispositions import (
    DispositionError,
    by_state,
    digest,
    notes,
    render,
    rulings,
)

pytestmark = pytest.mark.unit

NOTE = "On a corner lot, one of the required front yard setbacks may be reduced to eight feet."


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "footnotes"
    root.mkdir()
    monkeypatch.setattr(dispositions, "CONFIG_ROOT", root)
    return root


def write(config: Path, layer: str, body: str) -> Path:
    path = config / f"{layer}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# --- the default -------------------------------------------------------


def test_a_footnote_nobody_ruled_on_blocks(config: Path) -> None:
    rows = notes("or/clackamas/happy-valley")
    assert rows, "the census found no footnotes to rule on"
    assert all(row.state == "unread" for row in rows)
    assert all(row.blocking for row in rows)


def test_unread_is_never_written_down(config: Path) -> None:
    write(
        config,
        "or/clackamas/happy-valley",
        "notes:\n  - digest: abc123abc123\n    state: unread\n",
    )
    with pytest.raises(DispositionError, match="never written down"):
        rulings()


def test_only_a_decided_state_is_accepted(config: Path) -> None:
    write(config, "or/x", "notes:\n  - digest: abc123abc123\n    state: maybe\n")
    with pytest.raises(DispositionError, match="state must be one of"):
        rulings()


# --- and what a ruling has to say for itself ---------------------------


def test_a_dismissal_states_a_reason(config: Path) -> None:
    write(config, "or/x", "notes:\n  - digest: abc123abc123\n    state: dismissed\n")
    with pytest.raises(DispositionError, match="omission with extra steps"):
        rulings()


def test_encoded_names_what_it_became(config: Path) -> None:
    write(config, "or/x", "notes:\n  - digest: abc123abc123\n    state: encoded\n")
    with pytest.raises(DispositionError, match="name what it became"):
        rulings()


def test_a_ruling_without_a_digest_cannot_be_matched(config: Path) -> None:
    write(config, "or/x", "notes:\n  - state: dismissed\n    reason: because\n")
    with pytest.raises(DispositionError, match="without a digest"):
        rulings()


# --- rulings bind to words, not to line numbers ------------------------


def test_the_digest_survives_reflowed_whitespace_and_case() -> None:
    assert digest(NOTE) == digest(NOTE.replace(" ", "\n  ").upper())


def test_an_edited_word_is_a_different_footnote() -> None:
    assert digest(NOTE) != digest(NOTE.replace("eight", "ten"))


def test_a_ruling_follows_its_note_when_the_document_moves(config: Path) -> None:
    """Re-fetching a document renumbers every line in it. A disposition keyed
    to a line would silently detach; one keyed to the words does not."""
    layer = "or/clackamas/happy-valley"
    real = next(row for row in notes(layer) if "corner lot" in row.text.lower())
    write(
        config,
        layer,
        "notes:\n"
        f"  - digest: {digest(real.text)}\n"
        "    quote: some/other/document.txt#L1\n"
        "    state: dismissed\n"
        "    reason: a stale quote is allowed to be stale\n",
    )
    again = next(row for row in notes(layer) if row.line == real.line)
    assert again.state == "dismissed"
    assert not again.blocking


def test_an_amended_note_loses_its_ruling_and_says_so(config: Path) -> None:
    """The ruling was about a sentence. The sentence changed, so the ruling is
    void -- and the row is flagged, because someone decided this once and
    deserves to be told their decision no longer applies."""
    layer = "or/clackamas/happy-valley"
    real = next(row for row in notes(layer) if "corner lot" in row.text.lower())
    write(
        config,
        layer,
        "notes:\n"
        f"  - digest: {digest(real.text + ' as amended')}\n"
        f"  - quote: {real.quote}\n"[:0] or "",
    )
    # Written the long way so the quote lines up with the real note exactly.
    write(
        config,
        layer,
        "notes:\n"
        f"  - digest: {digest(real.text + ' as amended')}\n"
        f"    quote: {real.quote}\n"
        "    state: dismissed\n"
        "    reason: written against wording the codifier has since changed\n",
    )
    again = next(row for row in notes(layer) if row.line == real.line)
    assert again.state == "unread"
    assert again.blocking
    assert again.amended


# --- a class of dismissals is a shared reason --------------------------


def test_deleting_one_reason_returns_the_whole_class_to_unread(config: Path) -> None:
    """The reversibility the register exists for: a rejection pass is not a
    one-way door. Rulings that share a reason are a class, and dropping the
    class drops every ruling in it."""
    layer = "or/clackamas/happy-valley"
    rows = notes(layer)[:3]
    entries = "".join(
        f"  - digest: {digest(row.text)}\n"
        "    state: dismissed\n"
        "    reason: governs a use the pod is not\n"
        for row in rows
    )
    write(config, layer, "notes:\n" + entries)
    ruled = {digest(row.text) for row in rows}
    expected = sum(1 for row in notes(layer) if digest(row.text) in ruled)
    assert by_state(notes(layer))["dismissed"] == expected >= 3

    write(config, layer, "notes: []\n")
    after = notes(layer)
    assert "dismissed" not in by_state(after)
    assert all(row.blocking for row in after[:3])


def test_one_ruling_covers_every_printing_of_the_same_sentence(config: Path) -> None:
    """Happy Valley repeats "Interior side yard setbacks for townhomes may be
    reduced to zero..." under several tables. It is one sentence of code, ruled
    on once. Matching by words rather than by line is what makes that true, and
    it cannot leak across jurisdictions because the files are per-layer."""
    layer = "or/clackamas/happy-valley"
    counted: dict[str, int] = {}
    for row in notes(layer):
        counted[digest(row.text)] = counted.get(digest(row.text), 0) + 1
    repeated = [d for d, n in counted.items() if n > 1]
    assert repeated, "no repeated wording in the corpus to test against"

    write(
        config,
        layer,
        "notes:\n"
        f"  - digest: {repeated[0]}\n"
        "    state: dismissed\n"
        "    reason: one sentence of code, printed under more than one table\n",
    )
    ruled_rows = [row for row in notes(layer) if row.state == "dismissed"]
    assert len(ruled_rows) == counted[repeated[0]] > 1


# --- over the corpus ---------------------------------------------------


def test_every_captured_footnote_has_a_state(config: Path) -> None:
    rows = notes()
    assert len(rows) > 300
    assert all(row.state in dispositions.STATES for row in rows)
    assert all(row.blocking == (row.state == "unread") for row in rows)
    assert all(row.quote.startswith(row.doc) for row in rows)


def test_the_report_says_how_many_are_blocking(config: Path) -> None:
    text = render(notes("or/multnomah/troutdale"))
    assert "blocking=" in text
    assert "unread=" in text


# --- read, and waiting on data -----------------------------------------
#
# The fourth state exists because dismissing and blocking are both wrong for
# the same sentence: Oregon City's easement note is plain English nobody has
# to read twice, and nobody can answer it without an easement layer. These
# tests keep it from turning into a polite way of saying "ignore".


def unmeasured(fact: str, reason: str = "no layer held") -> str:
    return (
        "notes:\n"
        "  - digest: abc123abc123\n"
        "    state: unmeasured\n"
        f"    fact: {fact}\n"
        f"    reason: {reason}\n"
    )


def test_unmeasured_states_what_the_note_turns_on(config: Path) -> None:
    write(
        config,
        "or/x",
        "notes:\n"
        "  - digest: abc123abc123\n"
        "    state: unmeasured\n"
        "    fact: utility_easement\n",
    )
    with pytest.raises(DispositionError, match="in words"):
        rulings()


def test_unmeasured_names_a_registered_fact(config: Path) -> None:
    # An unregistered fact is a gap nobody can act on: no screen looks for it
    # and no data gets bought for it.
    write(config, "or/x", unmeasured("easements_probably"))
    with pytest.raises(DispositionError, match="easements_probably"):
        rulings()


def test_unmeasured_names_a_fact_about_the_lot(config: Path) -> None:
    # bonus_program is registered, and it is a choice the developer makes
    # rather than something true of the parcel. A note resting on it is
    # unencoded, not unmeasurable.
    write(config, "or/x", unmeasured("bonus_program"))
    with pytest.raises(DispositionError, match="which is a elective"):
        rulings()


def test_a_fact_with_an_assumption_is_encodable_not_unmeasured(config: Path) -> None:
    # corner_lot is assumed False across a batch, so the screen already
    # answers it. Calling it unmeasured would hide an encodable variant.
    write(config, "or/x", unmeasured("corner_lot"))
    with pytest.raises(DispositionError, match="encodable rather than unmeasured"):
        rulings()


def test_unmeasured_stops_blocking_and_goes_on_capping() -> None:
    # No config fixture: this one is about the rulings actually shipped.
    ruled = [row for row in notes("or/clackamas/oregon-city") if row.state == "unmeasured"]
    assert len(ruled) == 7, "Oregon City's seven unmeasured notes moved"
    assert not any(row.blocking for row in ruled), (
        "an unmeasured note has been read, so it cannot go on blocking the encoding"
    )
    assert all(row.caps_green for row in ruled), (
        "an unmeasured note turns on a fact nobody holds, so nothing under it is GREEN"
    )
    assert all(row.fact for row in ruled), "every one of them names the fact it needs"


def test_every_unmeasured_fact_is_one_nothing_assumes() -> None:
    # The gate that makes caps_green true rather than decorative: a site fact
    # carrying an assumption is answered by default, and the verdict under it
    # would not be capped at all.
    for row in notes():
        if row.state == "unmeasured":
            assert condition(row.fact).assume is None, row.fact


# --- one chapter, stored twice -----------------------------------------


ADOPTED = (
    "notes:\n"
    f"  - digest: {digest(NOTE)}\n"
    "    state: dismissed\n"
    "    reason: a corner lot relaxation, and a relaxation only widens where the pod may go\n"
)


def test_a_layer_may_adopt_another_layer_s_rulings(config: Path) -> None:
    """Multnomah County's R10, R20, RF and R7 are Portland-administered
    pockets, and the layer's 33.110.txt is PCC 33.110 stored a second time.
    Fifteen reasons written out twice would be fifteen chances for the two
    copies to disagree."""
    write(config, "or/multnomah/portland", ADOPTED)
    write(
        config,
        "or/multnomah/_unincorporated",
        "adopts:\n"
        "  - layer: or/multnomah/portland\n"
        "    reason: the same chapter, fetched twice\n"
        "notes: []\n",
    )

    held = rulings()["or/multnomah/_unincorporated"]

    assert [r.digest for r in held] == [digest(NOTE)]
    assert held[0].state == "dismissed"


def test_the_adopting_file_wins_where_both_speak(config: Path) -> None:
    """A pocket that reads a note differently says so, and saying so is not
    an error — it is the whole reason adoption is declared rather than
    inferred from a shared digest."""
    write(config, "or/multnomah/portland", ADOPTED)
    write(
        config,
        "or/multnomah/_unincorporated",
        "adopts:\n"
        "  - layer: or/multnomah/portland\n"
        "    reason: the same chapter, fetched twice\n"
        "notes:\n"
        f"  - digest: {digest(NOTE)}\n"
        "    state: encoded\n"
        "    encoded_as: setback_front_ft variant, when [corner_lot], 8 ft\n",
    )

    held = rulings()["or/multnomah/_unincorporated"]

    assert held[-1].state == "encoded", "own rulings come last, and the last one wins the digest"


def test_adopting_a_layer_that_has_no_rulings_file_is_refused(config: Path) -> None:
    """A typo would adopt nothing and read as a jurisdiction whose notes were
    all ruled on, which is the one failure this register exists to prevent."""
    write(
        config,
        "or/multnomah/_unincorporated",
        "adopts:\n  - layer: or/multnomah/portlandd\n    reason: typo\nnotes: []\n",
    )
    with pytest.raises(DispositionError, match="no rulings file"):
        rulings()


def test_an_adoption_states_why_another_jurisdiction_s_reasons_hold(config: Path) -> None:
    write(config, "or/multnomah/portland", ADOPTED)
    write(
        config,
        "or/multnomah/_unincorporated",
        "adopts:\n  - layer: or/multnomah/portland\nnotes: []\n",
    )
    with pytest.raises(DispositionError, match="why another jurisdiction"):
        rulings()


def test_adoption_does_not_chain(config: Path) -> None:
    """Who ruled on this has to fit in a sentence."""
    write(config, "or/multnomah/portland", ADOPTED)
    write(
        config,
        "or/multnomah/gresham",
        "adopts:\n  - layer: or/multnomah/portland\n    reason: because\nnotes: []\n",
    )
    write(
        config,
        "or/multnomah/_unincorporated",
        "adopts:\n  - layer: or/multnomah/gresham\n    reason: because\nnotes: []\n",
    )
    with pytest.raises(DispositionError, match="itself adopts"):
        rulings()


def test_the_county_pockets_carry_portland_s_rulings() -> None:
    """No config fixture: the adoption actually shipped. All fifteen captured
    notes here are 33.110's, and none of them blocks."""
    rows = notes("or/multnomah/_unincorporated")

    assert len(rows) == 15
    assert all(row.doc.endswith("33.110.txt") for row in rows)
    assert not any(row.blocking for row in rows)
