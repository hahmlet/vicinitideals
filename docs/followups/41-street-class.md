# 41. Street class per lot line -- (a)+(b) SHIPPED 6b924963 2026-10-05; (i)-(iii) SHIPPED 2026-10-06 b03dcd88/92c5f1d9/972caa17, deployed.

41. [Claude] [scan: YES] **Street class per lot line -- (a)+(b) SHIPPED 6b924963 2026-10-05;
   (i)-(iii) SHIPPED 2026-10-06 b03dcd88/92c5f1d9/972caa17, deployed.**
   Live: Gresham note 5 caps on measured `at_street_end` (False-only);
   `local_street` from Milwaukie's TSP map (True needs Metro to agree) and
   Wilsonville's (False only: Villebois "Collector Avenues" are the master
   plan's Figure 7). TRAP for every full re-screen: it needs ALL 7
   `street_class_*` keys (washington added) + rlis_streets acquired into
   the snapshot, or the facts stay unasked (safe, no gain). Rulings, in
   build order (memory project_flats_street_class.md; register
   `2026-10-05-corner-access-quieter-front`):
   (i) corner lots on a quiet AND a busy street: the building FACES THE
   BUSY STREET so the quiet one is the side and the drive comes off it
   (both the 10-02 side-street ruling and `lowest_class` hold) -- ~224
   Milwaukie lots; where the code fixes the front on the quiet street,
   the drive comes off the front (lane beside the building) or fails;
   (ii) MORE CITY MAPS for every `lowest_class` city (Oregon City,
   Fairview, Tualatin, Clackamas Co., West Linn if a layer exists,
   Hillsboro PSU layer...) -- each city's class words checked against its
   code's words (the Villebois lesson);
   (iii) Gresham sidewalk easement (note 1: setback measured from the
   easement line): MEASURE where the sidewalk runs against the lot line;
   where it cannot be measured, FALL BACK to a stated worst-case easement
   depth (pessimistic), never to "none". Built: nothing measures the walk
   (RLIS 2851 is presence only, +/-10 ft; Gresham publishes no layer) so
   every street line takes the worst case: 7 ft on a Metro-local street,
   20 ft elsewhere (PWS 6.05.01/6.06.02), and the cap lifts.
   WashCo uninc 2026-10-06: 501-8.5 B(2)-(4) bars a 4-plex from
   collector/arterial/neighbourhood-route access, so `lowest_class` KEPT
   and ranked off the county TSP map (FClass2; an undrawn street ranks 0
   only where Metro calls it local). Bounds /root/street-class_bound_
   {base,new}5 and 6 on 137, every gain read.
   Still open: Tualatin through lots PARKED (351 lots, ~30 green if signed;
   an exact answer needs a court entered off the back street + a Tualatin
   class map); Wilsonville note P via easement layer 150 (low value while
   access_easement caps RN). Beaverton ROW strips are dropped in normalize
   since 77c99822; only bounds on the 10-01 stage files meet them.
