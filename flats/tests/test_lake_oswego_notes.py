"""Lake Oswego's density notes, and the split path they close.

Every residential table in LOC 50.04 prints the same pair of sentences under
it: middle housing is exempt from maximum density, and a townhouse project
gets four dwellings per the lot area one single-family dwelling would need.
The first half is why a pod fits a 7,500 sq ft R-7.5 lot at all. The second is
the half the corpus was reading too kindly — four 1,500 sq ft townhouse lots
come to 6,000, and Lake Oswego will not allow four townhouses on 6,000 sq ft
in a zone whose single-family minimum is 7,500.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

LAYER = "or/clackamas/lake-oswego"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_pod_on_one_lot_is_exempt_from_maximum_density(rules: RuleSet) -> None:
    """Exempt, not a large number: the Maximum row of Table 50.04.001-1 prints
    a footnote marker and no figure at all."""
    for zone in ("R-7.5", "R-5", "R-3", "R-0"):
        whole = rules.resolve(LAYER, zone, lot={"lot_sqft": 8000})

        assert "max_density_du_per_acre" in whole.exempted, zone
        assert whole.values["quadplex_allowed"].value is True, zone


def test_four_townhouse_lots_need_the_land_one_house_would(rules: RuleSet) -> None:
    """R-7.5's single-family minimum is 7,500 and R-5's is 5,000. Below those
    the split-plat path is not permitted, however small the townhouse lots
    themselves may be."""
    for zone, floor in (("R-7.5", 7500), ("R-5", 5000)):
        under = rules.resolve(LAYER, zone, ("unit_lots",), lot={"lot_sqft": floor - 1})
        exactly = rules.resolve(LAYER, zone, ("unit_lots",), lot={"lot_sqft": floor})

        assert under.values["quadplex_allowed"].value is False, zone
        assert exactly.values["quadplex_allowed"].value is True, zone


def test_the_one_lot_path_is_untouched_by_the_townhouse_density(rules: RuleSet) -> None:
    """The note caps townhouse projects. A quadplex on a single lot is exempt,
    and reading the cap onto it would delete lots the code allows."""
    small = rules.resolve(LAYER, "R-7.5", lot={"lot_sqft": 6000})

    assert small.values["quadplex_allowed"].value is True


def test_every_governing_note_is_ruled_on() -> None:
    """Sixty-two captured, twenty-eight over an encoded value. What stays
    unread governs the commercial tables and the zones this layer does not
    encode."""
    unread = [n for n in notes() if n.layer == LAYER and n.state == "unread"]

    assert all(n.doc.endswith("use-table.txt") or n.line > 1590 for n in unread)


def test_the_uncomputed_facts_are_named_rather_than_assumed() -> None:
    """Four lot facts Lake Oswego's notes turn on and nothing measures. Each
    caps the verdict; none of them is a footnote somebody still has to read.

    `abuts_lower_density_zone` arrived on 2026-08-21 with R-2. The note under
    Table 50.04.001-13 takes the three subsections printed below the table into
    its body, and one of them requires a lot zoned R-0, R-2 or R-3 abutting
    R-6, 7.5, 10 or 15 to stand back from the common line by the greater of the
    table setback or the HEIGHT of the building -- 26 ft against a 7 ft side
    yard, decided by the neighbour's zoning."""
    capping = {
        n.fact for n in notes() if n.layer == LAYER and n.state == "unmeasured"
    }

    assert capping == {
        "split_zone",
        "site_specific_limitation",
        "net_developable_area",
        "abuts_lower_density_zone",
    }
