"""Clackamas ZDO 1005.02(E): half the development site's street frontage
must have buildings at the minimum front setback line (fg4-fixes,
false-green round 4: 19108 SE River Rd, C3, noted 2026-09-09 and held only
as an axis rule until now).

The share reaches every district where Table 1001-1 ticks Section 1005 for
middle housing -- PMD, MR-1, MR-2, VA, HDR and the zones that take HDR's
standards -- and not the R and VR districts, whose middle-housing rows
leave 1005 blank.
"""

from __future__ import annotations

import json

import pytest
import shapely
from shapely.geometry import box

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import BUILDING_SHARE
from flats.score.slack import Verdict
from flats.tests.test_frontage_caps import quoted
from flats.tests.test_round2_rulings import DESIGN, check

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
FIFTEEN = ("PMD", "MR1", "MR2", "HDR", "SHD", "RCHDR", "RTL", "CC", "C3", "OC", "RCC", "RCO")


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize(("zone", "band"), [(z, 15) for z in FIFTEEN] + [("VA", 10)])
def test_half_the_frontage_at_the_minimum_setback(corpus: RuleSet, zone: str, band: int) -> None:
    got = corpus.resolve(CLACKAMAS, zone).values
    assert got["building_frontage_min_pct"].value == 50
    assert got["building_frontage_band_ft"].value == band
    assert got["setback_front_ft"].value == band  # the band IS the minimum setback
    assert got["building_frontage_basis"].value == "site"
    # (E)(3)'s one-frontage rule is not held: every street for GREEN.
    assert "building_frontage_corner" not in got
    assert "building_frontage_through_one" not in got
    text = quoted(got["building_frontage_min_pct"].prov.quote)
    assert "50 percent" in text and "minimum front setback line" in text


@pytest.mark.parametrize("zone", ("R5", "R7", "R10", "R15", "R20", "R30", "VR45", "VR57"))
def test_the_r_and_vr_districts_owe_no_share(corpus: RuleSet, zone: str) -> None:
    assert "building_frontage_min_pct" not in corpus.resolve(CLACKAMAS, zone).values


def _c3_lot(corpus: RuleSet, width: float, depth: float = 200.0):
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.tests.test_fire import X0, Y0, bridge_row

    edges = [
        [X0, Y0, X0 + width, Y0, "F"],
        [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
        [X0 + width, Y0 + depth, X0, Y0 + depth, "R"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    row = bridge_row(
        jurisdiction="clackamas_unincorporated",
        zone="C3",
        TLID="22E00AA99999",
        edges_json=json.dumps(edges),
        frontage_ft=width,
        lot_width_ft=width,
        lot_depth_ft=depth,
        area_sqft=width * depth,
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + width - 5, Y0 + depth - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + width, Y0 + depth)),
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(
        lot, [DESIGN], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy(), step_deg=30.0
    )
    return s


def test_19108_se_river_rd_shape_is_not_green(corpus: RuleSet) -> None:
    # 125.8 ft of River Rd frontage: one pod covers well under the 62.9 ft
    # half, so the lot cannot be GREEN on one building.
    got = _c3_lot(corpus, 125.8)
    assert got.screening.colour is not Colour.green
    share = check(got.screening, BUILDING_SHARE)
    assert share is None or share.verdict is not Verdict.passes


def test_a_narrow_c3_lot_is_measured_at_the_setback_line(corpus: RuleSet) -> None:
    # 80 ft: the pod drawn at the 15 ft line fills more than half of it.
    got = _c3_lot(corpus, 80.0)
    drawn = got.facts.building_frontage_pct
    assert drawn is not None, "the share must be measured, not left unread"
    assert drawn[0] >= 50.0
    assert check(got.screening, BUILDING_SHARE).verdict is Verdict.passes
