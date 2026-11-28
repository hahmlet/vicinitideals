# 222. "Do we have everything?" -- 9-place completeness check, 2026-11-27 (item 217 tier 2)

222. [Claude] [Steph: questions marked S] [scan: YES -- several likely false GREENs]
   Nine API-credit workers (Opus 5.5, $31.0 total) asked Steph's three questions per place
   (overlay not read / cross-reference not followed / defined word with a second
   definition), most greens first. Full reports, unverified, in
   [docs/flats/completeness-2026-11/](../flats/completeness-2026-11/). Limits common to all:
   no DB (no GREEN counts per finding), could not read
   ../vicinitideals-worktrees/overlay-inventory*.findings.md (sandbox) -- diff A-items
   against item 204 before acting. Ledger blind spots they found: crossrefs misses a
   section number wrapped to the next line (Gresham 4.0130 -> 9.0100), table cells,
   standards with no section number, and standards in held-but-uncited text (West Linn
   38.030); glossary reads only the main definitions chapter.

   OWNER (Steph 2026-11-27): the FLATS Primary Development Agent triages this list first
   (already on the waitlist? partly done?) and either fixes or asks Steph. Three credit
   build workers started before that (milwaukie-vegetation, clack-1009,
   gresham-far-buffer, worktrees credit-*); the other four are HELD
   (data/flats/credit/HOLD).
   11-28: the three FINISHED, unmerged, local branches, HANDOFF.md in each worktree:
   flats/credit-milwaukie-vegetation ffc40693, flats/credit-clack-1009 ddc27b7b,
   flats/credit-gresham-far-buffer 24d74e92 (its 3 gate failures came on a memory-starved
   run -- re-run). Held jobs have empty worktrees, no commits.

   **Likely false GREEN, text held -> tier-3 build jobs (item 217):**
   - Milwaukie R-MD/R-HD minimum vegetation 15-30% (Table 19.301.4 row 5, 19.302.4) +
     40% front yard (19.301.5.C) not encoded. -> t3-milwaukie-vegetation
   - Clackamas uninc. Table 1009-1 landscaping 20-40% (HDR, MR-1/2, PMD, VA, RCHDR, SHD) +
     1009.08 outdoor recreation 200-300 sq ft/unit not encoded. -> t3-clack-1009
   - Gresham FAR row J (1.0/0.7/1.0) missing in LDR-5/LDR-7/TR; lot-of-record relief
     voids the "min lot size makes FAR moot" note; 9.0100 buffers mis-filed as fences
     (not held -- fetch). -> t3-gresham-far-buffer
   - Oregon City Thimble Creek: R-5 40 ft setback from the plan area's south edge
     (17.10.070) and MUC-2 residential upper-storey only (17.29.080.E); boundary geojson
     held but unused; header cites a non-existent 17.16.155. -> t3-oregon-city-thimble
   - Hillsboro 12.50.110 D.4: a lot on a stub street end has no frontage; street_end
     check exists (Gresham) but not wired for Hillsboro. -> t3-hillsboro-stub
   - West Linn CDC 38.030: wall >= 25 ft + zone yard from the centreline of a street
     whose required width < 50 ft; stored #L25 may be truncated. -> t3-west-linn-38030
   - Beaverton South/Cooper Mountain: CM-RM 15% open space (60.05.60 S8) not encoded;
     EDM 210.21.I parking-lot driveway 10 ft from side line (S: is the pod drive a
     "parking lot driveway"?). -> t3-beaverton-cm

   **Needs Steph (S) or a count first:**
   - S Portland visitability 33.110.265.E.3 (one step-free unit for 3-4plexes, adjustments
     prohibited) unencoded; deleted 2027-01-01 by Ord. 192241. Moot in 35 days?
   - Portland York plan district (33.597) EX nonresidential-use requirement, never read;
     5 more plan districts (PV, SI, PR, GS, CP) missing from the read/pending list;
     Cascade Station bans Household Living until 2027-01-01. Count GREENs inside first.
   - Portland 33.110.260 narrow lots (< 32 ft): height cap 1.5 x facade width, 60%
     landscaped front; triage note says "lot history" -- text applies by width. Count.
   - S Oregon City 17.04.1000: on a corner lot the director picks the rear line; screen
     always takes the line opposite the front. Flag, or screen both ways?
   - S Oregon City South End 17.22.050.A front porch (80 sq ft, 6 ft) within 20 ft of the
     sidewalk; pod has none -- does the 2026-11-08 no-porch ruling make these red?
   - S Milwaukie "street" includes alley (19.201): is a rear-alley lot a through lot, and
     is rear-court parking off an alley banned by 19.505.3.D.4.a?
   - S Hillsboro South Hillsboro 12.65.520.G / Witch Hazel South 12.68.520.E: "parking
     courts may be approved as part of a PUD" -- does that reach a quadplex?
   - Washington uninc. 501-8.1 E 9-10 ft pedestrian/utility easement on Special Area
     streets moves the yard line (302-7); does 431-4 A exclude middle housing?
   - Clackamas uninc. 845.02 alley-only access half of a cited sentence unencoded;
     ZDO 707 historic overlays held, never used; ZDO 705 greenway only as density.
   - Gresham / Oregon City: "1996 flood" inundation area beyond FEMA (Metro FLOOD96?).
   - Not held, fetch: Gresham Art. 5 (5.0100 flood, 5.0200 hillside, 5.0700 NRO) + 9.0100;
     Clackamas ZDO 1002/1004/1006/1007 (Table 1001-1 applies them to quadplexes) + 705;
     Washington CDC 410/421/422/380/379; Beaverton 60.10/60.37/60.67 + EDM drawings;
     Milwaukie 19.700 (no crossrefs row at all -- why?), Title 18, 16.32; West Linn
     Ch. 27/32, TSP Exhibits 6-9; Portland PCC 17.28.110, 33.400/405/410/440/465/475.

   **Green check (217 last tier, $7.06): 30 live greens, run 134, seed 68, round-5 lots
   excluded -- 23 RIGHT / 0 WRONG / 7 CAN'T TELL** (reports greens-g1..g3.md in the folder
   above). Can't-tells: 5 Portland corners -> item 223 (court vs side-street building line);
   Portland CM2/CE corners on the unencoded 33.130.215.B.1.b driveway-through-setback bar
   (portland.yaml#L6176, #L6898); Oregon City R-2 rear setback for a quadplex
   (oregon-city.yaml#L2043-L2048). Also: two FIT-TIGHT greens seat 0 stalls (1S102CD01000,
   1S127BB00100) -- no parking required there, but check that "green with no stall drawn" is
   intended; Portland visitability raised again (S question above).

   **Text bugs, low risk (fix with the next touch):** Washington words.py cards quote the
   wrong 106 entries (street, building height; townhouse/multifamily/grade shown silent);
   Beaverton lot-depth definition truncated (bdc.90#L1416); Hillsboro 12.61.700.E vs D
   label; West Linn stale clear-vision and private_drives notes; Gresham stale
   clear-vision note; Washington 430-84#L392 cites 501-8.2 B (means 8.5 B).
