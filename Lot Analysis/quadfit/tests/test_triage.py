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


def test_an_assumed_aisle_is_provenance_and_not_a_verdict():
    """The assumed aisle held 1,056 otherwise-clean lots at REVIEW for one run,
    and then stopped, on the statute the whole screen rests on.

    ORS 197A.400 lets a city apply only clear and objective standards to
    housing. Milwaukie and Wilsonville never wrote a drive-aisle width down --
    checked to the end of OAR 660-046-0220(2)(e)(E)'s single-family redirect --
    so there is no width for a court to fail against. Silence is a stronger
    position than a published number: Troutdale's 25 ft binds, and nothing
    binds here.

    So the flag grades nothing. It survives as a column a reviewer can filter,
    which is why this test asserts it is carried and ignored rather than
    deleting it.
    """
    lots = _run(
        [
            _base_row(parking_tier="min", geometry_assumed=False),
            _base_row(parking_tier="min", geometry_assumed=True),
        ],
        has_siteplan=True,
    )

    assert list(lots["triage"]) == ["green", "green"]
    assert list(lots["geometry_assumed"]) == [False, True]


def test_an_assumed_aisle_rescues_nothing_that_actually_fails():
    """The flag is inert in both directions. A lot that cannot take the
    building is red whether its aisle was published or assumed -- otherwise
    the column would be quietly laundering failures into review."""
    reds = _run(
        [
            _base_row(parking_tier="min", geometry_assumed=True,
                      fits_pod=False, fits_cov_pod=False),
            _base_row(parking_tier="min", geometry_assumed=True,
                      site_plan_ok=False, layout_method="none"),
        ],
        has_siteplan=True,
    )["triage"]
    assert list(reds) == ["red", "red"]


def test_a_real_review_trigger_still_fires_on_an_assumed_lot():
    """An assumed aisle must not shadow the triggers that do mean something.
    Same row, same flag, one unmapped sewer -- still yellow."""
    (only,) = _run(
        [_base_row(parking_tier="min", geometry_assumed=True,
                   sewer_main_dist_ft=float("nan"))],
        has_siteplan=True,
    )["triage"]
    assert only == "review"

