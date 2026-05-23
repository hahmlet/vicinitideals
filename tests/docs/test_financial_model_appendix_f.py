"""Static integrity tests for FINANCIAL_MODEL.md Appendix F (formula-
driven cells catalog). Catches mechanical drift in the 8-col data-point
table format:

  1. Every ``[text](#anchor)`` link in Appendix F resolves to a slugged
     data-point heading (``##### Name``) within the same file.
  2. Every named range (``s_*`` / ``r_*`` / ``p\\d+_*``) appearing in a
     row's "Excel Formula" field must also appear as a link in that
     row's "Refs" field.
  3. Two data-point headings cannot collapse to the same slug (collision
     test).

These checks are the load-bearing static gate for the auto-edit review
hook (Layer 2). If a future hook-driven edit breaks a link or drops a
ref, this test catches it at CI before push.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


DOC = Path(__file__).resolve().parents[2] / "docs" / "FINANCIAL_MODEL.md"

# Markdown link: [visible text](#anchor)
LINK_RE = re.compile(r"\[([^\]]+)\]\(#([a-z0-9][a-z0-9-]*)\)")

# Named-range tokens used in Excel formulas / hooks / etc.
#   s_foo_bar  /  r_uw_cf_levered  /  p1_noi  /  p12_levered
# Underscore-separated lowercase tokens.
NAMED_RANGE_RE = re.compile(r"\b(?:s_|r_|p\d+_)[a-z0-9_]+\b")


def _slug(heading: str) -> str:
    """Mirror GitHub-flavored markdown slug rules for ``##### Heading``:

      - lowercase
      - drop ``&`` and ``(`` / ``)`` / ``,`` / other punctuation
      - non-alphanumerics → ``-`` (collapsed)
      - strip leading/trailing ``-``
    """
    s = heading.lower()
    # Strip characters GitHub drops outright.
    s = re.sub(r"[&(),.—–'\"!?]", "", s)
    # Replace remaining non-alphanumerics with hyphen.
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _appendix_f_text(doc: Path) -> str:
    """Return only the Appendix F section (up to next ``## `` heading)."""
    text = doc.read_text(encoding="utf-8")
    start = text.find("## Appendix F:")
    assert start != -1, "Appendix F heading not found"
    rest = text[start:]
    # Find next top-level ``## `` heading (skipping the F: heading itself).
    nxt = rest.find("\n## ", 1)
    return rest if nxt == -1 else rest[:nxt]


def _data_point_blocks(appendix: str) -> dict[str, str]:
    """Slice Appendix F into per-data-point blocks keyed by heading slug.

    A data-point block starts at ``##### Heading`` and runs until the
    next ``##### `` heading or ``#### `` group heading.
    """
    blocks: dict[str, str] = {}
    # Split on the ``##### `` heading marker, keeping the heading text.
    matches = list(re.finditer(r"^##### (.+)$", appendix, re.MULTILINE))
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        slug = _slug(heading)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(appendix)
        blocks[slug] = appendix[start:end]
    return blocks


def _row_value(block: str, field: str) -> str:
    """Pull the Value cell for a given Field row inside a data-point block.
    Returns "" if the field isn't present (some rows omit Named Range etc.)
    """
    pat = re.compile(
        rf"^\|\s*\*\*{re.escape(field)}\*\*\s*\|\s*(.*?)\s*\|\s*$",
        re.MULTILINE,
    )
    m = pat.search(block)
    return m.group(1).strip() if m else ""


def test_appendix_f_headings_have_unique_slugs():
    """No two ``##### `` headings inside Appendix F may collapse to the
    same slug — otherwise links to one shadow the other silently."""
    appendix = _appendix_f_text(DOC)
    headings = re.findall(r"^##### (.+)$", appendix, re.MULTILINE)
    slugs: dict[str, list[str]] = {}
    for h in headings:
        slugs.setdefault(_slug(h.strip()), []).append(h.strip())
    collisions = {k: v for k, v in slugs.items() if len(v) > 1}
    assert not collisions, (
        f"slug collisions in Appendix F: {collisions}"
    )


def test_appendix_f_links_resolve():
    """Every ``[text](#anchor)`` link inside Appendix F must point at a
    slug that exists as a ``##### `` heading inside Appendix F."""
    appendix = _appendix_f_text(DOC)
    valid_slugs = {_slug(h.strip()) for h in re.findall(r"^##### (.+)$", appendix, re.MULTILINE)}
    broken: list[tuple[str, str]] = []
    for m in LINK_RE.finditer(appendix):
        text, anchor = m.group(1), m.group(2)
        if anchor not in valid_slugs:
            broken.append((text, anchor))
    assert not broken, (
        f"Appendix F links target missing anchors: {broken[:10]}"
        + (f" (+{len(broken) - 10} more)" if len(broken) > 10 else "")
    )


def test_excel_formula_named_ranges_appear_in_refs():
    """Every ``s_*`` / ``r_*`` / ``p<n>_*`` token in a row's Excel Formula
    cell must also appear as a link in that row's Refs cell — otherwise
    the row's navigation column lies about what it depends on, and an
    automated cross-reference review (Layer 2 hook) would silently miss
    rows that should be re-checked when the named range moves.
    """
    appendix = _appendix_f_text(DOC)
    blocks = _data_point_blocks(appendix)

    missing: list[tuple[str, str, set[str]]] = []
    for slug, block in blocks.items():
        formula = _row_value(block, "Excel Formula")
        refs = _row_value(block, "Refs")
        if not formula or formula.startswith("("):
            # No formula — skip (engine-only stubs, input cells, etc.)
            continue
        tokens = set(NAMED_RANGE_RE.findall(formula))
        if not tokens:
            continue
        # Strip cell-row template placeholders that look like named ranges
        # but aren't (e.g. ``perm_row``, ``cur_row``, ``end_period``).
        # Real named ranges always start with ``s_``, ``r_``, or ``p<digit>_``.
        # The regex already restricts to those prefixes, so all tokens
        # here are real named ranges.

        # Refs cell may use the token verbatim as the link text (e.g.
        # ``[s_combined_noi](#noi)``) OR the link text may be the human
        # name (``[NOI](#noi)``). For mechanical correctness we only
        # require the token itself appears somewhere in the Refs cell.
        #
        # Also accept per-loan-index templated forms: a Refs entry of
        # ``s_loan_n_annual_pi`` satisfies any concrete instance
        # (``s_loan_1_annual_pi``, ``s_loan_7_annual_pi``, ...) since
        # the workbook generates one cell per loan and the doc row
        # describes the pattern, not every concrete index.
        refs_lower = refs.lower()
        absent = set()
        for t in tokens:
            if t in refs_lower:
                continue
            # Build templated form: replace ``_1_`` / ``_2_`` ... with ``_n_``.
            templated = re.sub(r"_\d+_", "_n_", t)
            if templated != t and templated in refs_lower:
                continue
            absent.add(t)
        if absent:
            missing.append((slug, formula, absent))
    assert not missing, (
        "named ranges in Excel Formula but not listed in Refs:\n"
        + "\n".join(
            f"  [{slug}] missing {sorted(absent)} in Refs (formula: {formula})"
            for slug, formula, absent in missing
        )
    )
