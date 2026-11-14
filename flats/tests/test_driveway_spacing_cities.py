"""Driveway spacing in the cities FOLLOWUPS 178 found unchecked: Gresham,
Oregon City, West Linn, Milwaukie, Fairview, Sherwood and Wilsonville.

Each city's figures are the printed ones (flats/config/driveway_spacing.yaml);
the measurement is :mod:`flats.geom.driveway_spacing`'s. A cross street's
half right-of-way is 30 ft in every case below.
"""

from __future__ import annotations

import json

import pytest

from flats.geom import driveway_spacing as ds
from flats.tests.test_utility_easement import X0, Y0

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
OREGON_CITY = "or/clackamas/oregon-city"
WEST_LINN = "or/clackamas/west-linn"
MILWAUKIE = "or/clackamas/milwaukie"
FAIRVIEW = "or/multnomah/fairview"
SHERWOOD = "or/washington/sherwood"
WILSONVILLE = "or/clackamas/wilsonville"
CITIES = (GRESHAM, OREGON_CITY, WEST_LINN, MILWAUKIE, FAIRVIEW, SHERWOOD, WILSONVILLE)


def _rules(layer: str) -> ds.SpacingRules:
    rules = ds.rules_for(layer)
    assert rules is not None, layer
    return rules


def _at(cross: str | None) -> list[tuple[float, float, str | None]]:
    """One intersection, its centreline at the frontage's start."""
    return [(0.0, 30.0, cross)]


# --- the config ----------------------------------------------------------


def test_every_city_has_an_entry_on_its_own_map() -> None:
    from flats.ingest.sources import load_pipeline

    datasets = load_pipeline().datasets
    for layer in CITIES:
        rules = _rules(layer)
        assert rules.map in datasets and layer in datasets[rules.map].serves, layer


def test_every_unread_class_and_cross_is_a_named_class() -> None:
    for layer, rules in ds.load_rules().items():
        named = {*rules.classes.values(), *([rules.unlisted] if rules.unlisted else [])}
        assert set(rules.unread) <= named, layer
        assert not set(rules.unread) & set(rules.frontage), layer
        for r in rules.intersections:
            assert r.unread_cross <= named, (layer, r)
            if r.unread_cross:
                assert r.unread_quote and r.unread_cite, (layer, r)


def test_the_printed_figures() -> None:
    gresham = _rules(GRESHAM)
    by_cross = {frozenset(r.cross): r for r in gresham.intersections}
    assert by_cross[frozenset({"major_arterial", "standard_arterial"})].figure_ft == 100
    assert by_cross[frozenset({"local", "collector", "minor_arterial"})].figure_ft == 45
    assert all(r.basis == "curb_return" for r in gresham.intersections)
    assert set(gresham.unread) == {"minor_arterial", "standard_arterial", "major_arterial"}

    oc = _rules(OREGON_CITY)
    assert {next(iter(r.on)): r.figure_ft for r in oc.intersections} == {
        "arterial": 175, "collector": 100, "local": 25,
    }
    assert not oc.frontage

    wl = _rules(WEST_LINN)
    assert {k: v.figure_ft for k, v in wl.frontage.items()} == {
        "neighborhood_route": 50, "collector": 75, "arterial": 150,
    }
    (local,) = wl.intersections
    assert local.figure_ft == 50 and local.basis == "right_of_way_line"

    mw = _rules(MILWAUKIE)
    assert {k: v.figure_ft for k, v in mw.frontage.items()} == {"collector": 300, "arterial": 600}
    assert not mw.intersections

    fv = _rules(FAIRVIEW)
    assert set(fv.unread) == {"collector", "arterial"}
    (local,) = fv.intersections
    assert local.figure_ft == 50 and local.unread_cross == {"collector", "arterial"}

    sw = _rules(SHERWOOD)
    assert sw.frontage["collector"].figure_ft == 100
    assert sw.frontage["arterial"].figure_ft is None
    assert set(sw.unread) == {"neighborhood_route"}
    (local,) = sw.intersections
    assert local.figure_ft == 10 and local.basis == "curb_return"

    wv = _rules(WILSONVILLE)
    assert wv.applies is not None and wv.applies.when == "every_frontage_busy"
    assert {k: v.figure_ft for k, v in wv.frontage.items()} == {"collector": 100, "arterial": 600}


