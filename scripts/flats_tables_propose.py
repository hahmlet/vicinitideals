"""Propose the tables on a code book's pages, with the page evidence to check them.

FLATS does not read table structure itself (Steph 2026-10-24: tables are a
problem many people are solving; use their tool). Docling's TableFormer
proposes each table -- rows, columns, spanning cells, each cell's box -- and
takes every word from the PDF's own text layer, never from a picture, so it
cannot invent a word. It can still put a word in the wrong cell (Gresham
4.1415B lost a column and slid every number one over), so a proposal is
evidence, not an answer: ``flats.provenance.tables`` checks it against the
printed page before anything is shown as a table.

This runs OUTSIDE the app's environment -- Docling and pdfplumber are not
dependencies of the app -- in a separate venv, ideally on a GPU::

    <docling-venv>/Scripts/python.exe -I scripts/flats_tables_propose.py \\
        data/flats/books/422b8ce173ac29f5.pdf 94-593 \\
        -o flats/provenance/docs/or/clackamas/tualatin/tables.proposed.json

The output holds, per page with a table: Docling's cells, and the printed
evidence the check needs -- the words inside each table with their boxes, and
the printed vertical rules -- so the check runs anywhere, CI included, with no
model and no PDF.

Bake-off 2026-10-23 (FOLLOWUPS 115, 14 hard pages from 12 cities): Docling
13 of 14 right, 0 invented words; Marker and MinerU rewrote printed numbers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

#: Docling's TableFormer settings this file was made with -- stored with the
#: proposals, so a change of tool or setting is visible in the diff.
TOOL = "docling {version} TableFormer accurate, cell matching, no OCR"


def _pages(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def _evidence(plumber_page, box):
    """Printed words and vertical rules inside one table's box (PDF points, top-left origin)."""
    left, top, right, bottom = box
    words = [
        [w["text"], round(w["x0"], 2), round(w["top"], 2), round(w["x1"], 2), round(w["bottom"], 2)]
        for w in plumber_page.extract_words(x_tolerance=1.5, keep_blank_chars=False)
        if left - 2 <= (w["x0"] + w["x1"]) / 2 <= right + 2 and top - 2 <= (w["top"] + w["bottom"]) / 2 <= bottom + 2
    ]
    rules = [
        [round(e["x0"], 2), round(e["top"], 2), round(e["bottom"], 2)]
        for e in plumber_page.edges
        if e["orientation"] == "v"
        and e["bottom"] - e["top"] > 4
        and left - 2 <= e["x0"] <= right + 2
        and e["bottom"] > top
        and e["top"] < bottom
    ]
    return words, sorted(set(map(tuple, rules)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("book", type=Path)
    parser.add_argument("pages", help="PDF page numbers, 1-based: 94-593 or 300,302-305")
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args(argv)

    import docling
    import pdfplumber
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    try:
        from importlib.metadata import version

        tool = TOOL.format(version=version("docling"))
    except Exception:  # pragma: no cover - metadata missing
        tool = TOOL.format(version=getattr(docling, "__version__", "?"))

    opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    opts.table_structure_options.mode = TableFormerMode.ACCURATE
    opts.table_structure_options.do_cell_matching = True
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

    data = args.book.read_bytes()
    wanted = _pages(args.pages)
    out = {"book": hashlib.sha256(data).hexdigest(), "tool": tool, "pages": {}}
    started = time.time()
    with pdfplumber.open(args.book) as pdf:
        # Docling converts a range; ask for it in runs so a 500-page book is
        # not one long conversion that a single bad page can end.
        runs: list[tuple[int, int]] = []
        for n in wanted:
            if runs and runs[-1][1] == n - 1 and n - runs[-1][0] < 25:
                runs[-1] = (runs[-1][0], n)
            else:
                runs.append((n, n))
        for first, last in runs:
            doc = converter.convert(str(args.book), page_range=(first, last)).document
            for table in doc.tables:
                if not table.prov:
                    continue
                prov = table.prov[0]
                page_no = prov.page_no
                height = doc.pages[page_no].size.height
                tb = prov.bbox.to_top_left_origin(height)
                box = [round(tb.l, 2), round(tb.t, 2), round(tb.r, 2), round(tb.b, 2)]
                cells = []
                for cell in table.data.table_cells:
                    cb = cell.bbox.to_top_left_origin(height) if cell.bbox else None
                    cells.append(
                        {
                            "row": [cell.start_row_offset_idx, cell.end_row_offset_idx],
                            "col": [cell.start_col_offset_idx, cell.end_col_offset_idx],
                            "text": cell.text,
                            "header": bool(cell.column_header),
                            "box": [round(cb.l, 2), round(cb.t, 2), round(cb.r, 2), round(cb.b, 2)] if cb else None,
                        }
                    )
                words, rules = _evidence(pdf.pages[page_no - 1], box)
                out["pages"].setdefault(str(page_no), []).append(
                    {
                        "box": box,
                        "rows": table.data.num_rows,
                        "cols": table.data.num_cols,
                        "cells": cells,
                        "words": words,
                        "rules": [list(r) for r in rules],
                    }
                )
            print(f"pages {first}-{last}: {sum(len(out['pages'].get(str(p), [])) for p in range(first, last + 1))} tables", flush=True)
    out["seconds"] = round(time.time() - started)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{sum(len(v) for v in out['pages'].values())} tables on {len(out['pages'])} pages -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
