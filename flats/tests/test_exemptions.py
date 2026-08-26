"""The exemption ledger: does the cited page say the standard is not there?

``exempt: true`` is the only value in this corpus that can produce a false
GREEN with no lot-level margin to soften it. Every other number can be a
little wrong; an exemption is either right or the standard it removed was
real. So the assertion worth making is not that the readings are correct --
nothing automatic can judge a reading -- but that a reviewer opening the
citation would find the exemption there.

Two ratchets, and they do different jobs. The counts move deliberately, the
way the refusal ledger's do. The marker count does not move at all.
"""

from __future__ import annotations

import pytest

from flats.encode.exemptions import ORDER, counts, exemptions, survey, verdict
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

#: As of 2026-08-26. These are meant to move -- what they are not meant to do
#: is move quietly. An exemption added with a citation nobody can read the
#: exemption out of is the false GREEN this whole ledger exists to catch, and
#: it should cost a line here on the way in.
#:
#: ``numeric`` is 25 and every one of them was read on 2026-08-26. They fall
#: into two shapes, and neither turned out to be a standard somebody missed:
#:
#: * *the header came along with the cell.* Oregon zoning tables print three
#:   districts on one printed line, so a citation has to quote the header to
#:   say which column a figure came from -- and that drags the other two
#:   columns' figures in with it. Happy Valley's six density rows are this,
#:   and so are Gresham's four minimum density rows and Wood Village's two.
#: * *exemption by omission.* The section states every standard it has and the
#:   one in question is not among them. Fairview's six, Portland's three,
#:   Troutdale's two and Wilsonville's two are this shape, and no text match
#:   can ever close them: there is no sentence to find, which is the point.
#:
#: They stay counted anyway. The bucket means "a reviewer has to read this",
#: and next time one of them will not be innocent.
#:
#: ``marker`` fell 7 -> 0 the same day. See the test below.
EXPECTED = {"stated": 166, "numeric": 25, "marker": 0, "dash": 2, "silent": 0}

LAKE_OSWEGO = "or/clackamas/lake-oswego"


@pytest.fixture(scope="module")
def rows():
    return survey()


def test_the_ledger_sees_every_exemption_in_the_corpus(rows) -> None:
    assert counts(rows) == EXPECTED
    assert len(rows) == sum(EXPECTED.values())


def test_no_citation_in_this_corpus_points_at_a_footnote_marker(rows) -> None:
    """The one count that stays at zero.

    A citation resolving to ``[2]`` and nothing else is a pointer to a
    pointer. Every one of Lake Oswego's density exemptions was one: the note
    one line below states "Duplexes, triplexes, quadplexes, and cottage
    clusters are exempt from maximum density standards", in as many words, and
    no reviewer signing the card could have seen it. Seven values and five
    ``quadplex_allowed`` variants cited the marker line; the fix was to widen
    the span by one line, which is also how R-W was already written.

    Nothing else in the corpus does this, so the floor is zero rather than a
    number to be walked down.
    """
    marked = [r for r in rows if r.verdict == "marker"]
    assert marked == [], [r.label for r in marked]


def test_lake_oswego_cites_the_note_rather_than_the_number_beside_it(rows) -> None:
    """The fix, from the reader's end: open any of those citations now and the
    exemption is in the text."""
    lo = [r for r in rows if r.layer == LAKE_OSWEGO and r.field == "max_density_du_per_acre"]
    stated = [r for r in lo if r.verdict == "stated"]

    assert len(lo) == 10, [r.label for r in lo]
    assert len(stated) == 8, [r.label for r in lo if r.verdict != "stated"]
    # Against the store rather than the row's own text, which is trimmed to
    # something a terminal can print and drops the sentence past 300 chars.
    store = ProvenanceStore()
    for row in stated:
        assert "exempt from maximum density" in store.quote(row.quote), row.label


