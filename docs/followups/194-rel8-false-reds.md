# 194. rel8 false REDs to fix forward: Portland front maximum, Happy Valley sewer

[Claude] [scan: YES -- toward green, no GREEN at risk]

From the rel8 move read (../vicinitideals-worktrees/rel8-moves.findings.md, F2/F3). Not blocking.

1. **Portland CM1/CM2 front maximum (8 lots G->R).** 1N1E08DD -10000, 1N2E21CB -00200, 1S1E31AA -06300,
   1S2E02BA -14800, 1S2E07DD -05300, 1S2E15BB -15500, 1S2E20AA -03600 sit 11-63 ft back against the
   10 ft maximum (PCC Table 130-2); 1S2E16CA -15300's redraw misses fit (34 vs 68). In
   front_max_checked (flats/ingest/quadfit.py) try the drawing pulled to the front-max line first.
2. **Happy Valley sewer (177 Y->R).** WES mains are in no layer; "measured" rests on the CCSD#1 polygon
   alone, against sewer.yaml#L6-L10. Move Happy Valley to the unmeasured places (flag), or at least
   use a touch tolerance (one lot is 5e-11 ft off) and keep outside-district lots within 800 ft YELLOW.

Build as one lane cut from the rel10 base so it rides rel10.

## From the rel9 move read (../vicinitideals-worktrees/rel9-moves.findings.md), also fix-forward
3. **1N336BD00100 fire route 157 ft vs 150 ft (R)** -- fix-189 F3 now finds the turnaround and measures it red; the hand-off said F3 only moves toward green. Re-check the route.
4. **~70 lots lost GREEN only for an unmapped street class** (~46 Gresham) under drive-spacing. Find or trace the class (unranked = yellow is a standing ruling, so this is data, not policy).
5. **24 Beaverton type-A lots went yellow->red** (RC-OT 14, RC-BC 10), though the hand-off said no colour move. The reader ruled them right (toward red); the hand-off expectation was wrong. Note only.

2026-11-18 BUILT flats/false-reds-194 1e25ffa6 (from rel10d; hand-off ../vicinitideals-worktrees/false-reds-194.handoff.md; scope lists 137 /root/fr194/; suite 8,340 passed). (4) Gresham street missing from the city map counts quiet only where Metro and OSM both say residential (~16 of 75 clear the driveway check); (1) Portland front maximum: a no-lane plan pulled whole toward the street (scope 432; of the 8 named, 1 clears, 1 likely, 6 not fixable by a pull -- reasons in hand-off); 158's 1S212AD01301 shrunk envelope fixed (10 ft step in the front line misread as road). LEFT: (3) 1N336BD00100 stays RED (hose 157 ft); 189 Clackamas R10 share; same street-class losses in Milwaukie, Oregon City, West Linn, Sherwood (40 lots) not investigated. Every lot gaining GREEN must be read one by one. STEPH: downtown Gresham driveway cut on a local street needs city permission -- held off GREEN (safer); an older Gresham note says the rule never applies because downtown needs no parking.
