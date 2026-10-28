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


def _vias() -> list[tuple[str, str, str, str]]:
    """(layer, zone, field, via) for every cross-reference the corpus ships."""
    out = []
    for layer_id, layer in load_rules().items():
        for zone_code, zone in layer.zones.items():
            for field, value in zone.values.items():
                for number in (value, *value.variants):
                    if number.prov.via:
                        out.append((layer_id, zone_code, field, number.prov.via))
    return out


def test_every_cross_reference_resolves_to_lines_the_store_holds() -> None:
    """A `via` is shown boxed on the page check as the reason a number is read
    off another table (Steph 2026-10-22); one that points at nothing would
    show the reviewer an empty page as the evidence."""
    store = ProvenanceStore()
    vias = _vias()
    assert any(layer == "or/multnomah/gresham" for layer, *_ in vias)
    broken = []
    for layer_id, zone, field, via in vias:
        try:
            if not store.quote(via).strip():
                broken.append(f"{layer_id} {zone}.{field}: {via} resolves to blank")
        except ProvenanceError as exc:
            broken.append(f"{layer_id} {zone}.{field}: {exc}")
    assert not broken, "cross-references that do not resolve:\n" + "\n".join(broken)


def test_a_variant_quoting_its_own_text_does_not_inherit_the_base_cross_reference() -> None:
    gresham = load_rules()["or/multnomah/gresham"]
    front = gresham.zones["CMF"].values["setback_front_ft"]
    assert front.prov.via is None
    corridor = next(v for v in front.variants if v.when == ("civic_corridor",))
    assert corridor.prov.via == "or/multnomah/gresham/4.0400.corridor.txt#L485-L488"


def test_a_split_table_cell_carries_the_passage_that_splits_it() -> None:
    """Portland's Table 120-4 prints "5/10 ft." for RM3 side setbacks: the cell
    alone cannot say which half is ours, 33.120.220.B.1 does (Steph 2026-10-28,
    on the page check: "I don't know what that means"). Each half carries the
    other source, so the page check sets it aside for the two-source check."""
    portland = load_rules()["or/multnomah/portland"]
    side = portland.zones["RM3"].values["setback_side_ft"]
    low = next(v for v in side.variants if v.when == ("low_rise",))
    assert side.prov.via == low.prov.via == "or/multnomah/portland/33.120.txt#L543-L544"
    # A variant read off its own single page stays on the page check.
    alley = next(v for v in portland.zones["RM3"].values["setback_rear_ft"].variants if v.when == ("alley_at_rear",))
    assert alley.prov.via is None
