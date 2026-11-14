# 192. Steph's 2026-11-14 answers: encode the four that change the screen (rel10 lane)

[Claude] [scan: YES -- mixed, mostly moot today]

Steph answered the 2026-11-13 question sheet on 2026-11-14. All rulings are in
flats/config/rulings.yaml (ids 2026-11-14-*). Four of them need code; build them
as one lane cut from the rel10 base (origin/flats/pagecheck-34 or later), so it
rides rel10:

1. **Fairview: hold every corner lot** for the driveway-near-intersection check
   (19.162.020), not only corners next to a collector or arterial
   (ruling 2026-11-14-fairview-hold-every-corner). Fairview has 0 GREENs, so
   nothing moves today. Built in drive-spacing (rel9); change it on top.
2. **Oregon City + Hillsboro: an engineer-set corner sight area is GREEN + flag**,
   not YELLOW (rulings 2026-11-14-oregon-city-/hillsboro-engineer-sight-area-green).
   Built in sight-leftovers (rel9). Moot today. A new flag, severity under 3 so it
   never holds YELLOW alone; any measured sight rule still binds.
3. **Gresham MDR-24 corner townhouse lot with an observed alley gets the code's
   alley figure (16 ft)**, so the 2026-10-20 "25 ft whether or not an alley"
   ruling no longer hides the alley case (2026-11-14-gresham-mdr24-alley-corner-width-16).
   Low priority, no lot depends on it. Re-read Table 4.0130's MDR-24 corner
   rows first: corner-th-191 (3652cfa6) reworked corner/interior on the same table.
4. **King City buffer per side: 5 ft beside a single-family zone, 10 ft beside a
   commercial zone** (KCMC 16.124.110 C.2/C.3, kcc.16.124.landscaping.txt). Steph:
   "We should have all lots and their zoning, yes?" We do: neighbour zone per lot
   line exists (abuts_*_zone per line). kc-buffer (ae782611, rel9) lumped them
   into one `abuts_lower_density_zone` fact and charged 10 everywhere. Split the
   fact so each line takes its own figure. 0 King City GREENs today.

## Still open with Steph (no code until answered)
- **Q1 Sherwood/Fairview 150 ft queue distance:** Steph asked how many lots/streets.
  Fairview 0 GREENs; Sherwood 17 GREENs in total (4 corners), so at most 17 lots,
  likely a handful. The exact list comes from the rel9 re-screen; show Steph the
  streets then.
- **Q2 West Linn 35 vs 50 ft:** Steph asked how many streets. TSP Table 15's note
  says "Commercial" refers to the designated commercial zones, so the street class
  can be read from zoning: a local street in residential zoning = Local Residential
  = 35 ft. Offered as a fix (more GREEN, cite-backed); waits on Steph's yes.
  Affects at most West Linn's 32 corner GREENs, mostly fewer.
- **Q7 Gresham downtown storage:** one space (S8, "a storage facility with an
  interior at least 6 feet high and 24 square feet"), in the unit, a garage, a
  central facility or a private yard/patio, lockable. Waits on Steph's design answer.
- **Q9 Beaverton Area D:** the street is the future SW Millikan Way extension
  (Watson to Lombard, city CIP 3327; city page lists it as a current project with
  no alignment chosen). Not built as far as found. Lots can only be YELLOW or RED
  either way (ground floor too short).
- **Q10 Beaverton mixed corners:** within the 152 held lots; Steph asked which
  lots. Pull the list from the rel9 bound output.
- **Q11 King City definitions:** "Dwelling, multi" = 5+ units on one lot;
  "Dwelling, single-family attached" = own lot, shared walls = townhouse;
  "Fourplex" = 4 units on one lot. Pod is a fourplex or townhouses, not "multi".
  But 16.124.110 C opens with "different types of land use zones", so the zone
  reading has a basis. Waits on Steph.
- **Q19 Gresham bent/curved corners:** programmatic fix offered -- draw the
  home-lot lines ourselves and test which home lot touches the second street
  (Gresham: corner lot = frontage on two or more streets). Waits on Steph's yes.

BUILT 2026-11-14: flats/rulings-1114 98fe014b (cut from corner-th-191, rides rel10). Hand-off ../vicinitideals-worktrees/rulings-1114.handoff.md. Expected moves not counted (bound counts). Gresham item 3 turned out a tightening: the 16 ft alley row already fired, also for a side-line alley; now needs an alley along the whole rear line. New Steph question (sheet Q20): Hillsboro engineer-set DRIVEWAY sight area -- GREEN+flag like corners?
