"""Washington County's standard-plat gate, measured (FOLLOWUPS 83).

CDC 304-2.14 / 305-2.14 / 306-2.14 / 307-2.13 open the quick Type I review
only on a lot "approved for the construction of a Single Detached Dwelling
Unit through a Standard Subdivision or Standard Partition", and "Standard"
is set against the Middle Housing Land Division alone (CDC 106-107). Working
reading 2026-11-03, Steph GO 2026-11-07: any recorded subdivision or partition
plat passes; a middle housing land division, a lot no plat made and a lot
nothing read keep the flag. :mod:`flats.ingest.plats` reads it off the
county's legal description; the gate must never pass on anything else.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from flats.ingest import plats
from flats.ingest.plats import MHLD, PLATTED, UNPLATTED, UNREAD, classify, origin, parse, tlid_key
from flats.ingest.quadfit import iter_rows, lot_from_row, plat_origin_of
from flats.score.flags import Colour
from flats.score.screen import CLOSER_LOOK_REVIEW_CONDITIONS, review_with_conditions
from flats.tests.test_quadfit_bridge import _stage_files, row
from flats.tests.test_round2_rulings import DESIGN, facts, rules, run

pytestmark = pytest.mark.unit

GATE = {"type_i_standard_plat_required": True}


@pytest.mark.parametrize(
    ("legal", "want"),
    [
        # A plat's name, one whole lot, the assessor's notes: made by the plat.
        ("VIEW CREST, LOT 3", PLATTED),
        ("ROLLINGWOOD NO.2, BLOCK 3, LOT 2, ACRES 0.19", PLATTED),
        ("2016-037 PARTITION PLAT, LOT 1, ACRES 0.09", PLATTED),
        ("EMERALD ESTATES, LOT A, ACRES 4.05", PLATTED),
        ("HURLBUTT'S NORTHRIDGE A PLANNED DEVELOPMENT, LOT 36, ACRES 0.22", PLATTED),
        ("FOO ESTATES, LOT 9, ACRES 0.21; POTENTIAL ADD'L TAX LIABILITY", PLATTED),
        # Steph 2026-11-08: whole lots together, and whole lots with part of a
        # vacated street, are made by the plat too.
        ("TOUCHSTONE NO.3, LOT 45 & 46", PLATTED),
        ("FOO ACRES, LOT 13 AND 14", PLATTED),
        ("PARK RIDGE WEST, LOT 8, PLUS PT VACATED RD, ACRES 0.26", PLATTED),
        ("FOO ADDITION, BLOCK 2, LOT 1 & PT VACATED STREET", PLATTED),
        ("HYDE PARK, BLOCK 12, LOT 1-24, BLOCK 13, LOTS 1-24, PLUS PT VACATED ST, ACRES 7.21", PLATTED),
        ("NORTH PLAINS, BLOCK 4, LOT 5-8, PLUS PT VACATED STREETS, BLOCK 5, LOTS 1-6, 11, 13-16, ACRES 2.34", PLATTED),
        # A middle housing land division.
        ("HAZEL WOODS MIDDLE HOUSING, LOT 4, ACRES 0.06", MHLD),
        ("HAZEL WOODS MIDDLE HOUSING, TRACT A, ACRES 0.25", MHLD),
        # No plat made the lot as it stands.
        ("ACRES 10.05", UNPLATTED),
        ("ACRES 5.00, POTENTIAL ADD'L TAX LIABILITY", UNPLATTED),
        ("GENTRY PLACE, LOT PT 10, ACRES 0.15", UNPLATTED),
        ("WINTHROP PARK NO.2, LOT 94 & PT 93", UNPLATTED),
        ("1991-104 PARTITION PLAT, LOT PT 1, ACRES 4.34", UNPLATTED),
        ("FOO, LOT PT 69 PLUS PT VACATED RD", UNPLATTED),
        # A vacated tract, or an unnamed "portion", is not a street.
        ("FOO, LOT 3, PLUS PT VACATED TR 'A'", UNPLATTED),
        ("FOO, LOT 3, PLUS VACATED PORTION", UNPLATTED),
        # Not read: a condominium unit, a tract, several lots, anything else.
        ("SYLVAN HEIGHTS CONDO, LOT 157", UNREAD),
        ("KAISER WOODS, TRACT B, ACRES 0.69", UNREAD),
        ("FOO, LOT 7-F", UNREAD),
        ("FOO, LOT 3, BAR ESTATES, LOT 4", UNREAD),
        ("NORTH TIGARDVILLE ADDITION, AMENDED, LOT 46-49 & 51-52, ACRES 6.54", UNREAD),
        ("ACRES 10, ADDL: NON-FARM PARCEL", UNREAD),
        ("ROSEDALE GARDENS, BLOCK PT 3, ACRES 2.50, CODE SPLIT", UNPLATTED),
        ("", UNREAD),
        (None, UNREAD),
    ],
)
def test_a_legal_description_names_the_plat_that_made_the_lot(legal: str | None, want: str) -> None:
    assert origin(legal) == want


def _raw(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["TLID", "LEGAL_DESCRIPTION", "YEARBUILT"])


def test_only_a_plat_older_than_middle_housing_divisions_passes() -> None:
    """A plat recorded since 2022 may be a middle housing land division whose
    title does not say so: a partition plat carries its year, and a named
    subdivision passes only where its houses were built in three different
    years before 2022 -- one division's child lots share one parent's building."""
    raw = _raw(
        [
            ("1S100AA00100", "2021-010 PARTITION PLAT, LOT 1", 0),
            ("1S100AA00200", "2022-010 PARTITION PLAT, LOT 1", 0),
            ("1S100AA00300", "OLD TOWN, LOT 1", 1950),
            ("1S100AA00400", "OLD TOWN, LOT 2", 1962),
            ("1S100AA00500", "OLD TOWN, LOT 3", 1977),
            ("1S100AA00600", "OLD TOWN, LOT 4", 0),
            # An old fourplex's lot divided into four: one building year.
            ("1S100AA00700", "QUAD COURT, LOT 1", 1975),
            ("1S100AA00800", "QUAD COURT, LOT 2", 1975),
            ("1S100AA00900", "QUAD COURT, LOT 3", 1975),
            ("1S100AA01000", "QUAD COURT, LOT 4", 1975),
            # Houses built since 2022 say nothing of the plat's age.
            ("1S100AA01100", "NEW ACRES ESTATES, LOT 1", 2023),
            ("1S100AA01200", "NEW ACRES ESTATES, LOT 2", 2024),
            ("1S100AA01300", "NEW ACRES ESTATES, LOT 3", 2025),
        ]
    )
    frame, counts = classify(raw)
    got = dict(zip(frame["TLID"], frame["origin"].astype(str)))
    assert got["1S100AA00100"] == PLATTED
    assert got["1S100AA00200"] == UNREAD
    assert {got[f"1S100AA00{n}00"] for n in (3, 4, 5, 6)} == {PLATTED}
    assert {got[t] for t in ("1S100AA00700", "1S100AA00800", "1S100AA00900", "1S100AA01000")} == {UNREAD}
    assert {got[t] for t in ("1S100AA01100", "1S100AA01200", "1S100AA01300")} == {UNREAD}
    assert counts[PLATTED] == 5


def test_a_tlid_held_twice_is_read_only_where_both_agree() -> None:
    raw = _raw(
        [
            ("1S100AA00100", "2001-010 PARTITION PLAT, LOT 1", 0),
            ("1S100AA00100", "ACRES 0.30", 0),
            ("1S100AA00200", "2001-010 PARTITION PLAT, LOT 2", 0),
            ("1S100AA00200", "2001-010 PARTITION PLAT, LOT 2", 0),
        ]
    )
    frame, _ = classify(raw)
    got = dict(zip(frame["TLID"], frame["origin"].astype(str)))
    assert got == {"1S100AA00100": UNREAD, "1S100AA00200": PLATTED}


def test_the_county_and_regional_tlid_spellings_join() -> None:
    assert tlid_key("2S124A003100") == tlid_key("2S124A  -03100") == "2S124A003100"
    assert tlid_key("1N107    -00100") == "1N1070000100"
    # Other counties' and malformed ids never join: unread, not guessed.
    for other in ("1S1E20AA  -15100", "21E01AB  -00100", "R123456", "", None):
        assert tlid_key(other) is None


def test_the_gate_passes_only_on_a_lot_a_plat_made() -> None:
    assert review_with_conditions(rules(**GATE), facts(plat_origin=PLATTED), DESIGN) is None
    for how in (MHLD, UNPLATTED, UNREAD, None):
        assert review_with_conditions(rules(**GATE), facts(plat_origin=how), DESIGN) == "standard_plat"
    # The buildable-area gate still comes first.
    big = {**GATE, "type_i_max_buildable_sqft": 10000, "type_i_density_escape_du_per_acre": 12}
    assert review_with_conditions(rules(**big), facts(lot_sqft=20000, plat_origin=PLATTED), DESIGN) == "buildable_area"


def test_a_platted_lot_outside_the_statute_goes_green_and_an_unread_one_stays_yellow() -> None:
    got = run(facts(plat_origin=PLATTED), rules(**GATE))
    assert got.colour is Colour.green
    assert CLOSER_LOOK_REVIEW_CONDITIONS not in got.reasons
    for how in (MHLD, UNPLATTED, None):
        held = run(facts(plat_origin=how), rules(**GATE))
        assert held.colour is Colour.yellow
        assert CLOSER_LOOK_REVIEW_CONDITIONS in held.reasons


def test_the_bridge_reads_the_plat_for_washington_county_lots_only(tmp_path: Path) -> None:
    table = pd.DataFrame(
        {
            "TLID": ["1S101AA00100", "1S101AA00200"],
            "origin": [PLATTED, UNPLATTED],
            "plat": ["VIEW CREST", None],
        }
    )
    path = tmp_path / plats.PLATS
    table.to_parquet(path, index=False)
    s4, s5o = _stage_files(
        tmp_path,
        [
            row(TLID="1S101AA  -00100", jurisdiction="washington_unincorporated"),
            row(TLID="1S101AA  -00200", jurisdiction="washington_unincorporated"),
            row(TLID="1S101AA  -00300", jurisdiction="washington_unincorporated"),
            # The same string in another county is another lot.
            row(TLID="1S101AA00100", jurisdiction="portland"),
        ],
    )
    got = {r["TLID"]: lot_from_row(r).facts.plat_origin for r in iter_rows(s4, s5o, plats=path)}
    assert got == {
        "1S101AA  -00100": PLATTED,
        "1S101AA  -00200": UNPLATTED,
        "1S101AA  -00300": None,
        "1S101AA00100": None,
    }
    # Without the reading nothing is read.
    assert {lot_from_row(r).facts.plat_origin for r in iter_rows(s4, s5o)} == {None}


def test_plat_origin_of_refuses_an_unknown_jurisdiction() -> None:
    assert plat_origin_of({"plat_origin": PLATTED, "jurisdiction": "nowhere"}) is None
    assert plat_origin_of({"plat_origin": None, "jurisdiction": "washington_unincorporated"}) is None


def test_the_committed_pull_holds_no_unread_rows_and_names_its_source() -> None:
    import json

    assert plats.CURRENT.is_file()
    meta = json.loads(plats.CURRENT.with_name(plats.META).read_text(encoding="utf-8"))
    assert meta["source"] == plats.LAYER_URL and meta["fetched_at"]
    frame = pd.read_parquet(plats.CURRENT)
    assert set(frame["origin"].astype(str)) <= {PLATTED, MHLD, UNPLATTED}
    assert len(frame) == meta["kept"] and not frame["TLID"].duplicated().any()


def test_parse_names_the_plat_and_the_partition_year() -> None:
    assert parse("2016-037 PARTITION PLAT, LOT 1") == (PLATTED, "2016-037 PARTITION PLAT", 2016)
    assert parse("VIEW CREST, LOT 3") == (PLATTED, "VIEW CREST", None)
