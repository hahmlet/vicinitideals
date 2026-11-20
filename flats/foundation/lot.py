"""One lot's foundation result (FD6 section 2, items 1-8), in two layers.

* :func:`~flats.foundation.measure.measure` -- MEASURE, once, from the ground.
* :func:`assess` -- PRICE, from the stored record and the settings: every method
  (B always; B+P, A dry and A wet too, so the record is whole and the FD6
  section 8 lot-file shares, which the reference model counts over every lot,
  reproduce), the lot flags, the cheaper of A and B, and the plain-words
  classification. Re-pricing every lot after a price or threshold change is
  ``assess(record, new_settings)`` over the stored records.

Which methods a lot is *compared* on is
:data:`~flats.foundation.support.APPLICABLE` for its ground-support group.

:func:`from_row` reads one lot-file row (``fd2_lots.csv``): the six readings
``z_front_left`` ... ``z_back_right``, ``relief_ft``, ``elev_cell_m``,
``front_face_turn_deg``, the ground classes, ``frost_register_in``,
``bldg_overlap_share`` and ``year_built``. It returns None when a reading is
missing. Old buildings are attached to a record separately
(:func:`flats.foundation.measure.with_old_buildings`); :func:`assess` prices them
conditionally (:mod:`flats.foundation.infill`), outside every main total.

Never a colour: nothing here is read by the screen.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from flats.foundation import classify, model, support
from flats.foundation import infill as infill_mod
from flats.foundation.ground import Ground, six_readings
from flats.foundation.measure import Measured, measure
from flats.foundation.settings import Settings

READINGS = ("z_front_left", "z_front_mid", "z_front_right", "z_back_left", "z_back_mid", "z_back_right")

COARSE = "coarse_ground_model"
FRONT_GUESS = "front_face_guess"
WALL_CROSSES_OLD = "wall_crosses_old_building"


def num(text: str | None) -> float | None:
    """FD4 ``num``: a lot-file number, or None for blank / NaN / text."""
    if text is None or text == "":
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return None if math.isnan(value) else value


@dataclass(frozen=True, slots=True)
class Cheaper:
    """Item 8: the cheaper of A and B at one price level, and by how much."""

    prices: str  # "low" or "high"
    against: str  # "A dry" or "A wet"
    cheaper: str  # "A" or "B" ("same" on a tie)
    by: Decimal


@dataclass(frozen=True, eq=False)
class LotResult:
    measured: Measured
    group: str
    applicable: tuple[str, ...]
    #: Footing depth used (in): the lot's frost-register depth with
    #: ``use_frost_register``, else the ``embed_in`` setting.
    embed_in_used: float
    methods: dict[str, model.MethodResult]
    flags: tuple[str, ...]
    flag_words: tuple[str, ...]
    cheaper: tuple[Cheaper, ...]
    style: classify.Style
    challenges: tuple[classify.Item, ...]
    easy: tuple[classify.Item, ...]
    #: Old buildings under the pod, priced "if it had a basement": NOT in any
    #: method's cost.
    infill: infill_mod.Infill

    def __getitem__(self, method: str) -> model.MethodResult:
        return self.methods[method]

    @property
    def tlid(self) -> str | None:
        return self.measured.tlid

    @property
    def county(self) -> str | None:
        return self.measured.county

    @property
    def ground_source(self) -> str:
        return self.measured.ground_source

    @property
    def cell_m(self) -> float | None:
        return self.measured.cell_m

    @property
    def lump_ft(self) -> float:
        return self.measured.lump_ft


def _cheaper(methods: dict[str, model.MethodResult], applicable: tuple[str, ...]) -> tuple[Cheaper, ...]:
    if "B" not in applicable:
        return ()
    out = []
    b = methods["B"].cost
    for against in ("A dry", "A wet"):
        if against not in applicable:
            continue
        a = methods[against].cost
        for prices, av, bv in (("low", a.low, b.low), ("high", a.high, b.high)):
            winner = "B" if bv < av else "A" if av < bv else "same"
            out.append(Cheaper(prices, against, winner, abs(av - bv)))
    return tuple(out)


def assess(m: Measured, s: Settings, *, group: str | None = None) -> LotResult:
    """PRICE: one stored record -> its methods, flags, comparison and classification.
    ``group`` overrides the ground-support group the record's classes give."""
    if group is None:
        group = support.group_of_class(support.effective_class_of(m.ground_class, m.alt_ground_class), s)
    if group not in support.GROUPS:
        raise ValueError(f"unknown ground-support group {group!r}")
    methods = {
        "B": model.raised(m, s),
        "B+P": model.raised(m, s, piles=True),
        "A dry": model.slab(m, s),
        "A wet": model.slab(m, s, wet=True),
    }
    applicable = support.APPLICABLE[group]
    flags: list[str] = []
    words: list[str] = []
    for code, text in support.group_flags(group):
        flags.append(code)
        words.append(text)
    if m.cell_m is not None and m.cell_m > s.coarse_cell_over_m:
        flags.append(COARSE)
        words.append(f"coarse ground model: {m.cell_m:g} m cells (over {s.coarse_cell_over_m:g} m), relief understated")
    if m.front_face_turn_deg is not None and m.front_face_turn_deg > s.front_face_guess_over_deg:
        flags.append(FRONT_GUESS)
        words.append(f"the street-side face is turned {m.front_face_turn_deg:.0f} degrees: which face carries the front doors is a guess")
    embed = model.embed_of(m, s)
    old = infill_mod.assess(m, model.lot_settings(m, s), embed)
    if old.wall_crossed:
        flags.append(WALL_CROSSES_OLD)
        words.append(f"wall crosses a mapped building: longest stretch {old.longest_ft:.1f} ft (basement cost conditional, not in the total)")
    return LotResult(
        measured=m,
        group=group,
        applicable=applicable,
        embed_in_used=embed,
        methods=methods,
        flags=tuple(flags),
        flag_words=tuple(words),
        cheaper=_cheaper(methods, applicable),
        style=classify.style(group, methods, applicable),
        challenges=classify.challenges(m, group, methods, applicable, s, old),
        easy=classify.easy_parts(m, group, methods, applicable, s),
        infill=old,
    )


