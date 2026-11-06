"""Which named street each street lot line lies on (FOLLOWUPS 147).

A maximum front setback is held on each of a lot's streets. A run of lot line
that turns from one street onto another under the corner test's angle, or
whose two longest directions are not the two streets, reads as one street on
geometry alone, and the building is then measured only from the nearer one:
Tigard 1S135DC02000 stands 15 ft from SW 91st Ave and well past the maximum
from SW Lincoln St. Steph's ruling (2026-10-09, one street name on one
unbroken run is a bend) makes the name the test, so the name is read here.

Each line takes the name most of its sample points read off Metro's
centreline abreast of them (:func:`flats.geom.corridor._fronted`), spelled by
:func:`flats.geom.street_class.street_key`, so ``N LOMBARD ST`` and
``NE LOMBARD ST`` are one street. A line no centreline runs beside -- a chord
of a rounded corner, a gap in the network -- reads None, and is unread, never
a street of its own name.
"""

from __future__ import annotations

import collections
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from flats.geom.corridor import STREET_CLASS, STREETS_KEY, Lines, _dataset_path, _fronted
from flats.geom.street_class import _samples, _street_label, street_key

#: RLIS's TYPE and FTYPE for an alley (quadfit s1): an alley is not a street,
#: and a lot line beside both must not take the alley's name.
_ALLEY_TYPE = 1600
_ALLEY_FTYPE = "ALY"


def _is_alley(props: dict[str, Any]) -> bool:
    if str(props.get("FTYPE") or "").strip().upper() == _ALLEY_FTYPE:
        return True
    try:
        return int(props.get("TYPE")) == _ALLEY_TYPE
    except (TypeError, ValueError):
        return False


def load(sources: Path) -> Lines | None:
    """The snapshot's RLIS street centrelines with their names, or None where
    the snapshot holds none."""
    from shapely.geometry import shape

    from flats.ingest.delta import iter_features

    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    path = _dataset_path(sources, manifest, STREETS_KEY)
    if not path.is_file():
        return None
    lines, names = [], []
    for f in iter_features(path):
        props = f.get("properties") or {}
        if not f.get("geometry") or _is_alley(props):
            continue
        lines.append(shape(f["geometry"]))
        names.append(_street_label(props))
    return Lines.build(lines, names)


def line_name(edge: Sequence[Any], streets: Lines) -> str | None:
    """The street one lot line lies on: the name most of its sample points
    read. None where none reads a name; on a tie, the first read."""
    got = _samples([float(v) for v in edge[:4]])
    if got is None:
        return None
    points, own = got
    read: collections.Counter[str] = collections.Counter()
    for p in points:
        s = _fronted(p, own, streets)
        name = street_key(streets.names[s]) if s is not None else ""
        if name:
            read[name] += 1
    return read.most_common(1)[0][0] if read else None


def read(edges: Iterable[Sequence[Any]], streets: Lines) -> list[list[Any]]:
    """Every street line of one lot (s4's ``[x1, y1, x2, y2, cls]``) as
    ``[x1, y1, x2, y2, name]``, for :func:`flats.ingest.quadfit.lot_from_row`
    to find by the line's coordinates. The name None where unread."""
    return [
        [*e[:4], line_name(e, streets)]
        for e in edges
        if len(e) >= 5 and e[4] == STREET_CLASS
    ]
