"""``flats.tax`` -- Measure 5 compression, Measure 50 values, the partition reset.

The Gresham bills are worked by hand from the 2025-26 rates of code area 026
(the city's largest, 17,644 lots) and pinned to the cent.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from flats.tax import impact, oregon, rates
from flats.tax.oregon import Levy

EDU = "education"
GG = "general_government"


def _lv(district: str, kind: str, category: str, rate: str) -> Levy:
    return Levy(district, kind, category, D(rate))


SIMPLE = (
    _lv("school", "permanent", EDU, "4.0000"),
    _lv("school", "local_option", EDU, "1.5000"),
    _lv("school", "bond", EDU, "2.0000"),
    _lv("city", "permanent", GG, "6.0000"),
    _lv("county", "permanent", GG, "3.0000"),
    _lv("city", "bond", GG, "1.0000"),
)


def _line(bill: oregon.Bill, district: str, kind: str) -> D:
    return next(t.billed for t in bill.lines if t.levy.district == district and t.levy.kind == kind)


def test_no_compression_when_av_is_well_below_rmv():
    b = oregon.bill(D("100000"), D("300000"), SIMPLE)
    assert b.compression == D("0.00")
    assert b.total == D("1750.00")  # 17.5 per 1,000 x 100
    assert b.local_option == D("150.00")
    assert b.headline == D("1600.00")
    assert b.district("city") == D("700.00")


def test_education_compression_takes_the_local_option_first_and_can_wipe_it_out():
    # education non-bond 5.5 x 200 = 1,100 against a 5 x 200 = 1,000 limit: the
    # 100 comes out of the 300 local option, the permanent levy is untouched.
    b = oregon.bill(D("200000"), D("200000"), SIMPLE[:3])
    assert _line(b, "school", "local_option") == D("200.00")
    assert _line(b, "school", "permanent") == D("800.00")
    # at RMV 160,000 the limit is 800: the excess of 300 takes all of the option
    # and leaves the permanent levy exactly at the limit.
    b = oregon.bill(D("200000"), D("160000"), SIMPLE[:3])
    assert _line(b, "school", "local_option") == D("0.00")
    assert _line(b, "school", "permanent") == D("800.00")


def test_permanent_levies_compress_proportionally_once_options_are_gone():
    # general government 9 x 200 = 1,800 against 10 x 150 = 1,500: no option,
    # so both permanent levies keep 1,500 / 1,800 of themselves.
    b = oregon.bill(D("200000"), D("150000"), SIMPLE[3:])
    assert _line(b, "city", "permanent") == D("1000.00")
    assert _line(b, "county", "permanent") == D("500.00")
    assert b.compression == D("300.00")


def test_bonds_are_never_compressed():
    b = oregon.bill(D("200000"), D("100000"), SIMPLE)
    assert _line(b, "school", "bond") == D("400.00")
    assert _line(b, "city", "bond") == D("200.00")
    edu = sum(t.billed for t in b.lines if t.levy.category == EDU and t.levy.kind != "bond")
    assert edu == D("500.00")  # exactly the $5 limit on 100,000


def test_av_is_capped_by_rmv_and_grows_three_percent():
    assert oregon.assessed_value(D("250000"), D("200000")) == D("200000")
    assert oregon.av_path(D("100000"), D("106000"), 4) == [D("100000"), D("103000"), D("106000"), D("106000")]
    # the MAV keeps growing under the cap: once RMV rises again AV follows the MAV
    assert oregon.next_mav(D("106000"), D("106090")) == D("109180")


def test_partition_resets_land_mav_to_land_rmv_times_cpr():
    # ORS 308.156(5)(b) + OAR 150-308-0190(1): the old lot's MAV is irrelevant.
    roll = impact.Roll(D("400000"), D("0"), D("400000"), D("90000"))
    levies = (_lv("city", "permanent", GG, "1.0000"),)
    out = impact.pod(roll, levies, "city", D("0.540"), D("300000"), units=4)
    # each lot: land 100,000 x .54 + building 200,000 x .54 = 162,000
    assert out.av == D("648000")
    assert out.rmv == D("1200000")
    assert out.city == D("648.00")
    assert oregon.partitioned_land_mav(D("100000"), D("0.540")) == D("54000")


def test_demolition_keeps_the_lands_share_of_mav():
    # OAR 150-308-0120's own example: MAV 90,000, RMV 100,000, house 75,000.
    assert oregon.demolished_mav(D("90000"), D("25000"), D("100000")) == D("22500")


def test_new_house_is_demolished_land_mav_plus_house_times_cpr():
    roll = impact.Roll(D("200000"), D("150000"), D("350000"), D("175000"))
    levies = (_lv("city", "permanent", GG, "1.0000"),)
    out = impact.new_house(roll, levies, "city", D("0.540"), D("500000"))
    # 175,000 x 200/350 = 100,000 + 500,000 x .54 = 270,000
    assert out.av == D("370000")
    assert out.rmv == D("700000")
    assert "land_mav_prorated_from_av" in out.notes


def test_cpr_must_not_exceed_one():
    with pytest.raises(ValueError):
        oregon.new_value_mav(D("1000"), D("1.2"))


GRESHAM = rates.for_county("multnomah", "2025-26")


def test_every_gresham_code_area_reconciles_and_splits_urban_renewal():
    assert GRESHAM.cpr_residential == D("0.540")
    assert set(GRESHAM.code_areas) == {"026", "047", "137", "383", "386", "394", "402", "901", "902", "903", "904"}
    for code, levies in GRESHAM.code_areas.items():
        city = [lv for lv in levies if lv.district == "city_of_gresham"]
        assert {lv.kind for lv in city} == {"permanent", "local_option"}, code
        assert {lv.category for lv in levies if lv.kind == "urban_renewal"} == {EDU, GG}, code
    assert GRESHAM.levies("26") == GRESHAM.levies("026")
    assert GRESHAM.levies("001") is None


def test_gresham_026_bill_by_hand_uncompressed():
    b = oregon.bill(D("200000"), D("400000"), GRESHAM.levies("026"))
    assert b.total == D("4069.92")  # 20.3496 x 200
    assert b.compression == D("0.00")
    assert b.local_option == D("299.20")  # (1.35 + .096 + .05) x 200
    assert b.headline == D("3770.72")
    assert b.district("city_of_gresham") == D("683.26")
    assert b.district("city_of_gresham", local_option=True) == D("270.00")


def test_gresham_026_bill_by_hand_compressed_both_categories():
    # AV = RMV = 300,000. Education 5.4761 x 300 = 1,642.83 > 1,500 and has no
    # option: every education levy keeps 1,500 / 1,642.83. General government
    # 10.9390 x 300 = 3,281.70 > 3,000: the 281.70 comes out of the 448.80 of
    # options, permanent levies untouched. Each line worked by hand, rounded
    # half up.
    b = oregon.bill(D("300000"), D("300000"), GRESHAM.levies("026"))
    got = {(t.levy.district, t.levy.kind, t.levy.category): t.billed for t in b.lines}
    assert got[("multnomah_esd", "permanent", EDU)] == D("118.52")
    assert got[("gresham_barlow_sd10", "permanent", EDU)] == D("1239.97")
    assert got[("mt_hood_cc", "permanent", EDU)] == D("127.37")
    assert got[("urban_renewal_gresham", "urban_renewal", EDU)] == D("14.13")
    assert got[("gresham_barlow_sd10", "bond", EDU)] == D("816.21")
    assert got[("city_of_gresham", "permanent", GG)] == D("1024.89")
    assert got[("city_of_gresham", "local_option", GG)] == D("150.79")
    assert got[("metro", "local_option", GG)] == D("10.72")
    assert got[("multnomah_county", "local_option", GG)] == D("5.58")
    assert got[("multnomah_county", "permanent", GG)] == D("1578.24")
    assert b.total == D("5680.33")
    assert b.local_option == D("167.09")


# --- the snapshot's own arithmetic ---------------------------------------------

from flats.tax import snapshot  # noqa: E402


def test_house_value_is_median_rate_times_median_size():
    hv = snapshot.house_value(
        [(D("400000"), D("2000")), (D("300000"), D("1500")), (D("660000"), D("2200")), (D("0"), D("1800"))]
    )
    assert hv.sample == 3  # the zero-value record is dropped
    assert hv.per_sqft == D("200")  # 200, 200, 300
    assert hv.sqft == D("2000")
    assert hv.rmv == D("400000")


def test_green_source_names_which_screen_said_green():
    assert snapshot.green_source(True, True) == "both"
    assert snapshot.green_source(True, False) == "quadfit_only"
    assert snapshot.green_source(False, True) == "flats_only"
    assert snapshot.green_source(False, False) is None


def test_price_lot_prices_all_four_and_skips_what_it_cannot_price():
    roll = impact.Roll(D("200000"), D("150000"), D("350000"), D("175000"))
    kw = dict(city="city_of_gresham", cpr=D("0.540"), house_rmv=D("500000"), band=(D("275000"), D("450000")))
    row, notes = snapshot.price_lot(roll, GRESHAM.levies("026"), **kw)
    assert all(row[c] is not None for c in snapshot.COLUMNS)
    # the pod at the high end: 4 x 450,000 x .54 = 972,000 of AV
    assert row["c_high_av"] == D("972000")
    assert row["c_high_total"] > row["b_total"] > row["a_total"]
    _, notes = snapshot.price_lot(roll, None, **kw)
    assert notes == {"skipped": "taxcode_not_in_rate_file"}
    _, notes = snapshot.price_lot(None, GRESHAM.levies("026"), **kw)
    assert notes == {"skipped": "no_roll_values"}


def test_summary_names_both_sets_and_the_multiples():
    roll = impact.Roll(D("200000"), D("150000"), D("350000"), D("175000"))
    kw = dict(city="city_of_gresham", cpr=D("0.540"), house_rmv=D("500000"), band=(D("275000"), D("450000")))
    row, notes = snapshot.price_lot(roll, GRESHAM.levies("026"), **kw)
    rows = [
        {"green_source": "both", **row, "notes": notes},
        {"green_source": "quadfit_only", **dict.fromkeys(snapshot.COLUMNS), "notes": {"skipped": "no_av"}},
    ]
    params = {
        "jurisdiction": "or/multnomah/gresham", "tax_year": "2025-26", "created": "2026-09-23", "run_id": 12,
        "units": 4, "band": {"low": 275000, "high": 450000}, "cpr": "0.540",
        "house": {"rmv": 500000, "derivation": "test"},
    }
    text = snapshot.summarize(rows, params)
    assert "## FLATS if-signed green: 1 lots, 1 priced" in text
    assert "## quadfit green: 2 lots, 1 priced" in text
    assert "Pod high / today" in text and "Pod low / new house" in text
    assert "ILLUSTRATIVE" in text
    assert "- no_av: 1" in text
