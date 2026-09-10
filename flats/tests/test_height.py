"""The height of the building is a dial, and this is what turning it costs.

Every other test in this suite takes the design as given. This one is about the
one dimension of it nobody has decided yet: the pod stands two storeys, and
whether that is twenty-two feet under a flat roof or thirty-four under a pitched
one is a decision the design meeting has not made. The corpus already knows what
each answer is worth, so the point of :mod:`flats.encode.height` is to ask it
before the decision rather than after.

**The arithmetic is the part that can rot in silence, and this is the guard.**
Eleven setbacks in this corpus were not read off a page -- they were computed
from the design's height when the file was loaded, because Milwaukie and Gresham
draw a plane off the lot line and Portland's IR asks for half the building's
height in every yard. :class:`flats.rules.model.Value` says as much in as many
words: *"the constant it uses is the tallest design rather than a typical one"*.
That is sound encoding and it has a price. Those eleven numbers are true of a
26 ft pod and of nothing else, and until this module existed nothing in the
suite recomputed them, so a design change would have left eleven stale
distances behind and no test would have gone red.

:func:`~flats.encode.height.derived_at` is that arithmetic said once, and
:func:`test_every_derived_setback_reproduces_the_height_it_was_baked_to` runs it
against all eleven at the catalogue's own height. If the loader and the sweep
ever disagree about what a roof plane costs, they disagree here first.

Two conventions are kept from ``test_min_height.py``, for the same reasons:

* the mechanism is tested on bands and values written in this file, never on the
  corpus, so a test cannot go red because Gresham renumbered a table;
* the corpus tests assert only what stays true at any corpus size -- that the
  sweep agrees with the screen at the height they share, that a sampled height
  is always a standard some district actually states, and that no storey
  standard binds on two storeys. No count is pinned except at zero.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("shapely")

from flats.designs.model import load_catalog  # noqa: E402
from flats.encode.height import (  # noqa: E402
    HIGH_FT,
    LOW_FT,
    Band,
    Demand,
    Derived,
    Step,
    _at_height,
    bands,
    cliffs,
    curve,
    demand,
    derived,
    derived_at,
    widest,
)
from flats.rules.fields import DESIGN_HEIGHT_FT  # noqa: E402
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.model import Provenance, Status  # noqa: E402
from flats.rules.resolver import Resolved, RuleSet, Verdict, ZoneResolution  # noqa: E402
from flats.score.paper import paper_fit  # noqa: E402

pytestmark = pytest.mark.unit

WHERE = "or/multnomah/gresham"
PROV = Provenance(
    cite="GRC 7.0420(G)(1)",
    url="https://greshamoregon.gov/development-code/",
    retrieved=date(2026, 8, 12),
)


def plane(
    *,
    base: float,
    at: float,
    rise: float = 1.0,
    encoded: float | None = None,
    field: str = "setback_rear_ft",
    lots: int = 100,
) -> Derived:
    """A step-back written here, in the shape Gresham's rear yard has."""
    return Derived(
        layer=WHERE,
        zone="LDR-7",
        field=field,
        lots=lots,
        encoded_ft=base if encoded is None else encoded,
        base_ft=base,
        at_ft=at,
        rise=rise,
    )


def ratio(
    *,
    per: float,
    floor: float | None = None,
    encoded: float = 13.0,
    field: str = "setback_side_ft",
) -> Derived:
    """A height-proportional yard, in the shape Portland's IR has."""
    return Derived(
        layer="or/multnomah/portland",
        zone="IR",
        field=field,
        lots=100,
        encoded_ft=encoded,
        per_height_ft=per,
        floor_ft=floor,
    )


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------


def test_a_roof_plane_costs_nothing_until_the_building_reaches_it() -> None:
    """A rule that limits a roof does not push a roof that is under the limit.

    Gresham allows twenty-one feet AT the rear setback line. A building of
    twenty-one feet is allowed there, so it stands where Table 4.0130 puts it
    and the plane is not a rule about it at all.
    """
    held = plane(base=15.0, at=21.0)
    assert derived_at(held, 12.0) == 15.0
    assert derived_at(held, 20.9) == 15.0
    assert derived_at(held, 21.0) == 15.0


