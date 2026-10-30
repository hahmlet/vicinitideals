# 94. Townhouse row held to the street's angle -- up to ~105 false reds (found by the round-2 read of item 93, 2026-10-17).

94. [Claude] [scan: YES -- false reds only] [after 93 merges] **Townhouse row held to the street's
   angle -- up to ~105 false reds (found by the round-2 read of item 93, 2026-10-17).** The
   townhouse form sets the row of four home lots parallel to the street line. On a lot whose side
   lines meet the street at a slant (example 1S126DD01800), a row set square to the SIDE lines
   would still give every home lot its street frontage and fit. Fix: also try the row square to
   the side lot lines (and keep the frontage + per-home-lot width/area checks of b5c0cbf4 on the
   tilted row); then bound and read every gain. Never loosens a check, so no false-green risk
   beyond the usual read.
