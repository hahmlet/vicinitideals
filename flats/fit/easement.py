"""A utility easement nobody maps, read as a yard on every street line
(FOLLOWUPS 43, Steph 2026-10-01).

Beaverton prints "In no case shall a building encroach into a Public
Utility Easement (PUE)" under its residential tables (BDC 20.05 and 20.22
note 7), Oregon City "Public utility easements may supersede the minimum
setback" under its own, and no county publishes where the easements run. The footnote is
held on the site fact ``utility_easement`` (:mod:`flats.rules.conditions`),
which nothing observes, so every lot it reaches waits on it and stays out
of GREEN.

Steph's ruling stands in for the map: the building fits with a 10 ft yard
on every street line -> the question is answered; it fits only at 5 ft ->
yellow; not even at 5 ft -> red (Beaverton 2026-10-01, Oregon City
2026-10-05). ``flats/config/easements.yaml`` holds the numbers per city. This module holds the ruling and the two pure steps the
bridge takes with it -- the floor on the street yards (:func:`floored`) and
which of the three screenings answers the lot (:func:`pick`); the
screenings themselves are :func:`flats.ingest.quadfit.easement_checked`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

from flats.geom.envelope import Setbacks

#: The site fact the ruling answers.
FACT = "utility_easement"

#: Steph's ruling (HUMAN-OWNED).
RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "easements.yaml"

#: The yards a street line is cut with: the front (a street side the code
#: does not tell apart takes it), the street side, and Portland's two
#: refinements of a street line off a corridor. Never a side, rear or alley
#: line (Steph: "just the side on a street").
STREET_YARDS = ("front_ft", "street_side_ft", "street_off_corridor_ft", "street_clear_ft")


@dataclass(frozen=True, slots=True)
class EasementRule:
    """One city's reading: the street yard that answers the question, and
    the narrower one that leaves it open rather than red."""

    green_ft: float
    yellow_ft: float
    ruled: str = ""

    def __post_init__(self) -> None:
        if not 0 < self.yellow_ft <= self.green_ft:
            raise ValueError(f"need 0 < yellow_ft <= green_ft, got {self.yellow_ft}, {self.green_ft}")


@lru_cache(maxsize=1)
def rules(path: Path = RULES_PATH) -> dict[str, EasementRule]:
    """``easements.yaml``'s ``utility_easement`` block, by layer id."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = raw.get("utility_easement") or {}
    return {layer: EasementRule(**spec) for layer, spec in block.items()}


def rule_for(layer_id: str | None) -> EasementRule | None:
    """The ruling for a layer, or None where Steph made none."""
    return rules().get(layer_id) if layer_id else None


def floored(setbacks: Setbacks, street_ft: float | None) -> Setbacks:
    """``setbacks`` with every street yard at least ``street_ft``.

    A street-side yard the code does not tell apart stays None -- it takes
    the front number, which is floored. Side, rear and alley yards are left
    alone. ``street_ft`` None or 0 is no easement: ``setbacks`` unchanged.
    """
    if not street_ft:
        return setbacks
    changed = {
        name: max(float(value), street_ft)
        for name in STREET_YARDS
        if (value := getattr(setbacks, name)) is not None
    }
    return dataclasses.replace(setbacks, **changed)


Pick = Literal["as_is", "green", "yellow"]


def pick(
    *, as_is_missed: bool, green_missed: bool, green_measured: bool, yellow_missed: bool = True
) -> Pick:
    """Which screening answers one design (Steph 2026-10-01).

    ``green`` where the building fits with the green street yard: the
    question is answered. ``yellow`` where it fits only at the yellow yard,
    the question still open. Where it fits at neither, ``as_is`` -- the lot
    as the code's own yards cut it, the question left open -- where that fit
    misses too (the easement is not why the lot fails), and otherwise
    ``yellow``, its miss the answer (red). ``as_is`` too where the green-yard
    plan could not be cut from the lot's own lines (``green_measured``
    False: quadfit's envelope, which no floor reaches).

    The green yard is asked even where the as-is fit missed: on a corner lot
    the open question ranks the front where the building fits below a front
    where it misses but a variance might be granted, so the as-is miss can
    be the front the question chose rather than the lot.
    """
    if not green_measured:
        return "as_is"
    if not green_missed:
        return "green"
    if not yellow_missed:
        return "yellow"
    return "as_is" if as_is_missed else "yellow"
