"""Driveway spacing in the three cities FOLLOWUPS 205 found unchecked: Canby
(CMC Table 16.46.30 and 16.10.070(B)(9)), Gladstone (GMC 17.50.040(14), its
city standards PWDS 5.0070 held since 2026-11-18) and Hillsboro (Design and Construction Standards 230.6
and Figure 230.6, by CDC 12.50.715 C.2).

None has a street-class map of its own in the corpus: each reads the county
map its county entry reads, for this check only. A cross street's half
right-of-way is 30 ft in every case below.
"""

from __future__ import annotations

import pytest

from flats.geom import driveway_spacing as ds

pytestmark = pytest.mark.unit

CANBY = "or/clackamas/canby"
GLADSTONE = "or/clackamas/gladstone"
HILLSBORO = "or/washington/hillsboro"
CITIES = (CANBY, GLADSTONE, HILLSBORO)


def _rules(layer: str) -> ds.SpacingRules:
    rules = ds.rules_for(layer)
    assert rules is not None, layer
    return rules


def _at(cross: str | None) -> list[tuple[float, float, str | None]]:
    """One intersection, its centreline at the frontage's start."""
    return [(0.0, 30.0, cross)]


# --- the config ----------------------------------------------------------


def test_each_city_borrows_its_county_map_for_this_check_only() -> None:
    from flats.ingest.sources import load_pipeline

    datasets = load_pipeline().datasets
    for layer, county_map in (
        (CANBY, "street_class_clackamas"),
        (GLADSTONE, "street_class_clackamas"),
        (HILLSBORO, "street_class_washington"),
    ):
        rules = _rules(layer)
        assert rules.map == county_map
        # Not registered to serve the city: no other reader takes the map up.
        assert layer not in datasets[county_map].serves
        assert rules.map_ruling
        # A street the map does not draw reads local only where Metro and
        # OpenStreetMap agree (ruling 2026-10-09-quiet-street-both-agree).
        assert rules.unlisted == "local"
        # Read for every lot, not only one with every frontage busy.
        assert rules.applies is None


def test_the_class_words_off_each_map() -> None:
    def words(layer: str) -> list[str | None]:
        rules = _rules(layer)
        spec = ds.spec_of(rules.map)
        return [rules.class_of_rank(r, spec) for r in sorted({*spec.rank.values(), 0})]

    # Clackamas: LOCAL, CONNECTOR (no such city class: unread), COLLECTOR,
    # MINOR ARTERIAL, MAJOR ARTERIAL.
    assert words(CANBY) == ["local", None, "collector", "arterial", "arterial"]
    assert words(GLADSTONE) == ["local", None, "collector", "arterial", "arterial"]
    # Washington: undrawn, Neighborhood Route, Collector, Arterial, Principal
    # Arterial, Freeway (unread).
    assert words(HILLSBORO) == ["local", "neighborhood_route", "collector", "arterial", "arterial", None]


def test_the_printed_figures() -> None:
    canby = _rules(CANBY)
    assert {c: r.figure_ft for c, r in canby.frontage.items()} == {"arterial": 330, "collector": 100}
    (rule,) = canby.intersections
    assert (rule.figure_ft, rule.basis, set(rule.on)) == (50, "curb_return", {"local"})
    assert set(rule.cross) == {"local", "collector", "arterial"}

    gladstone = _rules(GLADSTONE)
    assert {c: r.figure_ft for c, r in gladstone.frontage.items()} == {"arterial": 150, "collector": 75}
    assert not gladstone.unread
    (rule,) = gladstone.intersections
    assert (rule.figure_ft, rule.basis, set(rule.on)) == (35, "right_of_way_line", {"local"})
    assert set(rule.cross) == {"local", "collector", "arterial"}

    hillsboro = _rules(HILLSBORO)
    assert {c: r.figure_ft for c, r in hillsboro.frontage.items()} == {"arterial": 600, "collector": 300}
    assert sorted((r.figure_ft, r.basis) for r in hillsboro.intersections) == [
        (10, "curb_return"), (25, "right_of_way_line"), (100, "right_of_way_line"),
    ]
    by_figure = {r.figure_ft: r for r in hillsboro.intersections}
    # The 25 ft is for a Local Road across only; a Neighborhood Route across,
    # which no note names, takes the 100 ft.
    assert set(by_figure[25].cross) == {"local"}
    assert set(by_figure[100].cross) == {"neighborhood_route", "collector", "arterial"}
    assert set(by_figure[10].cross) == {"local", "neighborhood_route", "collector", "arterial"}


