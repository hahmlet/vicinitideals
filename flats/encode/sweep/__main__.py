"""Sweep one jurisdiction, or all of them, and write the candidate holes.

    python -m flats.encode.sweep or/multnomah/portland
    python -m flats.encode.sweep --all --model qwen2.5:14b --size 60 --overlap 30

The knobs are the quality-for-time trade, exposed rather than chosen: smaller
chunks with heavier overlap read every line more times in more contexts, and a
bigger model reads each one better. Which of those is worth the wall-clock is
answered by the recall the run reports, not by an opinion held in advance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from flats.encode.sweep.ask import ENDPOINT, MODEL, Ollama
from flats.encode.sweep.audit import run, write
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules

#: Beside the gaps ledger, because it is the same kind of thing: a queue of work
#: a person has to do, written by a machine that cannot do it.
OUT = Path(__file__).resolve().parents[2] / "config" / "sweep"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-sweep",
        description="Read the code blind and report standards no field names.",
    )
    parser.add_argument("layer", nargs="?", help="layer id, e.g. or/multnomah/portland")
    parser.add_argument("--all", action="store_true", help="every layer that declares documents")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--size", type=int, default=120, help="chunk size in lines")
    parser.add_argument("--overlap", type=int, default=60, help="overlap in lines")
    parser.add_argument("--context", type=int, default=8192, help="model context window")
    parser.add_argument("--limit", type=int, default=0, help="chunks per document, 0 for all")
    parser.add_argument("--doc", default="", help="one document id, for benchmarking a change")
    parser.add_argument(
        "--tag",
        default="",
        help="suffix for the output file, so two configurations can be compared",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--docs", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.layer and not args.all:
        parser.error("name a layer, or pass --all")

    layers = load_rules(args.rules, strict=False)
    wanted = (
        [x for _, x in sorted(layers.items()) if x.code]
        if args.all
        else [layers[args.layer]]
        if args.layer in layers
        else []
    )
    if not wanted:
        print(f"no such layer: {args.layer}", file=sys.stderr)
        return 2

    ask = Ollama(endpoint=args.endpoint, model=args.model, context=args.context)
    trouble = ask.ready()
    if trouble:
        # Before any work. A sweep against a dead model does not fail, it
        # produces an empty hole list per document and a recall of zero, which
        # is indistinguishable from a model that read everything and found
        # nothing wrong.
        print(f"the model is not answering: {trouble}", file=sys.stderr)
        return 2
    store = ProvenanceStore(args.docs)
    print(f"{args.model} at {args.endpoint} — {len(wanted)} layer(s)")

    worst = 0.0
    for layer in wanted:
        print(f"{layer.layer} ...")
        try:
            report = run(
                layer,
                ask,
                store=store,
                size=args.size,
                overlap=args.overlap,
                limit=args.limit,
                only=args.doc,
                log=print,
            )
        except Exception as exc:  # noqa: BLE001 — one layer failing must not lose the rest
            print(f"  ! {layer.layer}: {exc}", file=sys.stderr)
            continue
        # Tagged, because an untagged second run overwrites the number the
        # first one was supposed to be compared against.
        stem = layer.layer.replace("/", "_") + (f".{args.tag}" if args.tag else "")
        path = write(report, args.out / f"{stem}.json")
        print(f"  {report.summary()} -> {path}")
        worst = max(worst, 1 - report.recall)

    if worst > 0.4:
        # Loud, because a hole list from a sweep that could not refind what we
        # already hold is a list of the easy holes, and reads like a complete one.
        print(
            "\nRecall is under 60% somewhere. The holes found are real candidates, "
            "but the absence of a hole is not evidence — re-run with smaller chunks, "
            "more overlap, or a larger model before treating any document as swept.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
