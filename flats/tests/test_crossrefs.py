"""The check that would have found Gresham's five feet a year earlier.

Every other check in this system starts from a document in the store: does the
citation resolve, does the line print the number, has anyone ruled on the
footnote over it. None of them can see a rule in a chapter nobody fetched,
because the loop never reaches a document that is not there.

Gresham's rear setbacks were read from Table 4.0130. The sentence that makes a
26 ft building stand five feet further back is in 7.0420, a design-standards
chapter in a different part of the code, and until yesterday nothing in the
encoding cited it. It was found by reading. Across roughly 21,000 lots, a year
late, and the system was silent the whole time — not because the check failed,
because there was no check.

This is the check. Read every document we hold, collect every section it points
at, and report the ones we cannot open. Rank by whether the pointer stands
beside a number the screen is already using, because that is the Gresham shape
exactly: a standard, and next to it a reference to the rule that qualifies it.

Two traps decide whether the answer is worth anything, and both are tested here.
Read too loosely and a table cell becomes a citation — "MDR-12, OFR  10 ft."
reports as a reference to Section 10, and the real findings drown. Read too
tightly and a wrapped line becomes a heading — Tualatin prints a bare
``TDC 36.410.`` at the start of eight lines, and a store that treats those as
headings answers for a chapter it does not hold, hiding the single most
referenced gap in that city.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from flats.encode.crossrefs import (
    BINDING_WINDOW,
    _REF,
    Dangling,
    _doc_ids,
    _headings,
    dangling,
    render,
    stale_rulings,
    state_law,
    survey,
    write,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
TUALATIN = "or/clackamas/tualatin"
WILSONVILLE = "or/clackamas/wilsonville"
OREGON_CITY = "or/clackamas/oregon-city"
MILWAUKIE = "or/clackamas/milwaukie"


@pytest.fixture(scope="module")
def layers() -> dict[str, Layer]:
    return load_rules()


@pytest.fixture(scope="module")
def tualatin(layers: dict[str, Layer]) -> dict[str, Dangling]:
    return {d.ref: d for d in dangling(layers[TUALATIN])}


# -- the thing it exists to catch ------------------------------------------


def test_the_chapter_that_hid_the_five_feet_is_held_now(
    layers: dict[str, Layer]
) -> None:
    """A regression on the finding, not on the tool.

    7.0420 resolves because 7.0400 is in the store. If a re-fetch ever drops
    that document this fails, and it should: the rear setback of six Gresham
    districts is computed from a sentence in it.
    """
    assert "7.0420" not in {d.ref for d in dangling(layers[GRESHAM])}


def test_the_reference_worth_chasing_was_chased(
    tualatin: dict[str, Dangling]
) -> None:
    """This ledger's first answer, and then what happened to it.

    Tualatin held two documents, and its residential chapter pointed eighteen
    times at TDC 36.410 — fifteen of them beside a number this screen uses,
    the loudest unread reference in the corpus. So it was fetched and read.
    It reduces the minimum lot size in a flexible lot subdivision, states its
    own path to be discretionary rather than clear and objective, and
    therefore cannot bind a by-right screen in either direction. Twenty-two
    binding references became two.

    Asserted as an absence because that is what working the queue looks like:
    a reference this loud reappearing means the document left the store.
    """
    assert "36.410" not in tualatin
    assert "73A" not in tualatin
    # Nothing left in this city is loud. The two that still bind are a
    # nonconforming-situations chapter and a retirement-housing section, at
    # two apiece against the fifteen this started with.
    assert max(d.binding for d in tualatin.values()) <= 2


def test_binding_is_what_orders_the_queue() -> None:
    """Mentions count how loud a reference is; binding counts whether it is
    standing next to something we screen against. A chapter mentioned once
    beside a setback outranks one mentioned forty times in a purpose clause."""
    loud = Dangling("l", "1.010", mentions=40, binding=0, sources=("a",), sample="")
    near = Dangling("l", "2.020", mentions=1, binding=1, sources=("a",), sample="")

    assert near.rank > loud.rank


def test_every_jurisdiction_is_asked(layers: dict[str, Layer]) -> None:
    """A survey that quietly skipped a layer would read as a clean bill."""
    rows = survey(list(layers.values()))
    assert {r.layer for r in rows} - set(layers) == set()
    assert any(r.binding for r in rows)


# -- reading too loosely ----------------------------------------------------


def test_a_table_cell_is_not_a_citation(tualatin: dict[str, Dangling]) -> None:
    """Zone codes sit directly in front of numbers in extracted tables, and a
    zone code has the same shape as a code abbreviation. "OFR  10 ft." is not
    a reference to Section 10, so a bare number after an abbreviation is
    refused — a section number carries a dot and a table cell does not."""
    assert "10" not in tualatin
    assert "20" not in tualatin


def test_a_spelled_out_word_may_still_take_a_bare_number(
    tualatin: dict[str, Dangling]
) -> None:
    """"See TDC Chapter 35" is a reference and there is nothing else it could
    be, so the strictness is on the abbreviation and not on the number."""
    assert "35" in tualatin


def test_state_law_is_counted_somewhere_else(
    layers: dict[str, Layer], tualatin: dict[str, Dangling]
) -> None:
    """ORS 92.010 is referenced eight times in Tualatin's definitions. It is a
    real gap and it is not Tualatin's chapter — a statute in the city's list
    would bury the city's own missing chapters under boilerplate."""
    assert "92.010" not in tualatin
    assert state_law(layers[TUALATIN]).get("92.010", 0) >= 5


