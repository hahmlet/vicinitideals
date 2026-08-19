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
    states_a_rule,
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


# --- the table the prose defers to ------------------------------------

WITH_TABLE = """33.110.220 Setbacks
B. Required setbacks. The required setbacks for buildings are
stated in Table 110-4.
Table 110-4
Standard                      RF          R5          R2.5
- Front building              20 ft.      10 ft.      10 ft.
 setback
Maximum Height                30 ft.      30 ft.      35 ft.
"""


def test_a_zone_reads_its_own_column_of_the_table() -> None:
    result = extract(WITH_TABLE, path=DOC, zone="R5")
    got = {c.field: c.value for c in result.candidates}

    assert got["setback_front_ft"] == 10
    assert got["max_height_ft"] == 30


def test_another_zone_reads_a_different_column_of_the_same_table() -> None:
    got = {c.field: c.value for c in extract(WITH_TABLE, path=DOC, zone="R2.5").candidates}

    assert got["max_height_ft"] == 35


def test_without_a_zone_the_table_is_left_unread() -> None:
    # A grid holds one value per zone. With no zone named there is no column
    # to read, and reading any of them would be picking one at random.
    assert extract(WITH_TABLE, path=DOC).candidates == ()


def test_prose_and_table_agreeing_is_not_a_conflict() -> None:
    text = WITH_TABLE + "The minimum front building setback is 10 feet.\n"

    assert extract(text, path=DOC, zone="R5").conflicted == ()


def test_prose_and_table_disagreeing_goes_to_a_person() -> None:
    # Which one governs is a reading question — often the prose is an exception
    # the table does not show. Both survive, flagged, and neither is encoded.
    text = WITH_TABLE + "The minimum front building setback is 15 feet.\n"
    result = extract(text, path=DOC, zone="R5")

    assert result.conflicted == ("setback_front_ft",)
    assert sorted(c.value for c in result.for_field("setback_front_ft")) == [10, 15]


def test_a_table_value_quotes_the_row_it_was_read_from() -> None:
    result = extract(WITH_TABLE, path=DOC, zone="R5")
    line = int(next(c for c in result.candidates if c.field == "max_height_ft").quote.rsplit("#L", 1)[1])

    assert "30 ft." in WITH_TABLE.splitlines()[line - 1]


def test_a_table_the_prose_defers_to_is_named() -> None:
    # The honest output for Portland: the setbacks are real, they are in Table
    # 110-4, and this harness cannot read a grid with one column per zone.
    # Naming it queues the work; guessing a column encodes another zone's rule.
    assert one(CHAPTER).tables == ("110-4",)


def test_a_corner_lot_side_setback_is_the_street_side() -> None:
    # Rivergrove's RLDO 5.080 phrases the street-side standard as "Side
    # Setback on a Corner Lot - 15 feet". The side that abuts the street is
    # the street-side setback; reading it as the interior side hands a
    # corner-only number to every lot in the zone.
    found = candidates_in(
        "Side Setback on a Corner Lot - 15 feet (to insure better visibility).", 1, DOC
    )

    assert [(c.field, c.value) for c in found] == [("setback_street_side_ft", 15)]


def test_the_parenthesised_corner_phrasing_is_also_the_street_side() -> None:
    found = candidates_in("Side Setback (corner lot) - 10 feet.", 1, DOC)

    assert [(c.field, c.value) for c in found] == [("setback_street_side_ft", 10)]


def test_a_corner_side_setback_is_the_street_side() -> None:
    found = candidates_in("The corner side setback is 12 feet.", 1, DOC)

    assert [c.field for c in found] == ["setback_street_side_ft"]


def test_an_exterior_side_setback_is_the_street_side() -> None:
    found = candidates_in("The exterior-side setback is 20 feet.", 1, DOC)

    assert [c.field for c in found] == ["setback_street_side_ft"]


def test_a_plain_side_setback_is_still_the_interior_side() -> None:
    # The corner patterns must not swallow the base standard.
    found = candidates_in("Side Setback - 10 feet.", 1, DOC)

    assert [(c.field, c.value) for c in found] == [("setback_side_ft", 10)]


# --- section attribution ----------------------------------------------------


def test_furniture_glued_before_a_heading_does_not_steal_its_section() -> None:
    # Rivergrove's compilation stamps an unpunctuated disclaimer and page
    # number ahead of every article; without a split at the heading the
    # paragraph starts before it and the candidate files under the previous
    # section.
    text = (
        "Section 4.120.  Procedures.  Applications are heard quarterly.\n"
        "THIS IS A COMPILATION OF ENACTMENTS AND IS NOT THE OFFICIAL ORDINANCE TEXT AT ALL\n"
        "15\n"
        "Section 5.010.  Land Use.  The minimum lot size is 10,000 square feet.\n"
    )
    result = extract(text, path=DOC)

    found = [c for c in result.candidates if c.field == "min_lot_sqft"]
    assert [(c.value, c.section) for c in found] == [(10000, "5.010")]


