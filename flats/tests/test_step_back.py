"""A rear yard that is deeper than the table says, because of a roof.

Gresham's Table 4.0130 prints a 15 ft rear setback for LDR-5, and for a year
that is what this corpus screened 12,854 lots against. Section 7.0420(G)(1) is
the other half of the rule and lives in another chapter: "the maximum roof
height at the rear setback line is 21 feet and increases at a rate of one foot
in height for every one foot of distance further from the rear property line."

A 26 ft box is five feet over the allowance at that line, and at one foot per
foot it buys those five feet by standing five feet further back. So the rear
setback for THIS building is 20 ft, not 15 — in Gresham's six largest
residential districts, a little over 21,000 lots, all in the strict direction.

Which is why the step-back is a form rather than a note. A note saying "roof
plane rule, not encoded" reads as a detail somebody chose to skip. It was five
feet of every rear yard in the city.

The form differs from `per_height_ft` in one way that shapes the whole
encoding: a height-proportional setback REPLACES the district's number, and a
step-back ADDS to it. So a value carrying one states two figures from two
sentences in two chapters, and carries a second citation for the second one —
the arrangement `measured_on` already uses, for the same reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS
from flats.rules.fields import DESIGN_HEIGHT_FT
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Layer, Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
POD = ("multi_story", "attached_wall")
DESIGN = f"{GRESHAM}/7.0400.middle-housing-design.txt"
#: The six districts 7.0420(G)(1) names, and what each rear yard becomes.
STEPPED = {"LDR-5": 20, "LDR-7": 20, "TR": 20, "LDR-PV": 15, "LDR-SW": 20, "VLDR-SW": 25}
PROV = Provenance(
    cite="Gresham Development Code Table 4.0130 row G",
    url="https://www.greshamoregon.gov/globalassets/government/city-codes-and-policies/development-code/dc-section-4.0100.pdf",
    retrieved="2026-08-20",
    quote=f"{GRESHAM}/4.0100.residential.txt#L399-L400",
)


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "multnomah"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/multnomah/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  R-6:\n"
        "    cite_default:\n"
        "      cite: GDC 7.0420\n"
        "      url: https://example.invalid/7\n"
        "      retrieved: '2026-08-20'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_five_feet_more_in_every_district_the_section_names(rules: RuleSet) -> None:
    for zone, stepped in STEPPED.items():
        res = rules.resolve(GRESHAM, zone, POD)
        assert res.values["setback_rear_ft"].value == stepped, zone


def test_the_district_keeps_its_own_printed_figure(gresham: Layer) -> None:
    """`value` is what a lot is measured against; `before_step_back` is what a
    reader finds in Table 4.0130. Both have to survive, because the citation
    check compares the second against the district table's own quote."""
    held = gresham.zones["LDR-5"].values["setback_rear_ft"]

    assert held.value == 20
    assert held.before_step_back == 15
    assert held.step_back_at_ft == 21
    assert held.step_back_rise == 1
    assert held.step_back_quote.startswith(DESIGN)


def test_the_arithmetic_is_the_sentence_and_not_a_constant(gresham: Layer) -> None:
    held = gresham.zones["LDR-5"].values["setback_rear_ft"]
    owed = (DESIGN_HEIGHT_FT - held.step_back_at_ft) / held.step_back_rise

    assert owed == 5
    assert held.value == held.before_step_back + owed


def test_the_step_back_reaches_the_exceptions_too(gresham: Layer) -> None:
    """A step-back belongs to the standard, not to its base.

    Pleasant Valley's rear yard is 10 ft, or 8 with an alley, and the roof
    plane pushes a 26 ft box five feet off whichever of the two applies.
    Stepping only the base would have left the alley lots reading 8 — the
    loosest number in the chapter, and three feet under a rule that says
    nothing about alleys.
    """
    held = gresham.zones["LDR-PV"].values["setback_rear_ft"]
    alley = next(v for v in held.variants if v.when == ("abuts_alley",))

    assert alley.value == 13
    assert alley.before_step_back == 8


def test_the_alley_column_that_was_never_read_across(gresham: Layer) -> None:
    """Table 4.0130 row G has printed "Rear With Alley 8 ft." the whole time.

    quadfit's own imported note on LDR-5 said "rear w/ alley 8 ft (not
    modeled)" — a gap somebody wrote down and then carried into this corpus
    unencoded. It is a lever rather than a tightening: `abuts_alley` is assumed
    False, so the deeper yard still binds by default.
    """
    for zone in ("LDR-5", "LDR-7", "TR", "TLDR"):
        held = gresham.zones[zone].values["setback_rear_ft"]
        alley = next(v for v in held.variants if v.when == ("abuts_alley",))
        # TLDR is not stepped back, so its 8 is both the printed figure and the
        # effective one; the other three carry the 8 as what the table says.
        assert (alley.before_step_back or alley.value) == 8, zone


def test_the_one_district_the_section_leaves_out(rules: RuleSet) -> None:
    """7.0420 reaches TLDR for every other design standard and (G)(1) does not
    name it, so its 15 ft rear yard is the whole rear yard — where the same 15
    ft in LDR-5 is 20. An omission is only usable where somebody checked it."""
    assert "TLDR" not in STEPPED
    assert rules.resolve(GRESHAM, "TLDR", POD).values["setback_rear_ft"].value == 15


