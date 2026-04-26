"""Soft validator for FINANCIAL_MODEL.md tagged metric headers.

Parses the math doc and reports any malformed audience tags or duplicate
metric names. This is a **soft gate** during the investor-export rollout —
drift produces an `xfail` (visible in CI output) rather than a red build.
Flip the `xfail` markers to plain assertions once the doc is fully tagged
and the bidirectional doc/export validator (commit 1+) is wired up.
"""
from __future__ import annotations

import pytest

from app.exporters._doc_validator import VALID_AUDIENCES, parse_doc


def test_doc_parses_at_all():
    """Hard requirement: the doc exists and the parser produces a non-empty
    catalogue. Anything less means commit 0 was reverted or the doc moved."""
    report = parse_doc()
    assert report.metrics, (
        "expected at least one tagged metric in FINANCIAL_MODEL.md — "
        "see _doc_validator.py for the header convention"
    )


def test_audience_set_is_stable():
    """Hard requirement: any tag in the doc must belong to the recognised
    vocabulary. The parser already filters unknown tags into
    ``malformed_tags``; this test asserts the surviving metric entries
    only carry valid audiences."""
    report = parse_doc()
    for metric in report.metrics:
        unknown = metric.audiences - VALID_AUDIENCES
        assert not unknown, (
            f"Metric {metric.name!r} (line {metric.line}) carries unrecognised "
            f"audience(s) {sorted(unknown)}. Valid: {sorted(VALID_AUDIENCES)}."
        )


@pytest.mark.xfail(strict=False, reason="soft gate — tighten once doc is fully tagged")
def test_no_malformed_audience_tags():
    """Soft gate: every tagged header parses cleanly into a known audience set.
    A failure here lists the offending headers so the doc author can fix them
    in one pass."""
    report = parse_doc()
    if report.malformed_tags:
        msg = "\n".join(
            f"  line {line}: {name!r} — invalid tag(s): {bad}"
            for line, name, bad in report.malformed_tags
        )
        pytest.fail(f"Malformed audience tags:\n{msg}")


@pytest.mark.xfail(strict=False, reason="soft gate — tighten once duplicates are resolved")
def test_no_duplicate_metric_names():
    """Soft gate: each metric name appears once. Duplicates would shadow each
    other in the export glossary and break the bidirectional validator."""
    report = parse_doc()
    if report.duplicate_names:
        msg = "\n".join(f"  line {line}: {name!r}" for line, name in report.duplicate_names)
        pytest.fail(f"Duplicate metric names:\n{msg}")


def test_investor_audience_has_coverage():
    """Sanity check: at least the major LP-facing metrics are tagged. Catches
    the case where a doc edit accidentally strips audience brackets."""
    report = parse_doc()
    investor_names = {m.name for m in report.for_audience("investor")}
    expected_minimum = {
        "Total Project Cost (TPC)",
        "NOI (Net Operating Income)",
        "DSCR (Debt Service Coverage Ratio)",
        "LTV (Loan-to-Value)",
        "LP IRR",
        "Equity Multiple (MOIC)",
    }
    missing = expected_minimum - investor_names
    assert not missing, (
        f"Expected investor-tagged metrics missing from FINANCIAL_MODEL.md: "
        f"{sorted(missing)}"
    )
