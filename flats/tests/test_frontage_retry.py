"""A frontage-cap miss is RED only where no placement passes (FOLLOWUPS 189 F4).

22E06AD01800, 13460 SE Rusk Rd (Clackamas R10): a corner lot whose best fit
stood the building across the corner with its court beside it, facing SE
Rusk Rd's short north line -- 51.22 percent of it against ZDO 845.02's half
(rel7 yellow -> red). Turned square to the north street, the court stands
behind the building from it and faces the long west street across its depth
only. The bridge tries the building squared to each street before it
answers RED. Real coordinates (s4/s5o, 2026-11-10 snapshot).
"""

from __future__ import annotations

import json

import pytest
import shapely

from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.slack import Verdict
from flats.designs.model import load_catalog
from flats.tests.test_round2_rulings import check

pytestmark = pytest.mark.unit

EDGES = [
    [7662425.92, 648477.02, 7662424.52, 648335.21, "R"],
    [7662424.52, 648335.21, 7662273.74, 648338.49, "R"],
    [7662273.74, 648338.49, 7662316.36, 648437.64, "F"],
    [7662316.36, 648437.64, 7662331.98, 648457.9, "F"],
    [7662331.98, 648457.9, 7662347.68, 648469.01, "F"],
    [7662347.68, 648469.01, 7662365.66, 648475.8, "F"],
    [7662365.66, 648475.8, 7662384.78, 648477.84, "F"],
    [7662384.78, 648477.84, 7662425.92, 648477.02, "F"],
]
LOT = (
    "POLYGON ((7662425.915 648477.025, 7662424.516 648335.209, 7662273.740 648338.493, "
    "7662313.599 648431.835, 7662316.361 648437.636, 7662319.606 648443.182, 7662323.310 648448.432, "
    "7662327.446 648453.348, 7662331.985 648457.895, 7662336.894 648462.040, 7662342.137 648465.754, "
    "7662347.676 648469.008, 7662353.472 648471.781, 7662359.483 648474.051, 7662365.664 648475.802, "
    "7662371.972 648477.023, 7662378.361 648477.703, 7662384.785 648477.838, 7662425.915 648477.025))"
)
ENVELOPE = (
    "POLYGON ((7662342.484 648446.957, 7662354.777 648455.656, 7662369.162 648461.088, "
    "7662385.429 648462.824, 7662405.775 648462.419, 7662404.721 648355.645, 7662298.435 648357.958, "
    "7662329.394 648429.979, 7662342.484 648446.957))"
)


DESIGN = load_catalog().latest("pod80x30")


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def _screen(corpus: RuleSet):
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.tests.test_fire import bridge_row

    row = bridge_row(
        TLID="22E06AD01800",
        jurisdiction="clackamas_unincorporated",
        zone="R10",
        tier="B",
        edges_json=json.dumps(EDGES),
        front_bearings_json="[63.98, 1.16]",
        frontage_ft=232.3,
        lot_width_ft=None,
        lot_depth_ft=None,
        area_sqft=16753.8,
        wkb=shapely.to_wkb(shapely.from_wkt(ENVELOPE)),
        lot_wkb=shapely.to_wkb(shapely.from_wkt(LOT)),
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(lot, [DESIGN], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy())
    return s


def test_rusk_rd_is_not_red_on_the_share_another_placement_passes(corpus: RuleSet) -> None:
    s = _screen(corpus)
    share = check(s.screening, "parking_frontage_share")
    assert share is not None
    assert share.threshold == 50.0
    assert share.verdict is Verdict.passes
    assert s.screening.colour is not Colour.red


def test_without_the_retry_the_first_placement_misses_the_cap(corpus: RuleSet, monkeypatch) -> None:
    # The placement the free search takes is the rel7 red: the retry, not a
    # change in the measure, is what reads the lot.
    from flats.ingest import quadfit

    monkeypatch.setattr(quadfit, "_frontage_missed", lambda signed: False)
    s = _screen(corpus)
    share = check(s.screening, "parking_frontage_share")
    assert share is not None and share.verdict is Verdict.fails
    assert share.observed == pytest.approx(51.22, abs=0.01)
