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
- Interpretations and alternate methods: one state list behind both pages, loaded by the browser;
  not yet collected.

## Waiting on Steph

1. A second, harder sample before printing a whole book (plumbing ch. 6 or 7; fire ch. 5 + App. D).
2. Which books first. Coordinator's suggestion: fire ch. 5 + App. D and the residential code, since
   the scan and the foundation model rest on them; plumbing and electrical when the factory design
   work needs them.

Decided by Steph 2026-11-19: internal use only, not posted publicly. NEC copy: Steph says it came
through a municipal library; kept for internal use.

## Then (Claude)

- Scout: collect the state interpretations / alternate methods list with each ruling's PDF, number,
  date and the section it concerns (flats-source-scout; the list needs a browser or its data feed).
- Section cutter front end for UpCodes prints (reuse the code-library tools: tables, superscripts,
  notes). No encoding.
- Tag Oregon wording per section from the matrix and change summary; attach interpretations and
  alternate methods as cited notes; record print date and source per section; a searchable index.
- Where it lives: the tools are here, but the readers are mostly the Factory-Sim agents. Decide the
  home folder before the first full book (a shared folder both repos read is the likely answer).