def test_above_the_plane_the_building_buys_its_height_in_distance() -> None:
    """Five feet over the allowance, at a foot per foot, is five feet back."""
    held = plane(base=15.0, at=21.0)
    assert derived_at(held, 26.0) == 20.0
    assert derived_at(held, 30.0) == 24.0
    assert held.at(40.0) == 34.0


def test_a_shallower_plane_buys_the_same_height_for_less_distance() -> None:
    """``rise`` is feet of HEIGHT per foot of DISTANCE, so it divides.

    Every rise in the corpus today is 1.0, where dividing and multiplying give
    the same answer and a wrong reading would never show. This pins the reading
    that matches the sentence, against the day a city prints 1:2.
    """
    steep = plane(base=15.0, at=21.0, rise=1.0)
    shallow = plane(base=15.0, at=21.0, rise=2.0)
    assert derived_at(steep, 31.0) == 25.0
    assert derived_at(shallow, 31.0) == 20.0


def test_a_ratio_replaces_the_printed_figure_and_its_floor_is_a_maximum() -> None:
    """"1 ft. for every 2 ft. of building height but not less than 10 ft."

    Below twenty feet the printed floor governs and above it the ratio does,
    and which of the two binds is a property of the building rather than of the
    code -- which is exactly why the file keeps both numbers and this does the
    arithmetic.
    """
    held = ratio(per=2.0, floor=10.0)
    assert derived_at(held, 18.0) == 10.0
    assert derived_at(held, 20.0) == 10.0
    assert derived_at(held, 26.0) == 13.0
    assert derived_at(held, 40.0) == 20.0


def test_a_ratio_with_no_printed_floor_is_still_a_rule() -> None:
    held = ratio(per=2.0, floor=None)
    assert derived_at(held, 18.0) == 9.0
    assert derived_at(held, 40.0) == 20.0


def test_a_setback_that_does_not_read_the_height_does_not_move() -> None:
    """The fall-through matters: `_at_height` writes over whatever it is given.

    A plain figure carried into this arithmetic must come out unchanged at
    every height, or recomputing one zone's roof plane would quietly rewrite
    its front yard as well.
    """
    flat = Derived(
        layer=WHERE, zone="LDR-7", field="setback_front_ft", lots=10, encoded_ft=15.0
    )
    assert not flat.plane
    assert [derived_at(flat, h) for h in (LOW_FT, 26.0, HIGH_FT)] == [15.0] * 3


# --------------------------------------------------------------------------
# The band: which heights a zone takes at all
# --------------------------------------------------------------------------


def test_a_ceiling_admits_its_own_figure_and_refuses_the_next_inch() -> None:
    """"Maximum height: 35 feet" permits a 35 foot building. That is the point
    of sampling half a foot past every stated standard rather than stepping."""
    band = Band(layer=WHERE, zone="LDR-7", lots=10, ceiling_ft=35.0)
    assert band.admits(35.0, 2)
    assert not band.admits(35.5, 2)
    assert band.refusals(35.5, 2) == ("max_height_ft",)


def test_a_floor_admits_its_own_figure_and_refuses_the_inch_below() -> None:
    band = Band(layer=WHERE, zone="MU-3", lots=10, floor_ft=25.0)
    assert band.admits(25.0, 2)
    assert not band.admits(24.5, 2)
    assert band.refusals(24.5, 2) == ("min_building_height_ft",)


def test_a_zone_that_states_no_height_standard_is_never_refused_for_height() -> None:
    """Six zones in this corpus state no ceiling at all. A missing standard is
    not a standard of zero, and the sweep must not invent one in either
    direction."""
    band = Band(layer=WHERE, zone="LDR-7", lots=10)
    assert band.refusals(LOW_FT, 1) == ()
    assert band.refusals(HIGH_FT, 40) == ()
    assert band.admits(1000.0, 99)


