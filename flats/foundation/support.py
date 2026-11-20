"""Ground-support groups (FD6 section 5.7; FD4 section 1; ``FD4_lot_reading.py`` ``bin_of()``).

| Group | What the model does |
|---|---|
| ordinary footing | B and A |
| piles under the wall | B+P (footing concrete dropped, screw piles added); no A |
| own look | B for the record; flagged "not standard" |
| not sorted | B; flagged "ground not sorted" |

The class is FD2's ground class, or for an Urban-land lot (``NO-DATA``) the
class of the named series mapped with it (``alt_ground_class``).
"""

from __future__ import annotations

from collections.abc import Mapping

from flats.foundation.settings import Settings

ORDINARY = "ordinary footing"
PILES = "piles under the wall"
OWN_LOOK = "own look"
NOT_SORTED = "not sorted"
GROUPS = (ORDINARY, PILES, OWN_LOOK, NOT_SORTED)

#: The methods each group is compared on (FD6 section 5.7).
APPLICABLE: dict[str, tuple[str, ...]] = {
    ORDINARY: ("A dry", "A wet", "B"),
    PILES: ("B+P",),
    OWN_LOOK: ("B",),
    NOT_SORTED: ("B",),
}

NOT_STANDARD = "not_standard"
GROUND_NOT_SORTED = "ground_not_sorted"


def effective_class_of(ground_class: str | None, alt_ground_class: str | None) -> str:
    """FD4 ``eff_class``: FD2's class, or for Urban-land lots the class of the named series."""
    ground = ground_class or ""
    if ground == "NO-DATA":
        return alt_ground_class or "UNSORTED"
    return ground


def effective_class(row: Mapping[str, str]) -> str:
    return effective_class_of(row.get("ground_class"), row.get("alt_ground_class"))


def group_of_class(cls: str, s: Settings) -> str:
    if cls in s.own_look_classes:
        return OWN_LOOK
    if cls in s.piles_classes:
        return PILES
    if cls in s.footing_classes:
        return ORDINARY
    return NOT_SORTED


def group_of(row: Mapping[str, str], s: Settings) -> str:
    """FD4 ``bin_of()``: the ground-support group of one lot-file row."""
    return group_of_class(effective_class(row), s)


def group_flags(group: str) -> tuple[tuple[str, str], ...]:
    if group == OWN_LOOK:
        return ((NOT_STANDARD, "not standard: the ground takes its own look (outside the comparison)"),)
    if group == NOT_SORTED:
        return ((GROUND_NOT_SORTED, "ground not sorted (outside the comparison)"),)
    return ()
