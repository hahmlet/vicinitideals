"""The document-not-held check, tested on sentences written here.

Same bargain as :mod:`flats.tests.test_stale`, and for the same reason: this
check counts *our own* stale sentences, so its intended end state is zero and
a pinned number would go red on the day the last one is repaired.

It bites harder here than it does there. On 2026-09-09 the four Gresham notes
that motivated the module were corrected, and the corrected sentences no longer
name a chapter next to the marker -- so they left the report entirely rather
than moving to ``settled``. The corpus is now capable of reporting nothing at
all, which means a synthetic fixture is the *only* thing that can prove the
check still fires. :func:`test_the_sentence_this_module_was_built_for_still_fires`
carries the Gresham sentence verbatim for exactly that reason.

So: the mechanism is tested on text in this file, and the corpus tests assert
only that whatever comes back is internally true.
"""

from __future__ import annotations

import pytest

import re

from flats.encode.unheld import (
    MANIFEST,
    Unheld,
    _comment_blocks,
    audit,
    claims,
    render,
)

pytestmark = pytest.mark.unit


def _run(text: str, held: tuple[str, ...] = (), quoted: tuple[str, ...] = ()) -> list[Unheld]:
    return claims(
        text,
        layer="or/x/y",
        kind="notes",
        answers=lambda ref: ref in held,
        quotes=lambda ref: ref in quoted,
    )


# --- what counts as a claim -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "A cross-reference to Chapter 9.0851, which is not in this corpus.",
        "Table 235-2 sends us to ZDO 1005, and that document is not held.",
        "We do not hold Chapter 12.16.",
        "Title 17 has never been fetched.",
        "The screen could not open Section 9.0822.",
    ],
)
def test_a_claim_that_a_document_is_missing_is_picked_up(text) -> None:
    rows = _run(text)
    assert len(rows) == 1
    assert rows[0].missing


@pytest.mark.parametrize(
    "text",
    [
        "Chapter 9.0851 caps parking at two stalls per unit.",
        "The applicant may choose either standard in ZDO 1005.",
        "Section 845 is additive to Section 1005, not an exemption from it.",
    ],
)
def test_prose_that_makes_no_such_claim_is_left_alone(text) -> None:
    assert _run(text) == []


def test_a_number_with_no_book_or_division_word_is_not_a_document() -> None:
    """A bare number in prose is a measurement far more often than a chapter.

    This check may not invent a claim out of one, because the whole value of
    the report is that every row is a sentence somebody actually wrote.
    """
    assert _run("The 1005 standard is not held.") == []
    assert _run("Chapter 1005 is not held.")


def test_a_thing_the_store_could_never_answer_for_is_dropped() -> None:
    """Overlays, maps and inventories decay too, and not against the store."""
    assert _run("The natural resources overlay in ZDO 1002 is not held.") == []
    assert _run("The chapter ZDO 1002 is not held.")


def test_naming_a_document_beats_naming_a_map_in_the_same_breath() -> None:
    text = (
        "The overlay map is beside the point; this is a cross-reference to "
        "Chapter 9.0851, a chapter not in this corpus."
    )
    assert _run(text)[0].missing == ("9.0851",)


# --- where in the sentence it looks -----------------------------------------


def test_only_the_sentence_the_marker_sits_in_is_the_claim() -> None:
    text = (
        "ZDO 999 is held and was read in full. The cell instead cites "
        "ZDO 1005, which is not in this corpus."
    )
    assert _run(text)[0].missing == ("1005",)


def test_what_follows_the_marker_is_not_the_subject_of_the_claim() -> None:
    """The FMD sentence, which is why the window looks backwards only.

    After a not-held marker a note usually lists the documents that DO mention
    the thing. Reading those as the subject inverts the claim: both of these
    are held, and both are named to say the district is real.
    """
    text = (
        "The Floodplain Management District, whose own chapter is not in this "
        "store: the only three documents here that name it are this one, "
        "ZDO 1012 and Gladstone 17.25."
    )
    assert _run(text) == []


def test_a_document_named_straight_after_the_marker_is_still_the_subject() -> None:
    """"We do not hold Chapter 12.16" -- the object position, kept narrow.

    Only as far as the first comma, colon, dash or quotation mark, because
    every one of those is where this corpus stops naming what is missing and
    starts naming what is present.
    """
    assert _run("We do not hold Chapter 12.16.")[0].missing == ("12.16",)
    assert _run("The screen could not open Section 9.0822.")[0].missing == ("9.0822",)


def test_a_quotation_after_the_marker_is_not_the_subject() -> None:
    """The fetch manifest's own shape, and the reason the window stops at a dash.

    A manifest comment argues for fetching a document by quoting the line that
    cites it, so the number after the marker is the one we are being told to
    go and get -- not one being claimed missing on its own account.
    """
    text = (
        "Clear Vision Area, cited eleven times across the district chapters and "
        'never fetched -- "Comply with Section 9.0200 - Clear Vision Area" sits '
        "in the development standards of Downtown."
    )
    assert _run(text) == []


