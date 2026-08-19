"""Facts a value's own footnotes turn on, which nothing measures yet.

A number can be read correctly, cited exactly, signed by a human, and still
not be the answer, because a sentence under the table says something the
screen cannot evaluate. Oregon City prints "public utility easements may
supersede the minimum setback" beneath every dimensional table in Title 17:
the sentence is plain, and no easement layer exists for Clackamas County. The
disposition register calls that ``unmeasured`` -- read, understood, waiting on
data -- and stops it blocking the encoding, which is right. What it must not
do is stop there, because the value then sails through resolution looking
exactly like one nothing qualifies.

This is the join that keeps that from happening. The encode side writes the
ledger (``python -m flats.encode.qualified --write-caps``); resolution reads
it and hands each affected standard the fact as a *lever*. From there the
existing machinery does the work with no special case: the fact is registered
with no assumption, so :func:`flats.score.configure.configure` lists it as
unknown, and a standard that turns on an unknown cannot be certified -- the
lot comes back UNKNOWN with the fact named, rather than GREEN.

It travels as a generated file rather than an import because the arrow between
these two halves points one way: encode reads rules, never the reverse. The
file being stale is the failure mode, so a test regenerates it and compares.

Absent file means an empty ledger. A checkout with no encoding work in it
resolves; it simply caps nothing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

#: Written by ``flats.encode.qualified``. Layer -> zone -> field -> facts.
LEDGER = Path(__file__).resolve().parents[1] / "config" / "caps.json"


@lru_cache(maxsize=1)
def _ledger(path: str = "") -> dict[str, dict[str, dict[str, tuple[str, ...]]]]:
    file = Path(path) if path else LEDGER
    if not file.exists():
        return {}
    raw = json.loads(file.read_text(encoding="utf-8"))
    return {
        layer: {
            zone: {field: tuple(facts) for field, facts in fields.items()}
            for zone, fields in zones.items()
        }
        for layer, zones in raw.items()
    }


def caps_for(layer: str, zone: str) -> dict[str, tuple[str, ...]]:
    """Per field, the unmeasured facts its footnotes turn on.

    Keyed by the layer the value was *encoded* in, not the one being resolved:
    a city inheriting a county standard inherits the county's footnotes with
    it, and the resolver applies these against whichever layer supplied each
    number.
    """
    return _ledger().get(layer, {}).get(zone, {})


def layers() -> tuple[str, ...]:
    """Layers carrying at least one capped value."""
    return tuple(sorted(_ledger()))


def reload() -> None:
    """Forget the cached ledger. For tests and for the writer."""
    _ledger.cache_clear()
