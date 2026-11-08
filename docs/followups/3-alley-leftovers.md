# 3. Alley leftovers

3. [Claude] [scan: YES for the court placement; NO for the lot-page note] **Alley leftovers** (rear alley caad6f3f run 24; side alleys + the
   6-inch tight-fit rule 82d4c7de, run 26; whole-line fixes 8bf9a451 and
   59533da1 live in run 42; the partial-alley cut 288f0daa on main).
   RULED by Steph 2026-09-28 (register `2026-09-28-partial-alley`): a line
   an alley runs PART of is read carefully -- covered stretch only -- and
   the covered stretch is the travel lane only if long enough (covered run
   with buildable ground behind it >= stalls x stall width; probe 53
   partial rear lines, 30 long enough, 23 not).
   Status 2026-11-08: the court placement (c) BUILT on
   flats/court-alley-leftovers, waits for its bound; the rest is read and
   accepted. Remove this item when that branch is live.
   (a) 36 of run 24's 4,803 quadfit cannot draw (knife-edge or a slanted
   alley), read and accepted.
   (b) Of the 55 side-alley lots gained, quadfit draws no pod on 23 -- 15
   because quadfit keeps the pod across the front while FLATS turns it (a
   wide shallow lot, court at the alley end), 3 an irregular block, the
   rest overlays; read, accepted; if Steph wants the drawing to agree,
   quadfit's s6s needs the turned pod (quadfit only, not FLATS).
   (c) quadfit s6s alley-as-aisle on 3-of-5 FIXED 10f193ea (rides the next
   s6s run). The partial-alley court placement BUILT: the fit keeps the
   alley as the aisle only where some window (any angle) stands the court
   against the covered stretch, else the court keeps its own aisle; the
   drawing prefers such a window; the final drawing is read and a court off
   the stretch holds the lot out of GREEN (ALLEY_COURT_OFF_STRETCH, flag
   PARKING-ALLEY-COURT-OFF-STRETCH).
   (d) Gresham's 200 alley lots fail lot area/frontage regardless.
