"""The other axis, and the thirty-eight zones that stated it into silence.

Thirty-eight zones across eight jurisdictions state a minimum lot depth. Every
one of them was read, quoted, cited and signed, and not one had ever been
compared against a parcel -- because nothing in either pipeline measured a lot
depth. The standard was encoded and then skipped, which is a worse failure than
an unencoded standard: an unencoded one shows up in a gap ledger and this
showed up nowhere. It took the reach ledger to say so out loud.

There is a tempting way to get a depth without measuring one, and it is wrong.
``area / frontage_ft`` has the units of a depth and is not one, because
``frontage_ft`` is the **sum** of every street-facing edge on the parcel. A
corner lot carries two of them and one Milwaukie parcel carried seven, so on
exactly the lots most likely to be corners the quotient is a fraction of the
real depth -- and it fails toward refusal, which is the dangerous direction.
That proxy forecast 38 Milwaukie lots failing on width or depth. Measured
properly it was six, and one of those six misses by six inches.

Two conventions from ``test_average_width.py``, for the same reasons:

* the mechanism is tested on rules written in this file, never on the corpus,
  so a test cannot go red because Milwaukie reworded a sentence;
* the corpus tests assert only that what is on file is internally true.

The measurement rules BOTH ways or it is an amnesty. A shallow lot is refused
here; a lot nothing measured is left unchecked, never refused. Both halves are
pinned below.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import load_catalog  # noqa: E402
from flats.fit.rectangle import Fit  # noqa: E402
from flats.rules.fields import FIELDS, OPTIONAL_FIELDS  # noqa: E402
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved  # noqa: E402
from flats.rules.resolver import Verdict as RuleVerdict, ZoneResolution  # noqa: E402
from flats.score.screen import CHECK_FIELD, LotFacts, Triage, screen  # noqa: E402
from flats.score.slack import SlackPolicy, Verdict  # noqa: E402

pytestmark = pytest.mark.unit

DEPTH = "min_lot_depth_ft"
RATIO = "max_lot_depth_ratio"

WHERE = "or/clackamas/milwaukie"
PROV = Provenance(
    cite="Milwaukie MMC 19.301.4",
    url="https://www.milwaukieoregon.gov/citycode",
    retrieved=date(2026, 8, 14),
)
POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})

DESIGN = load_catalog().latest("pod56x36")

#: Generous on everything else, so a test can break exactly one standard.
CLEAR = {
    "quadplex_allowed": True,
    "min_lot_sqft": 3000,
    "setback_front_ft": 10,
    "setback_rear_ft": 10,
    "setback_side_ft": 5,
    "min_frontage_ft": 25,
    "min_lot_width_ft": 25,
    "max_coverage_pct": 60,
    "max_far": 2.0,
    "max_height_ft": 60,
    "max_units": 4,
    "parking_min_per_unit": 1.0,
}


def rules(**overrides) -> ZoneResolution:
    values = {**CLEAR, **overrides}
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R-MD",
        verdict=RuleVerdict.trusted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=PROV,
                layer=WHERE,
                origin="zone",
            )
            for name, value in values.items()
            if value is not None
        },
    )


def fit() -> Fit:
    """Room to spare on everything geometric, so depth is the only question."""
    depth_ft = 36.0
    best = depth_ft + DESIGN.parking.court_depth_ft + 4.0
    return Fit(
        fits=True,
        width_ft=56.0,
        depth_ft=depth_ft,
        best_depth_ft=best,
        slack_ft=best - depth_ft,
    )


def lot(
    *,
    deep: float | None = 100.0,
    wide: float | None = 60.0,
    frontage: float = 60.0,
) -> LotFacts:
    """One parcel. ``frontage`` is stated separately from ``wide`` on purpose:
    they are three different lines and the screen must never swap them."""
    return LotFacts(
        lot_sqft=12000,
        frontage_ft=frontage,
        lot_width_ft=wide,
        lot_depth_ft=deep,
    )


def run(rule_set=None, parcel: LotFacts | None = None):
    return screen(rule_set or rules(), parcel or lot(), DESIGN, fit(), policy=POLICY)


def check(result, name: str):
    """One named check off a screening result, or None if it never ran."""
    return next((c for c in result.checks if c.check == name), None)


# --- the depth row is a standard, and it is now tested -----------------------


def test_a_deep_enough_lot_clears_the_row() -> None:
    result = run(rules(**{DEPTH: 80}), lot(deep=100))

    assert check(result, DEPTH).verdict is Verdict.passes
    assert result.triage is Triage.green


def test_a_shallow_lot_does_not_clear_it() -> None:
    """Five adjacent parcels on SE Vernie Ave in Milwaukie are ninety-eight
    feet wide and sixty-four feet deep against an eighty-foot standard. They
    genuinely fail, and until this row was wired nothing in the screen was
    able to say so. This is the half that costs, and a measurement without it
    is an amnesty."""
    result = run(rules(**{DEPTH: 80}), lot(deep=64, wide=98, frontage=98))

    assert check(result, DEPTH).verdict is not Verdict.passes
    assert result.triage is not Triage.green


def test_a_lot_nobody_measured_is_held_and_never_refused() -> None:
    """The other half of the same bargain. A depth of ``None`` is "not
    measured", and refusing a lot on a number nobody took is the false RED
    this project exists to avoid -- it silently deletes an acquisition target
    and nobody ever learns it existed."""
    result = run(rules(**{DEPTH: 80}), lot(deep=None))

    assert check(result, DEPTH) is None, "the check does not run"
    assert DEPTH in result.unchecked, "and says so, rather than passing quietly"


def test_a_zone_that_states_no_depth_is_not_an_incomplete_zone() -> None:
    # Most Oregon codes state no depth at all. Silence is not a gap, and the
    # field is optional for exactly that reason.
    result = run(rules(), lot(deep=100))

    assert check(result, DEPTH) is None
    assert DEPTH in OPTIONAL_FIELDS


# --- the ceiling on the same number ------------------------------------------


def test_a_lot_no_more_than_three_times_deeper_than_wide_clears_the_ratio() -> None:
    # Fairview 19.30 caps lot depth at three times the width. 60 x 180 is
    # exactly at it, and exactly at it passes.
    result = run(rules(**{RATIO: 3}), lot(wide=60, deep=180))

    assert check(result, RATIO).verdict is Verdict.passes


def test_a_lot_four_times_deeper_than_wide_does_not() -> None:
    result = run(rules(**{RATIO: 3}), lot(wide=60, deep=240))

    assert check(result, RATIO).verdict is not Verdict.passes


def test_the_ratio_needs_both_numbers_and_assumes_neither() -> None:
    """It is written against the width rather than in feet, so a lot holding
    one of the two measurements cannot be judged on it. Half a ratio is not a
    conservative ratio, it is a guess."""
    no_depth = run(rules(**{RATIO: 3}), lot(wide=60, deep=None))
    assert check(no_depth, RATIO) is None and RATIO in no_depth.unchecked

    no_width = run(rules(**{RATIO: 3}), lot(wide=None, deep=180))
    assert check(no_width, RATIO) is None and RATIO in no_width.unchecked


# --- depth is not a quotient of the two numbers already held -----------------


def test_the_verdict_does_not_move_when_the_frontage_does() -> None:
    """The indictment of ``area / frontage_ft``, pinned.

    Two parcels, same area and same measured depth, one with sixty feet of
    street and one with three hundred and forty-six -- a corner lot, both
    edges summed, which is what that column holds. Under the proxy the second
    reads 35 ft deep and is refused. Measured, both are 100 ft deep and both
    pass, and the screen must read the measurement.
    """
    interior = run(rules(**{DEPTH: 80}), lot(deep=100, frontage=60))
    corner = run(rules(**{DEPTH: 80}), lot(deep=100, frontage=346))

    assert check(interior, DEPTH).verdict is Verdict.passes
    assert check(corner, DEPTH).verdict is Verdict.passes
    assert check(interior, DEPTH).observed == check(corner, DEPTH).observed


# --- and what is on file is internally true ----------------------------------


def test_both_depth_standards_are_wired_to_a_check() -> None:
    """The reach ledger's complaint, as a test that fails the day somebody
    unwires one. A field in the registry that no screen names is a reviewer's
    care buying nothing."""
    for field in (DEPTH, RATIO):
        assert field in FIELDS
        assert field in CHECK_FIELD


def test_every_encoded_depth_is_quoted_from_a_line_that_states_one() -> None:
    stated = 0
    for lid, layer in load_rules(strict=False).items():
        for zone_name, zone in (layer.zones or {}).items():
            for field in (DEPTH, RATIO):
                value = zone.values.get(field)
                if value is None:
                    continue
                stated += 1
                assert value.prov.quote, (
                    f"{lid} {zone_name} {field} has no quote"
                )
    # A floor rather than a pin: the count moves every time a district is
    # encoded, and a test that pins a corpus condition goes red when the
    # corpus is fixed.
    assert stated >= 38, "the corpus has lost lot-depth standards it held"
