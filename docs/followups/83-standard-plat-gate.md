# 83. Measure Washington County's "standard plat" gate instead of flagging it (offered 2026-10-14, item 79).

83. [Claude] [scan: YES (yellows only go green)] **Measure Washington County's "standard plat" gate instead
   of flagging it (offered 2026-10-14, item 79).** 731 R-9/R-15/... lots are yellow only because
   nothing says whether the lot was made by a standard subdivision or partition plat (302-2.14 ..
   307-2.13), so unmeasured = worst. A lot's recorded legal description names its plat ("PARTITION
   PLAT 2004-123, LOT 2", or a subdivision name and lot) where it was platted, and reads metes and
   bounds where it was not -- that measures "made by a plat". "Standard" vs a PUD or expedited land
   division needs the land-use case type behind the plat. Candidate sources, NOT checked yet:
   Washington County Assessment & Taxation property records (legal description per tax lot), the
   county surveyor's plat index. First step: confirm either holds the legal description in bulk
   for the WashCo uninc lots, then rule how a PUD plat is told apart.
   SOURCE FOUND 2026-10-15: Washington County's Taxlots FeatureServer/151
   (gispub.co.washington.or.us/server/rest/services/Urban_Services_Plan_Framework/Urban_Services_Framework/FeatureServer/151),
   free, 2,000 per page, LEGAL_DESCRIPTION on 201,183 of 201,678 lots ("VIEW CREST, LOT 3",
   "2016-037 PARTITION PLAT, LOT 1"; metes and bounds otherwise). PUD named in the text on only
   58 lots; no case-type index found, so standard vs PUD is not separable from it. Next: read the
   CDC gate -- does a PUD plat change the answer? If not, measure "made by a plat" and go.

READ 2026-11-03 (Copilot scout + Claude check): the gates are 304-2.14 / 305-2.14 / 306-2.14 / 307-2.13 (R-9..R-25+; R-5/R-6 302/303-2.14 have no plat gate): "an existing lot or parcel that was approved for the construction of a Single Detached Dwelling Unit through a Standard Subdivision or Standard Partition" (cdc.304.r-9.txt#L92-L94). "Standard" is defined in cdc.106.definitions.txt#L613-L618, added by Ord. 890A (eff. 2023-03-09), and its stated contrast is the Middle Housing Land Division ("These are distinct from a Middle Housing Land Division") -- NOT old vs new plats. Claude first framed it as "pre-code plats may not count"; Steph asked whether that was validated -- it was not, and the text points the other way. WORKING READING: any recorded subdivision or partition plat, any age, passes the gate unless the lot was created by a Middle Housing Land Division (Section 606); a metes-and-bounds lot was not created through a subdivision/partition, so it misses this Type I path and falls to the next tier under the standing three-tier rule (no re-ask). PUD plats: no text treats them differently; count as platted. Build next: LEGAL_DESCRIPTION from WashCo Taxlots FeatureServer/151 -> plat named = pass (MHLD plats -> flag), metes and bounds = gate missed.
- 2026-11-08 BUILT ce734209 (flats/washco-plat-gate): WashCo Taxlots legal descriptions -> platted / MHLD (16, none gated) / no plat / unread; only platted passes (yellow->green). Proxy of 5,644 pod-sized gated lots: platted 2,735, no plat 1,547, held by age check 917, unread 445. Rides flats/rescreen-1110. [Steph] OFFERED: (1) 917 lots held because the plat cannot be shown older than 2022 middle-housing splits (tract built in 1-2 years) -- ease? (2) whole platted lot + part of a vacated street, or two whole platted lots -- count as made by a plat? Both built conservative.
- Steph 2026-11-08: (1) age-check lots stay YELLOW; (2) YES to both (whole lot + vacated street; several whole platted lots). Building (2) on the branch + rulings.yaml entries.
