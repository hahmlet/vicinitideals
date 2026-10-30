# 6. Where parking may SIT, and which street is "the front".

6. [Claude] [scan: YES] **Where parking may SIT, and which street is "the front".** Offered
   2026-09-19 when Steph asked why the court is always behind. **Steph's
   ruling 2026-09-19** (register `2026-09-19-orientation-choice-order`):
   trying each street as the front applies ONLY where
   the lot has more than one street AND the code leaves the choice to us;
   HUMAN_TODO 21 DECIDED: (1) the orientation that turns the lot green,
   (2) if both, the one that reaches the `preferred` band, (3) if both
   preferred or both only `minimum`, the orientation whose COURT has the
   least exposure to a street (its frontage on street edges; a court on no
   street beats one along the shorter street beats one along the longer);
   a higher band wins before exposure decides. **More parking is not a
   goal** ("sufficient, but minimal parking so we can fit a 2nd pod"), so
   s6s's "keep the orientation with the MOST stalls" rule goes. And read
   every city for multi-street rules even where the front is clear.
   Through lots RULED 2026-09-30 (register `2026-09-30-through-lots`,
   built 67402fea as (i)): city governs -> follow it, unmeasured -> worst
   (Gresham/Clackamas access control, Tualatin/Fairview lowest-class
   access); free choice -> the end that fits.
   BUILT and live (s6s_siteplan.py): Slice A per-line fields, Slice B
   corner fronts (bound 364c360e), through lots + side court + trimmed rear
   court (bound v4 vs run 10, loaded 2026-09-20), (k) 4a3cc09c, (l)
   5cb2bd75/547e0578/94fed5e3, (n) 91840447, (o) 38932a24 (a zero front
   setback is the code's answer -- Portland Table 130-2 "none", Oregon
   City 17.35.060.E -- never an unknown). Bound files on 137:
   `/root/corner_diff.py`, `corner_moves.csv`, `/root/lane_diag3.py`,
   `/root/strip_chains/v2/replay2.csv`. Still open:
   (f) the rear court keeps a tie with the side court; Steph's "room for a
   2nd pod" could read the other way (prefer the side court so the rear
   yard is free) -- the ties are NOT counted: only the winning offer is in
   the output, so counting needs both offers written out.
   (g) the two-row court's lane lands on its near row's end where a stall
   is drawn (one-row courts turn the aisle to the lane; two-row need the
   landing carved out of the row or the lane run to the aisle band).
   (h) the alley-aisle court (`townhome_rear_court_alley_aisle`) still
   scores the whole room's exposure -- trim it to its stall row + back-out
   depth.
   (j) COUNTED, not built: in a ban city (Portland 33.266.120.C.1.a,
   Milwaukie 19.505.3.D.4.a) the side court is drawn on ONE side of a
   through-lot pod -- a court on both sides would help 8 lots.
   (k) left: bent fronts whose body swings off the strip (Gresham
   1N3E30CB -12300, ~238 of the 286 targeted) need an angled/jog lane.
   (l) left: whether an alley that stops mid-lot needs the flat-cut strip
   is open; 32E07DC03600: the curved line past the lane may be a street s4
   does not label -- worth a look.
   (m) COUNTED 2026-09-29 on 09-18 data: 32 wide fronts with no envelope
   cell in street reach = 7 overlay carve-outs, 6 round tier-C insets, 3
   tier B with no strip, 16 with a strip in both envelopes (an older s6s
   refused them -- re-check on the current run).
   (n) left: read the 15 cul-de-sac/angled "not a pole" losses on the
   county run (local trial 65 lost / 51 redrawn / 884 same).
   Queued behind it, each to bound first: (b) Portland 33.266.120.C.1.b:
   on a corner lot the court must sit behind the side-street building line
   and pave at most 20 % of the side-street setback -- the drawn lane is
   consistent by construction, so only "behind the building line" is
   unread; (d) Fairview 19.30.050(D)(2)(a) side-yard parking setback ->
   redirect ledger; (e) Gresham 3.0100: the front is fixed where the
   minimum lot depth is met in one direction only (needs depth both ways).
   ((a) struck 2026-09-27; (c) `lowest_class` now reads street class, item
   41.)
