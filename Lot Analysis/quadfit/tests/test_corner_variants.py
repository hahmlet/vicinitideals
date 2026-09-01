"""Corner-lot status is a correctness fix, not an opportunity.

Fourteen jurisdictions define what a corner lot is; nothing computes which lots
are corners, so all seventy-eight `corner_lot` variants in the corpus are inert
and the base limb binds everywhere. That has sat on the work list described as
buildable room waiting to be released -- "worth ~10 ft of buildable envelope
wherever corner variants exist" -- and it is the other way round.

The corpus does hold twenty-eight corner variants that loosen, and they are big:
Gresham drops a 100 ft frontage minimum to 32 on a corner and a 75 ft width to
20. **Every one of them also requires `unit_lots`**, the middle-housing
land-division plat, which the site plan does not draw. So computing corner
status would release none of them. It would release twenty-nine that tighten:
Wood Village's side yard from 5 ft to 10 and rear from 15 to 20, Gresham's
frontage minimums from 35 to 40, MDR's lot width from 16 to 70.

The ten feet in the old note is real. It is a cost. That is still worth
building, because a false green is the dangerous kind of error and this is a
pile of them -- but it is worth scheduling as a correctness fix with no upside
in lot count, which goes on a different list to an opportunity.

These tests exist so the finding survives the next person to read the
work list, and so a newly encoded city that adds a REACHABLE loosening corner
rule -- which would genuinely change the calculation -- fails loudly instead of
quietly making the docstring above wrong.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _audit():
    """The quadfit conftest puts this directory on the path, as it does for
    `common`."""
    import audit_corner_variants

    return audit_corner_variants


def test_no_corner_rule_the_screen_could_reach_adds_buildable_room() -> None:
    """The whole finding, in one assertion.

    If this ever fails it is good news and the docstring above is out of date:
    somebody encoded a city whose corner rule loosens by right. Read it before
    changing the test -- a corner-lot computation with real upside is scheduled
    differently to one without.
    """
    audit = _audit()
    gain = [v for v in audit.scan() if v.reachable and v.direction == "loosens"]
    assert gain == [], [str(v) for v in gain]


def test_every_loosening_corner_rule_is_gated_behind_a_plat_we_do_not_draw() -> None:
    """Why the upside is not real rather than merely absent.

    Twenty-eight variants loosen and all of them are double-gated on
    `unit_lots`. That is the middle-housing land-division path: four lots under
    one building. The site plan places a pod on one lot, so the condition is
    never set, and corner status is not what is holding these back.
    """
    audit = _audit()
    loosening = [v for v in audit.scan() if v.direction == "loosens"]
    assert len(loosening) > 20, len(loosening)
    for v in loosening:
        assert "unit_lots" in v.when, str(v)


def test_the_reachable_corner_rules_are_the_ones_that_take_room_away() -> None:
    """Same population from the other side, so the count is not zero by
    accident: there ARE corner rules the screen would pick up today, and every
    one of them makes a lot harder to build on."""
    audit = _audit()
    reachable = [v for v in audit.scan() if v.reachable]
    assert len(reachable) > 30, len(reachable)

    directions = {v.direction for v in reachable}
    assert "loosens" not in directions, sorted(directions)
    assert "tightens" in directions


def test_the_ten_feet_in_the_old_note_is_wood_village_and_it_is_a_cost() -> None:
    """The specific claim that sent this to the work list as an opportunity.

    WVDC 720.030 hands over a corner-lot definition word for word from
    Portland's curve clause, and the rule it feeds takes the LR 7.5 side yard
    from 5 ft to 10 -- ten feet across a 56 ft pod, in the direction that loses
    lots rather than wins them.
    """
    audit = _audit()
    wv = {
        v.key: v for v in audit.scan()
        if v.layer == "or/multnomah/wood-village" and v.reachable
    }
    side = wv["or/multnomah/wood-village/LR 7.5.setback_side_ft"]
    assert (side.base, side.alt) == (5, 10)
    assert side.direction == "tightens"

    rear = wv["or/multnomah/wood-village/LR 7.5.setback_rear_ft"]
    assert (rear.base, rear.alt) == (15, 20)
    assert rear.direction == "tightens"