def test_a_suffix_letter_belongs_to_the_section_not_to_the_sentence(
    tualatin: dict[str, Dangling]
) -> None:
    """Tualatin really does have a Chapter 73A. It does not have a section
    40.220L — that is "TDC 40.220LOW DENSITY RESIDENTIAL ZONE" with a space
    lost in extraction.

    The bare chapter no longer appears, because a slice of it is held and a
    chapter reference resolves against anything under it. Its sections do,
    which is the same letter surviving the same reader.
    """
    assert "73A.170" in tualatin
    assert not [ref for ref in tualatin if ref.endswith("L")]


# -- reading too tightly ----------------------------------------------------


def test_a_wrapped_reference_does_not_answer_for_itself() -> None:
    """The trap that makes this whole check worth writing carefully.

    Extracted table text wraps, and eight lines of Tualatin's residential
    chapter begin with a bare ``TDC 36.410.``. Read as headings they would say
    the store holds chapter 36, and for a year the most-referenced gap in the
    city would have reported as fetched. A heading has to belong to the
    document it is in.

    Stated against the reader rather than against the corpus, because the
    corpus moved: 36.410 was fetched, and a test that watched for it in the
    ledger would now pass whether or not the ownership rule survived.
    """
    wrapped = (
        "TDC 36.410. Flexible Lot Subdivisions\n"
        "TDC 40.300. Development Standards\n"
    )

    assert _headings(wrapped, {"40", "41"}) == {"40.300"}


def test_a_reference_that_wrapped_across_a_column_is_not_a_heading() -> None:
    """The ownership rule cannot separate a chapter from its own siblings.

    Portland's whole code is Title 33, so every 33.x number that opens a line
    in any of its files passes the ownership test. Extraction wraps a citation
    at the column edge and drops the number onto the next line, where it is
    indistinguishable from a heading -- number, comma, title. Twenty chapters
    answered for themselves that way, Conditional Uses and Measurements among
    them, and none of them was ever in the store.

    What separates the two is the line before: a heading does not continue a
    sentence that stopped at the word "Chapter".
    """
    wrapped = (
        "         Screening must comply with the L3 or F2 standards of Chapter\n"
        "                    33.248, Landscaping and Screening.\n"
        "\n"
        "33.110.250 Additional Development Standards for Garages\n"
    )

    assert _headings(wrapped, {"33"}, {"33.110"}) == {"33.110.250"}


def test_a_held_chapter_still_answers_for_its_own_sections() -> None:
    """The guard above must not cost a real heading.

    A section of the chapter this document holds resolves on its heading and
    nothing else -- the filename claims 33.110, not 33.110.250 -- so a wrapped
    line ending in "Section" immediately before one would, unguarded, delete a
    section we hold from the store's answer.
    """
    text = (
        "     the requirements are stated in Section\n"
        "33.110.250 Additional Development Standards for Garages\n"
    )

    assert _headings(text, {"33"}, {"33.110"}) == {"33.110.250"}

def test_a_whole_title_answers_for_every_section_inside_it(
    layers: dict[str, Layer]
) -> None:
    """Oregon City's Title 17 is one file and Wilsonville's Chapter 4 is
    another. Both are more completely fetched than a city with twenty-six
    chapter files, and a check that counted documents would say the opposite.
    """
    assert "17.29.030" not in {d.ref for d in dangling(layers[OREGON_CITY])}
    assert "4.137" not in {d.ref for d in dangling(layers[WILSONVILLE])}


