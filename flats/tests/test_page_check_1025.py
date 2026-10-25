"""Steph's page-check round of 2026-10-25: each card she caught, pinned.

1063  the state's one approach for four homes boxed "more than four dwelling
      units", a line about something else; the 4 is printed nowhere.
1081  King City's stall width boxed the "9." of a heading as the 9 feet.
1087  King City's Pacific Highway held Sherwood's 61 feet; King City's code
      names 99W and leaves the figure to ODOT.
1097  King City's corner front showed only "a lot line that abuts a street",
      not the sentence that lets a lot have two.
1098  King City R-9's use card pointed at the chapter proof copy.

Each test reads the stored code text the card quotes, so a re-point that
drifts back to the wrong line fails here before Steph sees it again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.geom import dedication
from flats.rules.loader import load_rules
from flats.rules.model import _validate_street_table

pytestmark = pytest.mark.unit

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"
STATE = "or"
KING_CITY = "or/washington/king-city"


@pytest.fixture(scope="module")
def layers():
    return load_rules()


def lines(ref: str) -> list[str]:
    """The stored code lines a ``quote:`` or ``via:`` points at."""
    path, _, ranges = ref.partition("#")
    text = (DOCS / path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for part in ranges.split(","):
        start, _, end = part.lstrip("L").partition("-L")
        out += text[int(start) - 1 : int(end or start)]
    return out


def quoted(ref: str) -> str:
    return " ".join(" ".join(lines(ref)).split())


# --- 1063: one approach for four homes (OAR 660-046) -------------------------


def test_the_state_driveway_card_quotes_the_rule_not_the_four_unit_line(layers) -> None:
    held = layers[STATE].defaults["driveway_units_per_approach"]
    assert held.value == 4
    text = quoted(held.prov.quote)
    assert "driveways" in text
    assert "may not scale by the number of dwelling units" in text
    # The old box: a threshold for a different standard, read as the 4.
    assert "more than four dwelling units" not in text


# --- 1081: the stall width is the table's, not the heading's -----------------


def test_king_city_stall_width_quotes_the_table_and_its_sentence_is_the_via(layers) -> None:
    held = layers[KING_CITY].defaults["parking_stall_width_ft"]
    assert held.value == 9
    table = lines(held.prov.quote)
    assert table[0].startswith("Table 16.114-14")
    assert any(row.startswith("90") and "Standard" in row and "9.0 ft." in row for row in table)
    # The heading whose "9." was boxed is no longer in the quote...
    assert not any("Parking stall standard dimensions" in row for row in table)
    # ...it is the passage that sends the reader to the table.
    assert "in accordance with Table" in quoted(held.prov.via)


# --- 1087: Pacific Highway has no figure in King City's code -----------------


def test_king_city_holds_no_figure_for_pacific_highway(layers) -> None:
    held = layers[KING_CITY].defaults[dedication.NAMED_FIELD]
    table = dict((street, ft) for street, ft in held.value)
    assert table["Pacific Highway"] is None
    assert "61" not in held.prov.cite
    assert "as determined by the Oregon Department of Transportation" in quoted(held.prov.quote)


def test_a_street_named_without_a_figure_takes_the_deepest_not_the_other() -> None:
    rule = dedication.Rule(
        classes={}, class_by=None, named=(("BEEF BEND RD", 33.0),), other=25.0, unstated=("PACIFIC HWY",),
    )
    assert rule.required(["PACIFIC HWY"], {}) == 33
    assert rule.required(["MONARCH DR"], {}) == 25
    # A line that might be on either takes the deeper.
    assert rule.required(["PACIFIC HWY", "MONARCH DR"], {}) == 33


def test_a_street_table_may_hold_a_null_row_but_not_only_null_rows() -> None:
    _validate_street_table("t", [["Pacific Highway", None], ["Beef Bend Road", 33]])
    with pytest.raises(ValueError, match="without a figure"):
        _validate_street_table("t", [["Pacific Highway", None]])
    with pytest.raises(ValueError, match="non-negative"):
        _validate_street_table("t", [["Pacific Highway", -1]])


# --- 1097: a corner lot has two front lot lines -------------------------------


def test_king_city_corner_front_quotes_the_more_than_one_front_sentence(layers) -> None:
    held = layers[KING_CITY].defaults["front_lot_line_corner"]
    assert held.value == "both"
    text = quoted(held.prov.quote)
    assert "abuts a street" in text
    assert "more than one front lot line" in text


# --- 1098: R-9's use card reads the housing-type table ------------------------


def test_king_city_r9_use_card_quotes_the_section_not_the_chapter_copy(layers) -> None:
    held = layers[KING_CITY].zones["R-9"].values["quadplex_allowed"]
    assert held.value is False
    assert held.prov.quote.startswith("or/washington/king-city/16.84/16.84.010.txt#")
    assert "Multi-dwelling N P P P N P" in quoted(held.prov.quote)
