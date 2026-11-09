"""A building made to face the street may stand parallel to either part of a
bent front lot line (rel4 move-read finding 4, Tigard 2S103BA00137).

s4 clusters a front that bends 4.5 degrees into one bearing, 174.11, between
its two parts (171.09 and 175.57). Tigard RES-B makes the building face the
street (18.280.040.H, ``orientation_constraint: axis_required``), so that one
bearing was the only angle searched: the building stood parallel to neither
part, its near corner over the bend 21.08 ft from the front line against the
zone's 20 ft maximum (Table 18.280.1), and the lot read RED.
"""

from __future__ import annotations

import json

import pytest
import shapely
from shapely.geometry import Polygon

from flats.designs.model import load_catalog
from flats.ingest import quadfit
from flats.ingest.quadfit import front_parts, lot_from_row, screen_lot
from flats.score import relief, slack
from flats.tests.test_fire import X0, Y0, bridge_row

POD = load_catalog().latest("pod80x30")

# 2S103BA00137's lot lines (s4 edges_json), moved to the test origin.
EDGES = [
    [125.1, 129.7, 115.7, 0.0, "S"],
    [115.7, 0.0, 0.0, 8.4, "R"],
    [0.0, 8.4, 9.6, 141.6, "S"],
    [9.6, 141.6, 47.0, 135.7, "F"],
    [47.0, 135.7, 125.1, 129.7, "F"],
]


@pytest.fixture(scope="module")
def corpus():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _lot(corpus):
    edges = [[X0 + a, Y0 + b, X0 + c, Y0 + d, k] for a, b, c, d, k in EDGES]
    ring = Polygon([(e[0], e[1]) for e in edges])
    row = bridge_row(
        TLID="2S103BA99137",
        jurisdiction="tigard",
        zone="RES-B",
        area_sqft=ring.area,
        frontage_ft=116.1,
        lot_width_ft=None,
        lot_depth_ft=None,
        edges_json=json.dumps(edges),
        front_bearings_json="[174.11]",
        wkb=shapely.to_wkb(ring),
        lot_wkb=shapely.to_wkb(ring),
    )
    return lot_from_row(row, corpus.layers)


def test_front_parts_are_the_bent_fronts_own_directions(corpus) -> None:
    lot = _lot(corpus)
    got = sorted(front_parts(lot))
    assert got == [pytest.approx(171.04, abs=0.05), pytest.approx(175.61, abs=0.05)]


def test_a_building_facing_the_street_is_searched_along_each_part(
    corpus, policies, monkeypatch
) -> None:
    lot = _lot(corpus)
    (s,) = screen_lot(lot, [POD], rules=corpus, policy=policies[0], relief=policies[1])
    # The cluster and both parts (on 137 the real lot then stands the
    # building along the 78 ft part, within the 20 ft maximum).
    assert s.angles == 3
    if s.fit.fits:
        assert min(abs(s.fit.angle_deg - b) for b in (174.11, *front_parts(lot))) < 0.05
    # As before: the cluster alone.
    monkeypatch.setattr(quadfit, "front_parts", lambda lot: ())
    (before,) = screen_lot(lot, [POD], rules=corpus, policy=policies[0], relief=policies[1])
    assert before.angles == 1
