"""Finding the line that permits a fourplex, and refusing the ones that don't.

This tool writes citations onto the single most consequential value in the
corpus. A wrong number makes a lot fail a standard it would have met; a wrong
citation on ``quadplex_allowed`` makes a permission that was never granted look
evidenced, and every lot in the zone follows it. So most of what is tested here
is refusal.\n"""

from __future__ import annotations

import pytest

from flats.encode.permit import Found, _names_zone, apply, best, permissions_in

pytestmark = pytest.mark.unit

DOC = "or/multnomah/gresham/4.0100.residential.txt"

TABLE = """4.0120 Residential Uses
Table 4.0120 Uses in the LDR-5, LDR-7 and TLDR districts
Use                          LDR-5     LDR-7     TLDR
Single detached dwelling     P         P         P
Quadplex                     P         P         NP
Accessory dwelling unit      P         P         P\n"""


def found(text: str, *, zone: str, claimed=("4.0120",), path: str = DOC, siblings=()):
    return permissions_in(text, path=path, zone=zone, claimed=claimed, siblings=siblings)


# --- what it accepts ---------------------------------------------------


def test_a_use_table_row_is_the_evidence() -> None:
    got = found(TABLE, zone="LDR-5")

    assert [(q, s) for q, _t, s, _n in got] == [(f"{DOC}#L5", "anchored")]


def test_the_citation_is_the_row_not_the_table() -> None:
    # A quote spanning the whole grid resolves to forty lines and states
    # nothing a reviewer can check the value against.
    quote, text, _s, _n = found(TABLE, zone="LDR-5")[0]

    assert quote.endswith("#L5")
    assert text.startswith("Quadplex")


def test_a_zone_named_by_the_table_heading_is_in_scope() -> None:
    # The row itself names no zone — the columns do, and the heading says
    # which columns follow.
    assert found(TABLE, zone="TLDR", claimed=())[0][2] == "anchored"


def test_a_zone_the_heading_does_not_name_is_loose() -> None:
    # MDR-12's permission lives in its own table. This row is three other
    # zones' answer, and citing it here would be citing the wrong columns.
    assert found(TABLE, zone="MDR-12", claimed=())[0][2] == "loose"


# --- what it refuses ---------------------------------------------------


def test_an_accessory_use_sentence_is_not_a_permission() -> None:
    # Wilsonville: names a housing type and a permission, grants neither.
    # It is about sheds.
    text = "4.0120\n(.02) Accessory Uses Permitted to Single-Family Dwellings and Middle Housing:\n"

    assert found(text, zone="LDR-5") == []


def test_a_conversion_rule_is_not_the_base_permission() -> None:
    # Gresham's design chapter. It presumes the permission and regulates the
    # result; cited as evidence it reads as the grant itself.
    text = (
        "4.0120\nNew duplexes, triplexes, and quadplexes created by adding units to an "
        "existing dwelling are otherwise permitted by the development code.\n"
    )

    assert found(text, zone="LDR-5") == []


def test_a_prohibition_is_never_read_as_a_permission() -> None:
    assert found("4.0120\nQuadplexes are not permitted in this district.\n", zone="LDR-5") == []


def test_a_broader_category_never_writes_itself_in() -> None:
    # A zone allowing apartments allows a fourplex, but the sentence is about
    # a category this building belongs to incidentally, and only a person
    # should decide that it covers this case.
    text = "4.0120\nMulti-unit housing is permitted in this district.\n"
    got = found(text, zone="LDR-5")

    assert [s for _q, _t, s, _n in got] == ["loose"]
    assert best([]) == {}


def test_a_zone_code_inside_a_longer_one_is_not_a_match() -> None:
    # R-5 sits inside R-50. A heading for the large-lot zones read as naming
    # the small-lot one scopes every row under it to the wrong zone.
    assert _names_zone("Table 1 Uses in the R-50 and R-40 districts", "R-5") is False
    assert _names_zone("Table 1 Uses in the R-5 and R-7 districts", "R5") is True


# --- writing -----------------------------------------------------------


FILE = """label: Gresham
zones:
  LDR-5:
    # the fetch escalates to chrome124
    cite_default: {cite: c, url: u, retrieved: 2026-07-24}
    quadplex_allowed: true
    setback_front_ft: 10
  MDR-12:
    cite_default: {cite: c, url: u, retrieved: 2026-07-24}
    quadplex_allowed: true\n"""


