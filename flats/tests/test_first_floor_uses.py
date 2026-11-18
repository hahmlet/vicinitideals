"""Gresham's required first-floor uses, GDC 4.1121(A) (FOLLOWUPS 203).

The code names four stretches in words -- the north side of E Powell between
NW Miller and NE Roberts, N Main between E Powell and NE 4th, NE 3rd between
N Main and NE Hood, and the north side of NE 3rd between NE Hood and NE Kelly
-- where 75 percent of a building's ground floor within 40 ft of the
right-of-way must be in Commercial or Civic use. The pod is four homes, so a
Downtown lot on one of them is never GREEN: YELLOW with GROUND-FLOOR-USE
(how much of the pod stands within 40 ft is not measured).
"""

from __future__ import annotations

import hashlib
import json

import pytest

pytest.importorskip("shapely")

from shapely.geometry import LineString  # noqa: E402

from flats.geom.first_floor_uses import (  # noqa: E402
    CONDITION,
    SERVES,
    TRACED,
    ZONES,
    FirstFloorUses,
    load_first_floor_uses,
    observed_first_floor_uses,
)
from flats.rules.loader import AREAS_ROOT, load_rules  # noqa: E402
from flats.rules.resolver import RuleSet  # noqa: E402
from flats.score.flags import Colour  # noqa: E402
from flats.score.screen import CLOSER_LOOK_GROUND_FLOOR_USE, Triage  # noqa: E402
from flats.tests.test_screen import run, rules  # noqa: E402

pytestmark = pytest.mark.unit

PROVENANCE = AREAS_ROOT.parents[1] / "provenance" / "docs" / "or" / "multnomah" / "gresham" / "4" / "4.1121.txt"


def _feature(localid: int) -> LineString:
    data = json.loads((AREAS_ROOT / TRACED).read_text(encoding="utf-8"))
    (f,) = [f for f in data["features"] if f["properties"]["rlis_localid"] == localid]
    return LineString(f["geometry"]["coordinates"])


def _beside(line: LineString, side: str, gap: float = 30.0) -> list[object]:
    """A street line ``gap`` ft off ``line`` to one side, as s4 writes it."""
    off = line.parallel_offset(gap, side)
    (x1, y1), (x2, y2) = off.coords[0], off.coords[-1]
    return [x1, y1, x2, y2, "F"]


# --- the typed file ----------------------------------------------------------


def test_the_typed_file_says_what_it_is_drawn_from() -> None:
    data = json.loads((AREAS_ROOT / TRACED).read_text(encoding="utf-8"))
    src = data["source"]
    assert src["quote"] == "or/multnomah/gresham/4/4.1121.txt#L1-L6"
    assert src["text_sha256"] == hashlib.sha256(PROVENANCE.read_bytes()).hexdigest()
    assert src["drawn"] is False
    kinds = [f["properties"]["first_floor"] for f in data["features"]]
    assert {k: kinds.count(k) for k in set(kinds)} == src["counts"] == {"both": 9, "north": 6, "none": 292}
    text = PROVENANCE.read_text(encoding="utf-8")
    for words in ("75 percent", "40 feet", "north side of E Powell", "N Main Avenue", "NE Kelly"):
        assert words in " ".join(text.split())


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError):
        FirstFloorUses.build([LineString([(0, 0), (1, 0)])], ["X"], ["south"])


# --- real lot lines ----------------------------------------------------------


def test_n_main_binds_either_side() -> None:
    traced = load_first_floor_uses()
    for side in ("left", "right"):
        assert traced.answer([_beside(_feature(122744), side)]) is True


def test_e_powell_and_ne_3rd_east_of_hood_bind_their_north_side_only() -> None:
    traced = load_first_floor_uses()
    # Both drawn west to east: left is north.
    for localid in (122894, 122296):
        assert traced.answer([_beside(_feature(localid), "left")]) is True
        assert traced.answer([_beside(_feature(localid), "right")]) is False
    # W Powell, Miller to Main, is drawn east to west: right is north.
    assert traced.answer([_beside(_feature(122963), "right")]) is True
    assert traced.answer([_beside(_feature(122963), "left")]) is False


def test_ne_3rd_west_of_hood_binds_either_side() -> None:
    traced = load_first_floor_uses()
    for side in ("left", "right"):
        assert traced.answer([_beside(_feature(122287), side)]) is True


def test_a_downtown_lot_on_an_ordinary_street_is_answered_false() -> None:
    data = json.loads((AREAS_ROOT / TRACED).read_text(encoding="utf-8"))
    traced = load_first_floor_uses()
    marked = [LineString(f["geometry"]["coordinates"]) for f in data["features"] if f["properties"]["first_floor"] != "none"]
    far = next(
        LineString(f["geometry"]["coordinates"])
        for f in data["features"]
        if f["properties"]["first_floor"] == "none"
        and LineString(f["geometry"]["coordinates"]).length > 200
        and all(LineString(f["geometry"]["coordinates"]).distance(m) > 400 for m in marked)
    )
    assert traced.answer([_beside(far, "left")]) is False


def test_a_street_line_nothing_explains_near_a_marked_stretch_answers_nothing() -> None:
    main = _feature(122744)
    # A street line 100 ft off N Main: beyond the reach, inside the clearance.
    stray = _beside(main, "left", gap=100.0)
    assert load_first_floor_uses().answer([stray]) is None
    assert observed_first_floor_uses([stray], SERVES, "DCC") == {}


def test_only_gresham_downtown_lots_are_asked() -> None:
    edge = [_beside(_feature(122744), "left")]
    assert observed_first_floor_uses(edge, SERVES, "DCC") == {CONDITION: True}
    assert observed_first_floor_uses(edge, SERVES, "CMF") == {}
    assert observed_first_floor_uses(edge, "or/multnomah/portland", "DCC") == {}
    assert observed_first_floor_uses([], SERVES, "DCC") == {}


# --- the rules ---------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize("zone", sorted(ZONES))
def test_the_share_is_asked_only_on_a_named_stretch(corpus: RuleSet, zone: str) -> None:
    off = corpus.resolve(SERVES, zone, ())
    assert off.get("ground_floor_commercial_min_pct") is None
    assert corpus.resolve(SERVES, zone, (CONDITION,)).get("ground_floor_commercial_min_pct") == 75
    # The gate is a lever, so an unanswered fact holds the lot out of GREEN.
    assert CONDITION in off.levers


# --- the screen --------------------------------------------------------------


def test_a_lot_on_a_named_stretch_is_yellow_never_green() -> None:
    plain = run(rules())
    assert plain.colour is Colour.green
    got = run(rules(ground_floor_commercial_min_pct=75))
    assert got.colour is Colour.yellow
    assert got.triage is Triage.yellow
    assert got.binds == ()
    assert CLOSER_LOOK_GROUND_FLOOR_USE in got.reasons
    assert "GROUND-FLOOR-USE" in {f.code for f in got.flags}
