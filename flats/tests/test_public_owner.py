"""Multnomah's public land is RED by owner of record (FOLLOWUPS 205).

Steph RULED 2026-10-06 public and institutional land red. Washington
County's roll applies it by code (``public_land``: the vacant exempt codes
940, 950 ...; the improved x1 codes stay screened). Multnomah's roll holds no
such codes, so 36 government-owned and 27 housing-authority lots were GREEN
on run 128. The ``public_owner`` tier gives Multnomah the same answer off a
checked-in list of the lots whose owner of record is a public body.

Housing-authority land is YELLOW, not red (Steph 2026-11-18, rulings.yaml
``2026-11-18-housing-authority-land-yellow``): the roll does not rule it out,
the lot stays in the scan, and the screen holds it with a plain reason
(``flats/tests/test_housing_authority_hold.py``).
"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from flats.geom import roll

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LIST = roll.CONFIG.parent / "public_owners_multnomah.csv"

#: A city lot and a housing-authority lot off the list, GREEN on run 128.
CITY_LOT = "1N1E06DD  -01500"
HOUSING_LOT = "1N1E14AA  -06200"
#: Exempt as Multnomah marks it: assessed 0 beside a real market value.
BARE = {"LANDVAL": 465_500.0, "BLDGVAL": 0.0, "TOTALVAL": 465_500.0, "ASSESSVAL": 0.0, "BLDGSQFT": 0.0, "PROP_CODE": "211"}


def lot(tlid: str = CITY_LOT, **kw: Any) -> dict[str, Any]:
    return {"county": "multnomah", "tlid": tlid, "site_address": "123 SE MAIN ST", **BARE, **kw}


def tier(rules: roll.RollRules | None = None, **kw: Any) -> str | None:
    got = roll.read(lot(**kw), rules or roll.load_rules())
    return got["category"].removeprefix(roll.PREFIX) if got else None


def _rows() -> list[dict[str, str]]:
    with LIST.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# --- the names ----------------------------------------------------------------


@pytest.mark.parametrize(
    "owner",
    [
        "PORTLAND CITY OF", "CITY OF PORTLAND(LEASED", "GRESHAM CITY OF (PARKS & RECREATION", "PORTLAND WATER BUREAU",
        "MULTNOMAH COUNTY", "MULTNOMAH COUNTY TAX TITLE", "MULTNOMAH COUNTY LIBRARY DISTRICT",
        "OREGON STATE OF(DEPT OF", "OREGON STATE DEPT OF TRANSPORTATION", "STATE OF OREGON", "UNIVERSITY OF OREGON",
        "UNITED STATES OF AMERICA", "UNITED STATES POSTAL SERVICE", "U S POSTAL SERVICE",
        "METRO", "METRO-75% & PORTLAND CITY OF-25%", "METRO (PARKS & GREENSPACES", "PORT OF PORTLAND",
        "TRI-COUNTY METRO TRANS DIST OF OREG", "SCHOOL DISTRICT NO 1", "SCHOOL DIST NO 3",
        "CENTENNIAL UNIFIED SCHOOL DISTRICT ", "MT HOOD COMMUNITY COLLEGE", "WEST SLOPE WATER DISTRICT OF WASHIN",
        "ROCKWOOD WATER PEOPLE'S UTILITY DIS", "PDC DBA PROSPER PORTLAND",
    ],
)
def test_a_public_bodys_name_is_government(owner: str) -> None:
    assert roll.owner_group(owner, roll.load_rules().tier("public_owner")) == "government"


@pytest.mark.parametrize(
    "owner",
    ["HOME FORWARD", "HOME FORWARD DEVELOPMENT ENTERPRISE", "HOUSING AUTHORITY OF PORTLAND OREGO", "THE HOUSING AUTHORITY OF PORTLAND", "HOUSING AUTHORITY OF"],
)
def test_a_housing_authoritys_name_is_its_own_group(owner: str) -> None:
    assert roll.owner_group(owner, roll.load_rules().tier("public_owner")) == "housing_authority"


@pytest.mark.parametrize(
    "owner",
    [
        # Churches, charities, private schools and colleges stay checked.
        "ARCHDIOCESE OF PORTLAND IN OREGON", "EAST COUNTY CHURCH OF CHRIST", "HABITAT FOR HUMANITY PORTLAND/METRO",
        "UNIVERSITY OF PORTLAND", "LEWIS & CLARK COLLEGE", "REED COLLEGE", "COLUMBIA CHRISTIAN SCHOOLS",
        "CENTRAL CATHOLIC HIGH SCHOOL PORTLA", "THE TRUST FOR PUBLIC LAND", "METROPOLITAN FAMILY SERVICES",
        # Private names that carry a public word.
        "CITY OF PORTLAND PROPERTY LLC", "CITY OF PORTLAND 2500 LLC", "METRO 1740 SE 162ND AVENUE LLC",
        "METRO 425 CONDOMINIUM OWNERS' ASSOC", "METRO EAST WEB ACADEMY", "CLACKAMAS COUNTY BANK",
        "CHEVRON USA INC", "UNITED STATES BAKERY", "UNITED STATES NATIONAL BANK OF OREG", "STATE OFFICE BUILDING LLC",
        "OREGON STATE PUBLIC INTEREST RESEAR", "FEDERAL NATIONAL MORTGAGE ASSOCIATI", "PORTLAND METRO ARTS",
        "SPRINGWATER DEVELOPMENT LLC", "FIRE STATION NO 7 LLC", "HICKS,PATRICK L & HICKS,SUSAN J", "", None,
    ],
)
def test_a_private_name_is_in_no_group(owner: str | None) -> None:
    assert roll.owner_group(owner, roll.load_rules().tier("public_owner")) is None


# --- the list -----------------------------------------------------------------


def test_the_list_holds_only_names_the_patterns_call_public() -> None:
    public = roll.load_rules().tier("public_owner")
    rows = _rows()
    assert len(rows) > 7_000
    assert len({r["tlid"] for r in rows}) == len(rows)
    for r in rows:
        assert roll.owner_group(r["owner"], public) == r["group"], r
        # A name is cut at its first bracket (a bureau, a lessee).
        assert "(" not in r["owner"], r
        assert r["tlid"] == r["tlid"].rstrip() and r["tlid"], r


def test_the_tier_reads_the_list_whole() -> None:
    public = roll.load_rules().tier("public_owner")
    assert public.owners == {r["tlid"]: r["group"] for r in _rows()}
    assert public.owners[CITY_LOT] == "government"
    assert public.owners[HOUSING_LOT] == "housing_authority"


def test_the_redraw_script_asks_for_every_name_a_pattern_could_keep() -> None:
    spec = importlib.util.spec_from_file_location("flats_public_owners", ROOT / "scripts" / "flats_public_owners.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.unreached(roll.load_rules().tier("public_owner")) == []


# --- the reading --------------------------------------------------------------


def test_a_bare_untaxed_lot_a_public_body_owns_is_red() -> None:
    got = roll.read(lot(), roll.load_rules())
    assert got is not None and got["category"] == "roll_public_owner"
    assert "owner of record (a public body)" in got["source"]
    assert roll.load_rules().words(got["category"]) == "public land"


def test_a_public_lot_with_a_building_stays_screened() -> None:
    """Washington's improved x1 codes stay screened (ruled 2026-10-09); so
    does a Multnomah public lot the roll shows built -- by its building area,
    or by a building value where the footprint map draws a building."""
    assert tier(BLDGVAL=9_081_720.0, TOTALVAL=9_815_500.0, footprint_sqft=52_922.2) is None
    assert tier(BLDGSQFT=42_309.0) is None
    assert tier(BLDGVAL=729_960.0, BLDGSQFT=2_050.0) is None


def test_a_vacant_class_is_bare_whatever_small_value_stands_on_it() -> None:
    # 1S1E11DC -00700 on the roll: class 700 (multi-family vacant), a
    # building value of $10,000.
    assert tier(tlid="1S1E11DC  -00700", PROP_CODE="700", BLDGVAL=10_000.0) == "public_owner"
    assert tier(PROP_CODE="100", BLDGVAL=72_280.0) == "public_owner"
    assert tier(PROP_CODE="701", BLDGVAL=72_280.0, footprint_sqft=1_800.0) is None


def test_a_public_lot_the_roll_shows_taxed_stays_screened() -> None:
    assert tier(ASSESSVAL=120_000.0) is None


def test_a_value_the_roll_does_not_carry_is_neither_taxed_nor_built() -> None:
    assert tier(ASSESSVAL=None, BLDGVAL=None, BLDGSQFT=None) == "public_owner"
    assert tier(BLDGVAL=float("nan"), BLDGSQFT=None) == "public_owner"


def test_a_lot_off_the_list_is_untouched() -> None:
    assert tier(tlid="1N1E06DD  -99999") is None
    # Exempt and bare, and not a public body's: a church's or a charity's.
    assert tier(tlid="1S2E04CB  -03900") is None


def test_the_list_is_multnomahs_only() -> None:
    assert tier(county="washington") is None
    assert tier(county="clackamas") is None


def test_a_parcel_number_is_matched_whole_spaces_and_all() -> None:
    assert tier(tlid=CITY_LOT + "  ") == "public_owner"  # the lot table pads it
    assert tier(tlid=CITY_LOT.replace("  ", " ")) is None


# --- the housing-authority switch ---------------------------------------------


def test_housing_authority_land_is_held_not_red() -> None:
    rules = roll.load_rules()
    public = rules.tier("public_owner")
    assert public.groups == {"government"} and public.held == {"housing_authority"}
    # Not ruled out by the roll, so it stays in the scan ...
    assert roll.read(lot(tlid=HOUSING_LOT), rules) is None
    # ... and the hold names the owner in the roll's words.
    why = roll.owner_hold(lot(tlid=HOUSING_LOT), rules)
    assert why == "multnomah owner of record (a housing authority), with no assessed value and no building on the roll"


def test_the_hold_takes_the_same_test_as_the_governments() -> None:
    rules = roll.load_rules()
    # A government's lot is RED, never merely held.
    assert roll.owner_hold(lot(), rules) is None
    # Taxed, or built: screened like any lot, as a government's is.
    assert roll.owner_hold(lot(tlid=HOUSING_LOT, ASSESSVAL=120_000.0), rules) is None
    assert roll.owner_hold(lot(tlid=HOUSING_LOT, BLDGVAL=350_000.0, BLDGSQFT=2_400.0), rules) is None
    # A vacant class is bare whatever small value stands on it.
    assert roll.owner_hold(lot(tlid=HOUSING_LOT, PROP_CODE="700", BLDGVAL=10_000.0), rules) is not None
    # Another county's lot of the same number is not on Multnomah's list.
    assert roll.owner_hold(lot(tlid=HOUSING_LOT, county="washington"), rules) is None
    # A value the row does not carry is neither taxed nor built: held.
    assert roll.owner_hold({"county": "multnomah", "tlid": HOUSING_LOT}, rules) is not None


@pytest.mark.parametrize(
    "answer,red,held", [("yellow", False, True), ("red", True, False), ("screened", False, False)]
)
def test_the_switch_is_one_line(tmp_path: Path, answer: str, red: bool, held: bool) -> None:
    text = roll.CONFIG.read_text(encoding="utf-8")
    on = "housing_authority: yellow"
    assert text.count(on) == 1
    (tmp_path / "roll_red.yaml").write_text(text.replace(on, f"housing_authority: {answer}"), encoding="utf-8")
    (tmp_path / LIST.name).write_text(
        f"tlid,group,owner\n{CITY_LOT},government,PORTLAND CITY OF\n{HOUSING_LOT},housing_authority,HOME FORWARD\n",
        encoding="utf-8",
    )
    rules = roll.load_rules(tmp_path / "roll_red.yaml")
    assert (tier(rules, tlid=HOUSING_LOT) == "public_owner") is red
    assert (roll.owner_hold(lot(tlid=HOUSING_LOT), rules) is not None) is held
    assert tier(rules, tlid=CITY_LOT) == "public_owner"
    assert roll.owner_hold(lot(), rules) is None


def test_a_switch_word_the_tier_does_not_know_is_refused(tmp_path: Path) -> None:
    text = roll.CONFIG.read_text(encoding="utf-8")
    (tmp_path / "roll_red.yaml").write_text(text.replace("housing_authority: yellow", "housing_authority: green"), encoding="utf-8")
    (tmp_path / LIST.name).write_text("tlid,group,owner\n", encoding="utf-8")
    with pytest.raises(ValueError, match="housing_authority"):
        roll.load_rules(tmp_path / "roll_red.yaml")


# --- the lots FOLLOWUPS 205 found green ---------------------------------------

#: (parcel, class, building value, building area) as the roll of release 7
#: holds them; every one assessed at 0.
GOVERNMENT_BARE = [
    ("1N1E06DD  -01500", "800", 0.0, 0.0),  # City of Portland
    ("1N1E08BC  -14400", "100", 0.0, 0.0),  # School District No 1
    ("1N1E22AB  -09000", "211", 0.0, 0.0),  # State of Oregon
    ("1N1E22AB  -09800", "211", 0.0, 0.0),  # State of Oregon
    ("1S1E20CB  -00400", "211", 0.0, 0.0),  # United States Postal Service
    ("1S2E03AA  -09800", "201", 0.0, 0.0),  # Multnomah County Library District
    ("1S2E12BC  -03500", "700", 0.0, 0.0),  # City of Portland
    ("1S1E11DC  -00700", "700", 10_000.0, 0.0),  # TriMet, vacant class
    ("1S1E12BC  -17700", "700", 72_280.0, 0.0),  # School District No 1, vacant class
]
HOUSING_BARE = [
    ("1N1E09CD  -19600", "701", 0.0, 0.0),
    ("1N1E14AA  -06200", "701", 0.0, 0.0),
    ("1N1E22BC  -02200", "701", 0.0, 0.0),
    ("1N2E30CC  -12100", "701", 0.0, 0.0),
    ("1N2E36DD  -02800", "701", 0.0, 0.0),
    ("1S1E23DC  -01600", "701", 0.0, 0.0),
    ("1S2E11BD  -06700", "701", 0.0, 0.0),
    ("1S2E14CC  -06600", "701", 0.0, 0.0),
    ("1S3E06AB  -11401", "701", 0.0, 0.0),
]
#: Public-owned, GREEN on run 128, and built: they stay screened.
BUILT = [
    ("1S3E07AC  -03600", "211", 729_960.0, 2_050.0, None),  # Centennial School District
    ("1S1E06CB  -02700", "211", 9_081_720.0, 0.0, 52_922.2),
    ("1S2E07BA  -08500", "701", 10_000.0, 42_309.0, None),
    ("1N1E08AC  -07000", "711", 2_704_790.0, 48_612.0, None),
]


@pytest.mark.parametrize("tlid,code,bldg,sqft", GOVERNMENT_BARE)
def test_the_bare_public_lots_that_were_green_are_red(tlid: str, code: str, bldg: float, sqft: float) -> None:
    assert tier(tlid=tlid, PROP_CODE=code, BLDGVAL=bldg, BLDGSQFT=sqft) == "public_owner"


@pytest.mark.parametrize("tlid,code,bldg,sqft", HOUSING_BARE)
def test_the_bare_housing_authority_lots_that_were_green_are_held(tlid: str, code: str, bldg: float, sqft: float) -> None:
    assert tier(tlid=tlid, PROP_CODE=code, BLDGVAL=bldg, BLDGSQFT=sqft) is None
    held = roll.owner_hold(lot(tlid=tlid, PROP_CODE=code, BLDGVAL=bldg, BLDGSQFT=sqft), roll.load_rules())
    assert held is not None and "a housing authority" in held


@pytest.mark.parametrize("tlid,code,bldg,sqft,drawn", BUILT)
def test_the_built_public_lots_stay_screened(tlid: str, code: str, bldg: float, sqft: float, drawn: float | None) -> None:
    assert roll.load_rules().tier("public_owner").owners.get(tlid) is not None
    assert tier(tlid=tlid, PROP_CODE=code, BLDGVAL=bldg, BLDGSQFT=sqft, footprint_sqft=drawn) is None


# --- a building value alone (FOLLOWUPS 64 round 5, fg5 #40) --------------------

#: The University of Oregon's lot in the Old Town campus: $8,220 of
#: improvements, no building area on the roll, no footprint on the map (the
#: occupancy build of 2026-10-01 holds 0.0). GREEN on run 134.
UO_LOT = "1N1E13BD  -09900"


def test_a_building_value_with_no_building_area_or_footprint_is_bare() -> None:
    assert tier(tlid=UO_LOT, BLDGVAL=8_220.0, footprint_sqft=0.0) == "public_owner"


def test_a_building_value_where_the_map_was_not_read_is_bare_for_the_final_reading() -> None:
    assert tier(tlid=UO_LOT, BLDGVAL=8_220.0) == "public_owner"


def test_the_pre_filter_keeps_a_valued_lot_the_map_was_not_read_for() -> None:
    row = lot(tlid=UO_LOT, BLDGVAL=8_220.0, jurisdiction="or/multnomah/portland", zone="R5")
    assert roll.read(row, roll.load_rules(), unmapped="value") is None
    assert roll.improved(row, unmapped="value")
    assert not roll.improved(row)


def test_a_footprint_the_roll_gives_no_value_leaves_the_lot_bare() -> None:
    assert tier(BLDGVAL=0.0, footprint_sqft=1_200.0) == "public_owner"


def test_a_building_area_is_built_whatever_the_map_says() -> None:
    assert tier(BLDGSQFT=2_050.0, footprint_sqft=0.0) is None


def test_an_unknown_unmapped_mode_is_refused() -> None:
    with pytest.raises(ValueError):
        roll.improved(lot(), unmapped="guess")


def test_the_housing_hold_reads_value_where_the_map_was_not_read() -> None:
    row = lot(tlid=HOUSING_LOT, BLDGVAL=50_000.0)
    assert roll.owner_hold(row, roll.load_rules()) is None
    assert roll.owner_hold({**row, "footprint_sqft": 0.0}, roll.load_rules()) is not None


# --- a public school body's campus land ------------------------------------------


def campus(**kw: Any) -> str | None:
    return tier(tlid=UO_LOT, jurisdiction="or/multnomah/portland", **kw)


def test_a_public_universitys_lot_in_a_campus_zone_is_red_built_or_taxed() -> None:
    got = roll.read(lot(tlid=UO_LOT, jurisdiction="or/multnomah/portland", zone="CI1",
                        BLDGVAL=9_000_000.0, BLDGSQFT=40_000.0, ASSESSVAL=100_000.0), roll.load_rules())
    assert got is not None and got["category"] == "roll_public_owner"
    assert "UNIVERSITY OF OREGON, a public school body" in got["source"]
    assert "zoned CI1, a campus zone" in got["source"]


@pytest.mark.parametrize("zone", ["CI2", "IR"])
def test_every_portland_campus_zone_counts(zone: str) -> None:
    assert campus(zone=zone, BLDGSQFT=40_000.0) == "public_owner"


def test_a_public_universitys_built_lot_outside_a_campus_zone_stays_screened() -> None:
    assert campus(zone="RM1", BLDGSQFT=40_000.0) is None


def test_a_campus_zone_elsewhere_is_not_portlands() -> None:
    assert tier(tlid=UO_LOT, jurisdiction="or/multnomah/gresham", zone="CI1", BLDGSQFT=40_000.0) is None


def test_a_school_districts_lot_in_a_campus_zone_is_red() -> None:
    # 1S3E07AC -03600: Centennial School District, built (BUILT above).
    centennial = "1S3E07AC  -03600"
    assert roll.load_rules().tier("public_owner").owner_names[centennial].startswith("CENTENNIAL")
    assert tier(tlid=centennial, jurisdiction="or/multnomah/portland", zone="CI2", BLDGSQFT=2_050.0) == "public_owner"
    assert tier(tlid=centennial, jurisdiction="or/multnomah/portland", zone="R5", BLDGSQFT=2_050.0) is None


def test_a_city_lot_in_a_campus_zone_is_not_school_land() -> None:
    assert tier(jurisdiction="or/multnomah/portland", zone="CI1", BLDGSQFT=40_000.0) is None


def test_the_campus_owners_name_only_public_school_bodies() -> None:
    t = roll.load_rules().tier("public_owner")
    def school(name: str) -> bool:
        return any(p.search(name) for p in t.campus_owners)
    for name in ("UNIVERSITY OF OREGON", "PORTLAND STATE UNIVERSITY", "SCHOOL DISTRICT NO 1", "SCHOOL DIST NO 3",
                 "CENTENNIAL UNIFIED SCHOOL DISTRICT ", "MT HOOD COMMUNITY COLLEGE", "PORTLAND PUBLIC SCHOOLS",
                 "OREGON HEALTH & SCIENCE UNIVERSITY", "OREGON STATE UNIVERSITY"):
        assert school(name), name
    for name in ("PORTLAND CITY OF", "MULTNOMAH COUNTY", "METRO", "UNIVERSITY OF PORTLAND", "REED COLLEGE",
                 "LEWIS & CLARK COLLEGE", "PORTLAND WATER BUREAU", "OREGON STATE OF(DEPT OF"):
        assert not school(name), name