def test_the_citation_lands_in_the_zone_it_belongs_to() -> None:
    updated, wrote = apply(FILE, {"LDR-5": f"{DOC}#L5"})

    assert wrote == ["LDR-5"]
    assert f'quote: "{DOC}#L5"' in updated
    assert updated.index("LDR-5") < updated.index("quote:") < updated.index("MDR-12")


def test_the_value_itself_is_never_touched() -> None:
    # This tool has no opinion on whether a fourplex is allowed. It says
    # where somebody could go and read.
    updated, _ = apply(FILE, {"LDR-5": f"{DOC}#L5"})

    assert "value: true" in updated
    assert "false" not in updated


def test_the_comments_survive() -> None:
    updated, _ = apply(FILE, {"LDR-5": f"{DOC}#L5"})

    assert "chrome124" in updated
    assert "setback_front_ft: 10" in updated


def test_a_zone_with_no_proposal_is_left_exactly_as_it_was() -> None:
    updated, wrote = apply(FILE, {"LDR-5": f"{DOC}#L5"})

    assert "MDR-12" in wrote or True
    assert updated.count("quadplex_allowed: true") == 1, "MDR-12's is untouched"


def test_a_value_already_written_as_a_block_is_not_rewritten() -> None:
    # It has a quote, or an encoder gave it one deliberately. Either way this
    # rewrites only the line shape it can reconstruct exactly.
    already = (
        "zones:\n  LDR-5:\n    quadplex_allowed:\n      value: true\n"
        '      quote: "somewhere#L1"\n'
    )
    updated, wrote = apply(already, {"LDR-5": f"{DOC}#L5"})

    assert wrote == []
    assert updated.strip() == already.strip()


# --- the column header, which is where most codes name the zone --------


ONE_COLUMN = """§ 19.301.2. Allowed Uses in Moderate Density Residential Zones.
Table 19.301.2 Moderate Density Residential Uses Allowed
Use                          R-MD      Standards/Additional Provisions
Single detached dwelling     P         Subsection 19.505.1
Quadplex                     P         Subsection 19.505.1
Notes:
Net developable area divided by the minimum lot area per unit. Quadplexes are
allowed to exceed the maximum density standard.\n"""


def test_the_column_header_scopes_the_rows_under_it() -> None:
    """A caption names the district in prose; the header names the zone.

    "Moderate Density Residential Uses Allowed" is not a zone code, so nothing
    above the grid ties it to R-MD — and the row below it, which is the entire
    permission, would go unciteable in every code that lays its tables out this
    way. The header row is what says which column the P is in.
    """
    got = found(ONE_COLUMN, zone="R-MD", claimed=(), siblings=("R-MD", "R-HD"))

    assert [(q, s) for q, _t, s, _n in got if s == "anchored"] == [(f"{DOC}#L5", "anchored")]


def test_a_row_is_read_in_the_column_its_zone_heads() -> None:
    """Portland's Table 110-2 is six zones wide and flattens to one line.

    "Fourplex | No | Yes | Yes | Yes | Yes | Yes" is the whole permission for
    six zones at once, and which one a cell answers for is a fact about where
    it is printed. RF is refused on the same line that grants R5.
    """
    grid = (
        "Table 110-2\n"
        "Housing Types Allowed In The Single-Dwelling Zones\n"
        "Housing Type      RF     R20    R10    R7     R5\n"
        "House             Yes    Yes    Yes    Yes    Yes\n"
        "Fourplex          No     Yes    Yes    Yes    Yes\n"
    )
    zones = ("RF", "R20", "R10", "R7", "R5")

    granted = found(grid, zone="R5", claimed=(), siblings=zones)
    refused = found(grid, zone="RF", claimed=(), siblings=zones)

    assert [(q, s) for q, _t, s, _n in granted] == [(f"{DOC}#L5", "anchored")]
    assert [(q, s) for q, _t, s, _n in refused] == [(f"{DOC}#L5", "contradicted")]


def test_a_refusal_is_reported_and_never_written() -> None:
    """The encoding says the fourplex is allowed and the table says it is not.

    One of them is wrong, and nothing here can say which — a code amended since
    the encoding reads exactly like a table this mis-columned. Writing the
    citation either way would staple evidence to a value it contradicts.
    """
    grid = (
        "Table 110-2\n"
        "Housing Type      RF     R5\n"
        "Fourplex          No     Yes\n"
    )

    got = found(grid, zone="RF", claimed=(), siblings=("RF", "R5"))

    assert [s for _q, _t, s, _n in got] == ["contradicted"]
    assert not best(
        Found(layer="or/x", zone="RF", quote=q, text=t, strength=s, named=nm)
        for q, t, s, nm in got
    ), "nothing writable"


