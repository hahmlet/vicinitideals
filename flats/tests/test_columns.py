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
#: more aligned tables should raise it. It dropping is the failure that matters
#: -- it means the reader stopped seeing rows, and a blind reader reports every
#: corpus clean. It has already happened once: the first version read 29 rows
#: and pronounced the corpus clean, and the two things wrong with it were a
#: hyphen (Happy Valley keys R40 where its table prints R-40) and a header that
#: carries its own label cell. Both were invisible in the output, which said
#: only "0 disagree".
#:
#: It went the other way once too, on purpose. Widening it read 164, of which
#: seven were rows that had dropped a blank cell and were being indexed as
#: though they had not -- a shape the header, not the row's length, has to
#: settle. Skipping them costs seven and is the whole point.
REACH = 165


@pytest.fixture(scope="module")
def got() -> Survey:
    return survey()


def test_no_encoded_number_sits_in_another_districts_column(got: Survey) -> None:
    assert [str(row) for row in got.mismatches] == []


def test_the_check_has_not_gone_blind(got: Survey) -> None:
    # The failure this guards is silence. Change an extractor so its tables no
    # longer print one cell per column, or rename a district so it stops
    # matching its own header, and every assertion above passes on nothing.
    assert got.reached >= REACH, (
        f"the column check now reads {got.reached} citations, down from {REACH}"
    )


def test_most_of_what_it_reaches_it_can_also_judge(got: Survey) -> None:
    # The rest are cells of prose or a footnote pointer -- "Varies depending on
    # access" -- which belong to the footnote ledger rather than here. Pinned
    # as a share rather than a number so it does not have to be edited every
    # time a table is encoded, but low enough to notice the check quietly
    # turning into one that reads rows and judges none of them.
    assert got.judged >= got.reached // 2


# --- the check against itself -------------------------------------------
#
# Two fixtures, three lines each: a header, a row that agrees with what was
# encoded, and a row that does not. Without these, a passing suite proves only
# that the corpus and a reader that reads nothing are indistinguishable.


def _corpus(tmp_path: Path, row: str, encoded: str) -> tuple[Path, Path]:
    docroot = tmp_path / "docs"
    configroot = tmp_path / "config"
    doc = docroot / "or" / "x" / "city" / "table.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "  Table 1: Development Requirements\n"
        "                    A-1        B-2        C-3\n"
        f"{row}\n",
        encoding="utf-8",
    )
    layer = configroot / "or" / "x" / "city.yaml"
    layer.parent.mkdir(parents=True)
    layer.write_text(
        "zones:\n"
        "  B-2:\n"
        "    min_frontage_ft:\n"
        f"      {encoded}\n"
        '      quote: "or/x/city/table.txt#L3"\n',
        encoding="utf-8",
    )
    return configroot, docroot


def test_it_catches_a_number_taken_from_the_column_next_door(tmp_path: Path) -> None:
    configroot, docroot = _corpus(
        tmp_path,
        "        Townhouse   16 ft.     None       16 ft.",
        "value: 16",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert len(found.mismatches) == 1
    bad = found.mismatches[0]
    assert (bad.zone, bad.encoded, bad.cell) == ("B-2", "16", "None")
    assert "its own column reads 'None'" in str(bad)


def test_it_passes_the_same_row_read_correctly(tmp_path: Path) -> None:
    configroot, docroot = _corpus(
        tmp_path,
        "        Townhouse   16 ft.     None       16 ft.",
        "exempt: true",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.mismatches == ()


def test_a_row_with_dropped_blanks_is_skipped_rather_than_guessed(
    tmp_path: Path,
) -> None:
    # The row prints two cells where the header has three columns, because the
    # extractor dropped an empty one. Which one is gone decides what B-2's
    # number is, and nothing on the line says. Counting from the left here
    # would produce a confident finding out of a coin flip.
    configroot, docroot = _corpus(
        tmp_path,
        "        Townhouse   16 ft.     16 ft.",
        "value: 99",
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
        tmp_path,
        "        Townhouse   16 ft.     0 ft.      16 ft.",
        "exempt: true",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert len(found.mismatches) == 1
    assert found.mismatches[0].cell == "0 ft."


def test_reach_is_the_same_number_the_survey_reports(got: Survey) -> None:
    assert reach() == got.reached
