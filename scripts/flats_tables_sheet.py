"""A table a person corrects in a spreadsheet, round-tripped into ``tables.corrected.json``.

Where every proposer's table is refused (``python -m flats.provenance.tables``
lists them), or a person says a drawn table is wrong, the table goes out as a
workbook -- one sheet per table, the table as we have it beside a picture of
the printed page -- and comes back as a correction (Steph 2026-10-24: "a sure
fire way to have a human define a table"). A person types each cell's words
as printed, merges the cells the page prints as one, and bolds the headers.

The same workbook is the review: each sheet asks "Right as drawn?" (Y or N,
and a note). A table left as it was and answered Y is recorded right, N
recorded wrong -- a table a person found wrong is not drawn, and the next
reader is tried -- in ``tables.reviewed.json``; the share found wrong is the
checks' miss rate. A table whose cells were changed is a correction, and
the table it replaces is recorded wrong.

What comes back is not trusted either: ``flats.provenance.tables`` holds a
correction to the same two checks as any proposal -- every printed word in
exactly one cell, no two columns or rows overlapping on the page, and the
cells read across exactly the proved lines -- and ``import`` prints the
verdict for each table at once, so a typo is caught while the sheet is open::

    python scripts/flats_tables_sheet.py export or/clackamas/tualatin --held -o tualatin_tables.xlsx
    python scripts/flats_tables_sheet.py export or/clackamas/tualatin --all -o tualatin_review.xlsx
    python scripts/flats_tables_sheet.py export or/clackamas/tualatin --page 352 -o p352.xlsx
    python scripts/flats_tables_sheet.py import tualatin_tables.xlsx --by "Steph"
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flats.provenance import tables as checked  # noqa: E402
from flats.provenance.books import CACHE  # noqa: E402
from flats.provenance.store import ProvenanceStore  # noqa: E402

#: The grid starts on this sheet row; the rows above say what to do.
FIRST_ROW = 4
META = "_tables"
HOW = (
    "Make this table match the printed page in the picture. Type each cell's words exactly as printed "
    "(line breaks do not matter). Merge the cells the page prints as one cell; make a header cell bold. "
    "Leave rows 1-2 and the picture alone."
)
ASK = "Right as drawn? Y or N, then a note if you like:"


def _book(sha: str) -> Path:
    for path in sorted(CACHE.glob("*.pdf")):
        if hashlib.sha256(path.read_bytes()).hexdigest() == sha:
            return path
    raise SystemExit(f"the book {sha[:12]} is not in {CACHE}; fetch it first")


def _sources(directory: Path) -> list[tuple[str, dict]]:
    out = []
    for name in (checked.CORRECTED, checked.PROPOSED, checked.RULED):
        path = directory / name
        if path.is_file():
            out.append((name, json.loads(path.read_text(encoding="utf-8"))))
    return out


def _wanted(city: str, held: bool, every: bool, pages: set[int]) -> list[tuple[int, list[float], str]]:
    """(page, box, reader) of each table to export: every one, the refused ones, or those on the pages named."""
    out = []
    for section, found in checked.tables(ProvenanceStore()).items():
        if section.startswith(city + "/"):
            out += [(t.page, list(t.box), t.tool) for t in found if t.box and (every or (held and not t.shown) or t.page in pages)]
    return sorted(out)


def export(city: str, held: bool, every: bool, pages: set[int], out: Path) -> int:
    import pypdfium2 as pdfium
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    store = ProvenanceStore()
    directory = store.root / city
    sources = _sources(directory)
    if not sources:
        raise SystemExit(f"no table proposals under {directory}")
    sha = sources[0][1]["book"]
    pdf = pdfium.PdfDocument(str(_book(sha)))
    book = Workbook()
    meta = book.active
    meta.title = META
    meta.append(["sheet", "city", "book", "page", "box", "from", "reader"])
    for page, box, reader in _wanted(city, held, every, pages):
        # The table as it stands now: the proposal the library draws (or, if
        # refused, the one whose refusal it shows).
        proposal, origin = None, ""
        for name, raw in sources:
            found = [
                p
                for p in raw["pages"].get(str(page), [])
                if p["box"] == box and str(p.get("tool") or raw.get("tool", "")) == reader
            ]
            if found:
                proposal, origin = found[0], name
                break
        if proposal is None:
            continue
        name = f"p{page}"
        while name in book.sheetnames:
            name += "+"
        sheet = book.create_sheet(name)
        meta.append([name, city, sha, page, json.dumps(proposal["box"]), origin, reader])
        sheet["A1"] = HOW
        sheet["A1"].font = Font(bold=True)
        sheet["A2"] = f"Page {page} of the book; the table as read by {reader}."
        sheet["A3"] = ASK
        sheet["A3"].font = Font(bold=True)
        for cell in checked._unique_cells(proposal["cells"]):
            r0, r1 = cell["row"]
            c0, c1 = cell["col"]
            target = sheet.cell(row=FIRST_ROW + r0, column=1 + c0, value=" ".join(str(cell["text"]).split()))
            target.alignment = Alignment(wrap_text=True, vertical="top")
            if cell.get("header"):
                target.font = Font(bold=True)
            if r1 - r0 > 1 or c1 - c0 > 1:
                sheet.merge_cells(start_row=FIRST_ROW + r0, start_column=1 + c0, end_row=FIRST_ROW + r1 - 1, end_column=c1)
        for c in range(1, int(proposal["cols"]) + 1):
            sheet.column_dimensions[get_column_letter(c)].width = 28
        # The printed table, cut from the page, to the right of the grid.
        left, top, right, bottom = proposal["box"]
        scale = 2
        image = pdf[page - 1].render(scale=scale).to_pil()
        crop = image.crop((max(0, (left - 8) * scale), max(0, (top - 8) * scale), (right + 8) * scale, (bottom + 8) * scale))
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
        buffer.seek(0)
        picture = Image(buffer)
        picture.anchor = f"{get_column_letter(int(proposal['cols']) + 2)}{FIRST_ROW}"
        sheet.add_image(picture)
    if len(book.sheetnames) == 1:
        raise SystemExit("no table matched")
    book.save(out)
    print(f"{len(book.sheetnames) - 1} table(s) -> {out}")
    return 0


def _grid(sheet) -> tuple[int, int, list[dict]]:
    """The sheet's table: one cell per filled cell or merged range, rows and columns from 0."""
    merged = {}
    for rng in sheet.merged_cells.ranges:
        if rng.min_row >= FIRST_ROW:
            merged[(rng.min_row, rng.min_col)] = (rng.max_row, rng.max_col)
    cells = []
    last_row = last_col = 0
    for row in sheet.iter_rows(min_row=FIRST_ROW):
        for cell in row:
            if cell.value is None or str(cell.value).strip() == "":
                continue
            end_row, end_col = merged.get((cell.row, cell.column), (cell.row, cell.column))
            last_row, last_col = max(last_row, end_row), max(last_col, end_col)
            cells.append(
                {
                    "row": [cell.row - FIRST_ROW, end_row - FIRST_ROW + 1],
                    "col": [cell.column - 1, end_col],
                    "text": " ".join(str(cell.value).split()),
                    "header": bool(cell.font and cell.font.bold),
                    "box": None,
                }
            )
    return last_row - FIRST_ROW + 1, last_col, cells


