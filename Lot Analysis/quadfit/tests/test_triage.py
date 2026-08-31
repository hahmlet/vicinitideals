"""Unit tests for s7's per-lot failure attribution + green/review/red triage
(`attribute_and_triage`). Pure function over a lots DataFrame, so every
binding-constraint branch and every review trigger is exercised directly with a
hand-built frame — no pipeline run needed."""

from __future__ import annotations

import pytest

pytest.importorskip("pandas")
pytest.importorskip("numpy")

import pandas as pd  # noqa: E402

from s7_report import attribute_and_triage  # noqa: E402

pytestmark = pytest.mark.unit


class _Z:
    def __init__(self, zone, confidence):
        self.zone, self.confidence = zone, confidence


class _J:
    def __init__(self, eligible, zones):
        self.eligible, self.zones = eligible, zones


class _Rules:
    """Minimal stand-in: gresham/UNVERIFIED is the only needs_verification zone."""
    def __init__(self):
        self.jurisdictions = {
            "gresham": _J(True, [_Z("LDR-5", "verified"),
                                 _Z("UNVERIFIED", "needs_verification")]),
        }


FP = ["pod"]


def _base_row(**over):
    """A clean, buildable, trustworthy lot; override fields per test case."""
    r = {
        "frontage_ft": 50.0, "area_sqft": 5000.0,
        "fits_pod": True, "fits_cov_pod": True,
        "eligible": True, "policy_exclusion": "", "tier": "A",
        "jurisdiction": "gresham", "zone": "LDR-5",
        "slope_tier": "ideal", "sewer_main_dist_ft": 30.0, "ovl_flag": False,
        "in_sewer_district": False,
        # site-plan columns (only read when has_siteplan=True)
        "parking_tier": "not_evaluated", "site_plan_ok": True,
        "stalls_provided": 8, "open_space_ok": True, "layout_method": "x",
    }
    r.update(over)
    return r


def _run(rows, has_siteplan=False, min_stalls=4):
    lots = pd.DataFrame(rows)
    attribute_and_triage(lots, FP, _Rules(), has_siteplan, ["ovl_flag"], min_stalls)
    return lots


def test_binding_constraint_first_hit_ladder():
    rows = [
        _base_row(eligible=False, policy_exclusion="lot_below_zone_min_area"),
        _base_row(tier="D"),
        _base_row(fits_pod=False, fits_cov_pod=False),
        _base_row(fits_pod=True, fits_cov_pod=False),
        _base_row(),  # clean -> buildable
    ]
    lots = _run(rows)
    assert list(lots["binding_constraint"]) == [
        "lot_below_zone_min_area", "no_buildable_envelope",
        "pod_no_fit", "over_coverage", "",
    ]
    assert list(lots["triage"]) == ["red", "red", "red", "red", "green"]


def test_review_triggers_each_route_to_review_not_green():
    rows = [
        _base_row(),                              # green
        _base_row(frontage_ft=20.0, area_sqft=6000.0),  # flag_suspect neck
        _base_row(tier="C"),                      # irregular geometry
        _base_row(slope_tier="unknown"),          # no DEM
        _base_row(slope_tier="cost_prohibitive"),  # steep
        _base_row(sewer_main_dist_ft=500.0),      # far sewer
        _base_row(sewer_main_dist_ft=float("nan")),  # unknown sewer
        _base_row(zone="UNVERIFIED"),             # unverified zone rule
        _base_row(ovl_flag=True),                 # flag overlay touched
    ]
    lots = _run(rows)
    assert list(lots["triage"]) == ["green"] + ["review"] * 8
    # a review lot still passes the hard tests (no binding constraint)
    assert (lots["binding_constraint"] == "").all()
    # the flag-pole false-green is specifically caught
    assert bool(lots.loc[1, "flag_suspect"]) is True


def test_sewer_district_gate_clackamas_main_wins():
    # Clackamas, "main wins": a mapped main within reach stays green regardless
    # of district. No main -> inside a district = yellow, outside = hard red.
    rows = [
        # near a main -> green even though outside any district (main wins)
        _base_row(jurisdiction="happy_valley", sewer_main_dist_ft=30.0,
                  in_sewer_district=False),
        # no main, inside a district -> review (yellow)
        _base_row(jurisdiction="happy_valley", sewer_main_dist_ft=500.0,
                  in_sewer_district=True),
        _base_row(jurisdiction="clackamas_unincorporated",
                  sewer_main_dist_ft=float("nan"), in_sewer_district=True),
        # no main, outside every district -> red (no_public_sewer)
        _base_row(jurisdiction="clackamas_unincorporated",
                  sewer_main_dist_ft=500.0, in_sewer_district=False),
        _base_row(jurisdiction="tualatin", sewer_main_dist_ft=float("nan"),
                  in_sewer_district=False),
    ]
    lots = _run(rows)
    assert list(lots["triage"]) == ["green", "review", "review", "red", "red"]
    assert list(lots["binding_constraint"]) == [
        "", "", "", "no_public_sewer", "no_public_sewer"]