def test_the_class_words_off_each_map() -> None:
    def words(layer: str) -> list[str | None]:
        rules = _rules(layer)
        spec = ds.spec_of(rules.map)
        return [rules.class_of_rank(r, spec) for r in sorted(set(spec.rank.values()))]

    # Local, Minor / Standard / Major Collector, Minor / Standard / Major
    # Arterial, Principal Arterial (ODOT), Freeway (ODOT).
    assert words(GRESHAM) == [
        "local", "collector", "collector", "collector",
        "minor_arterial", "standard_arterial", "major_arterial", None, None,
    ]
    assert words(OREGON_CITY) == ["local", "collector", "arterial", "arterial", None]
    assert words(WEST_LINN) == ["local", "neighborhood_route", "collector", "arterial", "arterial", None]
    assert words(MILWAUKIE) == ["local", "neighborhood_route", "collector", "arterial"]
    assert words(FAIRVIEW) == ["local", "collector", "collector", "arterial", "arterial", None]
    assert words(SHERWOOD) == ["local", "neighborhood_route", "collector", "arterial", "arterial"]
    assert words(WILSONVILLE) == ["local", "collector", "arterial", "arterial"]


# --- Gresham PWS 6.03 ----------------------------------------------------


def test_gresham_arterial_frontage_is_unread_whatever_its_length() -> None:
    g = _rules(GRESHAM)
    for cls in ("minor_arterial", "standard_arterial", "major_arterial"):
        assert ds.chain_answer(2000.0, [], cls, g) == ds.UNREAD


def test_gresham_local_frontage_by_a_standard_arterial() -> None:
    g = _rules(GRESHAM)
    # Pass: 100 ft + 30 ft half right-of-way + 35 ft return = 165 ft, then a
    # 20 ft apron and a 5 ft inset: 190 ft.
    assert ds.chain_answer(200.0, _at("standard_arterial"), "local", g) == ds.CLEAR
    # A centreline 100 ft out fits on 120 ft, the pass does not: unread.
    assert ds.chain_answer(120.0, _at("standard_arterial"), "local", g) == ds.UNREAD
    # 60 ft: short of 100 ft at every placement.
    assert ds.chain_answer(60.0, _at("major_arterial"), "local", g) == ds.BLOCKED


def test_gresham_local_frontage_by_a_local_street_takes_45_ft() -> None:
    g = _rules(GRESHAM)
    # 45 + 30 + 35 = 110, apron and inset 135.
    assert ds.chain_answer(140.0, _at("local"), "local", g) == ds.CLEAR
    assert ds.chain_answer(120.0, _at("minor_arterial"), "collector", g) == ds.UNREAD
    assert ds.chain_answer(40.0, _at("local"), "local", g) == ds.BLOCKED
    # An ODOT street across (unread) is the strictest, for a pass only.
    assert ds.chain_answer(140.0, _at(None), "local", g) == ds.UNREAD


def test_gresham_mid_block_lot_clears() -> None:
    assert ds.chain_answer(60.0, [], "local", _rules(GRESHAM)) == ds.CLEAR


# --- Oregon City 16.12.035.A-B -------------------------------------------


def test_oregon_city_holds_the_pod_to_the_street_corner_distance() -> None:
    oc = _rules(OREGON_CITY)
    # Arterial: 175 + 30 + 20 + 5 = 230.
    assert ds.chain_answer(300.0, _at("local"), "arterial", oc) == ds.CLEAR
    assert ds.chain_answer(150.0, _at("local"), "arterial", oc) == ds.BLOCKED
    # Collector: 100 ft.
    assert ds.chain_answer(160.0, _at("local"), "collector", oc) == ds.CLEAR
    assert ds.chain_answer(90.0, _at("local"), "collector", oc) == ds.BLOCKED
    # Local: 25 + 30 + 20 + 5 = 80.
    assert ds.chain_answer(100.0, _at("collector"), "local", oc) == ds.CLEAR
    assert ds.chain_answer(60.0, _at("local"), "local", oc) == ds.UNREAD
    assert ds.chain_answer(20.0, _at("local"), "local", oc) == ds.BLOCKED


