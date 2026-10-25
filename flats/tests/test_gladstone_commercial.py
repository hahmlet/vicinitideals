"""Gladstone's five formerly-unread codes: MR, C-2, C-3, LI and C-1.

They were `zone_rulings: to_read` -- 380 lots that screened with no zone block at all
Now:

* MR  -- middle housing is outright (17.14.020(1)), a quadplex has its own
  5,000 sq ft row and the townhouse project path is 1,200 per lot.
* C-2 -- attached dwellings "(duplex, triplex, quadplex)" and townhouses are
  outright (17.18.020(11), (12)); a five-foot MAXIMUM front setback.
* C-3, LI, C-1 -- a dwelling is a conditional use and nothing else reaches a
  market-rate quadplex, so RED BY RULING (Steph, 2026-10-08, by right only):
  `quadplex_allowed` false, the standards kept so it could reverse -- and it
  did on 2026-10-15: ORS 197A.400 reduces the hearing to the clear and
  objective standards inside a UGB, so a `conditional_use` variant carries
  the true and the screen clears it there (GREEN with a flag).
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.ingest import assign as az
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

G = "or/clackamas/gladstone"
POD = ("multi_story", "attached_wall")
NEW = ("MR", "C2", "C3", "LI", "C1")
RED = ("C3", "LI", "C1")
LEVERS = ("conditional_use", "unit_lots", "design_review", "master_plan")


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def layer():
    return load_rules()[G]


def _quote(layer, zone: str, field: str) -> str:
    return layer.zones[zone].values[field].prov.quote or ""


def test_the_five_are_zone_blocks_not_rulings(layer) -> None:
    for z in NEW:
        assert z in layer.zones, z
    assert not any(r for r in getattr(layer, "zone_rulings", {}) or {} if r in NEW)


def test_mr_and_c2_are_outright(layer, rules) -> None:
    for z in ("MR", "C2"):
        assert layer.zones[z].values["quadplex_allowed"].value is True
        got = rules.resolve(G, z, POD)
        assert got.values["quadplex_allowed"].value is True
        assert got.missing_required == ()
    assert "17.14/17.14.020.txt#L3-L7" in _quote(layer, "MR", "quadplex_allowed")
    assert "17.18/17.18.020.txt#L25-L27" in _quote(layer, "C2", "quadplex_allowed")


@pytest.mark.parametrize("zone", RED)
def test_the_conditional_use_zones_open_by_the_statute(layer, rules, zone) -> None:
    field = layer.zones[zone].values["quadplex_allowed"]
    assert field.value is False
    (door,) = field.variants
    assert tuple(door.when) == ("conditional_use",)
    assert "ORS 197A.400" in door.prov.cite
    notes = layer.zones[zone].notes or ""
    assert notes.startswith("OPENED 2026-10-15 BY ORS 197A.400")
    assert "RED, RE-CHECKED 2026-10-14 under Steph's review rule" in notes
    # Only the conditional-use path lifts it; the unit-lot path alone does not.
    for levers in ((), *((*POD, lv) for lv in LEVERS if lv != "conditional_use")):
        got = rules.resolve(G, zone, levers)
        assert got.values["quadplex_allowed"].value is False, (zone, levers)
    opened = rules.resolve(G, zone, (*POD, "conditional_use"))
    assert opened.values["quadplex_allowed"].value is True
    assert rules.resolve(G, zone, POD).missing_required == ()


@pytest.mark.parametrize("zone", RED)
def test_the_use_gate_leaves_the_opened_zones_to_the_screen(rules, zone) -> None:
    # A zone that encodes its own relief path is the screen's to answer: inside
    # a UGB it clears the hearing, outside it does not.
    class _Relief:
        def for_use(self, layer_id):
            return type("O", (), {"available": False})()

    gate = az.use_gate_for(rules, _Relief())
    assert gate(G, zone) is None
    for z in ("MR", "C2"):
        assert gate(G, z) is None


def test_mr_numbers_and_quotes(layer, rules) -> None:
    v = rules.resolve(G, "MR", POD).values
    assert (v["setback_front_ft"].value, v["setback_side_ft"].value) == (20, 5)
    assert (v["setback_rear_ft"].value, v["setback_street_side_ft"].value) == (15, 20)
    assert (v["max_height_ft"].value, v["min_landscaped_pct"].value) == (35, 20)
    assert v["min_lot_sqft"].value == 5000
    assert v["min_density_du_per_acre"].value == 25
    unit = rules.resolve(G, "MR", (*POD, "unit_lots")).values
    assert unit["setback_side_ft"].value == 0
    assert unit["min_lot_sqft"].value == 4800  # 1,200 x 4 lots
    for field, line in (
        ("setback_front_ft", "L22-L23"),
        ("setback_side_ft", "L27-L28"),
        ("setback_rear_ft", "L37-L38"),
        ("setback_street_side_ft", "L32-L33"),
        ("min_lot_sqft", "L12-L13"),
        ("max_height_ft", "L42-L43"),
        ("min_landscaped_pct", "L45-L46"),
    ):
        assert f"17.14/17.14.050.txt#{line}" in _quote(layer, "MR", field), field
    assert layer.zones["MR"].values["min_density_du_per_acre"].measured_on == "net_developable_area"


def test_c2_numbers_and_quotes(layer, rules) -> None:
    v = rules.resolve(G, "C2", POD).values
    assert v["setback_front_max_ft"].value == 5
    assert v["setback_rear_ft"].value == 15
    assert (v["setback_front_ft"].value, v["setback_side_ft"].value) == (0, 0)
    assert (v["max_height_ft"].value, v["max_height_stories"].value) == (35, 3)
    assert v["parking_front_prohibited"].value is True
    assert v["parking_required_yard_prohibited"].value is True
    # Lot area is R-5's, by 17.18.060(5)(a), and nothing else is borrowed.
    assert v["min_lot_sqft"].value == 7000
    assert rules.resolve(G, "C2", (*POD, "unit_lots")).values["min_lot_sqft"].value == 6000  # 1,500 x 4
    assert "17.18/17.18.060.txt#L9" in _quote(layer, "C2", "setback_front_max_ft")
    assert "17.18/17.18.060.txt#L14" in _quote(layer, "C2", "max_height_ft")
    assert "Portland Avenue" in (layer.zones["C2"].notes or "")


def test_the_overlaid_yards_on_the_red_zones(rules) -> None:
    li = rules.resolve(G, "LI", POD).values
    assert (li["setback_side_ft"].value, li["setback_rear_ft"].value) == (20, 20)
    assert li["setback_front_ft"].value == 20  # MR's, carried by `like`
    assert rules.resolve(G, "C1", POD).values["setback_side_ft"].value == 15
    assert rules.resolve(G, "C3", POD).values["setback_front_ft"].value == 20


def test_every_figure_is_quoted_where_it_is_printed(layer) -> None:
    ready = readiness_for(layer, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
