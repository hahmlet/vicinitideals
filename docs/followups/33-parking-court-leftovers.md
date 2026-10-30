# 33. Parking court leftovers (fix ca26e048 LIVE as run 63, 2026-10-02: drift 61->63 green->yellow 3,459, unknown->yellow 4,453, 0 unexplained).

33. [Claude] [scan: YES for (c) and any speed-up (must prove identical answers)] **Parking court leftovers (fix ca26e048 LIVE as run 63, 2026-10-02:
   drift 61->63 green->yellow 3,459, unknown->yellow 4,453, 0 unexplained).**
   Still open ((a), the court beside the building, fixed f7ba7038; (d) the
   scanline raster ce65b86b DONE, 2.2-2.6x faster):
   (b) lots outside the 15,940 scoped whose court stands in a side or front
   yard INSIDE the lot are corrected only by the next full re-screen
   (weekly run 65 onward -- not recorded as checked);
   (c) s5o-envelope lots use the whole lot (less carve) as the court's
   ground. Next speed levers if needed: `has_window` in the court
   searches, `ground_for`.
