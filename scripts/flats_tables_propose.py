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

A second reader, ``--reader ruled``, proposes the tables on the pages named
from the printed rules alone: pdfplumber cuts the table along them, so none
of its cells can cross a rule. It is offered where Docling's proposal was
refused (``python -m flats.provenance.tables`` lists them), goes through the
same checks, and is written to ``tables.proposed.ruled.json``::

    <docling-venv>/Scripts/python.exe -I scripts/flats_tables_propose.py \\
        data/flats/books/422b8ce173ac29f5.pdf 303,316,352 --reader ruled \\
        -o flats/provenance/docs/or/clackamas/tualatin/tables.proposed.ruled.json

Some books print a column rule as a short horizontal stroke drawn thick
(Tualatin: 0.5 pt long, 13 pt thick = a 13 pt vertical bar); ``_strokes``
reads those as the rules they are. ``--evidence`` refreshes the words and
rules of an existing proposals file without running its reader again.
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


def _strokes(plumber_page) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Every printed rule on the page: vertical (x, top, bottom) and horizontal (y, left, right).

    A rule is a line, a rectangle's side, or a short stroke drawn thicker
    than it is long -- the stroke's thickness is then the rule's length,
    across the stroke.
    """
    vertical: list[tuple[float, float, float]] = []
    horizontal: list[tuple[float, float, float]] = []
    for line in plumber_page.lines:
        width = line.get("linewidth") or 0
        long_x, long_y = line["x1"] - line["x0"], line["bottom"] - line["top"]
        if long_y < 0.01 and long_x < 2 and width > 2:
            x = (line["x0"] + line["x1"]) / 2
            vertical.append((x, line["top"] - width / 2, line["top"] + width / 2))
        elif long_x < 0.01 and long_y < 2 and width > 2:
            y = (line["top"] + line["bottom"]) / 2
            horizontal.append((y, line["x0"] - width / 2, line["x0"] + width / 2))
        elif long_y < 0.01:
            horizontal.append((line["top"], line["x0"], line["x1"]))
        elif long_x < 0.01:
            vertical.append((line["x0"], line["top"], line["bottom"]))
    for rect in plumber_page.rects:
        horizontal += [(rect["top"], rect["x0"], rect["x1"]), (rect["bottom"], rect["x0"], rect["x1"])]
        vertical += [(rect["x0"], rect["top"], rect["bottom"]), (rect["x1"], rect["top"], rect["bottom"])]
    return vertical, horizontal


def _evidence(plumber_page, box):
    """Printed words and vertical rules inside one table's box (PDF points, top-left origin)."""
    left, top, right, bottom = box
    words = [
        [w["text"], round(w["x0"], 2), round(w["top"], 2), round(w["x1"], 2), round(w["bottom"], 2)]
        for w in plumber_page.extract_words(x_tolerance=1.5, keep_blank_chars=False)
        if left - 2 <= (w["x0"] + w["x1"]) / 2 <= right + 2 and top - 2 <= (w["top"] + w["bottom"]) / 2 <= bottom + 2
    ]
    vertical, _horizontal = _strokes(plumber_page)
    rules = [
        [round(x, 2), round(a, 2), round(b, 2)]
        for x, a, b in vertical
        if b - a > 4 and left - 2 <= x <= right + 2 and b > top and a < bottom
    ]
    return words, sorted(set(map(tuple, rules)))


