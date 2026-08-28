"""A citation following its own words when the document is renumbered.

The failure this guards against is silent and it has already happened. Gresham
republished its Pleasant Valley chapter with one sentence inserted at line 612.
Every quote below that line still resolved, still looked like evidence, and
pointed one line high. Nothing crashed, nothing went red, and 61 encoded values
quietly cited the wrong sentence.

Three properties carry the weight here.

*The words decide, not the arithmetic.* A citation moves only when the text it
names survives byte for byte somewhere in the new document. Where the words
themselves changed, the tool strands the quote and says so — because a human has
to read that one, and a guess dressed as a migration is the worst of both.

*A partial migration is never written.* If one line of a five-line span is lost,
the whole quote is left alone. A half-moved citation looks moved.

*A signature follows its evidence, not its address.* The fingerprint hashes the
quote string, so re-pointing would orphan every review on the document — which
would make a renumbering indistinguishable from an amendment and put the corpus
back where it started.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from flats.encode.verify import (
    Verification,
    VerificationLog,
    apply_verifications,
    fingerprint,
    sign,
)
from flats.provenance.repoint import (
    config_files,
    line_map,
    mentions,
    move_quote,
    readdress,
    repoint_files,
    survivors,
)
from flats.provenance.store import ProvenanceStore, parse_quote
from flats.rules.loader import CONFIG_ROOT
from flats.rules.model import Layer, Provenance, Status, Value, Zone

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland/33.110.txt"
GRESHAM_PV = "or/multnomah/gresham/4.1400.pleasant-valley.txt"
RETRIEVED = date(2026, 8, 27)
OLD = [f"line {n}" for n in range(1, 21)]


def shifted(at: int, *, text: str = "an inserted sentence") -> list[str]:
    """The same document with one line inserted before ``at`` (1-based)."""
    return OLD[: at - 1] + [text] + OLD[at - 1 :]


# --- the line map -----------------------------------------------------


def test_a_document_that_did_not_move_maps_to_itself() -> None:
    assert line_map(OLD, OLD) == {n: n for n in range(1, 21)}


def test_an_inserted_line_shifts_everything_below_it() -> None:
    mapping = line_map(OLD, shifted(11))
    assert mapping[10] == 10
    assert mapping[11] == 12
    assert mapping[20] == 21


def test_a_line_whose_words_changed_has_no_counterpart() -> None:
    new = list(OLD)
    new[6] = "line 7, as amended"
    mapping = line_map(OLD, new)
    assert 7 not in mapping
    assert mapping[6] == 6 and mapping[8] == 8


# --- moving one quote -------------------------------------------------


def test_a_quote_follows_its_words() -> None:
    after, lost = move_quote(f"{PORTLAND}#L15", line_map(OLD, shifted(11)))
    assert (after, lost) == (f"{PORTLAND}#L16", ())


def test_a_span_widens_over_a_line_inserted_inside_it() -> None:
    """Five cited lines become six. The reviewer now sees the new sentence,
    which is the conservative direction — a citation may show more than it did
    and must never show less."""
    after, lost = move_quote(f"{PORTLAND}#L10-L14", line_map(OLD, shifted(12)))
    assert (after, lost) == (f"{PORTLAND}#L10-L15", ())


def test_a_multi_span_quote_keeps_its_shape() -> None:
    """Three spans, and only the ones below the insertion move. A citation that
    names a table row and a footnote four lines down is the common shape here,
    and the two halves have to stay two halves."""
    after, _ = move_quote(f"{PORTLAND}#L3,L10,L12-L14", line_map(OLD, shifted(11)))
    assert after == f"{PORTLAND}#L3,L10,L13-L15"


def test_a_line_inserted_between_two_spans_joins_neither() -> None:
    """The citation named a row and a footnote, not the gap between them. A
    sentence dropped into that gap is not evidence anybody cited, and widening
    across it would quietly enlarge every multi-span quote in the corpus."""
    after, _ = move_quote(f"{PORTLAND}#L10-L11,L12-L13", line_map(OLD, shifted(12)))
    assert after == f"{PORTLAND}#L10-L11,L13-L14"


def test_moved_spans_still_parse() -> None:
    """Spans must ascend and not overlap or `parse_quote` refuses them. They
    cannot collide — the map comes from difflib's equal blocks and is strictly
    increasing — and this is the test that says so out loud."""
    after, _ = move_quote(f"{PORTLAND}#L3,L10-L11,L12,L14", line_map(OLD, shifted(11)))
    # L10-L11 widens over the insertion to L10-L12; the single L12 lands on 13
    # right behind it. Adjacent, ascending, and readable back.
    assert parse_quote(after).spans == ((3, 3), (10, 12), (13, 13), (15, 15))


def test_a_quote_whose_words_changed_is_stranded_whole() -> None:
    new = list(OLD)
    new[11] = "line 12, as amended"
    after, lost = move_quote(f"{PORTLAND}#L10-L14", line_map(OLD, new))
    assert after == ""
    assert lost == (12,)


def test_a_whole_document_quote_needs_no_repoint() -> None:
    after, lost = move_quote(PORTLAND, line_map(OLD, shifted(1)))
    assert (after, lost) == (PORTLAND, ())


# --- rewriting the corpus files ---------------------------------------


YAML = """\
# A comment that must survive, because these files are read by people.
defaults:
  setback_front_ft:
    value: 10
    quote: "or/multnomah/portland/33.110.txt#L15"   # trailing comment
  height_max_ft:
    value: 35
    quote: "or/multnomah/portland/33.110.txt#L3,L12-L14"
  parking_min_per_unit:
    value: 1
    quote: "or/multnomah/gresham/9.0800.parking.txt#L15"
