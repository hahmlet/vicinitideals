"""Write the citation a person read, with the one check a machine can still make.

``attach`` writes citations the readers agreed with, which is most of what can
be automated and about half of what is true. The rest of the corpus is held out
for reasons that are about the reader rather than the code: a cell reading
"15/04 feet", a row written for five housing types at once, a column headed
"R-5 – R-30", a grid published as HTML with every space stripped out of it. A
person settles those by looking at the page, and until now had nowhere to put
the answer.

This is that place. It takes the line somebody read and writes it onto the
value, after checking the one thing a machine still can: that the line actually
prints this number. That check is not a formality — the commonest way to
mis-cite a flattened table is to pick the row above the one you meant, and the
row above states a different number by definition.

What it deliberately does not check is *which column*. Position is exactly what
the reader could not resolve and the person could, and re-imposing it here would
refuse every citation this command exists to accept.

Run::

    python -m flats.encode.cite or/clackamas/happy-valley R40 setback_side_ft \\
        or/clackamas/happy-valley/16.22.residential.txt#L292 --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import yaml

from flats.encode.attach import Attachment, apply, insert_quotes
from flats.encode.find import _states, wording
from flats.encode.permit import layer_path
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules


def line_of(quote: str, store: ProvenanceStore) -> str:
    """The text a ``path#L12`` citation resolves to."""
    path, _, mark = quote.partition("#L")
    if not mark:
        raise ValueError(f"{quote}: not a line citation — expected path#L12")
    number = int(mark.split("-")[0].lstrip("L"))
    lines = store.load(path).text.splitlines()
    if not 1 <= number <= len(lines):
        raise ValueError(f"{quote}: the document has {len(lines)} lines")
    return lines[number - 1].strip()


def states(text: str, field: str, value: object) -> bool:
    """Whether the quoted line prints this value at all.

    Numbers by value rather than by spelling, so a line printing 7,500 evidences
    7500. Everything else — a permission, an enum — by the vocabulary that names
    it, because there is no number to compare and a citation that names neither
    the housing type nor the standard is pointing at the wrong line.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        pattern = wording(field, value)
        return bool(pattern and pattern.search(text))
    return _states(text, float(value))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-cite",
        description="Write a citation somebody read onto a held-out value.",
    )
    parser.add_argument("layer", help="layer id, e.g. or/clackamas/happy-valley")
    parser.add_argument("zone", help="zone code as the rule file writes it")
    parser.add_argument("field", help="field name")
    parser.add_argument("quote", help="path#L12 — the line that states it")
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--docs", type=Path, default=None, help="provenance store root")
    parser.add_argument(
        "--apply", action="store_true", help="write the file; without this it only reports"
    )
    args = parser.parse_args(argv)

    layers = load_rules(args.rules, strict=False)
    layer = layers.get(args.layer)
    if layer is None:
        print(f"no such layer: {args.layer}", file=sys.stderr)
        return 2

    held = layer.unread()
    value = held.get((args.zone, args.field))
    if value is None:
        # Either it is already quoted, or the zone and field name nothing. Both
        # are refusals: re-citing a value that carries a citation replaces
        # evidence somebody chose with evidence somebody typed.
        print(
            f"{args.zone} {args.field}: not held out in {args.layer} — "
            "nothing to cite, or it already carries a citation",
            file=sys.stderr,
        )
        return 2

    try:
        text = line_of(args.quote, ProvenanceStore(args.docs))
    except (ProvenanceError, OSError, ValueError) as exc:
        print(f"{args.quote}: {exc}", file=sys.stderr)
        return 2

    if not states(text, args.field, value.value):
        print(f"  ~ {args.zone} {args.field}: the line does not state {value.value!r}")
        print(f"    {text[:160]}")
        return 1

    print(f"  + {args.zone:8} {args.field:28} {value.value!s:>10}  {args.quote}")
    print(f"    {text[:160]}")
    if not args.apply:
        print("re-run with --apply to write")
        return 0

    path = layer_path(args.rules, args.layer)
    before = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(before) or {}
    one = Attachment(args.zone, args.field, value.value, args.quote)
    expected, refused = apply(raw, [one])
    for skip in refused:
        print(f"  ~ {skip}")
        return 1
    written, missed = insert_quotes(before, [one])
    for skip in missed:
        print(f"  ~ {skip}")
        return 1
    if yaml.safe_load(written) != expected:
        # The textual edit and the parsed transform disagree, which means the
        # edit landed somewhere unintended. A rule file is not worth guessing at.
        print(f"{path}: edit did not match the parsed result — nothing written", file=sys.stderr)
        return 1
    path.write_text(written, encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
