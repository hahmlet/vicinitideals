"""How tall may this building be, and what does each foot of it cost?

Every other question in this system takes the design as given and asks which
lots it fits. This one runs backwards. The pod's height is not a measurement
yet -- it is a decision nobody has made, bounded below by two floors under a
flat roof with a drainage slope and above by two floors under a pitched one --
and the point of asking the corpus is to find out what the decision is worth
before it is made. If twenty-two feet keeps land that twenty-three loses, that
is a number the design meeting should have.

**Height enters this corpus in two completely different ways**, and only one of
them is a cliff.

*The direct way* is `max_height_ft` and `min_building_height_ft`: a ceiling
refuses a building for being too tall and a floor refuses it for being too
short. These are step functions. A zone is in or out, every lot in it moves
together, and the whole cost of a foot is concentrated at the height where a
ceiling is crossed.

*The indirect way* is a setback that is computed FROM the height, and it is
continuous. Milwaukie and Gresham both draw a plane off the lot line -- so many
feet of height bought with so many feet of distance -- and Portland's IR sets
every yard at half the building's height. A taller building on those lots does
not become illegal; it needs a bigger lot. That is the softer cost, it applies
to about thirty thousand lots, and it is invisible to anything that only reads
`max_height_ft`.

**The eleven values in the second group are baked to the catalogue's current
height.** :class:`flats.rules.model.Value` says so in as many words -- *"the
constant it uses is the tallest design rather than a typical one"* -- and
that is sound encoding, because a lot is checked against one distance and the
file should not make the screen do arithmetic. It also means those eleven
numbers are only true of a 26 ft pod. Change the design and they are wrong, and
nothing in the suite would have noticed until this module existed:
:func:`derived_at` is the arithmetic, and ``test_height.py`` runs it against
every one of them at the catalogue's own height so the two can never drift
apart in silence.

What this does not do is turn a setback into a lot count. That needs each
parcel's width and depth and this repository holds lots aggregated by zone, so
the second panel reports what the LOT must be at each height and how many lots
are exposed to the change, which is the honest half of the answer. The first
panel is exact.

Run it::

    python -m flats.encode.height
    python -m flats.encode.height --at 22 --at 26 --at 30 --at 34
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from flats.designs.model import Design, load_catalog
from flats.rules.ledger import read_coverage
from flats.rules.loader import load_rules
from flats.rules.resolver import Resolved, RuleSet, ZoneResolution
from flats.score.paper import paper_fit

#: The design range the height decision is actually being made inside: two
#: storeys under a flat roof with a drainage slope at the bottom, two storeys
#: under a pitched roof at the top. Wider than either bound on purpose -- a
#: sweep that stops where somebody expects the answer to be cannot show them
#: the cliff just past it.
LOW_FT = 18.0
HIGH_FT = 40.0


@dataclass(frozen=True, slots=True)
class Derived:
    """A setback this corpus computed from the height of the building.

    Two forms, and they are different rules rather than two spellings of one.
    A STEP-BACK adds to the district's own printed setback once the building
    passes a stated height -- Gresham's rear yard is Table 4.0130's figure
    until twenty-one feet and grows a foot per foot after it. A RATIO replaces
    the printed figure entirely: Portland IR asks for half the building's
    height in every yard, with a printed floor under it.
    """

    layer: str
    zone: str
    field: str
    lots: int
    #: What the file holds today, at the catalogue's height.
    encoded_ft: float
    #: The district table's own figure, before any plane was added to it.
    base_ft: float | None = None
    #: The height at which the plane starts. Step-backs only.
    at_ft: float | None = None
    #: Feet of height gained per foot of additional distance.
    rise: float | None = None
    #: The divisor, where the yard is a ratio of the height instead.
    per_height_ft: float | None = None
    #: A printed floor under a ratio: "but not less than ten feet".
    floor_ft: float | None = None

    @property
    def plane(self) -> bool:
        return self.at_ft is not None

    def at(self, height_ft: float) -> float:
        return derived_at(self, height_ft)


def derived_at(value: Derived, height_ft: float) -> float:
    """What a height-derived setback comes to for a building this tall.

    The step-back arithmetic is the sentence read literally: ``rise`` is
    documented as *feet of height gained per foot of additional distance*, so
    the distance bought is the height above the plane DIVIDED by it. Every
    rise in the corpus today is 1.0, where dividing and multiplying agree, and
    the day one is not this is the reading that matches the words.
    """
    if value.plane:
        assert value.at_ft is not None
        base = value.base_ft or 0.0
        if height_ft <= value.at_ft:
            return base
        rise = value.rise or 1.0
        return base + (height_ft - value.at_ft) / rise
    if value.per_height_ft:
        return max(value.floor_ft or 0.0, height_ft / value.per_height_ft)
    return value.encoded_ft


@dataclass(frozen=True, slots=True)
class Band:
    """The heights at which one zone will take this building at all."""

    layer: str
    zone: str
    lots: int
    ceiling_ft: float | None = None
    floor_ft: float | None = None
    ceiling_storeys: float | None = None
    floor_storeys: float | None = None

    def admits(self, height_ft: float, storeys: float) -> bool:
        return not self.refusals(height_ft, storeys)

    def refusals(self, height_ft: float, storeys: float) -> tuple[str, ...]:
        """Which of the four height standards this building misses here."""
        missed = []
        if self.ceiling_ft is not None and height_ft > self.ceiling_ft:
            missed.append("max_height_ft")
        if self.floor_ft is not None and height_ft < self.floor_ft:
            missed.append("min_building_height_ft")
        if self.ceiling_storeys is not None and storeys > self.ceiling_storeys:
            missed.append("max_height_stories")
        if self.floor_storeys is not None and storeys < self.floor_storeys:
            missed.append("min_building_height_stories")
        return tuple(missed)


@dataclass(frozen=True, slots=True)
class Step:
    """One height, and what the corpus says about a building that tall."""

    height_ft: float
    #: Lots in zones that take the building at this height.
    lots: int
    #: Lots refused for being too tall, and for being too short.
    over_ceiling: int
    under_floor: int
    #: The zones that refuse it here, worst first.
    refused: tuple[tuple[str, str, int, str], ...] = ()

    @property
    def refused_lots(self) -> int:
        return self.over_ceiling + self.under_floor


def _lots() -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = defaultdict(int)
    for row in read_coverage() or []:
        out[(row.jurisdiction, row.zone)] += row.lots
    return dict(out)


def _permits(zone) -> bool:
    held = zone.values.get("quadplex_allowed")
    return held is not None and held.value is True


def _figure(zone, name: str) -> float | None:
    held = zone.values.get(name)
    return None if held is None or held.value is None else float(held.value)


def bands(layers=None) -> list[Band]:
    """One band per zone that permits this building, in every live layer."""
    layers = load_rules(strict=False) if layers is None else layers
    lots = _lots()
    out: list[Band] = []
    for name, layer in sorted(layers.items()):
        if not getattr(layer, "eligible", True):
            continue
        for code, zone in sorted(layer.zones.items()):
            if not _permits(zone):
                continue
            out.append(
                Band(
                    layer=name,
                    zone=code,
                    lots=lots.get((name, code), 0),
                    ceiling_ft=_figure(zone, "max_height_ft"),
                    floor_ft=_figure(zone, "min_building_height_ft"),
                    ceiling_storeys=_figure(zone, "max_height_stories"),
                    floor_storeys=_figure(zone, "min_building_height_stories"),
                )
            )
    return out


def derived(layers=None) -> list[Derived]:
    """Every setback in the corpus that was computed from the design's height."""
    layers = load_rules(strict=False) if layers is None else layers
    lots = _lots()
    out: list[Derived] = []
    for name, layer in sorted(layers.items()):
        if not getattr(layer, "eligible", True):
            continue
        for code, zone in sorted(layer.zones.items()):
            if not _permits(zone):
                continue
            for field, value in sorted(zone.values.items()):
                at = getattr(value, "step_back_at_ft", None)
                per = getattr(value, "per_height_ft", None)
                if at is None and per is None:
                    continue
                out.append(
                    Derived(
                        layer=name,
                        zone=code,
                        field=field,
                        lots=lots.get((name, code), 0),
                        encoded_ft=float(value.value),
                        base_ft=(
                            None
                            if value.before_step_back is None
                            else float(value.before_step_back)
                        ),
                        at_ft=None if at is None else float(at),
                        rise=(
                            None
                            if getattr(value, "step_back_rise", None) is None
                            else float(value.step_back_rise)
                        ),
                        per_height_ft=None if per is None else float(per),
                        floor_ft=(
                            None
                            if getattr(value, "floor_ft", None) is None
                            else float(value.floor_ft)
                        ),
                    )
                )
    return out


