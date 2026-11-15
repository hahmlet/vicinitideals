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
