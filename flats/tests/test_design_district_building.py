"""Design-district rules about the building itself (FOLLOWUPS 109 chunk 3).

Two standards a handful of design districts print and no base zone does:

* ``min_roof_pitch_in_12`` -- a floor under the primary roof's pitch, or a
  flat roof refused outright. The pod's roof is flat (Steph 2026-10-21,
  rulings.yaml ``2026-10-21-pod-roof-flat``: "the intent is to. So this
  would be a red flag"), so it misses every instance (``roof_pitch``).
* ``max_mass_footprint_sqft`` -- Oregon City's concept plan massing rule: a
  residence over 1,200 sq ft must break into secondary masses of 600 or less
  under separate roof-lines (OCMC 17.21.040.A, 17.22.040.A). The pod is one
  box under one roof, 2,000 sq ft or more (``mass_footprint``).

And the Oregon City areas that carry them: the Park Place and South End
concept plans, and the historic overlay district (17.40.030; 17.40.060.A
allows no new construction there without a certificate of appropriateness
from the Historic Review Board, so the lot is RED).
"""

from __future__ import annotations

import pytest
import shapely
import yaml

from flats.designs.model import Design, load_catalog
from flats.encode.load import load_trusted
from flats.geom.drawn import load_area
from flats.ingest.quadfit import observed_facts
from flats.rules.conditions import CONDITIONS, DRAWN_CONDITIONS
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import Colour
from flats.score.screen import CHECK_FIELD
from flats.tests.test_quadfit_bridge import row
from flats.tests.test_round2_rulings import facts, rules, run

pytestmark = pytest.mark.unit

OC = "or/clackamas/oregon-city"
AREAS = {
    "oregon_city_park_place": "or/clackamas/oregon-city/park-place-concept-plan.geojson",
    "oregon_city_south_end": "or/clackamas/oregon-city/south-end-concept-plan.geojson",
    "oregon_city_historic_overlay": "or/clackamas/oregon-city/historic-overlay.geojson",
}


def check(result, name: str):
    return next((c for c in result.checks if c.check == name), None)


# --- the fields and the checks ------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind", "is_maximum", "check_name"),
    [
        ("min_roof_pitch_in_12", "ratio", False, "roof_pitch"),
        ("max_mass_footprint_sqft", "area_sqft", True, "mass_footprint"),
    ],
)
def test_the_fields_are_optional_and_each_has_its_check(name, kind, is_maximum, check_name) -> None:
    f = field(name)
    assert f.kind == kind and f.is_maximum is is_maximum
    assert name in OPTIONAL_FIELDS
    assert CHECK_FIELD[check_name] == name


def test_both_catalogued_pods_state_a_flat_roof() -> None:
    catalog = load_catalog()
    for pod in ("pod56x36", "pod80x25"):
        assert catalog.latest(pod).roof_pitch_in_12 == 0


def test_a_pitched_roof_rule_turns_the_pod_red() -> None:
    got = run(facts(), rules(min_roof_pitch_in_12=4))
    assert got.colour is Colour.red
    c = check(got, "roof_pitch")
    assert c is not None and c.observed == 0 and c.threshold == 4 and c.slack < 0


def test_a_zone_with_no_roof_rule_runs_no_roof_check() -> None:
    got = run(facts(), rules())
    assert got.colour is Colour.green
    assert check(got, "roof_pitch") is None


def test_a_design_that_states_no_roof_is_not_measured() -> None:
    from flats.score import relief, slack
    from flats.score.screen import screen
    from flats.tests.test_round2_rulings import DESIGN, fit

    silent = DESIGN.model_copy(update={"roof_pitch_in_12": None})
    got = screen(
        rules(min_roof_pitch_in_12=4),
        facts(),
        silent,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )
    assert check(got, "roof_pitch") is None
    assert "roof_pitch" in got.unchecked


def test_a_pitched_pod_clears_the_rule() -> None:
    body = yaml.safe_load(
        """
        version: 1
        label: Pitched pod
        typology: townhome_rear_court
        footprint: {width_ft: 56, depth_ft: 36}
        units: 4
        stories: 2
        height_ft: 26
        roof_pitch_in_12: 6
        parking: {stalls_per_unit: 1.0, config: rear_court}
        delivery: {method: panelized}
        """
    )
    assert Design(**{**body, "id": "pitched"}).roof_pitch_in_12 == 6
    with pytest.raises(ValueError):
        Design(**{**body, "id": "bad", "roof_pitch_in_12": -1})


