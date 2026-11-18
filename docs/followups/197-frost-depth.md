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
