# Completeness check, hillsboro (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I answered all three questions for Hillsboro. Nothing was edited and nothing ruled. The main gap: South Hillsboro and Witch Hazel Village South both send "parking courts" to a planned-development (PUD) application, and the config never reads that sentence. I could not count how many of the 168 GREENs that touches.

**Scope.** Only these zones can be GREEN in Hillsboro: R-10, R-8.5, R-7, R-6, R-4.5, MR-1, SCR-LD and SCR-MD. Every other zone is held at REVIEW by the development-review ruling (`hillsboro.yaml#L13-L22`). Findings that only reach those other zones are ranked low.

**What I could not run or read.**
- `flats.encode.crossrefs` did not finish within 5 minutes, moved to the background, and printed nothing. I used the existing `data/flats/crossrefs.csv`, which is the uncommitted working-tree copy.
- I did not re-run `uncited` either; I read the existing `uncited.csv`.
- Writing a scratch script was blocked, so the "within 12 lines" check in B was done by grep over the cited section files, not by script.
- Listing `../vicinitideals-worktrees/` was blocked. I read only `overlay-inventory.findings.md`, not the other findings files or `overlay-inventory-lists/`.

## Ranked findings (most likely to make a GREEN wrong first)

1. **Parking courts need a PUD in South Hillsboro and Witch Hazel Village South — not handled.**
   - South Hillsboro, 12.65.520.G: "Alternative access for residential development, such as court yards and parking courts, may be approved as part of a PUD application" (`cdc.12.65.south-hillsboro.txt#L1055-L1057`).
   - Witch Hazel Village South has the same sentence at 12.68.520.E (`cdc.12.68.witch-hazel-village-south.txt#L610-L612`).
   - The config reads only the alley rule just before each one (`hillsboro.yaml#L643-L647`), and grep finds no "12.65.520" or "parking court" in it.
   - Question: does "alternative access" reach a quadplex? The alley rule before it names only single detached, townhouse and duplex. Witch Hazel Village South is also not mapped.
   - Could make GREEN wrong: **yes**, if read broadly.

2. **Lots at the end of a stub street have no frontage — not encoded.** 12.50.110 D.4: "Property abutting the end of a public or private street not ending in a cul-de-sac, or which may be subject to future extension, shall not be considered as having lot frontage" (`12.50/12.50.110.txt#L35`).
   - This line sits between two lines our values already cite (`#L33,L36`, `hillsboro.yaml#L1271,L3361`).
   - The street-end check already exists (`flats/geom/street_end.py`, used for Gresham), but Hillsboro does not use it.
   - Could make GREEN wrong: **yes**, on a lot whose only street line is a stub end. The "subject to future extension" part cannot be measured.

3. **Planned-development (PUD) overlay boundaries are not held — still open in the overlay inventory.** 12.27.540.C: "development standards of the underlying base zone may be modified or supplemented" (`cdc.12.27.overlay-zones.txt#L1721-L1723`). PUD approvals also carry binding conditions (12.80.120.K, `cdc.12.80.applications.txt#L1530`).
   - Could make GREEN wrong: **can't tell**. It depends on the approved PUDs, most likely in South Hillsboro.

4. **Orenco plan district, 12.62.500.A — not encoded and not mapped.** In the Orenco Station sub-area next to Sunset Downs, lots must be "6,800 square feet minimum and 10,000 square feet maximum". Only townhouse lots and middle-housing land divisions are exempt, so a quadplex on one lot is not (`12.62/12.62.500.txt#L3-L4`).
   - The config's Orenco note covers only SCR-OTC (`hillsboro.yaml#L632-L634`).
   - Could make GREEN wrong: **can't tell** — it reads like a rule for creating lots.

5. **Usable open space, 12.50.210 — open, already recorded as not encoded** (`hillsboro.yaml#L590-L595`). In middle-housing zones a quadplex takes the single-detached standard: "exempt if compliant with Section 12.50.210.D; otherwise 3%" (`12.50/12.50.210.txt#L23-L24`, table that follows).
   - Questions: does MR-1 or SCR-MD count as a middle-housing zone? Does the pod's leftover yard cover 3%?
   - Could make GREEN wrong: **unlikely**.

6. **Downtown 12.61.500 / 12.61.600.A: 10 ft from any line shared with SCC-DT** (`cdc.12.60-61.downtown.txt#L449-L455`). The SCR-MD block holds a 5 ft side setback (`hillsboro.yaml#L2604-L2607`).
   - No GREEN risk today: inside the Downtown Plan District the roof rule already makes the lot RED, and a lot the boundary cuts is kept off GREEN. This only matters if that roof ruling changes.

7. **SCR-DNC front-setback averaging is mislabelled.** The config says "front-yard averaging of 12.61.700.E, a relief" (`hillsboro.yaml#L1816`). The stored section has it at D, and it is stricter: "new construction shall conform to the average setback" where the block's average exceeds the standard by more than 5 ft (`12.61/12.61.700.txt#L9-L10`). The zone table itself says ".E" (`12.21/12.21.850.txt#L76`).
   - No GREEN risk: SCR-DNC is held at REVIEW.

