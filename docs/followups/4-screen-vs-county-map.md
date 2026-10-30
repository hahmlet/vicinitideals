# 4. Four places the screen and the county map disagree, found by the bridge's sample run (2026-09-17) and left alone on purpose.

4. [Claude] [scan: YES] **Four places the screen and the county map disagree, found by the
   bridge's sample run (2026-09-17) and left alone on purpose.** Each its
   own change. Done and dropped here: the side court (15ffab9e, run 42,
   2,374 yellow->green; the 3 ft front rule cef95109); (b) alley as aisle
   (caad6f3f, item 3); (e) corner fronts (ca52f76a, run 28) with its
   leftovers (i) `lowest_class` (now read off street ranks, item 41) and
   (vi) b440fc67, plus the Gresham through-lot corner f171c994; private
   drives (Steph RULED 2026-09-30, register + memory
   feedback_access_rulings_2026_09_30.md, built dbc2cc40, run 42). Open:
   (a) the court's shape: an L/T-shaped search for the other 339
   quadfit-fits lots; two-row stall count. `court_across` draws one row of
   stalls across the lot (six at 9 ft = 54 ft); quadfit's s6s uses the
   largest rectangle behind the building either way round, so a 63-ft-wide
   Portland R5 lot seats eight along its depth. County run 2026-09-18
   (`/root/bridge_county2`): 517 quadfit-green / FLATS-yellow lots off
   their own lane, 268 of them seating eight with the row along the lot.
   The other direction: on the 13,196 lots both call green FLATS seats
   FEWER than quadfit on 3,881 (one row across where s6s found two) and
   MORE on 160 (`target` where quadfit's tier is `minimum` 100, `preferred`
   where `target` 58) -- find what the screen's row counts that s6s's
   rectangle does not before changing either. The stall count was decided
   2026-09-18 (HUMAN_TODO 18) and is out of this item.
   (c) quadfit's policy gates are not site facts: `z_overlay_constrained_site`
   (PCC 33.418), the overlay kill layers, `existing_*` current use and the
   sewer gate (`no_public_sewer` is a hard gate there; here `public_sewer`
   is observed but no Clackamas standard turns on it) -- 84 of the 178
   screen-GREEN / quadfit-red lots in the sample.
   (d) the sweep -- the screen tries 180 angles, s6 fits at the front
   bearings only; 94 of those 178 are quadfit `siteplan_no_layout` lots the
   sweep found a fit on. (c) + (d) county-scale: 21,660 GREEN-where-red.
   (e) leftovers still open: (ii) corner lots with an alley are left
   unnamed (the alley's name is resolved against either frontage); (iii)
   the court's end is assumed to reach the side street, as for a side
   alley; (iv) Wilsonville V: 25 answers lose slack because the long
   interior lines are now SIDE lines (7.5 ft) not rear (5 ft) -- correct by
   the code, never changed a colour; (v) three Clackamas-unincorporated
   unnamed lots moved on input vintage, replayed identical. Wilsonville
   4.001(157)(2) / MCC 39.2000 pathway corners: HUMAN_TODO 24.
   (`steep_slope` struck 2026-09-27: no standard in the corpus is
   conditioned on it; the hillside rules ride the overlay layers.)
