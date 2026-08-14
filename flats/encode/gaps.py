"""Why an unquoted value is unquoted, and what would actually unstick it.

Every jurisdiction in the corpus sits on the ``unquoted`` rung of the readiness
ladder, and the ladder's advice for that rung is to run
:mod:`flats.encode.attach`. Run against all 41 stored documents, attach offers
nothing: it has already taken every citation it is willing to take. The ladder
is pointing at a command that cannot help, which is worse than pointing at
nothing — it reads as work remaining when the work is finished.

That is a framework hole, not an encoding one. ``unquoted`` is not one state,
it is eight, and they need opposite things:

``unofficial``   the value cites a third party restating the code — an
                 aggregator, a form, a landing page. No fetch and no reviewer
                 can rescue it; the citation itself is what is wrong.
``quotable``     a document states this number, cleanly, for this zone. attach
                 can write the citation. If any survive here, attach's refusals
                 and this module's reading of them disagree, which is a bug in
                 one of the two.
``contested``    a document states a *different* number. Nothing may be
                 attached and nothing may be signed until a person reads both.
``conditional``  the number is qualified: footnoted, or printed in one column
                 of a table banded by lot size. It needs encoding as a
                 variant, not a citation stapled to one half.
``multi``        the document states more than one number for the field, for
                 the same reason.
``undeclared``   the value names a document and ``code:`` does not, so nothing
                 has ever fetched it. Usually one line and a fetch; sometimes
                 the sign that the citation points at something that is not the
                 code at all — of the fifty-one this first caught, fifty were
                 a model-home application form and a Title 17 index page
                 standing in for chapters already in the store.
``unsourced``    no stored document states it and the value names no chapter
                 that would. The next action is to find the chapter — or to
                 admit the value came from the quadfit port with nothing behind
                 it and delete it.
``uncheckable``  a boolean, an enum or a curve. Corroboration emits no finding
                 for these at all, so their silence is not evidence of anything
                 and only a person can cite them.

The last three are what matter at corpus scale, because from inside the ladder
they look identical to each other and to everything above them. Splitting them
turned "385 values nothing supports" into 51 waiting on a chapter already named
on the value, 96 fields no reader was ever going to have an opinion about, and
180 genuinely unsourced — three different afternoons, only one of them long.

``unofficial`` is the one that is not about workload. Forty-one values cite a
zoning aggregator's restatement of the code. They corroborate, they would
attach cleanly, and signing one would put a reviewer's name on somebody's
transcription. :func:`flats.provenance.sources.authority_for` has always known
this; until now nothing asked it.

Run::

    python -m flats.encode.review gaps --layer or/multnomah
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from flats.encode.attach import unquoted
from flats.encode.corroborate import Finding, Verdict, check_layer, checkable
from flats.provenance.sources import authority_for, document_key, host_of
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.model import Layer

#: Worst first. A value is reported under the first cause that fits any
#: document, so a single disagreement outranks four agreements: attaching a
#: quote from the agreeing chapter would bury the one finding a person has to
#: resolve.
CAUSES = (
    "unofficial",
    "contested",
    "quotable",
    "conditional",
    "multi",
    "undeclared",
    "unsourced",
    "uncheckable",
)

NEXT = {
    "unofficial": (
        "re-cite against the adopted text — this citation is a third party's "
        "restatement, and no reviewer may sign it"
    ),
    "contested": "read both: the file and the document state different numbers",
    "quotable": "python -m flats.encode.attach {layer} --doc {doc} --apply",
    "conditional": (
        "encode as a variant — the document qualifies this number, by footnote "
        "or by the lot sizes the column was written for"
    ),
    "multi": "encode as variants — the document states more than one number",
    "undeclared": (
        "the value names a document nothing has fetched — declare that URL under "
        "`code:`, or re-cite it if that URL is not the adopted code: the two this "
        "cause first caught were a model-home application form and a title index "
        "page, neither of which states a standard"
    ),
    "unsourced": (
        "no stored document states this. Find the chapter that does, declare it "
        "under `code:`, and fetch — or delete a value nothing backs"
    ),
    "uncheckable": (
        "python -m flats.encode.review show {layer} — a boolean or an enum, which "
        "no reader can corroborate: quote it by hand"
    ),
}


@dataclass(frozen=True, slots=True)
class Gap:
    """One unquoted value, why it is unquoted, and where that was decided."""

    layer: str
    zone: str
    field: str
    cause: str
    detail: str = ""

    @property
    def action(self) -> str:
        return NEXT[self.cause].format(layer=self.layer, doc=self.detail or "<document>")

    def line(self) -> str:
        return f"  {self.cause:12} {self.zone:8} {self.field:28} {self.detail}"


def _cause(finding: Finding) -> tuple[str, str] | None:
    """What one document says about one value, as a cause and a detail.

    ``None`` where the document says nothing about it, which is the common
    case: most documents in a jurisdiction do not mention most of its fields.
    """
    if finding.verdict is Verdict.differs:
        found = ", ".join(str(v) for v in finding.found) or "-"
        return "contested", f"file {finding.encoded}, document {found}"
    if finding.verdict is Verdict.unsupported:
        # Unsupported with numbers behind it is the conditional-only case: the
        # document states figures for this field, all of them scoped by a
        # footnote or an adjustment clause, none of them the base standard.
        # That is a reading somebody has to make, not a missing chapter.
        if not finding.found:
            return None
        return "conditional", ", ".join(str(v) for v in finding.found)
    if finding.verdict is not Verdict.agrees:
        return None
    if finding.conditional:
        return "conditional", finding.notes[0][:60]
    if len(finding.found) > 1:
        return "multi", ", ".join(str(v) for v in finding.found)
    return "quotable", finding.quote


def classify(findings: Iterable[Finding]) -> tuple[str, str]:
    """One value's findings across every document, as a single cause.

    Findings from different documents are read together on purpose. A number
    that agrees in the zoning chapter and disagrees in the overlay chapter is
    contested, and reading each document alone is how that stays invisible.
    """
    best: tuple[str, str] | None = None
    for finding in findings:
        cause = _cause(finding)
        if cause is None:
            continue
        if best is None or CAUSES.index(cause[0]) < CAUSES.index(best[0]):
            best = cause
    return best or ("unsourced", "")


def gaps(layer: Layer, findings: Sequence[Finding]) -> list[Gap]:
    """Every unquoted value in a layer, with the cause behind it.

    Pure: the findings are handed in, so this is testable without a store, a
    document, or a network.
    """
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        grouped.setdefault((finding.zone, finding.field), []).append(finding)
    declared = {document_key(d.url) for d in layer.code} - {None}
    out: list[Gap] = []
    for zone, field in sorted(unquoted(layer)):
        value = layer.zones[zone].values[field]
        url = value.prov.url
        if not authority_for(url).may_verify:
            # First, ahead of everything a document could say. A value citing
            # an aggregator cannot be signed however well it corroborates, and
            # attaching a quote to it would leave a value that reads cited,
            # reads confirmed, and points at somebody's transcription.
            out.append(Gap(layer.layer, zone, field, "unofficial", host_of(url)))
            continue
        if not checkable(field, value):
            # No finding was ever emitted for this field, so its silence says
            # nothing. Calling that unsourced would send somebody hunting for a
            # chapter that is very likely already in the store.
            kind = FIELDS[field].kind if field in FIELDS else "not in the field registry"
            out.append(Gap(layer.layer, zone, field, "uncheckable", kind))
            continue
        cause, detail = classify(grouped.get((zone, field), ()))
        key = document_key(url)
        if cause == "unsourced" and key is not None and key not in declared:
            # Not missing — never fetched. The chapter is named on the value
            # itself and simply absent from `code:`, which is a one-line fix
            # and nothing like the hunt "unsourced" describes. `key is None`
            # is Municode, whose reader URL and fetchable URL share nothing:
            # unprovable, so unclaimed.
            cause, detail = "undeclared", url
        out.append(Gap(layer.layer, zone, field, cause, detail))
    return sorted(out, key=lambda g: (CAUSES.index(g.cause), g.zone, g.field))


def read_layer(layer: Layer, store: ProvenanceStore) -> list[Finding]:
    """Corroborate a layer against every one of its stored documents.

    Documents that are declared and missing are skipped rather than raised on:
    an unfetched chapter is the ``unfetched`` rung's problem, and failing here
    would hide the causes of every other value in the jurisdiction.
    """
    out: list[Finding] = []
    for path in sorted(layer.documents()):
        try:
            doc = store.load(path)
        except (ProvenanceError, FileNotFoundError):
            continue
        out.extend(check_layer(doc.text, layer, path=path))
    return out


def by_cause(items: Iterable[Gap]) -> dict[str, int]:
    counts = {c: 0 for c in CAUSES}
    for gap in items:
        counts[gap.cause] += 1
    return {k: v for k, v in counts.items() if v}


def summarise(layers: Mapping[str, list[Gap]]) -> dict[str, int]:
    """Corpus-wide counts, for the one line that says where the work is."""
    counts = {c: 0 for c in CAUSES}
    for items in layers.values():
        for gap in items:
            counts[gap.cause] += 1
    return {k: v for k, v in counts.items() if v}
