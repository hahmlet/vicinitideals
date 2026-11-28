# 223. Portland corner lots: the parking court is not kept behind the side-street building line (found by the 2026-11-27 green check)

223. [Claude] [scan: YES -- possible false-GREEN class, size unknown]
   PCC 33.266.120.C.1.a: "Vehicle area is prohibited between the primary structure and the
   street except as follows" (33.266/33.266.120.txt#L13); the exception is parking "located
   entirely behind the front and side street building lines" (#L17-L18), and a building line
   runs the whole lot (33.910/33.910.030.txt#L61). C.1.b caps paving between the side-street
   lot line and that building line at 20%. portland.yaml#L2384-L2393 says it plainly: "the
   site plan does not yet clip the court to the side-street building line on a corner lot
   (FOLLOWUPS 5)" -- left over when item 5 closed, never queued. The site plan keeps only the
   SIDE court off the street side (Lot Analysis/quadfit/s6s_siteplan.py ~#L1736-L1745); the
   rear court is not clipped (~#L1822). Section applies in every Portland zone (and the
   Multnomah pockets screened on 33.266.120, 8bf8f1b6).
   Evidence: green check g2 (docs/flats/completeness-2026-11/greens-g2.md): 5 of 11 sampled
   Portland greens are corner lots whose drawn court could sit nearer the side street than
   the building; the reports carry no plan coordinates, so CAN'T TELL, not wrong.
   NEXT: (1) count on 137 from the drawn plans: Portland corner greens whose court or aisle
   crosses the side-street building line; (2) if any, build the clip in the site plan (core
   area -- check no other lane owns s6s_siteplan.py) and bound it. Other cities may carry the
   same sentence; check which `parking_front_prohibited` cites a "building line" rule.
