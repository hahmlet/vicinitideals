"""Two unequal side yards, held as the pair the code prints (FOLLOWUPS 205).

MMC 19.301.5.A: "On lots greater than 7,000 sq ft in the R-MD Zone, one side
yard shall be at least 5 ft and one side yard shall be at least 10 ft, except
on a corner lot the street side yard shall be 20 ft." Steph ruled 2026-11-18
(rulings.yaml ``2026-11-18-milwaukie-side-yards-5-and-10``): "5 on one, 10 on
the other" -- not 10 on both, and not left unheld.

``setback_side_ft`` holds the 5 on every side lot line; the new
``setback_side_larger_ft`` holds the 10, as printed, owed on ONE side lot
line. The envelope is cut with it on each of the lot's two side lines in turn
and the better answer kept. Where a lot's side lines do not fall in two it
lies on every side line. The side yard height plane of the same table is
added once on top of each yard, never twice.

A corner lot (Steph, the same day, rulings.yaml
``2026-11-18-milwaukie-corner-interior-side-5``): the street side yard is the
20 and the other, interior, side yard is the 5 -- no 10 is owed there.
"""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

import pytest
import shapely
import yaml
from shapely.geometry import MultiPolygon, Polygon

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.geom.envelope import SIDE_MEET_FT, Setbacks, buildable, side_lines
from flats.geom import EdgeClass, Tier
from flats.ingest import quadfit as bridge
from flats.ingest.quadfit import envelope_for, larger_side_choices, lot_from_row, screen_lot, setbacks_for
from flats.provenance.store import ProvenanceStore
from flats.score import relief, slack
from flats.score.paper import larger_side_yard_ft, paper_fit
from flats.tests.test_envelope_sag import _lot_edges
from flats.tests.test_quadfit_bridge import POD, X0, Y0, Rules, pod, row

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"
EPS = 1e-6
F, S, R, SS = EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.street_side
#: Front 20, sides 5 and 10, rear 20: R-MD over 7,000 sq ft.
PAIR = Setbacks(front_ft=20, side_ft=5, rear_ft=20, side_larger_ft=10)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _resolved(corpus, sqft: float):
    return corpus.resolve(MILWAUKIE, "R-MD", frozenset(), lot={"lot_sqft": sqft})


# --- the corpus -----------------------------------------------------------------


def test_the_pair_is_the_codes_two_printed_figures(corpus) -> None:
    got = _resolved(corpus, 9_000)
    assert got.get("setback_side_ft") == 5
    assert got.get("setback_side_larger_ft") == 10
    larger = got.values["setback_side_larger_ft"]
    path, _, line = larger.prov.quote.partition("#L")
    text = ProvenanceStore().load(path).text.splitlines()[int(line) - 1]
    assert "one side yard shall be at least 5 ft and one side yard shall be at least 10 ft" in text
    assert "On lots greater than 7,000 sq ft in the R-MD Zone" in text


@pytest.mark.parametrize("sqft,larger", [(3_000, 5), (7_000, 5), (7_001, 10), (20_000, 10)])
def test_the_larger_yard_is_owed_only_over_7000_sq_ft(corpus, sqft: float, larger: float) -> None:
    got = _resolved(corpus, sqft)
    assert got.get("setback_side_larger_ft") == larger
    cut = setbacks_for(got)
    assert cut is not None and cut.side_ft == 5
    # At or under 7,000 the larger of the two is the 5 itself: nothing more to cut.
    assert cut.side_larger_ft == (10 if larger == 10 else None)


@pytest.mark.parametrize("sqft", [7_001, 9_000, 20_000])
def test_on_a_corner_lot_the_interior_side_yard_is_the_five(corpus, sqft: float) -> None:
    # Ruled 2026-11-18 (2026-11-18-milwaukie-corner-interior-side-5): the
    # street side yard is the sentence's 20 and the other side yard its 5.
    got = corpus.resolve(MILWAUKIE, "R-MD", frozenset({"corner_lot"}), lot={"lot_sqft": sqft})
    assert got.get("setback_side_ft") == 5
    assert got.get("setback_side_larger_ft") == 5
    assert not got.ambiguous
    assert got.get("setback_street_side_ft") == 20
    larger = got.values["setback_side_larger_ft"]
    path, _, line = larger.prov.quote.partition("#L")
    text = ProvenanceStore().load(path).text.splitlines()[int(line) - 1]
    assert "except on a corner lot the street side yard shall be 20 ft" in text
    # Nothing more to cut than the 5 every side line already takes.
    assert larger_side_yard_ft(got) is None
    cut = setbacks_for(got)
    assert cut is not None and cut.side_ft == 5 and cut.side_larger_ft is None
    # The same lot not known to be a corner lot keeps the pair.
    assert _resolved(corpus, sqft).get("setback_side_larger_ft") == 10