# --- West Linn 48.060 and TSP Table 15 -----------------------------------


def test_west_linn_bars_the_busier_classes() -> None:
    wl = _rules(WEST_LINN)
    for cls in ("neighborhood_route", "collector", "arterial"):
        assert ds.chain_answer(2000.0, [], cls, wl) == ds.BLOCKED


def test_west_linn_local_frontage_takes_50_ft() -> None:
    wl = _rules(WEST_LINN)
    # 50 + 30 + 20 + 5 = 105.
    assert ds.chain_answer(120.0, _at("arterial"), "local", wl) == ds.CLEAR
    assert ds.chain_answer(100.0, _at("local"), "local", wl) == ds.UNREAD
    assert ds.chain_answer(40.0, _at("local"), "local", wl) == ds.BLOCKED


# --- Milwaukie 12.16.040 -------------------------------------------------


def test_milwaukie_bars_collectors_and_arterials_only() -> None:
    mw = _rules(MILWAUKIE)
    assert ds.chain_answer(2000.0, [], "collector", mw) == ds.BLOCKED
    assert ds.chain_answer(2000.0, [], "arterial", mw) == ds.BLOCKED
    # (B)(5)(a)'s 45 ft relieves an existing lot by its own words.
    assert ds.chain_answer(30.0, _at("arterial"), "local", mw) == ds.CLEAR
    assert ds.chain_answer(30.0, _at("local"), "neighborhood_route", mw) == ds.CLEAR


# --- Fairview 19.162.020(G) ----------------------------------------------


def test_fairview_busy_frontage_is_unread() -> None:
    fv = _rules(FAIRVIEW)
    assert ds.chain_answer(2000.0, [], "collector", fv) == ds.UNREAD
    assert ds.chain_answer(2000.0, [], "arterial", fv) == ds.UNREAD


def test_fairview_local_frontage() -> None:
    fv = _rules(FAIRVIEW)
    # By a local street: 50 + 30 + 20 + 5 = 105.
    assert ds.chain_answer(120.0, _at("local"), "local", fv) == ds.CLEAR
    assert ds.chain_answer(40.0, _at("local"), "local", fv) == ds.BLOCKED
    # By a collector (a stop or signal may stand there; its TSP figure is
    # not held): unread within 150 + 30 + 25 = 205 ft ...
    assert ds.chain_answer(120.0, _at("collector"), "local", fv) == ds.UNREAD
    assert ds.chain_answer(250.0, _at("arterial"), "local", fv) == ds.CLEAR
    # ... and failed only on the code's own 50 ft.
    assert ds.chain_answer(40.0, _at("collector"), "local", fv) == ds.BLOCKED


def test_fairview_holds_every_corner_lot(monkeypatch) -> None:
    # Ruling 2026-11-14-fairview-hold-every-corner: a stop-sign corner is not
    # mapped, so a corner lot is never clear, even on local streets with no
    # intersection in reach; a mid-block lot so placed still clears.
    fv = _rules(FAIRVIEW)
    assert fv.corner_hold is not None
    assert fv.corner_hold.ruling == "2026-11-14-fairview-hold-every-corner"
    corner = json.dumps(
        [
            [X0, Y0, X0 + 300, Y0, "F"],
            [X0 + 300, Y0, X0 + 300, Y0 + 300, "S"],
            [X0 + 300, Y0 + 300, X0, Y0 + 300, "R"],
            [X0, Y0 + 300, X0, Y0, "F"],
        ]
    )
    midblock = json.dumps(
        [
            [X0, Y0, X0 + 300, Y0, "F"],
            [X0 + 300, Y0, X0 + 300, Y0 + 300, "S"],
            [X0 + 300, Y0 + 300, X0, Y0 + 300, "R"],
            [X0, Y0 + 300, X0, Y0, "S"],
        ]
    )
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "local")
    monkeypatch.setattr(ds, "chain_junctions", lambda *a, **k: [])
    network = object()
    assert ds.read_lot(midblock, [0.0], network, None, fv)[0] == ds.CLEAR
    answer, why = ds.read_lot(corner, [0.0, 90.0], network, None, fv)
    assert answer == ds.UNREAD and "corner lot" in why
    # A bend that may be two streets is held the same way.
    assert ds.read_lot(corner, [0.0, 25.0], network, None, fv)[0] == ds.UNREAD
    # Only Fairview holds every corner: the same corner clears in Oregon City.
    assert ds.read_lot(corner, [0.0, 90.0], network, None, _rules(OREGON_CITY))[0] == ds.CLEAR
    assert all(_rules(c).corner_hold is None for c in CITIES if c != FAIRVIEW)


