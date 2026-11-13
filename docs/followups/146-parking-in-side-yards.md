# 146. Let the drive lane (and court) use the side setback where the code allows it.

146. [Claude] [scan: YES -- reds/yellows only go green] **Let the drive lane (and court) use the side setback where the code allows it.**

Raised 2026-11-04 from Steph's question "are we currently placing parking within setbacks?" (FOLLOWUPS 68); GO 2026-11-04.

DONE, on main and live (run 122+): flats/side-yard-parking (mechanism e92ca641; field `parking_side_yard_allowed` none|lane|lane_and_court|silent variant; all cities encoded 605de374, rounds 4 add83c5f + 7d07ec92 for West Linn, Clackamas, WashCo, King City; e301e746 steep-ground crash fix), merged into rescreen-1110 (5c6fb501). Portland verified allowed (33.266.120). Steph rulings: silent codes = side setback usable but a lot that fits ONLY that way is YELLOW + flag, never GREEN (2026-11-05-side-yard-parking-silent-codes). Rear-court false-green risk was split out to FOLLOWUPS 150. Detail: ../vicinitideals-worktrees/side-yard-parking.handoff.md and side-yard-parking.readings.md.

OPEN:
- Read the side-yard moves of the live re-screen (Steph 11-05: no separate bound; Milwaukie and Wood Village townhouse greens first). No record found (11-13) that this read was done.
- WashCo 407-6.4 strip is applied to a fourplex's small court on a cautious reading (some greens may go yellow needlessly; ask Steph if the count is large).
- King City 16.124.110 C: 5 ft buffer on a multi-family property abutting a single-family zone, per line; not encoded (comment only). No King City lot was GREEN in run 118, so no live false GREEN; re-check any King City R-15/R-24 GREEN.
- Tualatin RML 10 ft strip: no lots in RML today, revisit if any appear.
