"""Tracts, zero-value parcels and public county codes are RED (Steph RULED 2026-10-09, FOLLOWUPS 59).

"All red": HOA tracts, common areas, open space, golf courses and parcels
the county values at $0 land + $0 building; the public county codes with
them. Churches and charities stay checked (FOLLOWUPS 47).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pd = pytest.importorskip("pandas")

from flats.geom import roll  # noqa: E402
from flats.ingest import assign as az  # noqa: E402
from flats.ingest import institutional as step  # noqa: E402

pytestmark = pytest.mark.unit

ZERO = {"LANDVAL": 0.0, "BLDGVAL": 0.0, "TOTALVAL": 0.0, "ASSESSVAL": 0.0}
WORTH = {"LANDVAL": 90_000.0, "BLDGVAL": 250_000.0, "TOTALVAL": 340_000.0, "ASSESSVAL": 300_000.0}


def lot(**kw: Any) -> dict[str, Any]:
    return {"county": "washington", "tlid": "1S101AA01100", "PROP_CODE": "100", "site_address": "123 SW MAIN ST", **WORTH, **kw}


def tier(**kw: Any) -> str | None:
    got = roll.read(lot(**kw), roll.load_rules())
    return got["category"].removeprefix(roll.PREFIX) if got else None


# --- the ruling, as the config holds it -------------------------------------


def test_the_four_tiers_steph_ruled_are_on() -> None:
    on = {t.key: t.enabled for t in roll.load_rules().tiers}
    assert on == {"public_land": True, "tract": True, "open_space": True, "no_address": True}


@pytest.mark.parametrize(
    "code", ["911", "981", "980", "910", "900", "901", "100", "400", "921", "941", "943", "951", "961", "971", "991", "993"]
)
def test_churches_charities_student_housing_rural_tracts_and_x1_codes_are_not_public_land(code: str) -> None:
    """OAR 150-308-0310: 91x church, 98x benevolent, 90x student housing stay
    checked; class 4 is rural acreage, not an HOA tract. The x1 codes carry
    values, buildings and addresses (Steph RULED 2026-10-09: screened)."""
    assert tier(PROP_CODE=code) is None


@pytest.mark.parametrize("code", ["920", "930", "940", "950", "960", "970", "990"])
def test_the_public_codes_of_washington_are_red(code: str) -> None:
    assert tier(PROP_CODE=code) == "public_land"


def test_a_public_code_is_read_only_where_the_county_uses_the_code_book() -> None:
    """Multnomah and Clackamas rolls hold no 9xx codes; a 940 there is not
    read as a city's."""
    assert tier(county="multnomah", PROP_CODE="940") is None
    assert tier(county="clackamas", PROP_CODE="940") is None


# --- zero value ----------------------------------------------------------------


def test_a_worth_something_lot_is_untouched_whatever_its_number() -> None:
    assert tier(tlid="1S134BC90000") is None


def test_the_tract_number_alone_is_nothing_without_zero_value() -> None:
    """341 Washington lots numbered 9xxxx are townhomes with a roll value."""
    assert tier(tlid="1S136CA90311", PROP_CODE="102", area_sqft=1000.0) is None


@pytest.mark.parametrize("tlid", ["1S134BC90000", "1N334DC90000", "37E04  80000", "21E05AANONTL", "1S2E13BC -TR-A"])
def test_zero_value_with_a_tract_number_is_red(tlid: str) -> None:
    assert tier(tlid=tlid, PROP_CODE="000", **ZERO) == "tract"


def test_zero_value_open_space_and_recreation_codes_are_red() -> None:
    assert tier(PROP_CODE="800", **ZERO) == "open_space"
    assert tier(PROP_CODE="035", **ZERO) == "open_space"


def test_zero_value_with_no_street_address_is_red() -> None:
    assert tier(site_address=None, **ZERO) == "no_address"
    assert tier(site_address="NO SITUS", **ZERO) == "no_address"
    assert tier(site_address="LEVY CODE 1234", **ZERO) == "no_address"


