"""Verbatim source text behind every encoded number, and the drift watch on it.

``store`` keeps the fetched code text and its hash; ``staleness`` turns a
changed hash into demoted values at load time. **No status is ever written to
the rule YAML** — staleness is derived on every load, never persisted, so a
derived answer can never disagree with a stored one.

``repoint`` is the one module here that does write to the rule files, and the
distinction is worth stating because it looks like an exception and is not. It
never writes a *status*. It rewrites a *pointer*: when a republished chapter
gains a line, the words a citation names are still there and only their line
number moved, so the quote follows them. Judgement is untouched — a value whose
cited words actually changed is reported and left exactly as it was, for a
person to read.
"""

from flats.provenance.repoint import (
    LineMap,
    Move,
    Stranded,
    line_map,
    move_quote,
    repoint_files,
    survivors,
)
from flats.provenance.staleness import (
    EVIDENCE_MISSING,
    SOURCE_CHANGED,
    Staleness,
    apply_staleness,
)
from flats.provenance.store import (
    STORE_ROOT,
    Document,
    DriftResult,
    Fetcher,
    ProvenanceError,
    ProvenanceStore,
    QuoteRef,
    check_drift,
    parse_quote,
    sha256,
)

__all__ = [
    "EVIDENCE_MISSING",
    "SOURCE_CHANGED",
    "STORE_ROOT",
    "Document",
    "DriftResult",
    "Fetcher",
    "LineMap",
    "Move",
    "ProvenanceError",
    "ProvenanceStore",
    "QuoteRef",
    "Staleness",
    "Stranded",
    "apply_staleness",
    "check_drift",
    "line_map",
    "move_quote",
    "parse_quote",
    "repoint_files",
    "sha256",
    "survivors",
]