def test_a_folded_scalar_reads_the_same_as_one_line() -> None:
    folded = "A cross-reference to\n      Chapter 9.0851, which is\n      not in this corpus."
    assert _run(folded)[0].missing == ("9.0851",)


# --- the three verdicts -----------------------------------------------------


def test_a_document_the_store_now_answers_for_is_contradicted() -> None:
    row = _run("A cross-reference to Chapter 9.0851, not in this corpus.", held=("9.0851",))[0]
    assert row.verdict == "contradicted"
    assert row.held == ("9.0851",)
    assert row.missing == ()


def test_a_document_the_store_still_cannot_open_is_outstanding() -> None:
    row = _run("Title 17 has never been fetched.")[0]
    assert row.verdict == "outstanding"
    assert row.missing == ("17",)


def test_a_sentence_written_as_history_is_not_asked_again() -> None:
    row = _run("Chapter 12.16 was not in the store when this was written.")[0]
    assert row.verdict == "settled"


def test_settled_language_is_narrow_enough_to_mean_something() -> None:
    row = _run("Chapter 12.16 is not in this corpus and probably never will be.")[0]
    assert row.verdict != "settled"


def test_a_layer_that_quotes_the_chapter_it_calls_missing_is_the_loud_row() -> None:
    row = _run(
        "A cross-reference to Chapter 9.0851, not in this corpus.",
        held=("9.0851",),
        quoted=("9.0851",),
    )[0]
    assert row.verdict == "contradicted"
    assert row.self_contradicted


def test_a_zone_note_carries_the_zone_it_was_written_on() -> None:
    rows = claims(
        "A cross-reference to Chapter 9.0851, not in this corpus.",
        layer="or/multnomah/gresham",
        kind="notes",
        zone="MDR-PV",
        answers=lambda ref: False,
    )
    assert rows[0].label == "or/multnomah/gresham:MDR-PV"


def test_a_ruling_carries_the_key_it_was_decided_against() -> None:
    """A crossref or reading ruling is answerable at a finer address than a note.

    Its whole point is that it closed one specific row, so the report has to
    say which one -- otherwise the reader is told a decision went stale and
    not which decision.
    """
    rows = claims(
        "Section 1002 is not in the store.",
        layer="or/clackamas/_unincorporated",
        kind="crossrefs",
        at="1002.02",
        answers=lambda ref: False,
    )
    assert rows[0].label == "or/clackamas/_unincorporated 1002.02"


# --- the fetch manifest is not a set of live claims -------------------------


def test_comments_inside_the_fetch_manifest_are_skipped_whole(tmp_path) -> None:
    """The argument for fetching a document is not a claim that it is missing.

    Every one of those sentences is true about the past and stands directly
    above the entry that made it false, so reading them live would bury the
    report in its own success stories.
    """
    path = tmp_path / "x.yaml"
    path.write_text(
        "code:\n"
        "  # cited eleven times across the district chapters and never fetched\n"
        '  - id: "9.0800.parking"\n'
        "defaults:\n"
        "  # Chapter 12.16 is not in this corpus\n"
        "  parking_min_per_unit: 0\n",
        encoding="utf-8",
    )
    blocks = list(_comment_blocks(path))
    assert blocks == ["Chapter 12.16 is not in this corpus"]


def test_the_manifest_is_the_block_that_lists_documents() -> None:
    """`ingest:` is the parcel-join config, and excluding it excludes nothing.

    This check was written against the wrong key first, which cost nothing
    only because the marker could not yet see a manifest comment's object.
    Both halves are asserted here so the confusion cannot come back quietly.
    """
    from flats.rules.loader import CONFIG_ROOT

    body = (CONFIG_ROOT / "or/multnomah/gresham.yaml").read_text(encoding="utf-8")
    assert MANIFEST == "code"
    assert re.search(rf"^{MANIFEST}:\n(?:.*\n)*?\s+- id:", body, re.MULTILINE)
    assert re.search(r"^ingest:\n\s+geoid:", body, re.MULTILINE)


def test_a_manifest_comment_would_otherwise_read_as_a_live_claim(tmp_path) -> None:
    """Why the exclusion is a correctness fix and not an optimisation."""
    path = tmp_path / "x.yaml"
    path.write_text(
        "defaults:\n"
        "  # Clear Vision Area. Chapter 9.0200 has never been fetched, and it is\n"
        "  # cited eleven times across the district chapters.\n"
        "  parking_min_per_unit: 0\n",
        encoding="utf-8",
    )
    assert _run(next(iter(_comment_blocks(path))))


# --- the report -------------------------------------------------------------


