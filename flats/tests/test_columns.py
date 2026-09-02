"""A number can be on the cited line and still be the wrong number.

Gresham Table 4.0130 G.1 prints ``16 ft. / 16 ft. / 16 ft. / None / None /
16 ft. / None`` across seven districts, and 16 had been encoded for all six of
the ones we hold. Every check in the corpus passed, because they all ask
whether the number appears on the quoted line and it appears three times. The
question nobody was asking is which column it appears in.

These tests cover the check that now asks it, and -- more importantly -- cover
the check *itself* going blind. A reader that stops finding rows reports a
clean corpus in exactly the same words as a corpus that is clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.columns import Survey, reach, survey

pytestmark = pytest.mark.unit

#: What the check could read on 2026-09-02. A floor, not a target: encoding
#: more tables should raise it. It dropping is the failure that matters -- it
#: means the reader stopped seeing rows, and a blind reader reports every
#: corpus clean.
#:
#: It has gone blind twice already, both times saying only "0 disagree". The
#: first version read 29 citations, missing Happy Valley entirely because its
#: layer keys R40 where its table prints R-40, and missing every table whose
#: header carries its own row-label cell. The second compared numbers only, so
#: "None" was invisible to it -- it would have walked past the misread it was
#: written for.
REACH = 518

#: Of what it reaches, how much it can actually compare. Far below ``REACH`` on
#: purpose: two citations in three name a footnote or a second row beside the
#: cell, and those are left alone rather than judged against a cell the corpus
#: deliberately overrode.
JUDGED = 150


@pytest.fixture(scope="module")
def got() -> Survey:
    return survey()


def test_no_encoded_number_sits_in_another_districts_column(got: Survey) -> None:
    assert [str(row) for row in got.mismatches] == []


def test_no_number_is_encoded_where_the_cell_states_no_standard(got: Survey) -> None:
    assert [str(row) for row in got.vacancies] == []


def test_the_check_has_not_gone_blind(got: Survey) -> None:
    # The failure this guards is silence. Change an extractor so its tables no
    # longer print one cell per column, or rename a district so it stops
    # matching its own header, and every assertion above passes on nothing.
    assert got.reached >= REACH, (
        f"the column check now reads {got.reached} citations, down from {REACH}"
    )
    assert got.judged >= JUDGED, (
        f"the column check now judges {got.judged} of them, down from {JUDGED}"
    )


# --- the check against itself -------------------------------------------
#
# A four-line document and a five-line layer. Without these, a passing suite
# proves only that the corpus and a reader that reads nothing are
# indistinguishable.


def _corpus(
    tmp_path: Path,
    row: str,
    encoded: str,
    *,
    spec: str = "L3",
    tail: str = "",
) -> tuple[Path, Path]:
    docroot = tmp_path / "docs"
    configroot = tmp_path / "config"
    doc = docroot / "or" / "x" / "city" / "table.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "  Table 1: Development Requirements\n"
        "                    A-1        B-2        C-3\n"
        f"{row}\n"
        f"{tail}\n",
        encoding="utf-8",
    )
    layer = configroot / "or" / "x" / "city.yaml"
    layer.parent.mkdir(parents=True)
    layer.write_text(
        "zones:\n"
        "  B-2:\n"
        "    min_frontage_ft:\n"
        f"      {encoded}\n"
        f'      quote: "or/x/city/table.txt#{spec}"\n',
        encoding="utf-8",
    )
    return configroot, docroot


TOWNHOUSE = "        Townhouse   16 ft.     None       16 ft."


def test_it_catches_a_number_taken_from_the_column_next_door(tmp_path: Path) -> None:
    configroot, docroot = _corpus(tmp_path, TOWNHOUSE, "value: 16")
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.mismatches == ()
    assert len(found.vacancies) == 1
    bad = found.vacancies[0]
    assert (bad.zone, bad.encoded, bad.cell) == ("B-2", "16", "None")
    assert "its own column reads 'None'" in str(bad)


def test_it_passes_the_same_row_read_correctly(tmp_path: Path) -> None:
    configroot, docroot = _corpus(tmp_path, TOWNHOUSE, "exempt: true")
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.mismatches == ()
    assert found.vacancies == ()


def test_a_wrong_number_is_a_different_finding_from_an_absent_one(
    tmp_path: Path,
) -> None:
    configroot, docroot = _corpus(
        tmp_path, "        Townhouse   16 ft.     45 ft.     16 ft.", "value: 16"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert len(found.mismatches) == 1
    assert found.vacancies == ()
    assert found.mismatches[0].cell == "45 ft."


def test_a_row_with_dropped_blanks_is_skipped_rather_than_guessed(
    tmp_path: Path,
) -> None:
    # The row prints two cells where the header has three columns, because the
    # extractor dropped an empty one. Which one is gone decides what B-2's
    # number is, and nothing on the line says. Counting from the left here
    # would produce a confident finding out of a coin flip.
    configroot, docroot = _corpus(
        tmp_path, "        Townhouse   16 ft.     16 ft.", "value: 99"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 0
    assert found.mismatches == ()


def test_zero_is_not_an_exemption(tmp_path: Path) -> None:
    # A cell reading "0 ft." states a standard of zero, which a lot can fail to
    # meet in principle and which the screen measures against. "None" states no
    # standard at all. Reading the first as the second is the one direction
    # that can green a lot the city would refuse.
    configroot, docroot = _corpus(
        tmp_path, "        Townhouse   16 ft.     0 ft.      16 ft.", "exempt: true"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert len(found.mismatches) == 1
    assert found.mismatches[0].cell == "0 ft."


def test_a_citation_that_reaches_past_the_table_is_left_alone(
    tmp_path: Path,
) -> None:
    """The second line named is usually where the real number is.

    Gresham CC's maximum front setback is "10 feet" in the cell and five feet
    by note 3c on every street class this screen cannot read; Happy Valley's
    lot width is "100 feet" in the cell and exempt by note 2 four hundred lines
    down. Both encodings are right and neither matches its own cell. Judging
    them against the cell reports the footnote as a misreading, so a citation
    that quotes the override is not judged at all -- and what stays judged is
    the citation naming the row and nothing else, which is the shape the
    townhouse frontage misread had.
    """
    configroot, docroot = _corpus(
        tmp_path,
        TOWNHOUSE,
        "value: 5",
        spec="L3,L4",
        tail="        1. Note: five feet where the street is a Collector.",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.mismatches == ()
    assert found.vacancies == ()


def test_a_wrapped_cell_is_not_judged_on_the_line_it_starts(tmp_path: Path) -> None:
    # Portland prints a density as "1 unit per" / "1,450 sq. ft. of" / "site
    # area" down three lines. The figure is not on the row the citation names,
    # and reading the leading "1" would report every density in the city wrong.
    configroot, docroot = _corpus(
        tmp_path,
        "        Density     1 unit per 2,500   1 unit per     1 unit per 900",
        "value: 1450",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.judged == 0
    assert found.mismatches == ()


def test_reach_is_the_same_number_the_survey_reports(got: Survey) -> None:
    assert reach() == got.reached
