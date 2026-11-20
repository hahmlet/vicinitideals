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
| Statewide code interpretations | https://www.oregon.gov/bcd/codes-stand/Pages/code-interps.aspx | All 77 |
| Statewide alternate methods | https://www.oregon.gov/bcd/codes-stand/Pages/alternate-methods.aspx | All 19 |

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
- The NEC itself: held as `nec-2026/nfpa70-2026.pdf` (dropped in `docs/` 2026-11-19). Steph
  2026-11-19: obtained through a municipal library; internal use only. (The file arrived with
  the names of a book-sharing site in its file name; noted so the source can be re-checked if
  it ever matters.) NFPA also lets anyone read the NEC free on its own site.

- **Extraction test of the held NEC file, 2026-11-19: poor.** 1,004 pages, each a scanned picture
  with machine-read text behind it, in two columns. The text has reading errors ("BONDI.",
  "CIRC ITS") and no table comes out as a table. Usable for looking a section up by eye; not good
  enough to cut into clean section files. A chapter-by-chapter print from a site that serves real
  text (as for fire and plumbing) would be far better, if one carries the 2026 NEC.

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

Collected 2026-11-19 (scout). Held in `state-interps/`, `state-alternate-methods/`, `state-appeals/`,
`state-technical-bulletins/`, with `inventory.csv` and `inventory.md` beside them.

| Kind | Rows | PDFs held |
|---|---|---|
| Code interpretations | 77 | 77 |
| Alternate methods | 19 | 19 |
| Appeal decisions (third view of the same list) | 12 | 12 |
| Technical bulletins (in the list, on no public page) | 9 | 8 (one link is dead at the state) |

- Both public pages are views of one state list of 117 rows. The page fills in after it loads, so
  the rows were read from what the page's own script fetched in a browser.
- The list gives number, title, code program and PDF link. **It has no date, section or status.**
  Dates and sections in the inventory were pulled from the first pages of each PDF by pattern and
  are unreviewed: 44 from a labelled "Code reference" block, 39 from a scan of page one, 31 with
  none found, and 5 PDFs are scanned pictures with no text (99-01, 99-02, 00-03, alternate method
  09-01 twice).
- Numbers repeat across code programs (03-01, 08-01, 99-01...), so the PDF file name is the key.
- Five are rescinded per their own PDF or file name. Old numbers are not stale: the state re-issues
  each with a "Last updated" date of Oct. 1 (2023, 2025, 2026) and updated edition references.
- By book: residential 19; plumbing 10 citing the 2026 code; electrical items still cite the 2023
  edition; **no fire-code program in the list** (the fire code is the State Fire Marshal's, not this
  division's); about 15 of the 77 are elevator and boiler.
- The plumbing matrix names four against its sections (22-01 at 309.5, 22-04 at 408.6, 14-01 at
  501.1, 15-02 at 507.2).
- Re-check each quarter and once in early October (new rows appeared 2026-01-20, 08-28, 11-05).
- **Steph 2026-11-19:** an older ruling that cites the 2023 edition still stands as "at least a safe
  bet" where the code text it interprets is unchanged. So each note says which edition it was
  issued under and, where we hold both texts, whether the section's wording changed since.
- **Steph 2026-11-19: leave out elevator and boiler rulings.** They stay in the folder and the
  inventory but are not attached to any section.
- Plan: each becomes a short cited note on the section it concerns (number, date, link), with the
  PDF kept beside the book. The pattern-read sections need a reading pass before they are attached.

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

## Where Steph drops printed chapters

One PDF per chapter, same print settings as the samples, straight into the book's folder (not
`docs/`). File names as the site gives them; they are renamed on arrival.

| Book | Folder | Wanted first |
|---|---|---|
| Fire | `data/flats/books/building-codes/ofc-2025/` | Chapter 5 and Appendix D (also the picture test), then 1, 2, 3, 9, 10, 33, Appendices B and C; the rest later |
| Residential, 2023 edition | `data/flats/books/building-codes/orsc-2023/` | Chapters 3 and 4 only (foundations, stairs, guards), because the 2026 book replaces it |
| Residential, 2026 edition | `data/flats/books/building-codes/orsc-2026/` | Whole book when it is published |
| Plumbing | `data/flats/books/building-codes/opsc-2026/` | Chapter 6 or 7 first (the wide-table test), then all |
| Electrical | `data/flats/books/building-codes/nec-2026/`, `oesc-2026/` | The held NEC is a scan with reading errors; chapter prints with real text wanted if a site has the 2026 NEC. Lowest priority. |

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
question is not settled. Decided by Steph 2026-11-19: **internal agent reference only;
the full text is not posted publicly.** Oregon's own sheets (amendment tables, change summaries,
interpretations, alternate methods) are state documents and carry no such concern. This is not
legal advice.
