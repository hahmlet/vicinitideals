"""Gresham's townhouse-only districts (FOLLOWUPS 109 chunk 4, 2026-10-28).

Eight districts read NP for a quadplex and P (or L) for a townhouse: the three
Civic Neighborhood sub-districts (CNTH, CNTM, CNRM), three Downtown ones (DMU,
DEM, DCL), the Rockwood Town Center (RTC) and Springwater's Townhouse
Residential district (THR-SW). Under Steph's 2026-10-15 ruling ("'Townhomes'
will have separate lots") the pod opens in each as four townhouses on four
unit lots, on the code's own townhouse rows -- and each district's own limit
on that permission rides on top of it:

* Downtown: Map 4.1140's street types bar townhouse access from some streets.
  The map is traced (flats.geom.street_types): ``gresham_downtown_barred_street``
  is True for a lot whose only streets bar it, False where a street that bars
  nothing or a rear alley gives a way in, and unanswered -- out of GREEN --
  where a street line has no traced centreline beside it.
* RTC: Table 4.0420 note 3 wants a non-residential ground floor on Stark.
  ``rockwood_stark_frontage`` is read off the street network by name, the way
  CMF's corridor is.
* THR-SW: the setback row states no rear yard for a townhouse without an
  alley (Rear No Alley N/A). Steph 2026-10-28, "I'm good with yellow": every
  unit lot opens, and one with no alley along its rear is held open by name
  on ``no_alley_at_rear`` -- YELLOW at best, never GREEN.

These tests pin the mechanism, not a lot count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import box, mapping

from flats.encode.readiness import quotes_the_number
from flats.geom.corridor import load_maps, named_specs
from flats.ingest.quadfit import NO_REAR_ALLEY, observed_facts
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


def test_springwater_opens_on_unit_lots_and_its_rear_yard_turns_on_the_alley(rules: RuleSet) -> None:
    for held in (("unit_lots",), ("unit_lots", "alley_at_rear"), ("unit_lots", NO_REAR_ALLEY)):
        got = rules.resolve(GRESHAM, "THR-SW", held)
        assert got.values["quadplex_allowed"].value is True, held
        assert got.missing_required == (), held
        # Rear With Alley: 8 in., stored in feet -- the only rear yard stated.
        assert got.values["setback_rear_ft"].value == pytest.approx(8 / 12, abs=0.01)
        assert got.values["min_lot_sqft"].value == 1800
    rear = rules.resolve(GRESHAM, "THR-SW", ("unit_lots",)).values["setback_rear_ft"]
    # A qualifier, not a number: the code states no rear yard without an alley.
    assert NO_REAR_ALLEY in rear.levers
    assert rear.unencoded == frozenset({NO_REAR_ALLEY})


def test_no_alley_at_rear_is_the_measured_negation_of_alley_at_rear() -> None:
    plain = observed_facts(row("gresham", "THR-SW"))
    assert plain["alley_at_rear"] is False
    assert plain[NO_REAR_ALLEY] is True
    alley = observed_facts(_alley_backed(row("gresham", "THR-SW")))
    assert alley["alley_at_rear"] is True
    assert alley[NO_REAR_ALLEY] is False
    # No edges, no alley record: unanswered, never a False that reads as a measurement.
    assert NO_REAR_ALLEY not in observed_facts({**row("gresham", "THR-SW"), "edges_json": "[]"})


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


def _placed(r: dict, x: float, y: float) -> dict:
    """The same lot moved so its front line's west end sits at ``(x, y)``."""
    import shapely
    from shapely import affinity

    raw = json.loads(r["edges_json"])
    dx, dy = x - raw[0][0], y - raw[0][1]
    edges = [[a + dx, b + dy, c + dx, d + dy, k] for a, b, c, d, k in raw]
    moved = {
        key: shapely.to_wkb(affinity.translate(shapely.from_wkb(r[key]), dx, dy))
        for key in ("wkb", "lot_wkb")
    }
    return {**r, "edges_json": json.dumps(edges), **moved}