def test_the_massing_cap_is_measured_a_unit() -> None:
    # Steph 2026-10-22: each dwelling unit is a "residence" (OCMC 17.04.1021),
    # so the 1,200 sq ft cap reads a unit's ground floor, about 504 sq ft.
    got = run(facts(), rules(max_mass_footprint_sqft=1200))
    c = check(got, "mass_footprint")
    assert c is not None and c.observed == 56 * 36 / 4 and c.slack > 0
    assert got.colour is Colour.green
    smaller = run(facts(), rules(max_mass_footprint_sqft=400))
    assert smaller.colour is Colour.red
    assert check(smaller, "mass_footprint").slack < 0


# --- the Oregon City areas ------------------------------------------------------


def test_the_three_areas_are_registered_drawn_conditions() -> None:
    assert set(AREAS) <= set(DRAWN_CONDITIONS)
    for name in AREAS:
        assert CONDITIONS[name].assume is None


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def test_oregon_city_declares_the_three_areas(corpus) -> None:
    declared = {a.condition: a for a in corpus[OC].drawn_areas.values()}
    assert {c: a.file for c, a in declared.items()} == AREAS
    assert {"R-10", "R-8", "R-5"} <= set(declared["oregon_city_park_place"].zones)
    assert {"R-10", "R-8"} <= set(declared["oregon_city_south_end"].zones)
    assert {"R-6", "R-3.5", "R-2", "MUC-1", "MUD"} <= set(declared["oregon_city_historic_overlay"].zones)


def test_the_historic_file_holds_all_three_city_layers() -> None:
    data = load_area(AREAS["oregon_city_historic_overlay"])
    for part in (
        "or/clackamas/oregon-city/canemah-historic-district.geojson",
        "or/clackamas/oregon-city/mcloughlin-conservation-district.geojson",
        "or/clackamas/oregon-city/barlow-trail-corridor.geojson",
    ):
        piece = load_area(part)
        assert data.buffer(1).contains(piece)


@pytest.mark.parametrize("zone", ["R-10", "R-8", "R-6", "R-5", "R-3.5", "R-2"])
def test_the_concept_plans_reach_the_pod_and_nothing_outside_them(corpus, zone) -> None:
    rs = RuleSet(corpus)
    outside = rs.resolve(OC, zone)
    assert outside.get("max_mass_footprint_sqft") is None
    assert outside.get("min_roof_pitch_in_12") is None
    park = rs.resolve(OC, zone, ["oregon_city_park_place"])
    assert park.get("max_mass_footprint_sqft") == 1200
    assert park.get("min_roof_pitch_in_12") == 5
    south = rs.resolve(OC, zone, ["oregon_city_south_end"])
    assert south.get("max_mass_footprint_sqft") == 1200
    assert south.get("min_roof_pitch_in_12") is None


@pytest.mark.parametrize("zone", ["R-10", "R-8", "R-6", "R-3.5", "R-2", "MUC-1", "MUD"])
def test_the_historic_overlay_refuses_the_pod(corpus, zone) -> None:
    rs = RuleSet(corpus)
    assert rs.resolve(OC, zone).get("quadplex_allowed") is True
    assert rs.resolve(OC, zone, ["oregon_city_historic_overlay"]).get("quadplex_allowed") is False


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


@pytest.mark.parametrize("condition", sorted(AREAS))
def test_a_lot_inside_each_area_is_inside_and_one_far_away_is_not(layers, condition) -> None:
    area = load_area(AREAS[condition])
    biggest = max(getattr(area, "geoms", [area]), key=lambda g: g.area)
    inside = biggest.representative_point().buffer(3)
    minx, miny, _, _ = area.bounds
    outside = shapely.box(minx - 3000, miny - 3000, minx - 2900, miny - 2900)
    zone = "R-6"

    def oc(lot) -> dict:
        return observed_facts(
            row(jurisdiction="oregon_city", zone=zone, lot_wkb=shapely.to_wkb(lot)), layers
        )

    assert oc(inside)[condition] is True
    assert oc(outside)[condition] is False


# --- the roof rules and the other chunk-3 district standards, per place ------


