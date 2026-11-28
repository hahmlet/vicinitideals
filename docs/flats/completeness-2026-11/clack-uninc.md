# Completeness check, clack-uninc (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I've answered A, B and C for unincorporated Clackamas County. The two ledgers handle the obvious references well, but each has a blind spot, and seven findings could make a GREEN wrong. I edited nothing and decided no rulings. Re-running the two ledgers rewrote `data/flats/crossrefs.csv` and `data/flats/uncited.csv`, so expect them in `git status`.

**What the ledgers already close.** In the fresh crossrefs run, every unincorporated reference that sits near a cited line has an outcome. The only one left open is 1105, marked "later" because it is about land divisions. Ledger-shown items are not repeated below.

**What they cannot see:**
- **Cross-refs ledger:** it only recognises section numbers written in a sentence. It cannot see bare numbers in table cells (Table 1001-1), Comprehensive Plan maps or figures, or outside codes.
- **Glossary:** it reads only chapter 202 (`glossary --layer ... → chapters=1, entries=277`). Definitions written inside other chapters are never captured.

## Ranked by whether it could make a GREEN wrong

**1. Yes — minimum landscaped area and outdoor recreation area are not encoded for the multifamily and mixed-use districts.**
- Table 1009-1 requires landscaping of 25% in HDR, MR-1, MR-2, PMD and VA, 20% in RCHDR and 40% in SHD (`zdo.1009.txt#L48-L58`).
- 1009.08(A): "An outdoor recreational area shall be provided in developments of … quadplexes … in the MR-1, MR-2, and HDR Districts … [and] SCMU". The minimum is "200 square feet … per dwelling unit", or 300 for three-bedroom units (`zdo.1009.txt#L272-L274`). For the pod that is 800–1,200 sq ft.
- Table 1001-1 applies Section 1009 to quadplexes in "all other zoning districts". The config's own note says so (`_unincorporated.yaml#L1716-L1724`).
- Neither value appears anywhere in this layer: a grep for `min_landscaped_pct` and `open_space_min_pct` comes back empty, though ten other layers use them. Nothing in `flats/config/` or FOLLOWUPS mentions 1009-1 or 1009.08.
- The uncited ledger does list these lines, but only as unfielded or unread.
- Question: how many of the 449 GREEN lots are in these districts?

**2. Can't tell (likely yes on steep or designated land) — Table 1001-1 applies more chapters to the building than the ledger knows.**
- For quadplexes in R-5 through R-30, VR-4/5 and VR-5/7, the table names 1002.01, 1002.094, 1003, 1004, 1006, 1007.04 and 1010 (`zdo.1001.txt#L94-L105`). The config admits this (`#L1717-L1719`).
- Yet the "1000" ruling (`#L629-L635`) says the only two sections in it that measure this building are 1012 and 1015.
- None of 1002, 1004, 1006 or 1007 is stored. The 1002.02 note says 1002 was fetched on 2026-11-08 (`#L723`), but no file is held.
- 1004 (Historic Protection) has no row in the ledger at all.
- In the ledger, 1002 has 3 mentions and 1006 has 2, both counted as not binding.
- For quadplexes in all other districts, the table names every one of these chapters (`#L109-L120`).
- Question: fetch 1002 and 1007 first? 1002.01 (hillsides) is where a slope rule would live.

**3. Yes, extent unknown — the Willamette River Greenway (ZDO 705) has no on-the-ground treatment.**
- It is handled only as a density subtraction, as narrows_only (`_unincorporated.yaml#L886-L891`).
- Yet the code speaks of "the required buffer area regulated by Section 705" (`zdo.1012.txt#L111`). Section 705 is not held.
- No `overlays.yaml` key covers it for `clackamas_unincorporated`. Only `clackamas_hca`, `_wqra`, `_landslide*` and `_fmd` exist.
- Section 1011 (open space) partly catches it (`zdo.1011.txt#L5`), but 1011 does not apply to R-district middle housing.

**4. Yes, where designated — the historic overlays (ZDO 707) are stored but never used.**
- ZDO 707 covers Historic Landmarks, Historic Districts and Historic Corridors. A grep of `flats/config`, `flats/rules`, `flats/ingest`, quadfit config and the followups finds no reference to it.
- 707.06(D): new structures in these areas "shall be reviewed as Type II applications". They must be "compatible with … scale, style, height", with location "consistent with … setbacks" (`zdo.707.txt#L302-L306`).
- Questions:
  - Does the Clackamas zoning feed (`zoning_metro`/`ZONE`) carry the HL/HD/HC codes?
  - Does ORS 197A.400 (held) override this discretionary review? That is Steph's call.