def cliffs(held: Sequence[Band] | None = None) -> list[float]:
    """Every height at which the answer changes, and nothing in between.

    A sweep at a fixed step misses a ceiling that sits between two of its
    samples and spends most of its rows saying nothing happened. The heights
    that matter are the stated standards themselves and the first hair above
    each ceiling, because a ceiling admits its own figure and refuses anything
    over it.
    """
    held = bands() if held is None else held
    edges = {LOW_FT, HIGH_FT}
    for band in held:
        if band.ceiling_ft is not None and LOW_FT <= band.ceiling_ft <= HIGH_FT:
            edges |= {band.ceiling_ft, band.ceiling_ft + 0.5}
        if band.floor_ft is not None and LOW_FT <= band.floor_ft <= HIGH_FT:
            edges |= {band.floor_ft, band.floor_ft - 0.5}
    return sorted(e for e in edges if LOW_FT <= e <= HIGH_FT)


def curve(
    heights: Iterable[float] | None = None,
    held: Sequence[Band] | None = None,
    storeys: float = 2,
) -> list[Step]:
    """What each candidate height admits and what it refuses."""
    held = bands() if held is None else held
    steps: list[Step] = []
    for height in heights if heights is not None else cliffs(held):
        over = under = keep = 0
        refused: list[tuple[str, str, int, str]] = []
        for band in held:
            missed = band.refusals(height, storeys)
            if not missed:
                keep += band.lots
                continue
            refused.append((band.layer, band.zone, band.lots, ", ".join(missed)))
            if "max_height_ft" in missed or "max_height_stories" in missed:
                over += band.lots
            else:
                under += band.lots
        refused.sort(key=lambda r: -r[2])
        steps.append(
            Step(
                height_ft=height,
                lots=keep,
                over_ceiling=over,
                under_floor=under,
                refused=tuple(refused),
            )
        )
    return steps