def _downtown(corpus, policies, x: float, y: float, zone: str = "DMU"):  # noqa: F811
    """The townhouse form of a 120 x 160 lot of ``zone`` placed at ``(x, y)``:
    its colour, its binds and its flag codes (from the signed result where
    the bridge kept that form)."""
    r = row("gresham", zone, width=120.0, depth=160.0)
    _, got = both(corpus, policies, _placed(r, x, y), design=wide())
    if got.forms["kept"] == "townhomes":
        s = got.signed
        return s.colour, {b.check for b in s.binds}, {f.code for f in s.flags}
    form = got.forms["townhomes"]
    return (
        Colour(form["colour"]),
        {b["check"] for b in form.get("binds", ())},
        {f["code"] for f in form.get("flags", ())},
    )


def test_a_downtown_lot_the_street_type_map_does_not_place_waits_on_it(corpus, policies) -> None:  # noqa: F811
    _, got = both(corpus, policies, row("gresham", "DMU", width=120.0, depth=160.0), design=wide())
    assert got.signed.colour is not Colour.green
    codes = {f["code"] for f in got.forms["townhomes"]["flags"]}
    assert "FACT-GRESHAM-DOWNTOWN-BARRED-STREET" in codes


@pytest.mark.parametrize("zone", DOWNTOWN)
def test_a_downtown_lot_on_a_local_street_opens_as_townhouses(corpus, policies, zone: str) -> None:  # noqa: F811
    # 30 ft north of NE 8th St's centreline: Downtown Local on Map 4.1140.
    colour, binds, codes = _downtown(corpus, policies, 7_708_700.0, 675_373.0, zone)
    assert "FACT-GRESHAM-DOWNTOWN-BARRED-STREET" not in codes
    assert "use" not in binds
    assert colour is not Colour.red


@pytest.mark.parametrize("zone", DOWNTOWN)
def test_a_downtown_lot_on_an_urban_boulevard_alone_is_red(corpus, policies, zone: str) -> None:  # noqa: F811
    # 30 ft north of E Powell Blvd, no other street and no alley.
    colour, binds, codes = _downtown(corpus, policies, 7_708_000.0, 673_581.0, zone)
    assert colour is Colour.red
    assert "FACT-GRESHAM-DOWNTOWN-BARRED-STREET" not in codes
    assert "use" in binds


#: Inside THR-SW's density window: 4 units on 10,014 to 14,520 sq ft net.
SPRINGWATER = dict(width=105.0, depth=135.0)


def _alley_backed(r: dict) -> dict:
    """The same lot with an alley along its whole rear line."""
    edges = json.loads(r["edges_json"])
    edges[2][4] = "A"
    cover = [None] * len(edges)
    cover[2] = "1" * 10
    return {**r, "edges_json": json.dumps(edges), "alley_cover_json": json.dumps(cover)}


def test_a_springwater_lot_without_an_alley_is_yellow_never_green(corpus, policies) -> None:  # noqa: F811
    _, got = both(corpus, policies, row("gresham", "THR-SW", **SPRINGWATER), design=wide())
    assert got.lot.observed[NO_REAR_ALLEY] is True
    assert got.signed.colour is Colour.yellow
    assert "use" not in {b.check for b in got.signed.binds}
    assert "FACT-NO-ALLEY-AT-REAR" in {f.code for f in got.signed.flags}


def test_an_alley_backed_springwater_lot_keeps_its_path(corpus, policies) -> None:  # noqa: F811
    _, bare = both(corpus, policies, row("gresham", "THR-SW", **SPRINGWATER), design=wide())
    _, got = both(corpus, policies, _alley_backed(row("gresham", "THR-SW", **SPRINGWATER)), design=wide())
    assert got.lot.observed[NO_REAR_ALLEY] is False
    assert "FACT-NO-ALLEY-AT-REAR" not in {f.code for f in got.signed.flags}
    # The flag is the only thing between them: the alley lot is held by
    # nothing the no-alley lot is not also held by.
    assert {f.code for f in got.signed.flags} <= {f.code for f in bare.signed.flags} | {"ACCESS-ALLEY"}


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