def test_multnomah_no_main_stays_review_never_red():
    # No sewer-district map exists in Multnomah, so a no-main lot there stays
    # yellow — it must never be forced red by the district gate.
    rows = [
        _base_row(jurisdiction="gresham", sewer_main_dist_ft=500.0,
                  in_sewer_district=False),
        _base_row(jurisdiction="multnomah_unincorporated",
                  sewer_main_dist_ft=float("nan"), in_sewer_district=False),
    ]
    lots = _run(rows)
    assert list(lots["triage"]) == ["review", "review"]
    assert (lots["binding_constraint"] == "").all()


def test_sewer_district_column_absent_is_backward_compatible():
    # Pre-district parquet has no in_sewer_district column: a far-sewer Clackamas
    # lot must stay review (never red), and the function must not raise.
    rows = [_base_row(jurisdiction="happy_valley", sewer_main_dist_ft=500.0),
            _base_row(jurisdiction="happy_valley", sewer_main_dist_ft=30.0)]
    lots = pd.DataFrame(rows).drop(columns=["in_sewer_district"])
    attribute_and_triage(lots, FP, _Rules(), False, ["ovl_flag"], 0)
    assert list(lots["triage"]) == ["review", "green"]
    assert (lots["binding_constraint"] == "").all()


def test_carve_overlay_or_verified_zone_stays_green():
    # a non-flag overlay column must NOT trip review (only flag_ovl_cols do)
    rows = [_base_row(), _base_row()]
    lots = pd.DataFrame(rows)
    lots["ovl_carve"] = [True, True]  # present but not in flag_ovl_cols
    attribute_and_triage(lots, FP, _Rules(), False, ["ovl_flag"], 0)
    assert list(lots["triage"]) == ["green", "green"]


def test_siteplan_subreasons_when_evaluated():
    rows = [
        _base_row(parking_tier="fail", site_plan_ok=False, layout_method="none"),
        _base_row(parking_tier="fail", site_plan_ok=False, layout_method="x",
                  open_space_ok=False),
        _base_row(parking_tier="minimum", site_plan_ok=False, layout_method="x",
                  open_space_ok=True, stalls_provided=2),
        # evaluated + site_plan_ok True -> buildable (green)
        _base_row(parking_tier="preferred", site_plan_ok=True),
        # NOT evaluated -> site-plan never binds even if site_plan_ok is False
        _base_row(parking_tier="not_evaluated", site_plan_ok=False,
                  layout_method="none"),
    ]
    lots = _run(rows, has_siteplan=True, min_stalls=4)
    assert list(lots["binding_constraint"]) == [
        "siteplan_no_layout", "siteplan_open_space_short",
        "siteplan_too_few_stalls", "", "",
    ]
    assert list(lots["triage"]) == ["red", "red", "red", "green", "green"]


def test_a_plan_drawn_to_an_assumed_aisle_is_review_and_never_green():
    """s6s draws Milwaukie and Wilsonville to an aisle nobody published.

    That is worth doing -- a plan with a caveat beats 6,091 lots nobody
    attempted -- but only because this is the other half of it. The lot passes
    every hard test, keeps its stall count, and still cannot be told to an
    acquisitions team as a green. Everything else about the row is clean, so
    the flag is the only thing standing between it and a verdict.
    """
    green, assumed = _run(
        [
            _base_row(parking_tier="min", geometry_assumed=False),
            _base_row(parking_tier="min", geometry_assumed=True),
        ],
        has_siteplan=True,
    )["triage"]

    assert green == "green"
    assert assumed == "review"


def test_a_run_from_before_the_assumption_still_triages():
    """The column is absent on older parquet, and absent means nothing assumed.

    A missing caveat must not read as a caveat on everything, or every stored
    run in the repo would go yellow the day this shipped.
    """
    (only,) = _run([_base_row(parking_tier="min")], has_siteplan=True)["triage"]
    assert only == "green"


def test_an_assumed_lot_that_fails_a_hard_test_is_still_red():
    """The flag downgrades a pass. It does not upgrade a failure into review,
    which would hide a lot that genuinely cannot take the building."""
    (only,) = _run(
        [_base_row(parking_tier="min", geometry_assumed=True,
                   fits_pod=False, fits_cov_pod=False)],
        has_siteplan=True,
    )["triage"]
    assert only == "red"

