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

## Sizing study plan (Steph 2026-11-04: one-time, find the settled size, 500 sq ft/floor; target ~Mon 11-09)
- Sizes 14..20 ft by 1 ft, depth = 500/width (15x33, 16x31, 17x29, 18x28, 19x26 new; 14x36, 20x25 exist).
- Prep (Thu-Fri): fit-only curve from the stored width/depth frontier (minutes); 5 design files on a study branch (never the live map); audit code for two-design assumptions (e.g. flats/encode/height.py latest("pod56x36")); 1-2k-lot sample x 7 designs on 137 to measure time + memory (OOM trap); results stay on 137 as parquet + a per-width report, not loaded into the 114 DB; supervisor with resume.
- 137 at 11-05 07:15Z: th_row3 done; queue durham_apron2, hv_cap2 (38k), pd2c, pdx_map_120c (28k), max_front (44k), fire_rp4, min_far, hb_active, stall_w (317k, 20-30 h) -> free ~Sat 11-07/Sun 11-08. Disk 22G free.
- [Steph] OPEN: the two-week full re-screen is also due ~Mon 11-10. Separate runs (re-screen ~14 h then study ~1.5-2.5 days, results ~Thu) or one combined run (study sizes ride the re-screen, only the two current sizes go on the map; ~1 day sooner, a failure in the extras could delay the map refresh)?
- Scope (Steph asked: only greens? 2026-11-05; from 137 /root/assign_pd2ab/lots.parquet): 429,390 lots red under BOTH sizes; 241,702 of them red only on size-sensitive checks (fit, open space, coverage, landscaping, FAR, parking/driveway shares, fire reach, steep ground) with no size-blind reason (lot area/width/frontage, density, height, roof, institutional, historic, county roll, sliver); 111,896 fail on fit alone; 59,388 within 15 ft of fitting. ~158.5k lots are not red/red (all greens + yellows). Proposed study scope: every non-red/red lot + the reds the fit-only frontier check says can physically hold at least one new size (exact, replaces the 15 ft guess) -- roughly 35-45% of the county instead of all of it.
- Steph 11-05: narrow the red pool for the study; after settling, retire most/all other sizes. Asked whether we have enough data now. Coordinator view: parking layout is the lever that can change the winner (fit_ft is the top red reason, 319k red/red lots; ~108k fail only on the court behind, run 49). 146 (lane/court in the side yard, GO after overlays) favours wide-shallow sizes on narrow lots; 92 (layout generator, PARKED by Steph) could favour any. Also: data covers metro counties only (all-Oregon market); 4 homes x 2 storeys fixed. [Steph] OPEN: study Monday on today's parking (re-check top 2-3 sizes after 146), or build 146 first and run the study after (~1 week later).
