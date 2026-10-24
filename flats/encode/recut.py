"""Re-cut a jurisdiction's section files, and carry everything that names them.

The section files are made by :mod:`flats.provenance.readable`, and every
change to that cleaning changes the files: lines join, split and renumber. A
citation is a line number, a reading ruling is a fingerprint over the lines it
read, and a page check or signature is a fingerprint over the citation. Left
alone, one improvement to the cleaning would quietly reopen all of it -- or,
worse, leave citations pointing at lines that now say something else.

So a re-cut is one step, done here:

1. **Before**, every stored section line is walked back to the proof-copy lines
   its letters came from (:func:`flats.provenance.sections.held` -- read from
   the file on disk, so it does not matter which cleaning made it).
2. The jurisdiction is cut again (:func:`flats.provenance.sections.write`).
3. **Citations move**: each cited line goes to the new lines holding the same
   proof-copy lines. A move is refused, and the citation left for a person,
   unless every span's words sit inside the new quote and the quote names the
   same printed pages.
4. **Readings carry**: a ruling whose card still stood is re-stamped when every
   line of the new card holds a line of the card that was ruled. Anything else
   comes back to be read again.
5. **Signatures, disputes and page checks**: their fingerprint hashes the
   quote, so each one standing on a moved quote is re-issued in the repository
   logs, and the database's (page checks, the signing inbox) are written to a
   carry file that ``scripts/flats_carry_answers.py`` applies in production.

Run it::

    uv run python -m flats.encode.recut or/clackamas/tualatin            # dry run
    uv run python -m flats.encode.recut or/clackamas/tualatin --write
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

from flats.encode import worklist
from flats.encode.dispute import LOG_PATH as DISPUTE_LOG
from flats.encode.dispute import Dispute, DisputeLog
from flats.encode.verify import LOG_PATH as VERIFY_LOG
from flats.encode.verify import Verification, VerificationLog, fingerprint
from flats.provenance import pages as page_map
from flats.provenance.repoint import _citations, config_files
from flats.provenance.sections import Rule, _spans, addresses, held, rules, split, write
from flats.provenance.store import ProvenanceError, ProvenanceStore, parse_quote
from flats.rules.loader import CONFIG_ROOT, load_rules

#: Where the carry files for production land, one per re-cut.
CARRY_DIR = Path(__file__).resolve().parents[2] / "data" / "flats" / "carry"

_SPAN = r"\d+(?:-L\d+)?"
_CITE = re.compile(
    rf"(?<![\w./-])(?P<dir>(?:[\w.-]+/)*)(?P<name>[\w.-]+\.txt)"
    rf"(?P<sep>#|\s)L(?P<spans>{_SPAN}(?:,\s*L{_SPAN})*)"
)


def _letters(lines: Sequence[str]) -> str:
    return re.sub(r"[\s-]", "", "".join(lines))


@dataclass
class Before:
    """What the section files said, and what stood on them, before the re-cut."""

    layer: str
    #: section path -> its stored lines
    text: dict[str, list[str]]
    #: section path -> per stored line, the proof-copy lines it holds
    held: dict[str, list[tuple[int, ...]]]
    #: section path -> its page map
    pages: dict[str, page_map.PageIndex | None]
    #: card key -> (fingerprint, per card line the proof-copy lines it holds)
    cards: dict[str, tuple[str, list[tuple[int, ...]]]]
    #: signable key -> (fingerprint, quote, payload, cite)
    signed: dict[tuple, tuple[str, str, object, str]]


@dataclass
class Report:
    moved: list[tuple[Path, str, str]] = field(default_factory=list)
    refused: list[tuple[Path, str, str]] = field(default_factory=list)
    carried: list[str] = field(default_factory=list)
    reread: list[tuple[str, str]] = field(default_factory=list)
    #: (key, old fingerprint, new fingerprint, old quote, new quote)
    reissued: list[tuple[tuple, str, str, str, str]] = field(default_factory=list)


def _signed(layer_id: str, layers: Mapping, paths: set[str]) -> dict[tuple, tuple[str, str, object, str]]:
    out = {}
    for path in sorted(paths):
        for key, payload, cite, quote in _citations({layer_id: layers[layer_id]}, path):
            out[key] = (
                fingerprint(*key[:3], payload, cite=cite, quote=quote, when=key[3]),
                quote,
                payload,
                cite,
            )
    return out


def first_cut(store: ProvenanceStore, rule: Rule) -> list[str]:
    """The fetched documents of a layer that a cut will split for the first time.

    A first cut moves citations off the fetched document itself. To the steps
    below it is a section file whose every line holds its own line, so the
    same words-and-pages check, reading carry and re-issue apply.
    """
    cut = store.proofs()
    out = []
    for file in sorted((store.root / rule.layer).glob("*.txt")):
        proof = f"{rule.layer}/{file.name}"
        if proof in cut or file.stem in rule.uncut or store.part_of(proof) is not None:
            continue
        if split(store.load(proof).text.splitlines(), rule, file.stem):
            out.append(proof)
    return out


def _proof_of(store: ProvenanceStore, path: str) -> str:
    part = store.part_of(path)
    return part.proof if part is not None else path


def snapshot(store: ProvenanceStore, layer_id: str, known: Mapping[str, Rule] | None = None) -> Before:
    parts = {p: part for p, part in store.parts().items() if part.layer == layer_id}
    text = {p: store.text_path(p).read_text(encoding="utf-8").splitlines() for p in parts}
    where = {p: held(store, p, known) for p in parts}
    rule = (known if known is not None else rules()).get(layer_id)
    for proof in first_cut(store, rule) if rule is not None else ():
        text[proof] = store.load(proof).text.splitlines()
        where[proof] = [(k,) for k in range(1, len(text[proof]) + 1)]
    layers = load_rules()
    cards = {}
    for card in worklist.cards(layers[layer_id], store):
        if card.path in where:
            cards[card.card_key] = (
                card.fingerprint,
                [where[card.path][ln.line - 1] for ln in card.lines],
            )
    return Before(
        layer=layer_id,
        text=text,
        held=where,
        pages={p: page_map.read(store, p) for p in text},
        cards=cards,
        signed=_signed(layer_id, layers, set(text)),
    )


def _pages(index: page_map.PageIndex | None, numbers: Sequence[int]) -> set[int] | None:
    if index is None:
        return None
    return {index.at(n).n for n in numbers}


def _move_citations(
    store: ProvenanceStore,
    before: Before,
    files: Sequence[Path],
    own: set[Path],
    *,
    write_files: bool,
    known: Mapping[str, Rule] | None = None,
) -> tuple[list[tuple[Path, str, str]], list[tuple[Path, str, str]]]:
    by_name = {p.rsplit("/", 1)[-1]: p for p in before.text}
    proof_of = {p: _proof_of(store, p) for p in before.text}
    after = {proof: addresses(store, proof, known) for proof in set(proof_of.values())}
    moved: list[tuple[Path, str, str]] = []
    refused: list[tuple[Path, str, str]] = []

    for file in files:
        original = file.read_text(encoding="utf-8")

        def swap(found: re.Match[str], file: Path = file) -> str:
            name, prefix = found.group("name"), found.group("dir")
            path = by_name.get(name)
            if path is None:
                return found.group(0)
            if prefix and prefix != path.rsplit("/", 1)[0] + "/":
                return found.group(0)
            if not prefix and file not in own:
                return found.group(0)
            try:
                ref = parse_quote(f"{path}#L{found.group('spans').replace(' ', '')}")
            except ProvenanceError:
                # Prose may list lines out of order ("#L452,L464,L63"): not a
                # quote this can move, so it stays for a person.
                refused.append((file, found.group(0), "its spans are out of order"))
                return found.group(0)
            stored = before.held[path]
            if any(not 1 <= n <= len(stored) for n in ref.numbers):
                refused.append((file, found.group(0), "names a line the file does not have"))
                return found.group(0)
            proof_lines = {k for n in ref.numbers for k in stored[n - 1]}
            where = after[proof_of[path]]
            landed = {where[k] for k in proof_lines if k in where}
            targets = {t for t, _ in landed}
            if not landed or len(targets) != 1:
                refused.append((file, found.group(0), "lands in no section or in two"))
                return found.group(0)
            target = targets.pop()
            lines = sorted({k for _, ks in landed for k in ks})
            new_text = store.text_path(target).read_text(encoding="utf-8").splitlines()
            whole = _letters(new_text[k - 1] for k in lines)
            old_text = before.text[path]
            for first, last in ref.spans:
                if _letters(old_text[first - 1 : last]) not in whole:
                    refused.append((file, found.group(0), "the old words are not in the new quote"))
                    return found.group(0)
            if _pages(before.pages[path], ref.numbers) != _pages(page_map.read(store, target), lines):
                refused.append((file, found.group(0), "the pages differ"))
                return found.group(0)
            new = f"{target}#{_spans(lines)}"
            new = new if prefix else new.rsplit("/", 1)[-1]
            if found.group("sep") != "#":
                new = new.replace("#", found.group("sep"), 1)
            if new != found.group(0):
                moved.append((file, found.group(0), new))
            return new

        text = _CITE.sub(swap, original)
        if write_files and text != original:
            file.write_text(text, encoding="utf-8", newline="")
    return moved, refused


def _carry_readings(
    store: ProvenanceStore,
    before: Before,
    layer_id: str,
    *,
    write_files: bool,
    known: Mapping[str, Rule] | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    layers = load_rules()
    layer = layers[layer_id]
    proofs = {_proof_of(store, p) for p in before.text}
    # Proof-copy line numbers repeat across proof copies, but a section file
    # belongs to one, so (section file, line) -> its proof lines is unambiguous.
    raw_of: dict[tuple[str, int], set[int]] = {}
    for proof in proofs:
        for k, (path, lines) in addresses(store, proof, known).items():
            for n in lines:
                raw_of.setdefault((path, n), set()).add(k)
    carried: list[str] = []
    reread: list[tuple[str, str]] = []
    path = worklist.layer_path(layer_id)
    text = path.read_text(encoding="utf-8").splitlines()
    for card in worklist.cards(layer, store):
        reading = layer.readings.get(card.card_key)
        old = before.cards.get(card.card_key)
        if reading is None or old is None or reading.fingerprint == card.fingerprint:
            continue
        if reading.fingerprint != old[0]:
            continue  # it had moved before this re-cut; it stays as it was
        ruled = {k for src in old[1] for k in src}
        if all(raw_of.get((card.path, ln.line), set()) & ruled for ln in card.lines):
            text = worklist._splice(
                text, card.card_key, reading.queue, reading.outcome, reading.note, card.fingerprint
            )
            carried.append(card.card_key)
        else:
            new = [ln.text for ln in card.lines if not raw_of.get((card.path, ln.line), set()) & ruled]
            reread.append((card.card_key, " | ".join(t[:80] for t in new)))
    if write_files and carried:
        path.write_text("\n".join(text) + "\n", encoding="utf-8", newline="")
    return carried, reread


def _reissue(before: Before, layer_id: str) -> list[tuple[tuple, str, str, str, str]]:
    layers = load_rules()
    now = _signed(layer_id, layers, set(before.text) | _quoted_paths(layers[layer_id]))
    out = []
    for key, (fp, quote, payload, cite) in before.signed.items():
        got = now.get(key)
        if got is None or got[1] == quote or got[2] != payload or got[3] != cite:
            continue
        out.append((key, fp, got[0], quote, got[1]))
    return out


def _quoted_paths(layer) -> set[str]:
    out = set()
    for _, values in [("defaults", layer.defaults)] + [(c, z.values) for c, z in layer.zones.items()]:
        for value in values.values():
            for part in (value, *value.variants):
                if part.prov.quote:
                    out.add(part.prov.quote.split("#", 1)[0])
    for zone in layer.zones.values():
        if zone.like is not None and zone.like.prov.quote:
            out.add(zone.like.prov.quote.split("#", 1)[0])
    return out


def _relog(reissued: Sequence[tuple[tuple, str, str, str, str]], *, verify_log: Path, dispute_log: Path) -> int:
    """Re-issue signatures and disputes standing on a moved quote; return how many."""
    by_old = {old: (key, new, a, b) for key, old, new, a, b in reissued}
    count = 0
    vlog = VerificationLog.load(verify_log)
    for v in vlog.active().values():
        hit = by_old.get(v.fingerprint)
        if hit:
            vlog.append(
                Verification(
                    layer=v.layer, zone=v.zone, field=v.field, fingerprint=hit[1],
                    reviewer=v.reviewer, reviewed=v.reviewed, when=v.when,
                    note=f"citation moved by a re-cut ({hit[2]} -> {hit[3]}); same words, same pages",
                ),
                verify_log,
            )
            count += 1
    dlog = DisputeLog.load(dispute_log)
    for d in dlog.active().values():
        hit = by_old.get(d.fingerprint)
        if hit:
            dlog.append(
                Dispute(
                    layer=d.layer, zone=d.zone, field=d.field, fingerprint=hit[1],
                    reviewer=d.reviewer, raised=d.raised, verdict=d.verdict, when=d.when,
                    note=f"{d.note} [citation moved by a re-cut ({hit[2]} -> {hit[3]})]",
                ),
                dispute_log,
            )
            count += 1
    return count


def carry_file(layer_id: str, reissued: Sequence[tuple[tuple, str, str, str, str]], day: date) -> Path:
    """The production half: which page checks and signing-inbox rows to re-issue."""
    target = CARRY_DIR / f"{day.isoformat()}.{layer_id.replace('/', '.')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"layer": k[0], "zone": k[1], "field": k[2], "when_key": "+".join(k[3]),
         "old_fingerprint": old, "new_fingerprint": new, "old_quote": a, "new_quote": b}
        for k, old, new, a, b in reissued
    ]
    target.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="")
    return target


def recut(
    layer_id: str,
    *,
    store: ProvenanceStore | None = None,
    known: Mapping[str, Rule] | None = None,
    write_files: bool = False,
    files: Sequence[Path] | None = None,
    verify_log: Path = VERIFY_LOG,
    dispute_log: Path = DISPUTE_LOG,
    day: date | None = None,
) -> Report:
    """Re-cut ``layer_id`` and carry its citations, readings and signatures.

    A dry run cuts too -- it is the only way to know where the lines go -- and
    puts the section files back as they were.
    """
    store = store or ProvenanceStore()
    known = known if known is not None else rules()
    before = snapshot(store, layer_id, known)
    # A bare file name in prose ("40.300.txt L12") is read as this
    # jurisdiction's only in its own files; elsewhere a citation names its path.
    own = {worklist.layer_path(layer_id), CONFIG_ROOT.parent / "footnotes" / f"{layer_id}.yaml"}
    chosen = list(files) if files is not None else config_files(CONFIG_ROOT)
    directory = store.root / layer_id
    saved = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()} if not write_files else {}
    report = Report()
    try:
        write(store, known[layer_id])
        report.moved, report.refused = _move_citations(
            store, before, chosen, own, write_files=write_files, known=known
        )
        if write_files:
            report.carried, report.reread = _carry_readings(
                store, before, layer_id, write_files=True, known=known
            )
            report.reissued = _reissue(before, layer_id)
            _relog(report.reissued, verify_log=verify_log, dispute_log=dispute_log)
            carry_file(layer_id, report.reissued, day or date.today())
    finally:
        if not write_files:
            for p in directory.rglob("*"):
                if p.is_file() and p not in saved:
                    p.unlink()
            for p, data in saved.items():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            for p in sorted(directory.rglob("*"), reverse=True):
                if p.is_dir() and not any(p.iterdir()):
                    p.rmdir()  # a chapter folder the dry run made
    return report


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    do_write = "--write" in args
    layers = [a for a in args if not a.startswith("--")]
    if len(layers) != 1:
        print("usage: python -m flats.encode.recut <layer> [--write]")
        return 2
    report = recut(layers[0].strip("/"), write_files=do_write)
    print(f"citations moved {len(report.moved)}, refused {len(report.refused)}")
    for file, cite, why in report.refused:
        print(f"  REFUSED {file.name}: {cite} -- {why}")
    if do_write:
        print(f"readings carried {len(report.carried)}, to read again {len(report.reread)}")
        for key, lines in report.reread:
            print(f"  READ AGAIN {key}: {lines}")
        print(f"signable values re-addressed {len(report.reissued)}")
    return 1 if report.refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