def test_the_two_that_are_not_stated_are_cells_holding_an_em_dash(rows) -> None:
    """R-2 and R-6 carry no footnote marker at all. Their Maximum (units/acre)
    cell is an em dash, which is how these tables print "no standard here" --
    real evidence, and evidence no regular expression can tell apart from an
    extraction that dropped a number. Counted in its own bucket rather than
    waved through or reported as broken."""
    dashes = {r.zone for r in rows if r.verdict == "dash"}

    assert dashes == {"R-2", "R-6"}
    for row in (r for r in rows if r.verdict == "dash"):
        assert row.layer == LAKE_OSWEGO
        assert row.field == "max_density_du_per_acre"


def test_a_layer_reports_only_its_own(rows) -> None:
    lo = exemptions(load_rules()[LAKE_OSWEGO])

    assert {r.layer for r in lo} == {LAKE_OSWEGO}
    assert len(lo) == len([r for r in rows if r.layer == LAKE_OSWEGO])


# --- the classifier -----------------------------------------------------


@pytest.mark.parametrize(
    "text,want",
    [
        ("None", "stated"),
        ("There is no required minimum lot size for development of land", "stated"),
        ("Quadplexes are exempt from maximum density standards.", "stated"),
        ("This subsection does not apply to middle housing.", "stated"),
        ("DLA is not the minimum lot area required per dwelling unit.", "stated"),
        ("This subsection applies only to properties in the Historic District.", "stated"),
        ("Single Detached,     1.0     0.7     NA     NA", "stated"),
        ("Townhome maximum density (units per net acre)   17.4 du/net acre", "numeric"),
        ("[2]", "marker"),
        ("[2],[3]", "marker"),
        ("(4)", "marker"),
        ("—", "dash"),
        ("Development standards for the district.", "silent"),
    ],
)
def test_the_classifier_reads_a_line_the_way_a_reviewer_would(text, want) -> None:
    assert verdict(text) == want


def test_a_span_takes_the_worst_line_in_it_and_stated_answers_for_the_rest() -> None:
    """One line stating the exemption settles the span -- that is a reviewer
    finding the answer. Failing that, a printed figure outranks a dash,
    because a figure is the one that could be a standard nobody noticed."""
    assert verdict("Maximum (units/acre)\n[2]\nQuadplexes are exempt") == "stated"
    assert verdict("Maximum (units/acre)\n17.4 du/net acre\n—") == "numeric"
    assert verdict("Maximum (units/acre)\n—") == "dash"
    assert ORDER.index("numeric") < ORDER.index("dash")


def test_a_cell_holding_a_bare_number_is_the_cell_and_not_a_marker() -> None:
    """The marker pattern requires brackets, and the requirement is load
    bearing. Without it "7,000" and "55" read as footnote references, which
    would have put forty-odd of Lake Oswego's, Milwaukie's and Fairview's
    perfectly good dimensional citations into the bucket reserved for
    citations that point at nothing."""
    assert verdict("7,000") == "numeric"
    assert verdict("55") == "numeric"
    assert verdict("15") == "numeric"


def test_na_is_matched_on_its_case_because_the_case_is_the_signal() -> None:
    """Gresham prints NA for four of seven districts on its floor area ratio
    row. A case-insensitive match for it would take the "na" out of half the
    words in a paragraph -- "national", "internal", "ordinance" -- and close
    every silent row in the corpus by accident."""
    assert verdict("Single Detached,   1.0   NA") == "stated"
    assert verdict("The national standard for internal ordinance drafting") == "silent"


def test_a_standard_is_not_an_exemption_however_negative_it_sounds() -> None:
    """The near misses, kept out on purpose. Each of these removes nothing."""
    for line in (
        "Residential density shall not exceed 45 units per acre.",
        "Buildings shall cover no more than 75 percent of each lot.",
        "The minimum density shall be no less than 20 units per net acre.",
    ):
        assert verdict(line) == "numeric", line