def test_zero_value_with_a_real_street_address_is_screened_normally() -> None:
    """Steph RULED 2026-10-09: no red, no flag. A lot the county has not
    valued yet looks exactly like this."""
    assert tier(**ZERO) is None


@pytest.mark.parametrize(
    "values",
    [
        {"LANDVAL": 0.0, "BLDGVAL": 0.0, "TOTALVAL": 0.0, "ASSESSVAL": 5000.0},
        {"LANDVAL": 0.0, "BLDGVAL": 0.0, "TOTALVAL": 4000.0, "ASSESSVAL": 0.0},
        {"LANDVAL": 0.0, "BLDGVAL": 0.0, "TOTALVAL": 0.0, "ASSESSVAL": None},
        {"LANDVAL": None, "BLDGVAL": None, "TOTALVAL": None, "ASSESSVAL": None},
    ],
)
def test_a_value_the_roll_does_not_show_as_zero_is_not_zero(values: dict[str, Any]) -> None:
    """Specially assessed farm and forest land has zero land and building
    beside a real assessed value; a value the roll lacks is unknown."""
    assert tier(site_address=None, tlid="1S134BC90000", **values) is None


# --- a lot with new houses around it stays screened ---------------------------------


def _box(x: float, y: float, size: float = 50.0) -> bytes:
    from shapely import wkb as shapely_wkb
    from shapely.geometry import box

    return shapely_wkb.dumps(box(x, y, x + size, y + size))


def _block(county: str, stem: str, years: list[Any], at: list[float] | None = None) -> list[dict[str, Any]]:
    """Houses on one tax map page; ``at`` is each house's west edge in feet
    (the bare lot sits at 0..50), default 100 ft apart from the bare lot."""
    return [
        {"county": county, "tlid": f"{stem}{i:05d}", "YEARBUILT": y, "site_address": "1 MAIN ST", "wkb": _box(at[n] if at else 100.0 + 10 * n, 0), **WORTH}
        for n, (i, y) in enumerate(zip(range(100, 100 + len(years)), years))
    ]


def _bare(tlid: str, county: str = "washington") -> dict[str, Any]:
    return lot(county=county, tlid=tlid, PROP_CODE="000", site_address=None, YEARBUILT=0, wkb=_box(0, 0), **ZERO)


def _read_with(row: dict[str, Any], others: list[dict[str, Any]]) -> str | None:
    rules = roll.load_rules()
    got = roll.read(row, rules, roll.built_lots([row, *others], rules))
    return got["category"].removeprefix(roll.PREFIX) if got else None


@pytest.mark.parametrize(
    ("county", "stem", "bare"),
    [
        ("washington", "1S214CD", "1S214CD27300"),
        ("clackamas", "22E09BD", "22E09BD02100"),
        ("multnomah", "1S2E08AD", "1S2E08AD  -11200"),
    ],
)
def test_the_block_is_the_tax_map_page_in_every_countys_number_format(county: str, stem: str, bare: str) -> None:
    assert roll.block({"county": county, "tlid": bare}) == (county, stem)


def test_the_distance_rule_is_500_feet() -> None:
    assert roll.load_rules().tier("no_address").built_within_ft == 500


def test_three_lots_built_since_2021_in_the_block_keep_a_bare_lot_checked() -> None:
    neighbours = _block("washington", "1S214CD", [2021, 2022, 2025, 1990])
    assert _read_with(_bare("1S214CD27300"), neighbours) is None


def test_two_new_lots_are_not_enough() -> None:
    neighbours = _block("washington", "1S214CD", [2021, 2022, 2020, 1990])
    assert _read_with(_bare("1S214CD27300"), neighbours) == "no_address"


def test_the_bare_lots_own_year_does_not_count() -> None:
    row = {**_bare("1S214CD27300"), "YEARBUILT": 2023}
    assert _read_with(row, _block("washington", "1S214CD", [2021, 2022])) == "no_address"


def test_new_houses_in_another_block_or_county_do_not_count() -> None:
    far = _block("washington", "1S214CC", [2022, 2022, 2022]) + _block("clackamas", "1S214CD", [2022, 2022, 2022])
    assert _read_with(_bare("1S214CD27300"), far) == "no_address"


