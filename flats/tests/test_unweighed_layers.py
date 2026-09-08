"""The coverage ledger's own blind spot, made into a row -- and closed.

The ledger answers "which of the zones we can see are missing rules". It
cannot answer the mirror question, and the mirror question is the one that
hides the larger hole: which of the rules we have written has nothing ever
counted lots against?

For five weeks the answer was ten Clackamas jurisdictions carrying 58 zones,
because the parcel corpus the ledger was built from was Multnomah County only
-- 286,359 rows, ``COUNTY == "M"`` on every one -- while the pipeline it
serves screened two counties. They did not appear on the report as zeroes.
They did not appear. Every ranking, every "N lots blocked" headline and every
judgement about what to encode next was computed over the county somebody
happened to load.

**Closed 2026-09-08.** The ledger was regenerated over the two-county corpus
the screen actually runs on: 333 pairs over 334,959 lots against 155 over
236,889, eighteen jurisdictions against fourteen, and ``unweighed`` returns an
empty list. The cost of the five weeks is on the record and worth keeping
here, because it was not paid in the abstract -- a district audit the same day
ranked fourteen cities at zero lots apiece from the stale ledger and nearly
closed its own queue on the number.

So this file no longer describes a hole. It keeps the check armed, which is a
different job and the reason an empty answer is still worth asserting: the
list grows the moment somebody encodes a jurisdiction in a county nobody has
counted, and that encoding will look finished and rank nowhere.

Asserted from the shipped ledger rather than from the 130 MB corpus. That
keeps the test cheap, and it tests the right thing: what a reader of the
committed file is entitled to be told.
"""

from __future__ import annotations

import pytest

from flats.encode.backlog import UNZONED
from flats.rules.ledger import read_coverage, unweighed
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

#: The four places the screening pipeline is switched off for. An excluded
#: jurisdiction gets no zoning join at all (``s2_assign.py``: ``if j.eligible
#: and j.zoning_layer``), so its lots arrive with no zone rather than not
#: arriving -- which is why they are the whole of the unzoned bucket.
SWITCHED_OFF = {
    "or/clackamas/lake-oswego": 14256,
    "or/multnomah/maywood-park": 327,
    "or/clackamas/rivergrove": 222,
    "or/clackamas/johnson-city": 7,
}


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_no_encoded_layer_is_outside_the_corpus_that_ranks_the_work(
    rules: RuleSet,
) -> None:
    """Empty, and it took five weeks and a wrong published claim to get here.

    The list is meant to shrink and it has shrunk to nothing. It grows again
    the moment somebody encodes a jurisdiction in a county nobody has counted
    -- which is the warning worth having, because that encoding will look
    finished and rank nowhere, exactly as Oregon City's R-2 did on the day it
    was written."""
    blind = unweighed(read_coverage(), rules)

    assert [u.jurisdiction for u in blind] == []


def test_the_ledger_now_spans_both_counties(rules: RuleSet) -> None:
    """334,959 lots over eighteen jurisdictions, and the headline percentage
    is finally a percentage of the land the screen runs on.

    The old version of this test asserted the opposite and was right to: it
    pinned that every Clackamas row belonged to Lake Oswego and totalled 758
    lots. A test that pins a corpus condition goes red when the corpus is
    fixed, and that is the test working."""
    rows = read_coverage()
    counties = {
        row.jurisdiction.split("/")[1]
        for row in rows
        if row.jurisdiction.startswith("or/")
    }
    clackamas = {row.jurisdiction for row in rows if "/clackamas/" in row.jurisdiction}

    assert counties == {"multnomah", "clackamas"}
    assert len({row.jurisdiction for row in rows}) == 18
    assert sum(row.lots for row in rows) == 334_959
    assert len(clackamas) == 11
    assert "or/clackamas/oregon-city" in clackamas
    assert "or/clackamas/_unincorporated" in clackamas


def test_every_jurisdiction_in_the_corpus_maps_to_a_layer(rules: RuleSet) -> None:
    """``observed()`` names an unmapped jurisdiction ``UNMAPPED/<name>`` rather
    than dropping it. There are none, and that is worth asserting rather than
    assuming: the two-county corpus brought four jurisdictions the old one
    never contained, and any of them could have arrived without a mapping."""
    rows = read_coverage()

    assert [r.jurisdiction for r in rows if not r.jurisdiction.startswith("or/")] == []


def test_a_parcel_with_no_zone_leaves_a_row_instead_of_leaving(
    rules: RuleSet,
) -> None:
    """The same failure a third time, and once the smallest of the three. A
    parcel whose zoning join came back blank was dropped by `observed()` with a
    bare `continue` -- 331 lots, 327 of them the whole of Maywood Park, gone
    from the ledger without a row.

    It is not given a zone code. It is given a name that cannot be mistaken for
    one, and it lands as `zone_missing`, which is what it is."""
    unzoned = [row for row in read_coverage() if row.zone == UNZONED]

    assert sum(row.lots for row in unzoned) == 14_822
    assert all(row.status == "zone_missing" for row in unzoned)


def test_the_unzoned_bucket_is_now_policy_rather_than_data(rules: RuleSet) -> None:
    """The finding that came with the rebuild, and the reason the bucket grew
    from 331 lots to 14,822 without anything breaking.

    Being switched off is not gated at report time. s2 joins zoning only where
    the jurisdiction is eligible, so an excluded city's lots never receive a
    zone and are dropped before anything is measured. They arrive here instead,
    under a name that says "no zone" -- so this bucket, which was written to
    catch a join that failed, now mostly holds a decision that was made.

    **14,812 of 14,822 lots are the four excluded places, and 10 are real
    blanks.** Lake Oswego alone is 14,256 of them, which is 96% of all the land
    the screen has been told not to look at, on the strength of a reason
    written about the ninth of the city that lay in the county we could see.
    """
    unzoned = {
        row.jurisdiction: row.lots
        for row in read_coverage()
        if row.zone == UNZONED
    }

    for name, lots in SWITCHED_OFF.items():
        assert unzoned.get(name) == lots, name

    joins = {k: v for k, v in unzoned.items() if k not in SWITCHED_OFF}
    assert sum(joins.values()) == 10
    assert sum(SWITCHED_OFF.values()) == 14_812


def test_a_layer_with_no_zones_is_not_reported_as_unweighed(rules: RuleSet) -> None:
    """The state layer preempts; it has no zones of its own and no lot could
    ever be observed against it. Reporting it would be noise in the one place
    that must not be noisy."""
    blind = {u.jurisdiction for u in unweighed(read_coverage(), rules)}

    assert "or" not in blind
    assert rules.layers["or"].zones == {}


def test_an_observed_layer_is_never_reported_unweighed(rules: RuleSet) -> None:
    """One lot is enough to leave this report, and that is the limitation worth
    stating out loud: `unweighed` catches a corpus that omits a jurisdiction,
    not one that under-samples it -- and not one that is switched off, which is
    how Lake Oswego sits in the ledger with 14,256 lots and no zone on any of
    them while reporting as counted."""
    observed = {row.jurisdiction for row in read_coverage()}
    blind = {u.jurisdiction for u in unweighed(read_coverage(), rules)}

    assert not (observed & blind)
    assert "or/clackamas/lake-oswego" in observed
