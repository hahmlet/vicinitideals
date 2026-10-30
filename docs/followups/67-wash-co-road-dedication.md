# 67. Washington County makes the owner hand over road land first (CDC 302-2.14 C(1), 303-306, 307-2.13, 375, 390).

67. [Claude] [READ at run 78 2026-10-20: moves at the bound; only (b) open] [MERGED to main (d3b6db52, a212b7f5, cities 7cbc3346 = item 77), rides the weekly ~2026-10-19]
   **Washington County makes the owner hand over road land first (CDC 302-2.14 C(1), 303-306,
   307-2.13, 375, 390).** 25/30/37/45 ft to centre line (local / neighbourhood route /
   collector / arterial), measured per street lot line from Metro's centreline (a stub with no
   street beside it reads the nearest centreline, OSM included, which can only be nearer); the
   shortfall comes off the envelope like a setback; unmeasured = whole distance; unranked class
   = 45 ft; private roads (RLIS 1700/1800) take nothing. Steph RULED 2026-10-14 "YES" (register
   `2026-10-14-road-dedication`; an unranked street is taken at its worst case).
   Coordinator rulings 2026-10-14 (on "never a false green" / "unranked = worst case"): (a) an
   unranked street keeps the worst case; (a2) a corner piece on two streets BOTH read with a
   class on the lot takes the deeper of the two (d3b6db52, test at real coordinates); a piece
   with any street unread stays worst case; a212b7f5: a short piece whose own class reading
   fails (corner cut-off, curve) and whose ONE street is read with a class on another line of
   the same lot takes that class; no name, two names, or a name read nowhere else stay worst case.
   NOT ADOPTED 2026-10-11, with reasons: OPTION C (unmapped street = local): the county TSP
   (Effective Sept 24, 2026, PDF p. 8 and 33-35) says "New Local Streets that are not in this
   plan may be established via the land development process" and "other neighborhood routes may
   be designated through the development review process" -- so an unmapped street can be a
   neighbourhood route (30 ft) as easily as a local one. NARROWER READING (30 ft for a street
   absent from the county's classified layer): FAILS -- layer 4 (street_class_washington) is not
   a complete list of collector-class streets (vs RLIS type 1400 89.9%: missing Bankston ~2,294
   ft, Grabhorn ~207 ft, Glencoe ~50 ft; type 1450 97%: missing Roy ~1,609 ft); layer 8 "Special
   Area Streets" holds Special Area Commercial Streets (37 ft) that layer 4 covers only 6-9%. A
   30 ft ceiling would need layer 8 as a dataset plus "stays 45" exceptions; not built.
   Option A stands.
   EXPECTED at the weekly (FINAL bound vs run 74 on the 3,693 moved lots, best design per lot,
   green->red / green->yellow / yellow->red / yellow->green): WashCo uninc 1,178 / 83 / 603 / 31
   (+2 red->yellow), Oregon City 713 / 56 / 228 / 19, Sherwood 20 / 0 / 30 / 2, Milwaukie 17 /
   18 / 57 / 6, King City 0/0/3/0; total 1,928 / 157 / 921 / 58. Greens in scope 10,402 -> about
   8,375. Ten lots end GREENER than run 74 by a placement-search artefact (item 57's kind), all
   read: 1S114DA00701 1S112CC03400 22E28CA00702 1N225AB20000 1S103DB01800 22E32CC03100
   1S110BB07900 2S132DA05500 1N128DA02000 22E27BC01900. Bound base
   /root/bridge_spliced_2026-10-14_demw (proven valid).
   OPEN: (b) lots whose tax lot includes the roadway (lot line under ~12 ft from centre line)
   understate the road and are left at worst case (63 lost, 73 kept green). (The Fitter
   cache-key bug, item 74, is fixed 8bda9817.)