def test_the_hillsboro_standards_are_stored_and_print_the_figure() -> None:
    from flats.provenance.store import ProvenanceStore

    path = ProvenanceStore().text_path("or/washington/hillsboro/dcs.230.6.driveways.txt")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert "Arterial 600 ft" in lines[44]
    assert "Collector 300 ft" in lines[45]
    assert "100 feet" in " ".join(lines[27:31]) and "Collector or Arterial" in " ".join(lines[27:31])
    assert "25 feet" in " ".join(lines[31:34]) and "Local Road" in " ".join(lines[31:34])


def test_the_gladstone_standards_are_stored_and_print_the_figures() -> None:
    """PWDS 2017 Section Five, 5.0070 (printed pp.9-10), stored 2026-11-18
    from the copy Steph downloaded from the city's media library."""
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    doc = store.load("or/clackamas/gladstone/pwds.5.streets.txt")
    assert doc.url == "https://www.ci.gladstone.or.us/media/17116"
    lines = store.text_path("or/clackamas/gladstone/pwds.5.streets.txt").read_text(encoding="utf-8").splitlines()
    assert lines[438].startswith("5.0070") and "Driveways and Approaches" in lines[438]
    assert "Minimum curb cut width shall be 16 ft." in lines[461]
    assert "closer to an intersecting street" in lines[462] and "right-of-way line" in lines[463]
    assert "neighborhood route" in lines[470] and "35 ft." in lines[470]
    assert "local street" in lines[471] and "35 ft." in lines[471]
    assert "adjacent curb cuts on the same side" in lines[472]
    assert "arterial street, 150 ft." in lines[474] and "collector street, 75 ft." in lines[475]
    assert "5 ft. from the property line" in lines[479]
    assert "Transportation System Plan" in lines[225]


# --- Canby CMC Table 16.46.30 --------------------------------------------


def test_canby_bars_arterials_and_collectors() -> None:
    canby = _rules(CANBY)
    assert ds.chain_answer(2000.0, [], "arterial", canby) == ds.BLOCKED
    assert ds.chain_answer(2000.0, [], "collector", canby) == ds.BLOCKED


def test_canby_local_frontage_takes_50_ft_from_an_intersection() -> None:
    canby = _rules(CANBY)
    assert ds.chain_answer(60.0, [], "local", canby) == ds.CLEAR
    # Pass: 50 ft + 30 ft half right-of-way + 35 ft return (the stop bar is
    # on no map), then a 20 ft apron and a 5 ft inset: 140 ft.
    assert ds.chain_answer(150.0, _at("local"), "local", canby) == ds.CLEAR
    assert ds.chain_answer(150.0, _at("arterial"), "local", canby) == ds.CLEAR
    assert ds.chain_answer(120.0, _at("local"), "local", canby) == ds.UNREAD
    # Short of 50 ft from the centreline at every placement.
    assert ds.chain_answer(40.0, _at("local"), "local", canby) == ds.BLOCKED


def test_canby_industrial_streets_are_read_off_the_zoning_map() -> None:
    from flats.ingest.sources import load_pipeline
    from flats.rules.loader import load_rules as load_layers

    spec = _rules(CANBY).industrial
    assert spec is not None
    assert spec.zones == {"M-1", "M-2", "C-M"} and spec.reach_ft == 60
    dataset = load_pipeline().datasets[spec.zoning]
    assert CANBY in dataset.serves
    layer = load_layers()[CANBY]
    assert all(layer.holds(z) == z for z in spec.zones)
    # A snapshot without the zoning map is refused, as one without the class
    # map is.
    assert spec.zoning in {r.industrial.zoning for r in ds.load_rules().values() if r.industrial}


def test_a_canby_local_street_by_an_industrial_district_is_unread(monkeypatch) -> None:
    import json

    from flats.tests.test_utility_easement import X0, Y0

    edges = json.dumps(
        [
            [X0, Y0, X0 + 100, Y0, "F"],
            [X0 + 100, Y0, X0 + 100, Y0 + 200, "S"],
            [X0 + 100, Y0 + 200, X0, Y0 + 200, "R"],
            [X0, Y0 + 200, X0, Y0, "S"],
        ]
    )
    canby = _rules(CANBY)
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "local")
    assert ds.read_lot(edges, [0.0], None, None, canby)[0] == ds.UNREAD  # no zoning read
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "collector")
    assert ds.read_lot(edges, [0.0], None, None, canby)[0] == ds.BLOCKED


