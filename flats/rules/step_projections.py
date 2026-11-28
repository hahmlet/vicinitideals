"""How far into a required yard a city lets the precast steps stand
(FOLLOWUPS 214).

The stair-room build (FOLLOWUPS 213) keeps every door's precast unit on the
lot and off the drawn court and lane. A building drawn at the setback line
puts those steps in the yard, and a code lists what may project into a yard:
what it does not list may not. ``flats/config/step_projections.yaml`` holds,
per city and zone, the sentences that name steps, stairs or landings, with
each figure as printed. This module reads them and turns one unit -- its
risers, whether it carries a railing -- into the setbacks its steps have to
keep (:func:`kept`), which the screen cuts the steps' ground with
(:func:`flats.ingest.quadfit.stair_yards_of`). A city, zone or yard the file
does not name lets the steps into none of it: the setback stands whole.

A unit is k risers of ``doors.riser_in``. Where a code measures the stair's
surface the unit is that high. Elsewhere it is read twice -- at its platform,
and, where it carries a railing, as taller than any figure (the railing's top
is not on the vendor page) -- and the reading that keeps more of the yard
stands: a reading that gives the steps room is taken only where every reading
gives it.
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from flats.geom.envelope import Setbacks

PATH = Path(__file__).resolve().parents[1] / "config" / "step_projections.yaml"
#: Where a row's ``cite`` paths live.
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

YARDS = ("front", "street_side", "side", "rear")
ENTIRE = "entire"
#: What a row reads: a sentence naming steps, stairs or landings; one naming
#: an uncovered porch, deck, patio or similar feature (Steph 2026-11-27,
#: rulings.yaml 2026-11-27-steps-count-as-porch); or a code that names none of
#: them as a projection at all (2026-11-27-steps-allowed-where-silent).
STEPS, PORCH, SILENT = "steps", "porch", "silent"
KINDS = (STEPS, PORCH, SILENT)
SURFACE = "surface"

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twelve": 12, "fifteen": 15, "eighteen": 18, "twenty": 20, "twenty-four": 24, "thirty": 30,
    "thirty-six": 36,
}
#: "ten (10) feet": the numeral a code prints after the word says the same.
_PAREN = re.compile(r"\s*\(\s*\d+(?:\.\d+)?\s*[½¼¾]?\s*\)")
#: "two and one-half feet".
_AND_HALF = re.compile(r"^([a-z-]+) and one-half(?=[\s(])")
_FRACTION = {"½": 0.5, "¼": 0.25, "¾": 0.75}
_NUMBER = r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+)/(\d+)|\s*([½¼¾]))?"
_LENGTH = re.compile(rf"^(?:{_NUMBER}|([a-z-]+?))[\s-]*(feet|foot|ft\.?|inches|inch|in\.?)$")
_SHARE = re.compile(r"^(\d+(?:\.\d+)?)\s*percent of the depth of the setback$")


def _number(m: re.Match[str], first: int) -> float:
    whole, num, den, frac, word = (m.group(first + i) for i in range(5))
    if word is not None:
        if word not in _WORDS:
            raise ValueError(f"not a number: {word!r}")
        return float(_WORDS[word])
    got = float(whole)
    if num is not None:
        got += float(num) / float(den)
    if frac is not None:
        got += _FRACTION[frac]
    return got


def length_ft(printed: str) -> float:
    """A printed length in feet: "3 feet", "three-foot", "2-1/2 feet",
    "2½ ft.", "36 in", "30 inches", "ten (10) feet", "two and one-half feet"."""
    text = _PAREN.sub("", printed.strip().lower())
    half = 0.0
    if (a := _AND_HALF.match(text)) is not None:
        text, half = a.group(1) + text[a.end():], 0.5
    m = _LENGTH.match(text)
    if m is None:
        raise ValueError(f"not a printed length: {printed!r}")
    value = _number(m, 1) + half
    return value / 12.0 if m.group(6).startswith("in") else value


def length_in(printed: str) -> float:
    return length_ft(printed) * 12.0


@dataclass(frozen=True, slots=True)
class Allowance:
    """One yard's room for the steps, as printed and as read: the whole yard
    (``entire``), a length into it (``into_ft``) or a share of its depth
    (``share``), never nearer the line than ``from_line_ft``. A row naming
    only ``from_line_ft`` lets the steps anywhere in the yard short of it."""

    entire: bool = False
    into_ft: float | None = None
    share: float | None = None
    from_line_ft: float | None = None
    printed: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def kept_ft(self, setback_ft: float) -> float:
        """The setback the steps keep in a yard ``setback_ft`` deep."""
        s = max(0.0, float(setback_ft))
        if self.entire or (self.into_ft is None and self.share is None):
            r = 0.0
        elif self.share is not None:
            r = s * (1.0 - self.share)
        else:
            r = s - float(self.into_ft or 0.0)
        r = max(r, 0.0)
        if self.from_line_ft is not None:
            r = max(r, self.from_line_ft)
        return min(r, s)


def _allowance(spec: Mapping[str, Any]) -> Allowance:
    printed = {k: str(v) for k, v in spec.items()}
    into, line = spec.get("into"), spec.get("from_line")
    if into is None and line is None:
        raise ValueError(f"a yard needs `into` or `from_line`: {spec!r}")
    entire, into_ft, share = False, None, None
    if into is not None:
        text = str(into).strip().lower()
        if text == ENTIRE:
            entire = True
        elif (m := _SHARE.match(text)) is not None:
            share = float(m.group(1)) / 100.0
        else:
            into_ft = length_ft(text)
    return Allowance(entire, into_ft, share, None if line is None else length_ft(str(line)), printed)


@dataclass(frozen=True, slots=True)
class Row:
    """One sentence of a code: the zones it reaches, the height band, and
    each yard's :class:`Allowance`."""

    id: str
    jurisdiction: str
    zones: frozenset[str] | None  # None = every zone
    up_to_in: float | None
    over_in: float | None
    surface: bool
    yards: Mapping[str, Allowance]
    cite: str
    quote: tuple[str, ...]
    raw: Mapping[str, Any]

    def reaches(self, zone: str | None) -> bool:
        return self.zones is None or (zone is not None and _zone_key(zone) in self.zones)

    def holds(self, height_in: float) -> bool:
        if self.up_to_in is not None and not height_in <= self.up_to_in + 1e-9:
            return False
        return not (self.over_in is not None and not height_in > self.over_in + 1e-9)


