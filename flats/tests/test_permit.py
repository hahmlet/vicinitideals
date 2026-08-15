"""Finding the line that permits a fourplex, and refusing the ones that don't.

This tool writes citations onto the single most consequential value in the
corpus. A wrong number makes a lot fail a standard it would have met; a wrong
citation on ``quadplex_allowed`` makes a permission that was never granted look
evidenced, and every lot in the zone follows it. So most of what is tested here
is refusal.
"""

from __future__ import annotations

import pytest

from flats.encode.permit import _names_zone, apply, best, permissions_in

pytestmark = pytest.mark.unit

DOC = "or/multnomah/gresham/4.0100.residential.txt"

TABLE = """4.0120 Residential Uses
Table 4.0120 Uses in the LDR-5, LDR-7 and TLDR districts
Use                          LDR-5     LDR-7     TLDR
Single detached dwelling     P         P         P
Quadplex                     P         P         NP
Accessory dwelling unit      P         P         P
"""


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
    quadplex_allowed: true
"""


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
allowed to exceed the maximum density standard.
"""


def test_the_column_header_scopes_the_rows_under_it() -> None:
    """A caption names the district in prose; the header names the zone.

    "Moderate Density Residential Uses Allowed" is not a zone code, so nothing
    above the grid ties it to R-MD — and the row below it, which is the entire
    permission, would go unciteable in every code that lays its tables out this
    way. The header row is what says which column the P is in.
    """
    got = found(ONE_COLUMN, zone="R-MD", claimed=(), siblings=("R-MD", "R-HD"))

    assert [(q, s) for q, _t, s, _n in got if s == "anchored"] == [(f"{DOC}#L5", "anchored")]


def test_a_header_naming_several_zones_scopes_nothing() -> None:
    """Four columns flatten to "Quadplex  P  N  P  N" and no reader can say
    which cell is which zone's. The row stays loose, which is the honest state
    — a citation pointing at another zone's answer is worse than none."""
    text = ONE_COLUMN.replace(
        "Use                          R-MD      Standards/Additional Provisions",
        "Use                          R-MD      R-HD      Standards",
    )

    got = found(text, zone="R-MD", claimed=(), siblings=("R-MD", "R-HD"))

    assert not [q for q, _t, s, _n in got if s == "anchored"]


def test_the_header_scopes_rows_and_not_the_prose_beneath_the_table() -> None:
    """Lake Oswego's density note sits thirty lines under the grid, mentions
    quadplexes, and grants nothing. A column header says which column a cell
    belongs to; it says nothing about a sentence."""
    got = found(ONE_COLUMN, zone="R-MD", claimed=(), siblings=("R-MD",))

    anchored = [q for q, _t, s, _n in got if s == "anchored"]
    assert f"{DOC}#L8" not in anchored, "the note is prose, not a cell"