def test_houses_are_measured_edge_to_edge_not_centre_to_centre() -> None:
    # West edges at 550: the nearest edge is 500 ft from the bare lot's east edge (50), the centres 575 ft apart.
    near = _block("washington", "1S214CD", [2022] * 3, at=[550.0] * 3)
    assert _read_with(_bare("1S214CD27300"), near) is None


def test_a_house_501_feet_away_does_not_count() -> None:
    mixed = _block("washington", "1S214CD", [2022] * 3, at=[100.0, 100.0, 551.0])
    assert _read_with(_bare("1S214CD27300"), mixed) == "no_address"


def test_three_houses_on_the_page_but_far_away_spare_nothing() -> None:
    assert _read_with(_bare("1S214CD27300"), _block("washington", "1S214CD", [2022] * 5, at=[3000.0] * 5)) == "no_address"


def test_a_bare_lot_with_no_geometry_stays_red() -> None:
    neighbours = _block("washington", "1S214CD", [2022] * 4)
    for wkb in (None, float("nan"), b"not a geometry", b""):
        assert _read_with({**_bare("1S214CD27300"), "wkb": wkb}, neighbours) == "no_address"


def test_a_house_with_no_geometry_is_not_counted() -> None:
    neighbours = _block("washington", "1S214CD", [2022] * 4)
    neighbours[0]["wkb"] = None
    neighbours[1]["wkb"] = b"junk"
    assert _read_with(_bare("1S214CD27300"), neighbours) == "no_address"


@pytest.mark.parametrize("years", [[None, None, None, None], [0, 0, 0, 0], ["", "n/a", 9999, 20210], [float("nan")] * 4])
def test_a_year_the_roll_does_not_hold_spares_nothing(years: list[Any]) -> None:
    assert _read_with(_bare("1S214CD27300"), _block("washington", "1S214CD", years)) == "no_address"


def test_a_lot_table_with_no_year_column_leaves_the_lot_red() -> None:
    rows = [{k: v for k, v in r.items() if k != "YEARBUILT"} for r in _block("washington", "1S214CD", [2022] * 4)]
    assert _read_with({k: v for k, v in _bare("1S214CD27300").items() if k != "YEARBUILT"}, rows) == "no_address"


def test_without_the_block_counts_a_bare_lot_is_red() -> None:
    assert roll.read(_bare("1S214CD27300"), roll.load_rules()) is not None


def test_new_houses_do_not_spare_a_tract_or_public_land() -> None:
    neighbours = _block("washington", "1S214CD", [2022] * 5)
    assert _read_with({**_bare("1S214CD90000"), "PROP_CODE": "000"}, neighbours) == "tract"
    assert _read_with({**_bare("1S214CD27300"), "PROP_CODE": "940"}, neighbours) == "public_land"


# --- the reading step and assign -------------------------------------------------