def test_a_band_names_every_standard_the_building_misses() -> None:
    """Attribution is the whole product here: "which standard" is what a design
    decision is made against, and a band that only said yes or no would leave
    the meeting arguing about feet when the problem was storeys."""
    band = Band(
        layer=WHERE,
        zone="MU-3",
        lots=10,
        ceiling_ft=30.0,
        floor_ft=25.0,
        ceiling_storeys=3,
        floor_storeys=2,
    )
    assert band.refusals(26.0, 2) == ()
    assert band.refusals(31.0, 4) == ("max_height_ft", "max_height_stories")
    assert band.refusals(20.0, 1) == (
        "min_building_height_ft",
        "min_building_height_stories",
    )


# --------------------------------------------------------------------------
# The curve
# --------------------------------------------------------------------------


TWO = [
    Band(layer=WHERE, zone="LOW", lots=1_000, ceiling_ft=30.0),
    Band(layer=WHERE, zone="TALL", lots=25, floor_ft=25.0),
]


def test_a_sampled_height_sits_on_each_side_of_every_stated_standard() -> None:
    """A fixed step misses a ceiling between two samples and spends most of its
    rows saying nothing happened. The heights that matter are the standards
    themselves and the first hair past each one."""
    got = cliffs(TWO)
    assert 30.0 in got and 30.5 in got
    assert 25.0 in got and 24.5 in got
    assert got[0] == LOW_FT and got[-1] == HIGH_FT
    assert got == sorted(got)


def test_a_standard_outside_the_design_range_is_not_sampled() -> None:
    """A 150 ft ceiling is real and cannot bind a two-storey building. Sampling
    it would print rows nobody can act on."""
    tower = [Band(layer=WHERE, zone="CBD", lots=5, ceiling_ft=150.0)]
    assert cliffs(tower) == [LOW_FT, HIGH_FT]


def test_the_curve_separates_too_tall_from_too_short() -> None:
    """Both are refusals and they are opposite arguments: one says build a
    lower roof, the other says build a taller one, and a single 'refused'
    column would net them against each other."""
    at_26 = curve([26.0], TWO)[0]
    assert (at_26.lots, at_26.over_ceiling, at_26.under_floor) == (1_025, 0, 0)

    at_31 = curve([31.0], TWO)[0]
    assert (at_31.lots, at_31.over_ceiling, at_31.under_floor) == (25, 1_000, 0)
    assert at_31.refused == ((WHERE, "LOW", 1_000, "max_height_ft"),)

    at_20 = curve([20.0], TWO)[0]
    assert (at_20.lots, at_20.over_ceiling, at_20.under_floor) == (1_000, 0, 25)
    assert at_20.refused_lots == 25


def test_the_curve_reports_the_biggest_refusal_first() -> None:
    """The sort is the answer to "what does this height cost", and the answer
    is a lot count, not an alphabet."""
    at_31 = curve([31.0], [*TWO, Band(layer=WHERE, zone="MID", lots=9, ceiling_ft=30.0)])[0]
    assert [row[1] for row in at_31.refused] == ["LOW", "MID"]


def test_the_best_band_has_two_walls() -> None:
    """Land is lost at both ends -- too short for a mixed-use floor at the
    bottom, over a ceiling at the top -- so the answer to "how tall" is a band,
    and what a candidate height wants to know is how much room is on each side
    of it."""
    assert widest(curve(None, TWO)) == (25.0, 30.0, 1_025)


def test_the_best_band_is_the_widest_one_and_not_the_first() -> None:
    """Two runs can keep the same land. The one with more room in it is the one
    a design can move inside without re-running this."""
    steps = [
        Step(height_ft=18.0, lots=100, over_ceiling=0, under_floor=0),
        Step(height_ft=20.0, lots=50, over_ceiling=50, under_floor=0),
        Step(height_ft=30.0, lots=100, over_ceiling=0, under_floor=0),
        Step(height_ft=40.0, lots=100, over_ceiling=0, under_floor=0),
    ]
    assert widest(steps) == (30.0, 40.0, 100)


