"""An overlay that applies everywhere must be *fetched* everywhere.

`overlays.yaml` declares the FEMA floodway a carve and the SFHA fringe a flag
for `jurisdictions: all`. That declaration was true of the policy and false of
the data for as long as flood has been screened: `s0_acquire.py` pulled the
NFHL with `"DFIRM_ID" = '41051C'`, which is Multnomah County alone, so every
Clackamas lot was measured against a flood layer that stopped at the county
line and passed for want of it.

Nothing caught it because nothing could. A missing overlay does not raise --
it produces a lot with `ovl_fema_sfha = False`, which is the same value a lot
genuinely outside the floodplain gets, and s7 reads them identically. The only
visible symptom was in the aggregate: 70,196 Clackamas lots recorded ONE flood
touch between them, against 1,239 across 180,548 Multnomah lots. That is what
an absent layer looks like, and it looks exactly like good news.

The invariant these tests pin is the one that would have failed on the day:
**every county the screen keeps lots from must appear in the acquisition filter
of every overlay that claims to apply to all of them.** `KEEP_COUNTIES` in
`s0_acquire` is the single source of truth for which counties are screened, so
adding a third county to it fails these tests until its FEMA study ID is added
in the same breath -- which is the whole point, because the failure mode is
silent and the fix is one string.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.unit


#: FEMA study identifiers are the county FIPS code plus a revision letter, so
#: the mapping from an RLIS county code to a DFIRM prefix is stable and short.
#: Washington is here unused -- it is the county a third jurisdiction would most
#: likely come from, and having it written down is what makes the test's failure
#: message actionable rather than a puzzle.
DFIRM_PREFIX = {
    "M": "41051",  # Multnomah
    "C": "41005",  # Clackamas
    "W": "41067",  # Washington
}


def _s0():
    """The quadfit conftest puts the tool directory on the path."""
    import s0_acquire

    return s0_acquire


def _flood_where() -> str:
    s0 = _s0()
    spec = s0.PHASE2_LAYERS["overlay_fema_flood"]
    return spec.get("where", "")


def test_the_flood_layer_is_fetched_for_every_county_the_screen_keeps() -> None:
    """The assertion that was false until 2026-09-01.

    If this fails after a county is added to `KEEP_COUNTIES`, the fix is to add
    that county's DFIRM prefix to the NFHL `where` clause -- not to relax the
    test. A flood layer that stops at a county line does not report an error, it
    reports dry land.
    """
    s0 = _s0()
    where = _flood_where()
    missing = []
    for code in sorted(s0.KEEP_COUNTIES):
        prefix = DFIRM_PREFIX.get(code)
        assert prefix, (
            f"county code {code!r} is screened but has no DFIRM prefix in this "
            f"test's map -- add it, then check the NFHL filter covers it"
        )
        if prefix not in where:
            missing.append((code, prefix))
    assert not missing, (
        f"screened counties absent from the NFHL filter: {missing}. "
        f"where={where!r}"
    )


def test_the_flood_filter_names_no_county_the_screen_does_not_keep() -> None:
    """The other direction, so the clause cannot quietly rot into a superset.

    Fetching a county we do not screen is not dangerous, only wasteful -- the
    NFHL download is the slowest acquisition in s0. This is the cheap guard that
    keeps the filter honest when a county is REMOVED from the screen.
    """
    s0 = _s0()
    where = _flood_where()
    kept = {DFIRM_PREFIX[c] for c in s0.KEEP_COUNTIES if c in DFIRM_PREFIX}
    named = set(re.findall(r"\b(\d{5})[A-Z0-9]\b", where))
    assert named, f"no DFIRM id found in the NFHL filter: {where!r}"
    assert named <= kept, f"NFHL fetches counties the screen does not keep: {named - kept}"


def test_an_overlay_declared_for_all_jurisdictions_says_so_explicitly() -> None:
    """Which overlays this invariant has to hold for.

    `jurisdictions: all` is the shape that makes a data gap invisible: a
    city-scoped overlay missing its layer is caught by the coverage grades in
    `overlays.yaml`, but an all-jurisdictions one silently grades every lot
    outside its data as clear. Today that is the two FEMA layers. If a third
    appears, it needs the same fetch-coverage argument made about it, and this
    test is where somebody finds that out.
    """
    from common import load_overlays

    specs = load_overlays()
    everywhere = sorted(s.key for s in specs.overlays if s.applies_to("a_city_that_does_not_exist"))
    assert everywhere == ["fema_floodway", "fema_sfha"], everywhere
