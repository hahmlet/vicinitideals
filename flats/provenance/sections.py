"""Code text one section to a file, readable, cut from the document it was fetched as.

A city publishes its code as chapters, and the store kept it that way: one
file per fetch, cited by line -- ``40-41.residential.txt#L225-L233``. The line
says where the words are and nothing about which section they belong to, so a
second tool had to read headings upward to check that a value citing "TDC
40.220" was quoting 40.220 at all (``flats/encode/attribution.py``), and 1,533
values cited a section that tool could not find above its lines.

Here a document is cut at its own headings into one file per section, filed
in a folder per chapter -- ``40/40.220.txt`` -- and a citation names the
section by naming the file. Line 1 of every file is its heading, so the line
in a citation is a line WITHIN the section.

**A section file is readable text, not the extraction's lines.**
:mod:`flats.provenance.readable` takes off the page furniture, repairs the
letter-spacing, settles the margin hyphens and joins the wrapped lines one
sentence to a line, and then proves the result keeps every word of the
extraction in order. The order is PDF, readable authoritative text, cited
encoding: a reader checks a value against a sentence, not against a column
the PDF happened to wrap.

**The fetched document stays, untouched, as the proof copy.** It is what the
URL served, what drift re-fetches and compares, and what the PDF page map was
built against. The section files are derived from it and nothing else. ONE
index per city (``sections.json``) is the only bookkeeping: each section's
first and last line in the proof copy, its file, its hash and its pages, plus
the proof copy's hash; no sidecar sits beside a section file. :func:`check`
fails the day a section file is not exactly the readable text of exactly that
slice, so a re-fetch cannot leave section files quietly describing the old
proof copy.

Each readable line knows the proof-copy lines it holds (:func:`held`, read
from the file on disk so it stays true whichever cleaning made it). That is
how a citation reaches the printed page (:func:`in_proof`), and how a change
to the cleaning moves every citation, reading ruling and page-check answer
standing on the old text without changing a word of what they quote
(``python -m flats.encode.recut``).

Three limits, each the conservative direction:

*Only a heading the rule names cuts.* A jurisdiction's heading form is written
in ``flats/config/sections.yaml``; a document in which it finds no heading is
not split at all.

*The contents list is not code.* Lines above the first real heading that are
the chapter's own list of headings are left in the proof copy and in no
section. Lines above it that are code text -- a slice that opened mid-section
-- must be named to a section in the rule, or the split refuses.

*A citation that spans two sections stays on the proof copy.* A table row and
the note that qualifies it are cited together or not at all (the store's own
rule); when they sit in different sections, no one section file holds the
citation, so it is left where it is and reported.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

from flats.provenance import pages as page_map
from flats.provenance import readable
from flats.provenance.store import (
    INDEX,
    Part,
    ProvenanceError,
    ProvenanceStore,
    parse_quote,
    sha256,
)

#: Where each jurisdiction's heading form is written down.
RULES = Path(__file__).resolve().parents[1] / "config" / "sections.yaml"


@dataclass(frozen=True, slots=True)
class Rule:
    """How one jurisdiction's documents are cut."""

    layer: str
    #: Matches a heading line; group ``n`` is the section number.
    heading: re.Pattern[str]
    #: Matches heading-shaped lines that are not headings (running headers).
    furniture: re.Pattern[str] | None = None
    #: Document id -> the section its opening lines belong to, for a slice
    #: that starts inside a section rather than at a heading.
    lead: Mapping[str, str] | None = None
    #: A page's header and footer, which the readable text leaves out (only
    #: in the lines just above a page start; see ``readable.py``).
    page_furniture: re.Pattern[str] | None = None


def rules(path: Path = RULES) -> dict[str, Rule]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, Rule] = {}
    for layer, body in raw.items():
        heading = re.compile(body["heading"])
        if "n" not in heading.groupindex:
            raise ValueError(f"{layer}: the heading pattern names no group 'n'")
        furniture = body.get("furniture")
        page = body.get("page_furniture")
        out[layer] = Rule(
            layer=layer,
            heading=heading,
            furniture=re.compile(furniture) if furniture else None,
            lead=dict(body.get("lead") or {}),
            page_furniture=re.compile(page) if page else None,
        )
    return out


