"""A rear alley along PART of the rear line waives only the stretch it runs.

FOLLOWUPS 3, Steph's ruling of 2026-09-28 ("careful reading"): a lot line an
alley runs part of abuts the alley along the covered stretch only. Until
2026-09-29 the registry's ``alley_at_rear`` was off on such a lot and the
whole rear line took the ordinary rear setback -- conservative. Now the
bridge resolves the lot once more with the alley and the envelope cuts the
rear line stretch by stretch, as side lines already were: the alley's rear
(Portland's waiver, Gresham's number) where s4's cover rays found the alley,
the larger of the two elsewhere. The court is charged against the smaller
strip, and the screen keeps whichever of the two cuts answers better -- each
is sound alone, so the better one is too.

Real lots, read off quadfit's s4 of 2026-09-29 (state-plane feet).
"""

from __future__ import annotations

import json

import pytest
import shapely
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier
from flats.geom.envelope import Setbacks, _pieces, buildable
from flats.ingest.quadfit import envelope_for, lot_from_row, part_rear_alley, screen_lot, setbacks_for
from flats.score import relief, slack
from flats.score.configure import configure

pytestmark = pytest.mark.unit

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""

#: 1S2E05AB -11900, Portland R5, tier A (the fixture of
#: `Lot Analysis/quadfit/tests/fixtures/alley_stops_short_1S2E05AB_11900.json`).
#: Street east; the 88.7 ft rear line on the west is an alley line on s4's
#: three rays of five, and ten of its eighteen cover rays -- the southern
#: 46.8 ft -- find the alley, which is drawn no further north.
STUB_EDGES = [
    [7667288.85, 682083.46, 7667286.58, 681994.75, "F"],
    [7667286.58, 681994.75, 7667186.62, 681997.77, "S"],
    [7667186.62, 681997.77, 7667188.88, 682086.49, "A"],
    [7667188.88, 682086.49, 7667288.85, 682083.46, "S"],
]
STUB_COVER = json.dumps([None, None, "1" * 10 + "0" * 8, None])
REAR = STUB_EDGES[2]
REAR_FT = shapely.LineString([(REAR[0], REAR[1]), (REAR[2], REAR[3])]).length
#: Where the last ray on the alley stands, from the south corner.
COVERED_FT = 2.5 + (REAR_FT - 5.0) * 9 / 17


def ring(edges: list[list[object]]) -> shapely.Polygon:
    return shapely.Polygon([(float(e[0]), float(e[1])) for e in edges])


def row(cover: str | None, **over: object) -> dict[str, object]:
    lot = ring(STUB_EDGES)
    base: dict[str, object] = {
        "TLID": "1S2E05AB  -11900",
        "jurisdiction": "portland",
        "zone": "R5",
        "tier": "A",
        "area_sqft": lot.area,
        "frontage_ft": 88.7,
        "lot_width_ft": 88.74,
        "lot_depth_ft": 100.01,
        "edges_json": json.dumps(STUB_EDGES),
        "front_bearings_json": "[88.54]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "alley_width_ft": 13.0,
        "alley_cover_json": cover,
        "lot_wkb": shapely.to_wkb(lot),
        "wkb": shapely.to_wkb(lot.buffer(-5, join_style="mitre")),
    }
    base.update(over)
    return base


