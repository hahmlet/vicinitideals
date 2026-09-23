"""The snapshot's own arithmetic, apart from the database: the new house's
value, one lot's row, and the summary the city reads.

``scripts/flats_tax_snapshot.py`` reads the lots and writes the rows; what it
computes lives here so it can be tested without a database.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any

from flats.tax import impact
from flats.tax.oregon import Levy, dollars

#: Scenario prefixes, in the order the row and the CSV carry them.
SCENARIOS = ("a", "b", "c_low", "c_mid", "c_high")
#: The pod's three unit values, in the order ``band`` carries them.
BAND_ENDS = ("low", "mid", "high")
FIGURES = ("av", "total", "local_option", "city", "city_local_option", "ten_year")
COLUMNS = tuple(f"{s}_{f}" for s in SCENARIOS for f in FIGURES)

#: green_source values, and which of them each headline set counts.
SETS = {
    "FLATS if-signed green": ("both", "flats_only"),
    "quadfit green": ("both", "quadfit_only"),
    "every green lot": ("both", "flats_only", "quadfit_only"),
}


def green_source(quadfit_green: bool, flats_green: bool) -> str | None:
    if quadfit_green and flats_green:
        return "both"
    if quadfit_green:
        return "quadfit_only"
    if flats_green:
        return "flats_only"
    return None


@dataclass(frozen=True)
class HouseValue:
    rmv: Decimal
    per_sqft: Decimal
    sqft: Decimal
    sample: int


def house_value(records: Iterable[tuple[Decimal, Decimal]]) -> HouseValue:
    """A new house's RMV: median building value per sq ft x median building sq
    ft, over (building value, building sq ft) pairs of recent single-family
    builds. Pairs with a zero or missing side are dropped."""
    pairs = [(bv, sf) for bv, sf in records if bv and sf and bv > 0 and sf > 0]
    if not pairs:
        raise ValueError("no new-build records to value a house from")
    per_sqft = Decimal(median(bv / sf for bv, sf in pairs))
    sqft = Decimal(median(sf for _, sf in pairs))
    return HouseValue(rmv=dollars(per_sqft * sqft), per_sqft=per_sqft, sqft=sqft, sample=len(pairs))


def townhome_value(values: Iterable[Decimal]) -> tuple[Decimal, int]:
    """The pod's middle unit value: the median assessor RMV (land + house)
    of recent single-family houses on small lots -- the nearest thing on the
    roll to a new fee-simple townhome. Zero or missing values are dropped."""
    vals = [v for v in values if v and v > 0]
    if not vals:
        raise ValueError("no small-lot new builds to value a townhome from")
    return dollars(Decimal(median(vals))), len(vals)


def _put(row: dict[str, Any], prefix: str, out: impact.Outcome) -> None:
    row[f"{prefix}_av"] = out.av
    row[f"{prefix}_total"] = out.headline
    row[f"{prefix}_local_option"] = out.local_option
    row[f"{prefix}_city"] = out.city
    row[f"{prefix}_city_local_option"] = out.city_local_option
    row[f"{prefix}_ten_year"] = out.ten_year


def price_lot(
    roll: impact.Roll | None,
    levies: Sequence[Levy] | None,
    *,
    city: str,
    cpr: Decimal,
    house_rmv: Decimal,
    band: tuple[Decimal, Decimal, Decimal],
    units: int = 4,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The figures of one lot, and its notes. A lot that cannot be priced
    (no roll values, a code area the rate file does not hold) gets empty
    figures and a ``skipped`` note naming why."""
    row: dict[str, Any] = dict.fromkeys(COLUMNS)
    notes: dict[str, Any] = {}
    if roll is None:
        notes["skipped"] = "no_roll_values"
        return row, notes
    why = impact.usable(roll)
    if why:
        notes["skipped"] = why
        return row, notes
    if levies is None:
        notes["skipped"] = "taxcode_not_in_rate_file"
        return row, notes
    outcomes = {
        "a": impact.current(roll, levies, city),
        "b": impact.new_house(roll, levies, city, cpr, house_rmv),
        **{
            f"c_{end}": impact.pod(roll, levies, city, cpr, value, units=units)
            for end, value in zip(BAND_ENDS, band, strict=True)
        },
    }
    for prefix, out in outcomes.items():
        _put(row, prefix, out)
        if out.notes:
            notes[prefix] = out.notes
        if out.compression:
            notes.setdefault("measure5_compression", {})[prefix] = str(out.compression)
    return row, notes