@dataclass(frozen=True, slots=True)
class Section:
    number: str
    #: First and last line in the proof copy, 1-based and inclusive.
    first: int
    last: int

    @property
    def chapter(self) -> str:
        """``40.300`` -> ``40``, ``73C.030`` -> ``73C``: the folder it is filed in."""
        return self.number.split(".", 1)[0]

    @property
    def file(self) -> str:
        return f"{self.chapter}/{self.number}.txt"


def _is_heading(rule: Rule, line: str) -> re.Match[str] | None:
    found = rule.heading.match(line)
    if found and rule.furniture is not None and rule.furniture.match(line):
        return None
    return found


def split(lines: Sequence[str], rule: Rule, doc_id: str) -> list[Section]:
    """The sections of one document, in order.

    A section starts at the LAST line its heading appears on. A chapter prints
    its headings twice -- once in its contents list, once over the text -- and
    the text is the later of the two. A heading printed three times is a
    question this cannot answer, and it says so.
    """
    seen: dict[str, list[int]] = {}
    for n, line in enumerate(lines, start=1):
        found = _is_heading(rule, line)
        if found:
            seen.setdefault(found.group("n"), []).append(n)
    if not seen:
        return []
    for number, where in seen.items():
        if len(where) > 2:
            raise ProvenanceError(
                f"{doc_id}: heading {number} is printed {len(where)} times "
                f"(lines {where}); which one opens the section is a reading"
            )
    starts = sorted((where[-1], number) for number, where in seen.items())
    order = [_sortable(number) for _, number in starts]
    if order != sorted(order):
        # A code prints its sections in number order. One out of order is a
        # line that looks like a heading and is not -- a reference wrapped to
        # the start of a line -- and cutting there would split a section.
        raise ProvenanceError(
            f"{doc_id}: headings out of number order ({[n for _, n in starts]}); "
            f"one of them is not a heading"
        )
    out: list[Section] = []
    for k, (first, number) in enumerate(starts):
        last = starts[k + 1][0] - 1 if k + 1 < len(starts) else len(lines)
        out.append(Section(number, first, last))

    opening = starts[0][0] - 1
    named = (rule.lead or {}).get(doc_id)
    if named:
        if named in seen:
            raise ProvenanceError(f"{doc_id}: lead section {named} is also a heading")
        out.insert(0, Section(named, 1, opening))
    else:
        text = [line for line in lines[:opening] if line.strip()]
        if text and not _is_heading(rule, text[0]):
            raise ProvenanceError(
                f"{doc_id}: lines 1-{opening} are text above the first heading, "
                f"not a contents list; name their section under 'lead'"
            )
        # A contents entry is a heading printed early, so every number in
        # the list must have its later printing over the text.
        for line in text:
            found = _is_heading(rule, line)
            if found and len(seen[found.group("n")]) != 2:
                raise ProvenanceError(
                    f"{doc_id}: contents entry {found.group('n')} has no heading below it"
                )
    return out


def _sortable(number: str) -> tuple[object, ...]:
    """``73C.030`` -> (73, "C", 30): chapter, chapter letter, section."""
    return tuple(
        int(piece) if piece.isdigit() else piece for piece in re.findall(r"\d+|[A-Z]+", number)
    )


def _lines(text: str) -> list[str]:
    return text.splitlines()


@dataclass(frozen=True, slots=True)
class Split:
    """One proof copy and the sections cut from it."""

    #: Store path of the proof copy.
    proof: str
    sha256: str
    sections: tuple[Section, ...]

    @property
    def directory(self) -> str:
        return self.proof.rsplit("/", 1)[0]

    def path(self, section: Section) -> str:
        return f"{self.directory}/{section.file}"

    def at(self, line: int) -> Section | None:
        """The section a proof-copy line was cut into."""
        for section in self.sections:
            if section.first <= line <= section.last:
                return section
        return None