# --- Sherwood 16.106.040.M.2 ---------------------------------------------


def test_sherwood_classes() -> None:
    sw = _rules(SHERWOOD)
    assert ds.chain_answer(2000.0, [], "collector", sw) == ds.BLOCKED
    assert ds.chain_answer(2000.0, [], "arterial", sw) == ds.BLOCKED
    assert ds.chain_answer(2000.0, [], "neighborhood_route", sw) == ds.UNREAD


def test_sherwood_local_frontage() -> None:
    sw = _rules(SHERWOOD)
    # By a local street: 10 + 30 + 35 + 20 + 5 = 100.
    assert ds.chain_answer(110.0, _at("local"), "local", sw) == ds.CLEAR
    # 10 ft centreline to centreline fails no frontage long enough to read.
    assert ds.chain_answer(60.0, _at("local"), "local", sw) == ds.UNREAD
    # By a collector: the standing queue holds it unread within 150 + 30 + 35.
    assert ds.chain_answer(110.0, _at("collector"), "local", sw) == ds.UNREAD
    assert ds.chain_answer(260.0, _at("neighborhood_route"), "local", sw) == ds.CLEAR


# --- Wilsonville 4.113(.14)D.4.c.ii --------------------------------------


def _corner() -> str:
    return json.dumps(
        [
            [X0, Y0, X0 + 100, Y0, "F"],
            [X0 + 100, Y0, X0 + 100, Y0 + 100, "S"],
            [X0 + 100, Y0 + 100, X0, Y0 + 100, "R"],
            [X0, Y0 + 100, X0, Y0, "F"],
        ]
    )


def _midblock() -> tuple[str, list[float]]:
    edges = [
        [X0, Y0, X0 + 100, Y0, "F"],
        [X0 + 100, Y0, X0 + 100, Y0 + 200, "S"],
        [X0 + 100, Y0 + 200, X0, Y0 + 200, "R"],
        [X0, Y0 + 200, X0, Y0, "S"],
    ]
    return json.dumps(edges), [0.0]


def test_wilsonville_reaches_only_a_lot_with_every_frontage_busy(monkeypatch) -> None:
    wv = _rules(WILSONVILLE)
    midblock, bearings = _midblock()
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "arterial")
    assert ds.read_lot(midblock, bearings, None, None, wv)[0] == ds.CLEAR
    assert ds.read_lot(_corner(), [0.0, 90.0], None, None, wv)[0] == ds.BLOCKED
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "local")
    assert ds.read_lot(_corner(), [0.0, 90.0], None, None, wv)[0] == ds.CLEAR
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: None)
    assert ds.read_lot(_corner(), [0.0, 90.0], None, None, wv)[0] == ds.UNREAD


# --- the lot answer ------------------------------------------------------


def test_an_unread_frontage_reads_through_read_lot(monkeypatch) -> None:
    midblock, bearings = _midblock()
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "standard_arterial")
    answer, why = ds.read_lot(midblock, bearings, None, None, _rules(GRESHAM))
    assert answer == ds.UNREAD and "not measured" in why


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
    [
        ("gresham", "LDR-7"),
        ("oregon_city", "R-5"),
        ("west_linn", "R-10"),
        ("milwaukie", "R-MD"),
        ("fairview", "R-6"),
        ("sherwood", "MDRL"),
        ("wilsonville", "R"),
    ],
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
