# 149. Pod unit width: 14 ft too narrow for two bedrooms side by side (raised 2026-11-04)

149. [Claude] [Steph] [scan: YES -- toward red if pod56x36 is retired] **Is the 56 x 36 pod (14 ft homes) a real product?**
   Steph 2026-11-04: "I don't know how we settled on 14ft wide. That puts only 1 bedroom width wise. It'd
   need to be at least 20 ft wide to put 2 bedrooms side by side on the South side." Asked: don't change
   anything, thoughts only.
   Origin: flats/config/pods/pod56x36.yaml was carried over from quadfit's footprints.yaml as one of two
   named candidates; no Steph ruling chose 14 ft. pod80x25 (20 ft homes) already meets the 20 ft wish.
   Every lot is screened with both designs and takes whichever fits (flats/designs/model.py catalog;
   flats/ingest/quadfit.py loads every design).
   Offered (not done): (a) count live GREEN/YELLOW lots that pass ONLY with pod56x36 (read-only query on
   the live run) to size what retiring it would cost; (b) whether "bedrooms on the South side" is a hard
   rule (the screen does not know which way a pod faces relative to south -- adding it would be a new
   orientation check and could cut many lots) or a preference; (c) a third design if wanted (e.g. 20 x 30
   or 18 ft homes) -- designs are versioned, adding one is a re-run of the fit stages, not a rebuild.
   Status: waiting on Steph.

## Count (2026-11-04, live run 115, flats.lot_results checks->>colour per design)
- 44,641 lots green with either design. 20,032 are green ONLY with pod56x36: 19,124 would go RED (80x25 red), 908 YELLOW. 22,015 green with both; 2,594 green only with pod80x25.
- Lost by place: Portland 8,540 of 23,073; WashCo uninc 3,356/6,121; Clackamas uninc 2,338/4,931; Beaverton 1,784/2,911; Gresham 1,016/1,994; Oregon City 954/1,622; Tigard 399/720.
- Steph: south-side orientation is theirs to handle, not a screen rule (dropped from (b)).