def _index_file(store: ProvenanceStore, directory: str) -> Path:
    return store.root / directory / INDEX


def splits(store: ProvenanceStore | None = None) -> dict[str, Split]:
    """Every split proof copy in the store, keyed by its path."""
    store = store or ProvenanceStore()
    out: dict[str, Split] = {}
    for file in sorted(store.root.rglob(INDEX)):
        directory = str(file.parent.relative_to(store.root)).replace("\\", "/")
        raw = json.loads(file.read_text(encoding="utf-8"))
        for name, body in raw["documents"].items():
            proof = f"{directory}/{name}"
            out[proof] = Split(
                proof=proof,
                sha256=body["sha256"],
                sections=tuple(Section(row[0], row[1], row[2]) for row in body["sections"]),
            )
    return out


def derived(paths: Iterable[str], store: ProvenanceStore | None = None) -> frozenset[str]:
    """``paths`` plus every section file cut from a proof copy among them.

    Drift is found on the proof copy, the thing that was fetched. The values it
    must reach cite the sections.
    """
    chosen = set(paths)
    out = set(chosen)
    for proof, cut in splits(store).items():
        if proof in chosen:
            out.update(cut.path(s) for s in cut.sections)
    return frozenset(out)


def chapters(paths: Iterable[str], store: ProvenanceStore | None = None) -> frozenset[str]:
    """``paths`` plus every file of the same chapter as one among them.

    A chapter is a proof copy and the sections cut from it. "Nobody has quoted
    a line of this chapter" was a question about the fetched document; a
    section nobody quotes, in a chapter somebody does, is not unopened.
    """
    out = set(paths)
    for proof, cut in splits(store).items():
        family = {proof, *(cut.path(s) for s in cut.sections)}
        if family & out:
            out |= family
    return frozenset(out)


# --- the readable text ------------------------------------------------------


def _breaks(store: ProvenanceStore, proof: str, length: int) -> list[int]:
    """The proof-copy lines a printed page starts on, and one past the end.

    The end counts because the last page's furniture is the book's last lines.
    """
    pages = page_map.read(store, proof)
    return [*(p.line for p in pages.pages), length + 1] if pages is not None else []


def _vocabulary(store: ProvenanceStore, proofs: Iterable[str]) -> Counter[str]:
    return readable.vocabulary(store.load(p).text for p in sorted(set(proofs)))


@dataclass(frozen=True, slots=True)
class Cut:
    """One section, cut and made readable."""

    section: Section
    path: str
    text: readable.Readable
    #: (PDF page, first line of the section on it).
    pages: tuple[tuple[int, int], ...]


def _cut(
    lines: Sequence[str],
    cut: Split,
    rule: Rule,
    breaks: Sequence[int],
    words: Mapping[str, int],
    pages: page_map.PageIndex | None,
) -> list[Cut]:
    out: list[Cut] = []
    for section in cut.sections:
        raw = lines[section.first - 1 : section.last]
        local = [b - section.first + 1 for b in breaks if section.first < b <= section.last + 1]
        text = readable.clean(
            raw, breaks=local, furniture=rule.page_furniture, heading=rule.heading, words=words
        )
        problems = readable.prove(raw, text, breaks=local, furniture=rule.page_furniture)
        if problems:
            raise ProvenanceError(f"{cut.path(section)}: {'; '.join(problems)}")
        out.append(Cut(section, cut.path(section), text, _pages_of(text, section, pages)))
    return out


def _pages_of(
    text: readable.Readable, section: Section, pages: page_map.PageIndex | None
) -> tuple[tuple[int, int], ...]:
    """The book's page map, cut to one section and renumbered to its lines."""
    if pages is None:
        return ()
    out: list[tuple[int, int]] = []
    for page in pages.pages:
        if page.line > section.last:
            break
        local = max(page.line, section.first) - section.first + 1
        line = next(
            (k for k, src in enumerate(text.sources, start=1) if src and src[0] >= local), None
        )
        if line is None:
            continue
        if out and out[-1][1] == line:
            out[-1] = (page.n, line)
        else:
            out.append((page.n, line))
    return tuple(out)


