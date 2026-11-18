# 197. Frost depth per jurisdiction, as a note

**Status:** scout running 2026-11-18.

Steph 2026-11-18: "Do we have frost line of every jurisdiction logged? There are standards, but I know in Gresham they modified theirs because 'that's just what we like to see'. We'll need that too."

Nothing held today: the only "frost" hits in the repo are incidental zoning text. Frost depth lives in the building code, not the zoning code we store.

What to collect, for every jurisdiction FLATS screens (cities + the three unincorporated counties):
- the state baseline (Oregon Residential Specialty Code table R301.2 and the Oregon Structural Specialty Code footing-depth rule), as printed, with edition;
- the figure each building department actually enforces, as printed in its own design-criteria handout / local amendment / permit guide (Gresham is known to ask for more than the baseline);
- who the building official is for the place (some cities contract to the county), document URL, date, and a stored copy under data/flats/books/frost/<city>/.
- where a department's figure is practice rather than adopted text, log it as "practice" with the document that states it; where nothing is published, log "not published" -- no guessing, no contacting the city.

Then: a small register (flats/config/frost_depth.yaml, store as printed) shown on the lot page next to the soil note and in the lot report. Note only -- no colour, no flag.

Steph ruling 2026-11-18: where a department is genuinely silent (we found where the figure would be stated and it gives none), the county figure, else the state figure, is used and is valid, flagged as state/county level. This does NOT cover "could not find where it would be stated" -- that stays unresolved. Recorded in rulings.yaml.

Scout back 2026-11-18 (../vicinitideals-worktrees/frost-scout.md; files in data/flats/books/frost/): 26 places. Found 10, silent 11, not found 5 (Fairview, Wood Village, Hillsboro, Tigard blocked by the sites' bot checks; Estacada image-only PDF). Only Gresham differs: 18 in below finished grade (Aug 2008 inspection checklist, practice not code) vs 12 in baseline; its 2021 design sheet is silent. State table prints Multnomah 18 with a footnote setting 12 below 2,500 ft. Weak: state table read from a mirror, not stored; six "silent" rows (Troutdale, Happy Valley, Milwaukie, West Linn, Wilsonville, Lake Oswego) rest on department pages only, building chapters unread; Washington Co from a 2024 archive copy. Next: Steph to download the 4 blocked pages (asked 11-18); read Estacada by eye; read the six building chapters; then build the register + lot note.

Steph 2026-11-18 supplied the blocked four. Fairview MC 15.05 (ecode360, stored) and Wood Village MC 15.04 (current through Ord. 6-2024, stored) only adopt the state codes; no local frost figure -> SILENT, state figure (12 in), flagged state level. Hillsboro and Tigard: Steph searched each municipal code for "frost", "foundation", "seismic" -- nothing -> SILENT, state figure (12 in), flagged state level, basis "Steph's search of the municipal code 2026-11-18" (department handouts not seen). Unresolved now: Estacada only (image PDF, read by eye). Open check: which department does building permits for Fairview and Wood Village -- if Gresham does, its 18 in practice may reach them.
