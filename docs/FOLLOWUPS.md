# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The county drawing sizes a one-row court on the ONE-WAY aisle.**
   `s6s_siteplan.py` L606-607 takes one row of stalls when the court is at
   least `stall_d + aisle_one` deep and charges `aisle_one` for it; the
   paper lot and the screen charge the two-way figure on purpose
   (`paper.court_depth`: a dead-end court off one side lane is entered and
   left forward, "the court is two-way", `parking_aisle_one_way_ft` declared
   excluded). Where the two figures differ the county drawing is the
   shallower one: Gresham 23 vs 24 (1 ft, the largest population), Wood
   Village 12 vs 24 (12 ft -- a 12 ft aisle behind 90-degree stalls is not a
   court a car backs out of). Every other city prints one figure. Decide
   which product is right (the paper lot's reasoning looks right), make s6s
   read `aisle_two` for the one-row court, measure the Gresham + Wood Village
   verdict moves before running (check the binding constraint first), then
   the county run. Offered 2026-09-17.
2. **The screen still has no production caller.** `flats/score/screen.py`
   (`screen()`, `fit_for`) is exercised only by tests; the plan page shows
   the paper lot, not the screen's triage. Wiring a caller is the step that
   turns the FLATS screen from a tested module into a product. Offered
   2026-09-17.
