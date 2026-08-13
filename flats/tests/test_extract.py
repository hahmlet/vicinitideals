"""Reading an ordinance into clauses and candidate values.

Extraction is allowed to be wrong; it is not allowed to be quietly wrong. Every
test here is about the second half — a number it cannot justify is not
proposed, a section stating two numbers is not resolved by guessing, and a
sentence it could not classify is reported rather than dropped.
"""

from __future__ import annotations

import pytest

from flats.encode.extract import (
    Extraction,
    candidates_in,
    extract,
    tag_of,
    to_yaml,
)
from flats.rules.ledger import Rase

pytestmark = pytest.mark.unit

DOC = "or/multnomah/portland/33.110.txt"

SECTION = """33.110.220 Development Standards
The standards of this section apply to all development in the R5 zone.
The minimum front building setback is 10 feet.
The minimum side building setback is 5 feet.
The minimum rear building setback is 5 feet.
The minimum lot area is 3,000 square feet.
The maximum building height is 35 feet.
Maximum building coverage is 45 percent.
Two parking spaces per dwelling unit are required.
Except on a corner lot, where the street-side setback is 10 feet.
Development site means the land occupied by a development.
"""


def one(text: str):
    return extract(text, path=DOC, jurisdiction="or/multnomah/portland")


# --- RASE tagging -----------------------------------------------------


@pytest.mark.parametrize(
    "text,tag",
    [
        ("The minimum front building setback is 10 feet.", Rase.requirement),
        ("No building shall exceed 35 feet in height.", Rase.requirement),
        ("Except where an alley abuts the lot.", Rase.exception),
        ("This section applies to all development in the R5 zone.", Rase.applicability),
        ("Development site means the land occupied by a development.", Rase.non_normative),
    ],
)
def test_clauses_are_tagged_by_what_they_do(text: str, tag: Rase) -> None:
    assert tag_of(text) == tag


def test_an_exception_outranks_the_requirement_inside_it() -> None:
    # "Except ... shall be 10 feet" is both, and reading it as a plain
    # requirement is how a screen applies a rule in the one case it does not
    # apply to. Exceptions win.
    assert tag_of("Except on a corner lot, the setback shall be 10 feet.") is Rase.exception


def test_a_sentence_it_cannot_place_is_left_untagged() -> None:
    # Not a failure. An untagged clause goes on the queue; a confidently
    # mis-tagged one goes into a bucket nobody re-reads.
    assert tag_of("Table 110-4.") is None


def test_untagged_clauses_are_reported(capsys) -> None:
    result = one("33.110.220 Standards\nTable 110-4.\n")

    assert [c.text for c in result.untagged] == ["Table 110-4."]


# --- candidate values -------------------------------------------------


def test_a_number_beside_a_subject_and_units_is_proposed() -> None:
    found = candidates_in("The minimum front building setback is 10 feet.", 3, DOC)

    assert [(c.field, c.value) for c in found] == [("setback_front_ft", 10)]
    assert found[0].quote == f"{DOC}#L3"


def test_a_number_with_no_subject_is_not_proposed() -> None:
    assert candidates_in("See Table 110-4 for 10 additional standards.", 1, DOC) == []


def test_a_subject_with_the_wrong_units_is_not_proposed() -> None:
    # "3,000 square feet" is not a setback, however close it sits to the word.
    assert candidates_in("The front setback table lists 3,000 square feet.", 1, DOC) == []


def test_thousands_separators_survive() -> None:
    found = candidates_in("The minimum lot area is 3,000 square feet.", 6, DOC)

    assert [(c.field, c.value) for c in found] == [("min_lot_sqft", 3000)]


def test_percentages_land_on_percentage_fields() -> None:
    found = candidates_in("Maximum building coverage is 45 percent.", 8, DOC)

    assert [(c.field, c.value) for c in found] == [("max_coverage_pct", 45)]


def test_a_ratio_per_unit_is_read_as_a_ratio() -> None:
    found = candidates_in("2 parking spaces per dwelling unit are required.", 9, DOC)

    assert [(c.field, c.value) for c in found] == [("parking_min_per_unit", 2)]


def test_a_number_spelled_out_in_words_is_not_invented() -> None:
    # "Two parking spaces" states a real standard this harness cannot read.
    # The right outcome is an unresolved requirement on the queue, not a
    # guessed 2 that nobody knows came from a guess.
    result = one("33.110.220 Standards\nTwo parking spaces per dwelling unit are required.\n")

    assert result.candidates == ()
    assert [c.text for c in result.unresolved()] == [
        "Two parking spaces per dwelling unit are required."
    ]


def test_the_more_specific_phrasing_wins() -> None:
    # "street-side setback" contains "side setback"; reading it as the interior
    # side would put a corner-lot standard on every lot in the zone.
    found = candidates_in("The street-side setback is 10 feet.", 1, DOC)

    assert [c.field for c in found] == ["setback_street_side_ft"]


def test_a_maximum_front_setback_is_a_different_field_from_the_minimum() -> None:
    found = candidates_in("The maximum front setback is 15 feet.", 1, DOC)

    assert [c.field for c in found] == ["setback_front_max_ft"]


# --- refusing to guess ------------------------------------------------


def test_two_numbers_for_one_field_are_both_kept_and_flagged() -> None:
    result = one(
        "33.110.220 Standards\n"
        "The minimum front building setback is 10 feet.\n"
        "On a corner lot the minimum front building setback is 15 feet.\n"
    )

    assert result.conflicted == ("setback_front_ft",)
    assert sorted(c.value for c in result.for_field("setback_front_ft")) == [10, 15]


