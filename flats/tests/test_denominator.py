"""Seven cities say "net acre" and mean seven different acres.

``measured_on: net_developable_area`` used to be a bare name, and the name is
the only part every code agrees on. Fairview subtracts street right-of-way and
stops. Milwaukie subtracts right-of-way, floodplain, protected water features
and their vegetated corridors, Goal 5 resources, slopes over 25 percent and
public open space. On a steep wooded lot those denominators are not close, and
a rate divided by the wrong one is a verdict about a different property.

Gresham goes further and disagrees with itself on purpose: 3.0100 prints one
subtraction list for minimum density and a shorter one for maximum, so inside
a single zone the floor and the ceiling are computed on different acres.

So a rate that names a denominator now has to say where its own city defines
it, and that definition is a citation the ladder verifies like any other.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from flats.encode.readiness import _quoted_parts, readiness_for
from flats.encode.tagging import tagged
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Layer, Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

FAIRVIEW = "or/multnomah/fairview"
GRESHAM = "or/multnomah/gresham"
MILWAUKIE = "or/clackamas/milwaukie"
PORTLAND = "or/multnomah/portland"

PROV = Provenance(
    cite="FMC Table 19.30.030.A",
    url="https://example.invalid/19",
    retrieved="2026-08-19",
    quote=f"{FAIRVIEW}/19.30.txt#L292,L299",
)


@pytest.fixture(scope="module")
def layers() -> dict[str, Layer]:
    return load_rules()


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _denominators(layers: dict[str, Layer]) -> list[tuple[str, str, str, Value]]:
    return [
        (layer_id, zone_code, name, value)
        for layer_id, layer in sorted(layers.items())
        for zone_code, zone in sorted(layer.zones.items())
        for name, value in sorted(zone.values.items())
        if value.measured_on is not None
    ]


def test_every_rate_on_an_unheld_quantity_says_where_its_city_defines_it(
    layers: dict[str, Layer],
) -> None:
    """The gate, stated as the corpus rather than as a raised exception. A
    denominator nobody defined is a rate nobody can check, and the name alone
    defines nothing: every code in the corpus uses the same one."""
    rows = _denominators(layers)

    assert rows, "no value names a denominator - this test is guarding nothing"
    missing = [
        f"{layer}/{zone}.{name}"
        for layer, zone, name, value in rows
        if not (value.measured_on_cite and value.measured_on_quote)
    ]
    assert missing == []


def test_each_definition_still_points_at_a_sentence(
    layers: dict[str, Layer], store: ProvenanceStore
) -> None:
    """A citation nothing resolves is the hole this field was added to close,
    so it is checked the way a value's own quote is."""
    for _layer_id, _zone, _name, value in _denominators(layers):
        store.quote(value.measured_on_quote)  # raises if the lines have drifted


def test_the_ladder_walks_the_denominator_citations(
    layers: dict[str, Layer], store: ProvenanceStore
) -> None:
    """Not a separate audit somebody has to remember to run: a definition that
    stopped resolving lands its jurisdiction on `no_evidence` like any other
    broken quote."""
    walked = [name for _zone, name, _quote, _n in _quoted_parts(layers[MILWAUKIE])]

    assert any("<net_developable_area>" in name for name in walked)
    assert readiness_for(layers[MILWAUKIE], store=store).no_evidence == ()


def test_the_loosest_and_the_strictest_acre_are_not_the_same_acre(
    layers: dict[str, Layer], store: ProvenanceStore
) -> None:
    """The reason the citation is per jurisdiction rather than a constant.
    Fairview's net acre is the lot less its street right-of-way; Milwaukie's is
    the lot less six categories of land. A screen holding one denominator for
    both would be wrong by every wet or steep square foot."""
    fairview = layers[FAIRVIEW].zones["R-6"].values["max_density_du_per_acre"]
    milwaukie = layers[MILWAUKIE].zones["R-MD"].values["max_density_du_per_acre"]

    assert fairview.measured_on == milwaukie.measured_on == "net_developable_area"
    assert fairview.measured_on_quote != milwaukie.measured_on_quote

    loose = store.quote(fairview.measured_on_quote).lower()
    strict = store.quote(milwaukie.measured_on_quote).lower()

    assert "right-of-way" in loose
    for deduction in ("floodplain", "goal 5", "25%", "vegetated corridor"):
        assert deduction in strict, deduction
        assert deduction not in loose, f"Fairview does not subtract {deduction}"