8. **Through lots.** The code makes both streets front lines: a front lot line is any line "separating a lot ... from a street", and double-frontage lots "do not have a rear lot line" (`12.01/12.01.500.txt#L349-L351,L354-L356`).
   - The config has no `front_lot_line_through` value, so the screen falls back to its worst case (`flats/geom/corner.py#L199-L202`). That is a gap in what is written down, not a GREEN risk.

## A. Overlays and plan districts — the rest

- **Encoded or flagged elsewhere:**
  - Floodplain overlay (RFO): the FEMA layer is held. 12.27.110.A.1 adopts the 2018 FEMA study but also "areas identified by the Floodplain Administrator or City Engineer"; that extra part cannot be mapped (low).
  - Significant Natural Resources Overlay: flagged as `hillsboro_snro` (`flats/rules/resource_overlays.py#L165`).
  - Downtown is traced; South Hillsboro is drawn and flagged; AmberGlen is read through the UC zones.
  - SID industrial overlay is an alias (`hillsboro.yaml#L5015`).
- **Cultural Resource Overlay:** read as "protected" (`historic/protection.yaml#L316`), but the list of designated sites is not held — this is already open in the overlay inventory. It reaches only designated structures (`12.27/12.27.320.txt#L9-L11`), so it matters for demolition only.
- **Airport overlay:** "(Reserved)" (`cdc.12.27.overlay-zones.txt#L36`).
- **Plan districts with no residential reach:** Hawthorn Farm and North Hillsboro Industrial are industrial. Witch Hazel Village defers to 12.50 (`cdc.12.67.witch-hazel-village.txt` Table 12.67.030-1).
- **Not overlays:** "Station Community Planning Area" is a Comprehensive Plan designation (`cdc.12.01.general.txt#L1732`). The Orenco Townsite "Conservation District" is SCR-OTC, which is already ruled out.

## B. Cross-references

- The ledger's binding rows for Hillsboro are all settled: 0.4 and 1.00 are misread figures; 15.50.715 is a typo for 12.50.715.
- Unfollowed references inside or beside cited passages: **#2 above** (12.50.110 D.4), and the 12.61.700 averaging in **#7**.
- Image-only targets that no value reads: Figures 12.50.110-A/B/C (how width, depth and frontage are measured on irregular, flag and corner lots) and Figure 12.50.130-C (rear lot line of irregular and flag lots). The definitions send the reader to them (`12.01/12.01.500.txt#L343,L346,L357`). Could change a number: **can't tell**.

## C. Defined words

Whole-code grep over all `cdc.*.txt` and `dcs*.txt`, outside 12.01, for: `for the purpose[s] of this | notwithstanding the definition | shall mean | is defined as | as used in this | for purposes of this`.
- None of these words gets a second definition: corner lot, through lot, lot width, lot depth, front lot line, yard, setback, height, townhouse, middle housing, lot coverage, alley, street, frontage.
- Second definitions found, none reaching a GREEN zone:
  - "floor area" includes garages — cottage clusters only (`cdc.12.50.700-920.design.txt#L296`).
  - "ground level wall area", four versions: `design.txt#L623-L625`, `cdc.12.64.amberglen.txt#L1617`, `cdc.12.65.south-hillsboro.txt#L1630`, `cdc.12.68...txt#L886-L887`. The South Hillsboro one feeds 12.65.850, which is flag-only.
  - "primary structure(s)" — multi-dwelling only (`design.txt#L433`).
  - A corner-lot side yard in Orenco (`cdc.12.62.orenco.txt#L356`) — SCR-OTC only.
- "Driveway" is not defined in 12.01.500 (grep `^Driveway` finds nothing). The Design and Construction Standards section 230.6 governs instead.
- Open questions, low risk:
  - **Story:** a basement counts as a story "if the finished floor level directly above the basement is more than 6 feet above finished grade" (`12.01.500.txt#L559`). On a steep lot that could take the pod past 2.5 stories; I did not check whether the screen allows for it.
  - **Grade:** two measuring points. "Grade, Finished" is the average at the centre of all walls (`12.01.500.txt#L229`); 12.50.140 measures from the centre of the front building plane (`12.50/12.50.140.txt#L9,L13`). This matters little where height is counted in stories.
  - **Corner lots:** the yard is "Interior (Corner Lot). Any yard other than a front yard" (`L701-L702`), and every non-front line is a side line. I did not check whether the screen puts a rear setback on a corner lot.

## For you to check
- How many of the 168 GREENs sit in South Hillsboro, Witch Hazel Village South, the Orenco Station sub-area, or an approved PUD (#1, #3, #4).
- Re-run `flats.encode.crossrefs` yourself; my run did not finish.
- Read the overlay-inventory findings files other than `overlay-inventory.findings.md`, which I could not list.

