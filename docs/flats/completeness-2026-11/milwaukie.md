# Completeness check, milwaukie (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I answered all three questions for Milwaukie. The most serious finding is not an overlay: both residential zones have a **minimum vegetation standard that the config never encodes**, and it is the one thing I found most likely to make a current GREEN wrong. Below are only the gaps the existing ledgers and config miss. Every finding has its evidence and the question it leaves. Paths are under `flats/provenance/docs/or/clackamas/milwaukie/` unless written in full.

## Ranked: could make a GREEN wrong

1. **YES (likely): minimum vegetation is not encoded for R-MD or R-HD.**
   - Table 19.301.4 row 5, "Minimum vegetation (percent of total lot area)", reads 15% / 25% / 25% / 30% across the four lot-size bands (`19.301/19.301.4.txt#L163-L169`). R-HD prints 15% (`19.302/19.302.4.txt#L42`).
   - 19.301.5.C adds "At least 40% of the front yard shall be vegetated" (`19.301/19.301.5.txt#L48`). 19.504.5 caps mulch at 20% of that area.
   - The config's R-MD and R-HD blocks have no `min_landscaped_pct` field (field list at `milwaukie.yaml#L1489-L1934`). A grep of the config and footnotes for "minimum vegetation", "19.301.5.C" and "front yard minimum" finds nothing. The uncited ledger has no row for it either, probably because a percentage is not a measured line.
   - `flats/rules/fields.py#L1823-L1830` says this field "binds the same way a coverage cap does -- it is lot area the pod and its parking may not have". The field is used for NMU, GMU and SMU (`milwaukie.yaml#L2437,L2553,L2646`), so the engine already supports it.
   - Questions: does 30% vegetation, plus the coverage cap, plus a parking court still fit on the smaller GREEN lots? Does the front-yard 40% conflict with driveway width on a narrow lot?

2. **CAN'T TELL: Chapter 19.700 (Public Facility Improvements) is not held, and the crossrefs ledger has no row for it at all** (grep count = 0).
   - The residential sections point at it: "Transportation requirements and public facility improvements are required as specified in Chapter 19.700" (`19.301/19.301.5.txt#L80`, `19.302/19.302.5.txt#L111`). Right-of-way dedication is also referenced at `19.202/19.202.4.txt#L49,L84`.
   - The config admits it is unheld (`milwaukie.yaml#L981-L983`) but takes the dedication strip only on the streets in Table 19.501.2.A: "A street the table leaves out takes none."
   - Question: does 19.700 require dedication or half-street improvements on substandard local streets? If so, lot area and the front line move on lots the screen treats as untouched. A second question: why does the ledger not list 19.700? Possibly its prefix matching treats it as held. I did not trace the cause.

3. **CAN'T TELL: the code's "street" includes alleys, which affects the parking ban and through lots.**
   - "Street" … "includes the terms 'road,' … 'alley'" (`19/19.201.txt#L740`; same wording in `12.16/12.16.010.txt#L28` and `12.24/12.24.020.txt#L14`).
   - "Through lot" means "an interior lot having frontage on 2 streets" (`19/19.201.txt#L381`).
   - The plex parking ban, 19.505.3.D.4.a, has no alley carve-out: parking shall not be "directly between the façade of a primary building(s) and an abutting street right-of-way" (`19.505/19.505.3.txt#L161`). The cottage rule shows the code knows how to exempt alleys: "except alley property lines" (`19.505/19.505.4.txt#L423`).
   - By contrast, "Corner lot" and "Front lot line" both exclude alleys explicitly (`19/19.201.txt#L365,L257`).
   - Question: is a lot with a rear alley read as a through lot? Is rear-court parking off an alley banned under `parking_front_prohibited` (`milwaukie.yaml#L1140-L1146`)? This is a ruling for Steph.

4. **CAN'T TELL (low): the Aircraft Landing Facility zone (L-F) is not handled at all.**
   - It is a mapped overlay in Table 19.107.1 (`19.100.introductory-provisions.txt#L134`). "The height of any structure … shall be limited according to requirements established by the Planning Commission or by other appropriate authorities" (`19.400.overlays.txt#~L3035-L3037`, §19.405.2.A).
   - The config, flags and footnotes have no L-F entry (grep of `flats/` outside provenance finds only an unincorporated-Clackamas footnote).
   - Question: is any L-F area actually mapped in `zoning_milwaukie`? If so, the height limit is unknown there.

5. **CAN'T TELL (low): Title 18 (Flood Hazard) is not held.**
   - Named at `19.400.overlays.txt#L470` and `19.200.definitions.txt#L17` ("Refer to Title 18 for definitions related to flood hazard areas").
   - Floodplain is subtracted from the density area (`milwaukie.yaml#L1743`), but the `FACT-IN-FLOODPLAIN` flag is `status: pending` (`flats/config/flags.yaml#L1955-L1966`). Title 18's own development standards (elevation, floodway prohibition) are unread.
   - Question: can a GREEN lot touch the FEMA 100-year flood area?

