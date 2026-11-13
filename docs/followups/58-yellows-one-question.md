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

## Pass 3 (2026-11-08/09, flats/one-question-yellows-2; merged to main, live run 124)

DONE: Johnson Creek hold split by what each rule reaches (`johnson_creek_land_division` holds the
townhouse form alone; ~72 single-held lots yellow -> green as an apartment); Springwater corridor
re-traced on the Parks parcel (lots that abut it, within 25 ft, and its own = 365 held; 17 of 30
single-held corridor yellows released).
Big single holders that cannot be measured or belong to another lane: LOT-OUTSIDE-UGB 62,948,
JURISDICTION-OFF 13,991 (Lake Oswego), JURISDICTION-NOT-ENCODED 13,423, SLOPE-GRADE 1,083,
RESOURCE-PERMIT 510, PARKING-COURT-FRONT-YARD 465, MEASURE-FRONT-MAX-STREET 175, FAR-MIN 190,
FACT-PDX-PLAN-DISTRICT-UNMEASURED 113.
STILL YELLOW: the 12 lots abutting the Springwater corridor -- the screen cannot set the 20 ft (R) /
10 ft (C) buffer and 20 ft vehicle setback on the one lot line that faces the corridor; needs a
per-line setback (a build, not data).