def cuts(
    store: ProvenanceStore, proof: str, known: Mapping[str, Rule] | None = None
) -> list[Cut]:
    """The sections of a proof copy as its index says they were cut.

    Re-derived from the proof copy itself, so it is what :func:`check`
    compares the section files with. ``known`` is :func:`rules`, for a test.
    """
    return _cuts(store, proof, store.load(proof).sha256, known)


_HELD: dict[tuple[Path, str, str], list[Cut]] = {}


def _cuts(
    store: ProvenanceStore, proof: str, digest: str, known: Mapping[str, Rule] | None = None
) -> list[Cut]:
    layer = proof.rsplit("/", 1)[0]
    family = {p: c for p, c in splits(store).items() if p.rsplit("/", 1)[0] == layer}
    key = (store.root, proof, digest + "".join(sorted(c.sha256 for c in family.values())))
    if key not in _HELD:
        rule = (known if known is not None else rules())[layer]
        lines = _lines(store.load(proof).text)
        _HELD[key] = _cut(
            lines,
            family[proof],
            rule,
            _breaks(store, proof, len(lines)),
            _vocabulary(store, family),
            page_map.read(store, proof),
        )
    return _HELD[key]


def addresses(
    store: ProvenanceStore, proof: str, known: Mapping[str, Rule] | None = None
) -> dict[int, tuple[str, tuple[int, ...]]]:
    """Proof-copy line -> (section file, the readable lines holding it).

    Page furniture and a contents list are in no section and map nowhere.
    """
    out: dict[int, tuple[str, tuple[int, ...]]] = {}
    for cut in cuts(store, proof, known):
        for k, src in enumerate(cut.text.sources, start=1):
            for local in src:
                line = cut.section.first + local - 1
                held = out.get(line)
                out[line] = (cut.path, (*held[1], k) if held else (k,))
    return out


def held(
    store: ProvenanceStore, path: str, known: Mapping[str, Rule] | None = None
) -> list[tuple[int, ...]]:
    """Each line of a section file AS STORED, as the proof-copy lines it holds.

    Read from the file on disk, not re-derived: after the cleaning changes,
    this is still where the old text's words were, which is what moving a
    citation of the old text needs. Raises when the file is not the proof
    copy's words.
    """
    part = store.part_of(path)
    if part is None:
        raise ProvenanceError(f"{path}: not a section file")
    key = (store.root, path, part.sha256)
    if key not in _ALIGNED:
        _ALIGNED[key] = _held(store, part, known)
    return list(_ALIGNED[key])


#: (store root, section file, its hash) -> what :func:`held` found.
_ALIGNED: dict[tuple[Path, str, str], tuple[tuple[int, ...], ...]] = {}


def _held(store: ProvenanceStore, part: Part, known: Mapping[str, Rule] | None) -> tuple[tuple[int, ...], ...]:
    path = part.path
    rule = (known if known is not None else rules())[part.layer]
    lines = _lines(store.load(part.proof).text)
    raw = lines[part.first - 1 : part.last]
    local = [
        b - part.first + 1
        for b in _breaks(store, part.proof, len(lines))
        if part.first < b <= part.last + 1
    ]
    text = store.text_path(path).read_text(encoding="utf-8").splitlines()
    found = readable.align(raw, text, breaks=local, furniture=rule.page_furniture)
    if found is None:
        raise ProvenanceError(f"{path}: the stored text is not the proof copy's words")
    return tuple(tuple(part.first + k - 1 for k in src) for src in found)


def printed(
    store: ProvenanceStore, path: str, known: Mapping[str, Rule] | None = None
) -> list[tuple[str, ...]] | None:
    """Each line of a section file as the extraction lines it was joined from.

    None for a document that is not a section file. For a tool whose rule was
    tuned on the printed line -- its width, its wrap -- and must keep meaning
    the same thing now that a line is a sentence. Read through :func:`held`,
    so it describes the file on disk whichever cleaning made it.
    """
    part = store.part_of(path)
    if part is None:
        return None
    lines = _lines(store.load(part.proof).text)
    return [tuple(lines[k - 1] for k in src) for src in held(store, path, known)]


