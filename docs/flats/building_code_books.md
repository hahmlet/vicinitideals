# State building code books -- access status

Status log, started 2026-11-19 from Steph's notes. One section per book: what is in force, where
the text can be read, what Oregon changes sit on separate sheets, and what we hold. Update the
"Held" lines whenever a file arrives or a link is re-checked.

**Purpose (Steph 2026-11-19): a reference library for AI agents, to support better decisions. It is
NOT encoded.** No rule files, no number-by-number checking of footnotes, no screen wiring. The work
is: clean readable text, Oregon's separate-sheet changes merged in, state interpretations and
alternate methods attached, every piece cited to its source.

Files we hold are private working copies in `data/flats/books/building-codes/` (gitignored, never
committed). These books are private publishers' model codes that Oregon adopted, so see
"Publishing" at the bottom before any of this text goes on a public page.

## Summary

| Book | Edition in force | Based on | One merged book exists? | Free to read | Held |
|---|---|---|---|---|---|
| Oregon Fire Code (OFC) | 2025 | 2024 International Fire Code | Yes (UpCodes) | Yes | Chapter 7 sample |
| Oregon Residential Specialty Code (ORSC) | 2026 being finalized | International Residential Code | Not yet for 2026 | 2026: not yet | Nothing |
| Oregon Electrical Specialty Code (OESC) | 2026 | 2026 NEC (NFPA 70) | **No**: NEC plus a state table | Table: yes | State table 1-E |
| Oregon Plumbing Specialty Code (OPSC) | 2026 | 2024 Uniform Plumbing Code | Yes (UpCodes) | Yes | Chapter 4 sample, state change summary, state matrix |

Across all books, the state also publishes:

| Thing | Where | Held |
|---|---|---|
| Statewide code interpretations | https://www.oregon.gov/bcd/codes-stand/Pages/code-interps.aspx | Nothing yet |
| Statewide alternate methods | https://www.oregon.gov/bcd/codes-stand/Pages/alternate-methods.aspx | Nothing yet |

## Oregon Fire Code (OFC) 2025

- No update known to be in progress or planned (Steph, 2026-11-19).
- Whole book free to read and print by chapter: https://up.codes/viewer/oregon/ifc-2024
- Held: `ofc-2025/ch07-upcodes-print.pdf` (Chapter 7, 5 pages, sample).
- Matters to the scan: Chapter 5 (fire access roads, the 150 ft hose rule) and Appendix D.

## Oregon Residential Specialty Code (ORSC) 2026

- Being finalized in its full adopted form. Will be sold as a PDF at shop.iccsafe.org; no date.
- Updates: https://www.oregon.gov/bcd/codes-stand/Pages/residential-structures.aspx
- Held: nothing. Until the 2026 book is out, the 2023 ORSC is the edition the foundation research
  cites (`../Factory-Sim/docs/research/FD1` section 10, `FD7` section 3).
- Matters most to FLATS: the foundation model (FOLLOWUPS 209) rests on it (footings, walls, fill,
  stairs, guards, handrails). Several of those rules are still "recalled", not re-read.

## Oregon Electrical Specialty Code (OESC) 2026

- 2026 update is in effect. **There is no merged book.** The rule is: read the 2026 NEC and apply
  the state's table of changes.
- State page: https://www.oregon.gov/bcd/codes-stand/Pages/electrical.aspx
- State table of changes: https://www.oregon.gov/bcd/codes-stand/Documents/26oesc-table1-E.pdf
  (held: `oesc-2026/26oesc-table1-E.pdf`, downloaded 2026-11-19).