def _same(base: dict, cells: list[dict]) -> bool:
    """The sheet's cells are the table as exported: same spans, words and headers."""

    def key(cell: dict) -> tuple:
        return (tuple(cell["row"]), tuple(cell["col"]), " ".join(str(cell["text"]).split()), bool(cell.get("header")))

    exported = {key(c) for c in checked._unique_cells(base["cells"]) if str(c["text"]).strip()}
    return exported == {key(c) for c in cells}


def _review(directory: Path, entry: dict) -> None:
    path = directory / checked.REVIEWED
    raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"reviews": []}
    raw["reviews"].append(entry)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load(workbook: Path, by: str) -> int:
    from openpyxl import load_workbook

    book = load_workbook(workbook)
    if META not in book.sheetnames:
        raise SystemExit(f"{workbook} was not made by this script (no {META} sheet)")
    store = ProvenanceStore()
    today = dt.date.today().isoformat()
    stamp = f"by hand: {by} {today}, from a spreadsheet"
    counts = {"right": 0, "wrong": 0, "corrected": 0, "unanswered": 0}
    for name, city, sha, page, box, origin, reader in book[META].iter_rows(min_row=2, values_only=True):
        if name not in book.sheetnames:
            continue
        sheet = book[name]
        directory = store.root / str(city)
        source = json.loads((directory / str(origin)).read_text(encoding="utf-8"))
        box = json.loads(str(box))
        base = next(p for p in source["pages"][str(page)] if p["box"] == box)
        rows, cols, cells = _grid(sheet)
        answer = str(sheet["B3"].value or "").strip().upper()[:1]
        note = " ".join(str(sheet["C3"].value or "").split())
        verdict = {"page": int(page), "box": box, "tool": str(reader), "by": by, "date": today, "note": note}
        if _same(base, cells):
            if answer in ("Y", "N"):
                said = "right" if answer == "Y" else "wrong"
                _review(directory, {**verdict, "verdict": said})
                counts[said] += 1
                print(f"{name}: {said}")
            else:
                counts["unanswered"] += 1
            continue
        # Changed: a correction, and the table it replaces was wrong.
        _review(directory, {**verdict, "verdict": "wrong", "note": note or "corrected in a spreadsheet"})
        counts["corrected"] += 1
        path = directory / checked.CORRECTED
        corrected = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"book": sha, "tool": "by hand", "pages": {}}
        if corrected["book"] != sha:
            raise SystemExit(f"{path} is for another book")
        found = [p for p in corrected["pages"].get(str(page), []) if not checked._overlaps(p["box"], box)]
        found.append(
            {"box": base["box"], "rows": rows, "cols": cols, "cells": cells, "words": base["words"], "rules": base["rules"], "tool": stamp}
        )
        corrected["pages"][str(page)] = found
        path.write_text(json.dumps(corrected, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{name}: corrected, {rows} x {cols}, {len(cells)} cells -> {path}")
        # The correction's own verdict, whatever else is drawn there.
        parts = [p for p in store.parts().values() if p.layer == str(city) and any(n == page for n, _ in p.pages)]
        verdicts = [checked.check(found[-1], part, store.load(part.path).text.splitlines(), int(page), stamp) for part in parts]
        best = next((t for t in verdicts if t.shown), next((t for t in verdicts if t.first), verdicts[0] if verdicts else None))
        if best is None:
            print("  REFUSED: no section of this city holds that page")
        else:
            print(f"  {best.section}: " + ("SHOWN" if best.shown else "REFUSED: " + "; ".join(best.problems)))
    checked._tables.cache_clear()
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    out = sub.add_parser("export")
    out.add_argument("city", help="the city's folder under the store, e.g. or/clackamas/tualatin")
    out.add_argument("--held", action="store_true", help="every table the check refused")
    out.add_argument("--all", action="store_true", help="every table, drawn or refused (the review)")
    out.add_argument("--page", type=int, action="append", default=[], help="every table on this book page")
    out.add_argument("-o", "--out", type=Path, required=True)
    back = sub.add_parser("import")
    back.add_argument("workbook", type=Path)
    back.add_argument("--by", required=True, help="who reviewed or corrected it")
    args = parser.parse_args(argv)
    if args.command == "export":
        return export(args.city.strip("/"), args.held, args.all, set(args.page), args.out)
    return load(args.workbook, args.by)


if __name__ == "__main__":
    sys.exit(main())