def test_both_halves_of_the_number_are_quoted(gresham: Layer, store: ProvenanceStore) -> None:
    held = gresham.zones["LDR-5"].values["setback_rear_ft"]

    table = store.quote(held.prov.quote)
    assert "15 ft." in table and "8 ft." in table

    plane = store.quote(held.step_back_quote)
    assert "maximum roof height" in plane
    assert "21 feet" in plane
    assert "one foot in heigh" in plane
    # The applicability sentence travels with it, because a quadplex reaching
    # this section at all is the premise of the whole encoding.
    assert "quadplex residential" in plane


def test_neither_chapter_prints_the_answer(gresham: Layer, store: ProvenanceStore) -> None:
    """Which is exactly why it is computed rather than typed."""
    held = gresham.zones["LDR-5"].values["setback_rear_ft"]
    assert "20 ft." not in store.quote(held.step_back_quote)

    ready = readiness_for(gresham, store=ProvenanceStore())
    assert not [row for row in ready.misquoted if row[0] in STEPPED]
    assert not [row for row in ready.no_evidence if row[0] in STEPPED]


def test_the_relief_nobody_can_check_is_registered(gresham: Layer) -> None:
    """7.0420(G)(1)(b) switches the limit off inside the Hillside Geological
    Risk Area or a Resource Area — an overlay that RELEASES a standard where
    every other one in this registry tightens. Assumed unknown, recorded in the
    notes rather than encoded, because the lever would need a twin of every
    existing variant and a boundary nothing here cuts."""
    fact = CONDITIONS["hillside_or_resource_overlay"]
    assert fact.kind == "site_fact"
    assert fact.assume is None

    for zone in STEPPED:
        notes = gresham.zones[zone].notes or ""
        assert "7.0420(G)(1)(b)" in notes, zone
        assert "Hillside Geological Risk Area" in notes, zone


def test_the_split_plat_path_is_caught_by_the_same_rule(gresham: Layer) -> None:
    """7.0420 names quadplexes and not townhouses, and GDC 3.0100 closes the
    gap: units divided through a Middle Housing Land Division "are considered a
    quadplex". Recorded in the notes because it is the reason no `unit_lots`
    variant stands the building back up."""
    for zone in STEPPED:
        assert "Middle Housing Land Division" in (gresham.zones[zone].notes or ""), zone


def test_a_step_back_only_applies_to_a_yard() -> None:
    with pytest.raises(ValueError, match="height limit near a lot line"):
        Value(
            name="min_lot_sqft",
            value=5000,
            step_back_at_ft=21,
            step_back_rise=1,
            step_back_cite="GDC 7.0420(G)(1)",
            step_back_quote=f"{DESIGN}#L358-L362",
            prov=PROV,
        )


def test_a_step_back_carries_its_own_citation() -> None:
    """The district table and the roof plane are two sentences in two chapters,
    and the value is neither of them alone. A reader handed only the table
    would find 15 where the file holds 20."""
    with pytest.raises(ValueError, match="second rule in a second section"):
        Value(
            name="setback_rear_ft",
            value=15,
            step_back_at_ft=21,
            step_back_rise=1,
            prov=PROV,
        )


def test_a_step_back_states_the_rate_it_rises_at() -> None:
    """A 1:1 plane and a 1:2 plane are different rules and both are written."""
    with pytest.raises(ValueError, match="rises at a rate the code prints"):
        Value(
            name="setback_rear_ft",
            value=15,
            step_back_at_ft=21,
            step_back_cite="GDC 7.0420(G)(1)",
            step_back_quote=f"{DESIGN}#L358-L362",
            prov=PROV,
        )


def test_a_step_back_needs_a_setback_to_be_added_to(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="no distance here to add it to"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_rear_ft:\n"
                "      exempt: true\n"
                "      quote: 'or/multnomah/somewhere/7.txt#L1'\n"
                "      step_back:\n"
                "        height_ft: 21\n"
                "        rise_per_ft: 1\n"
                "        cite: GDC 7.0420(G)(1)\n"
                "        quote: 'or/multnomah/somewhere/7.txt#L2'\n",
            ),
            strict=True,
        )


def test_a_step_back_states_the_height_it_limits(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="it is what the rule limits"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_rear_ft:\n"
                "      value: 15\n"
                "      quote: 'or/multnomah/somewhere/7.txt#L1'\n"
                "      step_back:\n"
                "        rise_per_ft: 1\n"
                "        cite: GDC 7.0420(G)(1)\n"
                "        quote: 'or/multnomah/somewhere/7.txt#L2'\n",
            ),
            strict=True,
        )


def test_a_building_under_the_allowance_is_pushed_nowhere(tmp_path: Path) -> None:
    """The rule limits a roof. A 26 ft pod against a 30 ft allowance owes
    nothing, and the district's own setback stands unchanged — which is why
    Gresham's other height transition rules, at 30 and 35 ft, are recorded and
    not encoded."""
    layers = load_rules(
        _somewhere(
            tmp_path,
            "    setback_rear_ft:\n"
            "      value: 15\n"
            "      quote: 'or/multnomah/somewhere/7.txt#L1'\n"
            "      step_back:\n"
            "        height_ft: 30\n"
            "        rise_per_ft: 1\n"
            "        cite: GDC 9.0610(A)(1)\n"
            "        quote: 'or/multnomah/somewhere/7.txt#L2'\n",
        ),
        strict=False,
    )
    held = layers["or/multnomah/somewhere"].zones["R-6"].values["setback_rear_ft"]
    assert held.value == 15
    assert held.before_step_back == 15
