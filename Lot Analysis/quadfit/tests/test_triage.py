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
    def __init__(self, zone, confidence, min_density=None, density_from_sqft=None):
        self.zone, self.confidence = zone, confidence
        self.min_density_du_per_acre = min_density
        #: Where a city applies its density floor only above a lot size --
        #: Gresham's MDR-24 starts at 11,000 sq ft -- the RATE itself is banded,
        #: so a small lot has no floor rather than a floor it clears.
        self.density_from_sqft = density_from_sqft

    def density_floor_lot_sqft(self, units: int = 4, lot_area_sqft=None):
        if not self.min_density_du_per_acre:
            return None
        if (
            self.density_from_sqft is not None
            and lot_area_sqft is not None
            and lot_area_sqft < self.density_from_sqft
        ):
            return None
        return units / float(self.min_density_du_per_acre) * 43_560.0


class _J:
    def __init__(self, eligible, zones):
        self.eligible, self.zones = eligible, zones

    def rule_for(self, zone):
        return next((z for z in self.zones if z.zone == zone), None)


class _Rules:
    """Minimal stand-in: gresham/UNVERIFIED is the only needs_verification zone.

    FLOORED states a minimum density of 8.71 units per acre, so four homes need
    20,005 sq ft and anything larger is short of the floor.

    BANDED states the same floor and confines it to sites of 24,000 sq ft and
    up, the shape Gresham writes MDR-24 in. Below the band there is no floor at
    all, which is a different thing from a floor a lot happens to clear -- and
    the gap between 20,005 and 24,000 is where the two answers differ.
    """
    def __init__(self):
        self.jurisdictions = {
            "gresham": _J(True, [_Z("LDR-5", "verified"),
                                 _Z("UNVERIFIED", "needs_verification"),
                                 _Z("FLOORED", "verified", 8.71),
                                 _Z("BANDED", "verified", 8.71,
                                    density_from_sqft=24_000)]),
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


class _Slope:
    def __init__(self, may_green):
        self.fallback_10m_may_green = may_green


class _Ocfg:
    """Only the slope knob `attribute_and_triage` reads off the config."""
    def __init__(self, may_green=False):
        self.slope = _Slope(may_green)


def _run(rows, has_siteplan=False, min_stalls=4, ocfg=None):
    lots = pd.DataFrame(rows)
    attribute_and_triage(lots, FP, _Rules(), has_siteplan, ["ovl_flag"],
                         min_stalls, ocfg)
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



def test_a_coarse_dem_answer_is_reported_but_may_not_green() -> None:
    """The eastern metro has no 1 m lidar, and a 10 m answer is a softer claim.

    USGS 3DEP's two metro lidar projects stop at about longitude -122.48. East
    of it there is no 1 m product at any vintage, which left Gresham,
    Troutdale, Fairview and Wood Village with NO elevation at all -- tiered as
    "unknown", which is a review trigger, which is why four whole cities had
    never produced one green lot. The 1/3 arc-second DEM covers all of it.

    But a number off a coarser instrument is not the same claim: calibrated
    against the 1 m answer on the 184,101 lots where both exist, the rule used
    (max slope over a 50 m box <= 10%) wrongly clears 1.50% of genuinely steep
    lots. So the default is that a coarse answer is printed and the lot still
    goes to a human. Flipping `fallback_10m_may_green` is the business call.
    """
    rows = [
        _base_row(slope_source="dem_1m"),      # fine instrument -> green
        _base_row(slope_source="dem_10m"),     # coarse -> review, not green
        _base_row(slope_source="none"),        # no DEM at all
    ]
    rows[2]["slope_tier"] = "unknown"

    held = _run(rows, ocfg=_Ocfg(may_green=False))
    assert list(held["triage"]) == ["green", "review", "review"]
    # It is held by the SOURCE, not by a failed test.
    assert (held["binding_constraint"] == "").all()

    allowed = _run(rows, ocfg=_Ocfg(may_green=True))
    assert list(allowed["triage"]) == ["green", "green", "review"]
    # A lot with no DEM at all is still review either way -- the switch buys
    # nothing where there is no number to trust.


def test_the_coarse_gate_is_off_when_the_column_is_absent() -> None:
    """A frame from before the fallback shipped must triage exactly as before.

    s5o only writes `slope_source` when it reaches the slope block at all
    (`--skip-slope` does not), so s7 has to tolerate its absence rather than
    assume every parquet on disk carries it.
    """
    rows = [_base_row(), _base_row(slope_tier="unknown")]
    lots = _run(rows, ocfg=_Ocfg(may_green=False))
    assert list(lots["triage"]) == ["green", "review"]
    assert "slope_source" not in lots.columns


# ---------------------------------------------------------------------------
# A frontage number that is really a mid-lot width
# ---------------------------------------------------------------------------


def test_an_unmeasurable_frontage_holds_a_lot_at_review():
    """Oregon City and Tualatin state a lot WIDTH and measure it across the
    middle of the lot; s4 measures the boundary that touches a street. Those
    are different lines, so falling short of the number is not a verdict the
    screen has earned -- it is a question for a person.

    The lot must not be red (nothing about it failed), must not be green (the
    code's standard is genuinely unchecked), and must carry no binding
    constraint, because there is no constraint it is known to violate.
    """
    lots = _run([
        _base_row(frontage_unmeasured=True),
        _base_row(frontage_unmeasured=False),
    ])
    assert list(lots["triage"]) == ["review", "green"]
    assert list(lots["binding_constraint"]) == ["", ""]


def test_an_unmeasurable_frontage_cannot_rescue_a_lot_that_fails_on_its_own():
    """Review is a hold, not a pardon. A lot the pod does not fit is red
    whether or not its frontage was measurable, or the flag would be a way to
    launder a failure into the queue."""
    lots = _run([
        _base_row(frontage_unmeasured=True, fits_pod=False, fits_cov_pod=False),
        _base_row(frontage_unmeasured=True, tier="D"),
    ])
    assert list(lots["triage"]) == ["red", "red"]
    assert list(lots["binding_constraint"]) == ["pod_no_fit", "no_buildable_envelope"]


def _gate_frame(rows):
    import pandas as pd

    from s7_report import policy_gates

    return policy_gates(pd.DataFrame(rows), _GateRules())[0]


class _GateRules:
    """The two shapes side by side, built from the real config models so the
    test breaks if `frontage_is_lot_width` stops being wired through."""

    def __init__(self):
        from common import JurisdictionRules, ZoneRule

        zone = ZoneRule(
            zone="R-10", quadplex_allowed=True, setback_front_ft=20,
            setback_side_ft=8, setback_rear_ft=20, min_frontage_ft=65,
        )
        self.jurisdictions = {
            "oregon_city": JurisdictionRules(
                eligible=True, frontage_is_lot_width=True, zones=[zone]),
            "west_linn": JurisdictionRules(
                eligible=True, frontage_is_lot_width=False, zones=[zone]),
        }


def _gate_row(juris, frontage):
    return {"jurisdiction": juris, "zone_raw": "R-10", "area_sqft": 9000.0,
            "frontage_ft": frontage}


def test_a_width_standard_does_not_drop_a_lot_in_the_funnel():
    """The same 40 ft lot under the same 65 ft number, in two cities.

    West Linn's tables head the row "Minimum lot width AT FRONT LOT LINE", so
    its number IS the street edge and the lot is properly excluded. Oregon
    City's is measured across the middle of the lot, so the lot survives the
    funnel carrying a flag instead.
    """
    gates = _gate_frame([
        _gate_row("oregon_city", 40.0),
        _gate_row("west_linn", 40.0),
        _gate_row("oregon_city", 80.0),
    ])
    assert list(gates["eligible"]) == [True, False, True]
    assert list(gates["policy_exclusion"]) == ["", "below_min_frontage", ""]
    assert list(gates["frontage_unmeasured"]) == [True, False, False]


def test_a_lot_can_be_too_big_for_four_homes():
    """The one standard in the corpus where MORE land is the problem.

    Forty zones state a minimum density -- homes per acre a residential site
    has to reach -- and four of them clear it on an ordinary lot and stop
    clearing it on a large one. It is not preempted: OAR 660-046-0220(2)(b)
    strikes out density MAXIMUMS for a quadplex and says nothing about a floor.

    REVIEW and not RED, which is the whole reason the check is safe to run.
    Every city that states a floor divides by NET developable area, and nothing
    here surveys that. Net is smaller than gross, so density measured on net is
    HIGHER: clearing the floor on gross area settles the question, and failing
    on gross area only opens it.
    """
    rows = [
        _base_row(zone="FLOORED", area_sqft=20_000.0),   # under the cap: fine
        _base_row(zone="FLOORED", area_sqft=25_000.0),   # over it: a question
        _base_row(zone="LDR-5", area_sqft=25_000.0),     # no floor stated
    ]
    lots = _run(rows)
    assert list(lots["triage"]) == ["green", "review", "green"]
    assert list(lots["density_floor_short"]) == [False, True, False]
    # And it is never a red: the lot passes every hard test it is given.
    assert list(lots["binding_constraint"]) == ["", "", ""]


def test_a_floor_that_does_not_reach_a_small_lot_is_no_floor():
    """A city can confine its own minimum density to lots above a size.

    Gresham prints 12.1 units per acre for MDR-24 and then says in the note
    that it applies to a site of 11,000 sq ft and up. Carried as one number it
    asked every smaller lot to meet a floor its own code does not reach.

    The first two lots are the same 22,000 sq ft, big enough that four homes
    miss an 8.71 du/acre floor. FLOORED states that floor for every lot and the
    lot is a question; BANDED states it only from 24,000 sq ft up, so the same
    lot is not being asked. The third lot is inside BANDED's band and short.
    """
    rows = [
        _base_row(zone="FLOORED", area_sqft=22_000.0),  # floor reaches it
        _base_row(zone="BANDED", area_sqft=22_000.0),   # below the band: unfloored
        _base_row(zone="BANDED", area_sqft=25_000.0),   # inside it, and short
    ]
    lots = _run(rows)
    assert list(lots["density_floor_short"]) == [True, False, True]
    assert list(lots["triage"]) == ["review", "green", "review"]


def test_the_density_floor_cannot_rescue_a_lot_that_fails_on_its_own():
    """A review trigger is a hold, never a pardon -- same as every other one."""
    lots = _run([_base_row(zone="FLOORED", area_sqft=25_000.0, fits_pod=False,
                           fits_cov_pod=False)])
    assert lots["triage"][0] == "red"
    assert lots["density_floor_short"][0]


def test_a_yellow_lot_says_why_it_is_yellow():
    """`binding_constraint` names a red lot's blocker; nothing named a yellow's.

    Eight conditions can hold a lot at review and not one of them was written
    into the row, so working the queue meant re-deriving the whole disjunction
    from the exported columns -- which two of them cannot support: the
    unverified-zone test needs rules.yaml, and the slope test needs a config
    flag that never reaches the CSV. Re-deriving a rule is how you get a
    different answer from the one the screen actually gave.
    """
    rows = [
        _base_row(),                                       # green: no reasons
        _base_row(zone="UNVERIFIED"),
        _base_row(slope_tier="cost_prohibitive"),
        _base_row(ovl_flag=True),
        _base_row(sewer_main_dist_ft=9_999.0),
        _base_row(zone="FLOORED", area_sqft=25_000.0),
    ]
    lots = _run(rows, ocfg=_Ocfg())
    assert list(lots["review_reasons"]) == [
        "", "unverified_zone", "slope", "overlay", "sewer_unconfirmed",
        "density_floor",
    ]
    assert list(lots["triage"]) == [
        "green", "review", "review", "review", "review", "review"]


def test_every_reason_a_lot_is_held_gets_named_not_just_the_first():
    """One lot, three problems. A queue sorted on the first one lies about the
    other two, and a lot whose only cure is item 6 must not read like a lot
    whose only cure is item 7."""
    lots = _run([_base_row(zone="UNVERIFIED", slope_tier="cost_prohibitive",
                           sewer_main_dist_ft=9_999.0, ovl_flag=True)],
                ocfg=_Ocfg())
    assert lots["review_reasons"][0] == (
        "unverified_zone,slope,sewer_unconfirmed,overlay")


def test_a_red_lot_carries_no_review_reasons():
    """Red is answered by `binding_constraint`. Naming yellow causes on a lot
    that is already off the board would make the queue look bigger than it is."""
    lots = _run([_base_row(zone="UNVERIFIED", fits_pod=False,
                           fits_cov_pod=False, slope_tier="cost_prohibitive")],
                ocfg=_Ocfg())
    assert lots["triage"][0] == "red"
    assert lots["binding_constraint"][0] == "pod_no_fit"
    assert lots["review_reasons"][0] == ""