def _zone_key(zone: str) -> str:
    return re.sub(r"[\s/-]", "", str(zone)).upper()


def _row(jurisdiction: str, spec: Mapping[str, Any]) -> Row:
    zones = spec.get("zones")
    if zones != "all" and not (isinstance(zones, list) and zones):
        raise ValueError(f"{spec.get('id')}: zones must be 'all' or a list")
    yards = {y: _allowance(a) for y, a in (spec.get("yards") or {}).items()}
    if not yards or set(yards) - set(YARDS):
        raise ValueError(f"{spec.get('id')}: yards must be some of {YARDS}")
    if spec.get("kind", STEPS) not in KINDS:
        raise ValueError(f"{spec.get('id')}: kind must be one of {KINDS}")
    if spec.get("measured") not in (None, SURFACE):
        raise ValueError(f"{spec.get('id')}: measured must be '{SURFACE}' or absent")
    quote = spec.get("quote") or ()
    return Row(
        id=str(spec["id"]),
        jurisdiction=jurisdiction,
        zones=None if zones == "all" else frozenset(_zone_key(z) for z in zones),
        up_to_in=None if spec.get("up_to") is None else length_in(str(spec["up_to"])),
        over_in=None if spec.get("over") is None else length_in(str(spec["over"])),
        surface=spec.get("measured") == SURFACE,
        yards=yards,
        cite=str(spec["cite"]),
        quote=(quote,) if isinstance(quote, str) else tuple(quote),
        raw=dict(spec),
    )