def test_a_conflict_is_a_comment_not_a_value() -> None:
    result = one(
        "33.110.220 Standards\n"
        "The minimum front building setback is 10 feet.\n"
        "On a corner lot the minimum front building setback is 15 feet.\n"
    )

    yaml = to_yaml(result, zone="R5", cite="PCC 33.110.220", url="https://x", retrieved="2026-08-12")

    assert "CONFLICT setback_front_ft" in yaml
    assert "value: 10" not in yaml, "picking one silently is the failure this prevents"


def test_a_requirement_that_produced_no_number_is_reported() -> None:
    # The rule the screen would otherwise ignore entirely.
    result = one(
        "33.110.220 Standards\nThe building shall be oriented toward the street.\n"
    )

    assert [c.text for c in result.unresolved()] == [
        "The building shall be oriented toward the street."
    ]


# --- the whole section ------------------------------------------------


def test_a_real_section_yields_the_standards_it_states() -> None:
    result = one(SECTION)
    got = {c.field: c.value for c in result.candidates if not c.conflict}

    assert got["setback_front_ft"] == 10
    assert got["setback_side_ft"] == 5
    assert got["setback_rear_ft"] == 5
    assert got["min_lot_sqft"] == 3000
    assert got["max_height_ft"] == 35
    assert got["max_coverage_pct"] == 45


def test_clauses_carry_the_section_number_they_sit_under() -> None:
    result = one(SECTION)

    assert {c.section for c in result.clauses} == {"33.110.220"}


def test_every_candidate_quotes_a_line_a_reviewer_can_open() -> None:
    result = one(SECTION)

    for c in result.candidates:
        line = int(c.quote.rsplit("#L", 1)[1])
        assert SECTION.splitlines()[line - 1].strip() == c.text


def test_the_draft_yaml_is_never_pre_verified() -> None:
    yaml = to_yaml(
        one(SECTION), zone="R5", cite="PCC 33.110.220", url="https://x", retrieved="2026-08-12"
    )

    assert "status:" not in yaml, "extraction cannot promote; only a signature can"
    assert "verified" not in yaml
    assert 'quote: "' in yaml


def test_an_empty_document_extracts_to_nothing() -> None:
    assert extract("", path=DOC) == Extraction(path=DOC)


# --- what a real chapter PDF looks like -------------------------------
#
# Every case below was found by running this against Portland's Title 33
# chapter 33.110 rather than imagined: the numbers live in a table, sentences
# wrap mid-clause, page furniture lands in the middle of them, cross-references
# read as numbers, and the relief provisions state figures that are not the
# standard.

CHAPTER = """33.110.220 Setbacks
A. Purpose. The setback regulations serve several purposes.
B. Required setbacks. The required setbacks for buildings are
stated in Table 110-4. Other setbacks may apply.
Chapter 33.110 Title 33, Planning and Zoning
Single-Dwelling Zones 1/1/25
110-14
C. Standards. The minimum lot area is
3,000 square feet.
Chapter 33.110 Title 33, Planning and Zoning
Single-Dwelling Zones 1/1/25
110-15
D. Exceptions to the required setbacks.
1. In the R7 zones, the front building setback may be reduced to 10 feet.
2. See Figures 110-2 and 110-3. Detached structures are addressed in 33.110.245.
Chapter 33.110 Title 33, Planning and Zoning
Single-Dwelling Zones 1/1/25
110-16
"""


def test_a_wrapped_sentence_is_read_as_one_clause() -> None:
    # "the minimum lot area is / 3,000 square feet" is a standard split across
    # two PDF lines. Read as two clauses it is a subject with no number and a
    # number with no subject, and the standard vanishes.
    result = one(CHAPTER)

    assert any(c.field == "min_lot_sqft" and c.value == 3000 for c in result.candidates)


def test_page_furniture_does_not_break_a_sentence() -> None:
    result = one(CHAPTER)

    assert not any("Single-Dwelling Zones" in c.text for c in result.clauses)
    assert not any(c.text.strip() == "110-14" for c in result.clauses)


def test_a_section_heading_does_not_swallow_its_first_sentence() -> None:
    result = one(CHAPTER)

    assert result.clauses[0].text == "33.110.220 Setbacks"


def test_a_cross_reference_is_not_a_number() -> None:
    # "33.110.245" reads as 33.11 and 245; "Figures 110-2" as 110 and 2. A
    # chapter is dense with these, and every one of them would be a value.
    result = one(CHAPTER)

    assert all(c.value not in (110, 245, 33.11) for c in result.candidates)


def test_relief_provisions_are_exceptions_by_scope() -> None:
    # "the front building setback may be reduced to 10 feet" sits under
    # "D. Exceptions". Encoding its 10 as the standard would understate the
    # setback on every lot in the zone — the confident wrong answer.
    result = one(CHAPTER)

    assert result.for_field("setback_front_ft") == ()
    assert any(c.tag is Rase.exception for c in result.clauses if "reduced to 10" in c.text)


def test_a_table_the_prose_defers_to_is_named() -> None:
    # The honest output for Portland: the setbacks are real, they are in Table
    # 110-4, and this harness cannot read a grid with one column per zone.
    # Naming it queues the work; guessing a column encodes another zone's rule.
    assert one(CHAPTER).tables == ("110-4",)
