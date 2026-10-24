"""The provenance store — the code text every encoded number came from.

A citation that is only a URL is not provenance. URLs rot, municipal codifiers
renumber sections, and "PCC 33.110.220" meant something different two amendments
ago. What makes an encoded number auditable is the *text* it was read from, kept
verbatim, hashed, and quotable by line.

So each cited source is fetched once, written under ``flats/provenance/`` as
plain text beside a small sidecar recording its URL, retrieval date and SHA-256,
and referenced from rule values as ``path#L42-L48``. Lot detail can then show
the sentence behind a setback, and a reviewer can check the encoding against the
words rather than against another database.

**Staleness is derived, never stored.** When a re-fetch produces different text,
every value citing that document becomes untrusted — but nothing rewrites the
YAML to say so. The hash is compared at load time and the status is computed
from it. Writing `stale` into the rule files would mean hand-authored files
churning under a robot, comments lost to a YAML round-trip, and two sources of
truth that can disagree. A derived answer cannot disagree with itself.

Fetching is injected rather than imported, so the drift watch is testable
without a network and the store has no opinion about HTTP.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

#: Documents live beside the code but in their own subtree. Thousands of code
#: excerpts interleaved with modules would make the package unreadable, and
#: keeping them apart means a stored document can never shadow a module.
STORE_ROOT = Path(__file__).resolve().parent / "docs"

#: In a jurisdiction's folder: which fetched documents were cut into section
#: files, where each section sits in its proof copy, its hash and its pages.
#: The section files carry no sidecars of their own; this is their bookkeeping,
#: one file for the jurisdiction. See ``flats/provenance/sections.py``.
INDEX = "sections.json"


@dataclass(frozen=True, slots=True)
class Part:
    """A section file and the proof copy it was cut from."""

    #: Store path of the section file.
    path: str
    #: Store path of the proof copy.
    proof: str
    number: str
    #: First and last line of the slice in the proof copy, 1-based, inclusive.
    first: int
    last: int
    #: Hash of the section file's text.
    sha256: str
    #: (PDF page, first line of the section on it), in line order.
    pages: tuple[tuple[int, int], ...] = ()

    @property
    def layer(self) -> str:
        return self.proof.rsplit("/", 1)[0]


def _parts_in(index: Path, directory: str) -> dict[str, Part]:
    """Every section an index records, keyed by the section file's store path."""
    raw = json.loads(index.read_text(encoding="utf-8"))
    out: dict[str, Part] = {}
    for name, body in raw.get("documents", {}).items():
        for number, first, last, file, digest, pages in body["sections"]:
            path = f"{directory}/{file}"
            out[path] = Part(
                path=path,
                proof=f"{directory}/{name}",
                number=number,
                first=first,
                last=last,
                sha256=digest,
                pages=tuple((n, line) for n, line in pages),
            )
    return out

#: ``or/multnomah/portland/33.110.txt#L42-L48`` -- path, then optional line
#: spans. Several are allowed, comma-separated: a number stated in a table row
#: and qualified by a footnote three lines further down is cited from both
#: places or from neither, and "from neither" is how a citation ends up
#: pointing at half of its own evidence.
_SPAN = r"\d+(?:-L?\d+)?"
_QUOTE_RE = re.compile(rf"^(?P<path>[^#]+?)(?:#L(?P<spans>{_SPAN}(?:,\s*L?{_SPAN})*))?$")


class ProvenanceError(Exception):
    """A citation does not resolve to stored text."""


