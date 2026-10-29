"""Restore the letters an extraction stored as a ligature glyph, and prove nothing else moved.

Gresham's Development Code sets "fi", "fl", "ff", "ffi" and "ffl" as one
glyph each, and pypdf hands them back as the Unicode presentation forms
U+FB00-U+FB04. The stored text read "ﬂoor area" and "aﬀordable": a person
sees the word, but nothing that reads letters does -- the spelling squiggle
underlined 'oor' two hundred times, a search for "floor" missed every one,
and a subject phrase could never match the sentence (FOLLOWUPS 116). The
letters were never lost, only stored in a form no reader of letters reads.

:func:`restore` writes each glyph out as its letters, nothing else.
:func:`mend` does that to a stored document and proves it three ways before
anything is written, each independent of the others:

1. **Only restored letters differ.** :func:`restored_only` walks the old and
   new text side by side: every character is the same character, except a
   ligature glyph, which is exactly its letters. No line moves, so no
   citation, page map or section boundary moves either.
2. **A fresh extraction agrees, word for word.** The book is read again from
   the cached PDF (its bytes checked against the page map's hash) with the
   extraction every document is stored under, which now restores the same
   letters (``flats-html-text/9``), and must give the mended text exactly.
   A drift check that re-fetches the book will find it unchanged.
3. **A second reader agrees, letter for letter.** pdfplumber -- another
   library, another text layer walk -- reads each page, and the page's
   letters (whitespace aside) must be the mended page's letters: the same
   sequence, or the same letters in another reading order where a table or
   a figure caption is read in a different order. That is the check that no
   letter was dropped anywhere -- including at a word's end ("foo t",
   "syste m" are a space inside a word, not a lost letter) -- and that every
   restored word is a word the page prints.

What a mend changes that is keyed on the words, and so must follow them: a
footnote ruling binds to its note's digest and a reading ruling to its
card's fingerprint. Each one whose only change is restored letters is
re-stamped where it stands; anything else is left, and reported. A restored
note can also come to read word for word as a note ruled in another chapter,
so one digest is answered twice; that is reported too, for one reason true
everywhere to be written into each entry.

A document already cut into section files is refused: its sections are
proved against the proof copy, so mend first, then cut.

Run it::

    uv run python -m flats.provenance.mend or/multnomah/gresham            # dry run
    uv run python -m flats.provenance.mend or/multnomah/gresham --write
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

#: Each ligature glyph and the letters it prints: the Unicode compatibility
#: decomposition, which is what the glyph is defined to mean.
LIGATURES: dict[str, str] = {
    ch: unicodedata.normalize("NFKC", ch) for ch in map(chr, range(0xFB00, 0xFB07))
}


def restore(text: str) -> str:
    """``text`` with every ligature glyph written out as its letters."""
    if not any(ch in text for ch in LIGATURES):
        return text
    return "".join(LIGATURES.get(ch, ch) for ch in text)


def glyphs(text: str) -> int:
    """How many ligature glyphs ``text`` holds."""
    return sum(text.count(ch) for ch in LIGATURES)


def restored_only(old: str, new: str) -> list[str]:
    """Every way ``new`` differs from ``old`` other than restored letters. Empty is proof.

    Written without :func:`restore`: it walks both texts a character at a
    time and accepts only the same character, or a ligature glyph in ``old``
    standing exactly where its letters stand in ``new``.
    """
    problems: list[str] = []
    old_lines, new_lines = old.split("\n"), new.split("\n")
    if len(old_lines) != len(new_lines):
        return [f"the line count moved ({len(old_lines)} -> {len(new_lines)})"]
    for n, (a, b) in enumerate(zip(old_lines, new_lines), start=1):
        i = j = 0
        while i < len(a):
            ch = a[i]
            if ch in LIGATURES:
                letters = LIGATURES[ch]
                if b[j : j + len(letters)] != letters:
                    problems.append(f"line {n}: {ch!r} is not restored as {letters!r}")
                    break
                i, j = i + 1, j + len(letters)
            elif j < len(b) and b[j] == ch:
                i, j = i + 1, j + 1
            else:
                problems.append(f"line {n}: the text parts at column {i} ({a[i:i + 20]!r})")
                break
        else:
            if j != len(b):
                problems.append(f"line {n}: the mended line runs on ({b[j:j + 20]!r})")
    return problems


def _letters(text: str) -> str:
    return "".join(c for c in text if not c.isspace())


@dataclass(frozen=True, slots=True)
class PageCheck:
    """One printed page: the mended text's letters against a second reader's."""

    n: int
    #: ``same`` (one sequence), ``reordered`` (the same letters in another
    #: reading order), ``within`` (a slice's edge page: every stored letter
    #: is on the page, which prints more) or ``differs``.
    verdict: str
    #: Letters the stored page holds and the second reader does not, and the
    #: other way round (``differs`` only).
    stored_only: str = ""
    fresh_only: str = ""


def witness(page: str, fresh: str, *, n: int, edge: bool = False) -> PageCheck:
    """``page`` (the mended text of one printed page) against ``fresh`` (a second reader's)."""
    a, b = _letters(page), _letters(fresh)
    if a == b:
        return PageCheck(n, "same")
    ca, cb = Counter(a), Counter(b)
    if ca == cb:
        return PageCheck(n, "reordered")
    if edge and not (ca - cb):
        return PageCheck(n, "within")
    return PageCheck(
        n,
        "differs",
        stored_only="".join(sorted((ca - cb).elements())),
        fresh_only="".join(sorted((cb - ca).elements())),
    )


def words_found(page: str, fresh: str) -> tuple[int, list[str]]:
    """How many restored words the second reader prints on the page, and the ones it does not.

    A restored word is the run of non-space text around a ligature glyph,
    with its letters restored; it is looked for in the second reader's page
    with whitespace taken out of both, so a word the two readers space
    differently is still the same word.
    """
    hay = _letters(restore(fresh))
    found, missing = 0, []
    for line in page.split("\n"):
        for token in line.split():
            if not any(ch in token for ch in LIGATURES):
                continue
            word = restore(token)
            if word in hay:
                found += 1
            else:
                missing.append(word)
    return found, missing


def _pages_of(lines: Sequence[str], starts: Sequence[tuple[int, int]]) -> list[tuple[int, str]]:
    """(PDF page, its stored text) from a page map's (page, first line) list."""
    out = []
    for k, (n, line) in enumerate(starts):
        last = starts[k + 1][1] - 1 if k + 1 < len(starts) else len(lines)
        out.append((n, "\n".join(lines[line - 1 : last])))
    return out


def plumber_pages(book: Path, numbers: Iterable[int]) -> dict[int, str]:
    """pdfplumber's text of each named page (1-based). Imported here: it is
    a reading tool, not something the app runs on."""
    import pdfplumber

    wanted = set(numbers)
    out: dict[int, str] = {}
    with pdfplumber.open(book) as pdf:
        for n in sorted(wanted):
            out[n] = pdf.pages[n - 1].extract_text() or ""
    return out


@dataclass
class Mended:
    """What a mend of one document found."""

    path: str
    glyphs: int = 0
    problems: list[str] = field(default_factory=list)
    pages: list[PageCheck] = field(default_factory=list)
    words: int = 0
    missing: list[str] = field(default_factory=list)
    #: Whether a fresh extraction of the book gives the mended text exactly.
    reextracted: bool = False

    @property
    def proved(self) -> bool:
        return (
            not self.problems
            and self.reextracted
            and not self.missing
            and all(p.verdict != "differs" for p in self.pages)
        )


def check_document(
    store,
    path: str,
    *,
    declared=None,
    reader: Callable[[Path, Iterable[int]], dict[int, str]] = plumber_pages,
) -> tuple[Mended, str]:
    """Mend one stored document in memory and prove it; (findings, mended text)."""
    from flats.provenance import books
    from flats.provenance import pages as page_map
    from flats.provenance.fetch import fetch_text

    doc = store.load(path)
    found = Mended(path=path, glyphs=glyphs(doc.text))
    new = restore(doc.text)
    found.problems = restored_only(doc.text, new)
    index = page_map.read(store, path)
    if index is None:
        found.problems.append("no page map: the pages cannot be read again to prove the mend")
        return found, new
    try:
        book = books.ensure(store, path)
    except books.BookError as exc:
        found.problems.append(str(exc))
        return found, new

    data = book.read_bytes()
    spec = declared
    fresh = fetch_text(
        doc.url,
        get=lambda _url: data,
        start=spec.start if spec else "",
        end=spec.end if spec else "",
        nth=spec.nth if spec else 1,
        extraction=spec.extraction if spec else "layout",
    )
    found.reextracted = fresh == new
    if not found.reextracted:
        found.problems.append("a fresh extraction of the book does not give the mended text")

    lines = new.split("\n")
    starts = [(p.n, p.line) for p in index.pages]
    sliced = bool(spec and (spec.start or spec.end))
    read = reader(book, [n for n, _ in starts])
    old_pages = _pages_of(doc.text.split("\n"), starts)
    for k, (n, text) in enumerate(_pages_of(lines, starts)):
        edge = sliced and k in (0, len(starts) - 1)
        found.pages.append(witness(text, read.get(n, ""), n=n, edge=edge))
        hits, missing = words_found(old_pages[k][1], read.get(n, ""))
        found.words += hits
        found.missing.extend(f"p{n} {w}" for w in missing)
    return found, new


# --- what follows the words -------------------------------------------------


def _footnote_digests(layer_id: str) -> dict[tuple[str, int], str]:
    """(document, line) -> digest of every footnote body the census finds."""
    from flats.encode.dispositions import digest
    from flats.encode.footnotes import survey

    out: dict[tuple[str, int], str] = {}
    for census in survey(layer_id):
        if census.layer != layer_id:
            continue
        for body in census.bodies:
            out[(body.doc, body.line)] = digest(body.text)
    return out


def _card_prints(layer_id: str) -> dict[str, tuple[str, str]]:
    """Reading card key -> (fingerprint, the text it is taken over).

    The reading queues' cards (``readings:``). A word ruling (``words:``)
    binds to a glossary entry's wording the same way; a layer that holds
    any is refused by :func:`mend` rather than re-stamped here.
    """
    from flats.encode import worklist
    from flats.provenance.store import ProvenanceStore
    from flats.rules.loader import load_rules

    worklist.refresh()
    layer = load_rules()[layer_id]
    out: dict[str, tuple[str, str]] = {}
    for card in worklist.cards(layer, ProvenanceStore(), lots={}):
        body = "\n".join(f"{ln.line}\t{ln.text}" for ln in card.lines)
        out[card.card_key] = (card.fingerprint, body)
    return out


def restamp_footnotes(
    file: Path, before: dict[tuple[str, int], str], after: dict[tuple[str, int], str], *, write: bool
) -> list[tuple[str, str]]:
    """Re-stamp each ruling whose note's only change is restored letters; (old, new) digests."""
    pairs = {
        before[key]: after[key]
        for key in before.keys() & after.keys()
        if before[key] != after[key]
    }
    if not pairs or not file.is_file():
        return []
    text = file.read_text(encoding="utf-8")
    done: list[tuple[str, str]] = []
    for old, new in sorted(pairs.items()):
        needle = f'digest: "{old}"'
        if needle in text:
            text = text.replace(needle, f'digest: "{new}"')
            done.append((old, new))
    if write and done:
        file.write_text(text, encoding="utf-8", newline="")
    return done


def narrowed(old_body: str, new_body: str) -> bool:
    """Whether a card's new body asks nothing its old body, letters restored, did not.

    The same body is the usual case. A card can also lose lines: a restored
    word ("floor" where the glyph stood) can let the uncited survey see that a
    line's number is already held, so the line leaves the queue. A reading
    made over the longer card covered every line that is left, so it still
    stands. A card that gained a line, or whose line changed by more than its
    letters, asks something nobody has read and is reopened.
    """
    was = set(restore(old_body).split("\n"))
    now = new_body.split("\n")
    return bool(now) and all(line in was for line in now)


def restamp_readings(
    layer_id: str,
    before: dict[str, tuple[str, str]],
    after: dict[str, tuple[str, str]],
    *,
    write: bool,
) -> tuple[list[str], list[str]]:
    """Re-stamp each reading whose card's only change is restored letters (or fewer lines).

    Returns (re-stamped card keys, reopened card keys left for a person).
    """
    from flats.encode import worklist
    from flats.rules.loader import load_rules

    layer = load_rules()[layer_id]
    path = worklist.layer_path(layer_id)
    lines = path.read_text(encoding="utf-8").splitlines()
    done: list[str] = []
    left: list[str] = []
    for key, reading in sorted(layer.readings.items()):
        old, new = before.get(key), after.get(key)
        if old is None or new is None or old[0] == new[0]:
            continue
        if reading.fingerprint != old[0]:
            continue  # loose before the mend; it stays as it was
        if narrowed(old[1], new[1]):
            lines = worklist._splice(lines, key, reading.queue, reading.outcome, reading.note, new[0])
            done.append(key)
        else:
            left.append(key)
    if write and done:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    return done, left


@dataclass
class Report:
    documents: list[Mended] = field(default_factory=list)
    footnotes: list[tuple[str, str]] = field(default_factory=list)
    readings: list[str] = field(default_factory=list)
    reopened: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    #: Footnote digests now answered by two rulings that decide differently:
    #: a restored note whose words now match a note ruled elsewhere. The cure
    #: is one reason true everywhere, written into each entry (travelled.py).
    shared: list[str] = field(default_factory=list)


def mend(
    layer_id: str,
    *,
    store=None,
    write: bool = False,
    every: bool = False,
    reader: Callable[[Path, Iterable[int]], dict[int, str]] = plumber_pages,
) -> Report:
    """Restore the ligature letters in a layer's stored documents, proved; write only with ``write``.

    A document is written only when all three proofs hold. Nothing is
    written at all on a dry run. ``every`` also witnesses the documents
    that hold no glyph (the end-letter check); those are never written.
    """
    from flats.provenance import pages as page_map
    from flats.provenance.fetch import EXTRACTOR, declared
    from flats.provenance.store import ProvenanceStore
    from flats.rules.loader import load_rules

    store = store or ProvenanceStore()
    layers = load_rules(strict=False)
    specs = {path: doc for _layer, path, doc in declared(layers, layer_id)}
    worded = bool(layer_id in layers and layers[layer_id].words)
    proofs = store.proofs()
    report = Report()
    chosen: dict[str, str] = {}
    for path in store.fetched():
        if store.layer_of(path) != layer_id:
            continue
        doc = store.load(path)
        if not glyphs(doc.text) and not every:
            continue
        if path in proofs and glyphs(doc.text):
            found = Mended(path=path, glyphs=glyphs(doc.text))
            found.problems.append("already cut into sections: mend before cutting")
            report.documents.append(found)
            continue
        found, new = check_document(store, path, declared=specs.get(path), reader=reader)
        if worded:
            found.problems.append("the layer holds word rulings, which a mend does not re-stamp")
        report.documents.append(found)
        if found.proved and found.glyphs:
            chosen[path] = new
    if not write or not chosen:
        return report

    from flats.encode.dispositions import CONFIG_ROOT as NOTES_ROOT

    notes_before = _footnote_digests(layer_id)
    cards_before = _card_prints(layer_id)
    for path, new in chosen.items():
        doc = store.load(path)
        sidecar = page_map.sidecar(store, path)
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
        saved = store.save(path, url=doc.url, text=new, retrieved=doc.retrieved, extractor=EXTRACTOR)
        # The lines did not move, so the page map is the same map of the new text.
        raw["sha256"] = saved.sha256
        sidecar.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8", newline="")
        report.written.append(path)
    notes_after = _footnote_digests(layer_id)
    report.footnotes = restamp_footnotes(
        NOTES_ROOT / f"{layer_id}.yaml", notes_before, notes_after, write=True
    )
    cards_after = _card_prints(layer_id)
    report.readings, report.reopened = restamp_readings(
        layer_id, cards_before, cards_after, write=True
    )
    from flats.encode.travelled import shadowed

    report.shared = [p.digest for p in shadowed() if p.layer == layer_id]
    return report


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    do_write = "--write" in args
    every = "--all" in args
    layers = [a for a in args if not a.startswith("--")]
    if len(layers) != 1:
        print("usage: python -m flats.provenance.mend <layer> [--all] [--write]")
        return 2
    report = mend(layers[0].strip("/"), write=do_write, every=every)
    bad = 0
    for found in report.documents:
        verdicts = Counter(p.verdict for p in found.pages)
        state = "PROVED" if found.proved else "REFUSED"
        bad += not found.proved
        print(
            f"{state} {found.path}: {found.glyphs} glyphs restored; fresh extraction "
            f"{'agrees' if found.reextracted else 'DIFFERS'}; pages {dict(verdicts)}; "
            f"restored words on the page {found.words}, missing {len(found.missing)}"
        )
        for problem in found.problems[:20]:
            print(f"  {problem}")
        for page in found.pages:
            if page.verdict == "differs":
                print(f"  p{page.n}: stored only {page.stored_only[:60]!r}; "
                      f"second reader only {page.fresh_only[:60]!r}")
        for word in found.missing[:20]:
            print(f"  not on the page: {word}")
    if do_write:
        print(f"written {len(report.written)}; footnote rulings re-stamped {len(report.footnotes)}; "
              f"readings re-stamped {len(report.readings)}, reopened {len(report.reopened)}")
        for key in report.reopened:
            print(f"  REOPENED {key}")
        for dg in report.shared:
            print(f"  ANSWERED TWICE {dg}: a restored note now reads as one ruled elsewhere; "
                  f"write one reason true everywhere into each entry")
    return 1 if bad else 0


__all__ = [
    "LIGATURES",
    "Mended",
    "PageCheck",
    "glyphs",
    "mend",
    "narrowed",
    "restore",
    "restored_only",
    "witness",
    "words_found",
]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