def _ruled(plumber_page) -> list[dict]:
    """The tables pdfplumber cuts along the page's printed rules, as proposals."""
    vertical, horizontal = _strokes(plumber_page)
    if len(vertical) < 2 or len(horizontal) < 2:
        return []
    lines_v = [
        {"x0": x, "x1": x, "top": a, "bottom": b, "width": 0, "height": b - a, "orientation": "v", "object_type": "line"}
        for x, a, b in vertical
    ]
    lines_h = [
        {"x0": a, "x1": b, "top": y, "bottom": y, "width": b - a, "height": 0, "orientation": "h", "object_type": "line"}
        for y, a, b in horizontal
    ]
    settings = {
        "vertical_strategy": "explicit",
        "horizontal_strategy": "explicit",
        "explicit_vertical_lines": lines_v,
        "explicit_horizontal_lines": lines_h,
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "intersection_tolerance": 3,
    }
    out = []
    for table in plumber_page.find_tables(settings):
        if len(table.rows) < 2:
            continue
        xs = sorted({round(c[0], 1) for c in table.cells} | {round(c[2], 1) for c in table.cells})
        ys = sorted({round(c[1], 1) for c in table.cells} | {round(c[3], 1) for c in table.cells})
        box = [round(v, 2) for v in table.bbox]
        words, rules = _evidence(plumber_page, box)
        # A filled band (Tualatin's black title bar) can leave a cell inside
        # another; the outer one is the printed cell.
        boxes = [
            c
            for c in table.cells
            if not any(o != c and o[0] <= c[0] and o[1] <= c[1] and o[2] >= c[2] and o[3] >= c[3] for o in table.cells)
        ]
        cells = []
        for x0, top, x1, bottom in boxes:
            # The cell's text is the printed words inside it, in reading order;
            # a word the font gives no name ("\ufffd") is the dash it prints.
            inside = sorted(
                (w for w in words if x0 - 1 <= (w[1] + w[3]) / 2 <= x1 + 1 and top - 1 <= (w[2] + w[4]) / 2 <= bottom + 1),
                key=lambda w: (round(w[2]), w[1]),
            )
            text = " ".join("\u2014" if w[0] == "\ufffd" else w[0] for w in inside)
            # A header is printed bold, every letter of it.
            letters = [
                ch
                for ch in plumber_page.chars
                if not ch["text"].isspace()
                and x0 - 1 <= (ch["x0"] + ch["x1"]) / 2 <= x1 + 1
                and top - 1 <= (ch["top"] + ch["bottom"]) / 2 <= bottom + 1
            ]
            header = bool(letters) and all("bold" in str(ch.get("fontname", "")).lower() for ch in letters)
            cells.append(
                {
                    "row": [ys.index(round(top, 1)), ys.index(round(bottom, 1))],
                    "col": [xs.index(round(x0, 1)), xs.index(round(x1, 1))],
                    "text": text,
                    "header": header,
                    "box": [round(x0, 2), round(top, 2), round(x1, 2), round(bottom, 2)],
                }
            )
        out.append(
            {"box": box, "rows": len(ys) - 1, "cols": len(xs) - 1, "cells": cells, "words": words, "rules": [list(r) for r in rules]}
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("book", type=Path)
    parser.add_argument("pages", help="PDF page numbers, 1-based: 94-593 or 300,302-305")
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--reader", choices=("docling", "ruled"), default="docling")
    parser.add_argument("--evidence", action="store_true", help="refresh the words and rules in --out; read no table again")
    args = parser.parse_args(argv)

    import pdfplumber

    data = args.book.read_bytes()
    wanted = _pages(args.pages)
    if args.evidence:
        out = json.loads(args.out.read_text(encoding="utf-8"))
        if out["book"] != hashlib.sha256(data).hexdigest():
            parser.error(f"{args.out} was made from another book")
        with pdfplumber.open(args.book) as pdf:
            for key, found in out["pages"].items():
                for proposal in found:
                    proposal["words"], rules = _evidence(pdf.pages[int(key) - 1], proposal["box"])
                    proposal["rules"] = [list(r) for r in rules]
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"evidence refreshed: {sum(len(v) for v in out['pages'].values())} tables -> {args.out}")
        return 0
    if args.reader == "ruled":
        tool = f"pdfplumber {pdfplumber.__version__} cut along the printed rules"
        out = {"book": hashlib.sha256(data).hexdigest(), "tool": tool, "pages": {}}
        with pdfplumber.open(args.book) as pdf:
            for n in wanted:
                found = _ruled(pdf.pages[n - 1])
                if found:
                    out["pages"][str(n)] = found
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{sum(len(v) for v in out['pages'].values())} ruled tables on {len(out['pages'])} pages -> {args.out}")
        return 0

    import docling
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
