# 220. Short slip roads outside Portland: read each city's definition of a street

[Claude] [scan: YES -- toward green]

From 215 (flats/pdx-connectors): Portland now reads a short slip road between two city streets
(RLIS connector, named only for city streets) as a street, citing Portland's definition. Outside
Portland the same roads are still held as limited (no driveway), because no other city's street
definition has been read. 2026-11-27: this is reading work, not a Steph question.

Do: for each jurisdiction with lots on such connectors (the 149 `limited` lots: washington_unincorporated
15, beaverton 15, tigard 12, clackamas_unincorporated 8, milwaukie 5, multnomah_unincorporated 1),
read the code's definition of street / road / right-of-way (whole-document grep, follow
cross-references), and encode the city as Portland is where the definition covers the connector.
Bridge on/off slip roads stay limited everywhere (Steph 2026-11-27).
Then bound (s4 rebuild of street_kind_json only, as 215's recipe), move read, release.
Start after 215 ships.

## Readings done 2026-11-27 (../vicinitideals-worktrees/slip-road-readings.md)
YES: clackamas_unincorporated (8), milwaukie (5), multnomah_unincorporated (1). UNCLEAR, stay limited:
tigard (12), beaverton (15), washington_unincorporated (15; needs ORS 801 definitions fetched).
Next: encode the three YES places like Portland on top of flats/pdx-connectors once 215's encoder is done.
