"""Everything somebody read and decided not to encode.

The two ledgers count what is missing. Neither counts what was *declined*, and
a declined standard looks exactly like one nobody found. The corpus is full of
these decisions and they are all correct at the moment they are written --
"note E lets coverage rise ten percent where multiple buildings share a lot,
and nothing here counts buildings", "7.0512 does not reach this building",
"the row prints 4,356 sq ft and means something else". Each is a sentence of
prose in a ``notes`` field, and prose is not counted by anything.

The failure that motivated this is small and instructive. A test docstring said
Table 4.0430's cells "wrap across a dozen lines each and the extraction shifts
fragments between columns; the setback rows in particular cannot be assigned to
a district by reading the text. Encoding them from this document would be a
guess wearing a citation." That was true when written. Four of the table's
seven columns were encoded from those exact lines afterwards, by somebody who
did not know the refusal existed, and the refusal sat there for weeks reading
like a live constraint. Nothing flagged it, because nothing was looking.

So: enumerate them. This does not judge a refusal and cannot -- a refusal is a
reading, and re-reading it is a human act. What it does is make the set
countable, so that adding one is a visible act and so that a reviewer can walk
the list instead of discovering an entry by accident.

It reads prose, because refusals are prose. That is the weakness and it is
stated rather than hidden: the marker is the phrase "not encoded" in any
casing, some matches are back-references to a refusal rather than refusals, and
the span shown is a window rather than a parse. Over-reporting is the safe
direction here for the same reason it is everywhere else in this subsystem.
The durable fix is a declared field on the model, which is a schema change to
sixteen files and is not this.

Three places are searched, because the corpus uses all three:

* **notes** -- layer and zone ``notes``, read from the loaded model rather than
  the file, so a phrase a YAML folded scalar broke across two lines is still
  found.
* **comments** -- ``#`` lines in the jurisdiction YAML, which the model drops.
* **tests** -- ``flats/tests``, because the refusal that prompted this module
  lived in a test docstring and not in the rules at all.

Run it::

    uv run python -m flats.encode.refusals
    uv run python -m flats.encode.refusals --layer or/multnomah/gresham
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from flats.rules.loader import CONFIG_ROOT, load_rules

#: The phrase every declared refusal in this corpus is written with. Matched
#: case-insensitively and across whitespace, so a folded YAML scalar that broke
#: it over a line ending is still one match.
MARKER = re.compile(r"not\s+encoded", re.IGNORECASE)

#: How much of the sentence around a marker to show. A window, not a parse --
#: enough to judge whether the refusal still holds without opening the file.
WINDOW = 320
#: Characters that must pass before a full stop is allowed to end the window.
#: "NOT ENCODED, on purpose." is a header, not a refusal.
FLOOR = 120

TESTS = Path(__file__).resolve().parents[1] / "tests"


@dataclass(frozen=True, slots=True)
class Refusal:
    """One declared decision not to encode something."""

    #: Where it was found: "notes", "comments" or "tests".
    kind: str
    #: Layer id for the first two kinds; the test file's name for the third.
    where: str
    #: Zone code, where the refusal sits on one zone rather than the layer.
    zone: str | None
    text: str

    @property
    def label(self) -> str:
        return f"{self.where}:{self.zone}" if self.zone else self.where


def _spans(text: str) -> Iterable[str]:
    """Each marker in `text`, with the run of prose that follows it.

    Cut at the first sentence end at least ``FLOOR`` characters past the
    marker, or at ``WINDOW`` characters, whichever comes first. The floor is
    what makes the window readable: half the corpus writes "NOT ENCODED, on
    purpose. (1) ..." and cutting at the nearest full stop would report the
    header and drop the refusal. Whitespace is collapsed so a folded scalar and
    a block scalar read the same.
    """
    flat = " ".join(text.split())
    for match in MARKER.finditer(flat):
        tail = flat[match.start() : match.start() + WINDOW]
        stop = re.search(r"(?<=[.!?])\s+(?=[A-Z(])", tail[FLOOR:])
        if stop:
            tail = tail[: FLOOR + stop.start() + 1]
        yield tail.strip()


def from_notes(layer_id: str | None = None) -> list[Refusal]:
    """Refusals in layer and zone ``notes``, read from the loaded model.

    The model rather than the file on purpose: a YAML folded scalar can break
    "not encoded" across a line ending, which the file does not contain and the
    model does.
    """
    out: list[Refusal] = []
    for name, layer in sorted(load_rules().items()):
        if layer_id and name != layer_id:
            continue
        for text in _spans(layer.notes or ""):
            out.append(Refusal("notes", name, None, text))
        for code, zone in sorted(layer.zones.items()):
            for text in _spans(zone.notes or ""):
                out.append(Refusal("notes", name, code, text))
    return out


def from_comments(layer_id: str | None = None) -> list[Refusal]:
    """Refusals written as ``#`` comments, which the model never sees.

    Attributed to the file rather than the zone. Walking back up the file to
    find the enclosing zone would be a guess about indentation, and a wrong
    attribution is worse than a coarse one.
    """
    out: list[Refusal] = []
    for path in sorted(CONFIG_ROOT.rglob("*.yaml")):
        name = path.relative_to(CONFIG_ROOT).with_suffix("").as_posix()
        if layer_id and name != layer_id:
            continue
        block: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                block.append(stripped.lstrip("#").strip())
                continue
            if block:
                out.extend(
                    Refusal("comments", name, None, text)
                    for text in _spans(" ".join(block))
                )
                block = []
        if block:
            out.extend(
                Refusal("comments", name, None, text) for text in _spans(" ".join(block))
            )
    return out


def from_tests() -> list[Refusal]:
    """Refusals recorded in test prose.

    Included because the one that prompted this module lived here and nowhere
    else, which meant it governed nothing, was checked by nothing, and still
    read as a live constraint to anyone who opened the file.

    Docstrings only, via the AST. Scanning the file whole would report the
    assertion that checks a refusal alongside the refusal itself, and a ledger
    whose rows are half quoted source is a ledger nobody finishes reading.
    """
    out: list[Refusal] = []
    for path in sorted(TESTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            for text in _spans(ast.get_docstring(node) or ""):
                out.append(Refusal("tests", path.name, None, text))
    return out


def refusals(layer_id: str | None = None) -> list[Refusal]:
    """Every declared refusal, in all three places, deduplicated on text."""
    rows = from_notes(layer_id) + from_comments(layer_id)
    if not layer_id:
        rows += from_tests()
    seen: set[tuple[str, str | None, str]] = set()
    out: list[Refusal] = []
    for row in rows:
        key = (row.where, row.zone, row.text)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def render(rows: Sequence[Refusal]) -> str:
    lines: list[str] = []
    for kind in ("notes", "comments", "tests"):
        group = [r for r in rows if r.kind == kind]
        if not group:
            continue
        lines.append(f"\n--- {kind} ({len(group)}) ---\n")
        for row in group:
            lines.append(f"  {row.label}")
            lines.append(f"      {row.text}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layer", help="Restrict to one jurisdiction.")
    ap.add_argument("--quiet", action="store_true", help="Counts only.")
    args = ap.parse_args(argv)

    rows = refusals(args.layer)
    if not args.quiet:
        print(render(rows))
    counts = {k: sum(1 for r in rows if r.kind == k) for k in ("notes", "comments", "tests")}
    print(
        f"\nrefusals={len(rows)}  "
        + "  ".join(f"{k}={v}" for k, v in counts.items())
        + "\n\n  A refusal is a reading, and nothing here judges one. What this "
        "counts is\n  how many readings are standing that no ledger would ever "
        "revisit."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
