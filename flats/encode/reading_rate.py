"""How often does reading it again find something?

Every defence in this project is a claim about a rate. "Blind re-reads catch
the errors no ledger can see" is one, and until now it has been kept the way
an anecdote is kept -- in the docstring of whichever module the re-read
produced, phrased as a story about the day it ran. A defence is only worth
something with a denominator attached, and a denominator nobody but its author
can find is not attached to anything.

So: read the committed answer sheets back and publish the arithmetic. Seven
blind re-reads have run, each one is a CSV in ``data/flats/``, and every
number below is recomputed from those files rather than quoted from prose.

**Two rates, never one.** The seven runs asked two different questions and
averaging them produces a figure that means nothing:

* **accuracy** -- re-read something we had already written down and asked *is
  this wrong?* The population is our own encodings.
* **completeness** -- read lines nobody had read and asked *did we miss
  something?* The population is the code, not our file.

A single "discrepancy rate" over both would divide errors by a denominator
that is mostly not errors' population at all.

**A flag is the second reader's claim, not a confirmed error**, and the
difference is large enough to matter. The dismissal run flags 71 cards; the
adjudication that followed it -- recorded in :mod:`flats.encode.stale` --
confirmed **three**. Publishing 71 as an error count would be the inflated
metric this project has already been caught by once, and publishing 3 as the
flag count would hide the work. Both are printed, and which is which is said
out loud.

**Where each run's threshold comes from.** The verdict vocabularies differ per
run because the questions did, so a spec below cannot be inferred -- it is a
reading of that run's own scoring code, and the comment on each says which.
The one that matters most is the dismissal run: a bare ``disagree`` there is
not a discrepancy. Waving away a *relaxation* costs lots and never
correctness, which is the trade this project makes everywhere; only
``alarming`` -- the reader says the note reaches us *and* makes a standard
stricter -- is the corner that can call a lot GREEN when it is not. That is
139 rows against 71.

Run::

    python -m flats.encode.reading_rate
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

#: Where the committed answer sheets live.
READINGS = Path(__file__).resolve().parents[2] / "data" / "flats"


def _is(field: str, *values: str) -> Callable[[dict[str, str]], bool]:
    """Row predicate: ``field`` holds one of ``values``."""
    wanted = {v.lower() for v in values}
    return lambda row: (row.get(field) or "").strip().lower() in wanted


def _isnt(field: str, *values: str) -> Callable[[dict[str, str]], bool]:
    unwanted = {v.lower() for v in values}
    return lambda row: (row.get(field) or "").strip().lower() not in unwanted


@dataclass(frozen=True, slots=True)
class Spec:
    """One blind re-read, and how to count it."""

    stem: str
    #: ``accuracy`` -- was what we wrote wrong? ``completeness`` -- did we miss
    #: something? Never summed across the two.
    asks: str
    #: What the run re-read, in words, for the report.
    subject: str
    #: Cards that produced an answer. A card the reader never reached is not a
    #: card that agreed, and folding the two would flatter the rate.
    scored: Callable[[dict[str, str]], bool]
    #: Cards where the reader's answer differs from what we held.
    flagged: Callable[[dict[str, str]], bool]
    #: Confirmed real after adjudication, where an adjudication is on record,
    #: with the module that holds it. ``None`` where nobody has adjudicated --
    #: which is not zero and must not print as zero.
    confirmed: tuple[int, str] | None = None


SPECS: tuple[Spec, ...] = (
    Spec(
        stem="second_reading_2026_09_07",
        asks="accuracy",
        subject="encoded numbers, re-read without the answer",
        # `unread` and `unscored` never produced an answer. `agree_alt` is
        # agreement: the reader named a different but equally correct spelling
        # of the same standard -- see flats.encode.reread.
        scored=_isnt("verdict", "unread", "unscored"),
        flagged=_is("verdict", "disagree"),
    ),
    Spec(
        stem="footnote_reading_2026_09_07",
        asks="accuracy",
        subject="footnotes, against the numbers they qualify",
        scored=_isnt("verdict", "unread"),
        flagged=_is("verdict", "disagree"),
    ),
    Spec(
        stem="dismissal_reading_2026_09_07",
        asks="accuracy",
        subject="footnotes we had waved away",
        scored=lambda row: True,
        # NOT `disagree`. See the module docstring: only the stricter corner
        # can buy a false GREEN, and `alarming` is exactly that corner in
        # flats.encode.waved's own scoring.
        flagged=_is("alarming", "true"),
        confirmed=(3, "flats.encode.stale"),
    ),
    Spec(
        stem="stale_reasons_2026_09_07",
        asks="accuracy",
        subject="dismissal reasons that argue about our own corpus",
        scored=lambda row: True,
        flagged=_is("verdict", "contradicted"),
    ),
    Spec(
        stem="missed_reading_2026_09_07",
        asks="completeness",
        subject="unread lines stating a standard",
        scored=lambda row: True,
        flagged=_is("outcome", "encode"),
    ),
    Spec(
        stem="missed_reading_2026_09_08",
        asks="completeness",
        subject="unread lines, second pass",
        scored=_isnt("verdict", ""),
        flagged=_is("binds", "yes"),
    ),
    Spec(
        stem="chapter_reading_2026_09_08",
        asks="completeness",
        subject="whole sections nobody had quoted",
        scored=_isnt("verdict", ""),
        flagged=_is("binds", "yes"),
    ),
)


@dataclass(frozen=True, slots=True)
class Reading:
    """One run's arithmetic."""

    stem: str
    asks: str
    subject: str
    read: int
    flagged: int
    confirmed: tuple[int, str] | None

    @property
    def date(self) -> str:
        """The run date, off the end of the filename it is stored under."""
        tail = self.stem.rsplit("_", 3)[-3:]
        return "-".join(tail) if len(tail) == 3 else ""

    @property
    def rate(self) -> float:
        return self.flagged / self.read if self.read else 0.0