@lru_cache(maxsize=4)
def rows(path: Path = PATH) -> tuple[Row, ...]:
    """Every row of the file, in order."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return tuple(_row(j, spec) for j, specs in (raw.get("jurisdictions") or {}).items() for spec in specs)


def rows_for(jurisdiction: str | None, zone: str | None) -> tuple[Row, ...]:
    return tuple(r for r in rows() if r.jurisdiction == jurisdiction and r.reaches(zone))


def readings_in(risers: int, *, riser_in: float, handrail_risers: int) -> tuple[float, ...]:
    """The heights a unit of ``risers`` is read at: its platform, and where
    it carries a railing, above any printed figure."""
    platform = risers * riser_in
    return (platform, math.inf) if risers >= handrail_risers else (platform,)


@dataclass(frozen=True, slots=True)
class Kept:
    """What one unit's steps keep of each yard: per yard, the
    :class:`Allowance` that stands (None = the whole setback) and the rows
    read."""

    allowances: Mapping[str, tuple[tuple[Allowance, ...], ...]]
    rows: tuple[str, ...]

    def yard_ft(self, yard: str, setback_ft: float) -> float:
        """The setback kept in ``yard``: the tightest reading's. Within one
        reading every row that holds is a permission of its own, so the most
        generous of them stands; a reading no row holds keeps the yard whole."""
        got = self.allowances.get(yard) or ((),)
        return max(min((a.kept_ft(setback_ft) for a in each), default=setback_ft) for each in got)

    @property
    def none(self) -> bool:
        return all(not each for got in self.allowances.values() for each in got)


def kept(
    jurisdiction: str | None,
    zone: str | None,
    risers: Iterable[int],
    *,
    riser_in: float,
    handrail_risers: int,
) -> Kept:
    """What steps of every count in ``risers`` keep of each yard in this
    city and zone -- every reading of every unit, the tightest standing."""
    found = rows_for(jurisdiction, zone)
    got: dict[str, list[tuple[Allowance, ...]]] = {y: [] for y in YARDS}
    used: list[str] = []
    for k in sorted(set(risers)):
        for h in readings_in(k, riser_in=riser_in, handrail_risers=handrail_risers):
            for y in YARDS:
                hit = [r for r in found if y in r.yards and r.holds(h if not r.surface else k * riser_in)]
                got[y].append(tuple(r.yards[y] for r in hit))
                used.extend(r.id for r in hit)
    return Kept({y: tuple(v) for y, v in got.items()}, tuple(dict.fromkeys(used)))


#: The street lines' refinements of the front (Portland's off-corridor and
#: across-the-street numbers): cut as tight as the front or the street side.
_STREET_EXTRA = ("street_off_corridor_ft", "street_clear_ft")
_STREET = ("front_ft", "street_side_ft", *_STREET_EXTRA)


def setbacks_kept(
    setbacks: Setbacks,
    k: Kept,
    *,
    sidewalk_ft: float | None = None,
    easement_ft: float | None = None,
) -> Setbacks:
    """``setbacks`` as the steps keep them. A street yard is measured from
    the sidewalk easement line where the screen shifted it there
    (``sidewalk_ft``) and never comes nearer the street than an assumed
    utility easement (``easement_ft``). The scenic corridor, the bearing
    separations and anything else no row names stand whole."""
    sw = max(0.0, float(sidewalk_ft or 0.0))

    def cut(yard: str, value: float | None, street: bool) -> float | None:
        if value is None:
            return None
        if not street:
            return k.yard_ft(yard, value)
        got = sw + k.yard_ft(yard, max(0.0, value - sw))
        return min(value, max(got, float(easement_ft or 0.0)))

    def street_extra(value: float | None) -> float | None:
        if value is None:
            return None
        return max(cut("front", value, True) or 0.0, cut("street_side", value, True) or 0.0)

    street_side = setbacks.street_side_ft
    if street_side is None and k.allowances.get("street_side") != k.allowances.get("front"):
        # The code does not tell the street side apart: it takes the front's
        # number, cut as the street side's own steps allow.
        street_side = setbacks.front_ft
    return dataclasses.replace(
        setbacks,
        front_ft=cut("front", setbacks.front_ft, True) or 0.0,
        street_side_ft=cut("street_side", street_side, True),
        street_off_corridor_ft=street_extra(setbacks.street_off_corridor_ft),
        street_clear_ft=street_extra(setbacks.street_clear_ft),
        side_ft=cut("side", setbacks.side_ft, False) or 0.0,
        side_larger_ft=cut("side", setbacks.side_larger_ft, False),
        alley_side_ft=cut("side", setbacks.alley_side_ft, False),
        rear_ft=cut("rear", setbacks.rear_ft, False) or 0.0,
        depth_rear_ft=cut("rear", setbacks.depth_rear_ft, False),
        alley_rear_ft=cut("rear", setbacks.alley_rear_ft, False),
    )


def cited_text(cite: str, docs: Path = DOCS) -> str:
    """The stored lines a ``path#Lnn,Lmm-Lpp`` cite names, joined, with
    whitespace collapsed."""
    path, _, spans = cite.partition("#")
    lines = (docs / path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for span in spans.split(","):
        a, _, b = span.strip().partition("-")
        lo, hi = int(a.lstrip("L")), int((b or a).lstrip("L"))
        if not 1 <= lo <= hi <= len(lines):
            raise ValueError(f"{cite}: lines {lo}-{hi} not in {path} ({len(lines)} lines)")
        out.extend(lines[lo - 1:hi])
    return " ".join(" ".join(out).split())