def run_lot(
    ground: Ground,
    s: Settings,
    *,
    group: str | None = support.ORDINARY,
    tlid: str | None = None,
    county: str | None = None,
    inputs: Mapping[str, object] | None = None,
) -> LotResult:
    """MEASURE then PRICE one ground (``group=None`` takes it from ``inputs``' classes)."""
    return assess(measure(ground, s, tlid=tlid, county=county, inputs=inputs), s, group=group)


def ground_from_row(row: Mapping[str, str], s: Settings) -> Ground | None:
    """The six readings and lump allowance of one lot-file row, or None if a reading is missing."""
    z = [num(row.get(k)) for k in READINGS]
    relief = num(row.get("relief_ft"))
    if relief is None or any(v is None for v in z):
        return None
    return six_readings(s, *z, relief_ft=relief, cell_m=num(row.get("elev_cell_m")))  # type: ignore[arg-type]


def measure_row(row: Mapping[str, str], s: Settings) -> Measured | None:
    """MEASURE one lot-file row, or None when a reading is missing. The TLID is
    kept whole (it may contain spaces)."""
    ground = ground_from_row(row, s)
    if ground is None:
        return None
    return measure(ground, s, tlid=row.get("TLID") or row.get("tlid"), county=row.get("county"), inputs=inputs_of(row))


def inputs_of(row: Mapping[str, str]) -> dict[str, object]:
    """The lot-file fields a record keeps but does not measure."""
    return {
        "relief_input_ft": num(row.get("relief_ft")),
        "ground_class": row.get("ground_class"),
        "alt_ground_class": row.get("alt_ground_class"),
        "frost_register_in": num(row.get("frost_register_in")),
        "bldg_overlap_share": num(row.get("bldg_overlap_share")),
        "front_face_turn_deg": num(row.get("front_face_turn_deg")),
        "year_built": num(row.get("year_built")),
    }


def from_row(row: Mapping[str, str], s: Settings) -> LotResult | None:
    """MEASURE and PRICE one lot-file row, or None when a reading is missing."""
    m = measure_row(row, s)
    return None if m is None else assess(m, s)
