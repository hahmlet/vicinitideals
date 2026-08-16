"""Reading the code for standards the field registry has no name for.

The sweep is the one check in FLATS that does not start from the registry, so
the things worth holding to are the ones that make its output checkable rather
than merely plausible. A finding must carry a line inside the passage it was
read from; a reply that cannot be parsed must produce nothing rather than
something; and the sweep must be scored against standards we already hold,
because a hole list from a reader that missed half of what it was shown reads
exactly like a hole list from one that missed nothing.
"""

from __future__ import annotations

import json

import pytest

from flats.encode.sweep.ask import Finding, merge, parse, prompt_for, scripted, sweep
from flats.encode.sweep.audit import Report, field_for, judge
from flats.encode.sweep.audit import run as sweep_run
from flats.encode.sweep.chunk import Chunk, chunks
from flats.encode.sweep.journal import Journal, Mismatch, Setup
from flats.rules.model import Layer, Provenance, Value, Zone

pytestmark = pytest.mark.unit

DOC = "or/clackamas/somewhere/16.22.txt"

TEXT = """16.22.010 Purpose.
This chapter states the standards for residential districts.
16.22.020 Development standards.
A. The minimum interior side yard is 10 feet.
B. The minimum lot area for a fourplex is 7,000 square feet.
C. Fences in a required front yard may not exceed 3 feet in height.
16.22.030 Parking.
Two off-street spaces are required per dwelling unit.
"""


def reply(*items: dict) -> str:
    return json.dumps({"found": list(items)})


def piece(first: int = 1, last: int = 8) -> Chunk:
    lines = TEXT.splitlines()[first - 1 : last]
    return Chunk(document=DOC, first=first, last=last, text="\n".join(lines))


# --- chunking -------------------------------------------------------------


def test_a_chunk_knows_the_lines_it_came_from():
    """Line numbers are what a citation is made of.

    A chunker that renumbered from one per passage would produce findings that
    all point at the top of the document, and every one of them would look
    exactly as citable as a right one.
    """
    got = chunks(TEXT, document=DOC, size=4, overlap=2)

    assert got[0].first == 1
    assert got[0].ref == f"{DOC}#L{got[0].first}-L{got[0].last}"
    # The document's own numbering, not the chunk's. Chunk two starts partway
    # down the file and its first line has to say so.
    assert got[1].numbered().lstrip().startswith(str(got[1].first))


def test_chunks_overlap_so_no_line_is_seen_only_once():
    """A standard severed by a boundary is the one miss nothing reports."""
    got = chunks(TEXT, document=DOC, size=4, overlap=2)

    covered = [n for c in got for n in range(c.first, c.last + 1)]
    assert set(covered) == set(range(1, len(TEXT.splitlines()) + 1))
    # Seen twice somewhere, which is the point of the overlap.
    assert len(covered) > len(set(covered))


def test_a_break_lands_before_a_heading_not_through_a_standard():
    """A section opening is the one place a cut costs nothing.

    Everywhere else a cut severs a standard from the sentence that scopes it,
    and the halves are individually unreadable rather than visibly broken.
    """
    got = chunks(TEXT, document=DOC, size=4, overlap=2)

    # "16.22.020 Development standards." opens on line 3, so the first chunk
    # ends above it rather than swallowing its first two rules.
    assert got[0].last == 2


def test_a_document_shorter_than_one_chunk_is_one_chunk():
    got = chunks("one line only", document=DOC, size=120, overlap=60)

    assert len(got) == 1
    assert (got[0].first, got[0].last) == (1, 1)


def test_overlap_at_or_above_the_chunk_size_still_advances():
    """A caller asking for total coverage gets a slow sweep, not a hang."""
    got = chunks(TEXT, document=DOC, size=3, overlap=99)

    assert got[-1].last == len(TEXT.splitlines())


# --- parsing --------------------------------------------------------------


def test_a_finding_outside_the_passage_is_dropped():
    """Either a hallucinated citation or a model numbering from one.

    Both make the line meaningless, and a meaningless line in a review queue
    costs a reviewer the same minute as a real one and returns nothing.
    """
    got = parse(reply({"standard": "side setback", "line": 400}), piece(1, 8), _LENS)

    assert got == []


def test_a_reply_that_is_prose_yields_nothing():
    assert parse("I could not find any standards in this passage.", piece(), _LENS) == []


def test_a_finding_without_a_line_is_dropped():
    got = parse(reply({"standard": "side setback"}), piece(), _LENS)

    assert got == []


