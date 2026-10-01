"""Parking kept out of the required yards (``parking_required_yard_prohibited``).

Cornelius 18.145.010 (B): "Unless otherwise provided, required parking and
loading spaces shall not be located in a required yard", where a parking
space is the stall "together with maneuvering and access space" (18.195).
Steph, 2026-10-01: *"Yes, charge them."*

What the screen did before: the rear court SHARED the rear yard. The ground
behind the building's rear wall was the deeper of the court and the yard
(``max(court, rear)``), so on a lot the court binds the court sat in the
yard. The side yards were already kept clear -- the court and the lane down
the building's flank are searched inside the envelope, which the side
setbacks cut -- and the front is ``parking_street_setback_ft``.

What it does now, where a layer declares the field: the court stands in
front of the yard and the two STACK (``court + rear``). Optional, so a layer
that does not declare it keeps the old bargain, and the guard at the bottom
pins the one layer that does.
"""

from __future__ import annotations

import json

import pytest
import shapely
import yaml

from flats.designs.model import Design
from flats.encode.load import load_trusted
from flats.fit.rectangle import Fitter
from flats.geom.edges import LotEdges, Tier
from flats.geom.envelope import Setbacks, buildable
from flats.ingest.quadfit import lot_edges
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import OPTIONAL_FIELDS, field
from flats.rules.loader import load_rules
from flats.score.paper import Alley, Beside, behind_wall_ft, court_depth, paper_fit, side_column
from flats.score.screen import _beside_beyond, _court_beyond_rear, fit_for

pytestmark = pytest.mark.unit

FIELD = "parking_required_yard_prohibited"
CORNELIUS = "or/washington/cornelius"

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


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


class Rules:
    """A resolution stub: the numbers, and the fields the code exempts."""

    def __init__(self, *exempted: str, **values: object) -> None:
        self.values = values
        self.exempted = exempted

    def get(self, name: str) -> object:
        return self.values.get(name)


class Unbanned:
    """A real resolution with the yard ban taken out: the screen before."""

    def __init__(self, rules) -> None:
        self._rules = rules

    def get(self, name: str) -> object:
        return None if name == FIELD else self._rules.get(name)

    def __getattr__(self, name: str) -> object:
        return getattr(self._rules, name)


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


# --- the rule ------------------------------------------------------------------


def test_the_field_is_optional_and_a_bool() -> None:
    assert FIELD in OPTIONAL_FIELDS
    assert field(FIELD).kind == "bool"


def test_unread_shares_the_yard_and_the_ban_stacks() -> None:
    # A 49 ft court behind a wall that must stand 10 ft off the rear line.
    assert behind_wall_ft(49.0, 10.0, Rules()) == 49.0
    assert behind_wall_ft(49.0, 10.0, Rules(**{FIELD: False})) == 49.0
    assert behind_wall_ft(49.0, 10.0, Rules(**{FIELD: True})) == 59.0
    # A court shallower than the yard sat wholly inside it; banned, it
    # stands in front of it.
    assert behind_wall_ft(5.0, 25.0, Rules()) == 25.0
    assert behind_wall_ft(5.0, 25.0, Rules(**{FIELD: True})) == 30.0
    # Nothing parked behind the wall: the yard alone, either way.
    assert behind_wall_ft(0.0, 25.0, Rules(**{FIELD: True})) == 25.0
    # No yard, nothing to keep clear.
    assert behind_wall_ft(49.0, 0.0, Rules(**{FIELD: True})) == 49.0


def test_the_court_charge_past_the_envelope_stacks_only_under_the_ban() -> None:
    plain = Rules(setback_rear_ft=10, parking_stall_depth_ft=20)
    banned = Rules(setback_rear_ft=10, parking_stall_depth_ft=20, **{FIELD: True})
    court, _ = court_depth(pod(), plain)
    assert court == 49.0
    # The envelope already lost the 10 ft rear strip.
    assert _court_beyond_rear(pod(), plain) == court - 10
    assert _court_beyond_rear(pod(), banned) == court
    # Cut at 0 where the rules ask 10 (a relaxing neighbour line): the wall
    # still stands 10 off and the court in front of it.
    assert _court_beyond_rear(pod(), banned, carved_rear_ft=0.0) == court + 10


def test_a_court_beside_the_building_stacks_what_it_runs_past_the_wall() -> None:
    row = Beside(band_ft=47.0, length_ft=60.0, stalls=6)
    # 60 ft of stalls beside a 56 ft deep building: 4 ft past the rear wall.
    plain = Rules(setback_rear_ft=10)
    banned = Rules(setback_rear_ft=10, **{FIELD: True})
    assert _beside_beyond(row, 56.0, plain) == 0.0
    assert _beside_beyond(row, 56.0, banned) == 4.0
    # A row no longer than the building runs nothing into the yard.
    assert _beside_beyond(row, 60.0, banned) == 0.0


