"""King City's older residential districts as townhouses (FOLLOWUPS 109 chunk 4, 117).

KCMC 16.84.010's housing-type table has no triplex or fourplex row, so the
fourplex on one lot is refused in all six of R-9, R-12, R-15, R-24, SF and AT.
The same table prints "Single dwelling attached P P P P N P", and 16.24 defines
that dwelling as one on its own lot, "a townhome or townhouse". Under Steph's
2026-10-15 ruling ("'Townhomes' will have separate lots") the pod opens in the
five P columns as four townhouses on four unit lots, read on:

* 16.84.040's column, with its townhouse notes 1 and 2 (1,500 sq ft, 20 ft);
* 16.84.050's outdoor area and main entrance (16.94.050 in R-12);
* 16.132's parking -- no minimum, 9 by 18 stalls, 24 ft aisles -- rather than
  the Kingston Terrace figures the layer's defaults hold;
* 16.136.030 A's access for three to six attached lots: one driveway in a
  30 ft strip.

These tests pin the mechanism, not a lot count.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import quotes_the_number
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet
from flats.score.flags import Colour
from flats.tests.test_townhouse_lots import both, corpus, land_division, policies, row, wide  # noqa: F401

pytestmark = pytest.mark.unit

KING_CITY = "or/washington/king-city"
OPENED = ("R-9", "R-12", "R-15", "R-24", "AT")


@pytest.fixture(scope="module")
def king_city() -> Layer:
    return load_rules()[KING_CITY]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


# --- the use gate -------------------------------------------------------------


@pytest.mark.parametrize("zone", (*OPENED, "SF"))
def test_the_one_lot_fourplex_stays_refused(rules: RuleSet, zone: str) -> None:
    assert rules.resolve(KING_CITY, zone).values["quadplex_allowed"].value is False


@pytest.mark.parametrize("zone", OPENED)
def test_the_townhouse_form_opens_on_unit_lots_with_nothing_missing(rules: RuleSet, zone: str) -> None:
    got = rules.resolve(KING_CITY, zone, ("unit_lots",))
    assert got.values["quadplex_allowed"].value is True
    assert got.missing_required == (), zone


def test_sf_prints_n_for_attached_and_stays_shut(rules: RuleSet) -> None:
    assert rules.resolve(KING_CITY, "SF", ("unit_lots",)).values["quadplex_allowed"].value is False


def test_the_permission_quotes_the_attached_row(king_city: Layer) -> None:
    for zone in OPENED:
        (variant,) = king_city.zones[zone].values["quadplex_allowed"].variants
        assert variant.when == ("unit_lots",)
        text = _text(variant.prov.quote)
        assert "R-9 R-12 R-15 R-24 SF AT" in text, zone
        assert "Single dwelling attached P P P P N P" in text, zone


# --- the columns --------------------------------------------------------------

#: 16.84.040, column by column: front, rear, height, coverage, density floor.
COLUMNS = {
    "R-9": (12, 10, 35, 80, 7.2),
    "R-12": (10, 10, 35, 80, 9.6),
    "R-15": (15, 20, 35, 75, 12),
    "R-24": (15, 20, 45, 75, 19.2),
    "AT": (10, 20, 30, 75, 12),
}


@pytest.mark.parametrize("zone", OPENED)
def test_each_zone_reads_its_own_column_and_cites_the_figure(king_city: Layer, zone: str) -> None:
    held = king_city.zones[zone].values
    front, rear, height, cover, density = COLUMNS[zone]
    for field, want in (
        ("setback_front_ft", front),
        ("setback_rear_ft", rear),
        ("max_height_ft", height),
        ("max_impervious_pct", cover),
        ("min_density_du_per_acre", density),
        ("min_lot_sqft", 1500),
        ("min_lot_width_ft", 20),
    ):
        assert held[field].value == want, (zone, field)
        assert quotes_the_number(_text(held[field].prov.quote), want), (zone, field)


def test_the_townhouse_notes_are_quoted_with_their_figures(king_city: Layer) -> None:
    held = king_city.zones["R-9"].values
    assert "T ownhouse lots may be a minimum of one thousand five hundred square feet" in _text(
        held["min_lot_sqft"].prov.quote
    )
    assert "T ownhouse lots may have a minimum width of twenty feet" in _text(held["min_lot_width_ft"].prov.quote)


def test_note_3s_average_width_reaches_only_r9_and_r12(king_city: Layer) -> None:
    for zone in OPENED:
        got = king_city.zones[zone].values.get("min_average_lot_width_ft")
        assert (got.value if got else None) == (24 if zone in ("R-9", "R-12") else None), zone


def test_a_spelled_figure_after_its_unit_heading_is_quoted() -> None:
    """Note 3 prints its unit first: "Minimum average lot width, in feet:
    twenty-four." The quote check reads that heading form; a bare colon after
    any other words still states no figure."""
    assert quotes_the_number("3 Minimum average lot width, in feet: twenty-four.", 24)
    assert not quotes_the_number("for four years: twenty-four.", 24)


def test_at_charges_the_two_storey_side_yard(rules: RuleSet) -> None:
    assert rules.resolve(KING_CITY, "AT", ("unit_lots",)).values["setback_side_ft"].value == 5
    assert rules.resolve(KING_CITY, "AT", ("unit_lots", "multi_story")).values["setback_side_ft"].value == 10


def test_a_dash_is_no_standard_and_is_cited_on_its_row(king_city: Layer) -> None:
    for zone, field in (
        ("R-15", "min_lot_depth_ft"),
        ("R-15", "setback_side_ft"),
        ("R-24", "min_lot_depth_ft"),
        ("AT", "setback_garage_entrance_ft"),
        ("AT", "setback_street_side_ft"),
    ):
        got = king_city.zones[zone].values[field]
        assert got.exempt, (zone, field)
        assert "R-9 R-12 R-15 R-24 SF AT" in _text(got.prov.quote), (zone, field)


@pytest.mark.parametrize(("zone", "area"), [("R-9", 300), ("R-12", 200)])
def test_the_outdoor_area_is_each_lots_own(rules: RuleSet, zone: str, area: int) -> None:
    got = rules.resolve(KING_CITY, zone, ("unit_lots",)).values
    assert got["open_space_min_sqft"].value == area * 4
    assert got["private_open_space_min_dimension_ft"].value == 10
    assert got["orientation_constraint"].value == "axis_required"


# --- parking and access: 16.132 and 16.136, not Kingston Terrace ---------------


@pytest.mark.parametrize("zone", OPENED)
def test_parking_reads_16_132_not_the_kingston_terrace_defaults(rules: RuleSet, zone: str) -> None:
    older = rules.resolve(KING_CITY, zone, ("unit_lots",)).values
    terrace = rules.resolve(KING_CITY, "KTTC").values
    assert (older["parking_stall_width_ft"].value, older["parking_stall_depth_ft"].value) == (9, 18)
    assert older["parking_aisle_two_way_ft"].value == 24
    assert older["parking_min_per_unit"].value == 0
    assert older["parking_max_per_unit"].value == 1.5
    assert older["driveway_min_width_two_way_ft"].value == 30
    # the layer default still governs Kingston Terrace
    assert (terrace["parking_stall_depth_ft"].value, terrace["parking_aisle_two_way_ft"].value) == (16, 20)
    assert "driveway_min_width_two_way_ft" not in terrace


def test_the_access_strip_quotes_the_three_to_six_lot_row(king_city: Layer) -> None:
    text = _text(king_city.zones["R-24"].values["driveway_min_width_two_way_ft"].prov.quote)
    assert "attached single-family dwelling units on individual lots" in text
    assert "3—6 1 30 ft. 24 ft." in text


# --- on a lot -----------------------------------------------------------------


def test_an_r24_lot_passes_as_townhouses_with_the_land_division_flag(corpus, policies) -> None:  # noqa: F811
    one, got = both(corpus, policies, row("king_city", "R-24", width=150.0, depth=200.0), design=wide())
    assert one.signed.colour is Colour.red
    assert any(b.check == "use" for b in one.signed.binds)
    assert got.signed.colour is Colour.green
    assert got.forms["works_as"] == "townhomes"
    assert land_division(got)


def test_an_sf_lot_stays_red_on_the_use_table(corpus, policies) -> None:  # noqa: F811
    _, got = both(corpus, policies, row("king_city", "SF", width=150.0, depth=200.0), design=wide())
    assert got.signed.colour is Colour.red


def test_r9_holds_every_home_lot_to_the_24_ft_average(corpus, policies) -> None:  # noqa: F811
    """Note 3 read the stricter way: each home lot averages 24 ft, which a
    20 ft home between its party walls cannot. Whether the average is the
    row's rather than each lot's is a question for Steph; until then R-9 and
    R-12 stay red on it, never green."""
    _, got = both(corpus, policies, row("king_city", "R-9", width=150.0, depth=200.0), design=wide())
    assert got.signed.colour is Colour.red
    assert "home_lot_average_width_ft" in {b["check"] for b in got.forms["townhomes"]["binds"]}