def test_the_prompt_shows_the_real_line_numbers():
    """The model can only cite the numbering it is shown."""
    text = prompt_for(piece(4, 6), _LENS)

    assert "     4  A. The minimum interior side yard is 10 feet." in text
    # And it is never shown the encoding, which is what keeps it from agreeing.
    assert "setback_side_ft" not in text


# --- merging --------------------------------------------------------------


def test_the_same_standard_from_two_lenses_is_one_finding_with_both():
    got = merge(
        [
            Finding(DOC, 4, "side setback", "", "10 feet", ("dimension",)),
            Finding(DOC, 4, "Side Setback", "", "", ("relief",)),
        ]
    )

    assert len(got) == 1
    assert got[0].lenses == ("dimension", "relief")


def test_a_lens_that_found_something_alone_still_keeps_it():
    """Union, not vote. Agreement ranks the queue; it does not filter it."""
    got = merge([Finding(DOC, 8, "parking", "", "2 per unit", ("access",))])

    assert len(got) == 1


# --- mapping to the registry ---------------------------------------------


def test_a_standard_we_name_maps_to_its_field():
    assert field_for("minimum interior side yard") == "setback_side_ft"
    assert field_for("minimum lot area for a fourplex") == "min_lot_sqft"
    assert field_for("off-street parking spaces per dwelling unit") == "parking_min_per_unit"


def test_a_standard_we_have_no_field_for_maps_to_nothing():
    """The whole question, in one assertion.

    A fence height is a real requirement, it constrains nothing about this
    building, and the registry has no name for it. What matters is that it comes
    back as unmapped rather than being silently attached to a height field.
    """
    assert field_for("maximum fence height in a required front yard") == ""


# --- scoring --------------------------------------------------------------


def _layer() -> Layer:
    cite = Provenance(
        cite="Ch. 16.22", url="https://example.invalid/16.22", retrieved="2026-08-15"
    )
    return Layer(
        layer="or/clackamas/somewhere",
        label="Somewhere",
        kind="city",
        zones={
            "R10": Zone(
                zone="R10",
                values={
                    "setback_side_ft": Value(
                        name="setback_side_ft",
                        value=10,
                        prov=cite.model_copy(update={"quote": f"{DOC}#L4"}),
                    ),
                    "min_lot_sqft": Value(
                        name="min_lot_sqft",
                        value=7000,
                        prov=cite.model_copy(update={"quote": f"{DOC}#L5"}),
                    ),
                },
            )
        },
    )


def test_a_standard_we_hold_and_the_sweep_refound_is_covered():
    covered, missed, holes = judge(
        _layer(),
        DOC,
        [Finding(DOC, 4, "minimum interior side yard", "", "10 feet", ("dimension",))],
    )

    assert covered == [f"{DOC}#L4 setback_side_ft"]
    assert missed == [f"{DOC}#L5 min_lot_sqft"]
    assert holes == []


def test_a_standard_no_lens_found_is_the_recall_score():
    """The reason to sweep ground we are confident about.

    A sweep that cannot refind what we already hold has no authority to say the
    rest is complete, and an empty hole list from such a sweep reads exactly
    like an empty one from a good sweep.
    """
    report = Report(
        layer="or/clackamas/somewhere",
        documents=(DOC,),
        covered=("a", "b"),
        missed=("c", "d"),
        holes=(),
        found=2,
    )

    assert report.recall == 0.5
    assert "recall 50%" in report.summary()


def test_a_standard_on_a_line_nobody_read_is_not_a_miss():
    """A partial run must not report the recall of a failed one.

    Reading two chunks of a forty-chunk document and scoring against every
    standard in the file returns zero, which reads as "this model finds
    nothing" when what happened is "this model was shown nothing".
    """
    covered, missed, _holes = judge(
        _layer(),
        DOC,
        [Finding(DOC, 4, "minimum interior side yard", "", "10 feet", ("dimension",))],
        swept=[(1, 4)],
    )

    assert covered == [f"{DOC}#L4 setback_side_ft"]
    # Line 5 was never read, so it is not evidence about the reader.
    assert missed == []


def test_a_standard_with_no_field_becomes_a_hole():
    _covered, _missed, holes = judge(
        _layer(),
        DOC,
        [Finding(DOC, 6, "maximum fence height", "fences in a front yard", "3 feet", ("relief",))],
    )

    assert len(holes) == 1
    assert holes[0].quote == f"{DOC}#L6"


