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

*The first one, 2026-09-29.* Hillsboro's single-dwelling tables print a corner
lot's coverage five points above a standard lot's -- R-10 40 to 45, R-7 and
R-8.5 45 to 50, R-6 and R-4.5 55 to 60 (Tables 12.21.150-1 to 12.21.550-1,
"45% for standard lot / 50% for corner lot") -- with no land-division gate.
That is real upside, and it is small in kind: coverage decides whether a pod
is allowed onto a lot a few hundred square feet short of the standard figure,
and it moves no wall. It is pinned below as `BY_RIGHT_GAINS` so the next one
still fails loudly. Hillsboro also adds two corner rules that tighten a
setback (MR-1's front 15 to 20, R-8.5's side 6 to 8). How many Hillsboro lots
either set touches is unmeasured until the Washington County map exists.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

#: The corner rules that loosen BY RIGHT -- no `unit_lots` gate -- and that
#: the screen would reach once corner status is computed. Hillsboro's
#: coverage rows, read 2026-09-29; see the module docstring.
BY_RIGHT_GAINS = {
    "or/washington/hillsboro/R-10.max_coverage_pct",
    "or/washington/hillsboro/R-8.5.max_coverage_pct",
    "or/washington/hillsboro/R-7.max_coverage_pct",
    "or/washington/hillsboro/R-6.max_coverage_pct",
    "or/washington/hillsboro/R-4.5.max_coverage_pct",
}


def _audit():
    """The quadfit conftest puts this directory on the path, as it does for
    `common`."""
    import audit_corner_variants

    return audit_corner_variants


def test_no_corner_rule_the_screen_could_reach_adds_room_but_hillsboros_coverage() -> None:
    """The whole finding, in one assertion.

    If this ever fails it is good news and the docstring above is out of date:
    somebody encoded a city whose corner rule loosens by right. Read it before
    changing the test -- a corner-lot computation with real upside is scheduled
    differently to one without. It failed once, for Hillsboro's coverage, and
    was read (module docstring).
    """
    audit = _audit()
    gain = {v.key for v in audit.scan() if v.reachable and v.direction == "loosens"}
    assert gain == BY_RIGHT_GAINS, sorted(gain ^ BY_RIGHT_GAINS)


def test_every_loosening_corner_rule_is_gated_behind_a_plat_we_do_not_draw() -> None:
    """Why the upside is not real rather than merely absent.

    Twenty-eight variants loosen and all of them are double-gated on
    `unit_lots`. That is the middle-housing land-division path: four lots under
    one building. The site plan places a pod on one lot, so the condition is
    never set, and corner status is not what is holding these back.

    Except `BY_RIGHT_GAINS`, which are not gated at all.
    """
    audit = _audit()
    loosening = [v for v in audit.scan()
                 if v.direction == "loosens" and v.key not in BY_RIGHT_GAINS]
    assert len(loosening) > 20, len(loosening)
    for v in loosening:
        assert "unit_lots" in v.when, str(v)


def test_the_reachable_corner_rules_are_the_ones_that_take_room_away() -> None:
    """Same population from the other side, so the count is not zero by
    accident: there ARE corner rules the screen would pick up today, and every
    one of them makes a lot harder to build on, `BY_RIGHT_GAINS` aside."""
    audit = _audit()
    reachable = [v for v in audit.scan()
                 if v.reachable and v.key not in BY_RIGHT_GAINS]
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


def test_only_fourteen_reachable_corner_rules_can_move_a_building() -> None:
    """How much the unbuilt feature is actually worth, pinned.

    Twenty-nine corner rules would fire, but a lot-width or frontage minimum
    only ever decides whether a zone's rules apply at all -- it does not move a
    wall. Four touched a setback, which is what changes an envelope, and 23 of
    the other 25 are Gresham's, a city with no green lots at all.

    Measured against the 2026-09-01 run: 20 green lots are corners in the one
    jurisdiction (Wilsonville) holding a reachable corner setback. That is why
    this is scheduled rather than built. If the number here grows in a NEW
    jurisdiction -- a newly encoded city with greens and a corner setback --
    the calculation changes and the feature stops being cheap to defer.

    Eight joined 2026-09-16 without changing it: Wilsonville's street-side
    yard on a corner lot over 10,000 sq ft and under 100 ft wide is 20
    percent of the lot width (WDC 4.113(.02)A.2), carried as a share on the
    eight zones that take their setbacks from 4.113(.02). Same jurisdiction,
    and the quadfit envelope already charges every street edge of a corner
    lot the larger of the front and the street side, where the over-10,000
    front is 20 -- more than 20 percent of any width under 100 -- so the
    pipeline's corner lots were being cut at least that deep already.

    Two joined 2026-09-29 in a NEW jurisdiction, which is the case this test
    was written to flag: Hillsboro's MR-1 front yard, 15 ft to 20 on a corner,
    and R-8.5's side yard, 6 to 8 (Tables 12.22.150-1 and 12.21.250-1). Both
    are drafts, and how many Hillsboro greens they would cost waits on the
    Washington County map -- measure it then, before deferring again.
    """
    audit = _audit()
    setbacky = [v for v in audit.scan()
                if v.reachable and v.direction == "tightens"
                and v.field.startswith("setback_")]
    assert len(setbacky) == 14, [str(v) for v in setbacky]
    assert {v.layer for v in setbacky} == {
        "or/multnomah/wood-village", "or/clackamas/wilsonville",
        "or/washington/hillsboro",
    }, sorted({v.layer for v in setbacky})
    shares = [v for v in setbacky if getattr(v.alt, "pct", None) is not None]
    assert len(shares) == 8 and {v.field for v in shares} == {"setback_street_side_ft"}
    assert all(v.alt.floor_ft == v.base == 10 for v in shares), [str(v) for v in shares]
