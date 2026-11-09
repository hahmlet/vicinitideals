# 7. Green and outdoor space: charge the SHAPE, not just the amount.

7. [Claude] [Steph: HUMAN_TODO 27] [scan: YES] **Green and outdoor space: charge the SHAPE, not just the amount.**
   Done and live: (a) open space / landscaping read lot - building -
   pavement (2026-09-28, `paper.paved`; `OPTIMISTIC_CHECKS` is empty);
   (b) Portland 33.110.240's 12x12 square (10x10 R2.5) on the lot's own
   ground, 7bd2d1e4..674208b6, run 42: 3,056 Portland lots fail on the
   square alone (green->yellow); Milwaukie's 96 sq ft / 5 ft patio
   encoded. Open:
   - Whether to chase the Portland square's near misses is HUMAN_TODO 27.
   - A side-street court standing as a long side strip stays unmeasured
     (`outdoor_square` returns None for a side-fed column). 2026-11-08
     census (assign_rescreen_1110): 3 Portland lots held yellow on it
     alone (R2.5 1N1W12AA  -07400; R5 1S2E17CC  -09900, 1N1E08BD  -13900).
     Measuring it means drawing the column in flats/fit/draw.py (placement),
     another lane's file; left until that lane is clear.
   - Fairview VA's paper minimum (3,102 sq ft) -- FIXED 2026-11-08 on
     flats/green-space-shape: the paper fit read waived (exempt) yards as
     unknown and never costed the envelope; it now reads them as 0 ft and
     charges a `leftover` floor (building + least pavement over 1 - the
     landscaping / open-space share, or plus the open-space area). VA is
     now 6,228 sq ft (pod56x36), set by the 25 % landscaping. Planning
     page only; no lot colour rests on the paper area. Knock-on: the
     screen's side-yard stated-fit trigger now also compares the lane and
     court let into the side yard (the paper's one orientation could hide
     it), so 38 zone x design pairs gain the stated fit (Canby, Oregon
     City R-8/R-10, Tualatin, West Linn, Fairview): GREEN->YELLOW only.
   - (c) for the county map only: landscaping share (Happy Valley 20 %,
     Portland RM 15-30 %, Oregon City R-2 15 %, Fairview 20-25 %,
     Wilsonville 15 %) -- s6s holds no landscaping reserve.
   - (d) what the leftover is FOR (sheds, ADUs, a second pod) is product
     direction, belongs with item 6's "least ground under pavement".
   Ruled NOT owed: Troutdale 8.120.B.1.b (balcony), Oregon City 17.62.057
   (multi-family), Wilsonville Villebois 25 % (communal), Gladstone /
   Tualatin / West Linn / Clackamas county state none.
