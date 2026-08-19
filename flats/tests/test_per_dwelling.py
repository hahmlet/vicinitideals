"""A lot area stated per dwelling unit, and the product nobody printed.

MCC 39.4862(C) sets the LR-7 minimum lot size at "5,000 square feet for each
dwelling unit". The pod is four of them, so the requirement is 20,000 — and
20,000 appears nowhere in the article. The file carried the product and cited
the sentence, which is the exact shape the citation check exists to catch: a
number a reader sent to the quote will not find.

So the file states what the sentence states and the multiplication happens at
load, where it can be read. Same bargain as `reduce_pct`, one axis over.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

MULTNOMAH = "or/multnomah/_unincorporated"
PROV = Provenance(
    cite="MCC 39.4862(C)",
    url="https://multco.us/file/chapter_39_-_zoning_code/download",
    retrieved="2026-08-19",
    quote=f"{MULTNOMAH}/39.lr-7.txt#L397-L399",
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
        "      cite: MCC 39.4862\n"
        "      url: https://example.invalid/39\n"
        "      retrieved: '2026-08-19'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_the_pod_needs_four_of_them() -> None:
    """The field is defined as the minimum lot area for a fourplex, so a code
    that states it per dwelling has stated it four times over."""
    rules = RuleSet(load_rules())
    lr7 = rules.resolve(MULTNOMAH, "LR7").values["min_lot_sqft"]

    assert lr7.value == 20000
    assert isinstance(lr7.value, int), "20000.0 invites a reader to wonder which was printed"


def test_the_citation_is_checked_against_the_sentence_and_not_the_product() -> None:
    """The article prints 5,000 and never 20,000. Checking the product against
    the quote reported the one encoding that did not invent a number as the
    misquote."""
    layers = load_rules()
    r = readiness_for(layers[MULTNOMAH], store=ProvenanceStore())

    assert ("LR7", "min_lot_sqft") not in r.misquoted


def test_a_value_states_a_total_or_a_per_dwelling_figure(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="a total or a per-dwelling"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_lot_sqft:\n"
                "      per_dwelling: 5000\n"
                "      value: 20000\n"
                "      quote: 'or/multnomah/somewhere/39.txt#L1'\n",
            ),
            strict=True,
        )


def test_only_an_area_may_be_stated_per_dwelling() -> None:
    """Four dwellings need four times the land and exactly as much width. A
    multiplied lot width would be a requirement no code anywhere states."""
    with pytest.raises(ValueError, match="an area scales"):
        Value(name="min_lot_width_ft", value=200, per_dwelling=50, prov=PROV)


def test_the_per_dwelling_figure_is_kept_for_the_reader() -> None:
    """Attribution has to be able to say where 20,000 came from."""
    rules = load_rules()
    held = rules[MULTNOMAH].zones["LR7"].values["min_lot_sqft"]

    assert held.per_dwelling == 5000