6. **CAN'T TELL (low): Chapter 16.32 (Tree Code) is not held.**
   - The crossrefs ledger lists it (15 mentions, binding 0, no outcome). The residential-facing mentions are only via 19.402 and 19.606 (`19.606/19.606.2.txt#L33`), and the config says 19.606's scope excludes middle housing.
   - Question: does 16.32 have its own tree-preservation or canopy standard for residential development? The held text cannot say.

7. **PROBABLY NO: Title 17 (Land Division) is not held.**
   - "Creation of new lots or parcels as part of a townhouse development is subject to the applicable land division process in Title 17" (`19.505/19.505.5.txt#L30`).
   - It affects only the `unit_lots` variants, not the quadplex on one lot.

8. **PROBABLY NO: the Planned Development zone (PD, §19.311) has no `zones:` entry** (zone keys at `milwaukie.yaml#L1490-L2600`).
   - For the coordinator: confirm that an unencoded zone can never come out GREEN.

## A. Overlays: what is handled (for completeness, no action)

- **Willamette Greenway (WG):** handled. Variants at `milwaukie.yaml#L1500-L1521` and `#L1795-L1816`, the 19.401.3 card at `#L466`, and the flag at `flags.yaml#L2515`.
- **Natural Resources (NR, WQR/HCA):** handled by the screening layer and the density subtraction (`milwaukie.yaml#L484-L499,L1743`).
- **Historic Preservation (HP):** handled through `flats/config/historic/protection.yaml#L163-L174` ("doubtful"). Its alteration rules (19.403.5) cover existing landmarks only, which is not a GREEN risk.
- **Flex Space (FS):** ruled not applicable to housing (`milwaukie.yaml#L449-L465`).
- **North Milwaukie Innovation Area (19.312):** handled (`#L66`, `#L140`).
- **Corridor design plan:** the code says such plans are "implemented through overlay zones" (`19/19.201.txt#L178`), but no such zone is in Table 19.107.1 or the stored code. Nothing to read.

## B. Cross-references near cited lines

I listed the outward references in the cited residential files (19.301.4–5, 19.302, 19.501, 19.502, 19.504, 19.505.1/.3/.4/.5, 19.202, 19.607, 12.16, 12.24). Every target is held except: 19.700 (finding 2), Title 17 (finding 7), 19.708 (circulation plans, not a dimension), 12.14 (accessory structures in the right-of-way), and the procedure chapters 19.800, 19.9xx and 19.1xxx (the ledger already shows these). Nothing else unfollowed could change a number for the building.

## C. Defined words

- **Front lot line is defined twice in 19.201.** `#L257` covers interior, corner and through lots only. `#L395-L399` adds flag-lot and back-lot clauses. The config cites the fuller one (`#L395-L399`, at `milwaukie.yaml#L1260`), so this is not a risk. Noted only.
- **Driveway is defined three ways:** `19/19.201.txt#L189`, `12.16/12.16.010.txt#L8` (same wording), and `12.24/12.24.020.txt` ("the point at which a motor vehicle gains ingress or egress"). The clear-vision wedge already works from the point, so no risk.
- **Lot width** is "measured at the Building line" (`19/19.201.txt#L409`) and **lot depth** is "the average horizontal distance between the front lot line and the rear lot line" (`#L389`). The config has no measurement-method field for either. Question: how does the engine measure width and depth, and is that the same as these definitions?
- **Height** is measured per 19.202.2 (`19.202/19.202.2.txt#L13-L28`), using whichever base point gives the greater height. The worst case adds 10 ft to the 20 ft constant, which is still under the 35 ft limit in R-MD/R-HD. No risk.
- **Townhouse applicability** text says lots must meet "the standards for a townhouse lot in both Section 19.302 and Subsection 19.505.5.E" (`19.505/19.505.5.txt#L17`). That names R-HD only, which looks like a code typo for R-MD lots. A question, not a ruling.
- **No second definitions found elsewhere.** I grepped the whole Milwaukie store for `for the purposes of this (section|subsection|chapter)` and `"<term>" means`, outside 19.201. The only hits were 12.16, 12.24, and non-residential sections (19.310.6, 19.311.5, 19.506.3, 19.511). None redefines lot, yard, setback, height, coverage, story, townhouse or middle housing.

## What I could not do

- I could not read `../vicinitideals-worktrees/overlay-inventory*.findings.md` or `overlay-inventory-lists/`; the sandbox blocks access outside the repo. Findings 4–6 may already be recorded there, so please check.
- `flats.encode.crossrefs` ran past 300 s and went to the background; I don't know if it finished. I used `data/flats/crossrefs.csv` as it stands in the working tree. I did not rerun `flats.encode.uncited`; I used the existing `data/flats/uncited.csv`.
- I did not use `definitions.py`, `glossary.py` or `words.py`. Part C is from grep.
- Section B was done by grepping the main residential files rather than a script over every cited line. Inline Python was not permitted, so the ±12-line window was not checked exhaustively.

Nothing was edited.

