"""Every citation the corpus ships has to resolve.

A quote is the one thing standing between a number in a YAML file and a
sentence in an ordinance. If it does not resolve, the number reads as sourced
while pointing at nothing — and the failure is silent, because a rule set
loads fine with a broken quote in it. Wilsonville shipped two whose line spans
descended, and nothing failed until the readiness ladder happened to look.

Two checks, deliberately separate:

*Parse.* A malformed or descending reference is an encoding mistake and is
always a failure, whether or not the document behind it has been fetched.

*Resolve.* A reference into a document the store holds must name lines that
document actually has. Documents nobody has fetched yet are skipped here —
that is the `unfetched` rung's job, not this test's.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import _quoted_parts
from flats.provenance.store import ProvenanceError, ProvenanceStore, parse_quote
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit


def _citations() -> list[tuple[str, str, str, str]]:
    """(layer, zone, field, quote) for every quote in the shipped corpus."""
    out: list[tuple[str, str, str, str]] = []
    for layer_id, layer in load_rules().items():
        for zone, field, quote, _, _drawn in _quoted_parts(layer):
            if quote:
                out.append((layer_id, zone, field, quote))
    return out


def test_every_shipped_quote_parses() -> None:
    """A reference that will not parse never had a chance of resolving."""
    broken = []
    for layer_id, zone, field, quote in _citations():
        try:
            parse_quote(quote)
        except ProvenanceError as exc:
            broken.append(f"{layer_id} {zone}.{field}: {exc}")

    assert not broken, "unparseable citations:\n" + "\n".join(broken)


def test_every_shipped_quote_resolves_where_the_document_is_stored() -> None:
    """The lines a citation names must exist in the document it names them in.

    Not "the text says the number" — that is corroboration, and the ladder
    checks it per jurisdiction. This is the weaker, absolute contract: the
    reviewer who follows the link is shown something.
    """
    store = ProvenanceStore()
    held = set(store.documents())
    broken = []
    for layer_id, zone, field, quote in _citations():
        try:
            path = parse_quote(quote).path
        except ProvenanceError:
            continue  # the parse test owns this one
        if path not in held:
            continue  # unfetched, which is a different rung
        try:
            if not store.quote(quote).strip():
                broken.append(f"{layer_id} {zone}.{field}: {quote} resolves to blank")
        except ProvenanceError as exc:
            broken.append(f"{layer_id} {zone}.{field}: {exc}")

    assert not broken, "citations that do not resolve:\n" + "\n".join(broken)
