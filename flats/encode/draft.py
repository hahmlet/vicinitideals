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

Run::

    python -m flats.encode.draft or/multnomah/portland \\
        --doc or/multnomah/portland/33.110.txt --apply
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

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


def apply(raw: dict[str, Any], additions: Sequence[Addition]) -> tuple[dict[str, Any], list[Skipped]]:
    """Add each value to the parsed YAML. Returns the document and what it refused."""
    out = dict(raw)
    zones = dict(out.get("zones") or {})
    refused: list[Skipped] = []
    for add in additions:
        zone = dict(zones.get(add.zone) or {})
        if add.field in zone:
            refused.append(Skipped(add.zone, add.field, "already in the file"))
            continue
        if not (zone.get("cite_default") or out.get("cite_default")):
            # Without an inherited citation the value would load as unsourced,
            # and an unsourced number is not a draft — it is a rumour.
            refused.append(Skipped(add.zone, add.field, "no cite_default to inherit"))
            continue
        zone[add.field] = {"value": add.value, "quote": add.quote}
        zones[add.zone] = zone
    out["zones"] = zones
    return out, refused


def _existing(layer) -> dict[str, set[str]]:
    return {code: set(zone.values) for code, zone in layer.zones.items()}


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
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    updated, refused = apply(raw, additions)
    for skip in refused:
        print(f"  ~ {skip}")
    path.write_text(
        yaml.safe_dump(updated, sort_keys=False, allow_unicode=True, width=110),
        encoding="utf-8",
    )
    written = len(additions) - len(refused)
    print(f"{args.layer}: wrote {written} draft value(s) to {path}")
    print("  every one is unsigned — they are now review work, not encoded rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
