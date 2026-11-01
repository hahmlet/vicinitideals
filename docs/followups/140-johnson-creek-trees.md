# 140. Johnson Creek tree limits: clear lots with no big trees?

[Claude] Offered 2026-11-01 with the Portland plan districts part 1 build (FOLLOWUPS 109,
branch flats/districts-pdx-pd1, 2a899813). PCC 33.537 (Johnson Creek Basin plan district) limits
removing larger trees on lots in the South subarea, on flood ground and along the Springwater
corridor; nothing measures trees, so about 430 lots that were GREEN go YELLOW ("check first").
QUESTION for Steph: use the city's tree-canopy layer (Metro / Portland canopy data, free) to clear
the lots with no qualifying trees, or leave them yellow? If yes: a source scout for the canopy
layer and its date, then an encoder adds a measured fact (no canopy over the pod's footprint +
court) and a bound; never release a lot the canopy layer cannot see clearly.

STEPH 2026-11-01: "Let's build in the tree map" (rulings.yaml
2026-11-01-johnson-creek-trees-cleared-by-canopy-map). Plan: (a) source scout -- the canopy layer,
its date, resolution and licence, plus a Springwater Corridor boundary layer; (b) encoder on a
branch stacked after pd1's release -- measured canopy fact over pod + court, and corridor-abutting
lot lines for the 20 ft buffer; canopy or an unreadable patch keeps YELLOW; (c) bound, read every
gained green, release.
READ 2026-11-01: 33.537.125 C.3 lets any tree within 10 ft of the building or a proposed driveway
come out by right, so the canopy test is only over the court/stalls more than 10 ft from both
(conservative: the court is not a "driveway"). C.6 (6-12 in. trees replaced two-for-one) is also
by right but the canopy layer cannot size trunks, so it does not clear anything.
