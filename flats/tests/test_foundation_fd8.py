"""FD8 (FOLLOWUPS 213): precast steps, the six-step cap, real doors, section 2d.

The answer keys are Factory-Sim ``docs/research/FD8-reply-to-flats-foundation-run.md``
(v3) section 3:

* "the same test lots under Steph's decisions" -- the precast rule and cap of
  section 2a with the real doors, every unit riser count at every door, both
  methods' costs to the dollar, B's railing sides and the outcome
  (:func:`flats.tests.foundation_key.fd8_table`);
* ``FD6_foundation_model.py --as-flats-built`` -- the framing size on FLATS's
  settings before FD8 (:func:`flats.tests.foundation_key.as_flats_built`).

Then the rules one by one: which face takes the front doors (Steph 2026-11-20),
the near-cap band, red only when every open method fails, the precast price
table, railing sides, the stair's own ground and the guard box, the stepped
footing, the stops and the steep-ground flag. None of it needs a data file.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import shapely

from flats.foundation import cap as caps
from flats.foundation import cost as costing
from flats.foundation import doors, lot, measure, model, settings, support
from flats.foundation import ground as grounds
from flats.foundation.frame import frame
from flats.tests.foundation_key import as_flats_built, fd8_table

PROD = settings.load()
T = fd8_table()


def _d(v: Decimal) -> int:
    return costing.dollars(v)


# ---------------------------------------------------------------- FD8 section 3, under Steph's decisions

#: lot: (along, across), A units, A low/high or None (over), B units, B low/high or None, B railing sides, outcome
FD8_TABLE = {
    "flat": ((0, 0), (0, 0, 0, 0, 0, 0, 0, 0), (16798, 28379), (4, 4, 4, 4, 4, 4, 4, 4), (29095, 40207), 8, "both fit"),
    "1 ft along": ((1, 0), (1, 1, 1, 2, 1, 1, 1, 2), (24514, 37538), (4, 5, 5, 5, 4, 5, 5, 6), (33699, 45351), 14, "both fit"),
    "2 ft along": ((2, 0), (1, 2, 2, 4, 1, 2, 2, 4), (29492, 44279), (4, 5, 6, 7, 4, 5, 6, 7), None, None, "slab only"),
    "2 ft across": ((0, 2), (0, 0, 0, 0, 4, 4, 4, 4), (28348, 43295), (4, 4, 4, 4, 7, 7, 7, 7), None, None, "slab only"),
    "3 ft along, 1 ft across": ((3, 1), (1, 3, 3, 5, 2, 4, 5, 7), None, (4, 6, 7, 8, 6, 8, 8, 10), None, None, "red"),
    "4 ft along": ((4, 0), (1, 3, 4, 7, 1, 4, 4, 7), None, (4, 7, 8, 10, 4, 7, 7, 10), None, None, "red"),
    "6 ft along": ((6, 0), (1, 5, 6, 10, 1, 5, 6, 10), None, (5, 8, 10, 13, 4, 9, 9, 14), None, None, "red"),
}


def _cost(r: model.MethodResult) -> tuple[int, int] | None:
    return None if r.over_cap else (_d(r.cost.low), _d(r.cost.high))


@pytest.mark.parametrize("name", list(FD8_TABLE))
def test_fd8_section_3_under_stephs_decisions(name: str) -> None:
    (along, across), a_units, a_cost, b_units, b_cost, b_sides, outcome = FD8_TABLE[name]
    g = grounds.plane(T, along, across)
    a, b = model.slab(g, T), model.raised(g, T)
    assert tuple(d.units for d in a.doors) == a_units
    assert tuple(d.units for d in b.doors) == b_units
    assert _cost(a) == a_cost and _cost(b) == b_cost
    if b_sides is not None:
        assert sum(d.rail_sides for d in b.doors) == b_sides
    # the outcome, on ordinary ground (A and B open)
    c = caps.cap_of({"A dry": a, "B": b}, support.ORDINARY, T)
    got = {(): "red", ("A dry",): "slab only", ("A dry", "B"): "both fit"}[c.clear]
    assert got == outcome
    assert (c.state == caps.RED) == (outcome == "red")


# ---------------------------------------------------------------- FD9: the eleven test lots, door by door

#: Factory-Sim ``docs/research/FD6_foundation_model.py`` (FD9 re-issue, no arguments), the
#: shipped settings on a plane over the framing: (along, across, front doors on the far
#: face), then per method (A dry, B) the unit risers, railing sides and door $ of the eight
#: doors (front four then back four, left to right; None = over the cap), the cost
#: (None = over the cap), and the ordinary lot's cap state with the best method's margin.
FD9_LOTS = {
    "flat": ((0, 0, False),
             ((0,) * 8, (0,) * 8, (60,) * 8), (16798, 28379),
             ((4,) * 8, (1,) * 8, (1460,) * 8), (29095, 40207), caps.FITS, -43.5),
    "1 ft along": ((1, 0, False),
                   ((1, 1, 1, 2, 1, 1, 1, 2), (0,) * 8, (614, 614, 614, 769, 614, 614, 614, 769)), (24792, 38007),
                   ((4, 5, 5, 5, 4, 5, 5, 6), (1, 2, 2, 2, 1, 2, 2, 2),
                    (1460, 2054, 2054, 2054, 1460, 2054, 2054, 2292)), (33984, 45834), caps.FITS, -31.9),
    "2 ft along": ((2, 0, False),
                   ((1, 2, 2, 4, 1, 2, 2, 4), (0, 0, 0, 2, 0, 0, 0, 2), (614, 769, 769, 1829, 614, 769, 769, 1829)),
                   (30509, 45486),
                   ((4, 5, 6, 7, 4, 5, 6, 7), (2, 2, 2, 0, 2, 2, 2, 0), (1829, 2054, 2292, None, 1829, 2054, 2292, None)),
                   None, caps.FITS, -20.3),
    "2 ft across": ((0, 2, False),
                    ((0, 0, 0, 0, 5, 5, 5, 5), (0, 0, 0, 0, 2, 2, 2, 2), (60, 60, 60, 60, 2054, 2054, 2054, 2054)),
                    (30811, 45816),
                    ((4, 4, 4, 4, 7, 7, 7, 7), (1, 1, 1, 1, 0, 0, 0, 0), (1460,) * 4 + (None,) * 4),
                    None, caps.FITS, -12.5),
    "1 ft across": ((0, 1, False),
                    ((0, 0, 0, 0, 2, 2, 2, 2), (0,) * 8, (60, 60, 60, 60, 769, 769, 769, 769)), (22696, 35939),
                    ((4, 4, 4, 4, 6, 6, 6, 6), (1, 1, 1, 1, 2, 2, 2, 2), (1460,) * 4 + (2292,) * 4),
                    (33476, 45292), caps.FITS, -29.4),
    "3 ft along, 1 ft across": ((3, 1, False),
                                ((1, 3, 3, 5, 3, 5, 5, 7), (0, 0, 0, 2, 0, 2, 2, 0),
                                 (614, 939, 939, 2054, 939, 2054, 2054, None)), None,
                                ((4, 6, 7, 8, 6, 8, 8, 10), (2, 2, 0, 0, 2, 0, 0, 0),
                                 (1829, 2292, None, None, 2292, None, None, None)), None, caps.RED, 3.4),
    "4 ft along": ((4, 0, False),
                   ((1, 3, 4, 7, 1, 4, 4, 7), (0, 0, 2, 0, 0, 2, 2, 0), (614, 939, 1829, None, 614, 1829, 1829, None)),
                   None,
                   ((4, 7, 8, 10, 4, 7, 7, 10), (2, 0, 0, 0, 2, 0, 0, 0), (1829, None, None, None, 1829, None, None, None)),
                   None, caps.RED, 3.0),
    "6 ft along": ((6, 0, False),
                   ((1, 5, 6, 10, 1, 5, 6, 10), (0, 2, 2, 0, 0, 2, 2, 0),
                    (614, 2054, 2292, None, 614, 2054, 2292, None)), None,
                   ((5, 8, 10, 13, 4, 9, 9, 14), (2, 0, 0, 0, 2, 0, 0, 0), (2054, None, None, None, 1829, None, None, None)),
                   None, caps.RED, 26.2),
    "2 ft 6 in along, 1 ft across": ((2.5, 1, False),
                                     ((1, 2, 3, 4, 3, 5, 5, 7), (0, 0, 0, 2, 0, 2, 2, 0), None), None,
                                     ((4, 6, 6, 8, 6, 8, 8, 10), (2, 2, 2, 0, 2, 0, 0, 0), None), None,
                                     caps.NEAR, 1.5),
    "2 ft 6 in along, 1 ft across, front doors on the far face": (
        (2.5, 1, True),
        ((3, 4, 5, 6, 1, 2, 3, 5), (0, 2, 2, 2, 0, 0, 0, 2), None), (38803, 56671),
        ((6, 7, 8, 9, 4, 6, 6, 8), (2, 0, 0, 0, 2, 2, 2, 0), None), None, caps.CLOSE, -0.2),
    "2 ft 9 in across": ((0, 2.75, False),
                         ((0, 0, 0, 0, 7, 7, 7, 7), (0,) * 8, (60,) * 4 + (None,) * 4), None,
                         ((4, 4, 4, 4, 8, 8, 8, 8), (1, 1, 1, 1, 0, 0, 0, 0), (1460,) * 4 + (None,) * 4), None,
                         caps.NEAR, 0.3),
}


def _left_to_right(doors: tuple[model.DoorResult, ...], far: bool) -> tuple[model.DoorResult, ...]:
    """The key reads each face left to right from the street. FLATS turns the
    whole frame (front doors on the far face, left and right as seen from it),
    so on the turned lot each face's four doors read the other way round; the
    shipped door positions are symmetric about the middle, so they are the
    same doors."""
    return tuple(doors[3::-1] + doors[:3:-1]) if far else doors


@pytest.mark.parametrize("name", list(FD9_LOTS))
def test_fd9_the_eleven_test_lots_door_by_door(name: str) -> None:
    (along, across, far), a_doors, a_cost, b_doors, b_cost, state, margin = FD9_LOTS[name]
    s = PROD.replace(use_frost_register=False)
    # the far face: the frame turned end for end, the plane falling the other way
    g = grounds.plane(s, -along, -across) if far else grounds.plane(s, along, across)
    a, b = model.slab(g, s), model.raised(g, s)
    for r, (units, sides, dollars), cost in ((a, a_doors, a_cost), (b, b_doors, b_cost)):
        ds = _left_to_right(r.doors, far)
        assert tuple(d.units for d in ds) == units
        assert tuple(d.rail_sides for d in ds) == sides
        if dollars is not None:
            got = tuple(None if d.over_cap else _d(costing.unit_door_cost(s, d.units, d.rail_sides)[0]) if d.units
                        else 60 for d in ds)
            assert got == dollars
        assert _cost(r) == cost
    c = caps.cap_of({"A dry": a, "B": b}, support.ORDINARY, s)
    assert c.state == state and c.best == "A dry"
    assert c.over_by_in == pytest.approx(margin, abs=0.05)


def test_fd9_the_platform_stands_on_the_lower_ground() -> None:
    """FD9 section 2: on rising ground the unit stands on the ground at the wall
    (the larger drop), so B's front doors on the "1 ft across" lot are four-riser
    units with one railing side, $1,460 each; measured from the foot they read a
    guard and two sides. The cap does not move."""
    s = PROD.replace(use_frost_register=False)
    b = model.raised(grounds.plane(s, 0, 1), s)
    front = [d for d in b.doors if d.face == "front"]
    assert [(d.units, d.rail_sides, d.guard) for d in front] == [(4, 1, False)] * 4
    assert {_d(costing.unit_door_cost(s, d.units, d.rail_sides)[0]) for d in front} == {1460}
    assert all(d.platform_in == pytest.approx(4 * s.riser_in) for d in front)


def test_fd8_precast_steps_alone() -> None:
    """The steps line of the flat lot: B eight four-riser units with a railing
    each side where the platform needs a guard, else one; A eight step pads."""
    g = grounds.plane(T, 0, 0)
    b, a = model.raised(g, T), model.slab(g, T)
    line = b.cost.line("precast steps and railings")
    assert line.quantity == 8 and line.low == line.high
    expect = sum(costing.unit_door_cost(T, d.units, d.rail_sides)[0] for d in b.doors)
    assert line.low == expect
    assert a.cost.line("step pads").quantity == 8 and a.cost.line("precast steps and railings").quantity == 0


# ---------------------------------------------------------------- --as-flats-built (FD8 section 3)

AS_FLATS_BUILT = {
    "flat": ((0, 0), (16798, 28379), (20409, 37375)),
    "3 ft along, 1 ft across": ((3, 1), (31652, 56984), (26519, 54046)),
    "6 ft along": ((6, 0), (38922, 70686), (30491, 62437)),
}


@pytest.mark.parametrize("name", list(AS_FLATS_BUILT))
def test_as_flats_built_still_reproduces_as_an_override(name: str) -> None:
    s = as_flats_built()
    (along, across), a_cost, b_cost = AS_FLATS_BUILT[name]
    g = grounds.plane(s, along, across)
    a, b = model.slab(g, s), model.raised(g, s)
    assert (_d(a.cost.low), _d(a.cost.high)) == a_cost
    assert (_d(b.cost.low), _d(b.cost.high)) == b_cost
    assert not a.over_cap and not b.over_cap  # the rule before FD8 has no cap


# ---------------------------------------------------------------- the precast rule (FD8 2a)

UNITS = (448, 589, 744, 881, 1025, 1166)
RAILS = (213, 268, 306, 336, 366, 404)


def test_the_precast_price_table_as_fd8_gives_it() -> None:
    assert PROD.precast_markup == pytest.approx(0.10)
    for k, (unit, rail) in enumerate(zip(UNITS, RAILS, strict=True), start=1):
        assert PROD.price(f"precast_unit_{k}").low == PROD.price(f"precast_unit_{k}").high == unit
        assert PROD.price(f"precast_rail_{k}").low == rail
        assert "delivery" in PROD.price(f"precast_unit_{k}").source.lower()
        for sides in (0, 1, 2):
            low, high = costing.unit_door_cost(PROD, k, sides)
            assert low == high == (Decimal(unit) + 110 + sides * Decimal(rail)) * Decimal("1.10")


@pytest.mark.parametrize(
    "h, k",
    [(0.0, 0), (8.0, 0), (8.01, 1), (15.25, 1), (15.26, 2), (44.25, 5), (51.5, 6), (51.51, 7)],
)
def test_unit_risers_round_up_and_ties_are_not_over(h: float, k: int) -> None:
    door = measure.DoorMeasure("front", 10.0, 0.0)
    d = model._unit_door(door, h, PROD.replace(stair_ground=False, guard_box=False))
    assert d.units == k and d.risers == k + 1
    assert d.over_cap == (k > 6)


@pytest.mark.parametrize(
    "h, sides, guard",
    [(8.0, 0, False), (20.0, 0, False), (36.0, 1, False), (37.0, 1, False), (38.01, 2, True), (51.5, 2, True)],
)
def test_railing_sides(h: float, sides: int, guard: bool) -> None:
    """2 with a guard (platform k x 7.25 over 30 in), else 1 at four risers or more, else 0."""
    door = measure.DoorMeasure("front", 10.0, 0.0)
    d = model._unit_door(door, h, PROD.replace(stair_ground=False, guard_box=False))
    assert (d.rail_sides, d.guard) == (sides, guard)


def test_a_platform_exactly_30_in_needs_no_guard() -> None:
    s = PROD.replace(stair_ground=False, guard_box=False, riser_in=7.5)
    d = model._unit_door(measure.DoorMeasure("front", 10.0, 0.0), 8.0 + 4 * 7.5, s)
    assert d.units == 4 and d.platform_in == pytest.approx(30.0) and not d.guard and d.rail_sides == 1


# ---------------------------------------------------------------- the stair's ground and the guard box (FD8 2d)


def test_the_stair_is_tested_where_it_lands() -> None:
    """Ground falling away from the door: the unit's foot stands lower, so it
    needs more risers than the door alone asks."""
    s = PROD.replace(guard_box=False)
    falling = measure.DoorMeasure("front", 10.0, 0.0, out_drops_in=tuple(i * 3.0 for i in range(12)))
    flat = measure.DoorMeasure("front", 10.0, 0.0, out_drops_in=(0.0,) * 12)
    h = 30.0
    on_flat, on_fall = model._unit_door(flat, h, s), model._unit_door(falling, h, s)
    assert on_flat.units == 4 and on_fall.units > on_flat.units
    assert on_fall.cap_height_in > h


def test_the_guard_box_raises_the_platform_over_low_ground_beside_it() -> None:
    s = PROD.replace(stair_ground=False)
    low_beside = measure.DoorMeasure("front", 10.0, 0.0, out_drops_in=(), box_drop_in=12.0)
    d = model._unit_door(low_beside, 30.0, s)
    assert d.units == 4 and d.platform_in == pytest.approx(4 * 7.25 + 12.0) and d.guard and d.rail_sides == 2


# ---------------------------------------------------------------- the cap on a lot


def _method(name: str, over_by: float, s: settings.Settings = PROD) -> model.MethodResult:
    h = s.cap_in + over_by
    k = model.units_at(h, s)
    door = model.DoorResult("front", 10.0, h, k + 1, 0.0, False, False, 0.0, units=k, cap_height_in=h,
                            over_cap=k > s.cap_risers)
    base = model.raised(grounds.plane(s, 0, 0), s)
    return base.__class__(**{**{f: getattr(base, f) for f in base.__dataclass_fields__}, "method": name,
                             "doors": (door,), "over_cap": door.over_cap})


@pytest.mark.parametrize(
    "a_over, b_over, state",
    [
        (-10.0, -5.0, caps.FITS),
        (-10.0, -1.5, caps.FITS),  # the best method decides: A is 10 in under
        (-1.5, 3.0, caps.CLOSE),
        (1.0, 3.0, caps.NEAR),
        (2.0, 9.0, caps.NEAR),
        (2.5, 9.0, caps.RED),
        (-10.0, 3.0, caps.FITS),  # A clears: not red, B is just not used
    ],
)
def test_red_only_when_every_open_method_fails_and_near_cap_is_yellow(a_over: float, b_over: float, state: str) -> None:
    methods = {"A dry": _method("A dry", a_over), "B": _method("B", b_over)}
    c = caps.cap_of(methods, support.ORDINARY, PROD)
    assert c.state == state
    if state == caps.RED:
        assert c.words.startswith("foundation: a door needs more than six steps on every method")
        assert "front door 1" in c.words and f"{a_over:.1f} in over" in c.words
    if state == caps.NEAR:
        assert "front door 1" in c.words and c.colour_moves


def test_piles_ground_is_red_on_b_plus_p_alone() -> None:
    methods = {"A dry": _method("A dry", -20.0), "B+P": _method("B+P", 6.0)}
    assert caps.cap_of(methods, support.PILES, PROD).state == caps.RED


def test_an_unread_ground_class_with_b_over_is_yellow() -> None:
    """Conservative: unsorted ground may need piles, where only B+P is open."""
    methods = {"A dry": _method("A dry", -20.0), "B": _method("B", 6.0)}
    assert caps.cap_of(methods, support.NOT_SORTED, PROD).state == caps.CLASS_UNREAD
    assert caps.cap_of(methods, support.ORDINARY, PROD).state == caps.FITS
    both = {"A dry": _method("A dry", -20.0), "B": _method("B", -10.0)}
    assert caps.cap_of(both, support.NOT_SORTED, PROD).state == caps.FITS


def test_a_lot_result_carries_its_cap_and_skips_methods_over_it() -> None:
    res = lot.run_lot(grounds.plane(T, 2, 0), T, group=support.ORDINARY)
    assert res.cap.state == caps.FITS and res.cap.clear == ("A dry",)
    assert res.cheaper == ()  # B is over the cap: nothing to compare
    assert "over_step_cap" in {i.code for i in res.challenges}
    red = lot.run_lot(grounds.plane(T, 6, 0), T, group=support.ORDINARY)
    assert red.cap.state == caps.RED


# ---------------------------------------------------------------- stepped footing, stops, steep ground


def test_the_stepped_footing_adds_wall_where_a_line_falls_more_than_a_step() -> None:
    g = grounds.plane(PROD, 0, 2)  # 24 in across the 25 ft ends
    on, off = model.raised(g, PROD), model.raised(g, PROD.replace(stepped_footing=False))
    end_on = next(ln for ln in on.lines if ln.name == "left end")
    end_off = next(ln for ln in off.lines if ln.name == "left end")
    assert sum(end_on.walls_in) > sum(end_off.walls_in)
    front_on = next(ln for ln in on.lines if ln.name == "front")
    assert set(front_on.walls_in) == {max(front_on.walls_in)}  # no fall along the front: its tallest wall


def test_b_over_ten_ft_is_engineered_not_priced_and_not_red() -> None:
    b = model.raised(grounds.plane(PROD, 0, 12), PROD)
    assert b.stop is not None and b.stop.startswith("engineered, not priced by this model")
    assert not b.usable


def test_steep_ground_is_a_flag_only() -> None:
    m = measure.measure(grounds.plane(PROD, 0, 12), PROD)  # 1 in about 2 across
    res = lot.assess(m, PROD, group=support.ORDINARY)
    assert lot.STEEP in res.flags
    assert any("slope setback applies: own look" in w for w in res.flag_words)
    flat = lot.assess(measure.measure(grounds.plane(PROD, 0, 0), PROD), PROD, group=support.ORDINARY)
    assert lot.STEEP not in flat.flags


# ---------------------------------------------------------------- which face takes the front doors (Steph 2026-11-20)

#: An 80 x 25 ft building, its long sides along x; the street is the line y = 0.
RING = [(10.0, 20.0), (90.0, 20.0), (90.0, 45.0), (10.0, 45.0), (10.0, 20.0)]
STREETS = ((0.0, 0.0, 100.0, 0.0),)


def _frame():
    return frame(RING, STREETS)


def test_the_street_frame_puts_the_front_on_the_street_side() -> None:
    fr = _frame()
    assert fr.fl[1] == fr.fr[1] == 20.0
    t = fr.turned()
    assert t.fl[1] == t.fr[1] == 45.0 and t.turned() == fr


def test_a_required_entrance_keeps_the_doors_on_the_street() -> None:
    court = [(10, 50), (90, 50), (90, 80), (10, 80), (10, 50)]  # behind the building
    assert doors.choose(_frame(), required=True, court=court) == (False, doors.REQUIRED)


def test_elsewhere_the_front_doors_face_the_parking() -> None:
    behind = [(10, 50), (90, 50), (90, 80), (10, 80), (10, 50)]
    in_front = [(10, 2), (90, 2), (90, 15), (10, 15), (10, 2)]
    assert doors.choose(_frame(), required=False, court=behind) == (True, doors.PARKING)
    assert doors.choose(_frame(), required=False, court=in_front) == (False, doors.PARKING)
    assert doors.choose(_frame(), required=False, lane=behind) == (True, doors.LANE)


def test_with_no_parking_the_front_doors_face_the_more_open_lot() -> None:
    deep_back = shapely.box(0, 0, 100, 120)
    deep_front = shapely.Polygon([(0, -60), (100, -60), (100, 50), (0, 50)])
    assert doors.choose(_frame(), required=False, lot=deep_back) == (True, doors.OPEN_LOT)
    assert doors.choose(_frame(), required=False, lot=deep_front) == (False, doors.OPEN_LOT)
    even = shapely.Polygon([(0, -5), (100, -5), (100, 70), (0, 70)])  # 25 ft in front, 25 ft behind
    assert doors.choose(_frame(), required=False, lot=even) == (False, doors.STREET_DEFAULT)


def test_turning_the_face_swaps_the_door_lists() -> None:
    """y = 0 is always the front-door face: on the turned frame the front
    doors stand on the drawn back side, at the front-door positions."""
    s = PROD
    fr = _frame()
    pts_street = fr.world([s.door_x_front_ft[0]], [0.0], s.length_ft, s.width_ft, s.box_ft)
    pts_turned = fr.turned().world([s.door_x_front_ft[0]], [0.0], s.length_ft, s.width_ft, s.box_ft)
    assert pts_street[0][1] < 30 < pts_turned[0][1]


def test_entrance_required_reads_the_zone() -> None:
    class Z:
        def __init__(self, v):
            self.v = v

        def get(self, name, default=None):
            return self.v if name == "entrance_faces_street" else default

    assert doors.entrance_required(Z("required")) and doors.entrance_required(Z("required_named"))
    assert not doors.entrance_required(Z("required"), entrance_side_fit=(1.0, 2.0))
    assert not doors.entrance_required(Z(None)) and not doors.entrance_required(None)


def test_the_door_face_rides_in_the_record_and_lifts_the_guess_flag() -> None:
    m = measure.measure(grounds.plane(PROD, 0, 0), PROD,
                        inputs={"door_face": "away", "door_face_rule": doors.PARKING, "front_face_turn_deg": 80.0})
    res = lot.assess(m, PROD, group=support.ORDINARY)
    assert lot.FRONT_GUESS not in res.flags and res.notes == (doors.WORDS[doors.PARKING],)
    street = measure.measure(grounds.plane(PROD, 0, 0), PROD,
                             inputs={"door_face": "street", "door_face_rule": doors.STREET_DEFAULT,
                                     "front_face_turn_deg": 80.0})
    assert lot.FRONT_GUESS in lot.assess(street, PROD, group=support.ORDINARY).flags
