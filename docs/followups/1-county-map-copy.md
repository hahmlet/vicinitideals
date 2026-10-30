# 1. The county map copy: loose ends after the first promotion (HUMAN_TODO 20).

1. [Claude] [Steph: HUMAN_TODO 23] [the "look again" bullet Copilot-able] [scan: NO] **The county map copy: loose ends after the first promotion (HUMAN_TODO
   20).** The September copy (snapshot 3, run 10: 400,032 lots = 288,031
   measured + 112,001 unmeasured with a reason) was PROMOTED 2026-09-20.
   Done since and dropped here: condo records (e7217598, run 42); Happy
   Valley `MURM2`/`MURm2` both aliased to MURM; terrain (`dem_3dep` is
   acquired and the slope stage exists). Still open:
   - No writer for lot decisions in `app/` yet (they are inserted by hand
     or by a future review page). No lot decisions exist yet (0 rows
     2026-09-25), so the "look again" flag has nothing to mark until a
     review page writes some.
   - A decision on a lot whose verdict moved in a re-screen of the same
     copy (`promote --run`) is not marked "look again" -- only ground and
     zone changes are flagged, so a re-screen's moves are read in its
     drift report and nowhere on the lot page.
   - The 142 Multnomah `_unincorporated` RR lots behind a
     `planned_development` lever are a relief-policy question --
     HUMAN_TODO 23 (2026-09-25).
