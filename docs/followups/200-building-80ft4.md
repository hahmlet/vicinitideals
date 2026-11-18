# 200. The building is 80 ft 4 in x 25 ft, not 80 ft x 25 ft

**Status:** told by Steph 2026-11-18 ("the building grew in width by 4 in. I've been meaning to tell you"); FD2 hand-off gives 80 ft 4 in x 25 ft, two storeys. rel10.

The live run (128) screens pod80x25@3. Every GREEN whose fit has less than 4 in to spare along the 80 ft side is a false GREEN for the real building. Also touched: frontage shares, side setbacks on narrow lots, lot coverage / floor area ratios (2,008.3 vs 2,000 sq ft footprint), court and drive geometry tied to the building length, the crane report (set-access).

Do: new design dimension in the design config (store as given: 80 ft 4 in), full bound in rel10, move read expects green -> yellow/red only from the length (any gain is a bug). Before the bound, count live greens with long-side slack under 4 in from the stored slack so the size is known.
To confirm with Steph only if the design config needs it: is 80 ft 4 in the outside face including cladding (assumed yes), and is 25 ft unchanged (FD2 says 25 ft).