"""


def test_the_rewrite_is_surgical(tmp_path: Path) -> None:
    """A substring swap, not a YAML round-trip. Comments, quoting style and
    line order all survive, because these files are argued over in prose and a
    serialiser would flatten the argument."""
    path = tmp_path / "portland.yaml"
    path.write_text(YAML, encoding="utf-8")
    moves, stranded = repoint_files(PORTLAND, line_map(OLD, shifted(11)), [path], write=True)

    out = path.read_text(encoding="utf-8")
    assert not stranded
    assert len(moves) == 2
    assert "# A comment that must survive" in out
    assert "# trailing comment" in out
    assert f'"{PORTLAND}#L16"' in out
    assert f'"{PORTLAND}#L3,L13-L15"' in out


def test_another_documents_quotes_are_left_alone(tmp_path: Path) -> None:
    path = tmp_path / "portland.yaml"
    path.write_text(YAML, encoding="utf-8")
    repoint_files(PORTLAND, line_map(OLD, shifted(11)), [path], write=True)
    assert "or/multnomah/gresham/9.0800.parking.txt#L15" in path.read_text(encoding="utf-8")


def test_a_file_with_nothing_to_move_is_not_written(tmp_path: Path) -> None:
    """A no-op run must not show up in a diff, or the next real one is buried."""
    path = tmp_path / "portland.yaml"
    path.write_text(YAML, encoding="utf-8")
    before = path.stat().st_mtime_ns
    moves, _ = repoint_files(PORTLAND, line_map(OLD, OLD), [path], write=True)
    assert not moves
    assert path.stat().st_mtime_ns == before


def test_write_false_reports_without_touching_anything(tmp_path: Path) -> None:
    path = tmp_path / "portland.yaml"
    path.write_text(YAML, encoding="utf-8")
    moves, _ = repoint_files(PORTLAND, line_map(OLD, shifted(11)), [path], write=False)
    assert len(moves) == 2
    assert path.read_text(encoding="utf-8") == YAML


def test_a_stranded_quote_is_reported_and_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "portland.yaml"
    path.write_text(YAML, encoding="utf-8")
    new = list(OLD)
    new[14] = "line 15, as amended"
    moves, stranded = repoint_files(PORTLAND, line_map(OLD, new), [path], write=True)

    assert [s.quote for s in stranded] == [f"{PORTLAND}#L15"]
    assert stranded[0].lines == (15,)
    assert not moves
    assert path.read_text(encoding="utf-8") == YAML


# --- signatures -------------------------------------------------------


def _layers(quote: str, *, field: str = "setback_front_ft") -> dict[str, Layer]:
    return {
        "or/multnomah/portland": Layer(
            layer="or/multnomah/portland",
            kind="city",
            label="Portland",
            zones={
                "R5": Zone(
                    zone="R5",
                    values={
                        field: Value(
                            name=field,
                            value=10,
                            status=Status.encoded,
                            prov=Provenance(
                                cite="PCC 33.110.220",
                                url="https://example.gov/33/110",
                                retrieved=RETRIEVED,
                                quote=quote,
                            ),
                        )
                    },
                )
            },
        )
    }


def test_a_signature_over_unchanged_words_follows_its_citation(tmp_path: Path) -> None:
    """The point of the whole module. A reviewer read line 15; the city inserted
    a sentence at line 11; line 15 is now line 16 and reads identically. Nothing
    they signed has changed, so nothing is withdrawn — but the fingerprint hashes
    the address, so the entry has to be re-issued or it orphans itself."""
    layers = _layers(f"{PORTLAND}#L15")
    log_path = tmp_path / "verifications.jsonl"
    value = layers["or/multnomah/portland"].zones["R5"].values["setback_front_ft"]
    VerificationLog().append(
        sign(
            "or/multnomah/portland",
            "R5",
            "setback_front_ft",
            value,
            reviewer="sjk",
            reviewed=RETRIEVED,
        ),
        log_path,
    )

    mapping = line_map(OLD, shifted(11))
    assert survivors(layers, PORTLAND, mapping) == {
        ("or/multnomah/portland", "R5", "setback_front_ft", ())
    }

    issued = readdress(layers, PORTLAND, mapping, log_path=log_path)
    assert len(issued) == 1
    assert issued[0].reviewer == "sjk"
    assert issued[0].reviewed == RETRIEVED
    assert "repointed" in issued[0].note

    # And the re-issued signature matches the value once its quote has moved.
    moved = _layers(f"{PORTLAND}#L16")
    promoted, orphans = apply_verifications(moved, VerificationLog.load(log_path))
    assert not orphans
    assert (
        promoted["or/multnomah/portland"].zones["R5"].values["setback_front_ft"].status
        is Status.verified
    )


def test_the_original_signature_stays_on_disk(tmp_path: Path) -> None:
    """Append-only. The migration is a new line, not an edit, so the history
    still shows what was signed and against which line numbers."""
    layers = _layers(f"{PORTLAND}#L15")
    log_path = tmp_path / "verifications.jsonl"
    value = layers["or/multnomah/portland"].zones["R5"].values["setback_front_ft"]
    VerificationLog().append(
        sign(
            "or/multnomah/portland",
            "R5",
            "setback_front_ft",
            value,
            reviewer="sjk",
            reviewed=RETRIEVED,
        ),
        log_path,
    )
    readdress(layers, PORTLAND, line_map(OLD, shifted(11)), log_path=log_path)

    assert len(log_path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_an_already_broken_signature_is_not_repaired(tmp_path: Path) -> None:
    """A review orphaned for some other reason — the number was edited, the cite
    retyped — must stay orphaned. Silently mending it as a side effect of an
    unrelated refresh is the one thing this apparatus exists to prevent."""
    layers = _layers(f"{PORTLAND}#L15")
    log_path = tmp_path / "verifications.jsonl"
    VerificationLog().append(
        Verification(
            layer="or/multnomah/portland",
            zone="R5",
            field="setback_front_ft",
            fingerprint=fingerprint(
                "or/multnomah/portland",
                "R5",
                "setback_front_ft",
                25,  # somebody signed 25 ft; the file now says 10
                cite="PCC 33.110.220",
                quote=f"{PORTLAND}#L15",
            ),
            reviewer="sjk",
            reviewed=RETRIEVED,
        ),
        log_path,
    )

    assert readdress(layers, PORTLAND, line_map(OLD, shifted(11)), log_path=log_path) == []


def test_a_stranded_value_is_not_spared(tmp_path: Path) -> None:
    """Words changed, so the signature must fall. `survivors` is what decides
    which reviews a refresh keeps, and it has to say no here."""
    layers = _layers(f"{PORTLAND}#L15")
    new = list(OLD)
    new[14] = "line 15, as amended"
    assert survivors(layers, PORTLAND, line_map(OLD, new)) == frozenset()


# --- against the real corpus ------------------------------------------


def _cited_lines(doc_path: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(doc_path)}#L[\d,\-L\s]*\d")
    return [
        m.group(0)
        for path in config_files(CONFIG_ROOT)
        for m in pattern.finditer(path.read_text(encoding="utf-8"))
    ]


def test_the_gresham_chapter_that_started_this_survives_its_own_drift() -> None:
    """Gresham 4.1400 gained a line at 612 and lost none. Nothing is stranded,
    so accepting that refresh is a re-point rather than a re-read of every value
    in the chapter — which is the whole reason this module exists."""
    stored = ProvenanceStore().load(GRESHAM_PV).text.splitlines()
    mapping = line_map(stored, stored[:611] + ["an inserted sentence"] + stored[611:])

    moves, stranded = repoint_files(GRESHAM_PV, mapping, config_files(CONFIG_ROOT), write=False)
    assert not stranded

    # Derived, not pinned: exactly the citations reaching past the insertion.
    # Most of this chapter's quotes are in the tables above it and must not move.
    below = [q for q in _cited_lines(GRESHAM_PV) if (parse_quote(q).end or 0) >= 612]
    assert moves and len(moves) == len(below)
    assert len(below) < len(_cited_lines(GRESHAM_PV))


def test_a_line_inserted_at_the_top_moves_every_citation() -> None:
    """The other end of the same property. Whatever the corpus cites in this
    chapter, all of it follows — no quote is left behind because its shape was
    unusual."""
    stored = ProvenanceStore().load(GRESHAM_PV).text.splitlines()
    mapping = line_map(stored, ["an inserted sentence", *stored])

    moves, stranded = repoint_files(GRESHAM_PV, mapping, config_files(CONFIG_ROOT), write=False)
    assert not stranded
    assert len(moves) == len(_cited_lines(GRESHAM_PV))


def test_a_citation_above_the_insertion_does_not_move() -> None:
    """The other half of the same property: a re-point must not churn quotes
    that did not move, or every refresh rewrites the whole corpus."""
    stored = ProvenanceStore().load(GRESHAM_PV).text.splitlines()
    mapping = line_map(stored, stored + ["appended at the end"])

    moves, stranded = repoint_files(GRESHAM_PV, mapping, config_files(CONFIG_ROOT), write=False)
    assert not moves and not stranded


def test_test_pins_are_reported_and_never_rewritten() -> None:
    """43 test files quote stored documents by line. They are assertions, and a
    tool that edits an assertion so it passes has deleted the assertion."""
    root = Path(__file__).resolve().parent
    pinned = mentions("or/multnomah/portland/33.110.txt", root)
    assert pinned
    assert all(p.suffix == ".py" for p, _ in pinned)
    assert config_files(CONFIG_ROOT)
    assert not any(p.suffix == ".py" for p in config_files(CONFIG_ROOT))
