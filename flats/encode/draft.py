"""Writing what the document states, and the file does not carry, into the file.

Corroboration ends with a list of standards the code states and the rule file
ignores — Portland's 30 ft. height limit, its 18 ft. garage entrance setback.
Every one of those is a rule the screen currently does not apply, which makes
lots pass a test they were never given. This closes that loop by writing them
into the jurisdiction file as drafts.

Three refusals keep it safe to run:

*It never overwrites.* A field the file already carries is left exactly as it
is, whatever the document says. Disagreements are a reading question and belong
to :mod:`flats.encode.corroborate` and a person, not to a writer.

*It never guesses.* A standard the document states more than one way — two
numbers for one field in one zone — is skipped and reported. Picking one is the
failure this whole subsystem exists to prevent.

*It writes drafts.* Every value lands unsigned, with the quote it came from, so
the reviewer queue grows by exactly what was added. Writing a number is not
knowing it is right.

And it edits rather than re-serialises. Parsing a rule file and dumping the
result back would delete every ``#`` comment in it — the fetch quirks, the
"UNPORTED" notes, the reasons a standard was left out — which is most of what
the encoders wrote down about their own decisions. Every one of the eighteen
files carries some. So the new keys are spliced into the text of the zone block
they belong to and nothing else is touched.

Run::

    python -m flats.encode.draft or/multnomah/portland \\
        --doc or/multnomah/portland/33.110.txt --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import yaml

from flats.encode.corroborate import Verdict, check_layer
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import ZONE_META


@dataclass(frozen=True, slots=True)
class Addition:
    """One value about to be written, and where it was read."""

    zone: str
    field: str
    value: float | int
    quote: str

    def __str__(self) -> str:
        return f"{self.zone:6} {self.field:28} = {self.value:<10} [{self.quote}]"


@dataclass(frozen=True, slots=True)
class Skipped:
    """A gap this cannot close, and why nobody should close it mechanically."""

    zone: str
    field: str
    reason: str
    found: tuple[float | int, ...] = ()

    def __str__(self) -> str:
        found = ", ".join(str(v) for v in self.found)
        return f"{self.zone:6} {self.field:28} {self.reason}" + (f" ({found})" if found else "")


def layer_path(root: Path, layer_id: str) -> Path:
    """The file a layer id was loaded from."""
    parts = layer_id.split("/")
    direct = root.joinpath(*parts).with_suffix(".yaml")
    if direct.exists():
        return direct
    # A state or county names its directory rather than a file of its own.
    for stem in ("_state", "_county"):
        candidate = root.joinpath(*parts, f"{stem}.yaml")
        if candidate.exists():
            return candidate
    return direct


def plan(findings, existing: dict[str, set[str]]) -> tuple[list[Addition], list[Skipped]]:
    """Sort corroboration findings into what can be written and what cannot."""
    additions: list[Addition] = []
    skipped: list[Skipped] = []
    for finding in findings:
        if finding.verdict is not Verdict.unencoded:
            continue
        if finding.field in existing.get(finding.zone, set()):
            # Should not happen — unencoded means absent — but a writer that
            # trusts its input to be consistent is a writer that overwrites.
            skipped.append(Skipped(finding.zone, finding.field, "already encoded"))
            continue
        if len(finding.found) != 1:
            skipped.append(
                Skipped(finding.zone, finding.field, "states more than one value", finding.found)
            )
            continue
        if finding.conditional:
            # "30 ft. [3]" with "[3] Additional height may be allowed" is not a
            # 30 ft. ceiling. Writing it as one encodes a limit the code does
            # not impose, and a lot that fails it turns red on a rule that was
            # never absolute. Conditions need their own encoding, not a number.
            skipped.append(
                Skipped(
                    finding.zone,
                    finding.field,
                    f"conditional — {finding.notes[0][:60]}",
                    finding.found,
                )
            )
            continue
        additions.append(Addition(finding.zone, finding.field, finding.found[0], finding.quote))
    return additions, skipped


#: A mapping key and the indent it sits at, with any YAML quoting removed.
#: Zone codes are quoted in some files and bare in others — "R-2.5" has to be,
#: R5 does not — and a writer that matched only one form would silently skip
#: half the corpus.
_KEY = re.compile(r"^(?P<indent> *)(?P<quote>['\"]?)(?P<name>[^'\":#]+)(?P=quote):(?P<rest>.*)$")


def _zone_lines(lines: Sequence[str]) -> dict[str, tuple[int, int, int]]:
    """Each zone block in the file: ``code -> (key line, end line, indent)``.

    ``end`` is the line the block's last content sits on, so an insertion goes
    at ``end + 1`` and lands inside the block rather than ahead of the next
    zone's comment.
    """
    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == "zones:"), None)
    if start is None:
        return {}
    body = []
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped and not lines[i].startswith((" ", "\t")):
            break
        body.append(i)
    keys = [
        (i, m)
        for i in body
        if (m := _KEY.match(lines[i])) and not lines[i].lstrip().startswith("#")
    ]
    if not keys:
        return {}
    depth = min(len(m.group("indent")) for _, m in keys)
    tops = [(i, m) for i, m in keys if len(m.group("indent")) == depth]

    out: dict[str, tuple[int, int, int]] = {}
    for n, (i, m) in enumerate(tops):
        stop = tops[n + 1][0] if n + 1 < len(tops) else body[-1] + 1
        last = i
        for j in range(i + 1, stop):
            if lines[j].strip() and not lines[j].lstrip().startswith("#"):
                last = j
        out[m.group("name").strip()] = (i, last, depth)
    return out


def apply(text: str, additions: Sequence[Addition]) -> tuple[str, list[Skipped]]:
    """Splice each value into the file's text. Returns it and what it refused.

    Textual rather than a re-dump so the comments survive — see the module
    docstring. Everything the decision rests on still comes from the parsed
    document; only the writing is done on lines.
    """
    raw = yaml.safe_load(text) or {}
    zones = raw.get("zones") or {}
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    blocks = _zone_lines(lines)

    refused: list[Skipped] = []
    planned: dict[str, list[Addition]] = {}
    for add in additions:
        block = zones.get(add.zone)
        if block is None or add.zone not in blocks:
            # The zone resolves through a parent layer, or is written inline.
            # Either way this file has no block to add a line to, and creating
            # one would move where the standard lives.
            refused.append(Skipped(add.zone, add.field, "no zone block in this file"))
            continue
        if add.field in block:
            refused.append(Skipped(add.zone, add.field, "already in the file"))
            continue
        if not (block.get("cite_default") or raw.get("cite_default")):
            # Without an inherited citation the value would load as unsourced,
            # and an unsourced number is not a draft — it is a rumour.
            refused.append(Skipped(add.zone, add.field, "no cite_default to inherit"))
            continue
        planned.setdefault(add.zone, []).append(add)

    # Bottom-up so an insertion never moves a line another one was measured to.
    for zone in sorted(planned, key=lambda z: blocks[z][1], reverse=True):
        _key, end, depth = blocks[zone]
        pad = " " * (depth + 2)
        written: list[str] = []
        for add in planned[zone]:
            written += [
                f"{pad}{add.field}:",
                f"{pad}  value: {add.value}",
                f"{pad}  quote: {json.dumps(add.quote)}",
            ]
        lines[end + 1 : end + 1] = written

    return newline.join(lines) + newline, refused


def _existing(layer) -> dict[str, set[str]]:
    out = {code: set(zone.values) for code, zone in layer.zones.items()}
    for w in layer.wanted:
        out.setdefault(w.zone, set()).add(w.field)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-draft",
        description="Write standards the document states and the rule file lacks.",
    )
    parser.add_argument("layer", help="layer id, e.g. or/multnomah/portland")
    parser.add_argument("--doc", required=True, help="store path of the document to read")
    parser.add_argument("--zone", action="append", default=[], help="limit to these zones")
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--docs", type=Path, default=None, help="provenance store root")
    parser.add_argument(
        "--zoned-doc",
        action="store_true",
        help="the document covers exactly one zone, so its sentences count as evidence",
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the file; without this it only reports"
    )
    args = parser.parse_args(argv)

    layers = load_rules(args.rules, strict=False)
    layer = layers.get(args.layer)
    if layer is None:
        print(f"no such layer: {args.layer}", file=sys.stderr)
        return 2
    try:
        doc = ProvenanceStore(args.docs).load(args.doc)
    except (ProvenanceError, FileNotFoundError) as exc:
        print(f"{args.doc}: {exc}", file=sys.stderr)
        return 2

    findings = check_layer(
        doc.text, layer, path=args.doc, zones=args.zone, zoned=args.zoned_doc
    )
    additions, skipped = plan(findings, _existing(layer))

    for add in additions:
        print(f"  + {add}")
    for skip in skipped:
        print(f"  ~ {skip}")
    if not additions:
        print(f"{args.layer}: nothing to add from {args.doc}")
        return 0

    if not args.apply:
        print(f"{args.layer}: {len(additions)} value(s) to add — re-run with --apply to write")
        return 0

    path = layer_path(args.rules, args.layer)
    updated, refused = apply(path.read_text(encoding="utf-8"), additions)
    for skip in refused:
        print(f"  ~ {skip}")
    path.write_text(updated, encoding="utf-8")
    written = len(additions) - len(refused)
    print(f"{args.layer}: wrote {written} draft value(s) to {path}")
    print("  every one is unsigned — they are now review work, not encoded rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
