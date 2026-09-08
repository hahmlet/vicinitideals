"""Which encoded standards can actually move a verdict, and which cannot.

Both blind re-readings of the corpus reached the same conclusion by different
routes: *the encoding is wrong where nothing reads it*. The 2026-09-07 second
reading found six misquoted numbers and three of the six sat in fields
:data:`flats.score.screen.CHECK_FIELD` does not screen. The footnote-aware
re-read of 731 cards that followed found exactly one note that tightens a
standard we hold too loosely -- Milwaukie's 0.5-space middle-housing ceiling on
an arterial -- in ``parking_max_per_unit``, which nothing reads either.

Twice is a pattern, and the pattern is not carelessness. A reader gives a
citation in an unscreened field the same care as one in a screened field,
because *nothing on the page says which is which*. The field registry says a
standard exists; it has never said whether anybody downstream asks for it.

So this module answers one question, from the source rather than from a list
somebody has to remember to update:

    For each field in the registry, which modules name it?

A field no module names is not a bug. Many are honest inventory -- a standard
the corpus records because a code states it, kept against the day a screen
grows a check for it. What is a bug is not *knowing*, and a list nobody
maintains going quietly stale. So the consumers are found by reading the
consuming modules with :mod:`ast`: a field is reached when a module under
:data:`CONSUMER_ROOTS` contains its name as a string literal. That is a
deliberately crude test -- a literal in a docstring counts -- and it is crude
in the safe direction, because it over-reports reach and so never invents a
gap that is not there.

Unread splits in two, and the split is the useful part. ``paper.py`` already
names, in the fit it returns, the standards its envelope does not cost:
``"setback_street_side_ft (corner lots only)"``. Ninety-five values sit behind
that field and every one of them is deliberate. So a literal that *begins*
with a field name is read as a declaration rather than a use, and the report
separates the standards somebody excluded on the record from the ones nothing
anywhere mentions.

``python -m flats.encode.consumed`` prints them with the weight of encoding
behind each: how many zones state one, across how many jurisdictions. That
weight is the point. A silently unread field with one value in one city is a
rounding error; ``setback_garage_entrance_ft``, with sixty-six values in ten
jurisdictions and a documented misreading already found in it, is a standing
invitation to spend a reviewer's afternoon on a number that cannot change an
answer.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from flats.rules.fields import FIELDS, OPTIONAL_FIELDS
from flats.rules.loader import load_rules

#: Where a field name has to appear for the standard to reach an answer. The
#: scoring package is the whole of it today: ``screen`` runs the checks and
#: ``paper`` lays the pod out inside the setbacks. ``designs`` is here because
#: a design fact can gate a variant, and ``normalize`` because a detector can
#: refuse a parcel before either runs.
CONSUMER_ROOTS: tuple[str, ...] = (
    "flats/score",
    "flats/designs",
    "flats/normalize",
)

_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Reach:
    """One field, and what reads it."""

    field: str
    readers: tuple[str, ...]
    #: Modules that name the field only inside a longer sentence -- which is
    #: how ``paper.py`` declares what its envelope deliberately leaves out
    #: ("setback_street_side_ft (corner lots only)"). A field excluded on the
    #: record is unread, but it is not unnoticed, and the two want different
    #: answers.
    declared: tuple[str, ...]
    #: (jurisdiction, zone) pairs that state a value for it.
    stated: tuple[tuple[str, str], ...]
    required: bool

    @property
    def reached(self) -> bool:
        return bool(self.readers)

    @property
    def silent(self) -> bool:
        """Unread, and nothing anywhere says so."""
        return not self.readers and not self.declared

    @property
    def layers(self) -> int:
        return len({lid for lid, _ in self.stated})

    @property
    def values(self) -> int:
        return len(self.stated)


def _literals(path: Path) -> set[str]:
    """Every string constant in one module, however it is spelled."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return set()
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def readers_by_field(
    root: Path | None = None,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """``(field -> modules that read it, field -> modules that exclude it)``.

    A literal equal to the field name is a read. A literal that *begins* with
    the field name and a space is a declaration -- the shape ``paper.py`` uses
    to name, in the result itself, the standards its envelope does not cost.
    """
    base = root or _ROOT
    read: dict[str, set[str]] = defaultdict(set)
    said_of: dict[str, set[str]] = defaultdict(set)
    for rel in CONSUMER_ROOTS:
        for path in sorted((base / rel).rglob("*.py")):
            if path.name == "__init__.py":
                continue
            said = _literals(path)
            where = path.relative_to(base).as_posix()
            for name in FIELDS:
                if name in said:
                    read[name].add(where)
                elif any(s.startswith(f"{name} ") for s in said):
                    said_of[name].add(where)
    return (
        {k: tuple(sorted(v)) for k, v in read.items()},
        {k: tuple(sorted(v)) for k, v in said_of.items()},
    )


def reach(layers=None, root: Path | None = None) -> list[Reach]:
    """Every registered field, with its readers and the weight behind it."""
    layers = load_rules() if layers is None else layers
    readers, declared = readers_by_field(root)

    stated: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for lid, layer in layers.items():
        for name in layer.defaults:
            stated[name].append((lid, "(defaults)"))
        for zone_code, zone in layer.zones.items():
            for name in zone.values:
                stated[name].append((lid, zone_code))

    return sorted(
        (
            Reach(
                field=name,
                readers=readers.get(name, ()),
                declared=declared.get(name, ()),
                stated=tuple(stated.get(name, ())),
                required=name not in OPTIONAL_FIELDS,
            )
            for name in FIELDS
        ),
        key=lambda r: (r.reached, -len(r.stated), r.field),
    )


def render(rows: list[Reach], unreached_only: bool = False) -> str:
    out: list[str] = []
    dark = [r for r in rows if r.silent and r.stated]
    told = [r for r in rows if not r.reached and r.declared and r.stated]
    lit = [r for r in rows if r.reached]
    idle = [r for r in rows if not r.reached and not r.stated]

    out.append(
        f"fields={len(rows)} reached={len(lit)} declared-excluded={len(told)} "
        f"silently-unread={len(dark)} unused={len(idle)}"
    )
    out.append(
        f"values behind the silently unread: {sum(r.values for r in dark)} "
        f"in {len({lid for r in dark for lid, _ in r.stated})} jurisdictions"
    )
    out.append("")
    out.append("ENCODED AND SILENTLY UNREAD -- a number here cannot change an answer")
    for r in dark:
        flag = " REQUIRED" if r.required else ""
        out.append(f"  {r.field:<34} {r.values:>5} values  {r.layers:>3} juris{flag}")
    if told:
        out.append("")
        out.append("UNREAD BUT DECLARED -- the screen names these as left out")
        for r in told:
            out.append(
                f"  {r.field:<34} {r.values:>5} values  <- {', '.join(r.declared)}"
            )
    if not unreached_only:
        out.append("")
        out.append("REACHED")
        for r in lit:
            out.append(f"  {r.field:<34} {r.values:>5} values  <- {', '.join(r.readers)}")
        if idle:
            out.append("")
            out.append("REGISTERED, NEVER ENCODED, NEVER READ")
            out.append("  " + ", ".join(r.field for r in idle))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dark", action="store_true", help="only the unreached fields")
    args = ap.parse_args(argv)
    print(render(reach(), unreached_only=args.dark))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
