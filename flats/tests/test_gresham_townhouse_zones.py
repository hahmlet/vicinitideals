"""Gresham's townhouse-only districts (FOLLOWUPS 109 chunk 4, 2026-10-28).

Eight districts read NP for a quadplex and P (or L) for a townhouse: the three
Civic Neighborhood sub-districts (CNTH, CNTM, CNRM), three Downtown ones (DMU,
DEM, DCL), the Rockwood Town Center (RTC) and Springwater's Townhouse
Residential district (THR-SW). Under Steph's 2026-10-15 ruling ("'Townhomes'
will have separate lots") the pod opens in each as four townhouses on four
unit lots, on the code's own townhouse rows -- and each district's own limit
on that permission rides on top of it:

* Downtown: Map 4.1140's street types bar townhouse access from some streets.
  The map is not held, so ``gresham_downtown_barred_street`` is unmeasured and
  every lot stays out of GREEN on it.
* RTC: Table 4.0420 note 3 wants a non-residential ground floor on Stark.
  ``rockwood_stark_frontage`` is read off the street network by name, the way
  CMF's corridor is.
* THR-SW: the setback row states no rear yard for a townhouse without an
  alley (Rear No Alley N/A), so only an alley-backed lot opens.

These tests pin the mechanism, not a lot count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import box, mapping

from flats.encode.readiness import quotes_the_number
from flats.geom.corridor import load_maps, named_specs
from flats.ingest.quadfit import observed_facts
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet
from flats.score.flags import Colour
from flats.tests.test_corridor_gresham import STREETS, X0, Y0, _fc, _lot, _row
from flats.tests.test_townhouse_lots import both, corpus, land_division, policies, row, wide  # noqa: F401

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
CIVIC = ("CNTH", "CNTM", "CNRM")
DOWNTOWN = ("DMU", "DEM", "DCL")
OPENED = (*CIVIC, *DOWNTOWN, "RTC", "THR-SW")


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


# --- the use gate -------------------------------------------------------------


@pytest.mark.parametrize("zone", OPENED)
def test_the_one_lot_quadplex_stays_shut(rules: RuleSet, zone: str) -> None:
    assert rules.resolve(GRESHAM, zone).values["quadplex_allowed"].value is False


@pytest.mark.parametrize("zone", (*CIVIC, *DOWNTOWN, "RTC"))
def test_the_townhouse_form_opens_on_unit_lots(rules: RuleSet, zone: str) -> None:
    got = rules.resolve(GRESHAM, zone, ("unit_lots",))
    assert got.values["quadplex_allowed"].value is True
    assert got.missing_required == (), zone


def test_downtown_street_types_close_it_again_and_unanswered_is_not_open(rules: RuleSet) -> None:
    for zone in DOWNTOWN:
        use = rules.resolve(GRESHAM, zone, ("unit_lots",)).values["quadplex_allowed"]
        assert "gresham_downtown_barred_street" in use.levers, zone
        barred = rules.resolve(GRESHAM, zone, ("unit_lots", "gresham_downtown_barred_street"))
        assert barred.values["quadplex_allowed"].value is False, zone


def test_rockwood_stark_frontage_closes_rtc(rules: RuleSet) -> None:
    on_stark = rules.resolve(GRESHAM, "RTC", ("unit_lots", "rockwood_stark_frontage"))
    assert on_stark.values["quadplex_allowed"].value is False


def test_springwater_opens_only_with_an_alley_at_the_rear(rules: RuleSet) -> None:
    assert rules.resolve(GRESHAM, "THR-SW", ("unit_lots",)).values["quadplex_allowed"].value is False
    alley = rules.resolve(GRESHAM, "THR-SW", ("unit_lots", "alley_at_rear"))
    assert alley.values["quadplex_allowed"].value is True
    assert alley.missing_required == ()
    # Rear With Alley: 8 in., stored in feet.
    assert alley.values["setback_rear_ft"].value == pytest.approx(8 / 12, abs=0.01)
    assert alley.values["min_lot_sqft"].value == 1800


# --- the townhouse rows -------------------------------------------------------


def test_civic_takes_the_strict_limb_across_its_street_types(rules: RuleSet) -> None:
    """Map 4.1242 is not held, so each setback is the largest the five street
    types print (the maximum front the smallest)."""
    for zone in CIVIC:
        got = rules.resolve(GRESHAM, zone, ("unit_lots",)).values
        assert got["setback_front_ft"].value == 10, zone
        assert got["setback_front_max_ft"].value == 10, zone
        assert got["setback_street_side_ft"].value == 10, zone
        assert got["setback_side_ft"].value == 5, zone
        assert got["setback_rear_ft"].value == 5, zone
        assert got["min_lot_width_ft"].value == 16, zone
        assert "min_lot_sqft" not in got, zone
    corner = rules.resolve(GRESHAM, "CNTH", ("unit_lots", "corner_lot")).values
    assert corner["min_lot_width_ft"].value == 25


def test_civic_heights_are_storeys_and_cnrm_takes_the_wallula_limb(gresham: Layer) -> None:
    storeys = {z: gresham.zones[z].values["max_height_stories"].value for z in CIVIC}
    assert storeys == {"CNTH": 10, "CNTM": 8, "CNRM": 4}


def test_downtown_note_11_tightens_side_and_alley_rear_by_the_neighbour(rules: RuleSet) -> None:
    for zone in DOWNTOWN:
        plain = rules.resolve(GRESHAM, zone, ("unit_lots",)).values
        assert plain["setback_side_ft"].value == 5, zone
        assert plain["setback_rear_ft"].value == 10, zone
        alley = rules.resolve(GRESHAM, zone, ("unit_lots", "alley_at_rear")).values
        assert alley["setback_rear_ft"].value == 3, zone
        abutting = rules.resolve(
            GRESHAM, zone, ("unit_lots", "alley_at_rear", "abuts_lower_density_zone")
        ).values
        assert abutting["setback_side_ft"].value == 10, zone
        assert abutting["setback_rear_ft"].value == 10, zone


def test_the_neighbour_list_is_note_11s_six_districts(gresham: Layer) -> None:
    rule = gresham.neighbours["abuts_lower_density_zone"]
    assert set(rule.true_for) == {"DRL-1", "DRL-2", "LDR-5", "LDR-7", "TR", "TLDR"}
    # Every other district the layer carries is on the false side, so a
    # Gresham neighbour is never unanswered for want of a listing.
    assert set(rule.true_for) | set(rule.false_for) == set(gresham.zones)
    assert not set(rule.true_for) & set(rule.false_for)


def test_dcl_ceiling_is_its_own_column_not_drl1s(gresham: Layer) -> None:
    assert gresham.zones["DCL"].values["max_density_du_per_acre"].value == 60
    assert gresham.zones["DMU"].values["max_density_du_per_acre"].exempt
    assert gresham.zones["DEM"].values["max_density_du_per_acre"].exempt


# --- on a lot -----------------------------------------------------------------


def test_a_civic_lot_passes_as_townhouses_with_the_land_division_flag(corpus, policies) -> None:  # noqa: F811
    one, got = both(corpus, policies, row("gresham", "CNTH", width=120.0, depth=160.0), design=wide())
    assert one.signed.colour is Colour.red
    assert any(b.check == "use" for b in one.signed.binds)
    assert got.signed.colour is Colour.green
    assert got.forms["works_as"] == "townhomes"
    assert land_division(got)


def test_a_downtown_lot_waits_on_the_street_type_map(corpus, policies) -> None:  # noqa: F811
    _, got = both(corpus, policies, row("gresham", "DMU", width=120.0, depth=160.0), design=wide())
    assert got.signed.colour is not Colour.green
    codes = {f["code"] for f in got.forms["townhomes"]["flags"]}
    assert "FACT-GRESHAM-DOWNTOWN-BARRED-STREET" in codes


def test_a_springwater_lot_without_an_alley_stays_red(corpus, policies) -> None:  # noqa: F811
    _, got = both(corpus, policies, row("gresham", "THR-SW", width=120.0, depth=160.0), design=wide())
    assert got.signed.colour is Colour.red
    assert "use" in {b["check"] for b in got.forms["townhomes"]["binds"]}


# --- Rockwood's Stark frontage, read off the street network --------------------

ON_STARK_BLOCK = box(X0 + 10_000, Y0, X0 + 10_300, Y0 + 300)
OFF_STARK_BLOCK = box(X0 + 20_000, Y0 + 5_000, X0 + 20_300, Y0 + 5_300)
ON_STARK = _lot(X0 + 10_100, Y0, {"south": True})
BEHIND_STARK = _lot(X0 + 10_100, Y0 + 200, {"north": True})
OFF_STARK = _lot(X0 + 20_100, Y0 + 5_100, {"south": True})


def _snapshot(root: Path) -> Path:
    blocks = [(ON_STARK_BLOCK, "RTC"), (OFF_STARK_BLOCK, "RTC"), (box(X0, Y0, X0 + 600, Y0 + 300), "CMF")]
    (root / "corridor_blocks_gresham.geojson").write_text(
        _fc([{"type": "Feature", "properties": {"ZONE": z}, "geometry": mapping(g)} for g, z in blocks]),
        encoding="utf-8",
    )
    (root / "rlis_streets.geojson").write_text(
        _fc(
            [
                {"type": "Feature", "properties": {"PREFIX": p, "STREETNAME": n, "FTYPE": t}, "geometry": mapping(g)}
                for p, n, t, g in STREETS
            ]
        ),
        encoding="utf-8",
    )
    return root


def _stark(lot, maps, zone: str = "RTC"):
    return observed_facts(_row(lot, zone), corridors=maps).get("rockwood_stark_frontage")


def test_the_stark_spec_is_rtc_on_se_stark() -> None:
    (spec,) = [s for s in named_specs() if s.key == "rockwood_stark"]
    assert spec.condition == "rockwood_stark_frontage"
    assert spec.zones == {"RTC"}
    assert spec.streets == ("SE STARK ST",)
    assert spec.blocks == "corridor_blocks_gresham"
    assert spec.behind_frontage is False


def test_stark_frontage_is_answered_per_rtc_lot(tmp_path: Path) -> None:
    maps = load_maps(_snapshot(tmp_path))
    assert _stark(ON_STARK, maps) is True
    assert _stark(BEHIND_STARK, maps) is False
    assert _stark(OFF_STARK, maps) is False
    # Only RTC lots are asked, and CMF's corridor reads only its own blocks.
    assert _stark(ON_STARK, maps, zone="CMF") is None
    cmf = observed_facts(_row(ON_STARK, "CMF"), corridors=maps).get("civic_corridor")
    assert cmf is not True


def test_no_street_network_leaves_stark_unanswered(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    (tmp_path / "rlis_streets.geojson").unlink()
    maps = load_maps(tmp_path)
    assert _stark(ON_STARK, maps) is None


# --- reading the printed figure ----------------------------------------------


def test_a_dimension_in_inches_alone_reads_as_feet() -> None:
    line = "THR-SW 6 ft. 1 ft. N/A 5 ft. 0 ft. N/A 8 ft. 8 ft. 20 ft. N/A 8 in."
    assert quotes_the_number(line, 0.67)
    # The inches of a feet-and-inches phrase are not read alone.
    assert not quotes_the_number("a stall 8 ft. 6 in. wide", 0.5)
    assert quotes_the_number("a stall 8 ft. 6 in. wide", 8.5)


def test_a_marker_glued_before_a_second_marker_is_cut_when_its_note_is_quoted() -> None:
    text = (
        "Maximum Building Front: 1012, 16 Front: 1512, 16\n"
        "     12.   Courtyard-type developments are exempted from maximum setbacks\n"
        "     16.   Maximum front setbacks do not apply on a site once ..."
    )
    assert quotes_the_number(text, 10, glued=True)
    assert quotes_the_number(text, 15, glued=True)
    assert not quotes_the_number(text, 10)
    # A thousands comma is still one number.
    assert not quotes_the_number("7,500 square feet", 7, glued=True)