def test_a_section_symbol_is_part_of_the_heading(
    layers: dict[str, Layer]
) -> None:
    """Four jurisdictions print every heading as "SECTION-SIGN 19.302.4.", and
    reading past the symbol is not optional.

    Milwaukie topped the first ledger with 123 binding hits, and eight of its
    twenty-three references were sections printed as headings in the very
    document doing the referencing. A check whose loudest answer is its own
    blind spot teaches a reader to discount it.
    """
    refs = {d.ref for d in dangling(layers[MILWAUKIE])}

    for own in ("19.301.2", "19.301.5", "19.302.2", "19.302.4", "19.302.5"):
        assert own not in refs, own

    # And the ones that really were absent are gone because the ledger was
    # worked, not because the check got looser. Milwaukie held 19.200 and
    # 19.300; every surviving reference pointed into 19.500, so 19.500 was
    # fetched, and with it the side yard height plane that put six feet on
    # both side yards of the zone. Fifteen binding references became five.
    assert "19.501.3" not in refs
    assert "19.505.1" not in refs
    # What is left is a different title, and this corpus is not going to grow
    # Milwaukie's public-works code.
    assert "12.24" in refs


def test_only_the_section_symbol_earns_that(layers: dict[str, Layer]) -> None:
    """Gresham stamps "[3.0100-7]" at the foot of 451 pages, which is a page
    number and not a section. Widening the marker set to "whatever punctuation
    starts the line" would have swallowed it, so the symbol is admitted by
    name."""
    text = "§ 19.302.4. Development Standards.\n     [19.400-7]\n  19.302.9 x\n"
    assert _headings(text, {"19"}) == {"19.302.4", "19.302.9"}


def test_a_chapter_may_carry_a_letter() -> None:
    """Tualatin's design standards are Chapter 73A, and a reader that stopped
    at the first non-digit gave that document no sections at all: it claimed
    nothing, and the chapter it held went on reporting as unfetched."""
    assert _doc_ids(["or/clackamas/tualatin/73A.020-060.residential-design.txt"]) == {
        f"73A.{n:03d}" for n in range(20, 61)
    }


def test_a_span_is_read_wherever_it_sits_in_the_name() -> None:
    """``40-41`` is two chapters and ``36.400-420`` is three sections of one,
    and the range was read only in the first group. So a document holding
    36.400, 36.410 and 36.420 claimed a section number that does not exist and
    answered for none of the three."""
    ids = _doc_ids(["or/clackamas/tualatin/36.400-420.lot-dimensions.txt"])

    assert {"36.400", "36.410", "36.420"} <= ids
    assert "36.400-420" not in ids


def test_a_reference_to_a_lettered_chapter_s_section_is_read_at_all() -> None:
    """Not read loosely — not read. The abbreviation branch failed at the
    letter, the keyword branch wants a keyword and the bare branch wants three
    dotted groups, so "Subject to TDC 73A.170" appeared in no ledger. A
    reference nobody can see is worse than one ranked badly."""
    refs = {
        (m.group("named") or m.group("abbrev") or m.group("dotted")).rstrip(".")
        for m in _REF.finditer(
            "Accessory Dwelling Unit P Subject to TDC 73A.170.\n"
            "TDC 40.220LOW DENSITY RESIDENTIAL ZONE (RL)\n"
        )
    }

    assert "73A.170" in refs
    # And the reason the letter has to end the token is still true.
    assert not [r for r in refs if r.endswith("L")]


def test_a_filename_may_claim_more_than_one_chapter() -> None:
    """``40-41.residential`` is two chapters in one fetch, and reading it as
    one would report every section of 41 as unfetched."""
    assert _doc_ids(["or/clackamas/tualatin/40-41.residential.txt"]) == {"40", "41"}
    assert _doc_ids(["or/multnomah/gresham/7.0400.middle-housing-design.txt"]) == {
        "7.0400"
    }
    assert _doc_ids(["or/clackamas/wilsonville/4.planning.txt"]) == {"4"}


# -- the ledger -------------------------------------------------------------


def test_the_window_is_narrow_enough_to_mean_something() -> None:
    """Binding says "beside", and beside has to stay small enough that it is
    not just "in the same chapter"."""
    assert 0 < BINDING_WINDOW <= 25


