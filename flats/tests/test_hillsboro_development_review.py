"""Hillsboro zones that need Development Review are RED, not green (Steph 2026-10-08).

CDC 12.80.040 B.1 requires a Development Review approval for "New development
in any zone excluding the exemptions listed in Subsection D.", and D.1 exempts
"Middle housing and single detached dwellings in the MR-1, SCR-LD, or SCR-MD
zones or any R zone". Development Review is a Type II application (12.80.040
E), and the by-right-only ruling (2026-10-08) makes a zone whose only path is a
review red, although its use table prints a P. 152 lots in MR-2, SCR-HD,
SCR-V, MR-3, MU-N, SCC-MM and UC-RM were green in live run 70 before this.
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


@pytest.mark.parametrize("zone", REVIEWED)
def test_development_review_zones_refuse_the_pod_outright(zone: str) -> None:
    rules = RuleSet(load_rules())
    use = rules.resolve(LAYER, zone).values["quadplex_allowed"]
    assert use.value is False
    # No condition opens it: SCR-OTC and MU-VTC keep their flag-lot refusal
    # (a lever that can only say no), and nothing else varies.
    assert use.levers <= {"flag_lot"}
    for lever in use.levers:
        pulled = rules.resolve(LAYER, zone, conditions=(lever,)).values["quadplex_allowed"]
        assert pulled.value is False, lever
    assert rules.layers[LAYER].zones[zone].notes.startswith("RED BY RULING (Steph, 2026-10-08")


@pytest.mark.parametrize("zone", EXEMPT)
def test_the_exempt_zones_stay_by_right(zone: str) -> None:
    use = RuleSet(load_rules()).resolve(LAYER, zone).values["quadplex_allowed"]
    assert use.value is True


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
