# Completeness check, beaverton (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I answered all three questions for Beaverton. There are four new gaps that could make a GREEN wrong, and several more where I can't tell without code text we don't hold. I edited nothing and made no rulings.

**What I didn't get to, and what you need to check:**
- **Old overlay findings not read.** The sandbox blocked `../vicinitideals-worktrees/` (the `overlay-inventory*.findings.md` files). I used the summary in `docs/followups/204-overlay-inventory.md` instead, so something marked "handled" in those findings may show up again below.
- **The ±12-line sweep was partial.** Ad-hoc `python -c` needed approval and writing scratch files was blocked. I hand-grepped the cited residential, Cooper Mountain, parking, EDM and Chapter 90 files; the Downtown (Ch. 70) and commercial windows got only a light pass.
- **Ledgers.** I ran `flats.encode.crossrefs`; it regenerated `data/flats/crossrefs.csv` (115 Beaverton rows, same as before). I did not rerun `uncited` because `uncited.csv` had already been regenerated earlier tonight; I read that copy.
- **Which zones the 322 GREENs are in: not checked.** I had no lot query. Count how many sit in CM-RM, in the South Cooper Mountain plan area, and in MR/commercial/mixed-use zones where a parking-lot driveway rule would apply. That decides how much A1–A4 matter.

## A. Overlays and special areas, ranked by risk to a GREEN

BDC 10.32 names three overlays: Historic (HO), Resource (RO) and Cooper Mountain Parks (CMPO) (`10/10.32.txt#L7-L10`). The config lists all three as NOT ENCODED (`beaverton.yaml#L633-L635`). HO is otherwise handled through `historic/protection.yaml#L143-L160`. What's left:

1. **Could make a GREEN wrong: yes. EDM 210.21.I is unread and missing from both ledgers.** "Parking lot driveways shall be located not closer than ten (10) feet to a side lot line" and "no parking stalls within 20 feet of the street right-of-way" (`edm.210.21.driveways.txt#L88-L92`). Nothing in the config, `driveway_lot_line.yaml` or `uncited.csv` covers it.
   - Question: is the pod's drive a "parking lot driveway"? In RMA, RMB, RMC and CM-RM, rule S12 lets driveways sit 3 or 6 ft from property lines "Notwithstanding the corner clearance" — does that also displace I.2?
2. **Yes. Cooper Mountain 15% open space (S8) is not encoded for CM-RM.** "sites shall provide at least 15 percent open space per gross site area at the time of Initial Development … in addition to the standards of Section 60.05.60.2.S4 through S6" (`60.05/60.05.60.txt#L298-L300`). CM-RM encodes only the S4 square-foot bands (`beaverton.yaml#L1602-L1626`). The uncited ledger lists the line as unread but nobody has decided anything on it.
   - Question: does a quadplex on an existing lot count as "Initial Development" (definition at `bdc.90.definitions.txt#L1268-L1276`)?
3. **Yes. South Cooper Mountain open area (S7) is not handled and not in the uncited ledger.** The outdoor open area must equal the Significant Natural Resource Area square footage on the site if that is larger than S4, plus a PB-10 buffer along SW Tile Flat Road (`60.05/60.05.60.txt#L257-L281`). The commercial and mixed-use version is at `bdc.60.05.design-review-standards.txt#L1539-L1558`.
   - The plan area is not defined in Chapter 90 (no heading matches "South Cooper Mountain" or "Cooper Mountain Community Plan"), and no boundary layer is held.