def test_the_ledger_round_trips(tmp_path: Path, layers: dict[str, Layer]) -> None:
    rows = dangling(layers[TUALATIN])
    path = write(rows, tmp_path / "crossrefs.csv")

    back = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(back) == len(rows)
    assert {r["ref"] for r in back} == {r.ref for r in rows}
    assert any(int(r["binding"]) for r in back)


def test_an_empty_answer_says_so_rather_than_printing_nothing() -> None:
    assert "no unfetched references" in "\n".join(render(()))


# -- leaving the queue without being fetched --------------------------------


GLADSTONE = "or/clackamas/gladstone"


def test_a_reference_can_be_settled_by_reading_it(layers: dict[str, Layer]) -> None:
    """The outcome this ledger could not previously record.

    Gladstone's 17.62.070 topped the whole corpus — ten mentions, ten of them
    beside a number this screen uses — and all ten are the same sentence,
    printed once and spanned by rowspan down every setback row: setbacks for
    manufactured homes in a mobile home park. The pod is factory-built and is
    neither a manufactured dwelling nor on a rented space, so reading it
    settles it, and a check built on "is the chapter in the store" can never
    see that.
    """
    ruled = {d.ref: d for d in dangling(layers[GLADSTONE]) if d.ruled}

    assert "17.62.070" in ruled
    assert ruled["17.62.070"].mentions == 10
    assert "mobile home park" in ruled["17.62.070"].ruling


def test_a_ruled_reference_stops_leading_the_queue(layers: dict[str, Layer]) -> None:
    """Rank, not visibility. A settled question sitting at the top of a queue
    forever teaches whoever works it to skip rows."""
    rows = dangling(layers[GLADSTONE])

    assert rows[0].ref != "17.62.070"
    assert dangling(layers[GLADSTONE])[-1].rank == (0, 0, 0)


def test_and_it_is_still_printed(layers: dict[str, Layer]) -> None:
    """Under its own heading, with the reason, so a reader can disagree with
    the ruling. A queue that silently dropped rows would be as untrustworthy
    as one that never dropped any."""
    printed = "\n".join(render(dangling(layers[GLADSTONE]), binding_only=True))

    assert "17.62.070" in printed
    assert "mobile home park" in printed
    # And it is out of the count that says how much work is left.
    assert "17.62.070" not in printed.split("closed —")[0]


def test_the_ruling_is_carried_into_the_ledger(
    tmp_path: Path, layers: dict[str, Layer]
) -> None:
    rows = dangling(layers[GLADSTONE])
    back = list(csv.DictReader(write(rows, tmp_path / "crossrefs.csv").open(encoding="utf-8")))

    ruled = next(r for r in back if r["ref"] == "17.62.070")
    assert "mobile home park" in ruled["ruling"]

    # And a row with no ruling carries an empty cell rather than something.
    # Chosen by asking the layer which references it has not ruled on, not by
    # naming one: a named unruled reference is an emptiness that goes red the
    # first time somebody does the work of ruling on it.
    unruled = next(
        r for r in back if r["ref"] not in layers[GLADSTONE].crossrefs
    )
    assert not unruled["ruling"]
    assert not unruled["outcome"]


def test_a_ruling_nobody_can_see_any_more_is_reported(layers: dict[str, Layer]) -> None:
    """The other direction. A ruling survives a re-fetch that removes the
    sentence, or a fetch of the chapter it ruled on — and either way it is
    describing a corpus that has moved."""
    assert stale_rulings(layers[GLADSTONE]) == []

    moved = layers[GLADSTONE].model_copy(
        update={"crossrefs": {"17.62.070": "x" * 50, "99.999": "y" * 50}}
    )
    assert stale_rulings(moved) == ["99.999"]


def test_and_no_layer_in_the_corpus_carries_one() -> None:
    """The check the ledger was already making and nothing was reading.

    Gresham kept rulings on 10.1700 and Table 9.0851 from when neither chapter
    had been fetched. Both were fetched and read on 2026-08-20, so neither
    dangled any more and the ledger printed them as stale for a day with
    nobody watching. The reasoning moved into the layer's notes, under READ AND
    NOT ENCODED, which is where 7.0512's already was."""
    stale = {
        name: refs
        for name, layer in load_rules().items()
        if (refs := stale_rulings(layer))
    }
    assert stale == {}