def in_proof(
    store: ProvenanceStore,
    path: str,
    ranges: Sequence[tuple[int, int]],
    known: Mapping[str, Rule] | None = None,
) -> tuple[str, list[tuple[int, int]]]:
    """A citation of a section file as the proof-copy lines its words are on.

    The page map and the book are the proof copy's, and the printed sheet
    carries the extraction's lines, not the readable ones: boxing a number on
    the page reads the lines the PDF printed.
    """
    part = store.part_of(path)
    if part is None:
        return path, list(ranges)
    sources = held(store, path, known)
    wanted = sorted(
        {
            n
            for first, last in ranges
            for k in range(first, last + 1)
            if 1 <= k <= len(sources)
            for n in sources[k - 1]
        }
    )
    out: list[tuple[int, int]] = []
    for n in wanted:
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return part.proof, out


def move_quote(
    quote: str, store: ProvenanceStore, known: Mapping[str, Rule] | None = None
) -> str | None:
    """A quote of a proof copy addressed to its section, or None when it spans two.

    The readable lines that hold every cited line; a quote into a document
    that was not split is returned unchanged.
    """
    ref = parse_quote(quote)
    if ref.path not in store.proofs() or ref.whole_document:
        return quote
    return _moved(quote, addresses(store, ref.path, known))


def _spans(lines: Sequence[int]) -> str:
    runs: list[list[int]] = []
    for n in lines:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ",".join(f"L{a}" if a == b else f"L{a}-L{b}" for a, b in runs)


