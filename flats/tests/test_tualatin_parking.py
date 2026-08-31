"""The chapter that points at a drawing, and the drawing that answers.

Clackamas County's parking geometry is refused because ZDO 1015.02(A)(4) hands
stall depth and aisle width to the Roadway Standards, 320.3(a) hands them to
Standard Drawings P100 and P200, and both sheets carry 69 characters of text
apiece -- the title block -- with every dimension drawn. Tualatin writes the
same sentence. TDC 73C.030(1): off-street parking lot design "must comply with
the dimensional standards set forth in Figure 73-1", and Figure 73-1 lives in
Appendix B at the back of the code rather than in the chapter.

It answers. The figure is two grids of numbers and they extract whole, which is
the difference between a code that publishes a table as a picture and one that
publishes it as a table. Nine by eighteen and a half, a 24-foot aisle, a 22-foot
drive.

Three other things this reading settles. TUALATIN NAMES THE BUILDING: 73C.090's
driveway rule reaches "single-family residential uses and middle housing types
(duplexes, triplexes quadplexes, townhouses, and cottage clusters)", so for once
no noun has to be argued for. IT REQUIRES NOTHING AND CAPS NOTHING: Table 73C-1
has no minimum column for vehicles at all, and prints None in both maximum
columns of the row that lists Quadplexes -- Fairview's shape, from a chapter
that Ordinance 1486-24 rewrote whole in June 2024. AND THE ONE RULE THAT WOULD
HAVE HURT DOES NOT REACH: 73C.220 sets parking ten feet off every property line
and ten feet off the building, but it governs "Multi-family residential uses (as
defined in TDC 31.060)", and TDC 31.060 defines a Multi-Family Structure as "A
structure containing five or more dwelling units on one lot".
"""

from __future__ import annotations

import pytest

from flats.encode.refusals import refusals
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

TUALATIN = "or/clackamas/tualatin"
PARKING = "or/clackamas/tualatin/73C.parking.txt"
FIGURES = "or/clackamas/tualatin/appendix-b.figures.txt"
DEFINITIONS = "or/clackamas/tualatin/31.definitions.txt"
ZONES = "or/clackamas/tualatin/40-41.residential.txt"


@pytest.fixture(scope="module")
def tualatin() -> Layer:
    return load_rules()[TUALATIN]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _lines(store: ProvenanceStore, path: str) -> list[str]:
    return store.load(path).text.splitlines()


# -- the drawing that answers -------------------------------------------------


def test_the_chapter_states_no_dimension_of_its_own(store: ProvenanceStore) -> None:
    """73C.030(1) is a pointer, and the whole chapter is a pointer.

    Not one of the four numbers this screen needs is printed in the words of
    Chapter 73C. The stall, the aisle and the two driveway widths are all in
    Figure 73-1, and the chapter's only job is to say so.
    """
    text = store.load(PARKING).text
    assert "dimensional standards set forth in Figure 73-1." in text
    for absent in ("18.5", "nine feet", "24-foot aisle"):
        assert absent not in text, f"{absent!r} turned up in the chapter after all"


def test_the_figure_carries_its_numbers_as_text(store: ProvenanceStore) -> None:
    """The difference between this and Clackamas County's P100.

    Both codes send a reader to a drawing. One drawing yields 69 characters and
    a title block; this one yields two complete dimension grids. The 90-degree
    column is the last of each row, because the header runs 0/parallel, 45, 60,
    75, 90.
    """
    lines = _lines(store, FIGURES)
    assert lines[25].strip() == "Parallel 45º 60º 75º 90º"
    assert lines[26].split() == ["Stall", "Width", "A", "8.0", "9.0", "9.0", "9.0", "9.0"]
    assert lines[27].split() == ["Stall", "Depth", "B", "24.0", "17.5", "19.0", "19.5", "18.5"]
    assert lines[28].split() == ["Aisle", "Width", "C", "N/A", "12.0", "16.0", "23.0", "24.0"]


