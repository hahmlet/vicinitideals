"""Two rear lines, one on the alley: each takes its own rear setback.

FOLLOWUPS 12(b) and the Gresham loose end of 3. The rules resolve the rear
setback once for a lot, switched by ``alley_at_rear``; but a lot can have a
rear line on the alley and another rear line off it -- the second leg of a
jogged rear, a corner lot's line opposite the side street. Portland's waiver
("no side or rear setback from a lot line abutting an alley") then reached
the line off the alley, so the bridge kept quadfit's envelope; Gresham's
rear-with-alley NUMBER (HDR-PV: 5 ft against the ordinary 15) reached it
unnoticed, because the fallback checked exemptions only. Now the bridge
resolves the lot a second time without the rear alley and the envelope cuts
the alley's number on the alley line and the ordinary one on the other.

Real lots, read off quadfit's s4 of 2026-09-29 (state-plane feet).
"""

from __future__ import annotations

import json

import pytest
import shapely
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.geom.corner import name_front
from flats.geom.edges import Edge, EdgeClass
from flats.geom.envelope import Setbacks
from flats.ingest.quadfit import envelope_for, lot_from_row, rear_off_alley, screen_lot
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

#: 1N1E14AD -17900, Portland R5, tier A: street on the west, the alley the
#: whole east (rear) line, and a 3 ft jog in the south side line that s4
#: names a rear edge (it runs with the frontage) -- a rear line off the alley.
JOG_EDGES = [
    [7653402.31, 702098.43, 7653400.97, 702051.45, "A"],
    [7653400.97, 702051.45, 7653357.38, 702052.51, "S"],
    [7653357.38, 702052.51, 7653357.3, 702049.51, "R"],
    [7653357.3, 702049.51, 7653300.9, 702050.88, "S"],
    [7653300.9, 702050.88, 7653302.33, 702100.86, "F"],
    [7653302.33, 702100.86, 7653402.31, 702098.43, "S"],
]
JOG_COVER = json.dumps(["1" * 10, None, None, None, None, None])

#: 1S3E20BD -21900, Gresham HDR-PV, tier B: 25 x 105, streets east and
#: south, the alley the whole north line, the neighbour's yard west. Gresham
#: leaves the corner front to the owner; fronting east, the west line is the
#: rear off the alley and the north alley line stays a rear alley line.
GRESHAM_EDGES = [
    [7697112.37, 663267.32, 7697110.89, 663162.05, "F"],
    [7697110.89, 663162.05, 7697085.9, 663162.75, "F"],
    [7697085.9, 663162.75, 7697087.37, 663267.69, "R"],
    [7697087.37, 663267.69, 7697112.37, 663267.32, "A"],
]
GRESHAM_COVER = json.dumps([None, None, None, "1" * 6])
EAST = 89.19


def ring(edges: list[list[object]]) -> shapely.Polygon:
    return shapely.Polygon([(float(e[0]), float(e[1])) for e in edges])


def row(edges, cover, **over: object) -> dict[str, object]:
    lot = ring(edges)
    base: dict[str, object] = {
        "TLID": "real",
        "jurisdiction": "portland",
        "zone": "R5",
        "tier": "A",
        "area_sqft": lot.area,
        "frontage_ft": 50.0,
        "lot_width_ft": 50.0,
        "lot_depth_ft": 100.0,
        "edges_json": json.dumps(edges),
        "front_bearings_json": "[88.37]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "has_z_overlay": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "alley_cover_json": cover,
        "lot_wkb": shapely.to_wkb(lot),
        # quadfit's own envelope, used only where the bridge cannot cut one.
        "wkb": shapely.to_wkb(lot.buffer(-5, join_style="mitre")),
    }
    base.update(over)
    return base


def line(e: list[object]) -> shapely.LineString:
    return shapely.LineString([(float(e[0]), float(e[1])), (float(e[2]), float(e[3]))])


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def resolved(corpus, lot, *, rear_alley: bool):
    """The lot's rules as the screen resolves them, with the rear alley or
    without it -- the second is what :func:`screen_lot` hands over as
    ``plain``."""
    config = configure(lot.facts, pod(), observed={**lot.observed, "alley_at_rear": rear_alley})
    return corpus.resolve(lot.layer_id, lot.zone, config.conditions, lot=config.measures)


