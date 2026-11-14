"""When a held section answers for a number it does not print (FOLLOWUPS 105 item 4).

The fetch queue in :mod:`flats.encode.crossrefs` used to resolve a reference
only when some held document printed that exact number at the start of a line.
So a subsection a code numbers locally ("7." under 60.05.15), Washington
County's hyphen numbering (431-8), a lettered part (12.61.700G), a range
(4.1531-4.1534) and a table caption all reported as chapters nobody had
fetched, while every one of them was in the store.

The fix is a set of narrow rules, and each one is tested twice: once on the
real reference that showed the gap, once on the nearest thing that must NOT
resolve. The second half matters more. A reference that resolves wrongly
hides an unread chapter, which is the failure this whole ledger exists to
prevent; a false "unfetched" only costs somebody a look.
"""

from __future__ import annotations

import pytest

from flats.encode.crossrefs import (
    _ancestors,
    _answers,
    _caption_at,
    _headings,
    _range,
    _resolves,
)
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

BEAVERTON = "or/washington/beaverton"
WASHINGTON = "or/washington/_unincorporated"
HILLSBORO = "or/washington/hillsboro"
GRESHAM = "or/multnomah/gresham"
TIGARD = "or/washington/tigard"
OREGON_CITY = "or/clackamas/oregon-city"
MULTNOMAH = "or/multnomah/_unincorporated"
SHERWOOD = "or/washington/sherwood"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _held(store: ProvenanceStore, layer: str):
    ids, headings = _answers(store, layer)
    return lambda ref, caption=None: _resolves(ref, ids, headings, caption)


# -- a section that numbers its parts locally --------------------------------


def test_a_subsection_printed_locally_is_held_with_its_section(store) -> None:
    """Beaverton's 60.05.15 prints its parts "1." to "9."; 60.05.15.7 is in it.

    20.05.15.txt line 66 points at "Standards of 60.05.15.7", and the section
    file 60.05/60.05.15.txt holds the text. The section's own "...of / Section
    60.05.15.3 by 25 percent." (line 232) is a wrapped reference, not the
    section numbering its parts in full, and does not count against it.
    """
    held = _held(store, BEAVERTON)
    assert held("60.05.15.7")
    assert held("60.05.25.16")


def test_but_not_where_the_level_is_printed_in_full(store) -> None:
    """Oregon City's 16.12 prints its sections "16.12.010", "16.12.016", ...

    So a 16.12.110 printed nowhere is a section the store does not have, not a
    part of 16.12 it holds silently. Same for Washington's 307-7, which prints
    307-7.1 and 307-7.2 and is cited for a 307-7.5 it does not contain.
    """
    assert not _held(store, OREGON_CITY)("16.12.110")
    assert not _held(store, WASHINGTON)("307-7.5")


def test_a_chapter_number_vouches_for_nothing_below_it(store) -> None:
    """A bare chapter is never the held number a part hangs from.

    Multnomah's 39.c-3.txt holds one zone and its name claims "39"; read as all
    of Chapter 39 it answered for 59 sections the store does not have, 39.9300
    (lot line adjustments) the loudest of them. And a printed "33.245, ..."
    opening a line of Portland text is a wrapped reference to the
    Inclusionary Housing chapter, which is not held: it may not answer for
    33.245.040 either.
    """
    held = _held(store, MULTNOMAH)
    assert not held("39.9300")
    assert not held("33.245.040")


def test_a_file_that_names_no_number_vouches_for_nothing(store) -> None:
    """Sherwood's 16.106/chapter-16.108.txt is two lines: "Sections:" and the title."""
    assert not _held(store, SHERWOOD)("16.108.060")


# -- hyphen numbering -------------------------------------------------------


def test_a_hyphen_numbered_subsection_is_a_heading_of_its_section() -> None:
    """cdc.431.transit-design.txt line 996: "431-8 Transitions in Density"."""
    text = "431-8 Transitions in Density\n431-8.1 Principles:\n"
    assert {"431-8", "431-8.1"} <= _headings(text, {"431"}, {"431"})


def test_but_a_sibling_s_number_is_not_one() -> None:
    """307-7.txt owns 307-7; a "305-3" opening one of its lines is someone else's."""
    assert "305-3" not in _headings("305-3 Dimensional Requirements\n", {"307-7"}, {"307-7"})


def test_washington_s_own_sections_resolve(store) -> None:
    held = _held(store, WASHINGTON)
    assert held("431-8")
    assert held("407-6")
    # 430-46 (flag lots) is a hyphen number, not a range "430 down to 46", and
    # no Section 430 is held beyond 430-84: still unfetched.
    assert _range("430-46") is None
    assert not held("430-46")


# -- a lettered part --------------------------------------------------------


def test_a_lettered_part_of_a_section_is_held_with_it(store) -> None:
    """Hillsboro 12.21.850: "See Subsection 12.61.700G." -- 12.61.700 is held."""
    assert _ancestors("12.61.700G")[0] == ("12.61.700", "")
    assert _held(store, HILLSBORO)("12.61.700G")


def test_but_a_lettered_chapter_is_a_chapter_of_its_own() -> None:
    """Tualatin's 73A is not part A of Chapter 73."""
    assert _ancestors("73A.170") == [("73A", ".")]
    assert not _resolves("73A.170", {"73"}, {"73", "held:73"})


# -- ranges -----------------------------------------------------------------


def test_a_range_resolves_when_every_member_is_held(store) -> None:
    """Gresham 4.1508: "Master Plan Requirements (Section 4.1531-4.1534)"."""
    assert _range("4.1531-4.1534") == ["4.1531", "4.1532", "4.1533", "4.1534"]
    assert _range("73A.020-060")[:2] == ["73A.020", "73A.021"]
    assert _held(store, GRESHAM)("4.1531-4.1534")


def test_and_not_when_one_member_is_missing(store) -> None:
    """4.1531 to 4.1535 are cut files; 4.1536 is in no document."""
    held = _held(store, GRESHAM)
    assert not held("4.1536")
    assert not held("4.1531-4.1536")


# -- table and figure captions ----------------------------------------------


def test_a_table_resolves_to_the_caption_the_store_prints(store) -> None:
    """Tigard 18.320.040.txt prints "Table 18.320.1" over its rows of setbacks.

    The same number is also Figure 18.320.1 (Building Projection Standards, in
    18.320.050), and a figure reference must not ride on the table's caption.
    """
    line = "Base zone site design standards are provided in Table 18.320.1. and Subsections"
    caption = _caption_at(line, line.index("18.320.1"))
    assert caption == "Table 18.320.1"
    held = _held(store, TIGARD)
    assert held("18.320.1", caption)
    assert not held("18.320.1", "Figure 18.320.1")


def test_every_number_in_a_list_of_figures_is_a_figure() -> None:
    line = "Refer to corresponding cross sections (Figures 18.910.3, 18.910.4 and 18.910.5)"
    assert _caption_at(line, line.index("18.910.5")) == "Figure 18.910.5"
    assert _caption_at("See Section 18.910.5.", 12) is None


def test_a_figure_caption_is_not_the_figure(store) -> None:
    """Beaverton 70.20.10.txt line 498 prints "Figure 70.20.10.6.2 Active
    Frontage Design Map". The map -- which streets are Type A -- is the one
    thing the corpus does not hold (FOLLOWUPS 105 item 1), and the figure sits
    under the held 70.20.10.6, so neither the caption nor the numbering may
    answer for it.
    """
    held = _held(store, BEAVERTON)
    assert not held("70.20.10.6.2", "Figure 70.20.10.6.2")
