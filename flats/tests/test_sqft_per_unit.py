"""A density stated as an area per unit, and the quotient nobody printed.

Portland's Table 120-4 asks "1 unit per 2,500 sq. ft. of site area" in RM1. The
same standard said in units per acre is 17.424, and 17.424 is in no Portland
document -- so a file that typed it would cite a table cell for a number the
cell does not contain. `sqft_per_unit` carries the printed operand and divides
43,560 by it at load, where the arithmetic can be read.

The floor matters for exactly the reason it was hard to encode: a four-unit pod
on a 20,000 sq ft RM1 lot owes eight units. Until this existed the lot screened
green with the floor never compared.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import SQFT_PER_ACRE
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
TABLE = f"{PORTLAND}/33.120.txt#L513-L515,L526-L528"
PROV = Provenance(
    cite="PCC 33.120 — Table 120-4",
    url="https://www.portland.gov/sites/default/files/code/120-md-zones_3.pdf",
    retrieved="2026-08-19",
    quote=TABLE,
)


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "multnomah"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/multnomah/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  RM1:\n"
        "    cite_default:\n"
        "      cite: PCC 33.120\n"
        "      url: https://example.invalid/120\n"
        "      retrieved: '2026-08-19'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_the_table_row_is_read_across_all_six_multi_dwelling_zones() -> None:
    """One row, six cells, six areas per unit. RM3 and RM4 print the same
    figure and land on the same floor, which is the table's doing, not a typo."""
    rules = RuleSet(load_rules())
    floors = {
        zone: rules.resolve(PORTLAND, zone).values["min_density_du_per_acre"].value
        for zone in ("RM1", "RM2", "RM3", "RM4", "RX", "RMP")
    }

    assert floors == {
        "RM1": round(SQFT_PER_ACRE / 2500, 3),
        "RM2": round(SQFT_PER_ACRE / 1450, 3),
        "RM3": round(SQFT_PER_ACRE / 1000, 3),
        "RM4": round(SQFT_PER_ACRE / 1000, 3),
        "RX": round(SQFT_PER_ACRE / 500, 3),
        "RMP": round(SQFT_PER_ACRE / 1875, 3),
    }


def test_the_floor_binds_at_exactly_four_times_the_printed_area() -> None:
    """17.424 du/acre on a four-unit pod is 10,000 sq ft of lot, which is four
    times the 2,500 the table prints. If the conversion were wrong in either
    direction this arithmetic would not close."""
    rules = RuleSet(load_rules())
    floor = rules.resolve(PORTLAND, "RM1").values["min_density_du_per_acre"].value

    assert 4 / (10_000 / SQFT_PER_ACRE) == pytest.approx(floor, abs=0.001)


def test_the_citation_is_checked_against_the_cell_and_not_the_quotient() -> None:
    """Table 120-4 prints 2,500 and never 17.424. Sending the quotient to the
    quote would report the one encoding that invented nothing as the misquote."""
    layers = load_rules()
    r = readiness_for(layers[PORTLAND], store=ProvenanceStore())

    assert ("RM1", "min_density_du_per_acre") not in r.misquoted
    assert ("RM1", "min_density_du_per_acre") not in r.no_evidence


def test_no_maximum_density_is_exempt_rather_than_a_large_number() -> None:
    """Table 120-4 prints "none" for RM1 through RX and 33.120.212.B says it in
    words. An exemption is what the code states; a big number would be a guess
    that a reader could not tell from a reading."""
    rules = RuleSet(load_rules())
    rm1 = rules.resolve(PORTLAND, "RM1")
    rmp = rules.resolve(PORTLAND, "RMP")

    assert "max_density_du_per_acre" in rm1.exempted
    assert "max_density_du_per_acre" not in rm1.values
    assert rmp.values["max_density_du_per_acre"].value == round(SQFT_PER_ACRE / 1500, 3)


def test_a_value_states_a_density_or_an_area_per_dwelling(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="a density or an area per"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_density_du_per_acre:\n"
                "      sqft_per_unit: 2500\n"
                "      value: 17.424\n"
                "      quote: 'or/multnomah/somewhere/33.120.txt#L1'\n",
            ),
            strict=True,
        )


def test_only_a_density_may_be_stated_as_an_area_per_unit() -> None:
    """A lot area per unit and a density per acre are reciprocals; a setback is
    neither, and dividing 43,560 by one would produce a number in feet that
    means nothing."""
    with pytest.raises(ValueError, match="a density"):
        Value(name="setback_front_ft", value=17.424, sqft_per_unit=2500, prov=PROV)


def test_the_printed_area_is_kept_for_the_reader() -> None:
    """Attribution has to be able to say where 17.424 came from."""
    rules = load_rules()
    held = rules[PORTLAND].zones["RM1"].values["min_density_du_per_acre"]

    assert held.sqft_per_unit == 2500
