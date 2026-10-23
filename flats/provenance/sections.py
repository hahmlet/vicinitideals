"""Code text one section to a file, cut from the document it was fetched as.

A city publishes its code as chapters, and the store kept it that way: one
file per fetch, cited by line -- ``40-41.residential.txt#L225-L233``. The line
says where the words are and nothing about which section they belong to, so a
second tool had to read headings upward to check that a value citing "TDC
40.220" was quoting 40.220 at all (``flats/encode/attribution.py``), and 1,533
values cited a section that tool could not find above its lines.

Here a document is cut at its own headings into one file per section --
``40.220.txt`` -- and a citation names the section by naming the file. Line 1
of every file is its heading, so the line in a citation is a line WITHIN the
section.

**The fetched document stays, untouched, as the proof copy.** It is what the
URL served, what drift re-fetches and compares, and what the PDF page map was
built against. The section files are derived from it and nothing else: a
``sections.json`` beside them records each one's first and last line in the
proof copy and the proof copy's hash, and :func:`check` fails the day a
section file is not exactly that slice of exactly that text. A re-fetch that
changes a proof copy therefore cannot leave section files quietly describing
the old one.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

from flats.provenance import pages as page_map
from flats.provenance.store import (
    INDEX,
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


def rules(path: Path = RULES) -> dict[str, Rule]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, Rule] = {}
    for layer, body in raw.items():
        heading = re.compile(body["heading"])
        if "n" not in heading.groupindex:
            raise ValueError(f"{layer}: the heading pattern names no group 'n'")
        furniture = body.get("furniture")
        out[layer] = Rule(
            layer=layer,
            heading=heading,
            furniture=re.compile(furniture) if furniture else None,
            lead=dict(body.get("lead") or {}),
        )
    return out


@dataclass(frozen=True, slots=True)
class Section:
    number: str
    #: First and last line in the proof copy, 1-based and inclusive.
    first: int
    last: int

    @property
    def file(self) -> str:
        return f"{self.number}.txt"


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

    def at(self, line: int) -> tuple[str, int] | None:
        """Where a proof-copy line lives now: (section path, line within it)."""
        for section in self.sections:
            if section.first <= line <= section.last:
                return self.path(section), line - section.first + 1
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
                sections=tuple(Section(n, a, b) for n, a, b in body["sections"]),
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


def move_quote(quote: str, cuts: Mapping[str, Split]) -> str | None:
    """The same quote addressed to its section, or None when it spans two.

    A quote into a document that was not split is returned unchanged.
    """
    ref = parse_quote(quote)
    cut = cuts.get(ref.path)
    if cut is None or ref.whole_document:
        return quote
    landed = {cut.at(n) for first, last in ref.spans for n in (first, last)}
    if None in landed:
        return None
    targets = {path for path, _ in landed}  # type: ignore[misc]
    if len(targets) != 1:
        return None
    # Every line between a span's ends is in the same section as its ends,
    # because a section is one unbroken run of the proof copy.
    target = targets.pop()
    section = next(s for s in cut.sections if cut.path(s) == target)
    shift = section.first - 1
    parts = [
        f"L{a - shift}" if a == b else f"L{a - shift}-L{b - shift}" for a, b in ref.spans
    ]
    return f"{target}#{','.join(parts)}"


def write(store: ProvenanceStore, rule: Rule, *, only: Iterable[str] | None = None) -> list[Split]:
    """Cut every document in ``rule.layer`` and write the section files."""
    directory = store.root / rule.layer
    chosen = set(only) if only is not None else None
    index_path = directory / INDEX
    existing = json.loads(index_path.read_text(encoding="utf-8"))["documents"] if index_path.is_file() else {}
    already = set(existing)
    made: list[Split] = []
    for text_file in sorted(directory.glob("*.txt")):
        name = text_file.name
        doc_id = text_file.stem
        proof = f"{rule.layer}/{name}"
        if chosen is not None and doc_id not in chosen:
            continue
        if name not in already and _is_section_file(store, proof):
            continue
        doc = store.load(proof)
        lines = _lines(doc.text)
        sections = split(lines, rule, doc_id)
        if not sections:
            continue
        cut = Split(proof=proof, sha256=doc.sha256, sections=tuple(sections))
        pages = page_map.read(store, proof)
        for section in sections:
            path = cut.path(section)
            if store.text_path(path).exists() and not _is_section_file(store, path):
                raise ProvenanceError(f"{path} already exists and is not a section file")
            body = "\n".join(lines[section.first - 1 : section.last]) + "\n"
            store.text_path(path).write_text(body, encoding="utf-8", newline="")
            meta = {
                "url": doc.url,
                "retrieved": doc.retrieved.isoformat(),
                "sha256": sha256(body),
                **({"extractor": doc.extractor} if doc.extractor else {}),
                "part_of": {"document": proof, "first": section.first, "last": section.last},
            }
            store.meta_path(path).write_text(
                json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline=""
            )
            if pages is not None:
                page_map.write(
                    store,
                    _pages_within(pages, path, sha256(body), section),
                    extractor=pages.extractor,
                )
        existing[name] = {
            "sha256": doc.sha256,
            "sections": [[s.number, s.first, s.last] for s in sections],
        }
        made.append(cut)
    if existing:
        index_path.write_text(_index_text(existing), encoding="utf-8", newline="")
    return made


def repage(store: ProvenanceStore, proof: str) -> int:
    """Re-derive the page maps of a proof copy's sections from its own map.

    Called after the proof copy's map is rebuilt; a section's map is never
    built from the PDF itself, so it cannot disagree with its book's.
    """
    cut = splits(store).get(proof)
    pages = page_map.read(store, proof)
    if cut is None or pages is None:
        return 0
    for section in cut.sections:
        path = cut.path(section)
        digest = store.load(path).sha256
        page_map.write(store, _pages_within(pages, path, digest, section), extractor=pages.extractor)
    return len(cut.sections)


def _index_text(documents: Mapping[str, Mapping[str, object]]) -> str:
    """The index, one section to a line, so a re-cut reads as a diff of sections."""
    out = ["{", '  "documents": {']
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


def _pages_within(
    pages: page_map.PageIndex, path: str, digest: str, section: Section
) -> page_map.PageIndex:
    """The proof copy's page map, cut to one section and renumbered from it."""
    out: list[page_map.Page] = []
    for page in pages.pages:
        if page.line > section.last:
            break
        line = max(page.line, section.first) - section.first + 1
        if out and out[-1].line == line:
            out[-1] = page_map.Page(n=page.n, line=line, label=page.label)
        else:
            out.append(page_map.Page(n=page.n, line=line, label=page.label))
    return page_map.PageIndex(
        path=path,
        sha256=digest,
        extractor=pages.extractor,
        source_sha256=pages.source_sha256,
        pages=tuple(out),
    )


