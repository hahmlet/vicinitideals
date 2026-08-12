"""Condo / air-parcel detection.

The bias under test: exclusion must be unambiguous. A suspicious parcel is
flagged and kept, never dropped — a false red silently deletes an acquisition
target, a false green costs one review.
"""

from __future__ import annotations

import pytest

from flats.normalize.condo import (
    ABSOLUTE_MIN_LOT_SQFT,
    CondoVerdict,
    check_condo,
    classify_frame,
)

pytestmark = pytest.mark.unit


def lot(**kw):
    base = {"area_sqft": 5000.0, "BLDGSQFT": 1800.0, "PROP_CODE": "101", "COUNTY": "M"}
    return {**base, **kw}


def test_ordinary_lot_is_land() -> None:
    assert check_condo(lot()).verdict is CondoVerdict.land
    assert check_condo(lot()).reason == ""


def test_condo_property_code_is_excluded() -> None:
    # PROP_CODE 122: 18,338 Multnomah taxlots, median area 46.7 sqft, no building.
    c = check_condo(lot(PROP_CODE="122", area_sqft=46.7, BLDGSQFT=0.0))

    assert c.verdict is CondoVerdict.excluded
    assert c.reason == "CONDO_AIR_PARCEL"
    assert not c.is_land


def test_large_condo_coded_parcel_is_suspect_not_excluded() -> None:
    # Condominium common-element land carries the same code as the unit air
    # parcels but is real, buildable ground — the R5 corpus holds one at
    # 329,000 sqft. Size, not code alone, decides.
    c = check_condo(lot(PROP_CODE="102", area_sqft=16_000.0))

    assert c.verdict is CondoVerdict.suspect
    assert c.reason == "SUSPECT_CONDO_COMMON_AREA"
    assert c.is_land


def test_condo_code_without_area_is_suspect() -> None:
    c = check_condo(lot(PROP_CODE="102", area_sqft=None))

    assert c.verdict is CondoVerdict.suspect
    assert c.reason == "SUSPECT_CONDO_UNKNOWN_AREA"


def test_condo_codes_are_scoped_to_their_county() -> None:
    # The code list is Multnomah's. Clackamas codes differently, so the same
    # digits there must not trigger an exclusion.
    assert check_condo(lot(PROP_CODE="122", COUNTY="C")).verdict is CondoVerdict.land


def test_parcel_below_physical_minimum_is_excluded() -> None:
    c = check_condo(lot(area_sqft=200.0, PROP_CODE="999"))

    assert c.verdict is CondoVerdict.excluded
    assert c.reason == "LOT_BELOW_PHYSICAL_MINIMUM"


def test_condo_code_wins_over_the_size_reason() -> None:
    # Both rules would fire on a 46 sqft condo. The code-based reason is the
    # more useful one for the ledger, so it must be checked first.
    assert check_condo(lot(area_sqft=46.7, PROP_CODE="122")).reason == "CONDO_AIR_PARCEL"


def test_physical_minimum_cannot_hide_a_real_opportunity() -> None:
    # The floor sits below every encoded fourplex minimum lot area, so nothing
    # excluded by it could have been buildable.
    assert ABSOLUTE_MIN_LOT_SQFT < 1500


def test_stacked_unit_is_suspect_not_excluded() -> None:
    # PROP_CODE 102's shape scaled above the physical floor: a parcel big enough
    # that size alone does not condemn it, carrying a building it cannot hold.
    c = check_condo(lot(area_sqft=900.0, BLDGSQFT=1800.0, PROP_CODE="999"))

    assert c.verdict is CondoVerdict.suspect
    assert c.reason == "SUSPECT_STACKED_UNIT"
    assert c.is_land, "suspicion routes to REVIEW; it must not delete the row"


def test_dense_large_lot_is_not_suspect() -> None:
    # An apartment block: high ratio, but a real lot. The size guard keeps the
    # ratio rule off it.
    assert check_condo(lot(area_sqft=9000.0, BLDGSQFT=27000.0)).verdict is CondoVerdict.land


def test_small_lot_with_ordinary_building_is_land() -> None:
    # A skinny R2.5 lot with a two-storey house — ratio below the threshold.
    assert check_condo(lot(area_sqft=1600.0, BLDGSQFT=1900.0)).verdict is CondoVerdict.land


@pytest.mark.parametrize("missing", ["area_sqft", "BLDGSQFT", "PROP_CODE", "COUNTY"])
def test_missing_columns_never_exclude(missing: str) -> None:
    row = lot()
    row[missing] = None
    # Never infer availability: a row we cannot assess is kept, at worst flagged.
    assert check_condo(row).is_land


def test_unparseable_numbers_do_not_crash() -> None:
    assert check_condo(lot(area_sqft="not a number", BLDGSQFT="")).is_land


def test_classify_frame_adds_columns() -> None:
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        [
            lot(),
            lot(PROP_CODE="122", area_sqft=46.7, BLDGSQFT=0.0),
            lot(area_sqft=900.0, BLDGSQFT=1800.0, PROP_CODE="9"),
        ]
    )

    out = classify_frame(df)

    assert list(out.condo_verdict) == ["land", "excluded", "suspect"]
    assert list(out.condo_reason) == ["", "CONDO_AIR_PARCEL", "SUSPECT_STACKED_UNIT"]
    assert len(out) == len(df), "classification never drops rows; the caller decides"