# --- Gladstone GMC 17.50.040(14) -----------------------------------------


def test_gladstone_bars_busy_frontages_and_holds_a_local_one_35_ft_off_the_corner() -> None:
    """PWDS 5.0070(D)(3): 150 ft (arterial) and 75 ft (collector) between
    adjacent curb cuts -- no map holds driveways, so barred. (D)(2)(e)-(f): 35 ft
    from an intersecting street's right-of-way line on a local street."""
    gladstone = _rules(GLADSTONE)
    assert ds.chain_answer(2000.0, [], "collector", gladstone) == ds.BLOCKED
    assert ds.chain_answer(2000.0, [], "arterial", gladstone) == ds.BLOCKED
    # No intersection in reach: clear.
    assert ds.chain_answer(60.0, [], "local", gladstone) == ds.CLEAR
    # Pass: 35 ft + 30 ft half right-of-way, then a 20 ft apron and a 5 ft inset.
    assert ds.chain_answer(95.0, _at("local"), "local", gladstone) == ds.CLEAR
    # A frontage whose every point is within 35 ft of the cross centreline: short.
    assert ds.chain_answer(30.0, _at("arterial"), "local", gladstone) == ds.BLOCKED
    # Between the two bounds: not shown clear, not failed.
    assert ds.chain_answer(60.0, _at("local"), "local", gladstone) == ds.UNREAD


def test_gladstone_lot_on_an_unread_street_is_held(monkeypatch) -> None:
    import json

    from flats.tests.test_utility_easement import X0, Y0

    edges = json.dumps(
        [
            [X0, Y0, X0 + 100, Y0, "F"],
            [X0 + 100, Y0, X0 + 100, Y0 + 200, "S"],
            [X0 + 100, Y0 + 200, X0, Y0 + 200, "R"],
            [X0, Y0 + 200, X0, Y0, "S"],
        ]
    )
    gladstone = _rules(GLADSTONE)
    # A local frontage is now held off the corner, which needs the street
    # centrelines: with none, unread.
    for cls, want in (("local", ds.UNREAD), ("arterial", ds.BLOCKED), ("collector", ds.BLOCKED), (None, ds.UNREAD)):
        monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules, cls=cls: cls)
        assert ds.read_lot(edges, [0.0], None, None, gladstone)[0] == want, cls


# --- Hillsboro Design and Construction Standards 230.6 -------------------


def test_hillsboro_bars_arterials_and_collectors_on_every_lot(monkeypatch) -> None:
    import json

    from flats.tests.test_utility_easement import X0, Y0

    hillsboro = _rules(HILLSBORO)
    assert ds.chain_answer(2000.0, [], "arterial", hillsboro) == ds.BLOCKED
    assert ds.chain_answer(2000.0, [], "collector", hillsboro) == ds.BLOCKED
    # A lot with ONE frontage, on an arterial: held (the FOLLOWUPS 205 lot).
    edges = json.dumps(
        [
            [X0, Y0, X0 + 100, Y0, "F"],
            [X0 + 100, Y0, X0 + 100, Y0 + 200, "S"],
            [X0 + 100, Y0 + 200, X0, Y0 + 200, "R"],
            [X0, Y0 + 200, X0, Y0, "S"],
        ]
    )
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "arterial")
    assert ds.read_lot(edges, [0.0], None, None, hillsboro)[0] == ds.BLOCKED
    # A quieter street is read against its intersections, and with no
    # centrelines to read them off it is unread, never clear.
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "neighborhood_route")
    assert ds.read_lot(edges, [0.0], None, None, hillsboro)[0] == ds.UNREAD


