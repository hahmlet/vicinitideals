"""Unincorporated Clackamas follows its own front-parking rule (Steph 2026-11-09,
rulings.yaml ``2026-11-09-clackamas-front-parking-follow-zdo``: "Follow the
county's rules.").

The 2026-11-08 ruling keeps the court out of the front yard where the code is
silent. ZDO 845.02(D) is not silent: parking may stand between a quadplex and a
public street where a dwelling separates it from the street, or where it faces no
more than half the street frontage. The screen measures the second on the final
drawing; the first is never measured. Anything unread keeps the hold.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import shapely
import yaml

import math

from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg
from flats.ingest.quadfit import court_in_front_yard, front_parking_allowed
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
RULING = "2026-11-09-clackamas-front-parking-follow-zdo"
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"
RULINGS = Path(__file__).resolve().parents[1] / "config" / "rulings.yaml"

F, S, R, SS = EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.street_side


class _Rules(dict):
    exempted: tuple[str, ...] = ("parking_front_prohibited",)


def _edges(*spec, bearings=(0.0,)) -> LotEdges:
    return LotEdges(
        Tier.clean,
        tuple(
            Edge(
                x1, y1, x2, y2, math.hypot(x2 - x1, y2 - y1), bearing_deg(x1, y1, x2, y2), cls,
                public_road=public,
            )
            for x1, y1, x2, y2, cls, public in spec
        ),
        tuple(bearings),
        100.0,
        1.0,
    )


#: A 100 x 200 interior lot, its front on a public street along y = 0.
INTERIOR = _edges(
    (0, 0, 100, 0, F, True), (100, 0, 100, 200, S, False),
    (100, 200, 0, 200, R, False), (0, 200, 0, 0, S, False),
)
#: The same lot whose front s4 did not read as a public street (a private road
#: the yards count, or nothing read).
UNREAD = _edges(
    (0, 0, 100, 0, F, False), (100, 0, 100, 200, S, False),
    (100, 200, 0, 200, R, False), (0, 200, 0, 0, S, False),
)
LOT = shapely.box(0, 0, 100, 200)
BUILDING = shapely.box(10, 30, 90, 60)
#: 40 ft of the 100 ft frontage, between the building and the street.
NARROW = shapely.box(30, 5, 70, 25)
#: 60 ft of it.
WIDE = shapely.box(10, 5, 70, 25)
BEHIND = shapely.box(30, 70, 70, 100)

CODE = {
    "parking_front_share_allowed": True,
    "parking_area_max_frontage_pct": 50,
    "parking_area_frontage_any_street": True,
}


def _plan(court, *, edges=INTERIOR, rules=CODE, exempt=True):
    got = _Rules(rules)
    if not exempt:
        got.exempted = ()
    ring = lambda g: [list(p) for p in g.exterior.coords]  # noqa: E731
    return SimpleNamespace(
        lot=SimpleNamespace(edges=edges, access=(), lot_geom=LOT),
        rules=got,
        street_edges=None,
        drawing={"fits": True, "building": ring(BUILDING), "court": ring(court)},
    )


def test_a_court_within_half_the_frontage_may_stand_in_front() -> None:
    """845.02(D)(2): 40 ft of a 100 ft public frontage is within the cap."""
    assert not court_in_front_yard(_plan(NARROW))


def test_a_court_over_half_the_frontage_is_held() -> None:
    assert court_in_front_yard(_plan(WIDE))


def test_a_court_behind_is_clear_as_before() -> None:
    assert not court_in_front_yard(_plan(BEHIND))


def test_a_line_not_read_as_a_public_street_keeps_the_hold() -> None:
    """845.02(D) speaks of a public street. A private road the yards count, or
    a street s4 did not read, is not shown to be one: the silent-codes hold."""
    assert court_in_front_yard(_plan(NARROW, edges=UNREAD))


def test_a_silent_code_keeps_the_hold() -> None:
    """Every other code: the 2026-11-08 ruling, unchanged."""
    silent = {k: v for k, v in CODE.items() if k != "parking_front_share_allowed"}
    assert court_in_front_yard(_plan(NARROW, rules=silent))
    off = dict(CODE, parking_front_share_allowed=False)
    assert court_in_front_yard(_plan(NARROW, rules=off))


def test_no_cap_or_an_outright_ban_keeps_the_hold() -> None:
    capless = {k: v for k, v in CODE.items() if k != "parking_area_max_frontage_pct"}
    assert court_in_front_yard(_plan(NARROW, rules=capless))
    banned = dict(CODE, parking_front_prohibited=True)
    assert court_in_front_yard(_plan(NARROW, rules=banned, exempt=False))


def test_an_unmeasured_lot_keeps_the_hold() -> None:
    s = _plan(NARROW)
    s.lot.lot_geom = None
    assert court_in_front_yard(s)


def test_the_cap_is_read_on_every_street() -> None:
    """A corner: the court in front is 40 ft of the 100 ft front, within the
    cap, and faces 33 ft of the 60 ft side street, over it -- the any-street
    reading (Steph 2026-10-14) holds it."""
    from flats.fit.frontage import street_runs

    corner = _edges(
        (0, 0, 100, 0, F, True), (100, 0, 100, 60, SS, True),
        (100, 60, 0, 60, R, False), (0, 60, 0, 0, S, False), bearings=(0.0, 90.0),
    )
    building, court = shapely.box(5, 35, 95, 55), shapely.box(55, 1, 95, 34)
    s = _plan(court, edges=corner)
    s.lot.lot_geom = shapely.box(0, 0, 100, 60)
    s.drawing["building"] = [list(p) for p in building.exterior.coords]
    front, side = street_runs(s.lot.lot_geom, corner, court, building)
    assert front[0] <= 50 < side[0]
    assert court_in_front_yard(s)
    assert not front_parking_allowed(s, building, court, ((0, 0, 100, 0),))
    # The same court on a lot whose side street is long enough passes.
    deep = _edges(
        (0, 0, 100, 0, F, True), (100, 0, 100, 200, SS, True),
        (100, 200, 0, 200, R, False), (0, 200, 0, 0, S, False), bearings=(0.0, 90.0),
    )
    s = _plan(court, edges=deep)
    s.drawing["building"] = [list(p) for p in building.exterior.coords]
    assert front_parking_allowed(s, building, court, ((0, 0, 100, 0),))


# --- the encoding ---------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def _quoted(ref: str) -> str:
    path, _, ranges = ref.partition("#")
    lines = (DOCS / path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for part in ranges.split(","):
        start, _, end = part.lstrip("L").partition("-L")
        out += lines[int(start) - 1 : int(end or start)]
    return " ".join(" ".join(out).split())


@pytest.mark.parametrize("zone", ["R8.5", "R7", "VA", "HDR"])
def test_unincorporated_clackamas_states_the_conditions(corpus, zone) -> None:
    quad = corpus.resolve(CLACKAMAS, zone).values
    assert quad["parking_front_share_allowed"].value is True
    text = _quoted(quad["parking_front_share_allowed"].prov.quote)
    assert "shall not be located between a building and a public street" in text
    assert "separated from the street by a dwelling" in text
    assert "does not exceed a total of 50 percent of the street frontage" in text
    assert quad["parking_area_max_frontage_pct"].value == 50
    town = corpus.resolve(CLACKAMAS, zone, ("unit_lots",)).values
    assert town["parking_front_share_allowed"].value is False
    text = _quoted(town["parking_front_share_allowed"].prov.quote)
    assert "Off-street parking areas shall not be located between a townhouse and a public street" in text


def test_cities_in_clackamas_keep_their_own_rules(corpus) -> None:
    for layer, zone in (("or/clackamas/oregon-city", "R-5"), ("or/clackamas/sandy", "R-2")):
        assert corpus.resolve(layer, zone).get("parking_front_share_allowed") is None


def test_the_ruling_is_on_the_register() -> None:
    entries = {e["id"]: e for e in yaml.safe_load(RULINGS.read_text(encoding="utf-8"))}
    got = entries[RULING]
    assert got["scope"] == {"county": "clackamas", "city": "_unincorporated"}
    assert "Follow the county's rules." in got["ruling"]
    assert "flats/ingest/quadfit.py" in got["encoded_in"]


# --- the screen -----------------------------------------------------------------


@pytest.fixture(scope="module")
def trusted():
    from flats.encode.load import load_trusted

    return load_trusted(strict=False).rules


def _through(width: float, kinds):
    import json

    from flats.tests.test_quadfit_bridge import X0, Y0, row

    depth = 170.0
    edges = [
        [X0, Y0, X0 + width, Y0, "F"],
        [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
        [X0 + width, Y0 + depth, X0, Y0 + depth, "F"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    return row(
        jurisdiction="clackamas_unincorporated", zone="R7", TLID="22E00AA00100",
        edges_json=json.dumps(edges), front_bearings_json="[0.0, 180.0]",
        frontage_ft=2 * width, lot_width_ft=width, lot_depth_ft=depth, area_sqft=width * depth,
        street_kind_json=None if kinds is None else json.dumps(kinds),
        wkb=shapely.to_wkb(shapely.box(X0 + 5, Y0 + 15, X0 + width - 5, Y0 + depth - 15)),
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + width, Y0 + depth)),
    )


@pytest.mark.parametrize(
    ("width", "kinds", "held"),
    [
        # The court behind faces the far street, a front by ZDO 202: 68 ft of
        # 140 ft is within half, of 130 ft is not.
        (140.0, ["street", None, "street", None], False),
        (130.0, ["street", None, "street", None], True),
        # Nothing read the streets as public: the hold stays.
        (140.0, None, True),
    ],
)
def test_a_clackamas_through_lot_follows_the_frontage_share(trusted, width, kinds, held) -> None:
    from shapely.geometry import Polygon

    from flats.fit.draw import court_between
    from flats.ingest.quadfit import court_yard_lines, lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_quadfit_bridge import pod

    rules = trusted
    (s,) = screen_lot(
        lot_from_row(_through(width, kinds), rules.layers), [pod()], rules=rules,
        policy=slack.load_policy(), relief=relief.load_policy(), step_deg=30.0,
    )
    drawing = s.drawing or {}
    if not (drawing.get("fits") and drawing.get("court")):
        pytest.skip("the through lot draws no fitting plan")
    building, court = Polygon(drawing["building"]), Polygon(drawing["court"])
    if not court_between(building, court, court_yard_lines(s)):
        pytest.skip("the court was drawn clear of both fronts")
    assert court_in_front_yard(s) is held
    assert s.facts.court_front_yard is held
    assert any(f.code == "PARKING-COURT-FRONT-YARD" for f in s.screening.flags) is held
