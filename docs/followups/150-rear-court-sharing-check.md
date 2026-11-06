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
