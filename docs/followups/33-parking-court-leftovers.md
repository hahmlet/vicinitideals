# 33. Parking court leftovers (fix ca26e048 LIVE as run 63, 2026-10-02: drift 61->63 green->yellow 3,459, unknown->yellow 4,453, 0 unexplained).

33. [Claude] [scan: YES for (c) and any speed-up (must prove identical answers)] **Parking court leftovers (fix ca26e048 LIVE as run 63, 2026-10-02:
   drift 61->63 green->yellow 3,459, unknown->yellow 4,453, 0 unexplained).**
   Status 2026-11-08: (b) CLOSED, (c) BUILT on flats/court-alley-leftovers
   (off flats/court-front-yard 698907b2), waits for its bound; remove this
   item when that branch is live.
   Done: (a) the court beside the building f7ba7038; (d) scanline raster
   ce65b86b (2.2-2.6x faster).
   (b) CLOSED: the lots outside the 15,940 scope were corrected by the full
   re-screen run 65 (2026-10-07, code 62b2259d, which holds ca26e048 and
   f7ba7038; promoted by Steph) and every full run since (the 10-19 one).
   (c) BUILT: an s5o envelope whose only unread yard is the rear (the rear
   line off the alley, no second resolution) now takes the court's ground
   from the front and side yards FLATS resolved; every other s5o-envelope
   lot with a taxlot polygon (no edges, landlocked, a yard with no number)
   is held out of GREEN, reason COURT_GROUND_UNREAD, flag
   PARKING-COURT-GROUND-UNREAD. Without a polygon the court stays inside
   s5o's envelope itself, so no hold.
   Count of s5o-envelope lots per colour: needs the bundle on 137
   (`envelope_source == "quadfit"`), not measured from the PC.
   Next speed levers if needed: `has_window` in the court searches, `ground_for`.