**5. Yes, on lots with an alley — the alley-access half of a cited sentence is not encoded.**
- The value `corner_access_street` quotes `845/845.02.txt#L34-L35`. Line 35 says: "For lots abutting an improved alley that complies with Comprehensive Plan Figure 5-1e or 10-SV-6, access shall be taken only from the alley."
- The comment at `#L1439-L1442` quotes only the first half.
- Figure 5-1e is not held, so "improved alley that complies" cannot be judged.

**6. Can't tell — the Regional Center design standards (1005.07) are never mentioned in the config.**
- The config mentions 1005.03–.05, .08, .09, .11 and .12, but never .07.
- 1005.07 says development "shall not be sited such that it precludes the construction of the new walkways" shown on Map X-CRC-7a (`zdo.1005.txt#L460`).
- It also applies the urban design elements of Map X-CRC-3 (`#L420`). Neither map is held.
- It reaches the non-R districts inside the Regional Center area, including RCHDR (29 lots, `#L4212`).

**7. Can't tell — 1003.05, fire hazard.**
- "So that dwellings are not sited in areas subject to extreme fire hazard, such as areas of heavy fuel concentration, draws" (`zdo.1003.txt#L71`).
- The config says it read 1003 whole but handles only 1003.02. 1003.03–.05 are not mentioned. No map is named.

**8. No (no district that allows the building)** — each of these sits only on land where the building is not allowed or is already RED by process:
- 704, River and Stream Conservation Area: named only in TBR (`zdo.406.txt#L519`).
- 714, Special Use Overlay: parks only (`zdo.401.txt#L775`).
- The Barlow Road corridor ban on "structural development" (`zdo.707.txt#L131`): rural, on Map 3-2.
- 1005.10: PMU only, and PMU is RED by process.

**9. Can't tell.** The stored text names special districts 702–707, 709 and 714. No index of Section 700 is stored ("Section 700, Special Districts", `zdo.1102.txt#L55`). So I cannot say whether 708 or 710–713 exist.

## C. Defined words: second definitions not captured
- **Corner lot:** 1005.07(D)(1) says "A corner lot is a lot, parcel, tax lot, or land area created by a lease agreement at the intersection of two streets" (`zdo.1005.txt#L430`). This differs from 202's (`zdo.202.definitions.txt#L277`), which is the only one encoded. Low risk: it only feeds the corner-entrance standard.
- **Private street:** 1005.07(E) refers to "a private street, as defined in Subsection 1005.07(G)" (`zdo.1005.txt#L436-L450`), against 202's definition at `#L587`. Low to medium risk, Regional Center only: front lot lines include private-street boundaries (`#L285`).
- **Height:** 202 hands height to "the State of Oregon Structural Specialty Code or … One and Two Family Dwelling Specialty Code" (`#L103`). Neither code's definition is held. 1005.09 has its own: "measured to top of parapet or roof" (`zdo.1005.txt#L518`). Ruling `2026-11-12-height-measured-per-city` (scope {}) covers this, so low risk.
- **Yard:** 202 has no YARD entry (grep returns 0). Table 315-4 uses "yard depth" (`zdo.315.txt#L1598`), and it is encoded as a side setback. Low risk.
- **Block face** (`zdo.1005.txt#L532`, Fuller Road) and the flood chapter's own definitions (703.05) are local definitions outside the pod's dimensions.
- **Single definition, found in 202 only:**

  | Word | 202 line |
  |---|---|
  | through lot | #L321 |
  | lot width | #L323 |
  | lot depth | #L281 |
  | front lot line | #L285 |
  | setback | #L489-L495 |
  | grade | #L203 |
  | story | #L575 |
  | townhouse | #L615 |
  | middle housing | #L353 |
  | floor area | #L197 |
  | lot coverage | #L279 |
  | driveway | #L165 |
  | alley | #L51 |
  | street / road | #L583, #L469 |
  | street frontage | #L581 |
  | accessory | #L35 |
  | flag lot | #L283 |

  The only other flag-lot definition is "flaglot" in 401 (`zdo.401.txt#L493`), which is EFU only. 903.08 is already cited.

## Not done / for the coordinator to check
- I could not read `../vicinitideals-worktrees/overlay-inventory*`: the sandbox blocks paths outside this repo. Please diff the items above against those files.
- I could not count how many of the 449 GREEN lots fall in each district; I have no database access. That count decides how much findings 1, 2 and 6 matter.
- I did not check items 1–3 against the actual county documents (ZDO 705, 1002, 1004, 1007 and the Comprehensive Plan Chapter 10 maps). Those are fetches.