def test_portlands_waiver_reaches_the_alley_line_and_not_the_jog(corpus, policies) -> None:
    lot = lot_from_row(row(JOG_EDGES, JOG_COVER), corpus.layers)
    assert lot.observed["alley_at_rear"] is True
    assert rear_off_alley(lot.edges)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    # FLATS cuts its own envelope now; before, the jog sent it to quadfit's.
    assert s.envelope.source == "flats"
    assert s.envelope.setbacks.alley_rear_ft == 0
    assert s.envelope.setbacks.rear_ft == 5
    env = s.envelope.geom
    # The alley line is waived: the envelope runs up to it ...
    assert env.distance(line(JOG_EDGES[0])) == pytest.approx(0.0, abs=0.01)
    # ... and the jog, a rear line on the neighbour, keeps R5's 5 ft.
    assert env.distance(line(JOG_EDGES[2])) >= 5.0 - 1e-6
    # The court is charged against the alley line's own number, as before.
    assert s.envelope.rear_cut_ft is None


def test_without_the_ordinary_rear_the_exempt_lot_keeps_quadfits_envelope(corpus) -> None:
    # The old contract, for a caller that resolves only once.
    lot = lot_from_row(row(JOG_EDGES, JOG_COVER), corpus.layers)
    got = resolved(corpus, lot, rear_alley=True)
    assert "setback_rear_ft" in got.exempted
    assert envelope_for(lot, got).source == "quadfit"
    assert envelope_for(lot, got, resolved(corpus, lot, rear_alley=False)).source == "flats"


def test_no_cover_on_record_is_no_rear_alley_line(corpus, policies) -> None:
    # s4 before alley_cover_json: nothing vouches for the alley running the
    # rear line, so every rear line keeps the ordinary 5 ft -- the alley one too.
    lot = lot_from_row(row(JOG_EDGES, None), corpus.layers)
    assert lot.observed["alley_at_rear"] is False
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
    assert s.envelope.source == "flats"
    assert s.envelope.setbacks.alley_rear_ft is None
    assert s.envelope.geom.distance(line(JOG_EDGES[0])) >= 5.0 - 1e-6


def gresham(corpus):
    lot = lot_from_row(
        row(
            GRESHAM_EDGES,
            GRESHAM_COVER,
            jurisdiction="gresham",
            zone="HDR-PV",
            tier="B",
            front_bearings_json=json.dumps([EAST, 178.4]),
            frontage_ft=130.0,
            lot_width_ft=25.0,
            lot_depth_ft=105.0,
        ),
        corpus.layers,
    )
    import dataclasses

    return dataclasses.replace(lot, edges=name_front(lot.edges, EAST))


def test_greshams_alley_number_reaches_the_alley_line_and_not_the_other_rear(corpus) -> None:
    lot = gresham(corpus)
    assert lot.observed["alley_at_rear"] is True
    assert rear_off_alley(lot.edges)
    got = resolved(corpus, lot, rear_alley=True)
    plain = resolved(corpus, lot, rear_alley=False)
    # HDR-PV: 15 ft rear, 5 ft where the rear line is on an alley.
    assert got.get("setback_rear_ft") == 5 and plain.get("setback_rear_ft") == 15
    env = envelope_for(lot, got, plain)
    assert env.source == "flats"
    assert (env.setbacks.rear_ft, env.setbacks.alley_rear_ft) == (15, 5)
    # The west line faces the neighbour's yard: 15 ft, not the alley's 5.
    assert env.geom.distance(line(GRESHAM_EDGES[2])) >= 15.0 - 1e-6
    assert env.geom.distance(line(GRESHAM_EDGES[3])) == pytest.approx(5.0, abs=0.05)
    # What the bridge cut before: the alley's 5 ft on the west line too.
    before = envelope_for(lot, got)
    assert before.geom.distance(line(GRESHAM_EDGES[2])) == pytest.approx(5.0, abs=0.05)
    assert env.sqft < before.sqft


def test_an_alley_rear_edge_the_cover_does_not_vouch_for_takes_the_larger_number() -> None:
    yards = Setbacks(front_ft=10, side_ft=5, rear_ft=15, alley_rear_ft=5)

    def rear(cover: str | None) -> Edge:
        return Edge(0, 100, 50, 100, 50.0, 0.0, EdgeClass.rear, alley=True, cover=cover)

    assert yards.for_edge(rear("1" * 10)) == 5
    assert yards.for_edge(rear(None)) == 5  # a classifier that measures no stretch
    assert yards.for_edge(rear("")) == 15  # none on record
    assert yards.for_edge(rear("1" * 6 + "0" * 4)) == 15  # the alley stops short
    off = Edge(0, 100, 50, 100, 50.0, 0.0, EdgeClass.rear)
    assert yards.for_edge(off) == 15
    # Exempt on the alley line, and the uniform inset of an irregular lot
    # still takes the deepest yard of either rear line.
    assert Setbacks(front_ft=10, side_ft=5, rear_ft=5, alley_rear_ft=0).largest_ft == 10
    assert Setbacks(front_ft=5, side_ft=5, rear_ft=15, alley_rear_ft=5).largest_ft == 15
