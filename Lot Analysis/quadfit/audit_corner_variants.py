"""Which way the corpus's corner-lot rules run, before anyone builds the check.

Fourteen jurisdictions define what a corner lot is and nothing in the screen
computes which lots are corners, so every `corner_lot` variant in the corpus is
inert: the base limb binds on all 250,744 lots. That has been sitting on the
work list as an opportunity -- "worth ~10 ft of buildable envelope wherever
corner variants exist" -- and this run says the opposite, which is worth knowing
before the feature is built rather than after.

**Every corner-lot variant that would fire on a lot this screen actually places
is a TIGHTENING.** Wood Village LR 7.5 takes the side yard from 5 ft to 10 and
the rear from 15 to 20. Gresham's residential districts take minimum frontage
from 35 ft to 40 and MDR's lot width from 16 ft to 70. Unincorporated Multnomah
takes width from 45 to 50. The ten feet in the old note is real and it is a
cost.

The corpus does hold twenty-eight corner variants that loosen, and they are the
reason the note read the way it did -- Gresham drops a 100 ft frontage minimum
to 32 on a corner, and a 75 ft width to 20. **Every single one of them also
requires `unit_lots`**, the middle-housing land-division plat path. The screen
does not take that path, so none of them can fire, and computing corner status
would not release them: it would release the thirty-two that take lots away.

That does not make the feature not worth building. A false green is the
dangerous kind of error and this is a pile of them. It makes it a correctness
fix with no upside in lot count, which is a different thing to schedule than an
opportunity, and the two get scheduled very differently.

    uv run python "Lot Analysis/quadfit/audit_corner_variants.py"
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

#: Fields where a LARGER number is stricter.
TIGHTENS = frozenset({
    "setback_front_ft", "setback_side_ft", "setback_rear_ft",
    "setback_street_side_ft", "setback_side_total_ft",
    "min_lot_sqft", "min_lot_width_ft", "min_lot_depth_ft",
    "min_frontage_ft", "parking_min_per_unit",
})

#: Fields where a LARGER number is more permissive.
LOOSENS = frozenset({
    "max_coverage_pct", "max_height_ft", "max_units",
    "max_density_du_per_acre", "parking_max_per_unit",
    "setback_front_max_ft",
})

#: Conditions that make a variant unreachable for this product as screened.
#: `unit_lots` is the middle-housing land-division plat, which fires off the
#: design catalog and is not the path the site plan draws; `conditional_use` is
#: a discretionary approval and by definition not by-right.
OUT_OF_REACH = frozenset({"unit_lots", "conditional_use"})


@dataclass(frozen=True)
class CornerVariant:
    layer: str
    zone: str
    field: str
    base: object
    alt: object
    when: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.layer}/{self.zone}.{self.field}"

    @property
    def reachable(self) -> bool:
        """True when nothing but corner status stands between the screen and
        this variant."""
        return not (set(self.when) & OUT_OF_REACH)

    @property
    def direction(self) -> str:
        if self.base is None or self.alt is None:
            return "exempt/none"
        try:
            base, alt = float(self.base), float(self.alt)
        except (TypeError, ValueError):
            return "unclassified"
        if base == alt:
            return "same"
        if self.field in TIGHTENS:
            return "tightens" if alt > base else "loosens"
        if self.field in LOOSENS:
            return "loosens" if alt > base else "tightens"
        return "unclassified"

    def __str__(self) -> str:
        return (f"{self.key}: {self.base} -> {self.alt} "
                f"when={list(self.when)} [{self.direction}]")


def scan() -> list[CornerVariant]:
    from flats.rules.loader import load_rules

    out: list[CornerVariant] = []
    for lid, layer in sorted(load_rules().items()):
        for zname, zl in sorted(layer.zones.items()):
            for fname, value in sorted(zl.values.items()):
                for v in getattr(value, "variants", ()) or ():
                    when = tuple(getattr(v, "when", ()) or ())
                    if "corner_lot" not in when:
                        continue
                    out.append(
                        CornerVariant(lid, zname, fname, value.value, v.value, when)
                    )
    return out


def main() -> None:
    rows = scan()
    reachable = [r for r in rows if r.reachable]
    print(f"{len(rows)} corner-lot variants in the corpus, all of them inert today")
    print(f"{len(reachable)} would fire the moment corner status is computed\n")

    for label, subset in (("ALL", rows), ("REACHABLE", reachable)):
        print(f"{label} by direction:")
        for d, n in Counter(r.direction for r in subset).most_common():
            print(f"    {d}: {n}")
        print()

    gain = [r for r in reachable if r.direction == "loosens"]
    print(f"{len(gain)} reachable variants that would ADD buildable room:")
    for r in gain:
        print("   ", r)
    if not gain:
        print("    (none -- computing corner status can only take lots away)")
    print()

    cost = [r for r in reachable if r.direction == "tightens"]
    print(f"{len(cost)} reachable variants that would TAKE buildable room:")
    for r in cost:
        print("   ", r)
    print()

    print("by jurisdiction:")
    for lay, n in Counter(r.layer for r in rows).most_common():
        live = sum(1 for r in rows if r.layer == lay and r.reachable)
        print(f"    {lay}: {n} ({live} reachable)")


if __name__ == "__main__":
    main()