def test_the_report_leads_with_the_file_arguing_with_itself() -> None:
    text = render(
        [
            Unheld("or/a/b", "notes", None, "claim one", ("9.0851",), (), False),
            Unheld("or/a/c", "notes", None, "claim two", ("1005",), (), True),
            Unheld("or/a/d", "comments", None, "claim three", (), ("17",)),
        ]
    )
    assert "the store answers for it today:        2" in text
    assert "of those, the layer QUOTES it:       1" in text
    assert "still true, and able to go stale:      1" in text
    assert text.index("or/a/c") < text.index("or/a/b")
    assert "<- and quotes it" in text


# --- against the real corpus, without pinning a number ----------------------


def test_the_sentence_this_module_was_built_for_still_fires() -> None:
    """Gresham's four notes, as they read before 2026-09-09, re-asked today.

    The corpus no longer contains this sentence, which is the point: the check
    can now report nothing forever and still be working. This is the fixture
    that says so, and it is also the regression that Section 9.0851 resolves
    inside ``9.0800.parking.txt`` -- a filename match would never find it.
    """
    from flats.encode.crossrefs import opens
    from flats.provenance.store import ProvenanceStore
    from flats.rules.loader import load_rules

    layer = load_rules(strict=False)["or/multnomah/gresham"]
    answers = opens(layer, ProvenanceStore())

    rows = claims(
        'Row J reads "As provided in Section 9.0851" -- a cross-reference to a '
        "chapter not in this corpus, so the state minimum stands rather than a "
        "number read out of this table.",
        layer="or/multnomah/gresham",
        kind="notes",
        zone="MDR-PV",
        answers=answers,
    )
    assert [r.verdict for r in rows] == ["contradicted"]
    assert rows[0].held == ("9.0851",)


def test_a_reference_the_store_really_cannot_open_stays_outstanding() -> None:
    """The other half of the same predicate, so the fixture above proves work."""
    from flats.encode.crossrefs import opens
    from flats.provenance.store import ProvenanceStore
    from flats.rules.loader import load_rules

    layer = load_rules(strict=False)["or/multnomah/gresham"]
    answers = opens(layer, ProvenanceStore())
    rows = claims(
        "Chapter 99.9999 is not in this corpus.",
        layer="or/multnomah/gresham",
        kind="notes",
        answers=answers,
    )
    assert [r.verdict for r in rows] == ["outstanding"]


def test_the_walk_reaches_the_rulings_and_not_only_the_prose() -> None:
    """The block a prose harvest structurally cannot see.

    A ruling is a structured field, not a note, so :mod:`flats.encode.refusals`
    never looks at one -- and a cross-reference closed *because* we do not hold
    the chapter is the sharpest form this claim takes. Asserted as a property
    of the walk, not as a count: which rulings say it is Oregon's business and
    ours to fix, and either number may go to zero.
    """
    from flats.rules.loader import load_rules

    layers = load_rules(strict=False)
    written = {
        (name, "crossrefs", ref)
        for name, layer in layers.items()
        for ref, ruling in layer.crossrefs.items()
        if claims(str(ruling), layer=name, kind="crossrefs", answers=lambda r: False)
    } | {
        (name, "readings", key)
        for name, layer in layers.items()
        for key, reading in layer.readings.items()
        if claims(reading.note, layer=name, kind="readings", answers=lambda r: False)
    }
    found = {(r.layer, r.kind, r.at) for r in audit() if r.kind in {"crossrefs", "readings"}}
    assert found == written


def test_no_sentence_in_the_corpus_disagrees_with_the_store() -> None:
    """The one number this file does assert, and it is asserted at zero.

    Pinning a count is the trap :mod:`flats.tests.test_stale` names: a ledger
    of our own mistakes goes red the day the last one is fixed. Asserting
    *zero* is the opposite. It cannot fail on success, and it fails on exactly
    one event -- a document arriving in the store that a sentence somewhere
    still says is missing, which is the day the sentence needs rewriting and
    the day nobody is looking. Four such sentences sat in Gresham for thirteen
    days and were found by accident.
    """
    bad = [r for r in audit() if r.verdict == "contradicted"]
    assert not bad, "\n".join(f"{r.label}: holds {r.held} -- {r.claim[:160]}" for r in bad)


def test_every_row_the_corpus_run_returns_is_internally_true() -> None:
    """No count is asserted. Only that each row says one coherent thing."""
    from flats.rules.loader import load_rules

    layers = load_rules(strict=False)
    for row in audit():
        assert row.layer in layers, row.layer
        assert row.kind in {"notes", "comments", "crossrefs", "readings"}
        if row.kind == "crossrefs":
            assert row.at in layers[row.layer].crossrefs, row.label
        if row.kind == "readings":
            assert row.at in layers[row.layer].readings, row.label
        if row.zone is not None:
            assert row.zone in layers[row.layer].zones, f"{row.label}: {row.claim[:80]}"
        assert row.held or row.missing, row.claim[:80]
        assert not (set(row.held) & set(row.missing))
        assert row.verdict in {"contradicted", "outstanding", "settled"}
        if row.verdict == "outstanding":
            assert not row.held
        if row.self_contradicted:
            assert row.held
