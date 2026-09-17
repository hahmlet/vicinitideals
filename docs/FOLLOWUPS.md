# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The 5 ft standoff between the rear wall and the first stall.** quadfit
   draws a gap of max(5, `parking_building_buffer_ft`) behind the building
   (`SiteplanSpec.building_parking_gap_ft`; Fairview encodes 4). Neither the
   paper lot nor the FLATS screen carries it: their court depth is stall +
   aisle with nothing between wall and stall, so both understate depth by
   5 ft against the county drawing. Declared in `PaperFit.excluded` rather
   than slipped in because the FLATS screen's `fit_ft` reads the same
   `court_depth` and every depth-bound verdict would move. One design
   constant on `Parking`, read in `court_depth`, both consumers move
   together. (The screen's fit charges the court's WIDTH since 2026-09-17,
   `screen.fit_for`; the gap is the last piece of the county drawing it
   lacks.) Offered 2026-09-17.
2. **A lane ceiling the pod cannot get under.** Six cities cap the
   maneuvering width on townhouse (unit-lot) plats at 10 or 12 ft
   (`parking_maneuvering_max_width_ft`, `unit_lots` variants only). A cap
   under the lane the design draws is not a wider lot, it is a site plan
   that cannot be drawn -- s6s drops the lane where the cap is under it, but
   the paper lot has no "cannot be drawn" state and declares the field
   unread. Adding that state to `PaperFit` (and a row on the plan page) is
   the honest fix; Milwaukie's 10 ft cap against a 12 ft lane is the case
   that would show. Offered 2026-09-17.