def test_a_wrapped_citation_does_not_move_the_section_cursor() -> None:
    # "TDC 36.410, or Greenway areas" is a sentence resuming after a line
    # wrap, not a heading — filing what follows under 36.410 attributes the
    # next standard to a cross-reference.
    text = (
        "40.210 Residential Districts\n"
        "Flexible lots are allowed pursuant to.\n"
        "TDC 36.410, or Greenway areas described elsewhere.\n"
        "The minimum front setback is 15 feet.\n"
    )
    result = extract(text, path=DOC)

    found = [c for c in result.candidates if c.field == "setback_front_ft"]
    assert [(c.value, c.section) for c in found] == [(15, "40.210")]


def test_a_bare_citation_line_is_not_a_heading_either() -> None:
    text = (
        "40.210 Residential Districts\n"
        "Small lots are governed by.\n"
        "TDC 36.410.\n"
        "The minimum front setback is 15 feet.\n"
    )
    result = extract(text, path=DOC)

    found = [c for c in result.candidates if c.field == "setback_front_ft"]
    assert [(c.value, c.section) for c in found] == [(15, "40.210")]


# --- vocabulary earned on real text -----------------------------------------


def test_a_driveway_width_per_frontage_is_not_a_frontage_standard() -> None:
    # Troutdale and Wilsonville both cap driveway approaches at "32 feet per
    # frontage"; the bare noun handed the driveway width to min_frontage_ft
    # on every zone in the chapter.
    found = candidates_in(
        "The total width of all driveway approaches must not exceed 32 feet per frontage.",
        1,
        DOC,
    )

    assert found == []


def test_a_qualified_frontage_is_still_read() -> None:
    found = candidates_in("The minimum street frontage is 35 feet.", 1, DOC)

    assert [(c.field, c.value) for c in found] == [("min_frontage_ft", 35)]


def test_an_average_lot_size_is_not_a_minimum() -> None:
    # Springwater's purpose paragraph describes character "at an average lot
    # size of 12,000 square feet" — nobody may hold a permit to an average.
    found = candidates_in(
        "The district provides Middle Housing at an average lot size of 12,000 square feet.",
        1,
        DOC,
    )

    assert found == []


def test_a_lot_size_class_selector_is_not_a_standard() -> None:
    # "In zones with a minimum lot size of less than 5,000 square feet ..."
    # keys a parking rule to a lot-size class; the threshold may corroborate
    # nothing and contradict nothing.
    assert not states_a_rule(
        "In zones with a minimum lot size of less than 5,000 square feet, a minimum of "
        "two off-street parking spaces per quadplex development is required."
    )


def test_relief_that_may_be_permitted_is_an_exception() -> None:
    found = candidates_in(
        "The maximum front or street side setback of up to 20 feet may be permitted "
        "when enhanced pedestrian spaces and amenities are provided.",
        1,
        DOC,
    )

    assert found == []


def test_a_sentence_naming_its_housing_type_carries_it() -> None:
    # Wilsonville § 4.113 states cottage-cluster setbacks and townhouse lot
    # minimums as prose. The type travels on the candidate so selection can
    # decide whether it speaks for the pod, exactly as for a typed table row.
    found = candidates_in(
        "For townhouses, the minimum lot size shall be 1,500 square feet.", 4, DOC
    )

    assert [c.housing_type for c in found] == ["townhouse"]


def test_an_untyped_sentence_carries_no_type() -> None:
    found = candidates_in("The minimum lot area is 3,000 square feet.", 6, DOC)

    assert [c.housing_type for c in found] == [""]


def test_a_zone_list_sentence_is_a_selection_not_a_base_standard() -> None:
    # Wilsonville footnote B: "For the PDR 3 through PDR 7 zones, the minimum
    # lot size for quadplexes ... is 7,000 square feet." The prose reader
    # cannot resolve the zone list against the zone it is checking, so the
    # sentence may corroborate but must never contradict — PDR-1's 20,000
    # is not wrong because a PDR-3-through-7 footnote says 7,000.
    assert not states_a_rule(
        "For the PDR 3 through PDR 7 zones, the minimum lot size for "
        "quadplexes is 7,000 square feet."
    )


def test_a_sub_district_sentence_is_a_selection() -> None:
    assert not states_a_rule(
        "In R-5 and R-7 sub-districts the minimum lot size for quadplexes "
        "and cottage clusters is 7,000 square feet."
    )


def test_a_plain_minimum_is_still_a_base_standard() -> None:
    assert states_a_rule("The minimum lot area is 7,000 square feet.")


