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

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from flats.encode.attach import unquoted
from flats.encode.corroborate import Finding, Verdict, check_layer, checkable
from flats.encode.find import passages
from flats.provenance.sources import authority_for, document_key, host_of
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.model import Layer, Value

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
    "unread",
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
    "unread": (
        "a stored document prints this answer and no reader will claim it — the "
        "cell reads \"15/04 feet\", the row is written for five housing types at "
        "once, the column header is a range. Open /flats/find and read the line"
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
    #: What the encoding believed, kept as a lead. A searcher told the answer is
    #: probably "10" finds the sentence stating 10 far faster than one reading a
    #: chapter cold, and a searcher who finds 15 instead has found something
    #: more valuable than a citation.
    believed: str = ""

    @property
    def action(self) -> str:
        return NEXT[self.cause].format(layer=self.layer, doc=self.detail or "<document>")

    def line(self) -> str:
        return f"  {self.cause:12} {self.zone:8} {self.field:28} {self.detail}"


def _lead(value: Value) -> str:
    """What the file claimed, printed the way a searcher would scan for it."""
    got = getattr(value, "value", None)
    return "" if got is None else str(got)


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


def gaps(
    layer: Layer,
    findings: Sequence[Finding],
    printed: Mapping[tuple[str, str], str] = MappingProxyType({}),
) -> list[Gap]:
    """Every unquoted value in a layer, with the cause behind it.

    Pure: the findings are handed in, so this is testable without a store, a
    document, or a network. ``printed`` is the loose search's answer — the
    first line in this layer's own documents that prints the value, where one
    does — and it exists to keep the largest cause honest. "Unsourced" sends
    somebody to hunt for a chapter, fetch it and declare it; that is the wrong
    afternoon entirely when the chapter is already in the store and the only
    thing missing is a person reading one line of it.
    """
    grouped: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        grouped.setdefault((finding.zone, finding.field), []).append(finding)
    declared = {document_key(d.url) for d in layer.code} - {None}
    out: list[Gap] = []
    unread = layer.unread()
    for zone, field in sorted(unquoted(layer)):
        value = unread[(zone, field)]
        url = value.prov.url
        if not authority_for(url).may_verify:
            # First, ahead of everything a document could say. A value citing
            # an aggregator cannot be signed however well it corroborates, and
            # attaching a quote to it would leave a value that reads cited,
            # reads confirmed, and points at somebody's transcription.
            out.append(Gap(layer.layer, zone, field, "unofficial", host_of(url), _lead(value)))
            continue
        if not checkable(field, value):
            # No finding was ever emitted for this field, so its silence says
            # nothing. Calling that unsourced would send somebody hunting for a
            # chapter that is very likely already in the store.
            kind = FIELDS[field].kind if field in FIELDS else "not in the field registry"
            out.append(Gap(layer.layer, zone, field, "uncheckable", kind, _lead(value)))
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
        if cause == "unsourced" and (zone, field) in printed:
            cause, detail = "unread", printed[(zone, field)]
        out.append(Gap(layer.layer, zone, field, cause, detail, _lead(value)))
    return sorted(out, key=lambda g: (CAUSES.index(g.cause), g.zone, g.field))


def printed_in(layer: Layer, store: ProvenanceStore) -> dict[tuple[str, str], str]:
    """Where each held-out value is printed, for the ones printed anywhere.

    One line per value: the best-ranked passage, which is the one whoever opens
    the hunt will be looking at first. The count is not kept — this decides
    which of two afternoons somebody is being sent on, and one line is enough
    to decide it.
    """
    documents = []
    for doc in layer.code:
        path = f"{layer.layer}/{doc.id}.txt"
        try:
            documents.append((path, store.load(path).text))
        except (ProvenanceError, OSError):
            continue
    out: dict[tuple[str, str], str] = {}
    for (zone, field), value in layer.unread().items():
        for path, text in documents:
            found, _ = passages(
                text,
                path=path,
                field=field,
                believed=value.value,
                zone=zone,
                limit=1,
                named=True,
            )
            if found:
                out[(zone, field)] = found[0].quote
                break
    return out


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


# --- the ledger ----------------------------------------------------------
#
# Reading a jurisdiction's gaps means corroborating every value against every
# stored document: forty seconds for Wilsonville, a minute for Gresham. That is
# fine for a command and impossible for a page, so the answer is written down
# once and read back many times.
#
# What makes a written answer safe is knowing when it stopped being true. The
# digest below is taken over exactly the inputs the answer depends on — the
# encoded values and the citations, nothing else — so a page can say "measured
# against a corpus that has since changed" instead of quietly showing last
# week's work list as though it were today's.

#: Where the ledger lives. Beside the rules rather than in the store: it is
#: derived from the encoding, and it changes when the encoding does.
LEDGER = Path(__file__).resolve().parents[1] / "config" / "gaps.json"


def digest(layers: Mapping[str, Layer]) -> str:
    """A hash of every encoded value and citation in the corpus.

    Not of the files: a comment, a reordering or a re-indent changes a file
    without changing a single answer, and a digest that moved for those would
    cry stale every time somebody tidied a YAML.
    """
    parts: list[str] = []
    for layer_id in sorted(layers):
        layer = layers[layer_id]
        queued: dict[str, dict[str, object]] = {}
        for w in layer.wanted:
            queued.setdefault(f"{w.zone} (unread)", {})[w.field] = w.value
        blocks = (
            [("(defaults)", layer.defaults)]
            + [(code, layer.zones[code].values) for code in sorted(layer.zones)]
            + [(zone, queued[zone]) for zone in sorted(queued)]
        )
        for zone, values in blocks:
            for name in sorted(values):
                value = values[name]
                for number in [value, *value.variants]:
                    key = "+".join(getattr(number, "key", ()) or ())
                    parts.append(
                        f"{layer_id}|{zone}|{name}|{key}|{number.value}|{number.prov.quote}"
                    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def snapshot(layers: Mapping[str, Layer], store: ProvenanceStore) -> dict:
    """Measure every layer's gaps and mis-attributed citations, once.

    Both in one pass because both read every stored document, and because they
    are two halves of the same question: a value with no citation and a value
    whose citation names the wrong section are equally unusable in front of a
    planner, and equally invisible to a review queue built on quotes.
    """
    from flats.encode.attribution import check as attribution_check

    out: dict = {"digest": digest(layers), "layers": {}}
    for layer_id in sorted(layers):
        layer = layers[layer_id]
        items = gaps(layer, read_layer(layer, store), printed_in(layer, store))
        wrong = [one for one in attribution_check(layer, store) if not one.agrees]
        out["layers"][layer_id] = {
            "misattributed": [
                {
                    "zone": one.zone,
                    "field": one.field,
                    "claimed": one.claimed,
                    "found": one.found,
                    "quote": one.quote,
                }
                for one in wrong
            ],
            "label": layer.label,
            "counts": by_cause(items),
            "gaps": [
                {
                    "zone": g.zone,
                    "field": g.field,
                    "cause": g.cause,
                    "detail": g.detail,
                    "believed": g.believed,
                    "action": g.action,
                }
                for g in items
            ],
        }
    return out


def read_ledger(path: Path | None = None) -> dict | None:
    """The written answer, or None where nobody has measured yet."""
    file = path or LEDGER
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Measure the corpus and write the ledger.

    Run after an encoding session, the way the page map is run after a fetch.
    """
    import argparse

    from flats.rules.loader import load_rules

    parser = argparse.ArgumentParser(prog="python -m flats.encode.gaps")
    parser.add_argument("--out", default=str(LEDGER), help="where to write the ledger")
    args = parser.parse_args(argv)

    layers = load_rules(strict=False)
    built = snapshot(layers, ProvenanceStore())
    Path(args.out).write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8", newline="")
    total = sum(len(one["gaps"]) for one in built["layers"].values())
    counts = {c: 0 for c in CAUSES}
    for one in built["layers"].values():
        for cause, count in one["counts"].items():
            counts[cause] += count
    print(f"{total} gap(s) across {len(built['layers'])} jurisdiction(s) -> {args.out}")
    for cause in CAUSES:
        if counts[cause]:
            print(f"  {cause:12} {counts[cause]:>4}  {NEXT[cause].split(chr(10))[0][:80]}")
    wrong = sum(len(one["misattributed"]) for one in built["layers"].values())
    print(f"\n{wrong} citation(s) name a section their quoted text is not in")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
