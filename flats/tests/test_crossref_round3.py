"""FOLLOWUPS 105 round 3: Tigard's S-3 parking screen, read (2026-11-08).

Tigard RES-A through RES-C: "off-street parking areas provided at the side
or rear of buildings and not in garages must be screened from adjacent
properties to the S-3 standard, as provided in Table 18.420.2"
(18.280.040.D.4, 18.280/18.280.040.txt#L111). The pod's open rear court is
that parking. Chapter 18.420 was fetched with Steph's OK on 2026-11-08 and
Table 18.420.2 gives S-3 a minimum depth of 5 feet holding a 6 ft
sight-obscuring fence or wall and trees (tdc.18.420.landscaping.txt
#L252-L255). It is encoded as the planted strip between parking and the lot
lines, ``parking_lot_line_buffer_ft`` 5, which the court is measured with --
so the hold the zones carried while the chapter was unread
(``tigard_s3_screen_reaches_court``) is gone.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import load_registry
from flats.score.paper import behind_wall_ft, lot_line_buffer_ft

pytestmark = pytest.mark.unit

TIGARD = "or/washington/tigard"
FIELD = "parking_lot_line_buffer_ft"
SCREENED = ("RES-A", "RES-B", "RES-C")


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize("zone", SCREENED)
def test_the_lower_density_zones_carry_the_5_ft_s3_strip(corpus: RuleSet, zone: str) -> None:
    resolved = corpus.resolve(TIGARD, zone, ())
    assert resolved.get(FIELD) == 5
    assert lot_line_buffer_ft(resolved) == 5.0
    # The quoted lines are the S-3 row of Table 18.420.2 and its column head.
    text = ProvenanceStore().quote(resolved.values[FIELD].prov.quote)
    assert "Minimum Depth" in text
    assert "S-3" in text and "5 feet" in text


@pytest.mark.parametrize("zone", SCREENED)
def test_the_strip_stands_between_the_court_and_the_rear_line(corpus: RuleSet, zone: str) -> None:
    resolved = corpus.resolve(TIGARD, zone, ())
    rear = float(resolved.get("setback_rear_ft") or 0.0)
    # A court reaching 40 ft past the wall needs 45 ft behind it; a yard
    # deeper than court and strip together still governs.
    assert behind_wall_ft(40.0, rear, resolved) == max(rear, 45.0)
    assert behind_wall_ft(0.0, rear, resolved) == rear


def test_the_other_tigard_zones_owe_no_parking_screen(corpus: RuleSet) -> None:
    for zone in corpus.layers[TIGARD].zones:
        if zone not in SCREENED:
            assert corpus.resolve(TIGARD, zone, ()).get(FIELD) is None, zone


def test_the_unread_hold_is_gone() -> None:
    assert "tigard_s3_screen_reaches_court" not in CONDITIONS
    assert "FACT-TIGARD-S3-SCREEN-REACHES-COURT" not in load_registry()


@pytest.mark.parametrize("zone", SCREENED)
def test_the_permission_is_unqualified_again(corpus: RuleSet, zone: str) -> None:
    resolved = corpus.resolve(TIGARD, zone, ())
    assert resolved.get("quadplex_allowed") is True
    assert "tigard_s3_screen_reaches_court" not in resolved.levers