def test_an_alley_is_not_the_aisle_where_the_yards_are_kept_clear() -> None:
    # The stall that backs out into the alley stands in the yard along it,
    # or backs across it: parking in a required yard either way.
    alley = Alley(width_ft=16.0, at_rear=False, at_side=True)
    fed = dict(parking_alley_access_required=True, parking_alley_backout_ft=23)
    assert side_column(pod(), Rules(**fed), alley) is not None
    assert side_column(pod(), Rules(**fed, **{FIELD: True}), alley) is None
    rear = Alley(width_ft=16.0, rear_whole=True)
    shallow, used = court_depth(pod(), Rules(**fed), rear)
    assert "parking_alley_backout_ft" in used
    kept, used = court_depth(pod(), Rules(**fed, **{FIELD: True}), rear)
    assert "parking_alley_backout_ft" not in used
    assert kept > shallow


# --- Cornelius ---------------------------------------------------------------


def test_cornelius_declares_it_on_its_own_sentence() -> None:
    held = load_rules()[CORNELIUS].defaults[FIELD]
    assert held.value is True
    text = " ".join(ProvenanceStore().quote(held.prov.quote).split())
    assert "required parking and loading spaces shall not be located in a required yard" in text


@pytest.mark.parametrize(("zone", "rear"), [("R-7", 10), ("R-10", 25), ("A-2", 15), ("CR", 10)])
def test_the_paper_lot_is_deeper_by_the_rear_yard(corpus, zone: str, rear: float) -> None:
    rules = corpus.resolve(CORNELIUS, zone, ())
    assert rules.get(FIELD) is True
    assert rules.get("setback_rear_ft") == rear
    before = paper_fit(pod(), Unbanned(rules))
    after = paper_fit(pod(), rules)
    assert after.min_depth_ft - before.min_depth_ft == pytest.approx(rear)
    assert FIELD in after.unsigned or FIELD not in rules.untrusted


#: Where Cornelius sits on the Oregon North state plane (EPSG:2913, feet),
#: near enough: a lot drawn there, not a surveyed one. The street is along
#: the south line.
X0, Y0 = 7_548_000.0, 681_000.0


def rectangle(width: float, depth: float) -> tuple[shapely.Polygon, LotEdges]:
    raw = [
        [X0, Y0, X0 + width, Y0, "F"],
        [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
        [X0 + width, Y0 + depth, X0, Y0 + depth, "R"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    got = lot_edges({"edges_json": json.dumps(raw), "front_bearings_json": "[90.0]", "tier": "A"})
    assert got is not None
    edges = LotEdges(Tier.clean, got.edges, got.front_bearings, got.frontage_ft, 1.0)
    return shapely.box(X0, Y0, X0 + width, Y0 + depth), edges


def room(rules, width: float, depth: float) -> tuple[float, int | None]:
    """The screen's fit check on this lot: the depth found less the depth
    the building and its court need past the envelope's rear edge, and the
    stalls the lot seats."""
    lot, edges = rectangle(width, depth)
    yards = Setbacks(
        front_ft=float(rules.get("setback_front_ft")),
        side_ft=float(rules.get("setback_side_ft")),
        rear_ft=float(rules.get("setback_rear_ft")),
    )
    fit = fit_for(Fitter(buildable(lot, edges, yards)), pod(), rules)
    return fit.best_depth_ft - (fit.required_ft + _court_beyond_rear(pod(), rules)), fit.stalls


def test_an_r7_lot_the_court_used_to_fit_by_parking_in_the_rear_yard(corpus) -> None:
    # 70 x 120 in R-7: front 10, sides 5, rear 10, so a 60 x 100 envelope.
    # The pod turned deep (54 ft of stalls across, 56 deep) and its 49 ft
    # court asked 56 + 39 of it while the court used the rear 10: 5 ft to
    # spare, six stalls. Out of the yard it asks 105, and the lot seats none.
    rules = corpus.resolve(CORNELIUS, "R-7", ())
    before, seated = room(Unbanned(rules), 70, 120)
    assert before == pytest.approx(5.0) and seated == 6
    after, seated = room(rules, 70, 120)
    assert after == pytest.approx(-5.0) and seated == 0
    # Ten feet deeper and it clears again.
    after, seated = room(rules, 70, 130)
    assert after == pytest.approx(5.0) and seated == 6


def test_an_r10_lot_loses_the_whole_25_ft_rear_yard(corpus) -> None:
    # 80 x 140 in R-10: front 25, sides 10, rear 25, a 60 x 90 envelope.
    rules = corpus.resolve(CORNELIUS, "R-10", ())
    before, seated = room(Unbanned(rules), 80, 140)
    assert before == pytest.approx(10.0) and seated == 6
    after, seated = room(rules, 80, 140)
    assert after == pytest.approx(-15.0) and seated == 0


# --- the blast radius ------------------------------------------------------------


def test_only_cornelius_keeps_parking_out_of_its_yards() -> None:
    """Steph's ruling was asked of Cornelius (and, on its own branch, Tigard).
    A layer that declares this moves its own lots and no others; adding one
    is a deliberate act, and this list says so."""
    declaring = set()
    for layer_id, layer in load_rules().items():
        if FIELD in layer.defaults:
            declaring.add(layer_id)
        for zone in layer.zones.values():
            if FIELD in zone.values:
                declaring.add(layer_id)
    assert declaring == {CORNELIUS}
