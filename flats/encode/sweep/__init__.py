"""Read a code document blind, and ask what FLATS has no name for.

Every other check in this system starts from the field registry: it takes a
standard FLATS knows about and asks whether the encoding holds it, whether the
citation resolves, whether a person has signed it. That loop cannot see a
standard the registry never declared — a requirement a city imposes on this
building for which there is no field, no gap, and therefore no trace.

This is the pass that runs the other way. A model reads the code without being
shown the encoding, says what the passage requires, and code compares that to
the registry. What maps to a field is coverage; what maps to nothing is the
question. The order matters: shown the encoding first, a model agrees with it.

Run it::

    python -m flats.encode.sweep or/multnomah/portland
"""

from flats.encode.sweep.ask import LENSES, Finding, Lens, Ollama, sweep
from flats.encode.sweep.audit import Hole, Report, field_for, judge, run, write
from flats.encode.sweep.chunk import Chunk, chunks

__all__ = [
    "LENSES",
    "Chunk",
    "Finding",
    "Hole",
    "Lens",
    "Ollama",
    "Report",
    "chunks",
    "field_for",
    "judge",
    "run",
    "sweep",
    "write",
]
