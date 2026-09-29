"""What open land lies across each lot line, read into ``abuts_park``
(flats/geom/park.py), the ``parks:`` block that says which of Metro's ORCA
unit types a code calls a park (loader), and Troutdale MU-3, the one column
in the corpus whose setback turns on it (TDC 3.230.A: ten feet "when
abutting a park (regardless of zoning district)").

The reading meets the lot on the conservative side: ANY line across a park
settles True (the ten feet), and False needs EVERY non-street line read with
nothing across it but land the layer rules out. A line across a type on
neither list -- a natural area, a trail parcel -- leaves the fact unstated,
and MU-3 screens UNKNOWN rather than taking the non-residential zero.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flats.encode.load import load_trusted
from flats.geom.park import PARK_FACTS, observed_parks
from flats.ingest.quadfit import OBSERVABLE, S4_COLUMNS, observed_facts
from flats.provenance.store import ProvenanceStore
from flats.rules.caps import caps_for
from flats.rules.conditions import CONDITIONS, PARK_CONDITIONS
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import ORCA_UNIT_TYPES, ParkRule
from flats.rules.resolver import RuleSet
from flats.tests.test_quadfit_bridge import EDGES, row
from flats.tests.test_rules import PORTLAND, portland

pytestmark = pytest.mark.unit

TROUTDALE = "or/multnomah/troutdale"
POD = ("multi_story", "attached_wall")
YARDS = ("setback_front_ft", "setback_side_ft", "setback_rear_ft")


def park_rule(true_for=("Park",), false_for=("Home Owners Association", "School Land", "Cemetery")) -> ParkRule:
    return ParkRule(
        condition="abuts_park",
        true_for=true_for,
        false_for=false_for,
        quote="or/multnomah/troutdale/1.020.definitions.txt#L686-L687",
        note="a test list, long enough to pass for a ruling's argument",
    )


RULES = {"abuts_park": park_rule()}


def seen(*kinds: str, none: int = 0) -> dict:
    """One non-street line as s4 writes it: the ORCA unit types its points
    stood in, and how many of its five points stood in none."""
    return {"k": sorted(kinds), "none": none}


# --- the registry ---------------------------------------------------------------


def test_the_fact_is_a_registered_measured_site_fact_with_no_assumption() -> None:
    assert PARK_FACTS == PARK_CONDITIONS == ("abuts_park",)
    c = CONDITIONS["abuts_park"]
    assert c.kind == "site_fact"
    assert c.assume is None, "an unread park is UNKNOWN, never assumed either way"
    assert "abuts_park" in OBSERVABLE
    assert "park_across_json" in S4_COLUMNS


def test_the_unit_types_are_orcas_seven() -> None:
    # LAND/orca.shp UNITTYPE, release 2026_08: every value the field holds.
    assert ORCA_UNIT_TYPES == {
        "Park",
        "Natural Area",
        "Home Owners Association",
        "Other",
        "School Land",
        "Cemetery",
        "Golf Course",
    }


# --- the reading ----------------------------------------------------------------


def test_one_line_across_a_park_settles_it_true() -> None:
    got = observed_parks([None, seen(none=5), seen("Park", none=3), seen("Natural Area")], RULES)
    assert got == {"abuts_park": True}


def test_false_needs_every_line_read_and_ruled_out() -> None:
    clear = [None, seen(none=5), seen("Home Owners Association", none=2), seen("School Land", "Cemetery")]
    assert observed_parks(clear, RULES) == {"abuts_park": False}


def test_a_type_on_neither_list_leaves_the_fact_unstated() -> None:
    for kind in ("Natural Area", "Other", "Golf Course"):
        got = observed_parks([None, seen(none=5), seen(kind, none=4), seen(none=5)], RULES)
        assert got == {}, kind


def test_a_whole_block_abuts_no_park_even_without_the_column() -> None:
    assert observed_parks(None, RULES, all_street=True) == {"abuts_park": False}


def test_no_column_or_an_untraced_lot_answers_nothing() -> None:
    assert observed_parks(None, RULES) == {}
    assert observed_parks([None, None], RULES) == {}
    assert observed_parks([], RULES) == {}


def test_a_layer_that_declares_no_list_is_never_answered() -> None:
    assert observed_parks([None, seen("Park")], {}) == {}


# --- the block in a layer file --------------------------------------------------

BLOCK = (
    "parks:\n"
    "  abuts_park:\n"
    "    true_for: [Park]\n"
    "    false_for: [School Land, Cemetery]\n"
    '    quote: "or/multnomah/troutdale/1.020.definitions.txt#L686-L687"\n'
    "    cite: TDC 1.020\n"
    "    note: >-\n"
    "      The code's park is city-owned recreation land, which ORCA's Park type\n"
    "      holds and its school and cemetery types do not.\n"
)


def test_the_block_loads_as_the_layers_lists(tmp_path: Path) -> None:
    root = tmp_path / "jurisdictions"
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK)
    got = load_rules(root)[PORTLAND].parks["abuts_park"]
    assert got.true_for == ("Park",) and got.false_for == ("School Land", "Cemetery")
    assert got.cite == "TDC 1.020"
    assert got.note.startswith("The code's park is city-owned")


def test_false_for_may_be_left_out(tmp_path: Path) -> None:
    root = tmp_path / "jurisdictions"
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK.replace("    false_for: [School Land, Cemetery]\n", ""))
    assert load_rules(root)[PORTLAND].parks["abuts_park"].false_for == ()


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (("  abuts_park:\n", "  abuts_a_school:\n"), "not a park condition"),
        (("    true_for: [Park]\n", "    true_for: []\n"), "true_for: a list of ORCA unit types"),
        (("    true_for: [Park]\n", "    true_for: [City Park]\n"), "not an ORCA unit type: City Park"),
        (("    false_for: [School Land, Cemetery]\n", "    false_for: [Park]\n"), "on both sides of the line: Park"),
        (('    quote: "or/multnomah/troutdale/1.020.definitions.txt#L686-L687"\n', ""), "a quote of the code's definition"),
        (
            (
                "      The code's park is city-owned recreation land, which ORCA's Park type\n"
                "      holds and its school and cemetery types do not.\n",
                "      Parks.\n",
            ),
            "at least",
        ),
        (("    cite: TDC 1.020\n", "    cite: TDC 1.020\n    when: [corner_lot]\n"), "unexpected when"),
    ],
)
def test_a_malformed_block_is_refused(tmp_path: Path, edit: tuple[str, str], message: str) -> None:
    root = tmp_path / "jurisdictions"
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK.replace(*edit))
    with pytest.raises(RuleLoadError, match=message):
        load_rules(root)


# --- the corpus -------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def test_troutdale_is_the_one_layer_that_reads_parks(corpus: dict) -> None:
    """Grepped 2026-09-28 for "abutting a park" / "adjacent to a park" /
    "contiguous to a park" across every city: 3.230.A's MU-3 column is the
    only encoded standard that turns on it. West Linn 43.040(B)(3) (a
    chapter this corpus reads and holds nothing from), Wilsonville 4.127(.18) (a Frog Pond design
    standard, zone refuses the building), Tualatin's lot-size variance
    criteria, and the manufactured-dwelling "parks" of Gresham, Fairview and
    Portland are not setbacks this screen holds."""
    got = {(lid, name) for lid, layer in corpus.items() for name in layer.parks}
    assert got == {(TROUTDALE, "abuts_park")}


def test_troutdales_park_is_the_citys_recreation_land(corpus: dict) -> None:
    r = corpus[TROUTDALE].parks["abuts_park"]
    assert r.true_for == ("Park",)
    assert set(r.false_for) == {"Home Owners Association", "School Land", "Cemetery"}
    # Natural Area, Other and Golf Course may be city parkland or may not;
    # ORCA's type does not say, so a line across one stays unresolved.
    assert ORCA_UNIT_TYPES - set(r.true_for) - set(r.false_for) == {"Natural Area", "Other", "Golf Course"}
    text = ProvenanceStore().quote(r.quote)
    assert "owned," in text and "operated, or maintained by the City" in text


def test_os_is_non_residential_now_the_park_row_is_read(corpus: dict) -> None:
    """TDC 3.020 files OS under Other Districts. It was kept off both lists
    while nothing could read the park row; with MU-3's ten feet guarded by
    `abuts_park`, OS goes where the outline puts it."""
    assert "OS" in corpus[TROUTDALE].neighbours["abuts_nonresidential_zone"].true_for


def test_mu3_charges_ten_feet_against_a_park_and_nothing_else_changes(corpus: dict) -> None:
    rules = RuleSet(corpus)

    def yards(*held: str) -> tuple:
        res = rules.resolve(TROUTDALE, "MU-3", held)
        for y in YARDS:
            assert not getattr(res.values[y], "ambiguous", ()), (held, y)
        return tuple(res.values[y].value for y in YARDS)

    assert yards() == (20, 20, 20)
    assert yards("abuts_nonresidential_zone") == (0, 0, 0)
    assert yards("abuts_nonresidential_zone", "abuts_park") == (10, 10, 10)
    # A park beside a residential line changes nothing: 20 is already larger.
    assert yards("abuts_park") == (20, 20, 20)
    # The pod's shared walls still owe no yard, park or not.
    assert yards(*POD, "abuts_nonresidential_zone", "abuts_park")[1] == 0
    assert yards(*POD, "abuts_nonresidential_zone")[1] == 0


def test_mu3_leans_on_the_park_fact_and_mu2_does_not(corpus: dict) -> None:
    rules = RuleSet(corpus)
    assert "abuts_park" in rules.resolve(TROUTDALE, "MU-3").levers
    assert "abuts_park" not in rules.resolve(TROUTDALE, "MU-2").levers


def test_no_declared_park_condition_caps_a_value_on_that_layer(corpus: dict) -> None:
    """The caps trap, for the park block: an observed fact lifts a cap, so a
    layer may declare `abuts_park` only where no footnote caps a value on it."""
    rules = RuleSet(corpus)
    for lid, layer in corpus.items():
        for name in layer.parks:
            for zone in layer.zones:
                res = rules.resolve(lid, zone)
                for field, r in res.values.items():
                    where = r.via or (zone if r.origin == "zone" else "(defaults)")
                    assert name not in caps_for(r.layer, where).get(field, ()), (lid, zone, field)


# --- the bridge -------------------------------------------------------------------


@pytest.fixture(scope="module")
def layers():
    return load_trusted(strict=False).rules.layers


def mu3(across: list | None, **over) -> dict:
    """A Troutdale MU-3 row on the bridge fixture lot (street edge first,
    then east side, rear, west side)."""
    base = row(jurisdiction="troutdale", zone="MU-3", **over)
    if across is not None:
        base["park_across_json"] = json.dumps(across)
    return base


def test_the_bridge_reads_a_park_behind_the_lot(layers) -> None:
    got = observed_facts(mu3([None, seen(none=5), seen("Park", none=2), seen(none=5)]), layers)
    assert got["abuts_park"] is True


def test_the_bridge_reads_a_lot_with_only_houses_and_a_school_behind_it(layers) -> None:
    got = observed_facts(mu3([None, seen(none=5), seen("School Land"), seen("Home Owners Association", none=1)]), layers)
    assert got["abuts_park"] is False


def test_the_bridge_leaves_a_natural_area_unstated(layers) -> None:
    got = observed_facts(mu3([None, seen(none=5), seen("Natural Area", none=1), seen(none=5)]), layers)
    assert "abuts_park" not in got


def test_a_whole_block_abuts_no_park_from_a_stage_file_without_the_column(layers) -> None:
    block = [[*e[:4], "F"] for e in EDGES]
    got = observed_facts(mu3(None, edges_json=json.dumps(block), tier="A"), layers)
    assert got["abuts_park"] is False
    # An irregular lot is not trusted to be a whole block.
    got = observed_facts(mu3(None, edges_json=json.dumps(block), tier="C"), layers)
    assert "abuts_park" not in got


def test_a_stage_file_from_before_the_column_leaves_the_fact_unasked(layers) -> None:
    got = observed_facts(mu3(None), layers)
    assert "abuts_park" not in got


def test_a_layer_without_the_block_answers_nothing(layers) -> None:
    got = observed_facts(row(zone="CM2", park_across_json=json.dumps([None, seen("Park")])), layers)
    assert "abuts_park" not in got
    # And without the corpus nothing is answered at all.
    assert "abuts_park" not in observed_facts(mu3([None, seen("Park")]))
