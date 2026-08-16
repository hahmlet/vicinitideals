"""A record of which passages have already been read, so a long sweep can stop.

A county-scale sweep is hours of wall-clock against a local model, and hours is
long enough that something will interrupt it: a session ends, a GPU falls off
the bus, a box reboots. Without a journal every interruption costs the whole
run, which in practice means the run never happens and the sweep only ever gets
pointed at documents small enough to finish in one sitting.

The unit of resume is the chunk, and a chunk that found nothing is recorded just
as loudly as one that found six standards. An empty result is a real result --
most passages of a zoning chapter state nothing about a fourplex -- and a
journal that only remembered the hits would re-read every empty passage on every
resume and never converge.

The configuration is written into the journal's first line and checked on
resume. This is the point of the file. Recall is only comparable between runs of
the same shape, so a dense run that silently inherited half a wide run's answers
would report a number that describes neither, and nothing downstream could tell.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from flats.encode.sweep.ask import Finding
from flats.encode.sweep.chunk import Chunk


@dataclass(frozen=True, slots=True)
class Setup:
    """The shape of a run. Two journals may only be joined if these match."""

    model: str
    size: int
    overlap: int
    context: int

    def as_json(self) -> dict[str, object]:
        return {"model": self.model, "size": self.size, "overlap": self.overlap,
                "context": self.context}


class Mismatch(RuntimeError):
    """Raised when a journal was written by a differently-shaped run."""


class Journal:
    """Append-only findings for one sweep configuration, keyed by chunk.

    Deliberately a flat file rather than anything cleverer. It is written from a
    process that may be killed at any moment, and a line-per-chunk append is the
    only write that is atomic enough to survive that without a database.
    """

    def __init__(self, path: Path, setup: Setup) -> None:
        self.path = Path(path)
        self.setup = setup
        self._done: dict[str, list[Finding]] = {}

    def open(self) -> int:
        """Load what a previous run got through. Returns the chunk count."""
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps({"setup": self.setup.as_json()}) + "\n")
            return 0

        with self.path.open(encoding="utf-8") as fh:
            for n, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    # A half-written last line is the normal shape of a killed
                    # process. Everything before it is still good.
                    continue
                if n == 0:
                    if row.get("setup") != self.setup.as_json():
                        raise Mismatch(
                            f"{self.path} was written by {row.get('setup')}, "
                            f"this run is {self.setup.as_json()} -- "
                            "use a different --tag rather than mixing them"
                        )
                    continue
                ref = str(row.get("chunk", ""))
                if not ref:
                    continue
                self._done[ref] = [
                    Finding(
                        document=str(f.get("document", "")),
                        line=int(f.get("line", 0)),
                        standard=str(f.get("standard", "")),
                        applies_to=str(f.get("applies_to", "")),
                        states=str(f.get("states", "")),
                        lenses=tuple(f.get("lenses", ())),
                    )
                    for f in row.get("found", [])
                    if isinstance(f, dict)
                ]
        return len(self._done)

    def has(self, chunk: Chunk) -> bool:
        return chunk.ref in self._done

    def get(self, chunk: Chunk) -> list[Finding]:
        return list(self._done.get(chunk.ref, ()))

    def put(self, chunk: Chunk, found: Iterable[Finding]) -> None:
        """Record one chunk's answer, on disk, before the next one is asked."""
        kept = list(found)
        self._done[chunk.ref] = kept
        row = {
            "chunk": chunk.ref,
            "document": chunk.document,
            "first": chunk.first,
            "last": chunk.last,
            "found": [
                {
                    "document": f.document,
                    "line": f.line,
                    "standard": f.standard,
                    "applies_to": f.applies_to,
                    "states": f.states,
                    "lenses": list(f.lenses),
                }
                for f in kept
            ],
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
            fh.flush()

    def findings(self, document: str = "") -> list[Finding]:
        """Everything journalled, optionally for one document."""
        out: list[Finding] = []
        for found in self._done.values():
            out.extend(f for f in found if not document or f.document == document)
        return out