def test_no_other_zone_in_the_corpus_states_a_larger_side_yard(corpus) -> None:
    stating = sorted(
        f"{layer_id}/{zone}"
        for layer_id, layer in corpus.layers.items()
        for zone, body in layer.zones.items()
        if "setback_side_larger_ft" in body.values
    )
    assert stating == [f"{MILWAUKIE}/R-MD"]


# --- the height plane is added once ----------------------------------------------


def _stub(side: float, printed: float | None, larger: float | None):
    values = {"setback_side_ft": SimpleNamespace(value=side, before_step_back=printed)}
    numbers = {"setback_side_ft": side, "setback_side_larger_ft": larger}
    return SimpleNamespace(values=values, exempted=(), get=numbers.get)


def test_at_the_pods_height_the_plane_adds_nothing(corpus) -> None:
    got = _resolved(corpus, 9_000)
    assert got.values["setback_side_ft"].before_step_back == 5
    assert larger_side_yard_ft(got) == 10


def test_a_taller_building_pays_the_plane_once_on_each_yard() -> None:
    # A 26 ft wall is six feet over Milwaukie's plane: 11 on the 5 ft side,
    # and 16 -- not 10, and not 22 -- on the 10 ft side.
    assert larger_side_yard_ft(_stub(side=11, printed=5, larger=10)) == 16


def test_no_larger_yard_where_the_code_states_one_side_yard() -> None:
    assert larger_side_yard_ft(_stub(side=5, printed=None, larger=None)) is None
    # Nor where the "larger" is no more than the side yard already cut.
    assert larger_side_yard_ft(_stub(side=5, printed=None, larger=5)) is None
    assert larger_side_yard_ft(_stub(side=12, printed=None, larger=10)) is None
    assert setbacks_for(Rules(setback_front_ft=20, setback_side_ft=5, setback_rear_ft=20)).side_larger_ft is None


# --- the side lot lines -----------------------------------------------------------

RECT = [(0.0, 0.0), (100.0, 0.0), (100.0, 130.0), (0.0, 130.0)]


def test_a_plain_interior_lot_has_two_side_lines() -> None:
    assert side_lines(_lot_edges(RECT, (F, S, R, S))) == (frozenset({1}), frozenset({3}))


def test_a_bent_side_line_is_one_line() -> None:
    bent = [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (104.0, 130.0), (0.0, 130.0)]
    assert side_lines(_lot_edges(bent, (F, S, S, R, S))) == (frozenset({1, 2}), frozenset({4}))


def test_a_corner_lot_has_one_and_a_pointed_lot_has_one() -> None:
    assert side_lines(_lot_edges(RECT, (F, SS, R, S), tier=Tier.corner)) == (frozenset({3}),)
    # Two side lines that meet at the back are one run of side line.
    triangle = [(0.0, 0.0), (100.0, 0.0), (50.0, 130.0)]
    assert side_lines(_lot_edges(triangle, (F, S, S))) == (frozenset({1, 2}),)
    assert SIDE_MEET_FT < 1


# --- the envelope ----------------------------------------------------------------


def _bounds(setbacks: Setbacks, classes=(F, S, R, S), tier=Tier.clean) -> tuple[float, ...]:
    env = buildable(Polygon(RECT), _lot_edges(RECT, classes, tier=tier), setbacks)
    return tuple(round(v, 6) for v in env.bounds)


def test_the_chosen_side_takes_the_ten_and_the_other_the_five() -> None:
    # Edge 1 is the east line (x = 100), edge 3 the west (x = 0).
    assert _bounds(dataclasses.replace(PAIR, larger_side=0)) == (5, 20, 90, 110)
    assert _bounds(dataclasses.replace(PAIR, larger_side=1)) == (10, 20, 95, 110)


