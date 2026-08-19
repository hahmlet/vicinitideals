"""The height row, and the one exception in this corpus the pod fails.

max_height_ft was the largest single hole in the coverage ledger: missing on
25 zones covering 138,459 lots, and 122,000 of those sat in Portland's four
single-dwelling zones and the three county pockets that borrow the same
chapter. Both ends of Table 110-4's height row were encoded -- RF at 30 and
R2.5 at 35 -- and the four columns between them were not.

Every pod in the catalog is 26 feet, so 30 clears with four feet of slack and
25 does not clear at all. That is the whole reason these numbers are worth
asserting rather than assuming: one of them is a real failure.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PDX = "or/multnomah/portland"
COUNTY = "or/multnomah/_unincorporated"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_pod_is_shorter_than_every_ceiling_but_one() -> None:
    """Which is what makes the exception worth encoding and the rest worth
    getting right: at 26 feet the margin against 30 is four feet, and a zone
    read one column across would have been read as 35."""
    assert {design.height_ft for design in load_catalog()} == {26.0}


def test_table_110_4_states_one_height_for_five_of_its_six_columns(
    rules: RuleSet,
) -> None:
    """"Maximum Height | 30 ft. | 30 ft. [3] | 30 ft. [3] | 30 ft. [3] |
    30 ft. [3] | 35 ft." against a header reading RF | R20 | R10 | R7 | R5 |
    R2.5. Six cells, six columns, and the four in the middle all read the
    same -- so no way of counting them changes a number.

    Note [3] hangs on four of those cells and is already ruled: additional FAR
    and height may be allowed under 33.110.265.F, which can only raise a
    ceiling.
    """
    assert {
        zone: rules.resolve(PDX, zone).get("max_height_ft")
        for zone in ("RF", "R20", "R10", "R7", "R5", "R2.5")
    } == {"RF": 30, "R20": 30, "R10": 30, "R7": 30, "R5": 30, "R2.5": 35}


def test_every_cell_of_that_row_cites_the_header_that_names_its_column(
    rules: RuleSet,
) -> None:
    """The value alone cannot be checked against a table that prints six
    districts on one physical line."""
    zones = load_rules()[PDX].zones

    for zone in ("RF", "R20", "R10", "R7", "R5", "R2.5"):
        quote = zones[zone].values["max_height_ft"].prov.quote
        assert quote == "or/multnomah/portland/33.110.txt#L435,L454", zone


def test_the_portland_administered_pockets_take_portlands_ceiling(
    rules: RuleSet,
) -> None:
    """R7, R10, R20 and RF in unincorporated Multnomah are governed by PCC
    33.110, and the county's own stored copy prints the table at the same
    lines."""
    assert {
        zone: rules.resolve(COUNTY, zone).get("max_height_ft")
        for zone in ("RF", "R20", "R10", "R7")
    } == {"RF": 30, "R20": 30, "R10": 30, "R7": 30}


def test_the_countys_own_zones_are_five_feet_looser(rules: RuleSet) -> None:
    """LR-7 and RR cite the Multnomah County Code rather than Portland's, and
    both state 35 feet. Reading the pockets' 30 across to them would have
    invented a standard the county does not impose."""
    assert rules.resolve(COUNTY, "LR7").get("max_height_ft") == 35
    assert rules.resolve(COUNTY, "RR").get("max_height_ft") == 35


def test_a_flag_lot_in_lr_7_is_the_one_lot_the_pod_is_too_tall_for(
    rules: RuleSet,
) -> None:
    """MCC 39.4862 exception (4): the ceiling is 25 feet for "a single family,
    duplex or multiplex dwelling on a flag lot or a lot having sole access
    from an accessway, private drive or easement". The pod is a multiplex and
    it is 26 feet, so this is not a margin -- it is a miss.

    Encoded as a variant rather than as the base, because the exception
    reaches flag lots and not the district. The other half of its trigger --
    sole access by accessway, private drive or easement -- is not a fact any
    layer here holds, so a lot reached only by an easement takes 35 and should
    take 25. That direction is recorded in the file; this test holds the half
    that can be seen.
    """
    ordinary = rules.resolve(COUNTY, "LR7")
    flag = rules.resolve(COUNTY, "LR7", ("flag_lot",))

    assert ordinary.get("max_height_ft") == 35
    assert flag.get("max_height_ft") == 25
    assert all(design.height_ft > 25 for design in load_catalog())