def test_gresham_measures_its_floor_and_its_ceiling_on_different_acres(
    layers: dict[str, Layer], store: ProvenanceStore
) -> None:
    """One city, one zone, two denominators. 3.0100 takes the Natural Resource
    and Hillside overlays out of the minimum-density acre and leaves them in
    the maximum-density acre, so the same lot yields a different net area
    depending which end of the range is being tested. This is why the citation
    lives on the value and not on the layer."""
    zone = layers[GRESHAM].zones["LDR-5"].values
    floor = zone["min_density_du_per_acre"]
    ceiling = zone["max_density_du_per_acre"]

    assert floor.measured_on == ceiling.measured_on == "net_developable_area"
    assert floor.measured_on_quote != ceiling.measured_on_quote

    under_floor = store.quote(floor.measured_on_quote)
    under_ceiling = store.quote(ceiling.measured_on_quote)

    assert "When calculating minimum density" in under_floor
    assert "Natural Resource Overlay" in under_floor
    assert "When calculating maximum density" in under_ceiling
    assert "High Slope Subarea" in under_ceiling
    assert "Natural Resource Overlay" not in under_ceiling


def test_the_definition_is_read_for_the_words_the_city_defined() -> None:
    """The point of capturing a glossary is to mark the text a value rests on,
    and a density rests on two sentences: the cell that prints the rate, and
    the definition that says what the acre is. Marking only the first read the
    number and skipped the arithmetic under it."""
    rows = [row for row in tagged(MILWAUKIE) if "<net_developable_area>" in row.field]

    assert rows, "the denominator's own sentence is not being marked"
    marked = {mark.spelled.lower() for row in rows for mark in row.marks}
    assert "net acre" in marked


def test_a_denominator_without_a_definition_is_refused() -> None:
    """The shorthand still parses - it is what the whole corpus was written in
    - and the model refuses it, so the error names the missing citation rather
    than a YAML shape somebody has to decode."""
    with pytest.raises(ValidationError, match="cite and quote where"):
        Value(
            name="max_density_du_per_acre",
            value=17.4,
            prov=PROV,
            measured_on="net_developable_area",
        )


def test_a_definition_without_a_denominator_is_refused() -> None:
    """A file that defines the acre and never says the rate is measured on it
    has written a note, not a rule."""
    with pytest.raises(ValidationError, match="with no 'measured_on'"):
        Value(
            name="max_density_du_per_acre",
            value=17.4,
            prov=PROV,
            measured_on_cite="FMC 19.13",
            measured_on_quote=f"{FAIRVIEW}/19.13.definitions.txt#L399",
        )


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
        "      cite: FMC 19.30\n"
        "      url: https://example.invalid/19\n"
        "      retrieved: '2026-08-19'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_the_mapping_form_wants_the_quantity_named(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="name the quantity under 'fact'"):
        load_rules(
            _somewhere(
                tmp_path,
                "    max_density_du_per_acre:\n"
                "      value: 10\n"
                "      measured_on:\n"
                "        cite: FMC 19.13\n"
                '        quote: "or/multnomah/fairview/19.13.definitions.txt#L399"\n',
            )
        )


def test_an_unknown_key_under_the_denominator_is_a_load_error(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="measured_on: unknown key"):
        load_rules(
            _somewhere(
                tmp_path,
                "    max_density_du_per_acre:\n"
                "      value: 10\n"
                "      measured_on:\n"
                "        fact: net_developable_area\n"
                "        cite: FMC 19.13\n"
                '        quote: "or/multnomah/fairview/19.13.definitions.txt#L399"\n'
                "        deducts: everything\n",
            )
        )


def test_the_denominator_is_still_not_a_lever(layers: dict[str, Layer]) -> None:
    """Naming the acre says the comparison rests on a quantity nobody measured.
    It does not say the number could move, and a reader who took it for a lever
    would go looking for a condition that lifts it."""
    value = layers[FAIRVIEW].zones["R-6"].values["max_density_du_per_acre"]

    assert value.measured_on_cite
    assert "net_developable_area" not in value.levers


def test_a_rate_this_screen_can_run_names_no_denominator(
    layers: dict[str, Layer],
) -> None:
    """Portland states its multi-dwelling density per square foot of site area,
    which is the lot. Nothing is deducted, so nothing is cited - and a file that
    named a denominator there would be reporting a survey it does not need.

    RMP is one unit per 1,500 sq ft of site area, and site area is the whole
    parcel. This is the case the `measured_on` field exists to be told apart
    from: a rate this screen can actually run against a lot it holds."""
    rmp = layers[PORTLAND].zones["RMP"].values["max_density_du_per_acre"]

    assert rmp.measured_on is None
    assert rmp.measured_on_cite is None
    assert rmp.sqft_per_unit == 1500

    # And the state lifts the ceiling off a quadplex before any of it is
    # reached -- OAR 660-046-0220(2)(b) bars a Large City from applying a
    # density maximum to one -- so nothing downstream divides by anything.
    assert (
        "max_density_du_per_acre"
        not in RuleSet(layers).resolve(PORTLAND, "RMP").values
    )
