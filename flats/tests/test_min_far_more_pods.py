"""Minimum FAR is red only where the needed pod footprints clearly cannot fit."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402

from flats.geom import pdx_overlays as pdx  # noqa: E402
from flats.score.flags import Colour  # noqa: E402
from flats.score.screen import CLOSER_LOOK_MIN_FAR, LotFacts, Triage  # noqa: E402
from flats.tests.test_screen import DESIGN, NO_RELIEF, POLICY, run, rules  # noqa: E402

pytestmark = pytest.mark.unit

FLOOR_SQFT = DESIGN.ground_sqft * DESIGN.stories
FOOTPRINT_SQFT = DESIGN.footprint.width_ft * DESIGN.footprint.depth_ft


def _general(buildable_sqft: float | None, *, lot_sqft: float = 9_000):
    lot = LotFacts(
        lot_sqft=lot_sqft,
        frontage_ft=100,
        lot_width_ft=100,
        buildable_area_sqft=buildable_sqft,
    )
    return run(rules(min_far=0.5), lot=lot, relief=NO_RELIEF)


def test_min_far_is_red_when_two_pod_footprints_cannot_fit() -> None:
    result = _general(2 * FOOTPRINT_SQFT - 1)

    assert result.triage is Triage.red
    assert [bind.check for bind in result.binds] == ["min_far"]
    assert CLOSER_LOOK_MIN_FAR not in result.reasons
    assert "FAR-MIN" not in {flag.code for flag in result.flags}


def test_min_far_is_yellow_when_two_pods_could_fit() -> None:
    result = _general(5_000, lot_sqft=15_000)

    assert result.triage is Triage.yellow
    assert result.binds == ()
    assert CLOSER_LOOK_MIN_FAR in result.reasons
    assert "FAR-MIN" in {flag.code for flag in result.flags}


def test_min_far_is_yellow_when_buildable_area_is_unknown() -> None:
    result = _general(None)

    assert result.triage is Triage.yellow
    assert result.binds == ()
    assert CLOSER_LOOK_MIN_FAR in result.reasons
    assert "FAR-MIN" in {flag.code for flag in result.flags}


@dataclass(frozen=True)
class _Envelope:
    geom: object
    source: str = "flats"

    @property
    def sqft(self) -> float:
        return float(self.geom.area)


@dataclass(frozen=True)
class _Rules:
    jurisdiction: str = "or/multnomah/portland"
    zone: str = "CM2"

    def get(self, name: str):
        return None


@dataclass(frozen=True)
class _Screened:
    lot: object
    design: object
    rules: object
    config: object
    fit: object
    screening: object
    signed: object
    angles: int = 1
    step_deg: float = 30.0
    envelope: object = None
    drawing: object = None


def _portland(buildable: object, *, building: object = None, lot_sqft: float = 10_000):
    from flats.score.screen import Screening

    lot_geom = shapely.box(0, 0, 100, 100)
    lot = SimpleNamespace(
        zone="CM2",
        facts=SimpleNamespace(lot_sqft=lot_sqft),
        lot_geom=lot_geom,
        edges=None,
        jurisdiction="or/multnomah/portland",
    )
    if building is None:
        building = shapely.box(0, 0, DESIGN.footprint.width_ft, DESIGN.footprint.depth_ft)
    drawing = {"building": [list(point) for point in building.exterior.coords]}
    screening = Screening(triage=Triage.green)
    return _Screened(
        lot=lot,
        design=DESIGN,
        rules=_Rules(),
        config=None,
        fit=None,
        screening=screening,
        signed=screening,
        envelope=None if buildable is None else _Envelope(buildable),
        drawing=drawing,
    )


def test_portland_main_street_min_far_is_yellow_when_two_pods_could_fit() -> None:
    result = pdx.checked(
        _portland(shapely.box(0, 0, 100, 100)),
        pdx.Reading(True, ("Inner",)),
    )

    assert result.signed.triage is Triage.yellow
    assert result.signed.binds == ()
    assert CLOSER_LOOK_MIN_FAR in result.signed.reasons
    assert "FAR-MIN" in {flag.code for flag in result.signed.flags}


def test_portland_main_street_min_far_is_red_when_two_footprints_cannot_fit() -> None:
    result = pdx.checked(
        _portland(shapely.box(0, 0, FOOTPRINT_SQFT * 2 - 1, 1)),
        pdx.Reading(True, ("Inner",)),
    )

    assert result.signed.triage is Triage.red
    assert [bind.check for bind in result.signed.binds] == [pdx.MIN_FAR_CHECK]
    assert CLOSER_LOOK_MIN_FAR not in result.signed.reasons
    assert "FAR-MIN" not in {flag.code for flag in result.signed.flags}


def test_portland_more_pods_room_is_measured_only_inside_the_overlay_part() -> None:
    overlay_part = shapely.box(0, 0, 50, 100)
    envelope = shapely.union_all(
        [shapely.box(0, 0, 30, 100), shapely.box(50, 0, 120, 100)]
    )
    building = shapely.box(20, 0, 76, DESIGN.footprint.depth_ft)
    reading = pdx.Reading(
        True,
        ("Inner",),
        main_street_share=0.5,
        main_street_part_wkb=shapely.to_wkb(overlay_part, hex=True),
    )

    result = pdx.checked(
        _portland(envelope, building=building),
        reading,
    )

    assert envelope.area >= 2 * FOOTPRINT_SQFT
    assert envelope.intersection(overlay_part).area < 2 * FOOTPRINT_SQFT
    assert result.signed.triage is Triage.red
    assert [bind.check for bind in result.signed.binds] == [pdx.MIN_FAR_CHECK]


def test_a_pod_meeting_min_far_keeps_the_existing_green_result() -> None:
    lot = LotFacts(lot_sqft=8_000, frontage_ft=100, lot_width_ft=100)

    result = run(rules(min_far=0.5), lot=lot, relief=NO_RELIEF)

    assert result.triage is Triage.green
    assert CLOSER_LOOK_MIN_FAR not in result.reasons
    assert "FAR-MIN" not in {flag.code for flag in result.flags}
    assert all(bind.check != "min_far" for bind in result.binds)
