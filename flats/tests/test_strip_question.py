"""The planted strip as a question, not a miss (Steph 2026-10-04).

Four codes keep a planted strip between parking and the lot lines
(``parking_lot_line_buffer_ft``: Gladstone, Tualatin, Multnomah
unincorporated, Hillsboro). Whether a townhome project owes it is open --
OAR 660-046-0220(2)(e)(E) may hold middle housing to the single-family
parking standards, which ask none. Steph: "Let's have strips be a flag for
yellow at this time". A plan that misses with the strip and fits without it
is screened a second time without it and carries PARKING-STRIP-UNCONFIRMED;
a plan that misses either way keeps its misses; a plan that fits with the
strip is untouched.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import box  # noqa: E402

from flats.designs.model import load_catalog  # noqa: E402
from flats.encode.load import load_trusted  # noqa: E402
from flats.ingest.quadfit import _Waived, lot_from_row, screen_lot  # noqa: E402
from flats.score import flags as fp  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.screen import PARKING_STRIP_UNCONFIRMED, STRIP_FIELD  # noqa: E402

pytestmark = pytest.mark.unit

X0, Y0 = 7_650_000.0, 680_000.0
CODE = "PARKING-STRIP-UNCONFIRMED"


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def pod():
    return load_catalog().latest("pod56x36")


def row(width: float, depth: float, juris: str = "gladstone", zone: str = "R7.2") -> dict:
    """A plain rectangle: street along the bottom, sides, rear at the top."""
    w, d = width, depth
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "S"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]
    return {
        "TLID": "TEST",
        "jurisdiction": juris,
        "zone": zone,
        "tier": "A",
        "area_sqft": w * d,
        "frontage_ft": w,
        "lot_width_ft": w,
        "lot_depth_ft": d,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + w - 5, Y0 + d - 10)),
        "lot_wkb": shapely.to_wkb(box(X0, Y0, X0 + w, Y0 + d)),
    }


def screened(corpus, pod, width: float, depth: float, **where):
    lot = lot_from_row(row(width, depth, **where), corpus.layers)
    (s,) = screen_lot(
        lot,
        [pod],
        rules=corpus,
        policy=slack.load_policy(),
        relief=relief.load_policy(),
        step_deg=30.0,
    )
    return s


def layer(corpus, juris: str = "gladstone", zone: str = "R7.2") -> str:
    return lot_from_row(row(70, 125, juris=juris, zone=zone), corpus.layers).layer_id


def test_gladstone_carries_the_strip(corpus) -> None:
    got = corpus.resolve(layer(corpus), "R7.2")
    assert got.get(STRIP_FIELD) == 5


def test_the_waived_reading_drops_only_the_strip(corpus) -> None:
    where = layer(corpus)
    got = _Waived(corpus, (STRIP_FIELD,)).resolve(where, "R7.2")
    assert got.get(STRIP_FIELD) is None
    assert got.get("setback_front_ft") == corpus.resolve(where, "R7.2").get("setback_front_ft")
    assert got.get("setback_front_ft") is not None


def test_a_lot_the_strip_alone_holds_is_yellow_with_the_flag(corpus, pod) -> None:
    s = screened(corpus, pod, 70, 125)
    assert s.signed.binds == ()
    assert s.facts.strip_waived
    assert PARKING_STRIP_UNCONFIRMED in s.signed.reasons
    assert CODE in [f.code for f in s.signed.flags]
    assert fp.colour(s.signed.binds, s.signed.flags) is fp.Colour.yellow


def test_a_lot_that_misses_without_the_strip_too_keeps_its_miss(corpus, pod) -> None:
    s = screened(corpus, pod, 70, 120)
    assert s.signed.binds
    assert not s.facts.strip_waived
    assert CODE not in [f.code for f in s.signed.flags]
    assert fp.colour(s.signed.binds, s.signed.flags) is fp.Colour.red


def test_a_lot_with_room_for_the_strip_is_not_asked(corpus, pod) -> None:
    s = screened(corpus, pod, 70, 135)
    assert not s.facts.strip_waived
    assert CODE not in [f.code for f in s.signed.flags]
    assert PARKING_STRIP_UNCONFIRMED not in s.signed.reasons


def test_a_city_with_no_strip_is_never_waived(corpus, pod) -> None:
    got = corpus.resolve(layer(corpus, "portland", "RM1"), "RM1")
    assert got.get("setback_front_ft") is not None
    assert got.get(STRIP_FIELD) is None
    s = screened(corpus, pod, 40, 100, juris="portland", zone="RM1")
    assert not s.facts.strip_waived
    assert CODE not in [f.code for f in s.signed.flags]