@dataclass(frozen=True, slots=True)
class QuoteRef:
    """A parsed ``path#Lstart-Lend`` reference, of one span or several."""

    path: str
    #: (first, last) line pairs, ascending and non-overlapping. Empty means
    #: the whole document.
    spans: tuple[tuple[int, int], ...] = ()

    @property
    def whole_document(self) -> bool:
        return not self.spans

    @property
    def start(self) -> int | None:
        """The first line cited: where a reviewer starts reading."""
        return self.spans[0][0] if self.spans else None

    @property
    def end(self) -> int | None:
        """The last line cited: what the document has to be long enough to hold."""
        return self.spans[-1][1] if self.spans else None

    @property
    def numbers(self) -> tuple[int, ...]:
        """Every line this quote names, in order."""
        return tuple(n for first, last in self.spans for n in range(first, last + 1))


def parse_quote(quote: str) -> QuoteRef:
    """Parse a quote reference, failing loudly on a malformed one.

    A citation nobody can resolve is worse than no citation: it reads as
    evidence while pointing at nothing.
    """
    m = _QUOTE_RE.match(quote.strip())
    if not m or not m.group("path"):
        raise ProvenanceError(f"malformed quote reference {quote!r} - expected 'path#L10-L14'")
    spans: list[tuple[int, int]] = []
    for piece in (m.group("spans") or "").split(","):
        piece = piece.strip().lstrip("L")
        if not piece:
            continue
        first, _, last = piece.partition("-")
        start = int(first)
        end = int(last.lstrip("L")) if last else start
        if start < 1:
            raise ProvenanceError(f"{quote!r}: line numbers are 1-based")
        if end < start:
            raise ProvenanceError(f"{quote!r}: end line precedes start line")
        if spans and start <= spans[-1][1]:
            # Backwards or overlapping. Both mean the citation was written
            # against a document that has since moved, and a reviewer reading
            # the spans in the order given sees a line twice or out of order.
            raise ProvenanceError(f"{quote!r}: spans must ascend and not overlap")
        spans.append((start, end))
    return QuoteRef(path=m.group("path"), spans=tuple(spans))


@dataclass(frozen=True, slots=True)
class Document:
    """One stored source document and the hash that detects it changing."""

    path: str
    url: str
    retrieved: date
    sha256: str
    text: str
    #: Which extraction algorithm produced this text. Empty for documents
    #: stored before the field existed. A hash that moves because the
    #: extractor changed is not an amendment, and telling the two apart
    #: needs the algorithm on the record beside the hash.
    extractor: str = ""

    def lines(self, ref: QuoteRef) -> str:
        """The quoted lines, or the whole document when no span is given."""
        return "\n".join(text for _, text in self.numbered(ref))

    def numbered(self, ref: QuoteRef) -> tuple[tuple[int, str], ...]:
        """The quoted lines, each with the number it carries in the document.

        The number is half the citation. A view that renumbers from one, or
        that silently closes the gap between two spans, shows a reviewer
        something they cannot find again in the store.
        """
        all_lines = self.text.splitlines()
        if ref.whole_document:
            return tuple(enumerate(all_lines, start=1))
        if ref.end is not None and ref.end > len(all_lines):
            raise ProvenanceError(
                f"{self.path}: quote asks for line {ref.end}, document has {len(all_lines)}"
            )
        return tuple((n, all_lines[n - 1]) for n in ref.numbers)


