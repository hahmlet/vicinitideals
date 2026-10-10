# False-GREEN sample, round 1 -- reading protocol (FOLLOWUPS 64)

Goal: for each sampled lot that is GREEN on the live map (run 70), decide blind
and deeply whether a careful human reader of the city's own code would agree.
This is a READING job. Change no rule, no code, no config, no data. Production
DB: SELECT only.

## What "GREEN" means here
The lot's best design (pod56x36@2 or pod80x25@2) has colour green: it clears
every standard FLATS holds and no open question is big enough to change that.
It is "as if signed" (the verdict field says `unknown / RULE_UNVERIFIED`; that
is normal and NOT a finding). Designs: a 4-unit two-storey townhome pod,
56x36 ft or 80x25 ft footprint, 26 ft tall, 12 ft ground storey, 4 parking
stalls charged (1 per home) in a rear court, drive lane, fire hose route
<= 150 ft from the street. Pod config: flats/config/pods/. Colour rule:
flats/config/colour.yaml.

## Standing rulings (Steph) -- judge by these, do not re-argue them
- BY-RIGHT ONLY. Any discretionary review (design review, conditional use,
  Council master plan, variance, adjustment) on the only path to the pod = RED.
  An OPTIONAL review is by-right. Ministerial staff checks count as by-right.
- No variances. A confirmed miss of a standard = RED. A fit miss of 1 ft or
  more = RED.
- Four stalls (one per home) is enough; zero-required zones need none.
- A stated number governs unless the code states an EXPRESS exception; a table
  that states no minimum sets none; definitions are literal.
- Post-January-2027 world (HB 2138) is assumed.
- Corner lot with more than one street: parking entrance on the SIDE street.
  A lot on ONE street whose frontage bends is NOT a corner where the code is
  silent. Private roads count as a way in for parking.
- Partial alley: waives only the stretch it covers.
- Institutional land (schools, hospitals, municipal, parks, utilities, rail,
  airports, malls) = RED. Churches and charities stay checked. HOA tracts,
  common areas, open space, golf courses, zero-value parcels with no address =
  RED. A zero-value parcel WITH a real street address is screened normally.
- Height: each city's own measuring rule. A gable is measured differently in
  different cities (FOLLOWUPS 62): the pod's 26 ft is compared to caps as one
  height. Note where a cap sits between ~22 and ~30 ft.
- Unmeasured facts are conservative (worse case) by design; that is not a
  false GREEN.

## KNOWN problem kinds (tag a WRONG as KNOWN-<n> if it is one of these in a new
place; otherwise NEW). Also read the FOLLOWUPS item (docs/FOLLOWUPS.md) first.
- KNOWN-59 tract / zero-value / public code shown green
- KNOWN-63 one street's bend or sliver read as a corner (or a corner read as
  one street); KNOWN-60 unranked corner street
- KNOWN-41 street class / quiet street / which street takes the drive
- KNOWN-47 institutional land (map overlap) missed
- KNOWN-53 by-right-only: a review-only zone shown green
- KNOWN-29/44 fire hose route / curb start
- KNOWN-38/49 slope; KNOWN-42/50 water, wetland, flood; KNOWN-43/40 utility
  easement
- KNOWN-61 compass-direction setbacks (Clackamas ZDO 1005.02(L): SHD, RCHDR,
  VTH, HDR building separation) not yet encoded
- KNOWN-62 roof shape / height measurement
- KNOWN-2 neighbour zoning per lot line; KNOWN-3/33 alley, court off lot
Anything else = NEW. Name a NEW kind in a short noun phrase.

## What to read, per lot
Files (absolute prefix: the repo worktree
C:\Users\Steph\Repos\vicinitideals\.claude\worktrees\bridge-cse_01YBExj1xnP7Y8uCSBVqa6HW,
git-bash form /c/Users/Steph/Repos/vicinitideals/.claude/worktrees/bridge-cse_01YBExj1xnP7Y8uCSBVqa6HW):
- data/flats/false_green/2026-10-10/work/lots/<slug>.json   dossier (facts,
  per-design results, margins, unchecked list, flags, neighbour summary, lot ring
  in EPSG:2913 feet)
- data/flats/false_green/2026-10-10/work/pics/<slug>.png    picture: lot (black),
  neighbours (grey, zone + address), the green design's envelope (dashed),
  building (red), court (purple), lane (blue), hose room (orange). VIEW IT with
  the Read tool.