def _somewhere(root: Path, block: str) -> Path:
    d = root / "or" / "clackamas"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/clackamas/somewhere\nkind: city\nlabel: Somewhere\n"
        "zones: {}\n" + block,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_a_ruling_has_to_say_something(tmp_path: Path) -> None:
    """"n/a" closes a row without telling the next reader anything, which is
    worse than leaving it open — an open row at least still shows the
    sentence."""
    with pytest.raises(RuleLoadError, match="at least"):
        load_rules(_somewhere(tmp_path, 'crossrefs:\n  "17.62.070": n/a\n'), strict=True)


# -- which number it stands beside ------------------------------------------


CLACKAMAS = "or/clackamas/_unincorporated"
RIVERGROVE = "or/clackamas/rivergrove"
FAIRVIEW = "or/multnomah/fairview"


def test_a_reference_says_which_standard_it_is_standing_beside(
    layers: dict[str, Layer],
) -> None:
    """Binding says a reference is beside *something*. That is not enough to
    judge it on.

    Fairview's queue opened on signs, wireless towers, home occupations and
    day care providers, every one of them flagged binding, because a use table
    is printed a few lines under the dimensional table of the same zone. The
    counts could not tell those from a design chapter that moves a setback,
    and the ledger had no way to say why they were not worth a fetch.
    """
    rows = {d.ref: d for d in dangling(layers[GRESHAM])}

    beside = rows["7.0221"]
    assert beside.fields == ("setback_rear_ft",)
    assert beside.slack_fields == ("setback_rear_ft",)


def test_a_use_permission_is_not_a_distance(layers: dict[str, Layer]) -> None:
    """The line the ranking is drawn on, and the registry already drew it.
    Reading a chapter cannot make a prohibited use slightly more prohibited,
    so a reference sitting in a use table is a different finding from one
    sitting beside a setback however adjacent both are."""
    both = Dangling(
        "l", "1.010", mentions=1, binding=1, sources=("a",), sample="",
        fields=("quadplex_allowed", "setback_rear_ft"),
    )
    use_only = Dangling(
        "l", "2.020", mentions=40, binding=9, sources=("a",), sample="",
        fields=("quadplex_allowed",),
    )

    assert both.slack_fields == ("setback_rear_ft",)
    assert use_only.slack_fields == ()
    assert both.rank > use_only.rank


def test_a_zone_borrowing_another_s_rules_names_no_standard() -> None:
    """``like`` is a real citation and belongs in the window -- it is the line
    a reviewer would open. It just cannot make a reference rank as though a
    dimension were at stake, because it names none."""
    borrowed = Dangling(
        "l", "1.010", mentions=1, binding=1, sources=("a",), sample="",
        fields=("like",),
    )

    assert borrowed.fields == ("like",)
    assert borrowed.slack_fields == ()
    assert borrowed.rank[0] == 0


def test_the_fields_are_carried_into_the_ledger(
    tmp_path: Path, layers: dict[str, Layer]
) -> None:
    rows = dangling(layers[GRESHAM])
    back = list(csv.DictReader(write(rows, tmp_path / "crossrefs.csv").open(encoding="utf-8")))

    row = next(r for r in back if r["ref"] == "7.0221")
    assert row["fields"] == "setback_rear_ft"
    assert row["slack_fields"] == "setback_rear_ft"
    assert row["outcome"] == "other_building"


# -- documents that claim nothing -------------------------------------------


def test_a_filename_may_open_with_the_code_s_own_abbreviation() -> None:
    """Clackamas County names its documents for the ordinance, not the
    chapter. Reading only the leading digits gave four of them no sections at
    all, so every reference to a section they hold reported as unfetched --
    and the county's own Section 1012, fifteen mentions and the loudest
    reference in that layer, led this queue while sitting in the store."""
    assert _doc_ids(["or/clackamas/_unincorporated/zdo.1012.txt"]) == {"1012"}
    assert _doc_ids(["or/clackamas/_unincorporated/zdo.202.definitions.txt"]) == {"202"}
    # And the abbreviation is not eaten out of a name that never had one.
    assert _doc_ids(["or/clackamas/tualatin/40-41.residential.txt"]) == {"40", "41"}


def test_the_chapter_it_was_hiding_is_answered_for(layers: dict[str, Layer]) -> None:
    refs = {d.ref for d in dangling(layers[CLACKAMAS])}

    assert "1012" not in refs
    assert "1012.03" not in refs
    assert "845.02" not in refs


