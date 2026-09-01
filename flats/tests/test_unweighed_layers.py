"""The coverage ledger's own blind spot, made into a row.

The ledger answers "which of the zones we can see are missing rules". It
cannot answer the mirror question, and the mirror question is the one that
hides the larger hole: which of the rules we have written has nothing ever
counted lots against?

The parcel corpus the ledger is built from -- quadfit's ``s2_lots.parquet`` --
is Multnomah County only. 286,359 rows, ``COUNTY == "M"`` on every one. Ten
encoded Clackamas jurisdictions carrying 55 zones between them have never had
a single lot weighed against them, and they do not appear on the report as
zeroes: they do not appear at all. Every ranking, every "N lots blocked"
headline and every judgement about what to encode next is computed over the
county somebody happened to load.

Lake Oswego looked like the exception and was not. Its rows come from the
sliver of the city inside Multnomah -- 757 lots, in exactly the four zones
that were encoded -- which is precisely why the six zones it was missing could
not surface here. See ``flats/tests/test_lake_oswego_zones.py``.

Asserted from the shipped ledger rather than from the 62 MB corpus. That keeps
the test cheap, and it tests the right thing: what a reader of the committed
file is entitled to be told.
"""

from __future__ import annotations

import pytest

from flats.encode.backlog import UNZONED
from flats.rules.ledger import read_coverage, unweighed
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_every_clackamas_layer_is_outside_the_corpus_that_ranks_the_work(
    rules: RuleSet,
) -> None:
    """The whole county, minus the one city with a foot in Multnomah.

    This list is meant to shrink. It shrinks when Clackamas parcels are loaded,
    and it grows the moment somebody encodes a jurisdiction in a county nobody
    has counted -- which is the warning worth having, because that encoding
    will look finished and rank nowhere."""
    blind = unweighed(read_coverage(), rules)

    assert [u.jurisdiction for u in blind] == [
        "or/clackamas/_unincorporated",
        "or/clackamas/gladstone",
        "or/clackamas/happy-valley",
        "or/clackamas/johnson-city",
        "or/clackamas/milwaukie",
        "or/clackamas/oregon-city",
        "or/clackamas/rivergrove",
        "or/clackamas/tualatin",
        "or/clackamas/west-linn",
        "or/clackamas/wilsonville",
    ]
    # 57 as of 2026-09-01: Wilsonville's V and TC. Both are blind in exactly
    # the way this test is about -- Villebois is 2,508 lots and ranks nowhere,
    # because no Clackamas parcel is loaded to rank it with.
    assert sum(u.zones for u in blind) == 57


def test_and_the_ledger_totals_are_multnomah_only(rules: RuleSet) -> None:
    """236,889 lots is not "the market". It is one county, and the headline
    percentage is a percentage of it."""
    rows = read_coverage()
    counties = {
        row.jurisdiction.split("/")[1]
        for row in rows
        if row.jurisdiction.startswith("or/")
    }

    assert counties == {"multnomah", "clackamas"}
    clackamas = [row for row in rows if row.jurisdiction.startswith("or/clackamas/")]
    assert {row.jurisdiction for row in clackamas} == {"or/clackamas/lake-oswego"}
    assert sum(row.lots for row in clackamas) == 758


def test_a_parcel_with_no_zone_leaves_a_row_instead_of_leaving(
    rules: RuleSet,
) -> None:
    """The same failure a third time, and the smallest of the three. A parcel
    whose zoning join came back blank was dropped by `observed()` with a bare
    `continue` -- 331 lots, 327 of them the whole of Maywood Park, gone from
    the ledger without a row.

    It is not given a zone code. It is given a name that cannot be mistaken
    for one, and it lands as `zone_missing`, which is what it is."""
    unzoned = [row for row in read_coverage() if row.zone == UNZONED]

    assert sum(row.lots for row in unzoned) == 331
    assert {row.jurisdiction: row.lots for row in unzoned} == {
        "or/multnomah/maywood-park": 327,
        "or/clackamas/lake-oswego": 1,
        "or/multnomah/fairview": 1,
        "or/multnomah/troutdale": 1,
        "UNMAPPED/nan": 1,
    }
    assert all(row.status in ("zone_missing", "jurisdiction_missing") for row in unzoned)


def test_a_layer_with_no_zones_is_not_reported_as_unweighed(rules: RuleSet) -> None:
    """The state layer preempts; it has no zones of its own and no lot could
    ever be observed against it. Reporting it would be noise in the one place
    that must not be noisy."""
    blind = {u.jurisdiction for u in unweighed(read_coverage(), rules)}

    assert "or" not in blind
    assert rules.layers["or"].zones == {}


def test_an_observed_layer_is_never_reported_unweighed(rules: RuleSet) -> None:
    """Whatever else is true of Lake Oswego's 757 lots, they are lots, and one
    lot is enough to leave this report. That is the limitation worth stating
    out loud: `unweighed` catches a corpus that omits a jurisdiction, not one
    that under-samples it."""
    observed = {row.jurisdiction for row in read_coverage()}
    blind = {u.jurisdiction for u in unweighed(read_coverage(), rules)}

    assert not (observed & blind)
    assert "or/clackamas/lake-oswego" in observed
