"""FINANCIAL_MODEL.md parser and validator.

Parses tagged metric headers from the math-doc source of truth and exposes
them to the investor export (for the Glossary sheet) and the bidirectional
validator tests (which prove the doc and the export agree on what metrics
exist).

Header convention::

    ## Metric Name [investor, app]

    **Definition.** Plain-English description.

    **Calculation.**
    ```
    metric = formula
    ```

    **Engine source.** ``module.function`` writes ``model.field``.

    **Notes / edge cases.** Anything else.

Only headers carrying bracketed audience tags are treated as metric headers.
Untagged ``##`` / ``###`` headers are structural/process sections and are
skipped by the parser; that is how engine-internals docs and process
walkthroughs (auto-sizing, fix-point iteration, refi math, etc.) coexist
with the investor-export glossary in a single file.

Valid audience tags: ``investor``, ``lender``, ``app``, ``internal``.

CLI usage::

    python -m app.exporters._doc_validator [path/to/FINANCIAL_MODEL.md]

Exits 0 on a clean parse, non-zero if any tagged header has malformed tags
or duplicate metric names.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

VALID_AUDIENCES: frozenset[str] = frozenset({"investor", "lender", "app", "internal"})

DOC_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "FINANCIAL_MODEL.md"
)

_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*\[([\w,\s]+)\]\s*$")
_PLAIN_HEADER_RE = re.compile(r"^#{2,3}\s+\S")


@dataclass(frozen=True)
class MetricEntry:
    """A single tagged metric parsed from the math doc."""

    name: str
    audiences: frozenset[str]
    body: str
    line: int  # 1-based line number of the header

    def has_audience(self, audience: str) -> bool:
        return audience in self.audiences


@dataclass
class ParseReport:
    """Result of parsing the math doc.

    ``metrics`` only contains entries with a recognised audience tag set.
    Malformed-tag headers and duplicates are reported separately so the
    validator test can surface a useful diff without losing the rest of
    the catalogue.
    """

    metrics: list[MetricEntry] = field(default_factory=list)
    malformed_tags: list[tuple[int, str, str]] = field(default_factory=list)
    duplicate_names: list[tuple[int, str]] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not (self.malformed_tags or self.duplicate_names)

    def names(self) -> set[str]:
        return {m.name for m in self.metrics}

    def for_audience(self, audience: str) -> list[MetricEntry]:
        return [m for m in self.metrics if m.has_audience(audience)]


def parse_doc(path: Path | None = None) -> ParseReport:
    """Parse the math doc and return a ParseReport.

    Tagged headers (``## Name [audience]``) become MetricEntry rows; the
    body is everything between the header and the next header of any
    kind. An untagged header closes the previous metric's body.
    """
    src = path or DOC_PATH
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines()
    report = ParseReport()
    seen: dict[str, int] = {}
    pending: tuple[str, frozenset[str], int] | None = None
    body_lines: list[str] = []

    def flush() -> None:
        nonlocal pending
        if pending is None:
            return
        name, audiences, line = pending
        report.metrics.append(
            MetricEntry(
                name=name,
                audiences=audiences,
                body="\n".join(body_lines).strip(),
                line=line,
            )
        )
        pending = None

    for idx, raw in enumerate(lines, start=1):
        m = _HEADER_RE.match(raw)
        if m is not None:
            flush()
            body_lines = []
            name = m.group(2).strip()
            tags = {t.strip().lower() for t in m.group(3).split(",") if t.strip()}
            invalid = tags - VALID_AUDIENCES
            if invalid:
                report.malformed_tags.append((idx, name, ", ".join(sorted(invalid))))
                continue
            if name in seen:
                report.duplicate_names.append((idx, name))
                continue
            seen[name] = idx
            pending = (name, frozenset(tags), idx)
        elif _PLAIN_HEADER_RE.match(raw):
            # Untagged structural header — close the previous metric body.
            flush()
            body_lines = []
        elif pending is not None:
            body_lines.append(raw)

    flush()
    return report


def metrics_for(audience: str, report: ParseReport | None = None) -> list[MetricEntry]:
    rpt = report if report is not None else parse_doc()
    return rpt.for_audience(audience)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DOC_PATH
    report = parse_doc(path)
    print(f"FINANCIAL_MODEL.md — parsed {len(report.metrics)} tagged metrics from {path}")
    by_audience: dict[str, list[str]] = {a: [] for a in VALID_AUDIENCES}
    for m in report.metrics:
        for a in m.audiences:
            by_audience.setdefault(a, []).append(m.name)
    for audience in sorted(VALID_AUDIENCES):
        names = sorted(by_audience.get(audience, []))
        print(f"  [{audience}] ({len(names)}):")
        for n in names:
            print(f"    - {n}")
    if report.malformed_tags:
        print("\nMalformed tags:")
        for line, name, bad in report.malformed_tags:
            print(f"  line {line}: '{name}' — invalid tag(s): {bad}")
    if report.duplicate_names:
        print("\nDuplicate metric names:")
        for line, name in report.duplicate_names:
            print(f"  line {line}: '{name}' already defined")
    return 0 if report.is_clean() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