def test_the_larger_grid_is_taken_and_the_error_runs_the_safe_way(
    tualatin: Layer, store: ProvenanceStore
) -> None:
    """Which grid is the standard space is drawn into the figure, not written.

    So it is chosen on the direction of the error: the larger rectangle is the
    stricter screen, and a lot that lays out four 9 x 18.5 stalls with a
    24-foot aisle lays out on the smaller grid too. This pins that the encoded
    numbers are the larger grid's and not the smaller's -- if a later reading
    finds the captions and they run the other way, nothing false was published,
    but this test has to be the thing that says so.
    """
    d = tualatin.defaults
    assert (d["parking_stall_width_ft"].value, d["parking_stall_depth_ft"].value) == (9, 18.5)
    assert d["parking_aisle_two_way_ft"].value == 24

    lines = _lines(store, FIGURES)
    smaller = lines[39].split()
    assert smaller[3:] == ["8.0", "8.0", "8.0", "8.0", "8.0"]
    assert lines[40].split()[-1] == "16.0"
    assert lines[41].split()[-1] == "20.0"


def test_what_identifies_the_grids_as_figure_73_1_is_in_the_document(
    store: ProvenanceStore,
) -> None:
    """The captions are images; the evidence for the caption is not.

    Appendix B lists its figures in order and 73-1 sits between 71-1 and 73-3.
    The grids sit on TDB:5 and TDB:6, between Figure 71-1's caption on TDB:4
    and Figure 73-3's after them, and they carry Ord. 1486-24 section 17 --
    the same June 2024 ordinance that enacted Chapter 73C. Three independent
    things, all of them in the stored text.
    """
    lines = _lines(store, FIGURES)
    assert lines[0] == "Figure 73-1: Parking Space Design Standards"
    assert lines[1] == "Figure 73-3: Tree Canopy Coverage"
    assert lines[17:19] == ["Figure 71-1", "Development Setbacks"]
    assert lines[20] == "TDB:5Supp. No. 11"
    assert lines[46] == "(Ord. No. 1486-24, § 17, 6-10-24)"
    assert lines[48] == "TDB:6Supp. No. 11"
    assert lines[50].strip() == "Figure 73-3: Tree Canopy Coverage"


# -- required, capped, and the difference -------------------------------------


def test_nothing_is_required_and_nothing_is_capped(tualatin: Layer) -> None:
    """Fairview's shape, out of a chapter rewritten in June 2024.

    Table 73C-1's heading is MAXIMUM PERMITTED VEHICLE PARKING and the only
    minimums in it are for bicycles, so a zero here is the absence of a column
    rather than a printed zero -- which is why it is encoded rather than left
    out. Left out, the state's cap on what a city may REQUIRE resolves alone
    and stands in for a requirement Tualatin does not have.
    """
    d = tualatin.defaults
    assert d["parking_min_per_unit"].value == 0
    assert d["parking_max_per_unit"].exempt is True
    assert RuleSet(load_rules()).resolve(TUALATIN, "RL").get("parking_min_per_unit") == 0


def test_the_quadplex_row_is_the_middle_housing_row(store: ProvenanceStore) -> None:
    """Named, in a list, with None beside it in both maximum columns."""
    lines = _lines(store, PARKING)
    assert lines[153].strip() == "(ii) Middle Housing:"
    assert lines[156].strip() == "c. Quadplexes"
    assert lines[159].split() == ["None", "None", "None", "Required", "N/A"]
    assert lines[131].startswith("MAXIMUM PERMITTED VEHICLE PARKING")


def test_no_vehicle_parking_minimum_anywhere_in_the_code(store: ProvenanceStore) -> None:
    """An absence claim, checked against the words rather than the chapter.

    The whole Development Code is 21,780 lines and the only "spaces per unit"
    figures in it are Table 73C-1's multi-family maximums and the bicycle
    minimums beside them. What is checkable here is the chapter that would
    hold one: `per unit` appears in 73C only in the multi-family maximum row
    and the bicycle column.
    """
    text = store.load(PARKING).text
    assert text.count("spaces per unit") == 2  # 1.2 and 2.0, both maximums
    assert "space per unit" in text  # the bicycle minimum
    assert "1.2 spaces per unit" in text and "2.0 spaces per unit" in text


# -- the building is named ----------------------------------------------------


