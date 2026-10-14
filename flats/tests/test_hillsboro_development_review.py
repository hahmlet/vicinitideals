"""Hillsboro zones that need Development Review are YELLOW (Steph 2026-10-14).

CDC 12.80.040 B.1 requires a Development Review approval for "New development
in any zone excluding the exemptions listed in Subsection D.", and D.1 exempts
"Middle housing and single detached dwellings in the MR-1, SCR-LD, or SCR-MD
zones or any R zone". Development Review is a Type II application (12.80.040
E) whose criteria reach the pod as code standards, and "the Review Authority
may impose conditions on the approval" (12.80.040 I).

From 2026-10-10 the by-right-only ruling (2026-10-08) refused these seventeen
zones. Steph's review rule of 2026-10-14 replaced it: "If it's otherwise clear
and measurable, but there is a 'may add conditions', yellow." So the use rows
stand again and each zone carries ``review_discretion: conditions``, which
raises REVIEW-CONDITIONS and holds a passing lot at YELLOW.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

LAYER = "or/washington/hillsboro"
DOC = "or/washington/hillsboro/cdc.12.80.applications.txt"

#: Zones whose use row admits the pod and that D.1 does not exempt.
REVIEWED = (
    "MR-2", "MR-3", "SCR-HD", "SCR-OTC", "SCR-DNC", "SCR-V",
    "SCC-SC", "SCC-MM", "MU-N", "MU-C", "MU-VTC",
    "UC-RM", "UC-MU", "UC-AC", "UC-NC", "UC-OR", "UC-RP",
)
#: The zones D.1 names: middle housing there needs no Development Review.
EXEMPT = ("MR-1", "SCR-LD", "SCR-MD", "R-10", "R-8.5", "R-7", "R-6", "R-4.5")
#: Base false, admitted on a variant: MU-C off an arterial (12.24.250 G), the
#: three retail-frontage zones outside the Retail Focus Frontage.
ON_A_VARIANT = {
    "MU-C": ("local_street",),
    "UC-AC": ("inside_mapped_use_area",),
    "UC-NC": ("inside_mapped_use_area",),
    "UC-OR": ("inside_mapped_use_area",),
}


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize("zone", REVIEWED)
def test_development_review_zones_admit_the_pod_with_a_conditions_flag(
    rules: RuleSet, zone: str
) -> None:
    got = rules.resolve(LAYER, zone, conditions=ON_A_VARIANT.get(zone, ()))
    assert got.values["quadplex_allowed"].value is True
    assert got.values["review_discretion"].value == "conditions"
    assert "12.80.040 I" in got.values["review_discretion"].prov.cite
    assert rules.layers[LAYER].zones[zone].notes.startswith("YELLOW, RE-RULED 2026-10-14")


@pytest.mark.parametrize("zone", EXEMPT)
def test_the_exempt_zones_stay_green_with_no_review(rules: RuleSet, zone: str) -> None:
    got = rules.resolve(LAYER, zone)
    assert got.values["quadplex_allowed"].value is True
    assert "review_discretion" not in got.values


def test_the_ruling_reads_the_stored_text() -> None:
    # The line numbers the notes cite still say what the notes say.
    store = ProvenanceStore()
    b1 = " ".join(store.quote(f"{DOC}#L318-L320").split())
    assert "New development in any zone excluding the exemptions listed in Subsection D." in b1
    d1 = " ".join(store.quote(f"{DOC}#L338-L343").split())
    assert "Middle housing and single detached dwellings in the MR-1, SCR-LD, or SCR-MD zones" in d1
    assert "or any R zone" in d1
    e = " ".join(store.quote(f"{DOC}#L379-L380").split())
    assert "subject to the Type II procedure" in e
    i = " ".join(store.quote(f"{DOC}#L452-L454").split())
    assert "the Review Authority may impose conditions" in i