def test_a_finding_a_line_or_two_off_still_counts_as_the_same_standard():
    """Extraction is accurate to a row, not to a character.

    A table row and the heading above it are one fact two lines apart, and an
    exact-line test would score a sweep that read the table perfectly as having
    missed all of it.
    """
    covered, _missed, _holes = judge(
        _layer(),
        DOC,
        [Finding(DOC, 6, "minimum interior side yard", "", "10 feet", ("dimension",))],
    )

    assert covered == [f"{DOC}#L4 setback_side_ft"]


# --- the sweep end to end -------------------------------------------------


def test_a_sweep_reads_every_lens_and_then_asks_what_it_missed():
    """Four calls: three lenses, then the model reading its own answer."""
    calls: list[str] = []

    def ask(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return reply({"standard": "interior side yard", "line": 4, "states": "10 feet"})
        if len(calls) == 4:
            return reply({"standard": "fence height", "line": 6, "states": "3 feet"})
        return '{"found": []}'

    got = sweep(piece(), ask)

    assert len(calls) == 4
    assert {f.standard for f in got} == {"interior side yard", "fence height"}


def test_a_sweep_that_finds_nothing_does_not_ask_what_it_missed():
    """There is nothing to be told it left out, and the call costs a GPU second."""
    calls: list[str] = []

    def ask(prompt: str) -> str:
        calls.append(prompt)
        return '{"found": []}'

    assert sweep(piece(), ask) == []
    assert len(calls) == 3


def test_a_model_that_answers_nothing_at_all_yields_nothing():
    assert sweep(piece(), scripted(["", "", ""])) == []


from flats.encode.sweep.ask import LENSES  # noqa: E402 — read after the module's own names

_LENS = LENSES[0]


# --- the journal, which is what makes a county-scale run finishable ---------


def _setup(**over) -> Setup:
    base = {"model": "qwen2.5:7b", "size": 60, "overlap": 30, "context": 8192}
    base.update(over)
    return Setup(**base)


def test_a_passage_already_read_is_not_asked_again(tmp_path):
    """The whole point: an interrupted run resumes where it stopped."""
    book = Journal(tmp_path / "run.jsonl", _setup())
    book.open()
    chunk = piece()
    book.put(chunk, [Finding(document=DOC, line=4, standard="interior side yard",
                             applies_to="", states="10 feet", lenses=("dimension",))])

    again = Journal(tmp_path / "run.jsonl", _setup())
    assert again.open() == 1
    assert again.has(chunk)
    assert [f.standard for f in again.get(chunk)] == ["interior side yard"]


def test_a_passage_that_found_nothing_is_still_remembered(tmp_path):
    """Most passages state nothing about a fourplex. Re-reading them never ends."""
    book = Journal(tmp_path / "run.jsonl", _setup())
    book.open()
    book.put(piece(), [])

    again = Journal(tmp_path / "run.jsonl", _setup())
    again.open()
    assert again.has(piece())
    assert again.get(piece()) == []


def test_a_journal_from_a_differently_shaped_run_is_refused(tmp_path):
    """Recall only compares between runs of the same shape."""
    book = Journal(tmp_path / "run.jsonl", _setup(size=60))
    book.open()
    book.put(piece(), [])

    other = Journal(tmp_path / "run.jsonl", _setup(size=30))
    with pytest.raises(Mismatch):
        other.open()


def test_a_half_written_last_line_does_not_lose_the_rest(tmp_path):
    """A killed process leaves a torn line. Everything before it is still good."""
    path = tmp_path / "run.jsonl"
    book = Journal(path, _setup())
    book.open()
    book.put(piece(), [])
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"chunk": "or/x#L9-L16", "found": [{"stand')

    again = Journal(path, _setup())
    assert again.open() == 1


class _Stored:
    """Enough of a provenance store to answer one document."""

    def __init__(self, text: str) -> None:
        self.text = text

    def load(self, path: str):  # noqa: ANN202 — duck-typed against ProvenanceStore
        assert path == DOC
        return self


def test_a_resumed_run_does_not_re_ask_a_passage_it_already_read(tmp_path):
    """Resume is measured in questions not asked, so count them."""
    from flats.rules.model import CodeDocument

    layer = _layer().model_copy(
        update={"code": (CodeDocument(id="16.22", url="https://example.invalid/16.22"),)}
    )
    only = chunks(TEXT, document=DOC, size=60, overlap=30)
    assert len(only) == 1, "the fixture is one passage, so 'all of it' is countable"

    book = Journal(tmp_path / "run.jsonl", _setup())
    book.open()
    book.put(only[0], [])

    asked: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return '{"found": []}'

    report = sweep_run(
        layer, ask, store=_Stored(TEXT), journal=book, size=60, overlap=30
    )
    assert asked == []
    assert report.documents == (DOC,)