def test_no_heights_sampled_is_no_band_rather_than_a_guess() -> None:
    assert widest([]) is None


# --------------------------------------------------------------------------
# Substitution, and the envelope
# --------------------------------------------------------------------------


def resolution(**values: float) -> ZoneResolution:
    return ZoneResolution(
        jurisdiction=WHERE,
        zone="LDR-7",
        verdict=Verdict.trusted,
        values={
            name: Resolved(
                name=name,
                value=value,
                status=Status.verified,
                prov=PROV,
                layer=WHERE,
                origin="zone",
            )
            for name, value in values.items()
        },
    )


def test_recomputing_a_height_touches_only_the_values_that_read_it() -> None:
    """The substitution is surgical on purpose. Everything else in the zone --
    lot size, coverage, parking, the front yard -- is a number off a page and
    means the same thing whatever this building turns out to be."""
    held = resolution(setback_rear_ft=20.0, setback_front_ft=15.0, min_lot_size_sqft=5_000)
    moved = _at_height(held, 31.0, [plane(base=15.0, at=21.0, encoded=20.0)])
    assert moved.values["setback_rear_ft"].value == 25.0
    assert moved.values["setback_front_ft"].value == 15.0
    assert moved.values["min_lot_size_sqft"].value == 5_000
    assert held.values["setback_rear_ft"].value == 20.0, "the original was mutated"


def test_a_derived_field_the_zone_does_not_hold_is_not_invented() -> None:
    held = resolution(setback_front_ft=15.0)
    moved = _at_height(held, 31.0, [plane(base=15.0, at=21.0)])
    assert "setback_rear_ft" not in moved.values


def a_demand(*, width: float, depth: float, orientation: str, court: float = 0.0,
             setbacks: tuple[tuple[str, float], ...] = ()) -> Demand:
    return Demand(
        layer=WHERE,
        zone="LDR-7",
        lots=100,
        height_ft=26.0,
        min_width_ft=width,
        min_depth_ft=depth,
        orientation=orientation,
        court_ft=court,
        setbacks=setbacks,
    )


def test_the_envelope_survives_an_orientation_flip() -> None:
    """`paper_fit` costs both orientations and reports the cheaper one, so the
    orientation MOVES with the setbacks: a pod that fits broadside under a
    five-foot side yard fits only end-on under an eleven-foot one. Comparing
    the widths across that flip compares two different buildings, and reads as
    a shorter building needing a wider lot. The area is what is comparable."""
    broadside = a_demand(width=86.0, depth=70.0, orientation="width_facing")
    end_on = a_demand(width=70.0, depth=86.0, orientation="depth_facing")
    assert broadside.min_width_ft != end_on.min_width_ft
    assert broadside.envelope_sqft == end_on.envelope_sqft == 6_020.0


def test_an_envelope_is_none_when_either_side_is_unknown() -> None:
    assert a_demand(width=86.0, depth=None, orientation="width_facing").envelope_sqft is None


def test_a_rear_yard_shallower_than_the_parking_court_is_absorbed_by_it() -> None:
    """The rear yard and the court behind the building OVERLAP, and the screen
    takes the greater of the two. So a rear-yard plane that rises with the roof
    costs nothing at all until it is deeper than the court -- which is why six
    Gresham zones move a setback in the sweep and ask for no more land."""
    shallow = a_demand(
        width=86.0, depth=70.0, orientation="width_facing", court=42.0,
        setbacks=(("setback_rear_ft", 24.0),),
    )
    deep = a_demand(
        width=86.0, depth=70.0, orientation="width_facing", court=42.0,
        setbacks=(("setback_rear_ft", 44.0),),
    )
    assert shallow.absorbed == ("setback_rear_ft",)
    assert deep.absorbed == ()


def test_only_the_rear_yard_is_absorbed_by_the_court() -> None:
    """The court sits behind the building. A side yard smaller than it is not
    hidden by it, and reporting one as absorbed would understate the cost."""
    side = a_demand(
        width=86.0, depth=70.0, orientation="width_facing", court=42.0,
        setbacks=(("setback_side_ft", 11.0),),
    )
    assert side.absorbed == ()


