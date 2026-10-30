# 36. Parking tool queue (Steph 2026-10-02: "do them in the reverse order you listed them").

36. [Claude] [Steph: the OAR strip question] [scan: YES] **Parking tool queue (Steph 2026-10-02: "do them in the reverse order
   you listed them").** (5) partly, (4) and (3) LIVE as code f7ba7038;
   (2) turning path LIVE as 1723db45 (Steph "ship it"; register
   `2026-10-02-three-point-turn`: every stall usable by the AASHTO P car,
   three-point turn ok; ledger `flats/config/court_turns.json`). TRAP: a new
   court shape in the corpus needs `python -m flats.score.turns`
   (test_turns fails until it is solved).
   CHECK after the weekly (not recorded done): read the moves on corner lots
   with `lowest_class` and in Tualatin, Gladstone, Multnomah uninc and
   Hillsboro; turning path expected ~3% of Portland greens on narrow
   end-on lots to go yellow (bound: 18 of 561).
   Strips: RULED Steph 2026-10-04 (register `2026-10-04-planted-strips-yellow`):
   "Let's have strips be a flag for yellow at this time" -- DONE 1d3c89cb:
   a plan that misses only by the strip and clears with it read as
   unstated is YELLOW with flag PARKING-STRIP-UNCONFIRMED. STRIP IMPACT
   (bound 2026-10-04, strips on vs off): Gladstone 384 -> 445 green of
   3,217 (+61), Multnomah uninc 885 -> 898 of 2,213, Hillsboro ~+20 of
   27,402. Steph: "planter strips aren't parking, they're landscaping".
   QUESTION for Steph, still open: OAR 660-046-0220(2)(e)(E) makes large
   cities apply single-family parking standards to middle housing -- it
   may cancel the strips single-family homes are not held to (Multnomah,
   Gladstone, Hillsboro, Wood Village, Oregon City); encoded strict
   meanwhile. The OAR question decides whether the flag can clear.
   Left of (5): strips not yet encoded -- Wood Village 350.065(C) and Oregon
   City 17.52.060.C (one-lot projects only), Happy Valley 16.43.030.E.3 and
   Troutdale 9.095(A) (the neighbour district's setback; needs per-line
   neighbour zoning), Tigard 18.280.040.D.4 (width in unstored 18.420);
   unread chapters ZDO 1009, West Linn CDC 54, Washington CDC 407-6,
   Sherwood 16.92, King City 16.124, Tigard 18.420, Troutdale Ch. 11;
   Fairview 19.163.030(E) 5% of the parking area.
   (1) the free-form generator (item 92) -- PARKED by Steph 2026-10-04
   ("leave the free form generator for now").
