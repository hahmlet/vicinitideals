"""Find footnote reasons that answer a page they were never read on.

A footnote ruling binds to the **text** of the note rather than to its line:
``_join`` digests the sentence and looks the ruling up by that digest. So a
codifier who prints the same sentence under two tables gets one answer for
both, and a codifier who amends the sentence loses the answer. That is the
right design, it is what ``adopts:`` extends across layers, and it pays --
34 ruled sentences in this corpus appear in more than one document, and every
one of them was read once.

**But the digest carries the reason with it, and a reason can be about the
table rather than about the sentence.** Clackamas ZDO 510's note 11 is word for
word ZDO 315's note 6. The reason written for 315 read:

    a quadplex is already permitted outright in all nine districts, so the door
    is one this building has no need of

True of Section 315. False of Section 510, where NC and C-2 prohibit a quadplex
and that note -- the affordable-housing door -- is the only way back in. The
ruling was already answering Section 510's note 11, correctly by luck, with an
argument that does not hold there, before anybody had read Section 510.

``stale.py`` cannot see this. That check finds reasons arguing about **our
corpus**, which expire when somebody encodes a district. This one argues about
**the page**, which is exactly what the standing rule demands -- just a
different page than the one it landed on.

So this module asks one narrow question of every shared ruling: *does the
reason name only some of the documents its sentence appears in?* A reason that
names both tables is answering both. A reason that names one table, about a
sentence printed in two, is a claim whose scope is smaller than its reach.

Two verdicts, and both are reading queues rather than findings:

``partial``    the reason names a proper, non-empty subset of the documents
``shadowed``   two entries answer one sentence and they do not say the same
               thing, so only file order decides which reason is on the record

``shadowed`` is the same defect seen from the other side and it needs no
heuristic at all. ``_join`` builds ``by_digest`` last-wins, so a register
holding two rulings for one sentence keeps one and silently drops the other.
On the day this was written all nine such pairs agreed on the *state* -- no
conclusion was decided by file order -- but three kept a reason written about
one document and threw away the one written about another, and a fourth kept
an entry whose whole reason is "left here as a pointer only" over the entry
that said what was encoded and why. The cure for both verdicts is the same:
one reason, true everywhere the sentence is printed.

What is deliberately **not** flagged:

- a reason naming no document at all -- most reasons argue about what the
  sentence says, which travels correctly and is the shape to prefer;
- a reason naming a document the sentence does not appear in -- "subject to
  Section 846" is a cross-reference, not a scope claim;
- a reason naming every document the sentence appears in, which is the repair.
  The four rewrites of 2026-09-08 all read "in neither of the two use tables
  this sentence appears in is the marker printed on a dwelling row", and that
  sentence is checkable in both places.

The check cannot tell a scope claim from a citation, so it over-reports by
design in one direction: it can call a sound reason partial, and a person sees
that in a second. What it cannot do is miss a reason that names *a* table and
not the others, which is the shape that was found.

The residual is a reason that travels **naming nothing a number can match**.
Gresham's downtown rulings argued "the L1 in DCC and DTM" and "a bare P in all
six sub-districts" -- district codes, printed under one table, silently
governing two more. Nothing here sees that. What found those was ``shadowed``,
below, and it found them by accident.

Usage:
    uv run python -m flats.encode.travelled [--csv out.csv]
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from flats.encode.dispositions import Note, Ruling, digest, notes, rulings

#: How a document is named inside a reason. Three shapes, all of them ways this
#: corpus already writes a citation in prose: a table ("Table 510-1", "Table
#: 19.30.030.A.4"), a section or chapter ("Section 315", "Chapter 33.110"), and
#: a bare dotted code ("19.301.4"), which is how the city codes cite themselves.
_NAMED = re.compile(
    r"Table\s+(\d+[A-Za-z]?(?:[-.]\d+[A-Za-z]?)*)"
    r"|(?:Section|Chapter|Subsection)\s+(\d+(?:\.\d+)*)"
    r"|(?<![\w.\-])(\d{1,3}\.\d{2,4}(?:\.\d+)*)(?![\w.\-])"
)

#: The states that carry an argument. ``encoded`` is included because an
#: ``encoded_as`` ruling still takes a sentence off the queue, and ``unread``
#: is not, because it has not been answered at all.
_ARGUED = frozenset({"dismissed", "unmeasured", "encoded"})


@dataclass(frozen=True, slots=True)
class Travelled:
    layer: str
    #: sha1 prefix of the normalised sentence -- the key the ruling binds on.
    digest: str
    reason: str
    #: Every document the sentence is printed in, shortest name first.
    appears_in: tuple[str, ...]
    #: The subset of those the reason names.
    names: tuple[str, ...]
    #: One quote reference per document, so a reader can open both sides.
    quotes: tuple[str, ...] = ()

    @property
    def silent_on(self) -> tuple[str, ...]:
        """The documents the reason says nothing about, and reaches anyway."""
        return tuple(d for d in self.appears_in if d not in self.names)


def _stem(doc: str) -> str:
    """``or/x/y/zdo.510.txt`` -> ``zdo.510``. The name a reason would use."""
    return doc.rsplit("/", 1)[-1].removesuffix(".txt")


def _heads(stem: str) -> set[str]:
    """The numbers by which a document could be named in prose.

    ``zdo.510`` is cited as "Section 510" and its tables as "Table 510-1", so
    its head is ``510``. ``4.1400.pleasant-valley`` is cited as "Section
    4.1400", so its head is ``4.1400`` -- and *not* ``4``, which on its own
    would match every chapter in a city that numbers its whole code 4.xxxx and
    would quietly make every Gresham reason look like it named everything.

    What this cannot do is know that Gresham's *Table* 4.1413 is printed inside
    the chapter stored as ``4.1400.pleasant-valley``. Those two numbers differ
    in the component that decides, and joining them would take a map of which
    table lives in which chapter. So a reason that cites only a table number
    names no document here. That is a miss in the safe direction for the
    corpus (it under-names, so the reason looks narrower, so it flags) and a
    miss in the unsafe direction for a reason that cites tables from *every*
    document it reaches -- which nothing in this corpus does today.
    """
    parts = [p for p in stem.split(".") if any(c.isdigit() for c in p)]
    if not parts:
        return set()
    if len(parts) == 1:
        return {parts[0]}
    return {".".join(parts[:i]) for i in range(2, len(parts) + 1)}


def _named_docs(reason: str, stems: set[str]) -> set[str]:
    """Which of ``stems`` this reason names. Never invents a document."""
    found: set[str] = set()
    for match in _NAMED.finditer(reason):
        cited = next(g for g in match.groups() if g).split("-")[0]
        parts = cited.split(".")
        candidates = {".".join(parts[:i]) for i in range(1, len(parts) + 1)}
        for stem in stems:
            if candidates & _heads(stem):
                found.add(stem)
    return found


def audit(rows: list[Note] | None = None) -> list[Travelled]:
    """Every shared ruling whose reason covers only part of its own reach."""
    rows = list(notes()) if rows is None else rows
    grouped: dict[tuple[str, str], list[Note]] = defaultdict(list)
    for note in rows:
        if note.state in _ARGUED and (note.reason or "").strip():
            grouped[(note.layer, digest(note.text))].append(note)

    out: list[Travelled] = []
    for (layer, dg), group in sorted(grouped.items()):
        stems = {_stem(n.doc) for n in group}
        if len(stems) < 2:
            continue
        for reason in sorted({n.reason for n in group if n.reason}):
            named = _named_docs(reason, stems)
            if not named or named == stems:
                continue
            out.append(
                Travelled(
                    layer=layer,
                    digest=dg,
                    reason=reason,
                    appears_in=tuple(sorted(stems)),
                    names=tuple(sorted(named)),
                    quotes=tuple(sorted(f"{n.doc}#L{n.line}" for n in group)),
                )
            )
    return out


@dataclass(frozen=True, slots=True)
class Shadowed:
    layer: str
    digest: str
    #: Every entry answering this sentence, in the order the register holds
    #: them. The last one is the one ``_join`` keeps.
    entries: tuple[Ruling, ...]

    @property
    def kept(self) -> Ruling:
        return self.entries[-1]

    @property
    def dropped(self) -> tuple[Ruling, ...]:
        return self.entries[:-1]


def _said(ruling: Ruling) -> tuple[str, ...]:
    """What an entry decides, with the quote it was filed under left out.

    Two entries under one digest are not a problem -- a sentence printed under
    two tables is worth recording twice -- but two entries that *decide
    differently* are, because only one of them is read.
    """
    return (
        ruling.state,
        (ruling.reason or "").strip(),
        ruling.encoded_as or "",
        ruling.fact or "",
        " ".join(ruling.zones),
    )


def shadowed(decided: dict[str, list[Ruling]] | None = None) -> list[Shadowed]:
    """Digests answered more than once, where the answers differ."""
    decided = rulings() if decided is None else decided
    out: list[Shadowed] = []
    for layer, entries in sorted(decided.items()):
        grouped: dict[str, list[Ruling]] = defaultdict(list)
        for ruling in entries:
            grouped[ruling.digest].append(ruling)
        for dg, group in sorted(grouped.items()):
            if len(group) > 1 and len({_said(r) for r in group}) > 1:
                out.append(Shadowed(layer=layer, digest=dg, entries=tuple(group)))
    return out


def shared(rows: list[Note] | None = None) -> int:
    """How many ruled sentences are answered in more than one document.

    The exposure this check is about. It is not a problem -- it is the design
    working -- but a reader should see it beside the flags, because the flags
    are only the subset that named a table out loud.
    """
    rows = list(notes()) if rows is None else rows
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for note in rows:
        if note.state in _ARGUED:
            grouped[(note.layer, digest(note.text))].add(_stem(note.doc))
    return sum(1 for docs in grouped.values() if len(docs) > 1)


def render(
    found: list[Travelled],
    exposure: int | None = None,
    doubled: list[Shadowed] | None = None,
) -> str:
    out: list[str] = []
    if exposure is not None:
        out.append(f"{exposure} ruled sentences answered in more than one document")
    if not found:
        out.append("partial   0 -- no reason names only some of the documents it reaches")
    else:
        out.append(f"partial   {len(found)} reason(s) narrower than their own reach:")
        for row in found:
            out.append("")
            out.append(f"  {row.layer}  {row.digest}")
            out.append(f"    appears in : {', '.join(row.appears_in)}")
            out.append(f"    names only : {', '.join(row.names)}")
            out.append(f"    silent on  : {', '.join(row.silent_on)}")
            out.append(f"    reason     : {row.reason[:300]}")
    if doubled is None:
        return "\n".join(out)
    if not doubled:
        out.append("shadowed  0 -- no sentence is answered twice with two different answers")
        return "\n".join(out)
    out.append("")
    out.append(f"shadowed  {len(doubled)} sentence(s) answered twice, only the last read:")
    for row in doubled:
        out.append("")
        out.append(f"  {row.layer}  {row.digest}")
        out.append(f"    kept    : {row.kept.quote}")
        out.append(f"              {(row.kept.reason or row.kept.encoded_as)[:220]}")
        for gone in row.dropped:
            out.append(f"    dropped : {gone.quote}")
            out.append(f"              {(gone.reason or gone.encoded_as)[:220]}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Footnote reasons narrower than their reach")
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args(argv)
    rows = list(notes())
    found = audit(rows)
    doubled = shadowed()
    print(render(found, shared(rows), doubled))
    if args.csv:
        import csv

        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["verdict", "layer", "digest", "appears_in", "names", "silent_on", "quotes", "reason"]
            )
            for row in found:
                writer.writerow(
                    [
                        "partial",
                        row.layer,
                        row.digest,
                        " ".join(row.appears_in),
                        " ".join(row.names),
                        " ".join(row.silent_on),
                        " ".join(row.quotes),
                        row.reason,
                    ]
                )
            for pair in doubled:
                writer.writerow(
                    [
                        "shadowed",
                        pair.layer,
                        pair.digest,
                        "",
                        pair.kept.quote,
                        " ".join(g.quote for g in pair.dropped),
                        " ".join(g.quote for g in pair.entries),
                        pair.kept.reason or pair.kept.encoded_as,
                    ]
                )
        print("wrote", args.csv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