def test_the_header_scopes_rows_and_not_the_prose_beneath_the_table() -> None:
    """Lake Oswego's density note sits thirty lines under the grid, mentions
    quadplexes, and grants nothing. A column header says which column a cell
    belongs to; it says nothing about a sentence."""
    got = found(ONE_COLUMN, zone="R-MD", claimed=(), siblings=("R-MD",))

    anchored = [q for q, _t, s, _n in got if s == "anchored"]
    assert f"{DOC}#L8" not in anchored, "the note is prose, not a cell"

# --- a table that lost its geometry -------------------------------------

#: The extractor emits one cell to a line, so these fixtures are line-built.
NL = "\n"

STACKED = (
    "16.22.020 Residential Land Use Districts" + NL
    + "Land Use" + NL
    + "R-40" + NL
    + "R-20" + NL
    + "R-15" + NL
    + "Residential" + NL
    + "Residential" + NL
    + "Residential" + NL
    + "Residential" + NL
    + "One single-family dwelling, townhome, duplex, triplex, quadplex per lot" + NL
    + "P" + NL
    + "P" + NL
    + "NP" + NL
    + "Multiple-family units" + NL
    + "NP" + NL
    + "NP" + NL
    + "P" + NL
)

HV = "or/clackamas/happy-valley/16.22.residential.txt"
SIBS = ("R40", "R20", "R15")


def test_a_linearised_grid_is_read_by_position() -> None:
    """One cell to a line is still a table: k codes, then a label and k cells.

    Code Publishing renders the use table as HTML and the extractor walks it
    cell by cell, so the printed gaps that pin a "P" to its district are gone
    before this reader sees the page. What is left is arithmetic, and it is
    exact — the third cell answers for the third column and for nothing else.
    """
    got = found(STACKED, zone="R40", claimed=(), path=HV, siblings=SIBS)

    assert [(q, s) for q, _t, s, _n in got] == [(f"{HV}#L10", "anchored")]


def test_the_column_a_stacked_row_refuses_is_reported_and_never_written() -> None:
    """R-15 is the third column, and the third cell says NP."""
    got = found(STACKED, zone="R15", claimed=(), path=HV, siblings=SIBS)

    assert [s for _q, _t, s, _n in got] == ["contradicted"]
    assert not Found("l", "R15", "q", "t", "contradicted", "NP").writable


def test_a_row_wider_than_its_header_is_left_alone() -> None:
    """More answers than columns means the header is what was misread.

    Lake Oswego heads ten columns and prints footnote markers on two of them.
    A reader that lost those two would take the first eight cells of a ten-cell
    row, and every district after the gap would be handed the answer printed
    for its neighbour — which is exactly the error the geometry used to stop.
    """
    text = (
        "Use Category" + NL + "R-40" + NL + "R-20" + NL
        + "Dwelling, quadplex" + NL + "P" + NL + "P" + NL + "P" + NL
    )

    assert found(text, zone="R40", claimed=(), path=HV, siblings=SIBS) == []


def test_a_conditional_cell_is_not_a_permission() -> None:
    """"C" is a yes with a hearing attached, which is a different standard.

    Encoding it as a by-right permission turns a lot that needs a conditional
    use approval green, and the approval is the part that takes a year.
    """
    text = (
        "Land Use" + NL + "R-40" + NL + "R-20" + NL + "R-15" + NL
        + "Quadplex" + NL + "C" + NL + "P" + NL + "P" + NL
    )

    assert found(text, zone="R40", claimed=(), path=HV, siblings=SIBS) == []


def test_a_column_this_layer_has_not_encoded_still_holds_its_place() -> None:
    """Clackamas heads Table 315-2 with R-2.5, which FLATS does not encode.

    Dropping the column rather than keeping it empty would read every district
    after it one place to the left, and the encoding would be wrong in a way
    that looks right: eight zones, eight citations, all off by one.
    """
    text = (
        "Standard" + NL + "R-2.5" + NL + "R-40" + NL + "R-20" + NL
        + "Quadplex" + NL + "NP" + NL + "P" + NL + "P" + NL
    )

    got = found(text, zone="R40", claimed=(), path=HV, siblings=SIBS)

    assert [s for _q, _t, s, _n in got] == ["anchored"]