def test_either_choice_leaves_the_same_width_fifteen_feet_short_of_the_lot() -> None:
    for side in (0, 1):
        x0, _, x1, _ = _bounds(dataclasses.replace(PAIR, larger_side=side))
        assert x1 - x0 == pytest.approx(100 - 15)
    # Two fives were the hole: ten feet where the code asks fifteen.
    x0, _, x1, _ = _bounds(dataclasses.replace(PAIR, side_larger_ft=None))
    assert x1 - x0 == pytest.approx(100 - 10)


def test_with_no_choice_made_every_side_line_takes_the_ten() -> None:
    assert _bounds(PAIR) == (10, 20, 90, 110)


def test_a_lot_whose_side_lines_do_not_fall_in_two_takes_the_ten_on_each() -> None:
    # The envelope alone, handed a larger yard and a lot with one interior
    # side line: that line takes it whatever was chosen (the street side
    # line keeps its own 20). Milwaukie's rules hand a corner lot no larger
    # yard (ruled 2026-11-18); this is the cut for a lot that is shaped like
    # a corner and not known to be one.
    corner = dataclasses.replace(PAIR, street_side_ft=20, larger_side=0)
    assert _bounds(corner, (F, SS, R, S), Tier.corner) == (10, 20, 80, 110)
    corner = dataclasses.replace(corner, larger_side=1)
    assert _bounds(corner, (F, SS, R, S), Tier.corner) == (10, 20, 80, 110)


def test_a_lot_cut_by_one_uniform_shrink_takes_at_least_the_larger_yard() -> None:
    assert PAIR.largest_ft == 20
    assert dataclasses.replace(PAIR, front_ft=0, rear_ft=0).largest_ft == 10
    env = buildable(
        Polygon(RECT), _lot_edges(RECT, (F, S, R, S), tier=Tier.irregular),
        dataclasses.replace(PAIR, front_ft=0, rear_ft=0, larger_side=0),
    )
    assert tuple(round(v, 6) for v in env.bounds) == (10, 10, 90, 120)


def test_an_envelope_never_grows_with_the_larger_yard() -> None:
    plain = buildable(Polygon(RECT), _lot_edges(RECT, (F, S, R, S)), dataclasses.replace(PAIR, side_larger_ft=None))
    for side in (0, 1, None):
        cut = buildable(Polygon(RECT), _lot_edges(RECT, (F, S, R, S)), dataclasses.replace(PAIR, larger_side=side))
        assert plain.buffer(EPS).contains(cut)
        assert cut.area < plain.area


# --- the bridge -------------------------------------------------------------------


def _row(width: float, depth: float, classes: str = "FSRS", **over: object) -> dict[str, object]:
    corners = [(X0, Y0), (X0 + width, Y0), (X0 + width, Y0 + depth), (X0, Y0 + depth)]
    edges = [[*a, *b, cls] for a, b, cls in zip(corners, corners[1:] + corners[:1], classes, strict=True)]
    box = shapely.box(X0, Y0, X0 + width, Y0 + depth)
    return row(
        jurisdiction="milwaukie", zone="R-MD", area_sqft=width * depth, frontage_ft=width,
        lot_width_ft=width, lot_depth_ft=depth, edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box.buffer(-5)), lot_wkb=shapely.to_wkb(box), **over,
    )


def test_the_bridge_tries_both_sides_only_where_there_is_a_pair_and_two_lines(corpus) -> None:
    big = lot_from_row(_row(100, 130), corpus.layers)
    assert larger_side_choices(big, _resolved(corpus, 13_000)) == (0, 1)
    # No larger yard at 7,000 sq ft or less.
    small = lot_from_row(_row(70, 100), corpus.layers)
    assert larger_side_choices(small, _resolved(corpus, 7_000)) == (None,)
    # One interior side line: nothing to choose, the envelope lays it there.
    corner = lot_from_row(_row(100, 130, "FFRS", front_bearings_json="[0.0, 90.0]"), corpus.layers)
    assert corner.edges is not None and len(side_lines(corner.edges)) == 1
    assert larger_side_choices(corner, _resolved(corpus, 13_000)) == (None,)
    # Another zone's rules state no larger yard.
    assert larger_side_choices(big, corpus.resolve("or/multnomah/portland", "R5", frozenset(), lot={"lot_sqft": 13_000})) == (None,)


