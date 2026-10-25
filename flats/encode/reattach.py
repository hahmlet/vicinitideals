"""Re-attach the reading decisions a section cut left behind (FOLLOWUPS 73).

A reading decision is filed under its card, ``<document>#<section>``, with a
fingerprint over the lines the card showed. Cutting a city into section files
renamed every card -- ``17.10.r-7.2.txt#17.10.055`` became
``17.10.055.txt#17.10.055`` -- so the decisions made before the cut stopped
naming any card, and the sections they answered came back as unread. The
re-cut tool carries a decision only when its card keeps its name, which a
first cut never does.

This puts a decision back on its section, and only where the words are the
same, the bargain a footnote ruling strikes with its digest:

1. The cards are rebuilt as the queue showed them just before the cut (from
   the commit before the one that first wrote the city's ``sections.json``,
   in a throwaway checkout), and a decision is taken up only if its
   fingerprint is the fingerprint of that card -- one that had already come
   loose before the cut stays loose.
2. The section file cut from the same proof copy, for the same section number,
   is found, and its card's lines are walked back to the proof-copy lines
   they hold (:func:`flats.provenance.sections.held`). The decision carries
   only when those are EXACTLY the lines the old card showed: the section
   file is proved letter for letter against the proof copy, and the proof
   copy has not changed, so the same lines are the same words. A card that
   now shows one word more, or one fewer, is a different question.
3. A carried decision is renamed where it stands, to the new card's name and
   fingerprint; the queue, the answer and the note are not touched.

Everything else is listed with its reason and left exactly as it was. Running
it again finds nothing more to carry; it is safe to repeat.

The decisions live in the jurisdiction files, not the database (the inbox
rows are keyed by the old card name and stand behind the files), so there is
no production half.

Run it::

    uv run python -m flats.encode.reattach or/clackamas/milwaukie            # dry run
    uv run python -m flats.encode.reattach or/clackamas/milwaukie --write
    uv run python -m flats.encode.reattach or/clackamas/milwaukie --before b5ca036c^
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from flats.encode import worklist
from flats.provenance.sections import held, splits
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Reading

REPO = Path(__file__).resolve().parents[2]

#: Run in the old checkout: the cards its queue showed, as JSON.
_DUMP = """
import json, sys
from flats.encode import worklist
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
layers, store = load_rules(), ProvenanceStore()
out = {}
for lid in sys.argv[1:]:
    out[lid] = [
        {"key": c.card_key, "path": c.path, "section": c.section,
         "fingerprint": c.fingerprint, "lines": [ln.line for ln in c.lines]}
        for c in worklist.cards(layers[lid], store, lots={})
    ]
sys.stdout.write(json.dumps(out))
"""


@dataclass(frozen=True, slots=True)
class OldCard:
    """A card as the queue showed it before the cut."""

    key: str
    #: The document it was read in: the proof copy, before it was cut.
    path: str
    section: str
    fingerprint: str
    #: The document lines the card showed.
    lines: frozenset[int]


@dataclass(frozen=True, slots=True)
class NewCard:
    """A card of a section file, with the proof-copy lines its lines hold."""

    key: str
    fingerprint: str
    #: The proof copy and section number the file was cut as.
    proof: str
    section: str
    lines: frozenset[int]


@dataclass
class Plan:
    #: (old card name, new card name, new fingerprint)
    carried: list[tuple[str, str, str]] = field(default_factory=list)
    #: (card name, why it stays)
    detached: list[tuple[str, str]] = field(default_factory=list)


def plan(
    readings: Mapping[str, Reading],
    old: Iterable[OldCard],
    new: Iterable[NewCard],
) -> Plan:
    """Which decisions go back on a section, and why each other one does not.

    Pure: the cards are handed in. A decision on a card that still exists is
    not this tool's (the queue already shows it, current or moved).
    """
    before = {c.key: c for c in old}
    now = list(new)
    names = {c.key for c in now}
    by_section = {(c.proof, c.section): c for c in now}
    out = Plan()
    taken: set[str] = set()
    for key, reading in sorted(readings.items()):
        if key in names:
            continue
        was = before.get(key)
        if was is None:
            out.detached.append((key, "no such card before the cut"))
            continue
        if reading.fingerprint != was.fingerprint:
            out.detached.append((key, "had already come loose before the cut"))
            continue
        card = by_section.get((was.path, was.section))
        if card is None:
            out.detached.append((key, "no section file holds this section's unread lines now"))
            continue
        if card.key in readings or card.key in taken:
            out.detached.append((key, f"{card.key} already carries a decision"))
            continue
        if card.lines != was.lines:
            more = len(card.lines - was.lines)
            fewer = len(was.lines - card.lines)
            out.detached.append(
                (key, f"the words changed: {more} line(s) not read then, {fewer} read then and gone")
            )
            continue
        out.carried.append((key, card.key, card.fingerprint))
        taken.add(card.key)
    return out


def cut_commit(layer_id: str) -> str:
    """The commit before the one that first wrote ``layer_id``'s index."""
    index = f"flats/provenance/docs/{layer_id}/sections.json"
    found = subprocess.run(
        ["git", "log", "--format=%H", "--diff-filter=A", "--", index],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()
    if not found:
        raise ValueError(f"{layer_id} has never been cut")
    return f"{found[-1]}^"


def old_cards(rev: str, layer_ids: Sequence[str]) -> dict[str, list[OldCard]]:
    """The cards each layer's queue showed at ``rev``, from a throwaway checkout."""
    with tempfile.TemporaryDirectory(prefix="reattach-") as tmp:
        tree = Path(tmp) / "tree"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(tree), rev],
            cwd=REPO, capture_output=True, check=True,
        )
        try:
            env = {**os.environ, "PYTHONPATH": str(tree), "PYTHONIOENCODING": "utf-8"}
            got = subprocess.run(
                [sys.executable, "-c", _DUMP, *layer_ids],
                cwd=tree, env=env, capture_output=True, text=True, encoding="utf-8", check=True,
            ).stdout
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(tree)], cwd=REPO, capture_output=True
            )
    raw = json.loads(got)
    return {
        lid: [
            OldCard(c["key"], c["path"], c["section"], c["fingerprint"], frozenset(c["lines"]))
            for c in rows
        ]
        for lid, rows in raw.items()
    }


