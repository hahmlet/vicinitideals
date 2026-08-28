"""A legend standing in front of the notes, and the eight it was hiding.

Milwaukie's use tables print "Notes:", then a key to the permission codes -- "P
= Permitted.", "CSU = Permitted with Community Service Use approval subject to
provisions of Section 19.904." -- and then, underneath that, the footnotes. The
block reader demanded a number directly under the heading and walked away from
all eight of Table 19.303.2's.

The demand is right and stays. A "Notes:" heading in this corpus sits over a
legend far more often than over notes, and reading a legend as a block would
invent footnotes in half the documents here. So a legend line is stepped over
rather than believed: it accumulates no bodies, and a heading followed by a
legend and nothing else is still refused.

What that opened, and what closed it again: three of Milwaukie's legends end
with a section heading, and a section heading is furniture by the same rule
that skips running page headers -- so the block walked out of its own table and
read the next subsection's "A." as a note. Nothing may come between a legend
and the note it stands in front of.
"""

from __future__ import annotations

import pathlib

import pytest

from flats.encode.footnotes import (
    HEADLESS_NOTE,
    LEGEND_CODE,
    LEGEND_LINE,
    census,
)
from flats.encode.dispositions import notes as dispositions
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"
DOC = f"{MILWAUKIE}/19.300.base-zones.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def base_zones(store: ProvenanceStore):
    return census(store.load(DOC).text, layer=MILWAUKIE, doc=DOC)


# --- stepping over the legend ----------------------------------------------


