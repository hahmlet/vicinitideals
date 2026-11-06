"""Side-yard parking is optional, with the original setback behavior by default."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from shapely.geometry import box

from flats.designs.model import load_catalog
from flats.fit.draw import draw
from flats.fit.rectangle import Fitter
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.rules.model import Provenance, Status
from flats.rules.resolver import Resolved, RuleSet
from flats.rules.resolver import Verdict as RuleVerdict
from flats.rules.resolver import ZoneResolution
from flats.score.paper import (
    paper_fit,
    side_yard_court_overlap_ft,
    side_yard_lane_overlap_ft,
    side_yard_mode,
    side_yard_stated_mode,
)
from flats.score.screen import (
    SIDE_YARD_PARKING_SILENT,
    LotFacts,
    Triage,
    fit_for,
    screen,
)
from flats.score.slack import SlackPolicy

pytestmark = pytest.mark.unit

FIELD = "parking_side_yard_allowed"
WHERE = "or/test/side-yard"
DESIGN = load_catalog().latest("pod56x36")
PROV = Provenance(
    cite="Test zoning code",
    url="https://example.invalid/code",
    retrieved=date(2026, 11, 1),
)


def rules(**overrides: object) -> ZoneResolution:
    values = {
        "quadplex_allowed": True,
        "min_lot_sqft": 3000,
        "min_lot_width_ft": 1,
        "setback_front_ft": 10,
        "setback_rear_ft": 10,
        "setback_side_ft": 5,
        **overrides,
    }
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="R5",
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


def screen_rules(**overrides: object) -> ZoneResolution:
    values = {
        "min_frontage_ft": 1,
        "max_coverage_pct": 100,
        "max_far": 10,
        "max_height_ft": 100,
        "max_units": 4,
        "parking_min_per_unit": 1,
        **overrides,
    }
    return rules(**values)


def test_field_is_optional_and_accepts_only_the_three_modes() -> None:
    assert FIELD in OPTIONAL_FIELDS
    assert field(FIELD).kind == "enum"
    assert field(FIELD).choices == ("none", "lane", "lane_and_court")


def test_missing_stated_reach_means_silence() -> None:
    got = rules(**{FIELD: "lane"})
    assert got.get("parking_side_yard_stated") is None
    assert side_yard_stated_mode(got) == "none"


def test_unset_matches_today_for_fit_width_and_colour() -> None:
    before = rules()
    unset = paper_fit(DESIGN, before)
    explicit_none = paper_fit(DESIGN, rules(**{FIELD: "none"}))
    assert unset.min_width_ft == explicit_none.min_width_ft
    assert unset.min_area_sqft == explicit_none.min_area_sqft

    fitter = Fitter(box(0, 0, 100, 160))
    fit = fit_for(fitter, DESIGN, before)
    fit_none = fit_for(fitter, DESIGN, rules(**{FIELD: "none"}))
    assert fit.across_ft == fit_none.across_ft
    assert fit.slack_ft == fit_none.slack_ft
    lot = LotFacts(lot_sqft=16_000)
    policy = SlackPolicy(tolerance={"fit_ft": 0.5})
    assert screen(before, lot, DESIGN, fit, policy=policy).colour == screen(
        rules(**{FIELD: "none"}), lot, DESIGN, fit_none, policy=policy
    ).colour


@pytest.mark.parametrize(("buffer_ft", "expected_drop"), [(None, 5), (3, 2)])
def test_lane_permission_reduces_width_only_by_the_unbuffered_side_yard(
    buffer_ft: float | None, expected_drop: float
) -> None:
    common = {} if buffer_ft is None else {"parking_lot_line_buffer_ft": buffer_ft}
    old = paper_fit(DESIGN, rules(**common))
    allowed = paper_fit(DESIGN, rules(**common, **{FIELD: "lane"}))
    assert allowed.min_width_ft == pytest.approx(old.min_width_ft - expected_drop)
    assert side_yard_lane_overlap_ft(rules(**common, **{FIELD: "lane"}), 12) == expected_drop


def test_combined_side_setback_supplies_the_one_side_overlap() -> None:
    combined = rules(
        setback_side_ft=None,
        setback_side_total_ft=10,
        **{FIELD: "lane"},
    )
    assert side_yard_lane_overlap_ft(combined, 12) == 5


def test_lane_and_court_can_use_the_same_side_setback() -> None:
    court_wider_than_lane = {
        "parking_min_per_unit": 1.5,
        "parking_stall_width_ft": 12,
    }
    old = paper_fit(DESIGN, rules(**court_wider_than_lane))
    lane_only = paper_fit(DESIGN, rules(**court_wider_than_lane, **{FIELD: "lane"}))
    lane_and_court = paper_fit(
        DESIGN, rules(**court_wider_than_lane, **{FIELD: "lane_and_court"})
    )
    fitter = Fitter(box(5, 5, 72, 55))
    without_side_yard = fit_for(fitter, DESIGN, rules(**court_wider_than_lane))
    with_side_yard = fit_for(
        fitter,
        DESIGN,
        rules(**court_wider_than_lane, **{FIELD: "lane_and_court"}),
    )
    assert lane_only.min_width_ft == old.min_width_ft
    assert lane_and_court.min_width_ft == pytest.approx(old.min_width_ft - 5)
    assert not without_side_yard.fits
    assert with_side_yard.fits
    assert with_side_yard.across_ft == pytest.approx(67)


def test_fit_relying_on_silent_side_yard_is_yellow_with_ruling_flag() -> None:
    silent = screen_rules(
        parking_min_per_unit=1.5,
        parking_stall_width_ft=12,
        setback_rear_ft=40,
        **{FIELD: "lane_and_court"},
    )
    fitter = Fitter(box(5, 5, 72, 55))
    fit = fit_for(fitter, DESIGN, silent, carved_rear_ft=40)
    assert fit.fits and fit.side_yard_stated_fit is not None
    assert not fit.side_yard_stated_fit.fits

    got = screen(
        silent,
        LotFacts(
            lot_sqft=6_700,
            frontage_ft=67,
            lot_width_ft=67,
            lot_depth_ft=100,
            envelope_rear_ft=40,
        ),
        DESIGN,
        fit,
        policy=SlackPolicy(tolerance={"fit_ft": 0.5}),
    )
    assert got.colour.value == "yellow"
    assert SIDE_YARD_PARKING_SILENT in got.reasons
    assert "2026-11-05-side-yard-parking-silent-codes" in SIDE_YARD_PARKING_SILENT
    assert any(flag.code == "SIDE-YARD-PARKING-SILENT" for flag in got.flags)


def test_a_failed_fit_on_steep_ground_does_not_crash_the_side_yard_check() -> None:
    # The fit's check is named steep_ground there, so looking for fit_ft alone
    # stopped the whole bridge on the first such lot (size_full, 2026-11-06).
    miss = Fitter(box(0, 0, 20, 20)).fit(56, 36)
    assert not miss.fits
    got = screen(
        screen_rules(**{FIELD: "lane_and_court"}),
        LotFacts(lot_sqft=400, frontage_ft=20, lot_width_ft=20, steep_blocks=True),
        DESIGN,
        replace(miss, side_yard_stated_fit=miss),
        policy=SlackPolicy(),
    )
    assert got.triage is not Triage.green
    assert "steep_ground" in {c.check for c in got.checks}


def test_stated_reach_fit_remains_green_eligible() -> None:
    stated = screen_rules(
        **{FIELD: "lane_and_court", "parking_side_yard_stated": "lane_and_court"}
    )
    fitter = Fitter(box(5, 5, 100, 170))
    fit = fit_for(fitter, DESIGN, stated)
    assert fit.fits
    assert fit.side_yard_stated_fit is None

    got = screen(
        stated,
        LotFacts(lot_sqft=16_000, frontage_ft=95, lot_width_ft=95),
        DESIGN,
        fit,
        policy=SlackPolicy(tolerance={"fit_ft": 0.5}),
    )
    assert got.triage is Triage.green
    assert got.colour.value == "green"
    assert not any(flag.code == "SIDE-YARD-PARKING-SILENT" for flag in got.flags)


def test_corner_lot_never_uses_side_yard_reach() -> None:
    allowed = rules(**{FIELD: "lane_and_court"})
    assert side_yard_mode(allowed) == "lane_and_court"
    assert side_yard_lane_overlap_ft(allowed, 12, corner=True) == 0
    assert side_yard_court_overlap_ft(allowed, 24, lane_ft=12, corner=True) == 0

    fitter = Fitter(box(5, 5, 72, 55))
    corner_fit = fit_for(fitter, DESIGN, allowed, corner=True)
    no_side_fit = fit_for(fitter, DESIGN, rules(), corner=True)
    assert corner_fit.across_ft == no_side_fit.across_ft
    assert corner_fit.slack_ft == no_side_fit.slack_ft
    assert corner_fit.side_yard_stated_fit is None


def test_city_side_yard_values_resolve_from_yaml() -> None:
    ruleset = RuleSet(load_rules())
    portland = ruleset.resolve("or/multnomah/portland", "R2.5")
    assert portland.get(FIELD) == "lane_and_court"
    assert portland.get("parking_side_yard_stated") == "lane_and_court"

    canby = ruleset.resolve("or/clackamas/canby", "R-1")
    assert canby.get(FIELD) == "lane_and_court"
    assert canby.get("parking_side_yard_stated") == "lane"

    gresham = ruleset.resolve("or/multnomah/gresham", "LDR-5")
    assert gresham.get(FIELD) == "lane"
    assert gresham.get("parking_side_yard_stated") == "none"

    county_qp = ruleset.resolve("or/multnomah/_unincorporated", "R10")
    assert county_qp.get(FIELD) == "lane_and_court"
    assert county_qp.get("parking_side_yard_stated") == "lane_and_court"
    assert county_qp.get("parking_lot_line_buffer_ft") == 5

    west_linn = ruleset.resolve("or/clackamas/west-linn", "R-10")
    assert west_linn.get(FIELD) is None
    assert west_linn.get("parking_side_yard_stated") is None



@pytest.mark.parametrize(
    "prohibition",
    ("parking_side_prohibited", "parking_required_yard_prohibited"),
)
def test_loader_prohibitions_override_lane_and_court(
    tmp_path: Path, prohibition: str
) -> None:
    source = tmp_path / "or" / "test" / "city.yaml"
    source.parent.mkdir(parents=True)
    source.write_text(
        "label: Test City\n"
        "cite_default:\n"
        "  cite: Test City zoning code\n"
        "  url: https://example.invalid/code\n"
        "  retrieved: 2026-11-01\n"
        '  quote: "code.txt#L1"\n'
        "zones:\n"
        "  R5:\n"
        "    setback_side_ft: 5\n"
        f"    {FIELD}: lane_and_court\n"
        f"    {prohibition}: true\n",
        encoding="utf-8",
    )
    loaded = RuleSet(load_rules(tmp_path)).resolve("or/test/city", "R5")
    current = paper_fit(DESIGN, rules(**{prohibition: True}))
    prohibited = paper_fit(
        DESIGN, rules(**{FIELD: "lane_and_court", prohibition: True})
    )
    assert loaded.get(FIELD) == "lane_and_court"
    assert loaded.get(prohibition) is True
    assert prohibited.min_width_ft == current.min_width_ft
    assert side_yard_lane_overlap_ft(loaded, 12) == 0
    assert side_yard_court_overlap_ft(loaded, 24, lane_ft=12) == 0


def test_lane_overlap_keeps_both_building_side_setbacks_and_draws_the_lane_in_yard() -> None:
    got = rules(**{FIELD: "lane"})
    lane_overlap = side_yard_lane_overlap_ft(got, 12)
    envelope = box(5, 5, 68, 180)
    fitter = Fitter(envelope)
    fit = fitter.fit_design(DESIGN, lane_ft=12 - lane_overlap)
    drawing = draw(
        fitter,
        fit,
        width_ft=DESIGN.footprint.width_ft,
        depth_ft=DESIGN.footprint.depth_ft,
        lane_ft=12,
        lane_overlap_ft=lane_overlap,
        court_depth_ft=0,
        court_beyond_ft=0,
    )
    assert drawing is not None and drawing.lane is not None and drawing.building is not None
    assert drawing.building.bounds[0] >= 5
    assert drawing.building.bounds[2] <= 68
    assert (
        drawing.lane.bounds[0] < drawing.room.bounds[0]
        or drawing.lane.bounds[2] > drawing.room.bounds[2]
    )
    assert drawing.to_json()["lane"] is not None


# Round 3 (2026-11-05): one real zone per tier, resolved from the YAML.
# (jurisdiction, zone, conditions, allowed, stated, buffer, mode, stated mode)
ROUND_3 = [
    # STATED: the code names the side yard or states the parking's own setback.
    ("or/clackamas/milwaukie", "R-MD", (), "lane_and_court", "lane_and_court", None,
     "lane_and_court", "lane_and_court"),
    ("or/multnomah/wood-village", "LR 7.5", (), "lane_and_court", "lane_and_court", 5,
     "lane_and_court", "lane_and_court"),
    ("or/multnomah/wood-village", "LR 7.5", ("unit_lots",), "lane_and_court",
     "lane_and_court", None, "lane_and_court", "lane_and_court"),
    ("or/washington/beaverton", "RMA", (), "lane_and_court", "lane_and_court", None,
     "lane_and_court", "lane_and_court"),
    ("or/clackamas/gladstone", "R5", (), "lane_and_court", "lane_and_court", 5,
     "lane_and_court", "lane_and_court"),
    ("or/clackamas/tualatin", "RML", (), "lane_and_court", "lane_and_court", 5,
     "lane_and_court", "lane_and_court"),
    # PART STATED: the lane is stated, the court silent.
    ("or/clackamas/tualatin", "RL", (), "lane_and_court", "lane", 5,
     "lane_and_court", "lane"),
    # SILENT: allowed, nothing stated -- yellow at best.
    ("or/clackamas/happy-valley", "R15", (), "lane_and_court", "none", None,
     "lane_and_court", "none"),
    ("or/clackamas/oregon-city", "R-10", (), "lane_and_court", "none", 5,
     "lane_and_court", "none"),
    ("or/clackamas/wilsonville", "R", (), "lane_and_court", "none", None,
     "lane_and_court", "none"),
    ("or/clackamas/estacada", "C-2", (), "lane_and_court", "none", None,
     "lane_and_court", "none"),
    ("or/washington/tigard", "RES-A", (), "lane_and_court", "none", None,
     "lane_and_court", "none"),
    ("or/washington/durham", "SDR", (), "lane_and_court", "none", None,
     "lane_and_court", "none"),
    # SILENT LANE, the court kept out (forbidden or unsure).
    ("or/washington/durham", "SDR", ("unit_lots",), "lane", "none", None, "lane", "none"),
    ("or/multnomah/troutdale", "MU-1", (), "lane", "none", None, "lane", "none"),
    ("or/multnomah/fairview", "R-6", (), "lane", "none", None, "lane", "none"),
    # FORBIDDEN: the code's permission names other zones, or a ban wins.
    ("or/washington/beaverton", "MR", (), "none", None, None, "none", "none"),
    ("or/clackamas/oregon-city", "R-10", ("unit_lots",), "lane", "none", None, "none", "none"),
    ("or/clackamas/milwaukie", "R-MD", ("unit_lots",), "lane", "lane", None, "none", "none"),
]


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize(
    ("where", "zone", "held", "allowed", "stated", "buffer", "mode", "stated_mode"),
    ROUND_3,
    ids=[f"{w.rsplit('/', 1)[-1]}-{z}-{'TH' if h else 'QP'}" for w, z, h, *_ in ROUND_3],
)
def test_round_3_city_values_resolve_per_tier(
    corpus: RuleSet,
    where: str,
    zone: str,
    held: tuple[str, ...],
    allowed: str,
    stated: str | None,
    buffer: float | None,
    mode: str,
    stated_mode: str,
) -> None:
    got = corpus.resolve(where, zone, held)
    assert got.get(FIELD) == allowed
    assert got.get("parking_side_yard_stated") == stated
    assert got.get("parking_lot_line_buffer_ft") == buffer
    assert side_yard_mode(got) == mode
    assert side_yard_stated_mode(got) == stated_mode