# --------------------------------------------------------------------------
# The corpus
# --------------------------------------------------------------------------


CATALOGUE_FT = load_catalog().latest("pod56x36").height_ft


def test_every_derived_setback_reproduces_the_height_it_was_baked_to() -> None:
    """**The drift guard.** The loader computed these eleven distances from
    :data:`DESIGN_HEIGHT_FT` when the corpus was read; this recomputes them
    from the catalogue's own height. The two must agree, and the day they stop
    agreeing is the day somebody changed the design without recomputing the
    setbacks that were derived from it.
    """
    held = derived()
    assert held, "no height-derived setbacks found -- this test proves nothing"
    for value in held:
        assert value.at(CATALOGUE_FT) == pytest.approx(value.encoded_ft), (
            f"{value.layer} {value.zone} {value.field}: the file holds "
            f"{value.encoded_ft} ft, recomputing at {CATALOGUE_FT} ft gives "
            f"{value.at(CATALOGUE_FT)}"
        )


def test_the_design_height_constant_is_the_height_the_sweep_sweeps_from() -> None:
    """Two places name the pod's height and both feed the same eleven numbers.
    If they part company the drift guard above passes while every derived
    setback is understated."""
    assert CATALOGUE_FT == DESIGN_HEIGHT_FT
    assert LOW_FT <= CATALOGUE_FT <= HIGH_FT


def test_the_sweep_at_the_design_height_agrees_with_the_screen() -> None:
    """End to end, and the strongest thing this file asserts: run the whole
    substitution at the height the corpus was baked to and every zone must ask
    for exactly the lot the live screen already asks for -- same width, same
    depth, same way round."""
    rules = RuleSet(load_rules(strict=False))
    design = load_catalog().latest("pod56x36")
    rows = demand(CATALOGUE_FT, rules)
    assert rows, "no height-coupled zones found -- this test proves nothing"
    for row in rows:
        live = paper_fit(design, rules.resolve(row.layer, row.zone))
        assert (row.min_width_ft, row.min_depth_ft, row.orientation) == (
            live.min_width_ft,
            live.min_depth_ft,
            live.orientation,
        ), f"{row.layer} {row.zone} moved at its own height"


def test_no_storey_standard_binds_on_a_two_storey_building() -> None:
    """The sweep prints "storeys are held at 2, so the whole question is feet",
    and that sentence is only true while it is true. A district capping two
    storeys, or requiring three, would make the feet-only reading wrong."""
    for band in bands():
        assert band.refusals(CATALOGUE_FT, 2) == band.refusals(CATALOGUE_FT, 2)
        assert "max_height_stories" not in band.refusals(LOW_FT, 2)
        assert "min_building_height_stories" not in band.refusals(LOW_FT, 2)


def test_every_sampled_height_is_a_standard_some_district_states() -> None:
    """The sweep samples the corpus, not a ruler. Every row it prints must be a
    stated standard, half a foot either side of one, or a bound of the design
    range -- otherwise it is reporting a cliff nobody legislated."""
    held = bands()
    stated = {b.ceiling_ft for b in held if b.ceiling_ft is not None}
    stated |= {b.floor_ft for b in held if b.floor_ft is not None}
    for height in cliffs(held):
        if height in (LOW_FT, HIGH_FT):
            continue
        assert any(abs(height - s) <= 0.5 for s in stated), (
            f"{height} ft is not within half a foot of any stated standard"
        )


def test_a_zone_with_no_ceiling_is_kept_at_every_height_in_the_range() -> None:
    """Six zones state no maximum. They are the floor under the curve: whatever
    the design meeting decides, these lots do not move."""
    open_ended = [b for b in bands() if b.ceiling_ft is None and b.floor_ft is None]
    assert open_ended, "no open-ended zones -- this test proves nothing"
    for height in cliffs():
        kept = {(b.layer, b.zone) for b in open_ended if b.admits(height, 2)}
        assert len(kept) == len(open_ended), f"a zone with no standard moved at {height} ft"