def test_the_driveway_rule_names_the_quadplex(
    tualatin: Layer, store: ProvenanceStore
) -> None:
    """No noun argued and no row chosen, which is a first in this corpus.

    Troutdale and Gladstone both turned on counting units in a definition, and
    unincorporated Multnomah on the same count running the other way. Tualatin
    lists the building: 73C.090(1)(a) reaches "middle housing types (duplexes,
    triplexes quadplexes, townhouses, and cottage clusters)", and the table
    under it starts at five dwelling units.
    """
    lines = _lines(store, PARKING)
    assert "middle housing types" in lines[532]
    assert "duplexes, triplexes quadplexes, townhouses, and cottage clusters" in lines[533]
    assert "minimum width of ten feet" in lines[534]
    assert "exceed 24 feet" in lines[535]
    assert "measured at" in lines[535]
    assert "the right-of-way line." == lines[536].strip()

    d = tualatin.defaults
    assert d["driveway_approach_min_width_ft"].value == 10
    assert d["driveway_approach_max_width_ft"].value == 24


def test_the_lane_and_the_cut_come_from_different_sections(tualatin: Layer) -> None:
    """The code separates them and says how: the cut is measured at the ROW.

    Figure 73-1's last two rows dimension the driveway inside a parking lot;
    73C.090 dimensions what meets the street. Taking 73C.090's ten-foot floor
    for the side lane would draw a court reached by a lane narrower than one
    car and two feet under the figure's own one-way number.
    """
    d = tualatin.defaults
    assert d["driveway_min_width_one_way_ft"].value == 12
    assert d["driveway_min_width_two_way_ft"].value == 22
    assert d["driveway_approach_min_width_ft"].value < d["driveway_min_width_one_way_ft"].value


# -- the rule that would have hurt --------------------------------------------


def test_multi_family_starts_at_five_so_73c_220_never_reaches(
    store: ProvenanceStore,
) -> None:
    """Two ten-foot rules turned off by one numbered definition.

    73C.220 asks for a 10-foot landscape setback between parking and every
    property line and a 10-foot landscaped transition between parking and the
    building. Either would take the rear court apart. It governs "Multi-family
    residential uses (as defined in TDC 31.060)" and TDC 31.060 counts to five.

    The one thing arguing the other way is in the section itself: its
    transition rule excepts duplexes and townhouses by name, which reads as
    though the section otherwise reached them. A numbered definition beats an
    exception list.
    """
    defs = _lines(store, DEFINITIONS)
    assert defs[250].startswith(
        "Multi-Family Structure. A structure containing five or more dwelling units on one lot."
    )
    parking = _lines(store, PARKING)
    assert parking[727].strip() == "TDC 73C.220.  Multi-family Residential Parking Lot Landscaping Requirements."
    assert "(as defined in TDC 31.060)" in parking[728]
    assert "Minimum 10-foot landscape setback" in parking[730]
    assert "Minimum 10-foot landscaped transition" in parking[736]
    assert "does not apply to Du-" in parking[745]


def test_the_setback_that_binds_is_rml_and_rml_holds_no_lots(tualatin: Layer) -> None:
    """The only parking setback in the city, and only half of it has a field.

    RL states ten feet inside its Conditional Uses row and a quadplex is
    permitted outright, so RL carries none. RML states the same ten feet as a
    row of its own, and it is measured from any lot line -- but the model holds
    only a setback from a street. RML's side yard is five, so the unheld half
    would bite five feet on each side.

    What makes that tolerable rather than a false green is that every one of
    Tualatin's 653 lots in the parcel universe is RL. This pins the shape, so
    that if RML ever gains a value here somebody has to come back to the
    refusal that says the city comes off the laid-out list.
    """
    assert "parking_street_setback_ft" not in tualatin.zones["RL"].values
    assert tualatin.zones["RML"].values["parking_street_setback_ft"].value == 10
    assert "parking_street_setback_ft" not in tualatin.defaults


def test_four_refusals_against_ten_values(tualatin: Layer) -> None:
    """Three landscaping rules and one setback, and only one of them bites.

    The five-foot planted perimeter is exactly the side yard in both zones and
    smaller than every other yard, so the envelope is already cut back that
    far. The tree canopy sits above a car rather than in its way. What is left
    is a hundred square feet of landscape island at the aisle ends, which is
    inside the court, and RML's unheld side and rear ten feet.
    """
    mine = [r for r in refusals() if r.kind == "comments" and r.where == TUALATIN]
    assert len(mine) == 4
    assert len(tualatin.defaults) == 10
