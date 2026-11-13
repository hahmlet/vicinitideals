# 115. Tables, superscripts and footnotes in the readable text (readable/3), Tualatin pilot

[Claude] [Steph] GO 2026-10-24 ("Tables, superscript, and footnotes are essential"); BUILT + LIVE; Steph's table review waiting.

BUILT + LIVE (8bc86bdc tables, df9346d5 superscripts/footnotes, 6c599e3f + c190fcf5 held-table round): tables are an OVERLAY on the proved text (no recut, no citation moves). Docling (MIT, bake-off winner over Marker/MinerU/pdfplumber 2026-10-23) proposes structure (scripts/flats_tables_propose.py, separate venv); a second reader (--reader ruled, pdfplumber cut along printed rules) takes the ones Docling cannot; flats/provenance/tables.py checks every proposal against the page positionally (column rules, overlaps, every printed word in a cell) AND the proved lines. Tualatin: 115 drawn, 1 refused (p379, Chapter 55 CO/MR use table -- Chapter 55 is not in the store; CO/MR not encoded; run 85 checked: Tualatin CO 0 green). Superscripts/footnotes (scripts/flats_marks_propose.py -> flats/provenance/marks/<book sha>.json; flats/provenance/marks.py places a mark only where its printed context is unique on the page) 1,808 placed across 26 of 38 cached books; guard misread(): 0 of 201 citations sit on a digit with a raised mark run on. Spreadsheet round trip: scripts/flats_tables_sheet.py export / import --by <name> (changed cells = correction, Y/N = reviewed). A gate pass means 'no contradiction found', not 'right'.

STILL OPEN:
- STEPH: review workbook 'Tualatin tables - review.xlsx' (31 tables: the 12 second-reader tables + 19 random Docling ones) sent 2026-10-24, not yet imported (no tables.reviewed.json on main as of 11-13); the import gives the first real miss rate.
- (i) page-check cards for drawn tables (a sample of passes + every hold) to measure the miss rate properly.
- (ii) Docling proposals for the other cities at rollout (tables.proposed*.json exist for most); known failures: Gresham 4.1415B (rotated headers), rotated WashCo tables, unruled Oregon City / Troutdale / Wilsonville need the column-gap check. 73 left WashCo 12 and Beaverton 30 tables held.
- (iii) footnote -> which cells it governs.
- (iv) marks not placed (Gresham 4.0100 75/92, 4.0400 113/153) stay plain digits: list them for the reader.
- Encode Tualatin Chapter 55 CO/MR (needs the chapter in the store first).