def test_a_whole_code_in_one_file_owns_what_it_prints() -> None:
    """Rivergrove's land development ordinance is 3.x, 5.x and 6.x in a single
    document named for the ordinance. There is no chapter it does not hold, so
    refusing it ownership reported its own sections as unfetched.

    It keeps the wrapped-line guard, which is the part that was doing the work
    -- ownership only ever short-circuited that guard for a document's own
    children, and a file that claims no children has none to short-circuit
    for."""
    text = "5.010 Land Use.\nAll land is zoned residential, per Chapter\n7.020, Parking.\n"

    assert _headings(text, None) == {"5.010"}


def test_and_rivergrove_stops_reporting_its_own_code_as_missing(
    layers: dict[str, Layer],
) -> None:
    refs = {d.ref for d in dangling(layers[RIVERGROVE])}

    assert "5.010" not in refs
    assert "5.080" not in refs


def test_every_document_either_claims_a_chapter_or_is_a_whole_code() -> None:
    """Two are named for an ordinance with no number in it at all, and both are
    the whole of what their jurisdiction publishes. Two more are engineering
    drawings, which have a sheet number and no chapter -- P100 and P200 are
    where Clackamas County publishes its parking geometry, and a sheet answers
    for no section of anything. Any other silent document would more likely be
    a filename that broke the convention, and the fallback would then be
    answering for a chapter nobody holds.

    ``roadway.320`` is deliberately NOT in this set. It was, until `_ABBREV`
    was widened to seven letters: at five, the leading word was neither an
    abbreviation to skip nor a number to read, and the Roadway Standards
    claimed nothing while holding the section every parking dimension in that
    county comes from."""
    store = ProvenanceStore()
    silent = {d for d in store.documents() if not _doc_ids([d])}

    assert silent == {
        "or/clackamas/johnson-city/ors.197a.420.txt",
        "or/clackamas/rivergrove/rldo.composite.txt",
        "or/clackamas/_unincorporated/roadway.p100.txt",
        "or/clackamas/_unincorporated/roadway.p200.txt",
    }
    assert _doc_ids(["or/clackamas/_unincorporated/roadway.320.txt"]) == {"320"}


# -- a decision is not a disposal -------------------------------------------


def _ordered(layers: dict[str, Layer]) -> list[tuple[str, Dangling]]:
    """Every fetch the corpus is currently carrying, found by asking.

    Named examples do not survive here. This pair of tests used to open on
    Fairview 19.164, which was ordered on 2026-08-26 and fetched the same
    afternoon; the ruling then came out, because a ruling on a reference the
    store can resolve reports as stale, and both tests went red for having
    named a row rather than a condition. What they are about is the rule --
    ``fetch`` and ``later`` are decisions and a decision is not a disposal --
    so the rule is what they ask for.
    """
    return [
        (layer_id, row)
        for layer_id, layer in layers.items()
        for row in dangling(layer)
        if row.outcome == "fetch"
    ]


def test_work_ordered_stays_in_the_queue(layers: dict[str, Layer]) -> None:
    """``CROSSREF_CLOSED`` has excluded ``fetch`` and ``later`` since the
    vocabulary was written, and the review queue honours it. This ledger did
    not, so the first ordered fetch anybody recorded sorted to the bottom
    under a heading reading "read, and about somebody else's building"."""
    ordered = _ordered(layers)

    assert ordered, "no fetch is ordered anywhere in the corpus"
    for layer_id, row in ordered:
        assert row.ruling, (layer_id, row.ref)
        assert not row.ruled, (layer_id, row.ref)
        assert row.rank[1] == row.binding, (layer_id, row.ref)


def test_and_the_queue_prints_why_it_is_still_there(layers: dict[str, Layer]) -> None:
    layer_id, row = _ordered(layers)[0]
    printed = "\n".join(render(dangling(layers[layer_id])))
    head = printed.split("closed —")[0]

    assert "FETCH:" in head
    assert row.ref in head
    # The closed ones are out of the working queue and under their own heading.
    # Asked as "they are below the line" rather than "they are not above it":
    # a section number is a substring of other section numbers and of the
    # sample text quoted beside them, so absence is the wrong question.
    tail = printed.split("closed —", 1)[1]
    closed = [d.ref for d in dangling(layers[layer_id]) if d.ruled]
    assert closed, layer_id
    assert all(ref in tail for ref in closed), (layer_id, closed)


def test_a_row_closed_by_reading_leaves(layers: dict[str, Layer]) -> None:
    rows = {d.ref: d for d in dangling(layers[FAIRVIEW])}

    assert rows["19.245"].outcome == "other_path"
    assert rows["19.245"].ruled
    assert rows["19.245"].rank == (0, 0, 0)
