"""Seven zones that let you build and never said how tall.

The coverage ledger reported no gaps on 19 August. It was right then. Zones
added afterwards re-opened it, and nobody re-ran it -- so twenty-six zones
across three jurisdictions were permitting a quadplex and stating no height,
which means the screen was placing a 26 ft building against no ceiling and
calling that a pass. Eight of the twenty-six are Wilsonville's.

The numbers were never unknown. Every one of these zones was ported carrying a
note that reads "height 35ft". A number with nothing pointing at a page is a
number this project does not have, so leaving it unencoded was right; leaving it
alone afterwards was not.

R states it in a sentence. The six PDR zones state it in a table whose height
column is one merged cell spanning all seven rows -- and the stored text is the
plain extraction, which flattens the grid and prints that cell once, right after
the PDR-1 row, where it reads as PDR-1's own number and leaves five zones
looking silent. That was settled by re-extracting the same PDF in layout mode,
not by inferring it.

OTR is still without one and should stay that way. Its code hands height to a
design standards book by name, and no citywide fallback exists to borrow. A zone
that reports no height is the ledger working.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WILSONVILLE = "or/clackamas/wilsonville"
CODE = f"{WILSONVILLE}/4.planning.txt"

#: The six that take the merged cell.
PDR = ("PDR1", "PDR2", "PDR3", "PDR4", "PDR5", "PDR6")


@pytest.fixture(scope="module")
def wilsonville() -> Layer:
    return load_rules()[WILSONVILLE]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the sentence ------------------------------------------------------------


def test_the_r_zone_states_it_outright(wilsonville: Layer, store: ProvenanceStore) -> None:
    held = wilsonville.zones["R"].values["max_height_ft"]
    assert held.value == 35
    assert "4.122(.05)E" in held.prov.cite
    assert "Maximum building or structure height: 35 feet" in store.quote(held.prov.quote)


# -- the merged cell ---------------------------------------------------------


def test_all_six_pdr_zones_take_the_same_cell(
    wilsonville: Layer, store: ProvenanceStore
) -> None:
    quotes = set()
    for zone in PDR:
        held = wilsonville.zones[zone].values["max_height_ft"]
        assert held.value == 35, zone
        assert "Table 2" in held.prov.cite, zone
        quotes.add(held.prov.quote)
    # One cell, so one quote. Six copies of the same citation would be six
    # places to correct if the table is ever misread.
    assert len(quotes) == 1


def test_the_quote_carries_the_header_because_the_figure_alone_names_nothing(
    wilsonville: Layer, store: ProvenanceStore
) -> None:
    """In the flattened text the merged cell is the bare line "35". Quoted on
    its own it evidences the number and not the standard, and a reviewer opening
    it would find a line with no subject."""
    quoted = store.quote(wilsonville.zones["PDR1"].values["max_height_ft"].prov.quote)
    assert "Table 2: Lot Standards for All PDR Zoned Lots" in quoted
    assert "Maximum" in quoted and "Building" in quoted and "Height (feet)" in quoted
    assert "35" in quoted


def test_the_flattened_grid_is_what_made_this_look_like_pdr_ones_number(
    store: ProvenanceStore,
) -> None:
    """The failure mode, pinned. The stored plain extraction prints the merged
    cell once, immediately after the PDR-1 row, and every later PDR row ends at
    its lot depth. Read raw, five zones state no height."""
    lines = store.load(CODE).text.splitlines()
    at = next(i for i, l in enumerate(lines) if "Table 2: Lot Standards for All PDR" in l)
    window = lines[at : at + 40]

    assert window[window.index("PDR-1 20,000") + 4] == "35"
    for row in ("PDR-4 3,000 75/75 35/35 F 60", "PDR-5 2,000 75/75 30/30 60"):
        line = next(l for l in window if l.startswith(row.split()[0]))
        assert line.strip().endswith("60"), line
        assert "35" not in line.split()[-1], line


def test_and_the_setback_cell_beside_it_is_read_the_same_way_already(
    wilsonville: Layer,
) -> None:
    """Which is the argument, not an analogy. Table 2's Setbacks column is the
    other merged cell -- "Per Section 4.113 (.02)", printed once on the same
    two lines after the PDR-1 row -- and every PDR zone in this layer already
    takes its setbacks from 4.113(.02). The height cell is the same shape in
    the same rendering, so reading one and not the other was the inconsistency,
    not reading both."""
    for zone in PDR:
        assert "4.113" in wilsonville.zones[zone].values["setback_front_ft"].prov.quote or any(
            "4.113" in str(v.prov.cite) for v in wilsonville.zones[zone].values.values()
        ), zone


# -- what the lot comes back as ----------------------------------------------


def test_no_wilsonville_zone_that_permits_the_building_is_silent_but_one(
    rules: RuleSet, wilsonville: Layer
) -> None:
    silent = [
        zone
        for zone in wilsonville.zones
        if "max_height_ft" in rules.resolve(WILSONVILLE, zone).missing_required
    ]
    assert silent == ["OTR"]


def test_otr_is_silent_on_purpose_and_has_nothing_to_borrow(
    wilsonville: Layer, store: ProvenanceStore
) -> None:
    """4.123(.06)A hands design and siting to the Old Town Residential Design
    Standards Book, naming height explicitly. The book is not a stored document,
    and there is no citywide number underneath it: 4.113(.03) is headed "Height
    Guidelines" and lists what the Development Review Board MAY regulate, which
    is a discretion rather than a standard."""
    assert "max_height_ft" not in wilsonville.zones["OTR"].values
    text = store.load(CODE).text
    assert "Design Standards Book including but not limited to architectural design" in text
    assert "(.03) Height Guidelines. The Development Review Board may regulate heights" in text
    assert "Fetch the design book before signing an OTR screen" in wilsonville.zones["OTR"].notes


def test_the_pod_clears_all_seven(rules: RuleSet) -> None:
    """26 against 35. It would have cleared before too -- the point is that
    before this it cleared against nothing."""
    pod = next(d for d in load_catalog() if d.id == "pod56x36")
    assert pod.height_ft == 26
    for zone in ("R",) + PDR:
        assert rules.resolve(WILSONVILLE, zone).values["max_height_ft"].value == 35, zone


def test_the_layer_records_why_the_number_was_known_and_not_encoded(
    wilsonville: Layer,
) -> None:
    """"height 35ft" was sitting in every one of these zones' ported notes. The
    next reader needs to know that a number in a note is not a number, or the
    same seven zones get "fixed" from the note again."""
    notes = wilsonville.notes
    assert "height 35ft" in notes
    assert "merged cell" in notes
    assert "4.113(.03)" in notes
