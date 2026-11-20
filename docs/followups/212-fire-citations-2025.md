# 212 -- Fire access rules still cite the 2022 fire code and the 2022 local guide

Found 2026-11-19 while reading the 2025 Oregon Fire Code for FOLLOWUPS 211.

## What

FLATS's fire access rules (`flats/config/fire_roads.yaml`, the fire block of
`flats/config/jurisdictions/or/_state.yaml`) cite "OFC 2022" through the stored copy of the regional
guide, `flats/provenance/docs/or/ofc.2022.applications-guide.txt` (Clackamas Fire, revised 2023-06-21).
Both have been replaced:

- The 2025 Oregon Fire Code is in force. Chapters 1, 3 to 12 and Appendices C and D are held in
  `data/flats/books/building-codes/ofc-2025/` (gitignored). Chapter 2 is still wanted.
- Clackamas Fire's guide has a 2025-code edition (revised 2025-12-02); Tualatin Valley Fire has
  2025-code guides for commercial (2026-05-14) and for houses and townhouses (2026-07-13). All held
  in `data/flats/books/fire-agencies/` with a `sources.md` (scout, 2026-11-19).

## Do

1. Compare each figure FLATS holds (150 ft hose route, dead-end 150 ft, 20 ft width, turnaround
   sizes, the hydrant distances if any are used) against the 2025 code text and the 2025 guides.
   The 150 ft, 20 ft and dead-end figures were read on 2026-11-19 and are unchanged; the rest are
   not yet compared.
2. Store the 2025 guide as the provenance document and re-point the citations (drift tool,
   `--repoint`). The TVF&R house and townhouse guide prints a 200 ft allowance for a driveway
   serving ONE single-family house; it does not apply to a four-home building, but say so where
   the rule is cited.
3. No screen result should move. If one does, stop and read it.

## Known and not changing

- No local agency says which roads an engine may stand on (whole-document search of every guide
  obtained, 2026-11-19: Clackamas Fire, Tualatin Valley, Gresham, Portland, Canby). So no per-city
  fire access rule is needed for FOLLOWUPS 211's questions.
- Portland's guide and Canby print 250 ft for a fully sprinklered building as a rule; Clackamas
  Fire and Tualatin Valley leave it to the fire official. Steph ruled 2026-10-01: RED, no sprinkler
  relief. Unchanged unless Steph reopens it.
- Not obtained: Hillsboro and Lake Oswego (pages refused the download), the 2026 Portland Fire Code
  (publisher's online reader only), Sandy, Molalla, Estacada, Forest Grove and Cornelius (no current
  document found).
