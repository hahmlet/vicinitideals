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
    state_law,
    survey,
    write,
)
from flats.rules.loader import load_rules
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
