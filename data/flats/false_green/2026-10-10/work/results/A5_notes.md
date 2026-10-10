# A5 notes (King City, Sherwood, Durham, Hillsboro, Beaverton)

Result: 12 RIGHT, 2 WRONG (both Hillsboro, KNOWN-53), 0 CANT_TELL.
Code prefix: flats/provenance/docs/or/washington/<city>/.

## King City 2S116AA14200 (R-9) -- RIGHT
Attached housing by right in R-9 (kcc.16.88-16.100.residential-zones.txt). Pod clears lot, setback, height, parking. Unchecked list read; nothing the lot fails. Geometry from picture plausible.

## Sherwood 2S132AB01900 (MDRL), 2S132AB01501 (MDRL), 2S129CC07200 (HDR) -- RIGHT
sdc.16.12.residential.txt: attached/quadplex permitted outright, no review gate; pod clears standards. Any minimum-density flag is a flag by Steph's 2026-10-02 ruling (screen.py ~L2060).

## Durham 2S113CD00500, 2S113CC00700, 2S113CC07800 (SDR) -- RIGHT
ddc.3.site-design.txt (density L4-L7, parking 3.7). Pod clears. On 500 and 700 the dossier ask is `discretionary`, caused by the minimum-density flag only (lot stays green). Interpretive risk for Steph: the code's density language may read as a ceiling rather than a floor; either way it is not a wall.

## Hillsboro 1N234AA01800 (SCR-V) -- WRONG (RED), KNOWN-53
- cdc.12.80.applications.txt L318-L320: "Approval of a Development Review application is required ... 1. New development in any zone excluding the exemptions listed in Subsection D."
- L341: "Middle housing and single detached dwellings in the MR-1, SCR-LD, or SCR-MD zones or any R zone when no Adjustments..." SCR-V is not named.
- L379: "Development Review applications are subject to the Type II procedure" (approval criteria at 12.80.040.H, L427).
- hillsboro.yaml (SCR-V block L2541-L2630) encodes no review gate. Zoning Review (12.80.170) is only for the exempt set.
- Secondary (YELLOW-level, not needed for RED): SCR-V minimum FAR not encoded (0.4/0.5); pod FAR about 0.039. Sibling of the minimum-density flag.
- POLICY: operating building ignored (prop 991, building value $10.37M, sqft not on roll; pod at NW corner in open ground, not on its parking per picture).
- Other standards: quadplex P (cdc.12.24.mixed-use-urban-center-zones.txt, Table 12.24.460-1 L1417-L1760); setbacks 0/5/10; 2-3 storeys; pod passes.

## Hillsboro 1S206AB08000 (SCR-MD) -- RIGHT
- Exempt from Development Review (12.80.030.D.1, L341); Zoning Review (12.80.170) is clear and objective.
- cdc.12.22.multi-dwelling-zones.txt Table 12.22.460-1 (L1017-L1105): quadplex permitted; lot min 7,000 vs 13,296 sf; setbacks 5/5/10; 2-3 storeys vs pod 2; min density 18 du/ac vs 13.1 = flag only (Steph ruling).
- Max front setback 13 ft not read by any screen (HUMAN_TODO 12; flats/geom/corridor.py L65); pod sits at the street end, likely met.
- POLICY: operating building ignored (1950 SFR 1,270 sf; pod placed clear of it per picture).

## Hillsboro 1S204AB02201 (MR-2) -- WRONG (RED), KNOWN-53
- Same quotes as above: 12.80.040.B.1 (L318-L320) requires DR for new development; D.1 exemption (L341) lists MR-1, SCR-LD, SCR-MD or R zones, not MR-2. MR-2 standards at cdc.12.22.multi-dwelling-zones.txt L400-L640.
- No encoded gate in hillsboro.yaml.
- POLICY: operating building ignored (1924 SFR 2,946 sf). Min density 17 du/na is a flag only.

## Beaverton 1S124AD01500 (RMC), 1S121CA06500 (RMC), 1S116DB10900 (RMC), 1S115CD00900 (RMB) -- RIGHT
- Quadplex is P in RMA/RMB/RMC (bdc.20.05.residential.txt L461-L475). Design review for middle housing: bdc.40.21 -- Design Review One is Type 1, Director, standards-based (ministerial). Types 2/3 only if the applicant elects guidelines (optional = by-right).
- FAR/density (bdc.20.25-30.density-height.txt 20.25.05, 20.25.10) pass; parking bdc.60.30.parking.txt L576-L690 passes; design standards 60.05.60.2 S1-S18 are standards-based.
- Height plane 20.30.10: RMC 25 ft at front and rear setback lines rising 1:1 to 35 ft; RMB 25 ft at rear line only. Encoded as step_back (beaverton.yaml L658-L800) and the envelope arithmetic confirms it is applied.
- Slack: 1S124AD01500 56x36 slack 41.5 ft; 1S115CD00900 80x25 slack 66 ft (50 x ~207 ft lot); 1S121CA06500 slack 1.5 ft (envelope 70x73; still a fit, not a miss); 1S116DB10900 slack 30.5 ft.
- POLICY: operating building ignored -- existing SFRs 1955/1,792 sf, 1953/1,192 sf, 1968/1,686 sf, 1997/1,458 sf respectively.

## Patterns
1. Hillsboro Development Review gate is encoded for no zone; SCR-V and MR-2 greens are false (0 of 3 Hillsboro lots right by accident only for SCR-MD).
2. Maximum front setback unread everywhere (known gap).
3. Minimum FAR unencoded in SCR-V.
4. ask=discretionary on green lots comes from the minimum-density path.
5. Geometry came from pictures only (DB and dossiers.jsonl reads were blocked), so court dimensions on narrow lots trust the engine fit.
