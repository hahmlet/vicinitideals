# 196. Soil type per lot, as a note only

[Claude] [scan: NO -- note only, no colour]

Steph 2026-11-17: "Do we have data on the soil types for all of our lots?" No. Steph said yes to pulling
the USDA soil survey (SSURGO / Soil Data Access; free, public) and attaching it to each lot as a NOTE ONLY
(no colour, no severity that can hold a lot), "start with green lots and let me know when those are
done. Then continue on the rest."

Per lot (dominant map unit under the lot, plus the worst component where the lot spans several): soil
name, drainage class, hydric yes/no, depth to water table, shrink-swell (linear extensibility), depth to
restrictive layer/bedrock, the "dwellings without basements" and "small commercial buildings" limitation
ratings, hydrologic group. State the survey scale caveat on the page (farm-field scale; a hint, not a
soils report). Optional second layer if cheap: DOGAMI landslide susceptibility and liquefaction.
Also feeds the crane check's "firm ground: not checked" (145) later.

Order: live GREEN lots first (report to Steph), then every lot.
Branch flats/soil-notes; hand-off ../vicinitideals-worktrees/soil-notes.handoff.md.

Steph 2026-11-17 (later): (1) log EVERY soil map unit on a lot with its square feet and share (not only dominant/worst); (2) keep the technical identifiers for later technical analysis: areasymbol + version date, musym, mukey, nationalmusym, muname, map unit kind; per component cokey, name, percent, major flag, taxonomic class. Map-unit and component tables stored once, lot rows point at mukey. Passed to the builder.
