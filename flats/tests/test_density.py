"""A ceiling on units per acre is a floor under lot area, said in other units.

Milwaukie caps R-MD at 6.2 dwelling units per acre on a lot of 7,000 sq ft or
more. Four units at that ceiling need 28,000 sq ft, and the lot-size row on
the same table asks 7,000 — so the density row, not the lot size row, decides
the zone. The corpus had a minimum-density pair and no maximum at all, which
made the note that reconciles them unwritable.
"""

from __future__ import annotations

import pytest

from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.screen import CHECK_FIELD

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_ceiling_is_registered_as_a_maximum() -> None:
    """A floor and a ceiling on the same axis subtract in opposite directions,
    and slack read the wrong way round turns a failing lot green."""
    field = FIELDS["max_density_du_per_acre"]

    assert field.is_maximum is True
    assert CHECK_FIELD["density_du_per_acre"] == "max_density_du_per_acre"


def test_a_quadplex_on_one_lot_is_exempt_from_the_ceiling(rules: RuleSet) -> None:
    """Footnote 4 exempts duplexes, triplexes, quadplexes and cottage clusters
    outright. It is the sentence that lets a pod exist in R-MD at all, and it
    is exempt rather than a large number: the code states no ceiling here."""
    whole = rules.resolve(MILWAUKIE, "R-MD", lot={"lot_sqft": 8000})

    assert "max_density_du_per_acre" in whole.exempted
    assert "max_density_du_per_acre" not in whole.values


def test_the_same_building_split_onto_four_lots_is_capped(rules: RuleSet) -> None:
    """Split-plat makes the pod four townhouses, and townhouses are held to
    four times the single-detached figure or 25 per acre, whichever is less."""
    for zone in ("R-MD", "R-HD"):
        split = rules.resolve(MILWAUKIE, zone, ("unit_lots",), lot={"lot_sqft": 8000})

        assert split.values["max_density_du_per_acre"].value == 25, zone


def test_a_flag_lot_closes_the_townhouse_path_and_not_the_quadplex_one(
    rules: RuleSet,
) -> None:
    """"Townhouses are not permitted on flag lots" — which is R-MD note 3, and
    says nothing about the same building on a single lot."""
    flag = rules.resolve(MILWAUKIE, "R-MD", ("unit_lots", "flag_lot"))
    whole = rules.resolve(MILWAUKIE, "R-MD", ("flag_lot",))

    assert flag.values["quadplex_allowed"].value is False
    assert whole.values["quadplex_allowed"].value is True
