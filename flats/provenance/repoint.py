"""Follow a citation when the document underneath it shifts.

Every quote in this corpus is a line number — ``path#L385-L392`` — which is what
makes provenance checkable and also what makes it brittle. A city republishes a
PDF, one sentence is inserted at line 612, and every citation below it now points
one line high. Nothing crashes. The quote still resolves, to the wrong words.

Until now the only answer was the blunt one: refuse the refresh, or accept it and
re-read the whole chapter. Gresham's Pleasant Valley chapter is 1,035 lines with
61 citations into it, and it drifted by a single inserted line. Re-reading 61
values because one sentence moved is how a corpus watch becomes a thing nobody
runs.

**The insight is that a line number is a pointer, not the evidence.** The
evidence is the words. If a cited line's text survives the shift byte for byte,
the citation can be re-pointed at where those words went and nothing about the
encoding has changed. If the words themselves changed, no amount of arithmetic
helps and a human has to read it. This module draws exactly that line and
refuses to guess across it.

Three deliberate limits:

*Stranded quotes are never rewritten.* If any single line a quote names has no
counterpart in the new text, the whole quote is left alone and reported. A
partially migrated citation is worse than a stale one, because it looks migrated.

*A span that grows keeps its ends.* When a line is inserted inside a cited span,
the new span covers it. The reviewer then sees the inserted sentence, which is
the conservative direction: a citation may show more than it did, never less.

*Tests are reported, never rewritten.* Test files pin quotes on purpose. A tool
that edits an assertion to make it pass is not a tool, and the whole point of
those pins is that a human decides.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from flats.encode.verify import (
    LOG_PATH,
    VerKey,
    Verification,
    VerificationLog,
    fingerprint,
    like_payload,
)
from flats.provenance.store import ProvenanceError, parse_quote
from flats.rules.model import LIKE, Layer

#: Where a re-point may write. Rule YAML and footnote rulings both carry quotes;
#: both are hand-authored, so the rewrite is a substring swap on the raw file and
#: never a YAML round-trip. Comments, ordering and block style survive untouched.
CONFIG_DIRS = ("jurisdictions", "footnotes")

#: A line number map: old line (1-based) -> new line. A line absent from this
#: map is one whose words did not survive.
LineMap = dict[int, int]


def line_map(old: Sequence[str], new: Sequence[str]) -> LineMap:
    """Where each old line's text ended up, for the lines that still exist.

    ``autojunk`` is off. It heuristically ignores lines that recur in more than
    1% of a large document, and in a code chapter the recurring lines are the
    blank ones and the table rules — exactly the anchors an alignment needs.
    """
    matcher = difflib.SequenceMatcher(None, list(old), list(new), autojunk=False)
    mapping: LineMap = {}
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def _format(path: str, spans: Sequence[tuple[int, int]]) -> str:
    if not spans:
        return path
    parts = [f"L{first}" if first == last else f"L{first}-L{last}" for first, last in spans]
    return f"{path}#{','.join(parts)}"


def move_quote(quote: str, mapping: LineMap) -> tuple[str, tuple[int, ...]]:
    """Re-point one quote, or report which of its lines it lost.

    Returns ``(new_quote, ())`` when every cited line survived, and
    ``("", lost_lines)`` when any did not. Never a half-migrated quote.
    """
    ref = parse_quote(quote)
    if ref.whole_document:
        return quote, ()

    moved: list[tuple[int, int]] = []
    lost: list[int] = []
    for first, last in ref.spans:
        landed = [mapping[n] for n in range(first, last + 1) if n in mapping]
        lost.extend(n for n in range(first, last + 1) if n not in mapping)
        if landed:
            moved.append((min(landed), max(landed)))
    if lost:
        return "", tuple(lost)

    # Spans cannot collide, and the reason is worth writing down because the
    # obvious defensive merge here would be dead code. The map is built from
    # difflib's equal blocks, which are strictly increasing, so a later span's
    # first line always lands after an earlier span's last. `parse_quote` will
    # read back what comes out of here. What CAN happen is that a line inserted
    # between two spans belongs to neither — correctly, since the citation named
    # neither of the sentences it now sits between.
    return _format(ref.path, moved), ()


@dataclass(frozen=True, slots=True)
class Move:
    """One citation that followed its words."""

    file: Path
    line: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class Stranded:
    """One citation whose words changed, which no re-point can decide."""

    file: Path
    line: int
    quote: str
    #: The old line numbers with no counterpart in the new text.
    lines: tuple[int, ...]


def _reference(doc_path: str) -> re.Pattern[str]:
    span = r"\d+(?:-L?\d+)?"
    return re.compile(rf"{re.escape(doc_path)}(?:#L{span}(?:\s*,\s*L?{span})*)?")


def repoint_files(
    doc_path: str, mapping: LineMap, paths: Iterable[Path], *, write: bool = False
) -> tuple[list[Move], list[Stranded]]:
    """Re-point every citation into ``doc_path`` found in ``paths``.

    The rewrite is a substring replacement on the file's own text. Nothing is
    parsed and re-serialised, so a file with no moved citation is not touched at
    all — including its mtime, which keeps a no-op run out of a diff.
    """
    pattern = _reference(doc_path)
    moves: list[Move] = []
    stranded: list[Stranded] = []

    for path in paths:
        original = path.read_text(encoding="utf-8")
        if doc_path not in original:
            continue
        lines = original.splitlines(keepends=True)
        touched = False
        for index, line in enumerate(lines):
            replaced = line
            for match in pattern.finditer(line):
                quote = match.group(0)
                try:
                    after, lost = move_quote(quote, mapping)
                except ProvenanceError:
                    # Malformed already; a re-point is not the place to fix it.
                    continue
                if lost:
                    stranded.append(Stranded(path, index + 1, quote, lost))
                    continue
                if after == quote:
                    continue
                replaced = replaced.replace(quote, after)
                moves.append(Move(path, index + 1, quote, after))
            if replaced != line:
                lines[index] = replaced
                touched = True
        if touched and write:
            path.write_text("".join(lines), encoding="utf-8")

    return moves, stranded


def config_files(root: Path) -> list[Path]:
    """The hand-authored YAML a re-point may rewrite."""
    found: list[Path] = []
    for name in CONFIG_DIRS:
        found.extend(sorted((root.parent / name).rglob("*.yaml")))
    return found


def mentions(doc_path: str, root: Path) -> list[tuple[Path, int]]:
    """Where else this document is cited — test pins, reported not rewritten.

    The stem is searched as well as the whole path, and that is not belt and
    braces. The first run of this reported one pinned file and there were three:
    the other two never write the path on a line. One builds it from an f-string
    (``f"{GRESHAM}/4.1400.pleasant-valley.txt"``) and one asks the store for a
    chapter by stem, so a literal search for the full path sees neither, and
    both pin line numbers that had just moved.

    A false positive here costs a line of output somebody skims past. A false
    negative costs an assertion that silently pins the wrong line, which is the
    exact failure this whole module exists to stop.
    """
    stem = doc_path.rsplit("/", 1)[-1].removesuffix(".txt")
    pattern = re.compile(rf"{_reference(doc_path).pattern}|{re.escape(stem)}")
    found: list[tuple[Path, int]] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                found.append((path, index))
    return found


def _citations(
    layers: dict[str, Layer], doc_path: str
) -> Iterator[tuple[VerKey, object, str, str]]:
    """Every signable thing whose quote points into this document.

    Yields ``(key, payload, cite, quote)``, where payload is what a signature
    hashes: a value, or the incorporation payload for a zone's ``like:`` claim.
    The ``like:`` case is here because it is the one citation that is not a
    field — a zone adopting another zone's standards cites the sentence that
    says so, and a re-point that moved that quote without moving its signature
    would strand the loudest kind of borrowed rule in the corpus.
    """
    for layer_id, layer in layers.items():
        blocks = [("defaults", layer.defaults)]
        blocks += [(code, zone.values) for code, zone in layer.zones.items()]
        for zone_name, values in blocks:
            for name, value in values.items():
                for part in (value, *value.variants):
                    quote = part.prov.quote or ""
                    if quote.split("#", 1)[0] != doc_path:
                        continue
                    when = tuple(sorted(getattr(part, "when", ())))
                    yield (layer_id, zone_name, name, when), part.value, part.prov.cite, quote
        for code, zone in layer.zones.items():
            like = zone.like
            if like is None:
                continue
            quote = like.prov.quote or ""
            if quote.split("#", 1)[0] == doc_path:
                yield (layer_id, code, LIKE, ()), like_payload(like), like.prov.cite, quote


def survivors(layers: dict[str, Layer], doc_path: str, mapping: LineMap) -> frozenset[VerKey]:
    """Verification keys whose evidence is unchanged, only relocated.

    A refresh withdraws every signature standing on the document, which is right
    when the words moved and wrong when only the numbering did. These are the
    ones to spare: every line they cite still reads exactly as it did when
    somebody signed it.

    The limit worth stating: this compares the *cited* lines, not their
    surroundings. A heading rewritten two lines above a cited row would not
    withdraw the signature. Widening the comparison would spare almost nothing,
    since a chapter that shifts at all shifts most of its context — and the
    document-level hash still demotes the whole file to `stale` until somebody
    accepts the refresh, so nothing here certifies an unread amendment.
    """
    spared: set[VerKey] = set()
    for key, _payload, _cite, quote in _citations(layers, doc_path):
        try:
            _after, lost = move_quote(quote, mapping)
        except ProvenanceError:
            continue
        if not lost:
            spared.add(key)
    return frozenset(spared)


def readdress(
    layers: dict[str, Layer],
    doc_path: str,
    mapping: LineMap,
    *,
    log_path: Path | None = None,
    note: str = "",
) -> list[Verification]:
    """Re-issue the signatures a re-point would otherwise silently orphan.

    A fingerprint hashes the quote string, so moving ``#L385-L392`` to
    ``#L387-L394`` breaks the match even when not one word changed — the value
    would drop back to draft looking like tampering rather than renumbering.

    This appends a fresh entry per spared signature: same reviewer, same date
    they read it, same value and citation, fingerprint recomputed over the new
    address, and a note saying it was moved and why. It is an append to an
    append-only log, so the original signature and this migration both stay on
    disk and a reader can see exactly what happened.

    Two guards make that defensible rather than convenient:

    * only where every cited line's text survived byte for byte, which is
      `survivors`' test and not a judgement call, and
    * only where the *existing* signature still matches the old quote. A
      signature already orphaned for some other reason — the number was edited,
      the citation was retyped — is left orphaned. Re-addressing it would repair
      a broken signature as a side effect of an unrelated refresh, which is the
      one thing this whole apparatus exists to prevent.
    """
    target = log_path or LOG_PATH
    log = VerificationLog.load(target)
    active = log.active()
    issued: list[Verification] = []

    for key, payload, cite, quote in _citations(layers, doc_path):
        prior = active.get(key)
        if prior is None:
            continue
        try:
            after, lost = move_quote(quote, mapping)
        except ProvenanceError:
            continue
        if lost or after == quote:
            continue
        layer_id, zone_name, field, when = key
        standing = fingerprint(
            layer_id, zone_name, field, payload, cite=cite, quote=quote, when=when
        )
        if standing != prior.fingerprint:
            continue
        entry = Verification(
            layer=layer_id,
            zone=zone_name,
            field=field,
            fingerprint=fingerprint(
                layer_id, zone_name, field, payload, cite=cite, quote=after, when=when
            ),
            reviewer=prior.reviewer,
            reviewed=prior.reviewed,
            when=when,
            note=note or f"citation repointed in {doc_path}; cited text unchanged",
        )
        log.append(entry, target)
        issued.append(entry)
    return issued
