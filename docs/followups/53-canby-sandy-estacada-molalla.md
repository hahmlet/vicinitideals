# 53. Canby, Sandy, Estacada, Molalla.

53. [Claude] [Steph: (b) Molalla PDFs; (c)-(d) HUMAN_TODO 30; (f) Downtown yes/no] [scan: Estacada + Canby/Sandy DONE in run 73; Sandy REVERSED by r3 (83a7683d on main), rides the weekly ~2026-10-19; (b)-(f) below still open] **Canby, Sandy, Estacada, Molalla.**
   Steph's by-right-only ruling (2026-10-08) made Canby and Sandy RED in every zone
   (register `2026-10-08-by-right-only`, `2026-10-08-canby-no-state-fourplex-backstop`,
   `2026-10-08-sandy-no-state-fourplex-backstop`; each zone note
   opens "RED BY RULING" so the ruling can be reversed). REVIEW TIERS (Steph 2026-10-14, r3;
   register `2026-10-14-review-tiers`): Sandy R-1/R-2/R-3 come back YELLOW -- the 17.90.40 B
   design review applies stated standards but may add conditions (REVIEW-CONDITIONS). Bound
   on run 74's inputs: 0 green / 108 yellow / 1,853 red of 1,961 (R-1 779 red, 719 on fit;
   R-2 69 y / 510 r and R-3 39 y / 564 r, mostly the landscaped-area minimum). Canby
   re-checked and stays RED: the 16.49.030 Type III review is a one-off judgement (zone notes
   quote it). Steph 2026-10-15 (item 85, not merged yet): judgement-only red and the "may add
   conditions" tier both become GREEN with a flag inside a UGB -- the clear-objective bound
   shows newly admitted Canby 108 green / 35 yellow and Estacada R-3 10 red -> 6 green / 4
   yellow, so Sandy's yellows move again when 85 merges.
   Estacada (run 73 LIVE): 14 green / 7 yellow / 2,860 red of 2,881; admits C-2, CMU, R-3
   (townhouse lots only) and NCR (only within 200 ft of Eagle Creek Rd or Hinman Rd,
   `near_named_street_200ft`, flats/geom/named_street.py); the 16.132.015 planning-staff
   review Steph ruled by-right (register `2026-10-08-estacada-staff-review-by-right`). All 14
   greens read by hand; doubts, none changed: 34E17 02000 (30941 SE River Mill Rd) is a
   split-zone lot, 47% NCR, its band not checked against the zone line; 34E20AB01200 (30905
   SE Eagle Creek Rd) is an occupied apartment complex ($3.9M of buildings); 34E20AC00200/00201
   (1015 NW Wade St) are two COM lots whose owner the roll does not give; `inside_ugb` was
   false on all 14 (the UGB layer was not read -- fixed f003fd49 on flats/clear-objective).
   Checks Steph asked for (2026-10-08): wetlands overlay = the NWI layer already applied;
   historic overlay = inventoried buildings only; 33% geotechnical = already stricter in
   slope.yaml (15%). Still open:
   (b) Molalla (HUMAN_TODO 29, Steph's PDFs): 7 of 11 chapters (2.3, 2.4, 3.2, 4.4 still 429)
   -- layer files parked outside the repo unless all 11 land (copy in /tmp/fg53/molalla_parked
   + the new 5.1); gate already read: admits R-2, R-3, R-5, refuses R-1, C-1, C-2, M-1, M-2,
   PSP; ALSO check whether those zones need design review.
   (c) NCR "major collector" half of EMC 16.25.020 is unmeasured (no street-class map for
   Estacada; Currin Rd looks like one) -- lots near it screen RED; add the name to STREETS in
   named_street.py once Steph confirms (HUMAN_TODO 30 q5).
   (d) Airport Safety overlay (16.54) zone map, side-line PUE (the code only says the city MAY
   require 10 ft), parking facing Eagle Creek Rd and the Currin Creek 70 ft strip: Steph's
   answers pending in HUMAN_TODO 30 q1-4.
   (e) minimum density 8.712 du/ac in C-2, R-3, NCR on the unit-lot path (the quote check
   wants a printed operand; needs a form that holds half of a per-dwelling area).
   (f) the Canby/Sandy doubts (design review, 20 ft yards, 13 du/ac, overlays) were MOOT
   while the by-right ruling held -- re-read them once item 85 lands; Estacada's R-3
   townhouse-only reading and the MMU Council-master-plan refusal were re-read 2026-10-08
   and stand; the Downtown zone (D) could be encoded with the named-street tool (fourplex
   outright if it does not face Broadway/Main/OR 224, north of OR 224, 16 du/ac) -- waiting
   on Steph's yes/no. Forest Grove stays blocked on HUMAN_TODO 28.
