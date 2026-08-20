"""A lot area stated in acres, and the square footage nobody printed.

MCC 39.4245(A) sets the EFU minimum lot size at "80 acres in the EFU base
zone". A parcel record answers in square feet, so the requirement is 3,484,800
-- and 3,484,800 appears nowhere in Chapter 39, nor in any other rural
ordinance in Oregon, because rural Oregon writes lot minimums in acres and only
in acres.

So the file states the acreage and the multiplication happens at load, where it
can be read. Same bargain as `per_dwelling` and `sqft_per_unit`, one unit over.
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

MULTNOMAH = "or/multnomah/_unincorporated"
PROV = Provenance(
    cite="MCC 39.4245(A)",
    url="https://multco.us/file/chapter_39_-_zoning_code/download",
    retrieved="2026-08-20",
    quote=f"{MULTNOMAH}/39.efu.txt#L1339-L1345",
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
        "      cite: MCC 39.4245\n"
        "      url: https://example.invalid/39\n"
        "      retrieved: '2026-08-20'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_eighty_acres_is_the_square_footage_a_parcel_record_answers_in() -> None:
    rules = RuleSet(load_rules())
    efu = rules.resolve(MULTNOMAH, "EFU").values["min_lot_sqft"]

    assert efu.value == 80 * SQFT_PER_ACRE
    assert isinstance(
        efu.value, int
    ), "3484800.0 invites a reader to wonder which was printed"


def test_the_citation_is_checked_against_the_acreage_not_the_product() -> None:
    """The article prints 80 and never 3,484,800.

    Checking the product against the quote would report the one encoding that
    did not invent a number as the misquote -- which is exactly what happened
    before this form existed.
    """
    layers = load_rules()
    r = readiness_for(layers[MULTNOMAH], store=ProvenanceStore())

    assert ("EFU", "min_lot_sqft") not in r.misquoted


def test_a_value_states_square_feet_or_acres(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="in square feet or in acres"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_lot_sqft:\n"
                "      acres: 80\n"
                "      value: 3484800\n"
                "      quote: 'or/multnomah/somewhere/39.txt#L1'\n",
            ),
            strict=True,
        )


def test_an_acreage_has_to_be_an_area(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="is not an area"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_lot_sqft:\n"
                "      acres: 0\n"
                "      quote: 'or/multnomah/somewhere/39.txt#L1'\n",
            ),
            strict=True,
        )


def test_only_an_area_may_be_stated_in_acres() -> None:
    """A lot WIDTH in acres is not a rule any code writes."""
    with pytest.raises(ValueError, match="states an area in the unit rural"):
        Value(name="min_lot_width_ft", value=200, acres=80, prov=PROV)


def test_the_acreage_is_kept_for_the_reader() -> None:
    """Attribution has to be able to say where 3,484,800 came from."""
    rules = load_rules()
    held = rules[MULTNOMAH].zones["EFU"].values["min_lot_sqft"]

    assert held.acres == 80