def sha256(text: str) -> str:
    """Hash of the normalized text.

    Line endings are normalized first: a codifier serving CRLF one day and LF
    the next would otherwise register as a substantive amendment and flip every
    value on the page to stale for nothing.
    """
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class ProvenanceStore:
    """Documents on disk under a root, addressed by relative path."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else STORE_ROOT
        #: index file -> (its mtime and size, what it records). Read once per
        #: edition, because every load of a section file asks it.
        self._indexes: dict[Path, tuple[tuple[int, int], dict[str, Part]]] = {}

    # --- paths -------------------------------------------------------

    def _under_root(self, path: str) -> Path:
        """``root / path``, refusing anything that leaves the store.

        A quote reference is text: it comes out of a YAML file an encoder
        wrote, and — since the review pages — out of a query string as well.
        Joining it onto a root is a filesystem read, so the join is checked
        rather than trusted. "or/multnomah/portland/33.110.txt" resolves under
        the root; "../../.env" and "/etc/passwd" do not, and neither is a
        citation any document could carry.
        """
        candidate = (self.root / path).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ProvenanceError(f"{path!r} is outside the provenance store")
        return candidate

    def text_path(self, path: str) -> Path:
        return self._under_root(path)

    def meta_path(self, path: str) -> Path:
        return self._under_root(f"{path}.meta.json")

    def exists(self, path: str) -> bool:
        if not self.text_path(path).is_file():
            return False
        return self.meta_path(path).is_file() or self.part_of(path) is not None

    # --- section files -------------------------------------------------

    def _index(self, file: Path) -> dict[str, Part]:
        try:
            stat = file.stat()
        except OSError:
            return {}
        stamp = (stat.st_mtime_ns, stat.st_size)
        held = self._indexes.get(file)
        if held is None or held[0] != stamp:
            directory = str(file.parent.relative_to(self.root)).replace("\\", "/")
            held = (stamp, _parts_in(file, directory))
            self._indexes[file] = held
        return held[1]

    def parts(self) -> dict[str, Part]:
        """Every section file in the store, keyed by its path."""
        out: dict[str, Part] = {}
        for index in sorted(self.root.rglob(INDEX)):
            out.update(self._index(index))
        return out

    def part_of(self, path: str) -> Part | None:
        """Where a section file was cut from, or None for any other document.

        A section file sits in a chapter folder under its jurisdiction's, so
        its index is one folder up.
        """
        here = self.root / path
        for folder in (here.parent.parent, here.parent):
            index = folder / INDEX
            if index.is_file():
                found = self._index(index).get(path)
                if found is not None:
                    return found
        return None

    def layer_of(self, path: str) -> str:
        """The jurisdiction a stored document belongs to.

        A document's folder, except that a section file is filed a folder
        deeper, under its chapter.
        """
        part = self.part_of(path)
        return part.layer if part is not None else path.rsplit("/", 1)[0]

    def documents(self) -> list[str]:
        """Every stored document a citation can name, sorted.

        Matched on the way out of the walk rather than filtered afterwards:
        the store holds a ``.meta.json`` beside every document, so walking
        everything and asking each entry whether it is a file was two stat
        calls per document to find one. The sidecars cannot match ``*.txt``,
        which is what the discarded name test was for.

        A proof copy that has been cut into section files is not listed. Its
        words are listed once, in their sections, and every ledger that walks
        this list would otherwise count each line twice. It is still stored,
        still loads, and is what :meth:`fetched` hands the drift check.
        """
        kept = self.proofs()
        return sorted(
            path
            for p in self.root.rglob("*.txt")
            if p.is_file()
            and (path := str(p.relative_to(self.root)).replace("\\", "/")) not in kept
        )

    def proofs(self) -> frozenset[str]:
        """Every fetched document that has been cut into section files."""
        out: set[str] = set()
        for index in self.root.rglob(INDEX):
            directory = str(index.parent.relative_to(self.root)).replace("\\", "/")
            raw = json.loads(index.read_text(encoding="utf-8"))
            out.update(f"{directory}/{name}" for name in raw.get("documents", {}))
        return frozenset(out)

    def section_files(self) -> frozenset[str]:
        """Every section file: derived from a proof copy, never fetched itself."""
        return frozenset(self.parts())

    def section_of(self, path: str, cut: frozenset[str] | None = None) -> str | None:
        """The section a section file holds, or None for any other document.

        Every line of a section file is that section, whatever a running
        header or a wrapped reference inside it looks like. ``cut`` is
        :meth:`section_files`, for a caller asking about many paths.
        """
        if path not in (cut if cut is not None else self.section_files()):
            return None
        return path.rsplit("/", 1)[-1].removesuffix(".txt")

    def fetched(self) -> list[str]:
        """Every document as it was fetched: what a re-fetch can be compared with.

        A section file carries its book's URL, but it is a slice of what that
        URL serves, so comparing it with a re-fetch would call every section
        changed. Its proof copy stands in for it.
        """
        cut = self.section_files()
        return sorted({p for p in self.documents() if p not in cut} | self.proofs())

    @staticmethod
    def owned(directory: Path) -> list[Path]:
        """The ``*.txt`` under one jurisdiction's folder that a citation can name.

        For tools that glob a jurisdiction's folder rather than ask the store:
        the proof copies are left out for the same reason :meth:`documents`
        leaves them out, and the section files in its chapter folders are put
        in. A chapter folder on its own owns nothing -- its files are its
        jurisdiction's -- so walking every folder lists each file once. Static
        because those tools are handed a folder, often a test's, not a store.
        """
        above = directory.parent / INDEX
        if above.is_file() and directory in ProvenanceStore._chapter_folders(above):
            return []
        index = directory / INDEX
        skip: set[str] = set()
        cut: list[Path] = []
        if index.is_file():
            raw = json.loads(index.read_text(encoding="utf-8")).get("documents", {})
            skip = set(raw)
            cut = [directory / row[3] for body in raw.values() for row in body["sections"]]
        top = [p for p in directory.glob("*.txt") if p.is_file() and p.name not in skip]
        return sorted({*top, *(p for p in cut if p.is_file())})

    @staticmethod
    def _chapter_folders(index: Path) -> frozenset[Path]:
        raw = json.loads(index.read_text(encoding="utf-8")).get("documents", {})
        return frozenset(
            (index.parent / row[3]).parent for body in raw.values() for row in body["sections"]
        )

    @staticmethod
    def owned_tree(root: Path) -> list[Path]:
        """:meth:`owned` for every folder under ``root``."""
        folders = sorted({p.parent for p in root.rglob("*.txt")})
        return sorted({p for folder in folders for p in ProvenanceStore.owned(folder)})

    @staticmethod
    def cut_names(directory: Path) -> frozenset[str]:
        """The names of the section files cut in one jurisdiction's folder."""
        index = directory / INDEX
        if not index.is_file():
            return frozenset()
        raw = json.loads(index.read_text(encoding="utf-8")).get("documents", {})
        return frozenset(
            row[3].rsplit("/", 1)[-1] for body in raw.values() for row in body["sections"]
        )

    # --- read / write ------------------------------------------------

    def save(
        self, path: str, *, url: str, text: str, retrieved: date, extractor: str = ""
    ) -> Document:
        """Write a document and its sidecar. Overwrites — re-fetching is normal."""
        if "\x00" in text:
            # Not sanitised here on purpose. A NUL means some extractor met a
            # glyph it could not decode, and silently swapping it at the last
            # gate would store a document whose extractor string is a lie
            # about how it was produced. The extraction fixes it and declares
            # itself — see flats/provenance/fetch.py:UNDECODED — and this only
            # has to make sure no path skips that.
            raise ProvenanceError(
                f"{path}: the extracted text carries "
                f"{text.count(chr(0))} NUL byte(s), which no document contains. "
                f"They are a glyph the extractor could not decode; it must "
                f"declare them rather than pass them through."
            )
        text_path = self.text_path(path)
        text_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = text.replace("\r\n", "\n")
        # newline="" suppresses the platform translation that would put CRLF back
        # on Windows. A store written on one OS and read on another has to be
        # byte-identical, or every hash comparison fails at once.
        text_path.write_text(normalized, encoding="utf-8", newline="")

        doc = Document(
            path=path,
            url=url,
            retrieved=retrieved,
            sha256=sha256(normalized),
            text=normalized,
            extractor=extractor,
        )
        meta = {"url": url, "retrieved": retrieved.isoformat(), "sha256": doc.sha256}
        if extractor:
            meta["extractor"] = extractor
        self.meta_path(path).write_text(
            json.dumps(meta, indent=2)
            + "\n",
            encoding="utf-8",
            newline="",
        )
        return doc

    def load(self, path: str) -> Document:
        text_path, meta_path = self.text_path(path), self.meta_path(path)
        if not text_path.is_file():
            raise ProvenanceError(f"no stored text at {path!r} — fetch it before citing it")
        if not meta_path.is_file():
            part = self.part_of(path)
            if part is None:
                raise ProvenanceError(f"{path!r} has text but no sidecar; its hash is unknown")
            # A section file's URL and date are its book's, and its hash is
            # the one its index recorded when it was cut.
            book = self.load(part.proof)
            return Document(
                path=path,
                url=book.url,
                retrieved=book.retrieved,
                sha256=part.sha256,
                text=text_path.read_text(encoding="utf-8").replace("\r\n", "\n"),
                extractor=book.extractor,
            )

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        # Normalize on the way in too: a document that reached the store by some
        # other route — a git checkout with autocrlf on — still has to hash to
        # the same value as the one that was fetched.
        text = text_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        return Document(
            path=path,
            url=meta["url"],
            retrieved=date.fromisoformat(meta["retrieved"]),
            sha256=meta["sha256"],
            text=text,
            extractor=meta.get("extractor", ""),
        )

    def quote(self, quote: str) -> str:
        """Resolve a ``path#L10-L14`` reference to the text it names."""
        ref = parse_quote(quote)
        return self.load(ref.path).lines(ref)

    # --- integrity ---------------------------------------------------

    def tampered(self) -> list[str]:
        """Documents whose text no longer matches their recorded hash.

        Not drift — drift is the source changing upstream. This is the local
        copy changing, which means an edit to evidence. Either way the values
        citing it can no longer be trusted, but the causes need different fixes.
        """
        bad: list[str] = []
        for path in sorted(set(self.documents()) | self.proofs()):
            try:
                doc = self.load(path)
            except ProvenanceError:
                bad.append(path)
                continue
            if sha256(doc.text) != doc.sha256:
                bad.append(path)
        return bad


