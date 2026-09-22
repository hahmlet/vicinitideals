"""The zone across each lot line, read into the three neighbour-zoning facts
(flats/geom/neighbour.py), the `neighbours:` block that says which codes
are which (loader), and the two guards that keep the reading honest:

* a layer may declare a condition only where no footnote caps a value on
  it -- an observed fact lifts a cap, and the base number would certify
  with the footnote's other number never written down; and
* Portland's OS on the true_for side is wrong for a CI home lot (33.150
  gives it ten feet against a park), which is safe only while both CI zones
  are capped and never certify.

The reading meets the lot on the conservative side: ANY line settles the
tightening answer, and the relaxing answer needs EVERY line fully read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.geom.neighbour import EVERY_LINE, NEIGHBOUR_FACTS, Line, lines_from_quadfit, observed_neighbours
from flats.provenance.store import ProvenanceStore
from flats.rules.caps import caps_for
from flats.rules.conditions import CONDITIONS, NEIGHBOUR_ZONE_CONDITIONS
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import NeighbourRule
from flats.rules.resolver import RuleSet
from flats.tests.test_rules import PORTLAND, portland

pytestmark = pytest.mark.unit


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "jurisdictions"


def rule(condition: str, true_for: tuple[str, ...], false_for: tuple[str, ...]) -> NeighbourRule:
    return NeighbourRule(
        condition=condition,
        true_for=true_for,
        false_for=false_for,
        quote="or/multnomah/portland/33.130.txt#L869-L875",
        note="a test list, long enough to pass for a ruling's argument",
    )


NONRES = {"abuts_nonresidential_zone": rule("abuts_nonresidential_zone", ("CM2", "OS"), ("R5", "RM1"))}
RES = {"abuts_residential_zone": rule("abuts_residential_zone", ("R5", "RM1"), ("CM2", "OS"))}


def line(*codes: str, unresolved: int = 0, city: str = "portland") -> Line:
    return Line(zones=tuple((city, c) for c in codes), unresolved=unresolved)


# --- the registry ---------------------------------------------------------------


def test_the_three_facts_are_registered_measured_site_facts() -> None:
    assert NEIGHBOUR_FACTS == NEIGHBOUR_ZONE_CONDITIONS
    for name in NEIGHBOUR_FACTS:
        assert CONDITIONS[name].kind == "site_fact", name
        assert CONDITIONS[name].assume is None, f"{name} is observed now, not assumed"
    assert EVERY_LINE == {"abuts_nonresidential_zone"}


# --- the every-line condition (Portland's relaxation) ---------------------------


def test_every_line_true_needs_every_line_read_and_nothing_residential() -> None:
    got = observed_neighbours([line("CM2"), line("OS"), line("CM2", "OS")], NONRES, "portland")
    assert got == {"abuts_nonresidential_zone": True}


def test_one_residential_point_settles_the_relaxation_false() -> None:
    # Two lines fully commercial, the third partly R5: the ten feet stand.
    got = observed_neighbours([line("CM2"), line("CM2"), line("CM2", "R5")], NONRES, "portland")
    assert got == {"abuts_nonresidential_zone": False}
    # Even where every other line is unread -- false is the cheap answer.
    got = observed_neighbours([line(unresolved=5), line("R5")], NONRES, "portland")
    assert got == {"abuts_nonresidential_zone": False}


def test_an_unread_line_leaves_the_relaxation_unstated() -> None:
    # A park drawn as right-of-way behind the lot: the rear line is nobody's
    # zone, and no relaxation is certified on it.
    got = observed_neighbours([line("CM2"), line(unresolved=5)], NONRES, "portland")
    assert got == {}
    # A split-zone neighbour is two points unresolved on an otherwise
    # commercial line, and that is enough to withhold the answer.
    got = observed_neighbours([line("CM2"), line("CM2", unresolved=2)], NONRES, "portland")
    assert got == {}
    # A code the lists do not place (Portland's CI in the E chapter's row).
    got = observed_neighbours([line("CM2"), line("CI2")], NONRES, "portland")
    assert got == {}


def test_a_neighbour_across_the_city_line_is_not_read_by_this_citys_list() -> None:
    # Gresham's LDR-7 is residential in Gresham's code; Portland's list says
    # nothing about it, so the line is unresolved and the fact unstated.
    got = observed_neighbours([line("CM2"), line("LDR-7", city="gresham")], NONRES, "portland")
    assert got == {}
    # Even a code that is spelled the same as one on the list: another
    # city's R5 is not Portland's R5.
    got = observed_neighbours([line("CM2"), line("R5", city="gresham")], NONRES, "portland")
    assert got == {}


# --- the any-line conditions (Oregon City's and the footnotes' tightening) -----


def test_any_line_true_is_settled_by_a_single_residential_point() -> None:
    got = observed_neighbours([line(unresolved=5), line("CM2", "R5")], RES, "portland")
    assert got == {"abuts_residential_zone": True}


def test_any_line_false_needs_every_line_read_and_nothing_residential() -> None:
    got = observed_neighbours([line("CM2"), line("OS", "CM2")], RES, "portland")
    assert got == {"abuts_residential_zone": False}
    got = observed_neighbours([line("CM2"), line(unresolved=1)], RES, "portland")
    assert got == {}
    got = observed_neighbours([line("CM2"), line("MUC-1")], RES, "portland")
    assert got == {}, "a code on neither list is a line nobody read"


# --- what is never answered -----------------------------------------------------


def test_a_lot_with_no_non_street_line_answers_nothing() -> None:
    assert observed_neighbours([], {**NONRES, **RES}, "portland") == {}


def test_a_condition_the_layer_did_not_declare_is_never_answered() -> None:
    lines = [line("CM2"), line("CM2")]
    assert observed_neighbours(lines, NONRES, "portland") == {"abuts_nonresidential_zone": True}
    assert "abuts_residential_zone" not in observed_neighbours(lines, NONRES, "portland")
    assert observed_neighbours(lines, {}, "portland") == {}


def test_both_conditions_answer_from_the_same_lines() -> None:
    lines = [line("CM2"), line("R5")]
    got = observed_neighbours(lines, {**NONRES, **RES}, "portland")
    assert got == {"abuts_nonresidential_zone": False, "abuts_residential_zone": True}


# --- decoding s4's record --------------------------------------------------------


def test_lines_from_quadfit_skips_street_edges_and_counts_what_it_cannot_spell() -> None:
    across = [
        None,  # the street edge
        {"z": [["portland", "R5a"], ["portland", "R5"]], "split": 0, "none": 0},
        {"z": [["portland", "CM2"], ["gresham", "LDR-7"]], "split": 1, "none": 2},
        {"z": [], "split": 0, "none": 5},
    ]

    def normalise(city: str, raw: str) -> str | None:
        if city != "portland":
            return None
        return raw.rstrip("abcdefghijklmnopqrstuvwxyz")

    lines = lines_from_quadfit(across, normalise)
    assert lines == (
        Line(zones=(("portland", "R5"),), unresolved=0),  # R5a and R5 are one code
        Line(zones=(("portland", "CM2"),), unresolved=4),  # 1 split + 2 none + Gresham
        Line(zones=(), unresolved=5),
    )


# --- the block in a layer file ----------------------------------------------------

BLOCK = (
    "neighbours:\n"
    "  abuts_nonresidential_zone:\n"
    "    true_for: [OS, CM2]\n"
    "    false_for: [R5, RM1]\n"
    '    quote: "or/multnomah/portland/33.130.txt#L869-L875"\n'
    "    cite: PCC 33.130.215.B.2\n"
    "    note: >-\n"
    "      The commercial chapter's two rows, none against OS and the C zones,\n"
    "      ten against the R zones.\n"
)


def test_the_block_loads_as_the_layers_lists(root: Path) -> None:
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK)
    layer = load_rules(root)[PORTLAND]
    got = layer.neighbours["abuts_nonresidential_zone"]
    assert got.true_for == ("OS", "CM2") and got.false_for == ("R5", "RM1")
    assert got.cite == "PCC 33.130.215.B.2"
    assert got.note.startswith("The commercial chapter's two rows")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (("abuts_nonresidential_zone", "abuts_a_school"), "not a neighbour-zoning condition"),
        (("    false_for: [R5, RM1]\n", ""), "false_for: a non-empty list"),
        (("    false_for: [R5, RM1]\n", "    false_for: []\n"), "false_for: a non-empty list"),
        (("    false_for: [R5, RM1]\n", "    false_for: [R5, CM2]\n"), "on both sides of the line: CM2"),
        (('    quote: "or/multnomah/portland/33.130.txt#L869-L875"\n', ""), "a quote of the sentence"),
        (
            (
                "      The commercial chapter's two rows, none against OS and the C zones,\n"
                "      ten against the R zones.\n",
                "      Two rows.\n",
            ),
            "at least",
        ),
        (("    cite: PCC 33.130.215.B.2\n", "    cite: PCC 33.130.215.B.2\n    when: [corner_lot]\n"), "unexpected when"),
        # `yes:`/`no:` are booleans to YAML; the loader names the keys it wants.
        (("    true_for: [OS, CM2]\n", "    yes: [OS, CM2]\n"), "unexpected True"),
    ],
)
def test_a_malformed_block_is_refused(root: Path, edit: tuple[str, str], message: str) -> None:
    portland(root, "  CM2:\n    quadplex_allowed: true\n", extra=BLOCK.replace(*edit))
    with pytest.raises(RuleLoadError, match=message):
        load_rules(root)


def test_a_layer_without_the_block_declares_nothing(root: Path) -> None:
    portland(root, "  CM2:\n    quadplex_allowed: true\n")
    assert load_rules(root)[PORTLAND].neighbours == {}


# --- the corpus ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> dict:
    return load_rules()


def declared(layers: dict) -> list[tuple[str, str, NeighbourRule]]:
    return [(lid, name, r) for lid, layer in layers.items() for name, r in layer.neighbours.items()]


def test_the_four_layers_that_read_their_lot_lines(corpus: dict) -> None:
    got = {(lid, name) for lid, name, _ in declared(corpus)}
    assert got == {
        ("or/multnomah/portland", "abuts_nonresidential_zone"),
        ("or/multnomah/troutdale", "abuts_nonresidential_zone"),
        ("or/multnomah/fairview", "abuts_nonresidential_zone"),
        ("or/clackamas/oregon-city", "abuts_residential_zone"),
    }


def test_every_neighbour_quote_resolves_and_every_code_is_the_layers_own(corpus: dict) -> None:
    store = ProvenanceStore()
    for lid, name, r in declared(corpus):
        text = store.quote(r.quote)
        assert text.strip(), (lid, name, r.quote)
        layer = corpus[lid]
        for code in (*r.true_for, *r.false_for):
            assert layer.holds(code) is not None or code in layer.zone_rulings, (lid, name, code)


def test_no_declared_condition_caps_a_value_on_that_layer(corpus: dict) -> None:
    """The caps trap. An observed fact lifts a cap; the value under the cap
    then certifies at its base number with the footnote's other number never
    encoded. So a layer may declare a condition only if no zone it resolves
    carries a cap leaning on it -- through inheritance too, because caps ride
    with the layer that encoded the value."""
    rules = RuleSet(corpus)
    for lid, name, _ in declared(corpus):
        for zone in corpus[lid].zones:
            res = rules.resolve(lid, zone)
            for field, r in res.values.items():
                where = r.via or (zone if r.origin == "zone" else "(defaults)")
                assert name not in caps_for(r.layer, where).get(field, ()), (
                    f"{lid} declares {name} but {zone}.{field} is capped on it "
                    f"(encoded in {r.layer} {where}); encode the footnote as a variant first"
                )


def test_portlands_os_on_the_relaxing_side_is_safe_only_while_ci_never_certifies(corpus: dict) -> None:
    """33.150 Table 150-2 gives a CI lot ten feet against an OS lot where the
    commercial chapters give none. One layer-wide list cannot say both, so
    OS sits on the relaxing side and the CI zones must stay capped on
    site_specific_limitation until CI gets a list of its own."""
    r = corpus["or/multnomah/portland"].neighbours["abuts_nonresidential_zone"]
    if "OS" not in r.true_for:
        return
    for zone in ("CI1", "CI2"):
        capped = caps_for("or/multnomah/portland", zone)
        for field in ("setback_side_ft", "setback_rear_ft"):
            assert "site_specific_limitation" in capped.get(field, ()), (zone, field)
