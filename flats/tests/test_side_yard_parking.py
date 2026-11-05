"""Side-yard parking is optional, with the original setback behavior by default."""

from __future__ import annotations

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
)
from flats.score.screen import LotFacts, fit_for, screen
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


def test_field_is_optional_and_accepts_only_the_three_modes() -> None:
    assert FIELD in OPTIONAL_FIELDS
    assert field(FIELD).kind == "enum"
    assert field(FIELD).choices == ("none", "lane", "lane_and_court")


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