def _bridge(tmp_path: Path, rows: list[dict[str, Any]], meta: dict[str, Any]) -> Path:
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    pd.DataFrame([{**{c: None for c in az.ROW_COLUMNS}, **r} for r in rows]).to_parquet(bridge / "lots.parquet", index=False)
    (bridge / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return bridge


def _normalized(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    normalized = tmp_path / "normalized"
    normalized.mkdir()
    base = {"jurisdiction": "or/a", "zone": "R5", "zone_raw": "R5", "area_sqft": 5000.0, "gate": None, "site_address": "1 MAIN ST"}
    pd.DataFrame([{**base, **WORTH, "PROP_CODE": "100", **r} for r in rows]).to_parquet(normalized / "lots.parquet", index=False)
    return normalized


def test_assign_answers_a_roll_lot_red_with_no_reading_file(tmp_path: Path) -> None:
    bridge = _bridge(
        tmp_path,
        [
            {"TLID": "LEFTOVER", "design": "d1", "triage": "green", "if_signed": "green", "colour": "green"},
            {"TLID": "HOUSE", "design": "d1", "triage": "green", "if_signed": "green", "colour": "green"},
        ],
        {},
    )
    normalized = _normalized(
        tmp_path,
        [
            {"county": "washington", "tlid": "LEFTOVER", "PROP_CODE": "000", "site_address": None, **ZERO},
            {"county": "washington", "tlid": "HOUSE"},
            {"county": "washington", "tlid": "CITY", "PROP_CODE": "940", **ZERO},
        ],
    )
    meta = az.assign(normalized, bridge, tmp_path / "out")
    frame = pd.read_parquet(tmp_path / "out" / "lots.parquet")
    assert frame["TLID"].tolist().count("LEFTOVER") == 1, "the scan row for the leftover must go"
    by = frame.set_index("TLID")
    for tlid in ("LEFTOVER", "CITY"):
        row = by.loc[tlid]
        assert (row["triage"], row["if_signed"], row["colour"], row["reasons"]) == ("red", "red", "red", "COUNTY_ROLL_RED")
    assert by.loc["HOUSE"]["colour"] == "green"
    bind = json.loads(by.loc["CITY"]["binds"])[0]
    assert bind["check"] == "roll_red"
    assert bind["source"] == "public land, per the washington roll code 940 (city)"
    assert meta["assign"]["roll_by_tier"] == {"public_land": 1, "no_address": 1} or meta["assign"]["roll_by_tier"] == {"no_address": 1, "public_land": 1}
    assert "COUNTY_ROLL_RED, by tier (red, out of the scan)" in (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")


def test_assign_and_the_reading_step_spare_a_bare_lot_among_new_houses(tmp_path: Path) -> None:
    houses = [{"county": "washington", "tlid": f"1S214CD0{i}000", "YEARBUILT": 2022, "wkb": _box(100.0 + 10 * i, 0)} for i in range(3)]
    bare = {"county": "washington", "tlid": "1S214CD27300", "PROP_CODE": "000", "site_address": None, "wkb": _box(0, 0), **ZERO}
    bridge = _bridge(
        tmp_path,
        [{"TLID": "1S214CD27300", "design": "d1", "triage": "green", "if_signed": "green", "colour": "green"}],
        {},
    )
    az.assign(_normalized(tmp_path, [bare, *houses]), bridge, tmp_path / "out")
    frame = pd.read_parquet(tmp_path / "out" / "lots.parquet").set_index("TLID")
    assert frame.loc["1S214CD27300"]["colour"] == "green"
    lots = pd.DataFrame([{**bare, "YEARBUILT": 0}, *[{**h, "PROP_CODE": "100", "site_address": "1 MAIN ST", **WORTH} for h in houses]])
    assert len(step.measure_roll(lots)) == 0


def test_the_reading_step_writes_roll_lots_so_the_bridge_skips_them() -> None:
    lots = pd.DataFrame(
        [
            {"county": "washington", "tlid": "LEFTOVER", "PROP_CODE": "000", "site_address": None, **ZERO},
            {"county": "washington", "tlid": "HOUSE", "PROP_CODE": "100", "site_address": "1 MAIN ST", **WORTH},
            {"county": "washington", "tlid": "SHARED", "PROP_CODE": "000", "site_address": None, **ZERO},
            {"county": "clackamas", "tlid": "SHARED", "PROP_CODE": "100", "site_address": "1 MAIN ST", **WORTH},
        ]
    )
    frame = step.measure_roll(lots)
    assert sorted(zip(frame["county"], frame["TLID"], frame["category"])) == [
        ("washington", "LEFTOVER", "roll_no_address"),
        ("washington", "SHARED", "roll_no_address"),
    ]
    frame = step.mark_whole(frame, lots["tlid"])
    # SHARED names a lot in two counties and only one is roll land: the bridge keys on TLID alone.
    assert dict(zip(frame["TLID"], frame["whole_tlid"])) == {"SHARED": False, "LEFTOVER": True}


def test_a_lot_the_map_already_holds_keeps_the_map_reading() -> None:
    lots = pd.DataFrame([{"county": "washington", "tlid": "T", "PROP_CODE": "000", "site_address": None, **ZERO}])
    assert len(step.measure_roll(lots, {("washington", "T")})) == 0