# --- the summary ---------------------------------------------------------------


def _money(x: Decimal | None) -> str:
    return "--" if x is None else f"${x:,.0f}"


def _ratio(num: Decimal, den: Decimal) -> str:
    return "--" if not den else f"{num / den:.2f}x"


def _col(rows: Sequence[dict[str, Any]], key: str) -> list[Decimal]:
    return [r[key] for r in rows if r.get(key) is not None]


def summarize(rows: Sequence[dict[str, Any]], params: dict[str, Any]) -> str:
    """Totals and medians per green set, and the pod's multiples."""
    lines = [
        f"# Property-tax impact -- {params['jurisdiction']}, tax year {params['tax_year']}",
        "",
        f"Snapshot of {params['created']}, run {params['run_id']}. "
        f"Headline = permanent rates (with the urban renewal divided from them) + bonds, "
        f"after Measure 5; local option levies are a separate column. Pod = {params['units']} "
        f"fee-simple lots at ${params['band']['low']:,} (low), ${params['band']['mid']:,} (mid: "
        f"{params['band']['mid_derivation']}) and ${params['band']['high']:,} (high) a unit. New house RMV ${params['house']['rmv']:,} "
        f"({params['house']['derivation']}). Residential CPR {params['cpr']}.",
        "",
        *(
            [
                f"The pod is valued at this year's ratio; it will get the ratio of the year it reaches "
                f"the roll, which has run {params['cpr_range']} since {params['cpr_since']} -- the pod's "
                f"tax moves with it one for one.",
                "",
            ]
            if params.get("cpr_range")
            else []
        ),
        "Ten-year figures are ILLUSTRATIVE: rates and market values held flat, "
        "assessed value growing 3% a year to its market-value cap.",
        "",
    ]
    for label, sources in SETS.items():
        group = [r for r in rows if r["green_source"] in sources]
        priced = [r for r in group if r.get("a_total") is not None]
        lines += [f"## {label}: {len(group):,} lots, {len(priced):,} priced", ""]
        if not priced:
            lines += ["Nothing to price.", ""]
            continue
        lines += [
            "| | today (A) | new house (B) | pod low (C) | pod mid (C) | pod high (C) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for title, fig in (
            ("headline, year 1, total", "total"),
            ("city share, year 1, total", "city"),
            ("local options, year 1, total", "local_option"),
            ("city local option, year 1, total", "city_local_option"),
            ("headline, 10 years (illustrative), total", "ten_year"),
        ):
            cells = [_money(sum(_col(priced, f"{s}_{fig}"), Decimal("0"))) for s in SCENARIOS]
            lines.append(f"| {title} | " + " | ".join(cells) + " |")
        for title, fig in (("headline, year 1, median lot", "total"), ("city share, year 1, median lot", "city")):
            cells = [_money(Decimal(median(_col(priced, f"{s}_{fig}")))) for s in SCENARIOS]
            lines.append(f"| {title} | " + " | ".join(cells) + " |")
        lines.append("")
        a = sum(_col(priced, "a_total"), Decimal("0"))
        b = sum(_col(priced, "b_total"), Decimal("0"))
        for end in BAND_ENDS:
            c = sum(_col(priced, f"c_{end}_total"), Decimal("0"))
            per_lot = [r[f"c_{end}_total"] / r["a_total"] for r in priced if r["a_total"]]
            typical = f", median lot {Decimal(median(per_lot)):.2f}x" if per_lot else ""
            lines.append(f"- Pod {end} / today: {_ratio(c, a)} in total{typical}")
            lines.append(f"- Pod {end} / new house: {_ratio(c, b)} in total")
        lines.append("")
    skipped: dict[str, int] = {}
    for r in rows:
        why = (r.get("notes") or {}).get("skipped")
        if why:
            skipped[why] = skipped.get(why, 0) + 1
    if skipped:
        lines += ["## Not priced", ""] + [f"- {why}: {n:,}" for why, n in sorted(skipped.items())] + [""]
    return "\n".join(lines)