@pytest.mark.parametrize(
    ("layer", "zone", "conditions", "pitch"),
    [
        ("or/multnomah/fairview", "VSF", [], 4),
        ("or/multnomah/fairview", "VTH", [], 4),
        ("or/multnomah/fairview", "VA", [], 4),
        ("or/multnomah/fairview", "VMU", [], 1),
        ("or/clackamas/_unincorporated", "VR57", [], 1),
        ("or/clackamas/_unincorporated", "VR45", [], 1),
        ("or/clackamas/_unincorporated", "VA", [], 1),
        ("or/clackamas/happy-valley", "VTH", ["unit_lots"], 1),
        ("or/clackamas/sandy", "R-1", [], 3),
        ("or/clackamas/sandy", "R-2", [], 3),
        ("or/clackamas/sandy", "R-3", [], 3),
        ("or/clackamas/west-linn", "R-10", ["willamette_historic_district"], 6),
        ("or/clackamas/west-linn", "R-5", ["willamette_historic_district"], 6),
        ("or/clackamas/wilsonville", "OTR", [], 4),
    ],
)
def test_each_roof_rule_resolves_to_its_printed_pitch(corpus, layer, zone, conditions, pitch) -> None:
    got = RuleSet(corpus).resolve(layer, zone, conditions)
    assert got.get("min_roof_pitch_in_12") == pitch
    assert run(facts(), rules(min_roof_pitch_in_12=pitch)).colour is Colour.red


@pytest.mark.parametrize(
    ("layer", "zone"),
    [
        ("or/clackamas/west-linn", "R-10"),
        ("or/clackamas/happy-valley", "VTH"),
    ],
)
def test_a_roof_rule_scoped_to_a_district_or_a_form_stays_off_elsewhere(corpus, layer, zone) -> None:
    assert RuleSet(corpus).resolve(layer, zone).get("min_roof_pitch_in_12") is None


def test_wood_village_town_center_holds_the_stricter_ground_floor_height(corpus) -> None:
    got = RuleSet(corpus).resolve("or/multnomah/wood-village", "TC")
    assert got.get("min_ground_story_ft") == 16
    assert run(facts(), rules(min_ground_story_ft=16)).colour is Colour.red


def test_wilsonville_old_town_takes_the_design_book_height(corpus) -> None:
    got = RuleSet(corpus).resolve("or/clackamas/wilsonville", "OTR")
    assert got.get("max_height_ft") == 25


@pytest.mark.parametrize("zone", ["TO:R24-40", "TO:R40-80", "TO:BUS"])
def test_washington_county_transit_districts_take_431_open_space_off_site(corpus, zone) -> None:
    # 431-7.1 B(1) lets the common open space sit within 1,300 ft's walk,
    # and Steph ruled 2026-10-22 that passes: the lot owes none of it.
    got = RuleSet(corpus).resolve("or/washington/_unincorporated", zone)
    assert got.get("open_space_min_sqft") is None
    assert got.get("open_space_min_dimension_ft") is None


def test_washington_county_transit_business_holds_431_frontage(corpus) -> None:
    got = RuleSet(corpus).resolve("or/washington/_unincorporated", "TO:BUS")
    assert got.get("building_frontage_min_pct") == 90
    assert got.get("building_frontage_min_pct_least") == 75
    assert got.get("building_frontage_less_drive") is True


def test_readiness_reads_a_roof_rule_in_the_code_s_own_words() -> None:
    from flats.encode.readiness import quotes_the_number, states_a_roof_rule

    ban = "Hipped, gambrel, or gabled roofs are required. Flat roofs are prohibited."
    assert states_a_roof_rule(ban, "min_roof_pitch_in_12", 1)
    assert states_a_roof_rule("Flat roofs are not permitted except", "min_roof_pitch_in_12 [unit_lots]", 1)
    assert not states_a_roof_rule(ban, "min_roof_pitch_in_12", 4)
    assert not states_a_roof_rule(ban, "max_height_ft", 1)
    assert not states_a_roof_rule("Flat roofs are allowed with a cornice", "min_roof_pitch_in_12", 1)
    ratio = "Primary roofs shall be pitched at a minimum ratio\nof five-twelfths, except"
    assert states_a_roof_rule(ratio, "min_roof_pitch_in_12", 5)
    assert not states_a_roof_rule(ratio, "min_roof_pitch_in_12", 6)
    # And the thousands a concept plan spells out.
    line = "footprints over one thousand two\nhundred square feet"
    assert quotes_the_number(line, 1200)
    assert not quotes_the_number(line, 1300)
