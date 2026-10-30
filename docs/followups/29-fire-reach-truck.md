# 29. Fire reach: measure where the truck really stands (Steph 2026-10-01, "later improvement"; RULED 2026-10-05).

29. [Claude] [Steph: (C) county widths, deferred] [scan: YES for (C) when widths arrive; (A)/(B) checked after the weekly run] **Fire reach: measure where the truck really stands (Steph 2026-10-01,
   "later improvement"; RULED 2026-10-05).** Item 28 (the 150 ft hose,
   OFC 503.1.1) is LIVE since run 59. RULING 2026-10-05 (register
   `2026-10-05-fire-hose-from-curb`; no national standard; one Southern
   California template says "10 feet from the edge of the curb"): Steph
   "Let's go with stricter" -- the hose starts 10 ft out from the NEAR
   curb, capped at the street's middle; "with a flag to check later" --
   FIRE-HOSE-START (severity 1, the plan stays red) where the hose is the
   one bind and the route clears measured from the curb.
   (A) SHIPPED d8880db1 2026-10-05: flats/geom/curbs.py reads PBOT Curbs +
   PaveWidth, Multnomah RoadWidth, Wilsonville Width; a drawn curb loosens
   only where a recorded width agrees within 4 ft.
   (B) Steph 2026-10-05 "Assume narrow" (register
   `2026-10-05-unmeasured-street-narrow`): a street with no measured width
   is the narrowest a truck may use (20 ft, OFC 503.2.1) until measured --
   the hose starts at its middle; FIRE-HOSE-START says a width may lift it.
   SHIPPED 57313463 (Steph "Yes, ship it now").
   CHECK after the weekly (not recorded done): the bound's county estimate
   was ~360 worse (sample range ~270-500), ~150 of them green today
   (~100-250); every bound loss was read (181 routes 140-150 now 150-160).
   TRAP: the bridge REFUSES a --curbs/--sources snapshot missing any of
   curbs_portland, pave_width_portland, road_width_multnomah,
   width_wilsonville: the weekly run must acquire them (or pass --curbs
   /root/fire-curb_sources/2026-10-05), and so must any lane's bound.
   (C) Ask Washington County, Clackamas County and West Linn for their
   pavement widths -- DEFERRED, Steph: "follow up with them later". Also
   published but unused: Oregon City Edge of Pavement (CAD, undated),
   Hillsboro Roadway polygons (mixed with parking lots). Not reachable
   from here: Beaverton, Gresham. Scripts /root/fire-curb_probe/; detail
   in memory project_flats_fire_curb.
