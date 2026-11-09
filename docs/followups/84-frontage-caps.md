# 84. Frontage caps read as caps on every street -- DONE on flats/dropped-lots-fairview (2026-11-08), remove once its bound is read.

84. [Claude] [scan: YES, one lot] **Frontage caps read as caps on every street.** History: MERGED
   2026-10-15 flats/frontage-caps 667f57e9; phase 3 flats/frontage-fragments d8c6da14 (556 gains,
   READ at run 78 2026-10-20). Every % cap is per street line (unknown street = shortest line).
   The last open piece, Fairview VC's conditional-use path on 1N3E33AB  -00500 (1700 NE Market
   Dr, the only FLX lot), was never a reading gap: FLATS already opens it (FLX alias of VC, observes
   inside_mapped_use_area; unit lots and the ORS 197A.400 conditional-use rulings), but quadfit's
   hand-written Fairview block carried no `zone_aliases`, so s3 dropped the lot zone_not_in_rules
   and FLATS could only say LOT-NOT-MEASURED. Fixed 2026-11-08 on flats/dropped-lots-fairview:
   `zone_aliases: {"FLX": "VC"}` in rules.yaml's fairview block, plus a quadfit test that every
   FLATS alias ruling resolves wherever quadfit holds its target (FLX was the only miss).
   Expected bound move: that one lot, yellow (not measured) -> whatever its fit gives.
   Close this item when the bound is read.