def _is_section_file(store: ProvenanceStore, path: str) -> bool:
    meta = store.meta_path(path)
    if not meta.is_file():
        return False
    return "part_of" in json.loads(meta.read_text(encoding="utf-8"))


def check(store: ProvenanceStore | None = None) -> list[str]:
    """Every way a section file has stopped being its slice of the proof copy."""
    store = store or ProvenanceStore()
    problems: list[str] = []
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
        lines = _lines(doc.text)
        for section in cut.sections:
            path = cut.path(section)
            want = "\n".join(lines[section.first - 1 : section.last]) + "\n"
            try:
                # Normalised like every load: a checkout with autocrlf on hands
                # back CRLF, and that is not a different slice.
                got = store.text_path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
            except OSError:
                problems.append(f"{path}: missing")
                continue
            if got != want:
                problems.append(f"{path}: not lines {section.first}-{section.last} of {proof}")
            meta = json.loads(store.meta_path(path).read_text(encoding="utf-8"))
            if meta.get("sha256") != sha256(got) or meta.get("part_of", {}).get("document") != proof:
                problems.append(f"{path}: sidecar does not describe this slice")
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


def repoint_text(text: str, cut: Split) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Every citation of ``cut.proof`` in ``text`` re-addressed to its section.

    Returns the new text, the (before, after) pairs, and the citations left on
    the proof copy because they span two sections.
    """
    name = cut.proof.rsplit("/", 1)[-1]
    directory = cut.directory + "/"
    moved: list[tuple[str, str]] = []
    kept: list[str] = []

    def swap(found: re.Match[str]) -> str:
        prefix = found.group("dir")
        if prefix and prefix != directory:
            return found.group(0)
        spans = found.group("spans").replace(" ", "")
        quote = f"{cut.proof}#L{spans}"
        after = move_quote(quote, {cut.proof: cut})
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
    cuts: Iterable[Split], files: Iterable[Path], *, write: bool = False
) -> tuple[list[Moved], list[tuple[Path, str]]]:
    moved: list[Moved] = []
    kept: list[tuple[Path, str]] = []
    chosen = list(cuts)
    for file in files:
        original = file.read_text(encoding="utf-8")
        text = original
        for cut in chosen:
            if cut.proof.rsplit("/", 1)[-1] not in text:
                continue
            text, pairs, left = repoint_text(text, cut)
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
    "Rule",
    "Section",
    "Split",
    "chapters",
    "check",
    "derived",
    "move_quote",
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
