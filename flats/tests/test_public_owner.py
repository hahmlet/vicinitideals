"""Multnomah's public land is RED by owner of record (FOLLOWUPS 205).

Steph RULED 2026-10-06 public and institutional land red. Washington
County's roll applies it by code (``public_land``: the vacant exempt codes
940, 950 ...; the improved x1 codes stay screened). Multnomah's roll holds no
such codes, so 36 government-owned and 27 housing-authority lots were GREEN
on run 128. The ``public_owner`` tier gives Multnomah the same answer off a
checked-in list of the lots whose owner of record is a public body.
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
    does a Multnomah public lot the roll shows built -- by value or by area,
    for Multnomah holds one without the other."""
    assert tier(BLDGVAL=9_081_720.0, TOTALVAL=9_815_500.0) is None
    assert tier(BLDGSQFT=42_309.0) is None
    assert tier(BLDGVAL=729_960.0, BLDGSQFT=2_050.0) is None


def test_a_vacant_class_is_bare_whatever_small_value_stands_on_it() -> None:
    # 1S1E11DC -00700 on the roll: class 700 (multi-family vacant), a
    # building value of $10,000.
    assert tier(tlid="1S1E11DC  -00700", PROP_CODE="700", BLDGVAL=10_000.0) == "public_owner"
    assert tier(PROP_CODE="100", BLDGVAL=72_280.0) == "public_owner"
    assert tier(PROP_CODE="701", BLDGVAL=72_280.0) is None


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


def test_housing_authority_land_is_public_while_the_switch_is_on() -> None:
    rules = roll.load_rules()
    assert "housing_authority" in rules.tier("public_owner").groups
    got = roll.read(lot(tlid=HOUSING_LOT), rules)
    assert got is not None and "a housing authority" in got["source"]


def test_the_switch_is_one_line(tmp_path: Path) -> None:
    text = roll.CONFIG.read_text(encoding="utf-8")
    on = "housing_authority_is_public: true"
    assert text.count(on) == 1
    (tmp_path / "roll_red.yaml").write_text(text.replace(on, "housing_authority_is_public: false"), encoding="utf-8")
    (tmp_path / LIST.name).write_text(
        f"tlid,group,owner\n{CITY_LOT},government,PORTLAND CITY OF\n{HOUSING_LOT},housing_authority,HOME FORWARD\n",
        encoding="utf-8",
    )
    off = roll.load_rules(tmp_path / "roll_red.yaml")
    assert off.tier("public_owner").groups == {"government"}
    assert tier(off, tlid=HOUSING_LOT) is None
    assert tier(off, tlid=CITY_LOT) == "public_owner"


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
    ("1S3E07AC  -03600", "211", 729_960.0, 2_050.0),  # Centennial School District
    ("1S1E06CB  -02700", "211", 9_081_720.0, 0.0),
    ("1S2E07BA  -08500", "701", 10_000.0, 42_309.0),
    ("1N1E08AC  -07000", "711", 2_704_790.0, 48_612.0),
]


@pytest.mark.parametrize("tlid,code,bldg,sqft", GOVERNMENT_BARE + HOUSING_BARE)
def test_the_bare_public_lots_that_were_green_are_red(tlid: str, code: str, bldg: float, sqft: float) -> None:
    assert tier(tlid=tlid, PROP_CODE=code, BLDGVAL=bldg, BLDGSQFT=sqft) == "public_owner"


@pytest.mark.parametrize("tlid,code,bldg,sqft", BUILT)
def test_the_built_public_lots_stay_screened(tlid: str, code: str, bldg: float, sqft: float) -> None:
    assert roll.load_rules().tier("public_owner").owners.get(tlid) is not None
    assert tier(tlid=tlid, PROP_CODE=code, BLDGVAL=bldg, BLDGSQFT=sqft) is None