def test_the_bridge_screens_a_corner_lot_with_five_on_its_interior_side(corpus, policies) -> None:
    # Ruled 2026-11-18 (2026-11-18-milwaukie-corner-interior-side-5). Two
    # street lines make the corner; the screen resolves the corner lot's
    # rules, and they hand the envelope no larger yard.
    policy, relief_policy = policies
    corner = lot_from_row(_row(100, 130, "FFRS", front_bearings_json="[0.0, 90.0]"), corpus.layers)
    got = screen_lot(corner, [pod()], rules=corpus, policy=policy, relief=relief_policy, step_deg=30.0)
    assert got
    for s in got:
        assert s.rules.get("setback_side_larger_ft") == 5
        assert s.envelope.setbacks.side_ft == 5
        assert s.envelope.setbacks.side_larger_ft is None
        assert s.envelope.setbacks.street_side_ft == 20
    # The interior lot beside it still owes the 10 on one side.
    interior = lot_from_row(_row(100, 130), corpus.layers)
    for s in screen_lot(interior, [pod()], rules=corpus, policy=policy, relief=relief_policy, step_deg=30.0):
        assert s.rules.get("setback_side_larger_ft") == 10
        assert s.envelope.setbacks.side_larger_ft == 10


def test_the_bridges_envelope_holds_five_and_ten(corpus) -> None:
    lot = lot_from_row(_row(100, 130), corpus.layers)
    rules = _resolved(corpus, 13_000)
    widths = {}
    for side in (0, 1, None):
        env = envelope_for(lot, rules, larger_side=side)
        assert env.source == "flats" and env.setbacks.side_larger_ft == 10
        x0, _, x1, _ = env.geom.bounds
        widths[side] = (round(x0 - X0, 6), round(X0 + 100 - x1, 6))
    # (west yard, east yard): edge 1 is the east line, edge 3 the west.
    assert widths == {0: (5, 10), 1: (10, 5), None: (10, 10)}


def test_the_placement_chooses_the_side_and_keeps_the_better_answer(corpus, policies, monkeypatch) -> None:
    lot = lot_from_row(_row(100, 130), corpus.layers)
    real = bridge.envelope_for
    tried: list[int | None] = []

    def spoiled(which: int | None):
        """The real envelope, emptied when the larger yard is on ``which``."""

        def cut(*args, **kw):
            tried.append(kw.get("larger_side"))
            env = real(*args, **kw)
            if which is not None and kw.get("larger_side") == which:
                return dataclasses.replace(env, geom=MultiPolygon([]), ground=MultiPolygon([]))
            return env

        return cut

    def screened(which: int | None):
        tried.clear()
        monkeypatch.setattr(bridge, "envelope_for", spoiled(which))
        (got,) = screen_lot(lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0)
        return got

    plain = screened(None)
    assert {0, 1} <= set(tried) and None not in tried
    assert plain.fit.fits and plain.envelope.setbacks.larger_side in (0, 1)
    # With the 10 ft yard workable on one side only, that side is the one kept.
    assert (got := screened(0)).fit.fits and got.envelope.setbacks.larger_side == 1
    assert (got := screened(1)).fit.fits and got.envelope.setbacks.larger_side == 0


# --- the paper lot ----------------------------------------------------------------


def test_the_paper_lot_charges_fifteen_feet_of_side_yard(corpus) -> None:
    # The same column of Table 19.301.4 either side of the line, so the only
    # difference is the pair: 5 + 10 across the paper lot where 5 + 5 stood.
    # A square building, so neither way round hides behind the 60 ft lot width.
    square = Design(**{**yaml.safe_load(POD), "id": "square", "footprint": {"width_ft": 70, "depth_ft": 70}})
    over, under = (paper_fit(square, _resolved(corpus, sqft)) for sqft in (7_001, 7_000))
    assert over.min_width_ft is not None and under.min_width_ft is not None
    assert over.width_binding == under.width_binding != "min_lot_width_ft"
    assert over.min_width_ft - under.min_width_ft == pytest.approx(5)
