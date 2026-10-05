"""The room each passing standard had to spare (FOLLOWUPS 37(ii)).

The record the bridge writes beside the answer, and the growth model the pod
design report tries a bigger or taller pod with (:mod:`flats.score.margins`).
"""

from __future__ import annotations

import json

import pytest

from flats.score import margins as mg
from flats.score.screen import Screening, Triage
from flats.score.slack import SlackPolicy, Verdict

POLICY = SlackPolicy(tolerance={"fit_ft": 0.5})


def _checks():
    return (
        # A ceiling with room: 30 % of the lot built on under a 40 % cap.
        POLICY.evaluate("coverage_pct", 30.0, 40.0, is_maximum=True),
        # A floor with room: 6,000 sqft of lot over a 5,000 minimum.
        POLICY.evaluate("lot_area_sqft", 6000.0, 5000.0, is_maximum=False),
        # Exactly at the limit is a pass with nothing to spare.
        POLICY.evaluate("height_ft", 35.0, 35.0, is_maximum=True),
        # Inside the tolerance: a miss the flag record already carries.
        POLICY.evaluate("fit_ft", 59.7, 60.0, is_maximum=False),
        # Outright miss.
        POLICY.evaluate("far", 0.9, 0.75, is_maximum=True),
    )


def test_only_outright_passes_are_kept() -> None:
    checks = _checks()
    assert {c.check: c.verdict for c in checks}["fit_ft"] is Verdict.tolerated
    kept = mg.passing(checks)
    assert [c.check for c in kept] == ["coverage_pct", "lot_area_sqft", "height_ft"]
    assert all(c.slack >= 0 for c in kept)


def test_the_record_is_observed_threshold_room_in_the_checks_own_units() -> None:
    got = mg.record(_checks())
    assert got == {
        "coverage_pct": [30.0, 40.0, 10.0],
        "lot_area_sqft": [6000.0, 5000.0, 1000.0],
        "height_ft": [35.0, 35.0, 0.0],
    }


def test_the_column_is_compact_json_and_empty_when_nothing_passed() -> None:
    text = mg.dumps(_checks())
    assert " " not in text
    assert json.loads(text) == mg.record(_checks())
    # Keys sorted, so two runs of the same lot write the same bytes.
    assert list(json.loads(text)) == sorted(json.loads(text))
    misses = [c for c in _checks() if c.verdict is not Verdict.passes]
    assert mg.dumps(misses) == ""
    assert mg.dumps([]) == ""


def test_the_record_is_rounded_and_never_writes_a_negative_zero() -> None:
    c = POLICY.evaluate("setback_ft", 10.00001, 10.0, is_maximum=False)
    assert mg.record([c]) == {"setback_ft": [10.0, 10.0, 0.0]}
    assert "-0" not in mg.dumps([c])


def test_a_stored_record_reads_back_from_text_or_a_mapping() -> None:
    text = mg.dumps(_checks())
    for raw in (text, json.loads(text)):
        got = mg.loads(raw)
        assert set(got) == {"coverage_pct", "lot_area_sqft", "height_ft"}
        cov = got["coverage_pct"]
        assert (cov.observed, cov.threshold, cov.slack) == (30.0, 40.0, 10.0)
        assert cov.share == pytest.approx(0.25)
    assert mg.loads(None) == {} and mg.loads("") == {}
    with pytest.raises(ValueError):
        mg.loads("[1, 2, 3]")


def test_a_limit_of_zero_has_no_share() -> None:
    assert mg.Margin("x", 0.0, 0.0, 0.0).share is None


def test_the_screening_hands_over_its_passes_and_its_colour_does_not_read_them() -> None:
    checks = _checks()
    s = Screening(triage=Triage.green, checks=checks)
    assert s.margins == mg.passing(checks)
    # The same answer with no checks at all keeps its colour: the margins
    # are derived from the checks, and the colour reads binds and flags.
    assert Screening(triage=Triage.green).colour == s.colour


# --- what a bigger or taller pod does ---------------------------------------


def test_a_longer_run_adds_the_step_times_the_other_side() -> None:
    # A 24 x 60 pod: the fit measured along the 60 ft side, so a foot more
    # run adds 24 sqft; measured along the 24 ft side, it adds 60.
    assert mg.grown(1.0, 60.0, 24.0, 60.0) == 24.0
    assert mg.grown(2.0, 24.0, 24.0, 60.0) == 120.0
    assert mg.grown(-1.0, 60.0, 24.0, 60.0) == -24.0
    assert mg.grown(1.0, None, 24.0, 60.0) is None


def test_coverage_and_floor_area_grow_with_the_footprint() -> None:
    change = mg.Change(extra_sqft=144.0, ground_sqft=1440.0, lot_sqft=6000.0)
    assert mg.after("coverage_pct", 30.0, change) == pytest.approx(33.0)
    assert mg.after("far", 0.5, change) == pytest.approx(0.55)


def test_paving_adds_and_open_space_takes_the_extra_footprint() -> None:
    change = mg.Change(extra_sqft=60.0, ground_sqft=1440.0, lot_sqft=6000.0)
    assert mg.after("impervious_pct", 50.0, change) == pytest.approx(51.0)
    assert mg.after("landscaped_pct", 30.0, change) == pytest.approx(29.0)
    assert mg.after("open_space_pct", 30.0, change) == pytest.approx(29.0)
    assert mg.after("open_space_sqft", 900.0, change) == pytest.approx(840.0)


def test_a_share_of_the_lot_needs_the_lot() -> None:
    change = mg.Change(extra_sqft=60.0, ground_sqft=1440.0, lot_sqft=None)
    assert mg.after("impervious_pct", 50.0, change) is None
    # Coverage scales on the footprint alone, so it still moves.
    assert mg.after("coverage_pct", 30.0, change) == pytest.approx(31.25)


def test_a_taller_pod_moves_height_foot_for_foot_and_nothing_else() -> None:
    change = mg.Change(taller_ft=2.0)
    assert mg.after("height_ft", 33.0, change) == 35.0
    assert mg.after("min_height_ft", 20.0, change) == 22.0
    assert mg.after("coverage_pct", 30.0, change) is None
    assert mg.after("stories", 3.0, change) is None


def test_the_standards_a_pod_does_not_move_read_as_unmoved() -> None:
    change = mg.Change(extra_sqft=144.0, ground_sqft=1440.0, lot_sqft=6000.0)
    for check in ("lot_area_sqft", "lot_width_ft", "density_du_per_acre", "parking_stalls"):
        assert mg.after(check, 1.0, change) is None


def test_the_shortfall_reads_the_side_of_the_limit() -> None:
    assert mg.shortfall("coverage_pct", 42.0, 40.0) == pytest.approx(2.0)
    assert mg.shortfall("coverage_pct", 38.0, 40.0) == 0.0
    assert mg.shortfall("landscaped_pct", 28.0, 30.0) == pytest.approx(2.0)
    assert mg.shortfall("min_height_ft", 22.0, 20.0) == 0.0
    assert mg.ceiling("height_ft") and not mg.ceiling("open_space_sqft")