@dataclass(frozen=True, slots=True)
class DriftResult:
    """What a re-fetch found for one document."""

    path: str
    url: str
    #: unchanged | changed | unreachable | missing
    state: str
    stored_sha: str | None = None
    fetched_sha: str | None = None
    detail: str = ""

    @property
    def invalidates(self) -> bool:
        """True when values citing this document can no longer be trusted.

        ``unreachable`` deliberately does not invalidate. A codifier's site
        being down is not evidence the law changed, and demoting a county's
        entire rule set because of a timeout would be a self-inflicted outage.
        It is reported so the gap is visible, not silently treated as fine.
        """
        return self.state in ("changed", "missing")


Fetcher = Callable[[str], str]


def check_drift(
    store: ProvenanceStore, fetch: Fetcher, *, paths: Iterable[str] | None = None
) -> list[DriftResult]:
    """Re-fetch each stored document and compare hashes.

    ``fetch`` takes a URL and returns text; injected so this is testable without
    a network and so the store stays out of the HTTP business.
    """
    results: list[DriftResult] = []
    for path in sorted(paths) if paths is not None else store.fetched():
        try:
            doc = store.load(path)
        except ProvenanceError as exc:
            results.append(DriftResult(path=path, url="", state="missing", detail=str(exc)))
            continue

        try:
            fresh = sha256(fetch(doc.url))
        except Exception as exc:  # any transport failure — treat alike
            results.append(
                DriftResult(
                    path=path,
                    url=doc.url,
                    state="unreachable",
                    stored_sha=doc.sha256,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        results.append(
            DriftResult(
                path=path,
                url=doc.url,
                state="unchanged" if fresh == doc.sha256 else "changed",
                stored_sha=doc.sha256,
                fetched_sha=fresh,
            )
        )
    return results
