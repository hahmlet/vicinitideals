"""FLATS foundation model (FOLLOWUPS 209; FD6 build steps 1-7).

For one pod on one lot: how does each foundation sit on this ground, what does
it take, and what does it cost? Two foundations and one variant (FD6 section 1):

* **A, slab on fill** -- floor 8 in above the highest ground;
* **B, raised floor on a wall** -- floor 32.75 in above the highest ground;
* **B+P** -- B with screw piles under the wall instead of the footing.

Plain functions only: no database, no web, no import of ``app``. Settings and
prices live in ``flats/config/foundation.yaml`` with their source labels.

**It never changes a lot's colour.** Steps are counted, never capped [Steph
2026-11-19]; a flag never removes a lot. Nothing under ``flats/score`` reads
this package.

Modules: :mod:`.settings` (the YAML), :mod:`.ground` (``ground(x, y)``: six
readings or a cell grid), :mod:`.model` (floor level, walls, doors, slab on
fill), :mod:`.cost` (section 6, Decimal), :mod:`.support` (ground-support
groups), :mod:`.lot` (one lot's result). ``python -m flats.foundation
<lots.csv>`` runs a lot file in place and prints the section 8 shares.

Design: Factory-Sim ``docs/research/FD6-foundation-model-spec.md``; answer key
``FD6_foundation_model.py`` beside it.
"""

from flats.foundation.lot import LotResult, from_row, run_lot
from flats.foundation.settings import Settings, load

__all__ = ["LotResult", "Settings", "from_row", "load", "run_lot"]