def widest(steps: Sequence[Step]) -> tuple[float, float, int] | None:
    """The longest run of sampled heights that keeps the most land.

    This is the sentence the design meeting actually needs, and it is not the
    same as "the lowest ceiling in the corpus". Land is lost at BOTH ends --
    four mixed-use districts refuse a building under twenty-five feet and the
    first ceiling refuses one over thirty -- so the answer is a band with two
    walls, and the useful thing to know about a candidate height is how much
    room it leaves on each side of itself.

    Widest, not first: two runs can keep the same land, and the one with more
    room in it is the one a design can move inside without re-running this.
    """
    if not steps:
        return None
    most = max(step.lots for step in steps)
    best: tuple[float, float, int] | None = None
    run: list[Step] = []
    for step in [*steps, None]:
        if step is not None and step.lots == most:
            run.append(step)
            continue
        if run:
            lo, hi = run[0].height_ft, run[-1].height_ft
            if best is None or (hi - lo) > (best[1] - best[0]):
                best = (lo, hi, most)
            run = []
    return best


def _at_height(rules: ZoneResolution, height_ft: float, held: Sequence[Derived]) -> ZoneResolution:
    """The same zone with its height-derived setbacks recomputed."""
    values = dict(rules.values)
    for value in held:
        current = values.get(value.field)
        if current is not None:
            values[value.field] = replace(current, value=value.at(height_ft))
    return replace(rules, values=values)


@dataclass(frozen=True, slots=True)
class Demand:
    """What a lot in one zone has to be, for a building of one height."""

    layer: str
    zone: str
    lots: int
    height_ft: float
    min_width_ft: float | None
    min_depth_ft: float | None
    #: Which way round the building was costed. Carried because it MOVES with
    #: height and moving it swaps width for depth: a pod that fits broadside
    #: under a five-foot side yard fits only end-on under an eleven-foot one,
    #: and comparing the two widths across that flip compares two different
    #: buildings. The envelope is what survives it.
    orientation: str
    #: What the parking court behind the building takes, which is why a rising
    #: rear setback can cost nothing at all: the two overlap, and until the
    #: setback is deeper than the court the court is still what governs.
    court_ft: float
    setbacks: tuple[tuple[str, float], ...]

    @property
    def envelope_sqft(self) -> float | None:
        if self.min_width_ft is None or self.min_depth_ft is None:
            return None
        return self.min_width_ft * self.min_depth_ft

    @property
    def absorbed(self) -> tuple[str, ...]:
        """Height-derived setbacks the court is still deeper than."""
        return tuple(
            name
            for name, value in self.setbacks
            if name == "setback_rear_ft" and value <= self.court_ft
        )


