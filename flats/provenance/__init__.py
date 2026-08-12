"""Verbatim source text behind every encoded number, and the drift watch on it.

``store`` keeps the fetched code text and its hash; ``staleness`` turns a
changed hash into demoted values at load time. Nothing here writes to the rule
YAML — staleness is derived on every load, never persisted.
"""

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
    "ProvenanceError",
    "ProvenanceStore",
    "QuoteRef",
    "Staleness",
    "apply_staleness",
    "check_drift",
    "parse_quote",
    "sha256",
]
