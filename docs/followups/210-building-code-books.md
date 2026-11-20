# 210 -- State building code books as an agent reference library (fire, residential, electrical, plumbing)

**Steph 2026-11-19:** "what I envision is the same kind of work we did with zoning code, cleaning it
up, inserting modifications made on separate sheets, and publishing as a referencable source of truth."
Then, same day: state interpretations and alternate methods "would also need to be incorporated,
with citations. WE DO NOT NEED TO ENCODE these texts. I don't want to do all the calculation
checking of footnotes etc. These would be for AI agent reference to encourage better decision making."

Status log and extraction test: [docs/flats/building_code_books.md](../flats/building_code_books.md).
Files: `data/flats/books/building-codes/` (gitignored).

## Where it stands

- Two UpCodes chapter prints tested 2026-11-19 (plumbing ch. 4, fire ch. 7): text, headings, tables
  and table notes all extract cleanly; Oregon amendments are already merged in (12 of 12 state-listed
  chapter 4 changes agree).
- Untested: figures, wide or multi-page tables.
- Electrical has no merged book: 2026 NEC + state table 1-E (held). NEC copy held (Steph: from a municipal
  library; internal use).
- 2026 residential code not yet published.
- Interpretations and alternate methods: COLLECTED 2026-11-19 -- 77 interpretations, 19 alternate
  methods, 12 appeals, 8 of 9 technical bulletins, with an inventory. Sections were pattern-read
  from the PDFs and need a reading pass; 5 PDFs are scanned pictures. No fire-code items in the list.

## Waiting on Steph

Steph is printing chapters (2026-11-19). Drop folders and the order wanted are in the status log
under "Where Steph drops printed chapters". First arrivals double as the two open tests: fire
ch. 5 + App. D (pictures) and plumbing ch. 6 or 7 (wide tables). Check each on arrival and tell
Steph at once if a chapter loses pictures or tables, before they print the rest.

Decided by Steph 2026-11-19: internal use only, not posted publicly. Older interpretations citing
the 2023 edition stand where the code text is unchanged. Elevator and boiler rulings left out.

## Then (Claude)

- Reading pass over the interpretation inventory: confirm the section, edition and date of each
  (flats-batch-reader), OCR the five scanned ones; elevator and boiler left out (Steph).
- Section cutter front end for UpCodes prints (reuse the code-library tools: tables, superscripts,
  notes). No encoding.
- Tag Oregon wording per section from the matrix and change summary; attach interpretations and
  alternate methods as cited notes; record print date and source per section; a searchable index.
- Where it lives: the tools are here, but the readers are mostly the Factory-Sim agents. Decide the
  home folder before the first full book (a shared folder both repos read is the likely answer).
