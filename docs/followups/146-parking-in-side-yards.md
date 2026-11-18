# 146. Let the drive lane (and court) use the side setback where the code allows it.

146. [Claude] [scan: YES -- reds/yellows only go green] **Let the drive lane (and court) use the side setback where the code allows it.**

Raised 2026-11-04 from Steph's question "are we currently placing parking within setbacks?" (FOLLOWUPS 68); GO 2026-11-04.

DONE, on main and live (run 122+): flats/side-yard-parking (mechanism e92ca641; field `parking_side_yard_allowed` none|lane|lane_and_court|silent variant; all cities encoded 605de374, rounds 4 add83c5f + 7d07ec92 for West Linn, Clackamas, WashCo, King City; e301e746 steep-ground crash fix), merged into rescreen-1110 (5c6fb501). Portland verified allowed (33.266.120). Steph rulings: silent codes = side setback usable but a lot that fits ONLY that way is YELLOW + flag, never GREEN (2026-11-05-side-yard-parking-silent-codes). Rear-court false-green risk was split out to FOLLOWUPS 150. Detail: ../vicinitideals-worktrees/side-yard-parking.handoff.md and side-yard-parking.readings.md.

OPEN:
- Read the side-yard moves of the live re-screen (Steph 11-05: no separate bound; Milwaukie and Wood Village townhouse greens first). No record found (11-13) that this read was done.
- WashCo 407-6.4 strip is applied to a fourplex's small court on a cautious reading (some greens may go yellow needlessly; ask Steph if the count is large).
- 2026-11-13 KC-BUFFER (flats/kc-buffer, rides rel9): King City 16.124.110 C ENCODED. `parking_lot_line_buffer_ft` 10 ft off every non-street line when `abuts_lower_density_zone` (SF, R-9, LC, NMU) in R-12/R-15/R-24/AT and the four Kingston Terrace zones; KTTC/KTBB also 10 ft when `abuts_residential_zone` (C.1); R-9 exempt (no multi-dwelling). Zone-based reading of "multi-family property" (conservative); 10 held for SF neighbours too (one fact per lot). Run 124 has 0 King City GREENs, so nothing live moves to yellow/red from this. Audit of the gained-green reads (108 and 146): see ../vicinitideals-worktrees/kc-buffer.handoff.md -- no wrong GREEN in a sample of 32 side-yard greens; the side-yard-specific read was never done before.
- Tualatin RML 10 ft strip: no lots in RML today, revisit if any appear.