def write(store: ProvenanceStore, rule: Rule, *, only: Iterable[str] | None = None) -> list[Split]:
    """Cut every document in ``rule.layer`` and write the readable section files."""
    directory = store.root / rule.layer
    chosen = set(only) if only is not None else None
    index_path = directory / INDEX
    existing = json.loads(index_path.read_text(encoding="utf-8"))["documents"] if index_path.is_file() else {}
    before = _files_of(existing)
    flat = {directory / p for paths in before.values() for p in paths}
    todo: list[Split] = []
    for text_file in sorted(directory.glob("*.txt")):
        name = text_file.name
        doc_id = text_file.stem
        proof = f"{rule.layer}/{name}"
        if chosen is not None and doc_id not in chosen:
            continue
        if name not in existing and text_file in flat:
            continue  # a section file of a flat cut, about to be replaced
        doc = store.load(proof)
        sections = split(_lines(doc.text), rule, doc_id)
        if sections:
            todo.append(Split(proof=proof, sha256=doc.sha256, sections=tuple(sections)))
    family = {f"{rule.layer}/{name}" for name in existing} | {c.proof for c in todo}
    words = _vocabulary(store, family)
    made: list[Split] = []
    for cut in todo:
        name = cut.proof.rsplit("/", 1)[-1]
        lines = _lines(store.load(cut.proof).text)
        pages = page_map.read(store, cut.proof)
        done = _cut(lines, cut, rule, _breaks(store, cut.proof, len(lines)), words, pages)
        for old in before.get(name, ()):
            for stale in (old.name, f"{old.name}.meta.json", f"{old.name}.pages.json"):
                (directory / old.parent / stale).unlink(missing_ok=True)
        rows = []
        for piece in done:
            target = store.text_path(piece.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(piece.text.text, encoding="utf-8", newline="")
            rows.append(
                [
                    piece.section.number,
                    piece.section.first,
                    piece.section.last,
                    piece.section.file,
                    sha256(piece.text.text),
                    [list(p) for p in piece.pages],
                ]
            )
        existing[name] = {"sha256": cut.sha256, "sections": rows}
        made.append(cut)
    if existing:
        index_path.write_text(_index_text(existing), encoding="utf-8", newline="")
    _HELD.clear()
    return made


def _files_of(documents: Mapping[str, Mapping[str, object]]) -> dict[str, list[Path]]:
    """Proof name -> the section files an index lists for it, in either form.

    A flat cut listed ``[number, first, last]`` and filed ``<number>.txt``
    beside its proof copy with sidecars of its own; it is replaced, not kept
    beside the readable one.
    """
    return {
        name: [
            Path(row[3]) if len(row) > 3 else Path(f"{row[0]}.txt")  # type: ignore[index]
            for row in body["sections"]  # type: ignore[union-attr]
        ]
        for name, body in documents.items()
    }


def repage(store: ProvenanceStore, proof: str, known: Mapping[str, Rule] | None = None) -> int:
    """Re-derive a proof copy's section pages after its page map was rebuilt.

    The readable text depends on where pages start -- furniture is only taken
    from above a page start, and no line is joined across one -- so a rebuilt
    map that moves the text is refused: the citations into the old text would
    have to be re-pointed first.
    """
    cut = splits(store).get(proof)
    if cut is None:
        return 0
    index_path = store.root / cut.directory / INDEX
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    rows = raw["documents"][proof.rsplit("/", 1)[-1]]["sections"]
    _HELD.clear()
    fresh = cuts(store, proof, known)
    for row, piece in zip(rows, fresh):
        if sha256(piece.text.text) != row[4]:
            raise ProvenanceError(
                f"{piece.path}: the new page map changes its readable text; "
                f"re-cut and re-point its citations"
            )
        row[5] = [list(p) for p in piece.pages]
    index_path.write_text(_index_text(raw["documents"]), encoding="utf-8", newline="")
    return len(fresh)


def _index_text(documents: Mapping[str, Mapping[str, object]]) -> str:
    """The index, one section to a line, so a re-cut reads as a diff of sections."""
    out = ["{", f'  "readable": {json.dumps(readable.VERSION)},', '  "documents": {']
    names = sorted(documents)
    for k, name in enumerate(names):
        body = documents[name]
        rows = [json.dumps(list(row)) for row in body["sections"]]  # type: ignore[union-attr]
        out.append(f"    {json.dumps(name)}: {{")
        out.append(f'      "sha256": {json.dumps(body["sha256"])},')
        out.append('      "sections": [')
        out.extend(f"        {row}{',' if j < len(rows) - 1 else ''}" for j, row in enumerate(rows))
        out.append("      ]")
        out.append("    }" + ("," if k < len(names) - 1 else ""))
    out.append("  }")
    out.append("}")
    return "\n".join(out) + "\n"


def check(
    store: ProvenanceStore | None = None, known: Mapping[str, Rule] | None = None
) -> list[str]:
    """Every way a section file has stopped being its proof copy's words."""
    store = store or ProvenanceStore()
    problems: list[str] = []
    parts = store.parts()
    for proof, cut in splits(store).items():
        try:
            doc = store.load(proof)
        except ProvenanceError as exc:
            problems.append(f"{proof}: {exc}")
            continue
        if doc.sha256 != cut.sha256:
            problems.append(
                f"{proof}: the proof copy changed since it was cut; re-run the split"
            )
            continue
        try:
            fresh = _cuts(store, proof, doc.sha256, known)
        except ProvenanceError as exc:
            problems.append(str(exc))
            continue
        for piece in fresh:
            path = piece.path
            part = parts.get(path)
            try:
                # Normalised like every load: a checkout with autocrlf on hands
                # back CRLF, and that is not a different text.
                got = store.text_path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
            except OSError:
                problems.append(f"{path}: missing")
                continue
            if got != piece.text.text:
                problems.append(f"{path}: not the readable text of lines "
                                f"{piece.section.first}-{piece.section.last} of {proof}")
            if part is None or part.sha256 != sha256(got):
                problems.append(f"{path}: the index does not describe this text")
            elif part.pages != piece.pages:
                problems.append(f"{path}: the index's pages are not its book's")
            if store.meta_path(path).exists() or page_map.sidecar(store, path).exists():
                problems.append(f"{path}: a sidecar beside a section file")
    return problems


# --- re-pointing the rule files -------------------------------------------

#: Every span carries its L in this corpus, and prose needs it to: "49.in.txt
#: L64-L67, 65.bce.txt L91" is two citations, not three spans of one.
_SPAN = r"\d+(?:-L\d+)?"


def _cited(name: str) -> re.Pattern[str]:
    """A citation of ``name``: the full store path, or the bare file name in prose."""
    return re.compile(
        rf"(?<![\w./-])(?P<dir>(?:[\w-]+/)*){re.escape(name)}"
        rf"(?P<sep>#|\s)L(?P<spans>{_SPAN}(?:,\s*L{_SPAN})*)"
    )


@dataclass(frozen=True, slots=True)
class Moved:
    file: Path
    before: str
    after: str


def _moved(quote: str, where: Mapping[int, tuple[str, tuple[int, ...]]]) -> str | None:
    ref = parse_quote(quote)
    landed = [where.get(n) for n in ref.numbers]
    if not landed or None in landed:
        return None
    targets = {path for path, _ in landed}  # type: ignore[misc]
    if len(targets) != 1:
        return None
    lines = sorted({k for _, ks in landed for k in ks})  # type: ignore[misc]
    return f"{targets.pop()}#{_spans(lines)}"


def repoint_text(
    text: str, proof: str, where: Mapping[int, tuple[str, tuple[int, ...]]]
) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Every citation of ``proof`` in ``text`` re-addressed to its section.

    ``where`` is :func:`addresses` for the proof copy. Returns the new text,
    the (before, after) pairs, and the citations left on the proof copy
    because they span two sections.
    """
    name = proof.rsplit("/", 1)[-1]
    directory = proof.rsplit("/", 1)[0] + "/"
    moved: list[tuple[str, str]] = []
    kept: list[str] = []

    def swap(found: re.Match[str]) -> str:
        prefix = found.group("dir")
        if prefix and prefix != directory:
            return found.group(0)
        spans = found.group("spans").replace(" ", "")
        after = _moved(f"{proof}#L{spans}", where)
        if after is None:
            kept.append(found.group(0))
            return found.group(0)
        new = after if prefix else after.rsplit("/", 1)[-1]
        if found.group("sep") != "#":
            new = new.replace("#", found.group("sep"), 1)
        moved.append((found.group(0), new))
        return new

    return _cited(name).sub(swap, text), moved, kept


def repoint(
    store: ProvenanceStore,
    proofs: Iterable[str],
    files: Iterable[Path],
    *,
    write: bool = False,
    known: Mapping[str, Rule] | None = None,
) -> tuple[list[Moved], list[tuple[Path, str]]]:
    moved: list[Moved] = []
    kept: list[tuple[Path, str]] = []
    chosen = {proof: addresses(store, proof, known) for proof in proofs}
    for file in files:
        original = file.read_text(encoding="utf-8")
        text = original
        for proof, where in chosen.items():
            if proof.rsplit("/", 1)[-1] not in text:
                continue
            text, pairs, left = repoint_text(text, proof, where)
            moved.extend(Moved(file, a, b) for a, b in pairs)
            kept.extend((file, q) for q in left)
        if write and text != original:
            file.write_text(text, encoding="utf-8", newline="")
    return moved, kept


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    do_write = "--write" in args
    args = [a for a in args if not a.startswith("--")]
    store = ProvenanceStore()
    if not args:
        problems = check(store)
        for p in problems:
            print(f"  {p}")
        print(f"{len(splits(store))} proof copies cut; {len(problems)} problems")
        return 1 if problems else 0
    known = rules()
    for layer in args:
        rule = known[layer.strip("/")]
        cuts = write(store, rule) if do_write else []
        print(f"{rule.layer}: {len(cuts)} documents cut, "
              f"{sum(len(c.sections) for c in cuts)} sections")
    return 0


__all__ = [
    "INDEX",
    "Cut",
    "Rule",
    "Section",
    "Split",
    "addresses",
    "chapters",
    "check",
    "cuts",
    "derived",
    "held",
    "in_proof",
    "move_quote",
    "printed",
    "repage",
    "repoint",
    "repoint_text",
    "rules",
    "split",
    "splits",
    "write",
]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
