"""Oregon property tax under Measures 5 and 50 -- pure functions, Decimal throughout.

Enough of the Oregon system to answer "what does this lot pay today, and what
would it pay built out?" for ordinary residential property: permanent rates,
local option levies, bonds and urban renewal division of tax. Exemptions,
special assessments and partial-exemption programmes are out of scope.

**Assessed value (Measure 50).** ORS 308.146(1)-(2): maximum assessed value
(MAV) is the larger of 103% of last year's assessed value (AV) and last year's
MAV; AV is the lesser of MAV and real market value (RMV).

**New value** (ORS 308.153(1)(b)): new property or improvements add their RMV x
the changed property ratio (CPR, "the ratio ... of the average maximum
assessed value over the average real market value", not greater than 1.00) to
MAV. The assessor sets one CPR per property class, rounded to three decimals
(OAR 150-308-0170).

**Demolition** (ORS 308.146(8); OAR 150-308-0120): the MAV is cut to the
unaffected share -- MAV x (RMV of what remains / total RMV). A demolished
house leaves MAV x land RMV / total RMV. ORS 308.166(6): the demolition
adjustment comes first, then new value (308.153) and partition (308.156).

**Partition -- the rule the pod's figure stands on.** ORS 308.146(3)(b) takes
partitioned or subdivided property out of the 103% rule and sends it to ORS
308.149 to 308.166. ORS 308.156(5): MAV is the MAV allocable to the portion
*not* affected, plus the RMV of the *affected* portion x CPR. OAR 150-308-0190
defines the affected portion of a partition as "(1) The entire land that was
subdivided or partitioned into smaller lots or parcels" (and the improvements
only where a building is split, re-perceived, or divided into units). So each
new lot's land MAV is reset to its land RMV x CPR -- the old lot's MAV history
does not survive -- and each new unit adds (building RMV) x CPR under 308.153.
A lot's MAV after partition + construction is therefore land RMV x CPR +
building RMV x CPR = unit RMV x CPR, however the assessor splits land from
building.

**Measure 5** (Or Const Art XI s11b; ORS 310.150): taxes on a property, other
than for bonded indebtedness, are limited per category to $5 per $1,000 of RMV
for the public school system and $10 per $1,000 of RMV for other government.
ORS 310.150(4)-(6): when a category exceeds its limit, a reduction ratio is
applied to the local option taxes alone (5), and only once "all local option
taxes have been eliminated" does a second ratio reduce every remaining item
in the category proportionally (6). Exempt bonded indebtedness is its own
category with no limit (3)(d). Urban renewal division of tax is compressed
within the category of the levy it was divided from.

Rounding: MAV and AV are carried to whole dollars; each levy's tax is carried
unrounded through compression and rounded to the cent (half up) as a bill
line; totals are sums of bill lines.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
DOLLAR = Decimal("1")
THOUSAND = Decimal("1000")

#: Measure 5 limit per $1,000 of RMV, by category.
M5_LIMIT: dict[str, Decimal] = {"education": Decimal("5"), "general_government": Decimal("10")}

#: Measure 50: the 3% a year MAV may grow on an unchanged property.
MAV_GROWTH = Decimal("1.03")

KINDS = ("permanent", "local_option", "bond", "urban_renewal")
CATEGORIES = tuple(M5_LIMIT)


@dataclass(frozen=True)
class Levy:
    """One district's rate in one code area, per $1,000 of AV."""

    district: str
    kind: str  # permanent | local_option | bond | urban_renewal
    category: str  # education | general_government
    rate: Decimal

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"levy kind {self.kind!r} is not one of {KINDS}")
        if self.category not in CATEGORIES:
            raise ValueError(f"levy category {self.category!r} is not one of {CATEGORIES}")


@dataclass(frozen=True)
class LevyTax:
    levy: Levy
    before: Decimal  # AV x rate, before compression, unrounded
    after: Decimal  # after Measure 5, unrounded

    @property
    def billed(self) -> Decimal:
        return cents(self.after)