def demand(height_ft: float, rules: RuleSet | None = None) -> list[Demand]:
    """The lot each height-coupled zone asks for, at this building height."""
    layers = load_rules(strict=False)
    rules = RuleSet(layers) if rules is None else rules
    design = load_catalog().latest("pod56x36")
    tall: Design = design.model_copy(update={"height_ft": height_ft})

    by_zone: dict[tuple[str, str], list[Derived]] = defaultdict(list)
    for value in derived(layers):
        by_zone[(value.layer, value.zone)].append(value)

    out: list[Demand] = []
    for (layer, zone), held in sorted(by_zone.items()):
        resolved = rules.resolve(layer, zone)
        fit = paper_fit(tall, _at_height(resolved, height_ft, held))
        out.append(
            Demand(
                layer=layer,
                zone=zone,
                lots=held[0].lots,
                height_ft=height_ft,
                min_width_ft=fit.min_width_ft,
                min_depth_ft=fit.min_depth_ft,
                orientation=fit.orientation,
                court_ft=fit.parking_depth_ft,
                setbacks=tuple((v.field, v.at(height_ft)) for v in held),
            )
        )
    return out


def _ft(x: float) -> str:
    return f"{x:g}"


def render(at: Sequence[float] | None = None) -> str:
    """The two panels: what height refuses, and what height costs."""
    held = bands()
    total = sum(b.lots for b in held)
    lines = [
        f"{len(held)} zones permit this building, {total:,} lots.",
        "Storeys are held at 2, which every storey standard in the corpus "
        "admits, so the whole question is feet.",
        "",
        "=== WHAT A HEIGHT REFUSES OUTRIGHT ===",
        f"{'height':>8}  {'lots kept':>10}  {'too tall':>10}  {'too short':>10}   binding",
    ]
    previous: Step | None = None
    steps = curve(at, held)
    for step in steps:
        binding = ""
        if step.refused:
            first = step.refused[0]
            binding = f"{first[0].split('/')[-1]} {first[1]} ({first[3]})"
            if len(step.refused) > 1:
                binding += f" +{len(step.refused) - 1} more"
        moved = "" if previous is None or previous.lots == step.lots else "  <-- cliff"
        lines.append(
            f"{_ft(step.height_ft):>8}  {step.lots:>10,}  {step.over_ceiling:>10,}"
            f"  {step.under_floor:>10,}   {binding}{moved}"
        )
        previous = step

    catalogue = load_catalog().latest("pod56x36").height_ft
    band = widest(steps)
    if band is not None:
        lo, hi, most = band
        lines += [
            "",
            f"The most land any height keeps is {most:,} lots, and every "
            f"height from {_ft(lo)} to {_ft(hi)} ft keeps it.",
        ]
        if lo <= catalogue <= hi:
            lines.append(
                f"The catalogue's {_ft(catalogue)} ft is inside that band: "
                f"{_ft(hi - catalogue)} ft of headroom over it and "
                f"{_ft(catalogue - lo)} ft under."
            )
        else:
            lines.append(
                f"The catalogue's {_ft(catalogue)} ft is OUTSIDE that band."
            )

    exposed = sum({(d.layer, d.zone): d.lots for d in derived()}.values())
    lines += [
        "",
        "=== WHAT A HEIGHT COSTS IN LOT SIZE ===",
        f"Setbacks the corpus derives FROM the height, over {exposed:,} lots. "
        "These refuse nobody; they ask for a bigger lot.",
        "The envelope is width x depth, and it is what to compare -- the "
        "orientation flips with the side yard,",
        "and across a flip the width and the depth trade places.",
        "",
    ]
    picks = list(at) if at else [LOW_FT, 21.0, catalogue, 30.0, HIGH_FT]
    base = {(d.layer, d.zone): d for d in demand(catalogue)}
    for height in picks:
        lines.append(f"  at {_ft(height)} ft:")
        for row in demand(height):
            was = base.get((row.layer, row.zone))
            area = row.envelope_sqft
            delta = ""
            if was is not None and area is not None and was.envelope_sqft:
                moved = area - was.envelope_sqft
                if abs(moved) >= 1:
                    delta = f"  {moved:+,.0f} sqft vs {_ft(catalogue)} ft"
                if was.orientation and row.orientation != was.orientation:
                    delta += f"  [turned {row.orientation}]"
            yards = ", ".join(
                f"{f.removeprefix('setback_').removesuffix('_ft')} {v:g}"
                for f, v in row.setbacks
            )
            note = "  (rear absorbed by court)" if row.absorbed else ""
            lines.append(
                f"    {row.layer.split('/')[-1]:<14} {row.zone:<9} {row.lots:>7,} lots  "
                f"{_ft(row.min_width_ft or 0):>5} x {_ft(row.min_depth_ft or 0):<6} "
                f"= {area or 0:>7,.0f} sqft  [{yards}]{note}{delta}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--at",
        type=float,
        action="append",
        help="a height in feet to report; repeatable. Default is every height "
        "at which the answer changes.",
    )
    args = parser.parse_args()
    print(render(args.at))


if __name__ == "__main__":
    main()
