"""Read back the footnotes we decided did not reach us.

Three checks stand over the footnote register and until now only two of them
ran on anything.

``qualified`` goes value → note: for every number we hold, which footnotes sit
over the lines it was read from, and has anybody ruled on them. ``applied``
goes note → value: a ruling that says "encoded" names the figure it became, so
the claim can be checked against the encoding rather than taken on trust. That
one covers **45** rulings.

Neither touches ``dismissed``, which is **784** of the 884 rulings on the
register -- and 478 of those sit over at least one number we hold, between them
touching **1,614 of the 1,792** qualified values. Nine tenths of the corpus
rests, in part, on somebody having decided a sentence did not apply. The rule
for a dismissal is that it carries a reason in writing, and that is all that
has ever been enforced: a reason is checked for existing, never for being
right.

A dismissal is the failure that cannot announce itself. An unread note blocks.
An unmeasured note caps the verdict at REVIEW. A wrong *encoding* produces a
number some later reader can compare against the page. A wrong dismissal
produces nothing at all -- the note simply stops being mentioned, and the
standard underneath it keeps whatever value it had, one condition looser than
the code actually allows. Which is the direction that calls a lot GREEN when it
is not.

So: read them again, and take the reason away first. The card carries the
note's own words, the passage of code it hangs off, and the list of standards
it governs. It does **not** carry why we waved it away, because a reader shown
"detached dwellings only" will agree with it. Two questions per card, and the
second is the one that matters:

1. Does this note reach a four-unit attached townhome on this lot?
2. If it does, does it make a standard *stricter* or *looser*?

Dismissing a relaxation is safe -- it costs lots, never correctness, which is
the trade this project makes everywhere. Dismissing a restriction is the bug.
So a disagreement is only alarming in one corner of the grid, and the report
sorts for it.

Usage:
    uv run python -m flats.encode.waved --out <dir> [--batch 25]
    uv run python -m flats.encode.waved --score <dir> [--csv out.csv]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from flats.encode.dispositions import Note
from flats.encode.qualified import qualified
from flats.encode.reread import CONTEXT, _above, _passage
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.fields import FIELDS

#: Verdicts a reader may return on whether the note reaches our building.
REACH = ("not_ours", "reaches", "some_zones")

#: And which way it moves a standard when it does reach us. Only ``stricter``
#: can turn a red lot green by being missed.
DIRECTION = ("stricter", "looser", "neither")


def _standards(pairs: list[tuple[str, str]]) -> list[str]:
    """``zone -> standard`` lines a reader can scan, deduplicated."""
    by_zone: dict[str, set[str]] = defaultdict(set)
    for zone, field in pairs:
        fdef = FIELDS.get(field)
        by_zone[zone].add(fdef.shown if fdef else field)
    return [f"{zone}: {', '.join(sorted(names))}" for zone, names in sorted(by_zone.items())]


def work_list(
    rows: list[Any] | None = None,
    store: ProvenanceStore | None = None,
    context: int = CONTEXT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """``(cards, answer key, what was skipped)``.

    A card is one dismissed footnote, not one value: the same sentence over
    eleven zones is one decision and re-reading it eleven times would buy
    eleven copies of the same answer. What the zones do buy is the *scope*
    line, which is on the card, because a note can reach some of them and not
    others and that is a real answer.
    """
    rows = qualified() if rows is None else rows
    store = ProvenanceStore() if store is None else store

    reach: dict[tuple[str, int, str], list[tuple[str, str]]] = defaultdict(list)
    held: dict[tuple[str, int, str], Note] = {}
    layers_of: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    for row in rows:
        for note in row.governing:
            if note.state != "dismissed":
                continue
            ident = (note.doc, note.line, note.mark)
            reach[ident].append((row.zone, row.field))
            layers_of[ident].add(row.layer)
            held.setdefault(ident, note)

    cards: list[dict[str, Any]] = []
    key: list[dict[str, Any]] = []
    skipped = {"unresolved": 0, "no_text": 0}
    docs: dict[str, list[str]] = {}

    for ident in sorted(reach, key=lambda i: (i[0], i[1], i[2])):
        note = held[ident]
        text = " ".join(note.text.split())
        if not text:
            skipped["no_text"] += 1
            continue
        path = note.doc
        if path not in docs:
            try:
                docs[path] = store.load(path).text.splitlines()
            except (ProvenanceError, FileNotFoundError, OSError):
                docs[path] = []
        whole = docs[path]
        if not whole:
            skipped["unresolved"] += 1
            continue

        spans = [(note.line, note.line)]
        headings, caption_at = _above(whole, note.line)
        pairs = sorted(set(reach[ident]))
        item_id = f"{len(cards):05d}"
        cards.append(
            {
                "id": item_id,
                "jurisdictions": sorted(layers_of[ident]),
                "mark": note.mark,
                "note": text,
                "document": path,
                "cited_lines": f"L{note.line}",
                "headings": headings,
                "passage": _passage(whole, spans, context, caption_at),
                # What this note currently sits over. The reader is not being
                # asked to check these numbers -- that was the second reading.
                # It is here so "reaches some of them" is an answer they can
                # give precisely.
                "governs": _standards(pairs),
                "values_governed": len(pairs),
                # A narrowing already recorded against the note's own words.
                "recorded_zones": list(note.zones),
            }
        )
        key.append(
            {
                "id": item_id,
                "doc": path,
                "line": note.line,
                "mark": note.mark,
                "ruled_in": note.ruled_in,
                # The answer. Never on the card.
                "reason": " ".join(note.reason.split()),
                "zones": sorted({z for z, _ in pairs}),
                "fields": sorted({f for _, f in pairs}),
                "values_governed": len(pairs),
            }
        )
    return cards, key, skipped


# --- scoring ---------------------------------------------------------------


def score(key: list[dict], answers: dict[str, dict]) -> list[dict[str, Any]]:
    """Join the readings back to the register.

    ``verdict`` is about the dismissal, not about a number:

    ``agree``      the reader also says it does not reach us
    ``narrower``   the reader says it reaches only some of the zones it sits over
    ``disagree``   the reader says it reaches our building
    ``missing``    nobody answered this card
    """
    out: list[dict[str, Any]] = []
    for k in key:
        a = answers.get(k["id"]) or {}
        got = str(a.get("reaches") or "").strip()
        if not got:
            verdict = "missing"
        elif got == "not_ours":
            verdict = "agree"
        elif got == "some_zones":
            verdict = "narrower"
        else:
            verdict = "disagree"
        direction = str(a.get("direction") or "").strip()
        out.append(
            {
                **k,
                "verdict": verdict,
                "reaches": got,
                "direction": direction,
                "confidence": str(a.get("confidence") or ""),
                "reader_note": str(a.get("note") or "")[:400],
                "reader_zones": ",".join(a.get("zones") or []),
                # The one corner of the grid that can call a lot green wrongly.
                "alarming": verdict in {"disagree", "narrower"}
                and direction == "stricter",
            }
        )
    return out


def render(rows: list[dict[str, Any]]) -> str:
    from collections import Counter

    out = [
        f"cards={len(rows)} "
        + " ".join(f"{k}={v}" for k, v in sorted(Counter(r["verdict"] for r in rows).items()))
    ]
    out.append(
        "direction  "
        + " ".join(
            f"{k or '-'}={v}"
            for k, v in sorted(Counter(r["direction"] for r in rows).items())
        )
    )
    alarming = [r for r in rows if r["alarming"]]
    out.append("")
    out.append(f"WAVED AWAY BUT RESTRICTIVE: {len(alarming)}")
    for r in sorted(alarming, key=lambda r: -r["values_governed"]):
        out.append(
            f"  [{r['mark']}] {r['doc']}#L{r['line']}  "
            f"{r['values_governed']} values  {r['reaches']}"
        )
        out.append(f"      we said: {r['reason'][:150]}")
        out.append(f"      reader : {r['reader_note'][:150]}")
    return "\n".join(out)


def _write_work(out_dir: Path, batch: int, context: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cards, key, skipped = work_list(context=context)
    (out_dir / "answer_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    for n in range(0, len(cards), batch):
        chunk = cards[n : n + batch]
        (out_dir / f"batch_{n // batch:03d}.json").write_text(
            json.dumps(chunk, indent=1), encoding="utf-8"
        )
    print(
        f"cards={len(cards)} batches={(len(cards) + batch - 1) // batch} "
        f"values_behind={sum(k['values_governed'] for k in key)} skipped={skipped}"
    )
    return 0


def _score_dir(work: Path, csv_out: Path | None) -> int:
    import csv

    key = json.loads((work / "answer_key.json").read_text(encoding="utf-8"))
    answers: dict[str, dict] = {}
    for path in sorted(work.glob("answers_*.json")):
        try:
            for a in json.loads(path.read_text(encoding="utf-8")):
                answers[str(a.get("id"))] = a
        except json.JSONDecodeError as exc:
            print(f"BAD JSON {path.name}: {exc}")
    rows = score(key, answers)
    print(render(rows))
    if csv_out:
        with csv_out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("wrote", csv_out)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="write the work list here")
    ap.add_argument("--score", type=Path, help="score a finished work directory")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--context", type=int, default=CONTEXT)
    args = ap.parse_args(argv)
    if args.out:
        return _write_work(args.out, args.batch, args.context)
    if args.score:
        return _score_dir(args.score, args.csv)
    cards, _, skipped = work_list(context=args.context)
    print(f"dismissed footnotes over an encoded value: {len(cards)} skipped={skipped}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