def test_hillsboro_local_frontage_by_a_collector_or_arterial_takes_100_ft() -> None:
    hillsboro = _rules(HILLSBORO)
    assert ds.chain_answer(60.0, [], "local", hillsboro) == ds.CLEAR
    assert ds.chain_answer(60.0, [], "neighborhood_route", hillsboro) == ds.CLEAR
    # Pass: 100 ft from the right-of-way line (30 ft out), a 20 ft apron and
    # a 5 ft inset: 155 ft.
    assert ds.chain_answer(160.0, _at("collector"), "local", hillsboro) == ds.CLEAR
    assert ds.chain_answer(120.0, _at("collector"), "local", hillsboro) == ds.UNREAD
    assert ds.chain_answer(60.0, _at("arterial"), "local", hillsboro) == ds.BLOCKED
    # A Neighborhood Route across is held to the same.
    assert ds.chain_answer(160.0, _at("neighborhood_route"), "local", hillsboro) == ds.CLEAR
    assert ds.chain_answer(120.0, _at("neighborhood_route"), "local", hillsboro) == ds.UNREAD
    # A street across the map cannot class takes the strictest, for a pass.
    assert ds.chain_answer(160.0, _at(None), "local", hillsboro) == ds.CLEAR
    assert ds.chain_answer(150.0, _at(None), "local", hillsboro) == ds.UNREAD


def test_hillsboro_local_frontage_by_a_local_street() -> None:
    hillsboro = _rules(HILLSBORO)
    # Note 3 governs the pass: 10 ft past the curb's point of curvature,
    # taken as 30 + 35 ft out, then 20 + 5: 100 ft. Note 2's 25 ft from the
    # right-of-way corner (30 + 25 + 25 = 80 ft) is inside it.
    assert ds.chain_answer(105.0, _at("local"), "local", hillsboro) == ds.CLEAR
    assert ds.chain_answer(105.0, _at("local"), "neighborhood_route", hillsboro) == ds.CLEAR
    assert ds.chain_answer(95.0, _at("local"), "local", hillsboro) == ds.UNREAD
    assert ds.chain_answer(40.0, _at("local"), "local", hillsboro) == ds.UNREAD
    assert ds.chain_answer(20.0, _at("local"), "local", hillsboro) == ds.BLOCKED


# --- the screen ----------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    from flats.score import relief, slack

    return slack.load_policy(), relief.load_policy()


def _screen(corpus, policies, row):
    from flats.designs.model import load_catalog
    from flats.ingest.quadfit import lot_from_row, screen_lot

    (s,) = screen_lot(
        lot_from_row(row, corpus.layers),
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=policies[0],
        relief=policies[1],
        step_deg=30.0,
    )
    return s


@pytest.mark.parametrize(
    "jurisdiction,zone",
    [("canby", "R-1.5"), ("gladstone", "MR"), ("hillsboro", "R-7")],
)
def test_a_lot_nothing_read_is_held_and_a_clear_one_is_not(corpus, policies, jurisdiction, zone) -> None:
    from flats.score import flags as flag_plan
    from flats.score.screen import DRIVEWAY_SPACING_BLOCKED, DRIVEWAY_SPACING_UNREAD
    from flats.tests.test_utility_easement import lot_row

    held = _screen(corpus, policies, lot_row(120.0, 200.0, jurisdiction=jurisdiction, zone=zone, driveway_spacing=None))
    assert held.signed.colour is not flag_plan.Colour.green
    assert DRIVEWAY_SPACING_UNREAD in held.signed.reasons
    blocked = _screen(
        corpus, policies,
        lot_row(120.0, 200.0, jurisdiction=jurisdiction, zone=zone, driveway_spacing=ds.BLOCKED,
                driveway_spacing_why="collector"),
    )
    assert blocked.signed.colour is not flag_plan.Colour.green
    assert DRIVEWAY_SPACING_BLOCKED in blocked.signed.reasons
    clear = _screen(corpus, policies, lot_row(120.0, 200.0, jurisdiction=jurisdiction, zone=zone, driveway_spacing=ds.CLEAR))
    assert DRIVEWAY_SPACING_UNREAD not in clear.signed.reasons
    assert DRIVEWAY_SPACING_BLOCKED not in clear.signed.reasons


def test_a_canby_lot_with_a_clear_frontage_is_still_green(corpus, policies) -> None:
    from flats.score import flags as flag_plan
    from flats.tests.test_utility_easement import lot_row

    clear = _screen(corpus, policies, lot_row(120.0, 200.0, jurisdiction="canby", zone="R-1.5", driveway_spacing=ds.CLEAR))
    assert clear.signed.colour is flag_plan.Colour.green