- flats/provenance/docs/or/<county>/<city>/*.txt   the STORED CODE TEXT. This
  is "the zone's own words". Read it, not our YAML layer
  (flats/config/jurisdictions/...), which may be wrong -- that is what is being
  tested. You may open the layer only to learn WHICH stored file and lines our
  encoding cites, then read those lines yourself AND the surrounding words.
  grep the whole city folder before claiming something is absent.

For each lot, in this order, write down evidence:
1. USE. Is a 4-unit attached townhome (rowhouse / attached houses / townhouse /
   fourplex / multi-dwelling -- use the city's own term and definition) allowed
   BY RIGHT in this zone on this lot? Any review / conditional / lot-size gate /
   overlay / plan-district / master-plan requirement? Does the zone letter in
   the dossier match the real zone (a split zone, overlay, plan district)?
2. LOT. Min lot area, min/avg width, frontage, depth, density (min AND max),
   for attached housing specifically (attached lots are often sized differently
   from detached). Compare each to the real lot (area_sqft, frontage_ft,
   lot_width_ft, lot_depth_ft, the ring, the picture).
3. BUILDING. Setbacks (front/side/rear/street-side/alley, garage), max height
   AND how the city measures it, coverage, FAR, stories, floor-area ratios,
   open space, landscaping, building length / separation, any attached-housing
   or townhouse standard.
4. PARKING & ACCESS. Required / max stalls, stall + aisle geometry, driveway
   width / spacing / approach limits, shared access, which street the drive may
   use, alley rules, fire access (150 ft hose route, turnaround).
5. GEOMETRY. Look at the picture. Does the pod + court + lane plainly fit
   inside the lot and inside the envelope? Is the "front" street right? Is the
   lot a flag lot, sliver, odd shape, corner, through lot, cul-de-sac, on a
   private drive? Is the drawn lane/court reachable from a street?
6. LAND. Slope (facts.slope), flood/floodway, wetlands, steep ground,
   overlays (facts.observed.*, has_z_overlay, constrained_sites_overlay).
7. WHO/WHAT. assessor prop_code / land_use / values (facts.assessor), tract?
   zero value? public or institutional? condo? existing big building? split
   zone?
8. UNCHECKED. checks.unchecked lists standards the screen did NOT test. For each
   one, search the code: does it actually carry a number that this lot or pod
   could fail? An unchecked standard that the code really holds and the lot
   fails is a false GREEN.
9. FLAGS. checks.flags / flags in dossier: open items riding along below the
   line. Are any of them big enough to change the colour in your judgement?

Verbs: RIGHT = green stands; WRONG = a careful reader would say YELLOW or RED
(give which, and the standard and the numbers); CAN'T TELL = the answer turns
on a fact you cannot get (say exactly what is missing and which way it likely
falls). Do not hedge into CAN'T TELL when the stored words decide it.
Be sceptical: the aim is to FIND false greens, not to confirm. But do not
invent problems: every WRONG needs the code quote (file:line + words) and the
lot number it is compared with. Check your arithmetic and your units.

## Output (write these files; do NOT commit, do NOT push, do NOT edit anything else)
1. data/flats/false_green/2026-10-10/work/results/<GROUP>.csv   header:
   tlid,city,zone,ruling,reason,kind
   ruling = RIGHT | WRONG | CANT_TELL. reason = one sentence of plain English with
   the decisive numbers + code cite (file:line). kind = for WRONG: NEW:<short
   name> or KNOWN-<n>:<short name>; for others leave empty. CSV-quote fields.
   TLIDs contain internal spaces (e.g. "1N2E20DC  -00100"): copy exactly, never
   split on whitespace.
2. data/flats/false_green/2026-10-10/work/results/<GROUP>_notes.md   one section
   per lot: the evidence you wrote down for steps 1-9 (short), the quotes with
   file:line, the numbers. Enough that someone can check you without redoing it.
3. IMMEDIATELY when you decide a lot is WRONG (do not wait for the end), append
   one line to data/flats/false_green/2026-10-10/work/results/ALERTS.txt:
   `<GROUP>|<tlid>|<city>|<YELLOW or RED>|<one-line reason with the numbers>`
   (use `echo '...' >> file`; one line per lot).
4. Final reply to the coordinator (under 250 words): counts RIGHT / WRONG /
   CANT_TELL, the WRONG lots with one-line reasons, patterns you noticed across
   lots (a standard checked by nobody, a zone read wrong, etc.).

Read-only DB (SELECT only) if you need more facts:
ssh -o BatchMode=yes root@192.168.1.28 "cd /root/stacks/vicinitideals && docker compose exec -T postgres psql -U re_modeling -d re_modeling -Atc '<SELECT ...>'"
Never write production data, never deploy, never touch LXC 137, never run git
commands that change state.