def new_cards(
    layer_id: str,
    store: ProvenanceStore,
    lines_of: Callable[[str], Sequence[Sequence[int]]] | None = None,
) -> list[NewCard]:
    """This layer's cards on section files, each as the proof-copy lines it shows."""
    lines_of = lines_of or (lambda path: held(store, path))
    cut = {s_path: (proof, s.number) for proof, c in splits(store).items() for s in c.sections
           for s_path in (c.path(s),)}
    out = []
    for card in worklist.cards(load_rules()[layer_id], store, lots={}):
        where = cut.get(card.path)
        if where is None:
            continue
        src = lines_of(card.path)
        proof_lines = frozenset(k for ln in card.lines for k in src[ln.line - 1])
        out.append(NewCard(card.card_key, card.fingerprint, where[0], where[1], proof_lines))
    return out


def _rekey(lines: list[str], old_key: str, new_key: str, fingerprint: str) -> list[str]:
    """``lines`` with the ``readings`` entry ``old_key`` renamed and re-stamped
    where it stands; its queue, answer and note are left byte for byte."""
    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == "readings:"), None)
    if start is None:
        raise ValueError("no readings block")
    stop = start + 1
    while stop < len(lines) and (not lines[stop].strip() or lines[stop].startswith((" ", "	", "#"))):
        stop += 1
    here = next((i for i in range(start + 1, stop) if worklist._entry_key(lines[i]) == old_key), None)
    if here is None:
        raise ValueError(f"no reading {old_key}")
    if any(worklist._entry_key(lines[i]) == new_key for i in range(start + 1, stop)):
        raise ValueError(f"{new_key} already carries a decision")
    end = here + 1
    while end < stop and (not lines[end].strip() or lines[end].startswith("    ")):
        end += 1
    body = list(lines[here:end])
    body[0] = f'  "{new_key}":'
    stamp = [k for k, ln in enumerate(body) if ln.startswith("    fingerprint:")]
    if len(stamp) != 1:
        raise ValueError(f"{old_key}: not one fingerprint line")
    body[stamp[0]] = f"    fingerprint: {fingerprint}"
    return lines[:here] + body + lines[end:]


def apply(layer_id: str, result: Plan, path: Path | None = None) -> Path:
    """Re-file every carried decision in the jurisdiction file, in place."""
    path = path or worklist.layer_path(layer_id)
    raw = path.read_text(encoding="utf-8")
    text = raw.splitlines()
    for old_key, new_key, fingerprint in result.carried:
        text = _rekey(text, old_key, new_key, fingerprint)
    path.write_text(worklist.NEWLINE.join(text) + worklist.NEWLINE, encoding="utf-8", newline="")
    try:
        load_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    return path


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    do_write = "--write" in args
    rev = ""
    if "--before" in args:
        at = args.index("--before")
        rev = args[at + 1]
        del args[at : at + 2]
    layers = [a.strip("/") for a in args if not a.startswith("--")]
    if len(layers) != 1:
        print("usage: python -m flats.encode.reattach <layer> [--before <rev>] [--write]")
        return 2
    layer_id = layers[0]
    rev = rev or cut_commit(layer_id)
    store = ProvenanceStore()
    readings = load_rules()[layer_id].readings
    result = plan(readings, old_cards(rev, [layer_id])[layer_id], new_cards(layer_id, store))
    print(f"{layer_id} (cards as of {rev}): carried {len(result.carried)}, "
          f"left detached {len(result.detached)}")
    for old_key, new_key, _ in result.carried:
        print(f"  CARRIED {old_key} -> {new_key}")
    for key, why in result.detached:
        print(f"  DETACHED {key}: {why}")
    if do_write and result.carried:
        apply(layer_id, result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