def readings(root: Path | None = None) -> list[Reading]:
    """Recompute every run from its committed answer sheet.

    A missing file is skipped rather than counted as zero: a run that was
    never stored is not a run that found nothing, and the distinction is the
    same one :func:`flats.rules.ledger.read_coverage` draws between ``None``
    and an empty list.
    """
    base = root or READINGS
    out: list[Reading] = []
    for spec in SPECS:
        path = base / f"{spec.stem}.csv"
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                rows = [r for r in csv.DictReader(fh)]
        except OSError:
            continue
        scored = [r for r in rows if spec.scored(r)]
        out.append(
            Reading(
                stem=spec.stem,
                asks=spec.asks,
                subject=spec.subject,
                read=len(scored),
                flagged=sum(1 for r in scored if spec.flagged(r)),
                confirmed=spec.confirmed,
            )
        )
    return out


def render(runs: Iterable[Reading]) -> list[str]:
    """The published lines. Per run, and per question -- never one total."""
    runs = list(runs)
    if not runs:
        return []

    lines = ["", "BLIND RE-READS — what reading it again found:", ""]
    for asks, label in (
        ("accuracy", "was what we wrote wrong?"),
        ("completeness", "did we miss something?"),
    ):
        group = [r for r in runs if r.asks == asks]
        if not group:
            continue
        read = sum(r.read for r in group)
        flagged = sum(r.flagged for r in group)
        pct = flagged / read * 100 if read else 0.0
        lines.append(f"  {asks.upper()} — {label}")
        for r in group:
            extra = ""
            if r.confirmed:
                n, where = r.confirmed
                extra = f"  → {n} confirmed real ({where})"
            lines.append(
                f"    {r.date}  {r.read:>5,} read  {r.flagged:>4,} flagged"
                f"  {r.rate * 100:5.2f}%  {r.subject}{extra}"
            )
        lines.append(f"    {'':10}  {read:>5,} read  {flagged:>4,} flagged  {pct:5.2f}%")
        lines.append("")

    lines.append(
        "  A flag is the second reader's claim, not a confirmed error. Where an\n"
        "  adjudication has run it is named above; where none has, the flag count\n"
        "  is the honest ceiling and the confirmed count is unknown, not zero."
    )
    return lines


def main() -> int:
    runs = readings()
    if not runs:
        print("No reading sheets in data/flats/. Nothing to report.")
        return 1
    for line in render(runs):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
