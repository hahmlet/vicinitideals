# 150. Rear-court sharing of the rear setback may be wrong in Gresham, Sandy, Troutdale -- FALSE GREEN RISK (found 2026-11-05)

150. [Claude] [scan: YES -- toward red] **The parking court shares the rear setback where the code may forbid it.**
   Found by the side-yard parking reading (FOLLOWUPS 146; table in ../vicinitideals-worktrees/side-yard-parking.readings.md).
   Today the court parks inside the REAR setback everywhere unless parking_required_yard_prohibited or
   parking_lot_line_buffer_ft is set (flats/score/paper.py paper_fit ~L1441-L1452).
   - Gresham (pod as quadplex): 7/7.0420.txt#L56 lists parking "in the front or street side yard setback, or in the rear yard
     setback when there is an alley" -- read as a closed list, no alley = no parking in the rear setback.
   - Sandy: 17.98/17.98.50.txt#L6 "Parking areas, which abut a residential zoning district, shall meet the setback" -- read
     literally the court must stay out of side AND rear setbacks.
   - Troutdale: 9/9.095.txt#L3 same wording as Sandy.
   Work: Claude reads each in full (definitions of parking area vs driveway, the zones it reaches, TH vs QP), then encode
   parking_required_yard_prohibited (or a rear-only field) where it binds; bound; read every lost green.
   Status: found, not started. Priority over 146's gains (false green).
   11-05: round 2 bound HOLD (moveread ../vicinitideals-worktrees/rear-court-150.moveread.md). Round 3 c89c1057: the drawn court is
   checked line by line against 3.130.A (side 10/7.5/5 by neighbour district, rear 20 max); Sandy strip read on the drawn court.
   The five Gresham 50x100 lots were left alone (Copilot could not tell if the fit was unmeasured): re-check in the r3 move-read.
   Re-bound /root/rear_court3 (vs live pd2ab; re-splice on the new live at release).

## Round 4 mini check (2026-11-06)
- rc4mini (10cc88b4, 133 lots: the 132 Troutdale false greens + 24E14DA00700):
  45 Troutdale lots still GREEN with the court under the single-house yard,
  and Sandy 24E14DA00700 still GREEN. Causes: the drawn check ran only on an
  outright fit pass, but a tolerated fit still reads GREEN; the screen's
  doubt test kept a `rules.trusted` gate; Sandy's check compared the bare
  `sandy` with the layer path. The test fixture used the path for both and
  hid it.
- FIXED 553af386 (pushed). rc5mini: 16 more GREEN -> YELLOW, no new GREENs;
  the 36 GREENs left measured court-to-line by hand: every one clears a rear
  and side figure. One to look at in the move-read: 1N3E36AC  -06300 has no
  rear line in s4's classes (three side lines), court 17.2 ft off the line
  opposite the front -- an upstream edge-class question, not this branch.
- Re-bound /root/rear_court4 queued on 137 behind max_front2: base 6f2d8c35,
  new 553af386, splice base and compare live = rel2.