def test_a_frontage_rate_is_not_a_frontage_minimum() -> None:
    # Wilsonville 4.113: "At least one connection shall be made to each
    # adjacent street and sidewalk for every 200 linear feet of street
    # frontage." The genitive measures frontage as a quantity — reading it
    # puts a 200-foot minimum on every zone in the chapter.
    assert (
        candidates_in(
            "At least one connection shall be made to each adjacent street "
            "and sidewalk for every 200 linear feet of street frontage.",
            1,
            DOC,
        )
        == []
    )


def test_a_row_naming_both_bounds_is_read_as_the_minimum() -> None:
    # "Lot size (minimum and maximum density)" is a minimum that mentions a
    # ceiling on something else. Reading it as a ceiling deleted the base
    # standard of six Happy Valley zones and left the townhouse row to
    # contradict them.
    found = candidates_in(
        "Lot size (minimum and maximum density): quadplex 40,000 sq. ft.", 1, DOC
    )

    assert [c.field for c in found] == ["min_lot_sqft"]


def test_a_setback_qualified_after_its_name_reads_as_the_qualified_field() -> None:
    # A numbered table states the standard first and qualifies it after:
    # "Front Yard Setback Maximum". Read left to right it is a front
    # setback, which is the one thing it is not.
    found = candidates_in("The front yard setback maximum is 30 feet.", 1, DOC)

    assert [c.field for c in found] == ["setback_front_max_ft"]


def test_a_street_side_yard_is_the_street_side_setback() -> None:
    found = candidates_in("The street side yard setback is 10 feet.", 1, DOC)

    assert [c.field for c in found] == ["setback_street_side_ft"]


def test_a_height_plane_is_not_a_height_limit() -> None:
    # Milwaukie's side yard height plane starts 20 ft above ground where the
    # zone's height limit is 35 — a sloped envelope over the side yard, not a
    # ceiling. Filed as the limit it halves the building on every lot.
    assert (
        candidates_in(
            "The height above ground at the minimum required side yard depth is 20 feet.",
            4,
            DOC,
        )
        == []
    )


def test_a_yard_named_without_the_word_setback_is_not_read_from_prose() -> None:
    # The bare-yard labels are a table row shape — "c. Street side yard" over
    # a column of numbers — and they are matched whole for that reason. A
    # sentence mentioning a front yard is not a standard.
    assert candidates_in("Parking is prohibited in the front yard within 5 feet.", 9, DOC) == []


def test_a_measure_written_as_a_word_is_read() -> None:
    # Wilsonville states half its setbacks in words -- "Minimum side yard
    # setback: Ten feet." -- and a reader that saw only digits read the
    # sentence, found no number in it, and left the standard unread.
    found = candidates_in("Minimum side yard setback: Ten feet.", 3, DOC)

    assert [(c.field, c.value) for c in found] == [("setback_side_ft", 10)]


def test_a_word_measure_keeps_the_rest_of_the_line_where_it_was() -> None:
    # Every other rule here reasons about where a number sits relative to the
    # subject it governs. The substitution pads to the same width so that a
    # sentence with a word in it is measured exactly like one with a digit.
    from flats.encode.extract import _digits

    line = "The minimum front yard setback shall be twenty-five feet."

    assert len(_digits(line)) == len(line)
    assert [(c.field, c.value) for c in candidates_in(line, 4, DOC)] == [("setback_front_ft", 25)]


def test_a_counted_word_is_not_a_measure() -> None:
    # "Four out of five attached garages ... shall be set back a minimum of 20
    # feet" counts garages, and the count is not a setback. The unit after the
    # word is what separates the two, so only a word a unit follows is read.
    from flats.encode.extract import _digits

    assert _digits("Four out of five attached garages") == "Four out of five attached garages"
    values = {c.value for c in candidates_in(
        "Four out of five attached garage doors shall be set back a minimum of 20 "
        "feet from the front facade.",
        5,
        DOC,
    )}

    assert values == {20}


def test_a_number_said_twice_is_read_once() -> None:
    # "four (4) feet" is the same measure written both ways, and the digit is
    # already readable. Converting the word as well would state it twice.
    from flats.encode.extract import _digits

    assert _digits("a minimum of four (4) feet") == "a minimum of four (4) feet"


def test_a_hundred_is_read_whole() -> None:
    from flats.encode.extract import _word_value

    assert _word_value("one hundred") == 100
    assert _word_value("thirty-five") == 35
    assert _word_value("seven") == 7


# --- a number in a unit we hold no field in ----------------------------
#
# The subject matcher works on words, and the words that name a field appear in
# sentences that are about something else entirely. What separates them is what
# the number is measured in.