def test_a_legend_may_stand_between_the_heading_and_note_one() -> None:
    seen = census(
        "\n".join(
            [
                "Townhouse                        P        P",
                "Notes:",
                "P       =       Permitted.",
                "N       =       Not permitted.",
                "CU      =       Permitted with conditional use approval.",
                "1.",
                "The limit of 4 consecutive townhouses does not apply in GMU.",
                "2.",
                "Day care uses are limited to 5,000 sq ft.",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1", "2"]


def test_a_legend_on_its_own_is_still_not_a_block() -> None:
    """Stepped over, not believed. Nothing numbered follows, so nothing is
    accumulated and the heading is refused exactly as before."""
    seen = census(
        "\n".join(
            [
                "Notes:",
                "P       =       Permitted/allowed by right",
                "N       =       Not permitted.",
                "III     =       Type III review required.",
            ]
        ),
        doc="d.txt",
    )
    assert seen.blocks == ()


def test_a_section_heading_after_the_legend_ends_it() -> None:
    """Milwaukie's § 19.301.3 sits between the legend and the next
    subsection's lettered paragraphs. Furniture is skipped everywhere else in
    a block; here it has to stop the reading, or the block leaves its table
    and reads "A. Agricultural or horticultural uses" as note A."""
    seen = census(
        "\n".join(
            [
                "Notes:",
                "P       =       Permitted/allowed by right",
                "N       =       Not permitted.",
                "§ 19.301.3. Use Limitations and Restrictions.",
                "A.",
                "Agricultural or horticultural uses are permitted, provided"
                " that the following conditions are met.",
                "B.",
                "Marijuana production is not permitted except as follows:",
            ]
        ),
        doc="d.txt",
    )
    assert seen.blocks == ()


def test_the_legend_shape() -> None:
    assert LEGEND_LINE.match("P       =       Permitted.")
    assert LEGEND_LINE.match("CSU     =       Permitted with approval")
    assert LEGEND_LINE.match("N = Not permitted.")
    assert not LEGEND_LINE.match(
        "The following describe limitations on use categories"
    )
    assert not LEGEND_LINE.match("1. Day care uses are limited to 5,000 sq ft.")
    assert not LEGEND_LINE.match("Minimum lot area = 3,000 square feet")


def test_a_numbered_subsection_is_not_a_headless_note() -> None:
    """The tempting way to reach Milwaukie's other two notes, and the reason
    it is refused. "1.  Properties in the MUTSA have a maximum front yard
    setback of 10 ft" is a real note printed with a period and a column gap --
    but so is every numbered subsection in this corpus, and admitting the
    shape turned twelve hundred of them into footnote bodies across
    twenty-eight documents."""
    assert HEADLESS_NOTE.match("1  Minimum lot size for single detached dwelling")
    assert not HEADLESS_NOTE.match(
        "1.  Properties in the MUTSA have a maximum front yard setback of 10 ft"
    )


# --- the legend the extraction pulled apart --------------------------------


def test_a_legend_may_arrive_one_part_per_line() -> None:
    """Milwaukie's second use table prints the code, the equals sign and the
    definition on three lines each, and then its four notes."""
    seen = census(
        "\n".join(
            [
                "Notes:",
                "P",
                "=",
                "Permitted.",
                "CSU",
                "=",
                "Permitted with community service use approval.",
                "1.",
                "Multifamily residential is permitted outright in a"
                " stand-alone building.",
                "2.",
                "All activities related to trade schools must be conducted"
                " inside an enclosed building.",
            ]
        ),
        doc="d.txt",
    )
    assert [b.mark for b in seen.bodies] == ["1", "2"]


def test_a_bare_code_needs_the_equals_sign_under_it() -> None:
    """A lone "P" is a permission cell in every use table in this corpus. The
    equals sign on the next line of its own is what no cell is."""
    seen = census(
        "\n".join(
            [
                "Notes:",
                "P",
                "P",
                "N",
                "1.",
                "Day care uses are limited to 5,000 sq ft.",
            ]
        ),
        doc="d.txt",
    )
    assert seen.blocks == ()
    assert LEGEND_CODE.match("CSU")
    assert LEGEND_CODE.match("III")
    assert not LEGEND_CODE.match("Permitted")
    assert not LEGEND_CODE.match("P = Permitted")


def test_the_second_use_table_answers_its_own_four(base_zones) -> None:
    block = next(b for b in base_zones.blocks if b.head == 3785)
    assert [b.mark for b in block.bodies] == ["1", "2", "3", "4"]


# --- what Milwaukie says now ------------------------------------------------


def test_the_use_table_answers_its_own_eight(base_zones) -> None:
    block = next(b for b in base_zones.blocks if b.head == 911)
    assert [b.mark for b in block.bodies] == [str(n) for n in range(1, 9)]


def test_the_lettered_subsections_are_not_blocks(base_zones) -> None:
    """51, 424 and 1571 are legends whose next content is a section heading.
    Read as blocks they contributed marks A, B and C from the subsections
    below them."""
    assert sorted(b.head for b in base_zones.blocks) == [
        279,
        509,
        911,
        1070,
        3785,
    ]


def test_the_orphans_the_blocks_were_hiding(base_zones) -> None:
    """Twenty-nine markers on two use tables had no body in their region --
    Commercial[3,4] and Vehicle sales and rentals[5] on the first,
    Residential[1] and Waste management[4] on the second. Four are left, and
    they are honest: all four sit in one development standards table whose
    notes are printed in the shape this reader still refuses. See the
    subsection test above.

    Two of the four arrived with `flats-html-text/7`, which stopped welding a
    superscript to the number under it. "10-30[1]" is a maximum front yard
    setback of ten to thirty feet under note 1; the store used to hold
    "10-301", where the marker was invisible and the range was wrong.
    """
    assert [m.line for m in base_zones.unbodied] == [3924, 3925, 3927, 3928]


def test_the_four_consecutive_townhouse_limit(base_zones) -> None:
    """Note 1 lifts a limit in one zone, which is the code saying the limit
    exists in the others. 19.505.5 prints it twice -- no more than 4
    consecutive townhouses in the High Density Zone, a maximum of 4 in R-MD --
    and the pod is exactly four attached units."""
    first = next(b for b in base_zones.bodies if b.line == 921)
    assert "limit of 4 consecutive townhouses" in first.text
    assert "does not apply in the GMU Zone" in first.text


def test_the_high_density_side_yard_quotes_both_paragraphs() -> None:
    """Table 19.302.4 prints no side yard number: it reads "See Subsection
    19.302.5.A", and that subsection is two paragraphs. The 5 ft was quoted
    from the one that begins "for development other than a townhouse"."""
    text = pathlib.Path(
        "flats/config/jurisdictions/or/clackamas/milwaukie.yaml"
    ).read_text(encoding="utf-8")
    assert f'"{DOC}#L526,L530"' in text


def test_every_new_note_is_ruled_and_none_blocks() -> None:
    ruled = {row.quote: row for row in dispositions(MILWAUKIE)}
    for line in (921, 923, 925, 927, 929, 931, 933, 935, 3809, 3812, 3819, 3822):
        assert ruled[f"{DOC}#L{line}"].state == "dismissed"
    assert not [row for row in qualified() if row.blocking]