@dataclass(frozen=True)
class Bill:
    """One year's tax on one property, with the figures the snapshot reports."""

    av: Decimal
    rmv: Decimal
    lines: tuple[LevyTax, ...]

    def _sum(self, keep) -> Decimal:
        return sum((t.billed for t in self.lines if keep(t.levy)), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        return self._sum(lambda lv: True)

    @property
    def headline(self) -> Decimal:
        """Permanent rates (with the urban renewal divided from them) plus bonds."""
        return self._sum(lambda lv: lv.kind != "local_option")

    @property
    def local_option(self) -> Decimal:
        return self._sum(lambda lv: lv.kind == "local_option")

    @property
    def compression(self) -> Decimal:
        """What Measure 5 took off, to the cent."""
        return cents(sum((t.before - t.after for t in self.lines), Decimal("0")))

    def district(self, name: str, *, local_option: bool = False) -> Decimal:
        """One district's permanent + bond tax, or its local option tax."""
        if local_option:
            return self._sum(lambda lv: lv.district == name and lv.kind == "local_option")
        return self._sum(lambda lv: lv.district == name and lv.kind in ("permanent", "bond"))


def cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def dollars(x: Decimal) -> Decimal:
    return x.quantize(DOLLAR, rounding=ROUND_HALF_UP)


# --- Measure 50 ---------------------------------------------------------------


def assessed_value(mav: Decimal, rmv: Decimal) -> Decimal:
    """ORS 308.146(2) / 308.153(4) / 308.156(6): the lesser of MAV and RMV."""
    return min(mav, rmv)


def new_value_mav(rmv_new: Decimal, cpr: Decimal) -> Decimal:
    """ORS 308.153(1)(b): MAV added by new property worth ``rmv_new``."""
    _check_cpr(cpr)
    return dollars(max(rmv_new, Decimal("0")) * cpr)


def demolished_mav(mav: Decimal, remaining_rmv: Decimal, total_rmv: Decimal) -> Decimal:
    """OAR 150-308-0120: MAV x the share of RMV that survives the demolition."""
    if total_rmv <= 0:
        raise ValueError("total RMV must be positive to prorate MAV")
    return dollars(mav * remaining_rmv / total_rmv)


def partitioned_land_mav(land_rmv: Decimal, cpr: Decimal) -> Decimal:
    """ORS 308.156(5)(b) with OAR 150-308-0190(1): a partitioned lot's land MAV
    is reset to its land RMV x CPR."""
    _check_cpr(cpr)
    return dollars(land_rmv * cpr)


def next_mav(av: Decimal, mav: Decimal) -> Decimal:
    """ORS 308.146(1): next year's MAV on an unchanged property."""
    return max(dollars(av * MAV_GROWTH), mav)


def av_path(mav: Decimal, rmv: Decimal, years: int) -> list[Decimal]:
    """AV for ``years`` years from this one, RMV held flat, no new value."""
    out: list[Decimal] = []
    for _ in range(years):
        av = assessed_value(mav, rmv)
        out.append(av)
        mav = next_mav(av, mav)
    return out


def _check_cpr(cpr: Decimal) -> None:
    if not (Decimal("0") < cpr <= Decimal("1")):
        raise ValueError(f"CPR {cpr} is outside (0, 1.00] (ORS 308.153(1)(b))")


# --- Measure 5 ----------------------------------------------------------------


def bill(av: Decimal, rmv: Decimal, levies: Iterable[Levy]) -> Bill:
    """The year's tax on a property with this AV and RMV in a code area."""
    raw = [(lv, av * lv.rate / THOUSAND) for lv in levies]
    after = {id(lv): tax for lv, tax in raw}
    for category, limit in M5_LIMIT.items():
        subject = [(lv, tax) for lv, tax in raw if lv.category == category and lv.kind != "bond"]
        cap = rmv * limit / THOUSAND
        excess = sum((tax for _, tax in subject), Decimal("0")) - cap
        if excess <= 0:
            continue
        options = [(lv, tax) for lv, tax in subject if lv.kind == "local_option"]
        others = [(lv, tax) for lv, tax in subject if lv.kind != "local_option"]
        excess = _reduce(options, excess, after)
        if excess > 0:
            _reduce(others, excess, after)
    return Bill(av=av, rmv=rmv, lines=tuple(LevyTax(lv, tax, after[id(lv)]) for lv, tax in raw))


def _reduce(group: Sequence[tuple[Levy, Decimal]], excess: Decimal, after: dict[int, Decimal]) -> Decimal:
    """Take up to ``excess`` off ``group`` proportionally; return what is left over."""
    total = sum((tax for _, tax in group), Decimal("0"))
    if total <= 0:
        return excess
    take = min(excess, total)
    for lv, tax in group:
        after[id(lv)] = tax - take * tax / total
    return excess - take


def cumulative(mav: Decimal, rmv: Decimal, levies: Sequence[Levy], years: int) -> list[Bill]:
    """One bill a year for ``years`` years, rates and RMV held flat."""
    return [bill(av, rmv, levies) for av in av_path(mav, rmv, years)]