def point_along(d: float) -> shapely.Point:
    """The point ``d`` ft up the rear line from its south corner."""
    x1, y1, x2, y2 = (float(v) for v in REAR[:4])
    t = d / REAR_FT
    return shapely.Point(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def resolved(corpus, lot, *, rear_alley: bool):
    config = configure(lot.facts, pod(), observed={**lot.observed, "alley_at_rear": rear_alley})
    return corpus.resolve(lot.layer_id, lot.zone, config.conditions, lot=config.measures)


def test_the_covered_stretch_is_waived_and_the_rest_keeps_the_rear(corpus) -> None:
    lot = lot_from_row(row(STUB_COVER), corpus.layers)
    assert lot.observed["alley_at_rear"] is False  # the registry's: not the whole line
    assert part_rear_alley(lot)
    got = resolved(corpus, lot, rear_alley=False)
    alleyed = resolved(corpus, lot, rear_alley=True)
    assert got.get("setback_rear_ft") == 5 and "setback_rear_ft" in alleyed.exempted

    before = envelope_for(lot, got)
    after = envelope_for(lot, got, None, alleyed)
    assert (after.setbacks.rear_ft, after.setbacks.alley_rear_ft) == (5, 0)
    assert before.setbacks.alley_rear_ft is None
    env = after.geom
    # Behind the covered stretch, past the south side yard: up to the line.
    assert env.distance(point_along(25.0)) == pytest.approx(0.0, abs=0.01)
    # Past where the alley stops, and a square cap's width beyond it: 5 ft.
    assert env.distance(point_along(COVERED_FT + 6.0)) >= 5.0 - 1e-6
    assert env.distance(point_along(80.0)) >= 5.0 - 1e-6
    # The whole-line cut kept 5 ft everywhere.
    assert before.geom.distance(point_along(25.0)) >= 5.0 - 1e-6
    # The gain is the 5 ft strip behind the covered stretch, less the side
    # yard at the south end and the cap at the north: never more.
    gain = after.sqft - before.sqft
    assert 0 < gain <= 5.0 * (COVERED_FT - 5.0) + 0.5
    assert gain == pytest.approx(5.0 * (COVERED_FT - 5.0 - 5.0), abs=2.0)
    # The court is charged against the strip the envelope lost there: none.
    assert after.rear_cut_ft == 0 and before.rear_cut_ft is None
    assert after.geom.contains(before.geom.buffer(-0.01))


def test_no_cover_on_record_is_no_stretch_and_nothing_changes(corpus) -> None:
    for cover in (None, json.dumps([None, None, "", None]), json.dumps([None, None, "0" * 18, None])):
        lot = lot_from_row(row(cover), corpus.layers)
        assert lot.facts.alley_at_rear is True and lot.facts.alley_rear_whole is False
        assert not part_rear_alley(lot)
        got = resolved(corpus, lot, rear_alley=False)
        alleyed = resolved(corpus, lot, rear_alley=True)
        env = envelope_for(lot, got, None, alleyed)
        assert env.setbacks.alley_rear_ft is None and env.rear_cut_ft is None
        assert env.sqft == pytest.approx(envelope_for(lot, got).sqft)


def test_a_tier_c_lot_is_still_shrunk_by_its_largest_yard(corpus) -> None:
    lot = lot_from_row(row(STUB_COVER, tier="C"), corpus.layers)
    assert not part_rear_alley(lot)


def test_the_screen_keeps_the_better_of_the_two_cuts(corpus, policies) -> None:
    lot = lot_from_row(row(STUB_COVER), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    unmeasured = lot_from_row(row(None), corpus.layers)
    (u,) = screen_lot(unmeasured, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    from flats.ingest.quadfit import _front_rank

    # Never worse than the whole-line ordinary cut (which the record with no
    # cover still gets): the stretch cut only ever adds a candidate.
    assert _front_rank(s)[:2] <= _front_rank(u)[:2]
    assert s.envelope.setbacks.alley_rear_ft in (None, 0)


def test_the_rear_line_is_cut_per_stretch_like_the_side() -> None:
    # Gresham-style numbers: 15 ft ordinary rear, 5 ft on the alley.
    yards = Setbacks(front_ft=10, side_ft=5, rear_ft=15, alley_rear_ft=5)

    def rear(cover: str | None) -> Edge:
        return Edge(0, 100, 100, 100, 100.0, 90.0, EdgeClass.rear, alley=True, cover=cover)

    # Twenty rays 5 ft apart from 2.5 ft: the first ten cover 0..47.5.
    pieces = _pieces(rear("1" * 10 + "0" * 10), yards)
    assert [d for _, d in pieces] == [5, 15]
    assert pieces[0][0][2] == pytest.approx(47.5)
    assert _pieces(rear("1" * 20), yards) == [((0, 100, 100, 100), 5)]
    assert _pieces(rear(""), yards) == [((0, 100, 100, 100), 15)]
    assert _pieces(rear("0" * 20), yards) == [((0, 100, 100, 100), 15)]
    # A stretch in the middle: the neighbour on both sides of it.
    assert [d for _, d in _pieces(rear("0" * 5 + "1" * 10 + "0" * 5), yards)] == [15, 5, 15]
    # No alley number: the line takes the ordinary rear whatever the cover.
    plain = Setbacks(front_ft=10, side_ft=5, rear_ft=15)
    assert _pieces(rear("1" * 10 + "0" * 10), plain) == [((0, 100, 100, 100), 15)]
    # An alley number LARGER than the ordinary one reaches the covered
    # stretch, and the rest keeps the larger too.
    tight = Setbacks(front_ft=10, side_ft=5, rear_ft=5, alley_rear_ft=10)
    assert _pieces(rear("1" * 10 + "0" * 10), tight) == [((0, 100, 100, 100), 10)]
    # A rear line off the alley never sees the alley number.
    off = Edge(0, 100, 100, 100, 100.0, 90.0, EdgeClass.rear)
    assert _pieces(off, yards) == [((0, 100, 100, 100), 15)]


def test_the_cut_on_a_plain_rectangle() -> None:
    # 100 x 100, street south, alley behind the west 47.5 ft of the north line.
    lot = shapely.box(0, 0, 100, 100)
    edges = LotEdges(
        tier=Tier.clean,
        edges=(
            Edge(0, 0, 100, 0, 100.0, 90.0, EdgeClass.front),
            Edge(100, 0, 100, 100, 100.0, 0.0, EdgeClass.side),
            Edge(0, 100, 100, 100, 100.0, 90.0, EdgeClass.rear, alley=True, cover="1" * 10 + "0" * 10),
            Edge(0, 100, 0, 0, 100.0, 180.0, EdgeClass.side),
        ),
        front_bearings=(90.0,),
        frontage_ft=100.0,
        convexity=1.0,
    )
    yards = Setbacks(front_ft=10, side_ft=5, rear_ft=15, alley_rear_ft=5)
    env = buildable(lot, edges, yards)
    # x 5..95 wide, y 10..85 deep, plus 10 ft more behind x 5..32.5 (the
    # 15 ft piece's square cap reaches 15 ft back from 47.5).
    assert env.area == pytest.approx(90 * 75 + (47.5 - 15 - 5) * 10)


def test_setbacks_for_takes_the_alleys_rear_from_the_second_resolution() -> None:
    class Rules:
        def __init__(self, *exempted: str, **values: object) -> None:
            self.values, self.exempted = values, exempted

        def get(self, name: str) -> object:
            return self.values.get(name)

    got = Rules(setback_front_ft=10, setback_side_ft=5, setback_rear_ft=15)
    assert setbacks_for(got, None, Rules(setback_rear_ft=5)).alley_rear_ft == 5  # type: ignore[arg-type]
    assert setbacks_for(got, None, Rules("setback_rear_ft")).alley_rear_ft == 0  # type: ignore[arg-type]
    # The same number, or none stated: nothing is split.
    assert setbacks_for(got, None, Rules(setback_rear_ft=15)).alley_rear_ft is None  # type: ignore[arg-type]
    assert setbacks_for(got, None, Rules()).alley_rear_ft is None  # type: ignore[arg-type]
    assert setbacks_for(got, None, Rules(setback_rear_ft=5)).rear_ft == 15  # type: ignore[arg-type]
