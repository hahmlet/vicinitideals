"""The last nine zones that let you build and never said how tall.

Third and final instalment of the gap the coverage ledger re-opened after 19
August. Wilsonville had seven, Happy Valley nine, and unincorporated Clackamas
these nine -- every one of them permitting a quadplex and stating no height, so
the screen was placing a 26 ft building against no ceiling and calling it a
pass. After this the only zone in the corpus still silent on height is
Wilsonville's OTR, which is silent on purpose.

Two tables answer all nine at 35 feet, and Section 845 -- which governs how a
quadplex is designed here -- states no height of its own, so the district table
is the whole of it.

The finding worth keeping is not about height. Reading these cells is what
surfaced that ``zdo.315.txt`` carried 305 footnote markers and zero bodies: the
worst unreconciled document in the corpus, and the source of every value in this
layer. The footnote gate governed nothing here, and it was silent because it
could not see rather than because the notes were clean -- so note 9 on the VR
cells was read by hand, and this file pinned the reading and the blindness
together, because the second is the reason the first had to happen.

Both causes are fixed now, in ``test_ordered_list_notes.py``, and the tests
below that held the blindness hold the repair instead. That is what they were
for: a test that describes a fault has to fail when somebody fixes it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.designs.model import load_catalog
from flats.encode.footnotes import census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
ZDO = f"{CLACKAMAS}/zdo.315.txt"

#: Table 315-2, transposed one cell per line, two cells per district in header
#: order. The second of each pair is the one that reaches this building.
LOW_DENSITY = {
    "R5": 1173,
    "R7": 1175,
    "R8.5": 1177,
    "R10": 1179,
    "R15": 1181,
    "R20": 1183,
    "R30": 1185,
}

#: Table 315-3, three values under three headers.
VILLAGE = ("VR57", "VR45")


@pytest.fixture(scope="module")
def clackamas() -> Layer:
    return load_rules()[CLACKAMAS]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def lines(store: ProvenanceStore) -> list[str]:
    return store.load(ZDO).text.splitlines()


# -- Table 315-2: two cells per district, and only one of them is ours -------


def test_each_low_density_district_takes_its_own_cell(
    clackamas: Layer, store: ProvenanceStore
) -> None:
    for zone, line in LOW_DENSITY.items():
        held = clackamas.zones[zone].values["max_height_ft"]
        assert held.value == 35, zone
        assert held.prov.quote == f"{ZDO}#L1169,L{line}", zone
        quoted = store.quote(held.prov.quote)
        assert "Maximum Building Height" in quoted, zone
        assert "All other buildings, including accessory dwelling units: 35 feet" in quoted


def test_the_row_prints_two_cells_and_the_first_is_not_this_building(
    lines: list[str],
) -> None:
    """An accessory building over 500 square feet takes 20 feet or the height
    of the primary dwelling. Four attached primary dwellings are not an
    accessory building, so the pod is measured against the second line -- which
    is why the quote carries the row label, so a reviewer can see there were
    two lines to choose between."""
    assert lines[1168] == "Maximum Building Height"
    for zone, line in LOW_DENSITY.items():
        accessory = lines[line - 2]
        assert accessory.startswith("Accessory buildings larger than 500 square feet"), zone
        assert "20 feet or the height of the primary dwelling" in accessory, zone


def test_the_eight_districts_print_the_same_sentence_so_position_names_the_column(
    lines: list[str],
) -> None:
    """Which is the argument for this layer's Table 315-2 convention rather
    than an exception to it. Sixteen cells, eight districts, every "all other
    buildings" line word-for-word identical: nothing in the text distinguishes
    R-5's cell from R-30's, so the only thing that can is where it sits."""
    cells = lines[1169:1185]
    assert len(cells) == 16
    ours = cells[1::2]
    assert len(set(ours)) == 1
    assert ours[0] == "All other buildings, including accessory dwelling units: 35 feet"
    # Eight columns in the header, in the order the cells follow.
    assert lines[1142:1150] == ["R-2.5", "R-5", "R-7", "R-8.5", "R-10", "R-15", "R-20", "R-30"]
    # And FLATS holds no R-2.5, so the first pair is skipped rather than lost.
    assert "R2.5" not in load_rules()[CLACKAMAS].zones


def test_the_low_density_height_row_carries_no_footnote_marker(lines: list[str]) -> None:
    """Unlike the coverage row directly above it, which is marked 5,6. Worth
    asserting because the gate cannot check it here -- see below."""
    assert lines[1167] == "50 percent5,6"
    for line in LOW_DENSITY.values():
        assert not lines[line - 1].rstrip().endswith(tuple("0123456789"))


# -- Table 315-3: three values, three headers, and note 9 --------------------


def test_the_village_zones_read_a_three_value_row_positionally(
    clackamas: Layer, store: ProvenanceStore, lines: list[str]
) -> None:
    """The rule this layer already states for front, maximum front and side: a
    three-value row under three headers is positional and nothing is merged.
    Here the three agree anyway, so the merge question cannot change it."""
    assert lines[1315:1319] == ["Standard", "VR-5/7", "VR-4/5", "VTH"]
    assert lines[1319] == "Maximum Building Height"
    assert lines[1320:1323] == ["35 feet9"] * 3

    for zone in VILLAGE:
        held = clackamas.zones[zone].values["max_height_ft"]
        assert held.value == 35, zone
        assert held.prov.quote == f"{ZDO}#L1320-L1323", zone
        assert store.quote(held.prov.quote).count("35 feet9") == 3, zone


def test_note_nine_cannot_loosen_this_ceiling_because_it_excludes_middle_housing(
    lines: list[str],
) -> None:
    """The note relieves one platted subdivision of the 35 feet, and names
    middle housing developed under Section 845 as the thing the relief does not
    reach. A quadplex is exactly that, so the standard stands unconditionally
    for this building -- the note reads in the direction that keeps the
    ceiling, not the one that lifts it."""
    note = lines[1413]
    assert note.startswith("9 Except for middle housing developed pursuant to Section 845")
    assert "Triplexes, Quadplexes, Townhouses, and Cottage Clusters" in note
    assert "Sieben Creek Estates" in note
    assert "is not required to comply with this standard" in note


def test_and_section_845_states_no_height_of_its_own(store: ProvenanceStore) -> None:
    """So there is nothing underneath the district table to preempt it. 845 is
    the section that decides how a quadplex here is designed; it is silent on
    how tall."""
    assert "height" not in store.load(f"{CLACKAMAS}/zdo.845.txt").text.lower()


# -- why that note had to be read by hand ------------------------------------


def test_the_document_behind_this_whole_layer_had_no_readable_footnotes(
    store: ProvenanceStore,
) -> None:
    """305 markers and zero bodies when these heights were encoded: the worst
    unreconciled document in the corpus, and every value in this layer cites
    it. Both causes are fixed now -- see test_ordered_list_notes.py -- so what
    this holds is the shape of the repair, not the fault. Still unreconciled,
    which is the ledger being honest rather than a claim of completeness."""
    got = census(store.load(ZDO).text, layer=CLACKAMAS, doc=ZDO)
    assert len(got.markers) > 400
    assert len(got.bodies) == 84
    assert len(got.unbodied) < len(got.markers) / 4
    assert not got.reconciled


def test_and_the_gate_that_governed_nothing_here_now_governs_all_of_it(
    clackamas: Layer,
) -> None:
    """The fault this pins is not a wrong number, it is a check that could not
    run. Every other layer's values are held back when a note above them is
    unread; this layer's would have certified under all 305. Seventy-three are
    governed now, and none of them blocked -- every note was read and ruled.

    Nine of the seventy-three arrived later than the rest. ZDO 1012 prints the
    notes under Table 1012-1, Bonus Density, with no heading and the mark
    welded to the first word, so the reader saw four markers and no block at
    all; with the welded run allowed to open one, its region reaches back over
    the general density paragraph that every maximum density quotes."""
    rows = [r for r in qualified() if r.layer == CLACKAMAS]
    assert len(rows) == 73
    assert not any(r.blocking for r in rows)


def test_and_the_cause_was_the_spelling_not_the_absence_of_notes(
    lines: list[str],
) -> None:
    """The notes were always there and always numbered. This code writes them
    as "1 The minimum and maximum lot size standards" -- one space, no heading
    -- and the gapped-run reader demands a column gap, because at one space
    that pattern also matches every numbered paragraph in a code. Declining it
    there is still right; the run had to earn its reading another way."""
    from flats.encode.footnotes import HEADLESS_NOTE, NOTES_HEAD, _tight_run

    first = lines[1397]
    assert first.startswith("1 The minimum and maximum lot size standards apply")
    assert HEADLESS_NOTE.match(first) is None  # one space, so the gapped rule declines
    assert HEADLESS_NOTE.match(first.replace("1 ", "1   ")) is not None  # a gap would not
    assert not any(NOTES_HEAD.match(line.strip()) for line in lines)
    # What reads it instead: the run proves itself 1, 2, 3, and something above
    # it in the region actually bears a marker.
    assert _tight_run(lines, 1397, 0)


def test_which_is_why_the_reading_is_written_into_the_layer_rather_than_left_to_it() -> None:
    yaml = Path("flats/config/jurisdictions/or/clackamas/_unincorporated.yaml").read_text(
        encoding="utf-8"
    )
    assert "305 footnote markers and ZERO bodies" in yaml
    assert "silent because it was blind, not because the notes were clean" in yaml
    assert "Sieben Creek" in yaml


# -- what the lot comes back as ----------------------------------------------


def test_no_zone_in_this_layer_is_missing_anything_now(
    rules: RuleSet, clackamas: Layer
) -> None:
    for zone in clackamas.zones:
        assert not rules.resolve(CLACKAMAS, zone).missing_required, zone


def test_the_pod_clears_all_nine(rules: RuleSet) -> None:
    pod = next(d for d in load_catalog() if d.id == "pod56x36")
    assert pod.height_ft == 26
    for zone in (*LOW_DENSITY, *VILLAGE):
        assert rules.resolve(CLACKAMAS, zone).values["max_height_ft"].value == 35, zone


def test_and_the_corpus_wide_height_gap_is_now_one_zone_wide(rules: RuleSet) -> None:
    """Twenty-six zones across three jurisdictions when this started. What is
    left is Wilsonville's OTR, which hands height to a design standards book by
    name and should keep reporting nothing until somebody fetches it."""
    silent = [
        (layer_id, zone)
        for layer_id, layer in sorted(rules.layers.items())
        for zone in layer.zones
        if (got := rules.resolve(layer_id, zone)).values.get("quadplex_allowed")
        and got.values["quadplex_allowed"].value
        and "max_height_ft" in got.missing_required
    ]
    assert silent == [("or/clackamas/wilsonville", "OTR")]