- The NEC itself: a copy was dropped in `docs/` on 2026-11-19 and moved to
  `nec-2026/nfpa70-2026.pdf`. **Its file name shows it came from a book-piracy site. It is not used
  for anything and should be replaced or deleted** (Steph's call). NFPA lets anyone read the NEC
  free on its own site (read-only, free sign-up); a licensed PDF is sold by NFPA.

## Oregon Plumbing Specialty Code (OPSC) 2026

- Based on the 2024 Uniform Plumbing Code.
- State page: https://www.oregon.gov/bcd/codes-stand/Pages/plumbing.aspx
- State summary of amendments and substantive changes (95 pages, shows added and struck wording):
  https://www.oregon.gov/bcd/codes-stand/Documents/26opsc-change-summary.pdf (held)
- State adoption matrix (7 pages, every change and its outcome):
  https://www.oregon.gov/bcd/codes-stand/Documents/26opsc-matrix.pdf (held)
- Whole book free to read and print by chapter: https://up.codes/viewer/oregon/upc-2024
- Held: `opsc-2026/ch04-upcodes-print.pdf` (Chapter 4, 17 pages, sample).

## Statewide interpretations and alternate methods

- Both pages are views of one searchable state list (interpretations, alternate methods, appeals).
  The list is filled in by the browser after the page loads, so a plain download of the page comes
  back empty (checked 2026-11-19). Collecting the full list with each ruling's PDF is a scouting
  job, not yet done.
- They tie to code sections. The plumbing matrix already names four against its sections
  (Statewide Code Interpretation No. 22-01 at 309.5, 22-04 at 408.6, 14-01 at 501.1, 15-02 at 507.2).
- Plan: each one becomes a short cited note attached to the section it interprets, with its number,
  date and link, and the ruling's own PDF kept beside the book.

## Extraction test, 2026-11-19 (the two UpCodes chapter prints)

Verdict: **clean and easy -- easier than the zoning codes.**

| Thing | Result |
|---|---|
| Text | Real text, not a picture. Chapter 4: 42,181 characters, 141 numbered sections, all found in order. Chapter 7: 28 sections. |
| Headings | Bold, numbered, one per line. Cut into sections mechanically. |
| Tables | Both tables in Chapter 4 came out whole, cell by cell (they are drawn with ruled cells). |
| Table notes | Kept. The small raised note numbers flatten into the word beside them ("residential4"), but they are printed smaller, so they can be put back as proper superscripts. 32 found in Chapter 4. |
| Page breaks | A table's notes can fall on the next page. No running headers or footers to strip except one "Exported by" line at the end. |
| Defined terms | The fire code prints them in italics; recoverable. |
| Oregon amendments | **Already merged in.** Checked 12 of the state's listed Chapter 4 changes against the print: all 12 agree (the Oregon closet-flange wording, the 1.8 gpm shower limit, "wet rooms", urinals as floor drains, section 422.1 pointing to the Building Code, and so on). |

What the print does not carry:

1. **No mark of which words are Oregon's** and which are the model code's. The state's change
   summary supplies that for the significant changes and the matrix lists every change.
2. **No edition or date stamp** on the pages beyond the title line. We record the print date ourselves.
3. **Figures**: neither sample chapter has one, so untested. A picture would likely be dropped.
4. **Wide or multi-page tables**: untested. Chapter 4's are small.

Next test before printing a whole book: one hard chapter. For plumbing, Chapter 6 (water supply,
big sizing tables) or Chapter 7 (drainage tables); for fire, Chapter 5 and Appendix D (figures).

## How the work would go

Lighter than the zoning code library, because nothing is encoded.

1. Print each chapter to PDF, one file per chapter, same settings as the samples.
2. Cut into readable section files with tables, superscripts and notes kept.
3. Tag the Oregon wording from the state's matrix and change summary. For plumbing and fire this is
   a spot check, because the merge is already done. **For electrical it is real work**: the state
   table has to be applied to the NEC by us, since nobody publishes the merged book.
4. Attach interpretations and alternate methods to their sections as cited notes.
5. Every section carries: book, edition, source link, print date, and the state sheet any Oregon
   change came from. An index agents can search by section number or by words.

Not done, by design: no rule encoding, no footnote-by-footnote rulings, no calculations checked.
An agent that relies on a number still quotes the section and its source.

## Publishing

Different from zoning. A zoning code is written by the city. These books are written and sold by
private publishers (ICC, IAPMO, NFPA) and adopted by Oregon. Courts have mostly sided with posting
adopted law for free, and UpCodes does exactly that, but the publishers still sue over it and the
question is not settled. Position until Steph decides otherwise: **internal agent reference only;
the full text is not posted publicly.** Oregon's own sheets (amendment tables, change summaries,
interpretations, alternate methods) are state documents and carry no such concern. This is not
legal advice.
