"""Clackamas County ZDO 1009: the landscaped share and the recreation area.

FOLLOWUPS 222 (completeness check, clack-uninc item 1). Table 1001-1 ticks
Section 1009 for quadplexes "in all other zoning districts" -- every district
the pod may stand in except the R-5 to R-30 and VR middle-housing row, whose
1009 column is blank. Table 1009-1 sets the minimum share of the site that is
landscaped; 1009.08(A) adds an outdoor recreational area in MR-1, MR-2 and HDR.
Until this file the layer held neither, so the ground a quadplex owes as
landscaping was never asked for in fourteen districts.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"

#: Table 1009-1 as the screen resolves it. RTL, CC, C3 and OC carry HDR's
#: figure through like: HDR (Table 510-1 note 15), RCC and RCO RCHDR's through
#: like: RCHDR (note 13); each is the larger of the two readings (their own
#: Table 1009-1 rows say 10, 10, 15 and 20, and 10 and 10).
SHARE = {
    "PMD": 25,
    "MR1": 25,
    "MR2": 25,
    "VA": 25,
    "HDR": 25,
    "SHD": 40,
    "RCHDR": 20,
    "SCMU": 15,
    "RTL": 25,
    "CC": 25,
    "C3": 25,
    "OC": 25,
    "RCC": 20,
    "RCO": 20,
}

#: 1009.08(A): 300 sq ft a unit (three or more bedrooms, the larger), four units.
RECREATION = ("MR1", "MR2", "HDR", "RTL", "CC", "C3", "OC")


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.mark.parametrize(("zone", "pct"), sorted(SHARE.items()))
def test_every_district_table_1009_1_reaches_holds_its_share(
    rules: RuleSet, zone: str, pct: int
) -> None:
    got = rules.resolve(CLACKAMAS, zone).values.get("min_landscaped_pct")
    assert got is not None, zone
    assert got.value == pct, zone


@pytest.mark.parametrize("zone", RECREATION)
def test_the_recreation_area_is_four_units_at_three_hundred(rules: RuleSet, zone: str) -> None:
    got = rules.resolve(CLACKAMAS, zone).values.get("open_space_min_sqft")
    assert got is not None, zone
    assert got.value == 1200, zone


@pytest.mark.parametrize("zone", ("PMD", "VA", "SCMU", "SHD", "RCHDR", "RCC", "RCO"))
def test_no_recreation_area_where_1009_08_a_does_not_name_the_district(
    rules: RuleSet, zone: str
) -> None:
    """SHD and RCHDR state an exemption, because they would otherwise inherit
    HDR's through like: HDR; SCMU's is relieved down to the 15 percent share
    by 1009.08(A)(1)(b), so the share is the binding figure."""
    got = rules.resolve(CLACKAMAS, zone).values.get("open_space_min_sqft")
    assert got is None or got.value is None, zone


@pytest.mark.parametrize("zone", ("R5", "R7", "R10", "VR57", "VR45"))
def test_the_middle_housing_row_owes_no_1009_share(rules: RuleSet, zone: str) -> None:
    """Table 1001-1 leaves the 1009 column blank for middle housing in R-5
    to R-30 and VR; Table 1009-1 asks those districts only of conditional
    uses."""
    got = rules.resolve(CLACKAMAS, zone).values
    assert got.get("min_landscaped_pct") is None, zone
    assert got.get("open_space_min_sqft") is None, zone


def test_the_quotes_print_the_figures(rules: RuleSet, store: ProvenanceStore) -> None:
    hdr = rules.resolve(CLACKAMAS, "HDR").values
    share = store.quote(hdr["min_landscaped_pct"].prov.quote)
    assert "HDR, MR-1, MR-2, MRR, PMD, VA, VTH" in share
    assert "25 percent" in share
    rec = store.quote(hdr["open_space_min_sqft"].prov.quote)
    assert "quadplexes" in rec and "MR-1, MR-2, and HDR Districts" in rec
    assert "300 square feet per dwelling unit" in rec
    shd = store.quote(rules.resolve(CLACKAMAS, "SHD").values["min_landscaped_pct"].prov.quote)
    assert "40 percent" in shd
