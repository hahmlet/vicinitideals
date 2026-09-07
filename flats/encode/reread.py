"""Read every number in the corpus a second time, without showing the reader
the first answer.

Encoding is one person reading one page and writing down one figure. Nothing
downstream can tell a careful reading from a careless one, and the corpus has
now twice been wrong in a way no ledger could see: a figure taken from the
right page and the wrong row (Oregon City's garage door width, standing in for
a garage setback in five zones) and a figure taken from the wrong half of a
banded standard (Portland's outdoor area, the over-20,000 sq ft band applied to
every lot). Both survived because everything after encoding trusts the number.

So: read it again, and take the answer away first.

``work_list`` turns each cited value into a card carrying the passage of code,
the zone, the name of the standard and the condition being encoded -- and NOT
the figure. The answer key goes to a separate file. A reader given the card
states what the page says; ``score`` joins the two afterwards. A reader who
cannot see the answer cannot drift toward it, which is the whole design, and it
is why the two halves are built here rather than in one pass.

Run 2026-09-07 over 1,902 citations: 1,845 scored, 1,845 agreed, and the six
disagreements it did surface were all the same shape -- an exception held as
though it were the rule. Three more were the *reader* being wrong, every one of
them because the card could not reach the column headings of a wide table.
That is what ``CONTEXT`` and ``HEADER_LINES`` are for.

Usage:
    uv run python -m flats.encode.reread --out <dir> [--batch 40] [--context 20]
    uv run python -m flats.encode.reread --score <dir> [--csv out.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from flats.encode.readiness import _quoted_parts
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.loader import Layer, load_rules

#: Lines either side of a citation the card carries. Six was the first run's
#: value and it was too few: Gresham's Table 4.0131 prints eleven column
#: headings one per line, so a citation into its body could not see which
#: column it was in and three readings came back "I cannot tell". The reader
#: was right to say so. Twenty reaches that header; ``HEADER_LINES`` covers
#: the tables it does not.
CONTEXT = 20

#: How far above a citation to look for the table caption and section heading
#: that say what the reader is looking at.
LOOK_BACK = 400

#: How far above a citation a table caption may be and still pull its header
#: block into the card. Beyond this the caption is reported in ``headings``
#: alone -- a hundred lines of table between the caption and the cited row is
#: a card nobody reads.
CAPTION_REACH = 120

#: How much of a table to carry down from its caption. Gresham's Table 4.0131
#: prints eleven column headings one per line before its first row, so the
#: block that says which column is which is about that tall. Everything
#: between the header block and the cited row is elided, visibly.
HEADER_LINES = 22

_CAPTION = re.compile(r"^\s*Table\s+[0-9A-Z]", re.I)
_HEADING = re.compile(
    r"^\s*(?:§\s*)?(?:Sec(?:tion|\.)?\s+)?(?P<sec>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)"
    r"(?P<rest>[ .—-]+\S.*)?$"
)
_TITLED = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_NUM = re.compile(r"(?<![\d.,])(?:\d[\d,]*(?:\.\d+)?|\.\d+)")


# --- the work list ---------------------------------------------------------


def _ranges(ref: str) -> list[tuple[int, int]]:
    """The line spans a citation names, as ``(first, last)`` pairs.

    Citations carry more than one shape -- ``#L12``, ``#L12-L18``,
    ``#L12,L18-L20`` -- and a span that cannot be parsed is dropped rather
    than guessed at, because a card pointed at the wrong lines is worse than
    no card.
    """
    _, _, fragment = ref.partition("#L")
    out: list[tuple[int, int]] = []
    for part in fragment.replace("L", "").split(","):
        edges: list[int] = []
        for edge in part.split("-"):
            edge = edge.strip()
            if not edge:
                continue
            try:
                edges.append(int(edge))
            except ValueError:
                continue
        if edges:
            out.append((edges[0], edges[-1]))
    return out


def _titled(line: str) -> bool:
    found = _HEADING.match(line)
    rest = found.group("rest") if found else None
    return bool(rest) and len(line) <= 120 and bool(_TITLED.search(rest))


def _above(whole: list[str], first: int) -> tuple[dict[str, str], int | None]:
    """The nearest table caption and section heading above a line.

    Returns the pair and, separately, the caption's own line number, because
    the caption is where a table's header block starts and the header block is
    what decides which column a figure sits in.
    """
    out: dict[str, str] = {}
    caption_at: int | None = None
    for n in range(min(first, len(whole)) - 1, max(first - LOOK_BACK, 0) - 1, -1):
        line = whole[n].strip()
        if not line:
            continue
        if "caption" not in out and _CAPTION.match(line):
            out["caption"] = line[:160]
            caption_at = n + 1
        if "section" not in out and _titled(line):
            out["section"] = line[:160]
        if len(out) == 2:
            break
    return out, caption_at


def _passage(
    whole: list[str],
    spans: list[tuple[int, int]],
    context: int = CONTEXT,
    caption_at: int | None = None,
) -> list[str]:
    """The lines a reader is shown, cited ones marked ``>>``.

    Elisions print as ``...`` so a reader can see that lines were dropped
    rather than assuming the passage runs continuously.
    """
    wanted: set[int] = set()
    for a, b in spans:
        wanted.update(range(max(a - context, 1), min(b + context, len(whole)) + 1))
    first = min(a for a, _ in spans)
    if caption_at is not None and 0 < first - caption_at <= CAPTION_REACH:
        wanted.update(range(caption_at, min(caption_at + HEADER_LINES, first)))
    out: list[str] = []
    prev = None
    for n in sorted(wanted):
        if prev is not None and n != prev + 1:
            out.append("      ...")
        mark = ">>" if any(a <= n <= b for a, b in spans) else "  "
        out.append(f"{mark} L{n:<6d}{whole[n - 1]}")
        prev = n
    return out


def _label(name: str) -> tuple[str, str, str]:
    """``(field key, human label, definition)`` for a row name such as
    ``setback_front_ft [corner]`` or ``max_height_ft [step-back]``.

    The sense -- ceiling or floor -- is spelled out because a reader who has
    it backwards reports the wrong number from the right sentence, and that is
    a mistake the score cannot distinguish from a misreading.
    """
    key = name.split(" ")[0].split("[")[0]
    fdef = FIELDS.get(key)
    if fdef is None:
        return key, key, ""
    sense = ""
    if fdef.is_maximum is True:
        sense = " This standard is a MAXIMUM (a ceiling)."
    elif fdef.is_maximum is False:
        sense = " This standard is a MINIMUM (a floor)."
    return key, fdef.shown, f"{fdef.describe}{sense} Kind: {fdef.kind}."


def work_list(
    layers: dict[str, Layer],
    store: ProvenanceStore,
    context: int = CONTEXT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """``(cards, answer key, what was skipped)``.

    The two lists share an ``id`` and nothing else. Nothing in a card carries
    the encoded figure -- ``test_reread`` asserts it, because the single way
    this whole exercise can be worthless is a number leaking into the side the
    reader sees.
    """
    cards: list[dict[str, Any]] = []
    key: list[dict[str, Any]] = []
    skipped = {"no_quote": 0, "no_number": 0, "drawn": 0, "unresolved": 0, "no_lines": 0}
    docs: dict[str, list[str]] = {}

    for lid, layer in sorted(layers.items()):
        for zone, name, quote, number, drawn in _quoted_parts(layer):
            if not quote:
                skipped["no_quote"] += 1
                continue
            if number is None or isinstance(number, bool):
                # An exemption, a same_as, a measured-on definition: nothing on
                # the page for a reader to find a figure in.
                skipped["no_number"] += 1
                continue
            if drawn:
                # A dimension that exists only as CAD geometry. There is no
                # sentence to re-read.
                skipped["drawn"] += 1
                continue
            path = quote.partition("#L")[0]
            if path not in docs:
                try:
                    docs[path] = store.load(path).text.splitlines()
                except (ProvenanceError, FileNotFoundError, OSError):
                    docs[path] = []
            whole = docs[path]
            if not whole:
                skipped["unresolved"] += 1
                continue
            spans = _ranges(quote)
            if not spans:
                skipped["no_lines"] += 1
                continue
            fkey, shown, describe = _label(name)
            when = ""
            if "[" in name and "]" in name:
                when = name[name.index("[") + 1 : name.index("]")]
            item_id = f"{len(cards):05d}"
            headings, caption_at = _above(whole, spans[0][0])
            cards.append(
                {
                    "id": item_id,
                    "layer": lid,
                    "zone": zone,
                    "zone_notes": (
                        (layer.zones[zone].notes or "")[:300]
                        if zone != "defaults" and zone in layer.zones
                        else ""
                    ),
                    "field": fkey,
                    "standard": shown,
                    "definition": describe,
                    "condition": when if when != "step-back" else "",
                    "step_back": when == "step-back",
                    "document": path,
                    "cited_lines": ",".join(f"L{a}-L{b}" for a, b in spans),
                    "headings": headings,
                    "passage": _passage(whole, spans, context, caption_at),
                }
            )
            key.append(
                {
                    "id": item_id,
                    "layer": lid,
                    "zone": zone,
                    "row": name,
                    "field": fkey,
                    "quote": quote,
                    "encoded": (
                        number if isinstance(number, (int, float, str)) else str(number)
                    ),
                }
            )
    return cards, key, skipped


# --- scoring ---------------------------------------------------------------

#: The verdicts, and each one means something different about what to do next.
VERDICTS = (
    "agree",  # the reader's figure is the one we hold
    "agree_alt",  # we hold one of the figures the reader listed as possible
    "disagree",  # the reader read a different number: open the page
    "unread",  # the reader found no figure for this standard on these lines
    "unscored",  # what we hold is not a number (a curve, an enum)
    "missing",  # nobody has answered this card yet
)


def _num(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def _numbers_in(texts: Any) -> list[float]:
    out: list[float] = []
    for t in texts or []:
        for m in _NUM.finditer(str(t)):
            try:
                out.append(float(m.group(0).replace(",", "")))
            except ValueError:
                pass
    return out


def score(key: list[dict], answers: dict[str, dict]) -> list[dict[str, Any]]:
    """One row per answer-key entry, with a verdict and the reader's doubts.

    The flags are deliberately independent of the verdict. A reader can hand
    back the right number and still say the passage never names this zone --
    which is what caught Gresham's four downtown districts claiming a
    townhouse-only cell -- so ``wrong_zone`` has to survive an ``agree``.
    """
    rows: list[dict[str, Any]] = []
    for k in key:
        a = answers.get(k["id"])
        enc = _num(k["encoded"])
        verdict = "missing"
        if a is not None:
            fig = _num(a.get("figure"))
            if enc is None:
                verdict = "unscored"
            elif fig is None:
                verdict = "unread"
            elif math.isclose(fig, enc, rel_tol=1e-6, abs_tol=1e-9):
                verdict = "agree"
            elif any(
                math.isclose(x, enc, rel_tol=1e-6, abs_tol=1e-9)
                for x in _numbers_in(a.get("alternatives"))
            ):
                verdict = "agree_alt"
            else:
                verdict = "disagree"
        flags = []
        if a is not None:
            if a.get("for_this_zone") is False:
                flags.append("wrong_zone")
            if a.get("confidence") == "unclear":
                flags.append("unclear")
            if (a.get("note") or "").strip():
                flags.append("noted")
        rows.append(
            {
                "id": k["id"],
                "verdict": verdict,
                "flags": "+".join(flags),
                "layer": k["layer"],
                "zone": k["zone"],
                "row": k["row"],
                "encoded": k["encoded"],
                "read": (a or {}).get("figure", ""),
                "form": (a or {}).get("form", ""),
                "confidence": (a or {}).get("confidence", ""),
                "for_this_zone": (a or {}).get("for_this_zone", ""),
                "alternatives": " | ".join(map(str, (a or {}).get("alternatives") or [])),
                "fragment": ((a or {}).get("fragment") or ""),
                "note": ((a or {}).get("note") or ""),
                "quote": k["quote"],
            }
        )
    return rows


# --- CLI -------------------------------------------------------------------


def _write_work(out_dir: Path, batch: int, context: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cards, key, skipped = work_list(load_rules(), ProvenanceStore(), context)
    (out_dir / "answer_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    n = 0
    for i in range(0, len(cards), batch):
        (out_dir / f"batch_{n:03d}.json").write_text(
            json.dumps(cards[i : i + batch], indent=1), encoding="utf-8"
        )
        n += 1
    print(f"cards={len(cards)} batches={n} skipped={skipped}")
    return 0


def _score_dir(work: Path, csv_out: Path | None, show: set[str]) -> int:
    key = json.loads((work / "answer_key.json").read_text(encoding="utf-8"))
    answers: dict[str, dict] = {}
    for a in sorted(work.glob("answers_*.json")):
        try:
            for ans in json.loads(a.read_text(encoding="utf-8")):
                answers[str(ans.get("id"))] = ans
        except json.JSONDecodeError as exc:
            print(f"BAD JSON {a.name}: {exc}", file=sys.stderr)
    rows = score(key, answers)
    print("VERDICTS", dict(Counter(r["verdict"] for r in rows)))
    print("FLAGS   ", dict(Counter(f for r in rows for f in r["flags"].split("+") if f)))
    if csv_out:
        with csv_out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {csv_out}")
    for r in rows:
        if show and (r["verdict"] in show or any(f in show for f in r["flags"].split("+"))):
            print(
                f"\n[{r['verdict']}{' ' + r['flags'] if r['flags'] else ''}] "
                f"{r['layer']} {r['zone']} {r['row']}  "
                f"encoded={r['encoded']} read={r['read']}"
            )
            print(f"    {r['quote']}")
            for label in ("fragment", "alternatives", "note"):
                if r[label]:
                    print(f"    {label}: {r[label][:220]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, help="write the work list to this directory")
    ap.add_argument("--score", type=Path, help="score the answers in this directory")
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--context", type=int, default=CONTEXT)
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--show", default="", help="verdicts or flags to print, comma separated")
    args = ap.parse_args(argv)
    if args.out:
        return _write_work(args.out, args.batch, args.context)
    if args.score:
        return _score_dir(args.score, args.csv, {s for s in args.show.split(",") if s})
    ap.error("one of --out or --score is required")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