def test_an_offset_in_inches_is_not_a_cap_on_dwelling_units() -> None:
    # Gresham's middle-housing design chapter, verbatim. Read as evidence it
    # put a twelve-unit maximum on eleven zones, quoted to a facade rule.
    assert candidates_in(
        "Provide an offset between dwelling units of at least 12 inches; or", 423, DOC
    ) == []


def test_punctuation_between_the_number_and_its_unit_does_not_hide_it() -> None:
    # Wood Village, verbatim. "forty-five" is respelled as a digit, so the
    # text after the first 45 is "(45) degrees" — an anchor tight to the
    # number reads a 45-unit maximum out of a rule about which way a door
    # faces, and writes it onto two zones.
    assert candidates_in(
        "All street-facing units shall have the main entry facing the street "
        "or be at an angle of up to forty-five (45) degrees from the street.",
        64,
        DOC,
    ) == []


def test_a_number_a_formula_produced_is_not_a_standard() -> None:
    # Gresham prints its density equation as text, and the words on the left
    # of it name a field. The 1 became a one-unit cap on a multi-family zone,
    # which turns every lot in it red.
    assert candidates_in(
        "Number of Proposed Dwelling Units + Proposed Commercial Floor Area ≥ 1",
        519,
        DOC,
    ) == []


def test_a_density_is_not_a_maximum_number_of_units() -> None:
    """"Units per acre" names the same field words as a unit cap and states a
    different kind of thing: 24 units per acre is not 24 units. It used to be
    refused outright, because no field held a rate. Two fields do now, so the
    number is read for those two and still refused for everything else."""
    got = candidates_in("The maximum density is 24 units per acre.", 12, DOC)
    assert [(c.field, c.value) for c in got] == [("max_density_du_per_acre", 24)]

    # The trap it was written for, unchanged. Gresham's middle-housing design
    # chapter puts "dwelling units" beside a 12 in a sentence about an offset,
    # and a reader that took it would cap eleven zones at twelve units.
    assert (
        candidates_in(
            "Provide an offset between dwelling units of at least 12 inches.", 12, DOC
        )
        == []
    )


def test_a_height_in_storeys_is_not_a_height_in_feet() -> None:
    assert candidates_in("Maximum building height is 3 stories.", 14, DOC) == []


def test_the_unit_it_does_model_still_reads() -> None:
    # The refusal is a list, not a rule that a number needs a unit at all —
    # half the corpus states them bare under a heading that carries the unit.
    found = candidates_in("Maximum building height is 35 feet.", 15, DOC)

    assert [c.value for c in found] == [35]


def test_both_ends_of_a_density_are_read_and_neither_is_guessed() -> None:
    """The reader was blind to every density in the corpus: "units per acre"
    was listed as a unit no field is held in, so eight jurisdictions' density
    values were hand-encoded and nothing cross-checked them. Two fields hold a
    rate now.

    Both ends are named explicitly. A row headed "Density" alone does not say
    which end it is, and a guess puts a floor on the field that holds
    ceilings."""
    def read(text: str) -> list[tuple[str, float]]:
        return [(c.field, c.value) for c in candidates_in(text, 1, DOC)]

    assert read(
        "A. The minimum net density in the R-2 district shall be 17.4 "
        "dwelling units per acre."
    ) == [("min_density_du_per_acre", 17.4)]
    assert read(
        "B. The maximum net density in the R-2 district shall be 21.8 "
        "dwelling units per acre."
    ) == [("max_density_du_per_acre", 21.8)]
    assert read("Maximum Density (dwelling units per acre)  21.8") == [
        ("max_density_du_per_acre", 21.8)
    ]
    assert read("Density  8.7 units per acre") == [], "which end is not stated"


def test_a_zone_designation_is_a_name_and_not_a_number() -> None:
    """"The minimum net density in the R-2 district shall be 17.4 dwelling
    units per acre" states one number and names another. Read as evidence the
    name becomes a two-unit density on the very field the sentence is about --
    a value the document supposedly states twice, which is a disagreement
    invented by the reader rather than found in the code."""
    got = candidates_in(
        "A. The minimum net density in the R-2 district shall be 17.4 "
        "dwelling units per acre.",
        1,
        DOC,
    )
    assert [(c.field, c.value) for c in got] == [("min_density_du_per_acre", 17.4)]

    decimal = candidates_in(
        "The minimum lot size in the R-3.5 district is 3,500 square feet.", 1, DOC
    )
    assert [(c.field, c.value) for c in decimal] == [("min_lot_sqft", 3500)]

    # Case-sensitive, because an outline marker is not a zone.
    outline = candidates_in("a-1. The minimum front setback is 10 feet.", 1, DOC)
    assert [(c.field, c.value) for c in outline] == [("setback_front_ft", 10)]
