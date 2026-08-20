"""An acreage that is a divisor rather than a floor.

MCC 39.5340(A) sets the number of dwellings a Planned Development may hold "by
dividing the total site area by the minimum lot area per dwelling unit required
by the underlying district". The rural districts state that minimum in acres --
one in Orient Rural Center Residential, five in Rural Residential -- so four
attached units want four acres in the first and twenty in the second, and
neither article prints either figure.

Two conversions composed, then. `acres` alone would carry the wrong number and
`per_dwelling` alone cannot be written in acres, so the form is its own, and
the citation is checked against the one figure a reader will actually find.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import DWELLINGS, SQFT_PER_ACRE
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

MULTNOMAH = "or/multnomah/_unincorporated"
POD = ("multi_story", "attached_wall")
PROV = Provenance(
    cite="MCC 39.4625(A) with MCC 39.5340(A)",
    url="https://multco.us/file/chapter_39_-_zoning_code/download",
    retrieved="2026-08-20",
    quote=f"{MULTNOMAH}/39.or.txt#L420-L422",
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
        "      cite: MCC 39.5340\n"
        "      url: https://example.invalid/39\n"
        "      retrieved: '2026-08-20'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_one_acre_each_is_four_acres_of_site() -> None:
    rules = RuleSet(load_rules())
    opened = rules.resolve(MULTNOMAH, "OR", (*POD, "planned_development"))

    assert opened.values["min_lot_sqft"].value == DWELLINGS * SQFT_PER_ACRE
    assert opened.values["min_lot_sqft"].value == 174_240


def test_the_base_zone_still_asks_for_one() -> None:
    """Without the overlay the acre is a floor, not a divisor.

    39.4625(A) is a minimum lot size like any other and applies to the lot in
    front of you. It only becomes a per-dwelling figure once 39.5340(A) is the
    rule doing the reading, which is why the two are different variants of the
    same standard rather than two standards.
    """
    rules = RuleSet(load_rules())
    assert rules.resolve(MULTNOMAH, "OR", POD).values["min_lot_sqft"].value == 43_560


def test_the_citation_is_checked_against_the_acreage_not_the_product() -> None:
    """39.4625(A) prints "one acre" and prints 174,240 nowhere."""
    layers = load_rules()
    r = readiness_for(layers[MULTNOMAH], store=ProvenanceStore())

    assert ("OR", "min_lot_sqft") not in r.misquoted
    assert ("RR", "min_lot_sqft") not in r.misquoted


def test_an_area_is_stated_outright_or_per_dwelling(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="outright or per dwelling unit"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_lot_sqft:\n"
                "      acres_per_dwelling: 1\n"
                "      value: 174240\n"
                "      quote: 'or/multnomah/somewhere/39.txt#L1'\n",
            ),
            strict=True,
        )


def test_a_per_dwelling_acreage_has_to_be_an_area(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="is not an area"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_lot_sqft:\n"
                "      acres_per_dwelling: 0\n"
                "      quote: 'or/multnomah/somewhere/39.txt#L1'\n",
            ),
            strict=True,
        )


def test_only_an_area_may_be_stated_per_acre() -> None:
    """A lot WIDTH of one acre per dwelling is not a rule any code writes."""
    with pytest.raises(ValueError, match="states an area per dwelling"):
        Value(name="min_lot_width_ft", value=200, acres_per_dwelling=1, prov=PROV)


def test_an_area_is_acres_or_acres_each_but_not_both() -> None:
    with pytest.raises(ValueError, match="in acres or in acres per"):
        Value(
            name="min_lot_sqft", value=174_240, acres=1, acres_per_dwelling=1, prov=PROV
        )


def test_the_stated_acreage_is_kept_for_the_reader() -> None:
    """Attribution has to be able to say where 174,240 came from."""
    held = load_rules()[MULTNOMAH].zones["OR"].values["min_lot_sqft"]
    variant = held.variants[0]

    assert held.acres == 1
    assert variant.acres_per_dwelling == 1
    assert variant.when == ("planned_development",)


def test_a_variant_may_also_state_a_plain_acreage() -> None:
    """Rural Residential prints two minimums in one sentence.

    Twenty acres within a mile of the Urban Growth Boundary, five beyond it.
    Which applies is a distance nobody has measured, so the base is the twenty
    and the five waits on the site fact -- and both are acreages, because the
    article states no square footage at all.
    """
    held = load_rules()[MULTNOMAH].zones["RR"].values["min_lot_sqft"]
    assert held.acres == 20
    assert held.value == 20 * SQFT_PER_ACRE

    stated = {v.when: (v.acres, v.acres_per_dwelling) for v in held.variants}
    assert stated[("beyond_ugb_mile",)] == (5, None)
    assert stated[("planned_development",)] == (None, 20)
    assert stated[("planned_development", "beyond_ugb_mile")] == (None, 5)
