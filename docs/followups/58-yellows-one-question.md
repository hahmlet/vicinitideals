# 58. Yellows held by one measurable question (offered 2026-10-08; first pass DONE c98be01d 2026-10-09; LIVE in run 69).

58. [Claude] [scan: YES] **Yellows held by one measurable question (offered 2026-10-08;
   first pass DONE c98be01d 2026-10-09; LIVE in run 69).** MEASURED: MEASURE-FIRE-ROUTE
   (paved type-2000 streets count as truck roads: Portland 348 rows yellow -> green) and
   FACT-CIVIC-CORRIDOR for Rockwood (`rockwood_design_district`, the city's own layer; 290
   rows / ~148 lots yellow -> green; SC/SC-RJ and CMF stay yellow). CANNOT BE MEASURED from
   data we hold, left yellow (counts per design):
   - FACT-AT-STREET-END (Gresham, 789): Table 4.0131 note 5 numbers are not encoded and the
     street-class layer cannot separate Minor Access Streets (see 37(iii)).
   - ACCESS-STREET-UNCONFIRMED (441): the only road line is a private drive or lies across
     someone else's land; no map says whether the lot abuts it.
   - PARKING-STRIP-UNCONFIRMED (213): OAR 660-046-0220(2)(e)(E) is an open reading of law,
     not a fact on the ground (Steph ruled yellow flag 2026-10-04; the question is in 36).
   - FACT-CIVIC-CORRIDOR (the rest): Gresham's own corridor map is the source, and Glisan /
     162nd are not on it.
   Open: a new source for any of these four would release them; nothing else queued.

## Pass 3 (2026-11-08, branch flats/one-question-yellows-2, off rel5)

Ranked from the rel4 assign (102,121 yellow lots; 94,834 held by one reason). The big
single holders cannot be measured, or another lane owns them: LOT-OUTSIDE-UGB 62,948,
JURISDICTION-OFF 13,991 (Lake Oswego), JURISDICTION-NOT-ENCODED 13,423, SLOPE-GRADE 1,083,
RESOURCE-PERMIT 510, PARKING-COURT-FRONT-YARD 465 (a ruling, plus the Clackamas lane),
MEASURE-FRONT-MAX-STREET 175, FAR-MIN 190, FACT-PDX-PLAN-DISTRICT-UNMEASURED 113,
FACT-PDX-JOHNSON-CREEK-UNMEASURED 102.
MEASURED: the Johnson Creek hold was split by what each rule reaches. PCC 33.537.140.E
(South density) and 160 (Flood Risk Area) govern land divisions only (33.537.010), so the
lots only they reach are a new tracing, `johnson_creek_land_division`, that holds the
townhouse form alone (`fold_land_division`); the one-lot apartment form makes no land
division. The Springwater corridor reach (130) still holds both forms. Expected: about 72
single-held lots go yellow -> green as an apartment, the townhouse form stays yellow.
Pass 3b (2026-11-09, Steph: "you may always download maps"): Map 537-1 draws the
corridor only as its trail line; its land is the Portland Parks property "Springwater
Corridor" (Parks_Misc layer 2, stored as springwater-corridor.geojson), and the trail runs
inside it the whole way through the plan district. The corridor tracing was re-traced on
that parcel: held = lots that abut it, lots within 25 ft, and its own lots (365). Of the 30
single-held corridor yellows, 12 abut and stay yellow; 17 do not (14 South lots, green as
an apartment only; 3 across a street, green on both forms). The 403 lots beside corridor
parcels: 49 lots newly held across the whole check, none green in rel4.
STILL YELLOW: the abutting lots. The screen cannot set the 20 ft (R) / 10 ft (C) buffer
and 20 ft vehicle setback on the one lot line that faces the corridor; that needs a
per-line setback (a build, not data).