4. **Yes. Cooper Mountain access ban on Neighborhood Routes is not encoded.** West of SW 175th, "Vehicular access is not allowed between intersections if the distance between intersections is 350 feet or less" (`bdc.60.55.transportation.txt#L470-L478`). It's in the uncited ledger as unfielded; `driveway_spacing.yaml` has nothing on it.
5. **Can't tell. Resource Overlay (RO).** "Properties that contain the Resource Overlay shall be subject to the rules in Section 60.37" (`20.22/20.22.25.txt#L5-L6`). We don't hold 60.37 (crossref row 60.37, 10 mentions).
6. **Yes if the lot is in the Parks Overlay. CMPO.** "required open space shall first be placed inside the Parks Overlay" at Initial Development (`20.22/20.22.45.txt#L28-L29`). That could take the building site. Not encoded.
7. **Can't tell. Significant Natural Resource Areas (SNRAs, citywide).** They are not in the 10.32 overlay list, so the config's NOT ENCODED note doesn't cover them. They carry the same 25% / 15% tree-DBH preservation rule as groves (`bdc.60.60.trees-and-vegetation.txt#L54-L62`), and 60.67 is not held. Grove lots get the `FACT-BEAVERTON-SIGNIFICANT-GROVE` flag (`flags.yaml#L2685`); SNRA lots get nothing (no SNRA match in config or rules for Beaverton).
   - Question: should SNRAs get the same flag as groves?
8. **Can't tell. Floodplain rules (60.10) are not held.** The `fema_sfha` permit in `flats/rules/resource_overlays.py#L295-L299` cites other cities' rules, not Beaverton's.
9. **Can't tell. EDM Standard Drawings are not held.** Driveway width for four or more units is "as shown in the Standard Drawings" (`edm.210.21.driveways.txt#L60-L71`).
10. **No. Downtown Historic Overlay new-construction rules.** 70.20.10.11 applies to facades within 20 ft of seven named buildings (`70.20/70.20.10.txt#L808-L810`). It's design only, such as columns 25–35 ft apart.

## B. Cross-references

- The ledger uses a 12-line window (`flats/encode/crossrefs.py#L112`), the same as the brief. Every binding Beaverton row already has an outcome; nothing numbered is left open.
- Unnumbered references the ledger can't see, inside cited windows: the EDM drawings and I.2/I.3 (A1, A9). Also the sight-clearance note on corner lots (`20.05/20.05.15.txt#L278`, `20.22/20.22.15.txt#L162`), which is already tracked as follow-up 161.
- The public utility easement sentence (`20.05.15.txt#L282`) is already handled in `easements.yaml#L33-L37`.
- Numbered targets that matter and aren't held: 60.37 (A5), 60.10 (A8), 60.67 (A7), and 60.61.30/35 (Cooper Mountain tree specs, which feed S8's canopy option).

## C. Defined words

Definitions the config captures: corner lot L1412, front lot line L1420-L1426, street L2484, frontage L1095, through lot L2618, yards L2895-L2917, net acreage L41-L53, attached dwelling and quadplex L728 / L790 (all in `bdc.90.definitions.txt`). I grepped every stored document for "for the purposes of", "shall mean", "is defined as" and "means".

1. **Possible text loss: lot depth.** The stored definition is incomplete: "Lot, Depth. The perpendicular distance measured from the mid-point of the opposite, usually the rear, lot line" (`bdc.90#L1416`); the front-line half is missing. It feeds the 100 ft minimum depth (`beaverton.yaml#L2122-L2125`). Compare against the PDF.
2. **Can't tell: lot-line rules the config doesn't declare.** The flag-lot front line excludes the pole (`bdc.90#L1422-L1424`), and irregular lots get a 10-ft rear line (L1428-L1430). I couldn't confirm the geometry follows these. The through-lot rule (L1424) isn't declared either, but an undeclared value is screened at the worst reading (`fields.py#L2511-L2513`), so it carries no risk.
3. **Local definitions that tighten nothing:**
   - "Adjacent" (within 10 ft of a street line) in `60.05/60.05.60.txt#L51,L75`, versus "Near or close" at `bdc.90#L60`. It only matters for entrance alternatives the pod doesn't use.
   - "Site" as the area the application affects (`bdc.60.05#L850-L858`). It only relaxes.
   - "New residential development" (`bdc.20.25-30#L14-L17`). Consistent with treating minimum density as a hard floor.
4. **Two "grade" definitions.** Grade uses a 5 ft band (L1127-L1129); grade plane uses 6 ft (L1135-L1138). Height uses grade plane (L335) and story uses grade (L2470). There is no second height measurement anywhere in the code.
5. **Not defined anywhere:** "parking lot driveway" (A1), the two Cooper Mountain plan areas (A3), and "common driveway" (Steph already decided this on 2026-10-02). Building coverage is defined (L560), but no zone table has a coverage limit.

