"""What a term means *here* — the measurement, encoded per jurisdiction.

Every dimensional standard is written in terms the city defines: a corner lot
takes a street-side setback instead of an interior one, a front lot line is
where the front setback is measured from, an alley may or may not be frontage
at all. FLATS spent its first months making sure no *number* could be asserted
without a citation, while the *meaning of the measurement the number applies
to* stayed hard-coded in geometry — one global test, applied to nineteen
jurisdictions, uncited.

It is wrong, and provably. Four codes, four incompatible corner lots:

    Portland     "frontage on more than one intersecting street, and where the
                 lot frontages intersect. A street that curves with angles that
                 are 120 degrees or less ... is considered two intersecting
                 streets."                                    33.910
    Gresham      "a lot that has frontage on two or more streets" — no
                 intersection required at all — "also includes a lot abutting
                 the inside curve of a street with a delta angle ... of 60
                 degrees or more."                            3.0100
    Oregon City  "a lot abutting upon two or more streets at their
                 intersection."                               17.04.665
    Rivergrove   "at least two adjacent sides of which abut streets other than
                 alleys, provided the angle of the intersection of the adjacent
                 streets does not exceed 135 degrees."        RLDO

One lot with a street front and back is a corner in Portland and Gresham, and
is not in Oregon City or Rivergrove. Gresham's 60-degree delta and Portland's
120-degree interior angle are the same bend measured from opposite ends;
Rivergrove wants a sharper one than either.

So ``corner_lot`` is a name in *our* vocabulary — the hook a rule hangs a
variant on — and the test that decides it belongs to the municipality. Two
cities can disagree about which lots are corner lots while both are right, and
the encoding has to be able to say so.

The registry is closed for the same reason :mod:`flats.rules.fields` and
:mod:`flats.rules.conditions` are: a test invented inline is a second opinion
nobody can find later. A jurisdiction that has not been read has *no*
definition, which is not the same as the default one — it is a gap, and the
screen says so rather than quietly applying somebody else's code.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Sequence

#: Two lot lines closer than this in direction are one straight run, not a
#: corner. A platted lot line drifts a degree or two off true; a street that
#: actually turns, turns by more.
COLLINEAR_TOL_DEG = 8.0


class Abuts(str, enum.Enum):
    """What is on the other side of a lot line."""

    street = "street"
    alley = "alley"
    #: A private drive or access easement. Not a street in most of these codes
    #: and explicitly one in Wilsonville, whose corner lot test reads "abut a
    #: street or private drive" -- which is why it is its own kind rather than
    #: quietly filed under street.
    private_drive = "private_drive"
    #: Another lot, a tract, water — anything that is not a right-of-way.
    none = "none"


@dataclass(frozen=True, slots=True)
class Side:
    """One boundary segment, before anyone decides what it means.

    Deliberately dumb. Everything a definition needs is here as measurement —
    how long, which way it points, what it abuts — and nothing here has been
    named front, rear or side, because which name it takes is the question the
    definition answers.
    """

    length_ft: float
    #: Direction in [0, 180). A lot line has no front and back.
    bearing_deg: float
    abuts: Abuts = Abuts.none
    #: Street identity where the centreline layer gives one. Two segments of
    #: the same street are one frontage however the boundary was split.
    street_id: str = ""


#: A lot boundary in ring order. Consecutive sides share a vertex; the last
#: shares one with the first.
Boundary = Sequence[Side]


def interior_angle_deg(a: Side, b: Side) -> float:
    """The angle the lot turns through where two sides meet, in (0, 180].

    180 is a straight run — two segments of one line — and anything less is a
    corner of some sharpness. Bearings are direction-free, so this is the
    smaller of the two angles the lines make, expressed the way the codes
    write it: Portland's "120 degrees or less", Rivergrove's "does not exceed
    135 degrees".
    """
    d = abs(a.bearing_deg - b.bearing_deg) % 180.0
    turn = min(d, 180.0 - d)
    return 180.0 - turn


def _frontages(
    boundary: Boundary, *, alleys_count: bool, drives_count: bool = False
) -> set[int]:
    """Indices of the sides that count as street frontage.

    What counts is per-code and not negotiable by us: every code read so far
    says an alley is not frontage, and Wilsonville alone says a private drive
    is. Both are flags on the definition rather than a house rule.
    """
    kinds = {Abuts.street}
    if alleys_count:
        kinds.add(Abuts.alley)
    if drives_count:
        kinds.add(Abuts.private_drive)
    return {i for i, s in enumerate(boundary) if s.abuts in kinds}


def _runs(boundary: Boundary, front: set[int]) -> list[list[int]]:
    """Frontage split into unbroken stretches of boundary.

    Consecutive frontage sides that continue in the same direction are one
    stretch of one street however the surveyor split them. A stretch ends where
    the frontage does — at a side lot line — or where the boundary turns.

    Ring order matters and so does the wrap: a lot whose frontage crosses index
    zero has one stretch, not two.
    """
    n = len(boundary)
    if not front or len(front) == n:
        start = 0
    else:  # begin at a side that opens a stretch, so the wrap cannot split one
        start = next(i for i in range(n) if i in front and (i - 1) % n not in front)
    runs: list[list[int]] = []
    for step in range(n):
        i = (start + step) % n
        if i not in front:
            continue
        prev = (i - 1) % n
        straight = 180.0 - COLLINEAR_TOL_DEG
        if runs and prev in front and interior_angle_deg(boundary[prev], boundary[i]) >= straight:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def _junctions(boundary: Boundary, runs: Sequence[Sequence[int]]) -> list[float]:
    """Interior angles where one stretch of frontage runs into the next.

    Only stretches that actually share a vertex. Two frontages either side of a
    rear lot line meet nowhere, which is exactly the through lot the four codes
    split on — Gresham and Portland admit it and Oregon City and Rivergrove do
    not, and neither reading is reachable without knowing they never touch.
    """
    n = len(boundary)
    out = []
    for run in runs:
        last = run[-1]
        after = (last + 1) % n
        if any(after == other[0] for other in runs if other is not run):
            out.append(interior_angle_deg(boundary[last], boundary[after]))
    return out


def _streets(boundary: Boundary, runs: Sequence[Sequence[int]], p: "Definition") -> int:
    """How many streets those stretches are on.

    Street identity settles it wherever the centreline layer gives one. Where
    it does not, two stretches that meet are the same street unless they meet
    sharply enough for the code to say otherwise: a road that bends gently
    through a lot's frontage is one road, and Portland and Gresham both write
    down the angle at which it stops being one. Stretches that never meet are
    always different streets — that is the through lot.
    """
    named = {boundary[i].street_id for run in runs for i in run if boundary[i].street_id}
    anonymous = [run for run in runs if not boundary[run[0]].street_id]
    junctions = _junctions(boundary, anonymous)
    if p.curve_is_one_street:
        # Clackamas County settles it outright: "A lot within the radius curve
        # of a single street is not a corner lot." However tight the bend, an
        # unnamed stretch that runs into another is the same road.
        merged = len(junctions)
    else:
        bend = p.curve_at_or_below_deg or 180.0 - COLLINEAR_TOL_DEG
        merged = sum(1 for angle in junctions if angle > bend)
    return len(named) + max(len(anonymous) - merged, 0)


# --- the tests a definition may name ----------------------------------

Verdict = Literal[True, False, None]


def _prepare(boundary: Boundary, p: "Definition") -> tuple[int, list[float]]:
    front = _frontages(
        boundary, alleys_count=p.alleys_count, drives_count=p.drives_count
    )
    runs = _runs(boundary, front)
    return _streets(boundary, runs, p), _junctions(boundary, runs)


def _frontage_count(boundary: Boundary, p: "Definition") -> bool:
    """Gresham. Frontage on N or more streets, and nothing about intersecting.

    This is the loosest of the four readings and the only one that makes a
    through lot a corner lot, which follows from the text rather than in spite
    of it: the definition asks for frontage on two streets and says nothing
    about where they go.
    """
    streets, junctions = _prepare(boundary, p)
    if streets >= p.count:
        return True
    # "also includes a lot abutting the inside curve of a street with a delta
    # angle of 60 degrees or more" — one street, bent far enough to count twice.
    return p.curve_at_or_below_deg is not None and any(
        angle <= p.curve_at_or_below_deg for angle in junctions
    )


def _within(angle: float, ceiling: float, p: "Definition") -> bool:
    """Whether a junction angle clears the ceiling this code wrote.

    Rivergrove says the angle "does not exceed 135 degrees" and Multnomah
    County says "less than 135 degrees". At 134 and at 136 they agree; at
    exactly 135 they do not, and encoding both as the same comparison would
    quietly pick one code's answer for the other.
    """
    return angle <= ceiling if p.angle_inclusive else angle < ceiling


def _intersecting(boundary: Boundary, p: "Definition") -> bool:
    """Portland and Oregon City. The frontages have to meet.

    Two streets that never touch are a through lot and not a corner, whatever
    they add up to. The angle only enters where a single curving street is
    being asked to count as two, which is the clause Portland writes as "120
    degrees or less" and Gresham as a 60-degree delta.
    """
    streets, junctions = _prepare(boundary, p)
    straight = 180.0 - COLLINEAR_TOL_DEG
    ceiling = p.max_intersection_angle_deg or straight
    if streets >= p.count and any(_within(a, ceiling, p) for a in junctions):
        return True
    return p.curve_at_or_below_deg is not None and any(
        angle <= p.curve_at_or_below_deg for angle in junctions
    )


def _adjacent(boundary: Boundary, p: "Definition") -> bool:
    """Rivergrove. Two *adjacent sides*, and the angle has a ceiling.

    Adjacency is the whole of the difference from :func:`_intersecting`, and
    the ceiling is the whole of the difference from everyone: a fork that meets
    at 150 degrees is a corner in Portland and is not one here.
    """
    _streets_unused, junctions = _prepare(boundary, p)
    ceiling = p.max_intersection_angle_deg or 180.0 - COLLINEAR_TOL_DEG
    return any(_within(a, ceiling, p) for a in junctions)


#: Every test a ``corner_lot`` definition may name, and nothing else. Adding a
#: reading means adding it here, next to the ones it has to be told apart from.
TESTS = {
    "corner_lot": {
        "frontage_count": _frontage_count,
        "intersecting_frontages": _intersecting,
        "adjacent_frontages": _adjacent,
    }
}

#: Terms a jurisdiction may define. A term absent from a layer is unread, not
#: defaulted — see :func:`decide`.
TERMS: tuple[str, ...] = tuple(TESTS)


@dataclass(frozen=True, slots=True)
class Definition:
    """One municipality's test for one term, and where it is written.

    ``quote`` is not optional and is not decoration. A definition is a rule; a
    rule without a citation is somebody's recollection, and the whole point of
    holding these per jurisdiction is that four cities demonstrably say four
    different things.
    """

    term: str
    test: str
    quote: str
    cite: str = ""
    #: How many streets the term asks for. Every code read so far says two.
    count: int = 2
    #: A single street bent to this interior angle or tighter counts as two
    #: intersecting streets. Portland states 120; Gresham's "delta angle of 60
    #: degrees or more" is the same bend from the other side.
    curve_at_or_below_deg: float | None = None
    #: The widest angle two streets may meet at and still make a corner.
    #: Rivergrove and Multnomah County both state 135 and mean different
    #: things by it -- see :attr:`angle_inclusive`.
    max_intersection_angle_deg: float | None = None
    #: Whether a bend in one street can never make a corner, however tight.
    #: Clackamas County writes it out -- "a lot within the radius curve of a
    #: single street is not a corner lot" -- which is the reverse of Portland
    #: and Gresham, both of which turn a tight enough curve into two streets.
    #: Silence is a third thing again: Oregon City states no angle, so a
    #: non-collinear frontage is read as an intersection.
    curve_is_one_street: bool = False
    #: Whether the stated ceiling is itself allowed. "Does not exceed 135
    #: degrees" includes 135; "less than 135 degrees" does not. One boundary
    #: angle apart, and the two codes that state a ceiling state it both ways.
    angle_inclusive: bool = True
    #: Whether an alley counts as street frontage. Every code that addresses it
    #: says no — Portland's street lot line "does not include lot lines that
    #: abut an alley", Gresham's "lot line abutting an alley is a rear lot
    #: line", Rivergrove's corner test says "streets other than alleys".
    alleys_count: bool = False
    #: Whether a private drive counts as street frontage. Wilsonville is the
    #: only code read so far that says it does -- "each abut a street or
    #: private drive" -- and it matters, because a lot on a private drive is a
    #: corner there and an interior lot everywhere else.
    drives_count: bool = False
    #: Set where the code states a second way to be the term that we cannot
    #: measure. Wilsonville's clause (2) turns on whether an abutting tract
    #: carries a non-vehicular pathway, which no layer we hold records. A
    #: definition marked this way may still answer True; it may never answer
    #: False, because the clause it cannot see could make the answer yes. It
    #: returns unknown instead, and the screen carries that through.
    incomplete: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.term not in TESTS:
            raise ValueError(f"{self.term}: not a definable term — add it to TESTS")
        if self.test not in TESTS[self.term]:
            known = ", ".join(sorted(TESTS[self.term]))
            raise ValueError(f"{self.term}: unknown test {self.test!r} — one of {known}")
        if not self.quote:
            raise ValueError(f"{self.term}: a definition without a quote is a recollection")
        if self.curve_is_one_street and self.curve_at_or_below_deg is not None:
            raise ValueError(
                f"{self.term}: curve_is_one_street contradicts "
                f"curve_at_or_below_deg={self.curve_at_or_below_deg}"
            )
        if self.count < 1:
            raise ValueError(f"{self.term}: count must be at least 1")
        for name in ("curve_at_or_below_deg", "max_intersection_angle_deg"):
            angle = getattr(self, name)
            if angle is not None and not 0.0 < angle <= 180.0:
                raise ValueError(f"{self.term}: {name} must be in (0, 180], got {angle}")

    def holds(self, boundary: Boundary) -> Verdict:
        """Whether this lot answers the term, by this jurisdiction's reading.

        ``None`` where the answer would be no *and* the code states a further
        clause we cannot measure. A no we cannot stand behind is an unknown.
        """
        answer = TESTS[self.term][self.test](boundary, self)
        if answer or not self.incomplete:
            return answer
        return None


def decide(
    definitions: Mapping[str, Definition],
    term: str,
    boundary: Boundary,
) -> Verdict:
    """Answer one term for one lot, or ``None`` where the city is unread.

    ``None`` is the point of the function. A jurisdiction whose definitions
    chapter nobody has opened does not get somebody else's test applied to its
    lots quietly — it gets an unknown, which the configuration stage turns into
    a named gap and the ledger counts. Four cities disagreeing four ways is the
    evidence that a borrowed default is a wrong answer rather than a safe one.
    """
    found = definitions.get(term)
    return None if found is None else found.holds(boundary)


def parse(raw: object, *, where: str, problems: list[str]) -> dict[str, Definition]:
    """Read a layer's ``definitions:`` block, collecting every error.

    Same contract as the rest of the loader: one bad definition does not hide
    the next one.
    """
    out: dict[str, Definition] = {}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        problems.append(f"{where}.definitions: expected a mapping")
        return out
    for term, body in raw.items():
        if not isinstance(body, dict):
            problems.append(f"{where}.definitions.{term}: expected a mapping")
            continue
        try:
            out[str(term)] = Definition(term=str(term), **body)
        except (TypeError, ValueError) as exc:
            problems.append(f"{where}.definitions.{term}: {exc}")
    return out


def unread(layer_id: str, definitions: Mapping[str, Definition]) -> tuple[str, ...]:
    """Terms this jurisdiction has not defined. One gap each."""
    return tuple(term for term in TERMS if term not in definitions)


__all__ = [
    "Abuts",
    "Boundary",
    "COLLINEAR_TOL_DEG",
    "Definition",
    "Side",
    "TERMS",
    "TESTS",
    "decide",
    "interior_angle_deg",
    "parse",
    "unread",
]
