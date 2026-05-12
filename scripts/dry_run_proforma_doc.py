"""Dry-run the proforma parser against a non-xlsx document (PDF/DOCX/HTML/etc).

Uses MarkitDown to convert the file to markdown, then runs the same revenue
and OpEx prompts the production Celery task uses. No DB or Redis touched.

Usage:
    uv run python scripts/dry_run_proforma_doc.py <path>
"""
from __future__ import annotations

import json
import sys

# Re-use the production task's helpers (markdown conversion, LLM client,
# post-processing, schemas). Keeps drift between dry-run and prod minimal.
from app.tasks.proforma_parse import (
    ParsedExpenses,
    ParsedRevenue,
    _llm_client,
    _markitdown_to_text,
    _postprocess_expense_lines,
    build_opex_prompt,
    build_revenue_prompt,
)
from app.config import settings


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    print(f"\nFile: {path}\n")

    with open(path, "rb") as fh:
        content = fh.read()

    print("Converting via MarkitDown…")
    md = _markitdown_to_text(content, path)
    if not md:
        print("ERROR: MarkitDown produced no output.")
        sys.exit(2)

    print(f"Markdown length: {len(md):,} chars")
    print("=" * 60)
    print("FIRST 40 LINES OF MARKDOWN:")
    print("=" * 60)
    for line in md.splitlines()[:40]:
        print(line)
    print()

    client = _llm_client()

    print("=" * 60)
    print(f"PARSING REVENUE (model={settings.ollama_model})…")
    print("=" * 60)
    rev_prompt = build_revenue_prompt(md)
    try:
        parsed_rev: ParsedRevenue = client.chat.completions.create(
            model=settings.ollama_model,
            response_model=ParsedRevenue,
            messages=[{"role": "user", "content": rev_prompt}],
        )
        print(json.dumps([u.model_dump() for u in parsed_rev.unit_types], indent=2))
    except Exception as exc:
        print(f"Revenue parse ERROR: {exc}")

    print()
    print("=" * 60)
    print(f"PARSING OPEX (model={settings.ollama_model})…")
    print("=" * 60)
    opex_prompt = build_opex_prompt(md)
    try:
        parsed_exp: ParsedExpenses = client.chat.completions.create(
            model=settings.ollama_model,
            response_model=ParsedExpenses,
            messages=[{"role": "user", "content": opex_prompt}],
        )
        raw_lines = [e.model_dump() for e in parsed_exp.expense_lines]
        print("--- RAW LLM OUTPUT (before snap) ---")
        for r in raw_lines:
            print(f"    {r['original_label']!r:40s} raw_cat={r['mapped_category']!r}")
        print("--- AFTER _snap_category POST-PROCESSING ---")
        processed = _postprocess_expense_lines(raw_lines)
        for d in processed:
            flag = "" if d["is_operating_expense"] else "  [EXCLUDED]"
            conf = d["confidence"]
            conf_label = "HIGH" if conf >= 0.85 else ("MID" if conf >= 0.60 else "LOW")
            print(f"  [{conf_label:4s} {conf:.2f}]{flag}")
            print(f"    {d['original_label']!r:40s} -> {d['mapped_category']!r}")
            print(f"    Annual: ${d['annual_amount']:,.0f}")
    except Exception as exc:
        print(f"OpEx parse ERROR: {exc}")


if __name__ == "__main__":
    main()
