"""Find the characters a code book prints raised and small: footnote marks, ordinals.

A PDF's text layer gives a superscript as an ordinary character beside its
neighbour, so "1" with a raised "3" after it comes out as "13", and a reader of
the stored text cannot tell them apart. The book can: the raised character is
smaller and sits above the line. This records each one with the characters
printed either side of it, in the order the PDF stores them -- the order the
stored text was extracted in -- so ``flats.provenance.marks`` can find it in the
stored lines without the PDF.

Runs outside the app's environment (pdfplumber is not an app dependency)::

    <venv>/Scripts/python.exe -I scripts/flats_marks_propose.py data/flats/books/*.pdf \\
        -o flats/provenance/marks

One file per book, named by the book's SHA-256, the same hash its page maps
record. A book with no raised characters gets no file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

#: Smaller than the page's body text by this much, and raised above the
#: character before it by at least this many points.
SMALL = 0.85
RAISED = 1.2
#: Characters of context kept either side.
CONTEXT = 24


def _visible(chars):
    return [c for c in chars if c["text"].strip() and not c["text"].startswith("(cid")]


def scan(pdf) -> dict[str, list[dict]]:
    pages: dict[str, list[dict]] = {}
    for n, page in enumerate(pdf.pages, 1):
        chars = _visible(page.chars)
        if not chars:
            continue
        body = statistics.mode(round(c["size"], 1) for c in chars)
        found: list[dict] = []
        k = 0
        while k < len(chars):
            c = chars[k]
            prev = chars[k - 1] if k else None
            starts = (
                c["size"] < body * SMALL
                and prev is not None
                and prev["size"] >= body * 0.9
                and abs(prev["x1"] - c["x0"]) < 2.5
                and c["bottom"] < prev["bottom"] - RAISED
                and c["bottom"] > prev["top"]
            )
            if not starts:
                k += 1
                continue
            end = k + 1
            while (
                end < len(chars)
                and chars[end]["size"] < body * SMALL
                and abs(chars[end - 1]["x1"] - chars[end]["x0"]) < 1.5
                and abs(chars[end - 1]["bottom"] - chars[end]["bottom"]) < 0.6
            ):
                end += 1
            run = chars[k:end]
            found.append(
                {
                    "text": "".join(x["text"] for x in run),
                    "before": "".join(x["text"] for x in chars[max(0, k - CONTEXT) : k]),
                    "after": "".join(x["text"] for x in chars[end : end + CONTEXT]),
                    "box": [round(run[0]["x0"], 2), round(min(x["top"] for x in run), 2),
                            round(run[-1]["x1"], 2), round(max(x["bottom"] for x in run), 2)],
                }
            )
            k = end
        if found:
            pages[str(n)] = found
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("books", type=Path, nargs="+")
    parser.add_argument("-o", "--out", type=Path, required=True)
    args = parser.parse_args(argv)

    import pdfplumber

    args.out.mkdir(parents=True, exist_ok=True)
    for book in args.books:
        data = book.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        try:
            with pdfplumber.open(book) as pdf:
                pages = scan(pdf)
        except Exception as exc:  # noqa: BLE001 - one unreadable book must not stop the rest
            print(f"{book.name}: cannot read: {exc}", flush=True)
            continue
        target = args.out / f"{sha}.json"
        if not pages:
            target.unlink(missing_ok=True)
            print(f"{book.name}: none", flush=True)
            continue
        out = {"book": sha, "tool": f"pdfplumber {pdfplumber.__version__} size<{SMALL} raised>{RAISED}pt", "pages": pages}
        target.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"{book.name}: {sum(len(v) for v in pages.values())} marks on {len(pages)} pages", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
