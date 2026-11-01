# 73. The code library as a public, structured repository

73. [Claude] [Steph] **STRUCTURING ROLLOUT DONE 2026-10-31** (Steph: "finish one of the
projects"; "Yes" to closing it after the Washington County tables). Batches 1-8 cut every
encoded jurisdiction's stored code into readable section files with citations carried
(batch 8 = Washington County: 32 of 46 documents, 297 sections, 268 citations moved, merge
07fa1e17; tables 67b9aaa4 -- 18 drawn, 12 held, 11 of them the rotated 375-10 use table).
Steph 2026-10-10: the library goes PUBLIC (CC0 on the code text, unofficial-copy notice).

KNOWN GAPS, left on purpose (fix one only when it causes a real problem):
- Whole, no page map or no section numbers: WashCo cdc.106 definitions, 430-84 middle
  housing, 431 transit design, all 11 community plans; Clackamas ZDO 202 + roadway sheets;
  Multnomah 39.2000; Portland 33.150 (cutting drops the Sylvania note) + 9 unmapped chapters;
  Oregon City Title 17; Beaverton definitions + UPAA; Cornelius 4 chapters; Gladstone
  17.21/17.27; Gresham pws; King City 16.24; Sandy 17.64; Sherwood 5 documents; Tigard TSP;
  Tualatin app. B; Wilsonville 2.
- Not cut: Lake Oswego (switched off), Johnson City, Wood Village, Canby.
- Tables held or not proposed: WashCo 12 held; Beaverton 30 held; the other cities' tables
  beyond Tualatin and WashCo were not proposed (scripts/flats_tables_propose.py, Docling venv
  %TEMP%\bx\envs\docling, books in data/flats/books by URL hash).
- gaps.json reads "302-2.14" as "2.14" on 28 WashCo labels (cosmetic).

PARKED -- Steph 2026-11-01: "Not ready to publicize". Do not re-offer until Steph raises it.
HOSTING, when Steph is ready -- its own GitHub repo our apps read as a dependency,
CC0 on the text, Steph to pick the tooling licence; keep rulings/encoding private.
