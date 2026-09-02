# Human TODO — things only Steph (or another human) can move

This is the standing list of decisions, phone calls, and readings that the
agent cannot do alone. The agent maintains it: items get added when work
surfaces them, and struck through (with a date and what happened) when they
close. Items are ordered by how many lots ride on them, biggest first.

Pipeline state when last updated (2026-09-02, after the FEMA county-gap re-run):
**green 10,106 · review 30,252 · red 210,386** across 250,744 lots in 13 cities
laid out with real site plans. The 73 greens lost against 2026-09-01 are the
measured cost of one missing county in the flood download.

---

## If you approved every item below, could you trust a green lot?

Asked directly on 2026-09-01. The honest answer is **not yet, and the gap is
not mainly on this list.** Working the list is necessary and it is not
sufficient. Four things stand between a green verdict and a lot you could buy
on it, and only the first is a queue item:

1. **Nothing is signed.** Not one of ~2,340 encoded numbers has been read and
   confirmed by a person (item 7). Every green today rests on an unreviewed
   reading. This is the biggest single item and it is *work*, not a decision —
   you cannot approve your way past it in an afternoon.
2. **82% of greens rest on one legal argument** about a parking dimension no
   city wrote down (item 3, corrected on 2026-09-01 to include Portland). The
   argument is good. It is still an argument.
3. **Nothing screened environmental overlays anywhere in Clackamas County** —
   floodplain, wetland, habitat, steep slope. Multnomah had thirteen such
   layers; the eleven Clackamas jurisdictions had none, and **2,820 greens
   (28%) were graded with that check simply absent.** Found 2026-09-01, and
   now mostly closed. The flood half was a one-line bug — the FEMA download was
   filtered to Multnomah's county code while the config claimed flood applied
   everywhere. Fixed and re-run: **73 lots that had been green were not**, and
   flood touches roughly tripled. The other half was real work and is agent
   work: every Clackamas city that produces a green publishes its own
   natural-resource geometry, and **every city that has a green is now wired** —
   Oregon City, Happy Valley, Wilsonville, West Linn, unincorporated Clackamas,
   and Milwaukie. Milwaukie was the one that looked blocked: its overlay
   chapter sits on a host that will not serve it to a script and the chapter's
   id is not published anywhere. It was found by reading the raw page of the
   *next* chapter, which links back to it. **Nothing is needed from you on this
   item any more.** The two cities still unscreened, Tualatin and Gladstone,
   have no greens between them.
4. **No green has ever been checked against a real answer.** The one back-test
   run measured the opposite direction — of fourplexes that really were
   permitted, did we flag the lot? (60%.) Nobody has taken a green lot to a
   planner and asked whether we are right. Until that happens the accuracy of
   a green is an estimate, not a measurement.

The cheapest thing that would change this, by a wide margin, is **(4)**: pull
twenty greens across three cities and have a land-use planner or attorney rule
on them. That converts every number on this page from a guess into a rate, and
it costs one person a few days.

---

## 1. Read one drawing: Clackamas County's parking detail — **17,486 lots**

The single biggest unlock left, and it is half the entire review queue.

Clackamas County's rule book says parking must match its zoning code AND its
standard construction drawings. The stall size was readable off the drawing's
title block (9 × 18 ft). The **drive-aisle width is drawn inside the picture**,
and our evidence standard requires quoting words at a line number — a picture
cannot be quoted, so the county has sat unread-able for a month while smaller
cities were finished.

Three ways to close it, strongest first:

- **Email county planning** and ask, in writing, what drive-aisle width
  Standard Drawing P100 requires for 90° parking. A written answer is evidence
  nobody can argue with. (This is the same move as item 2 — could be one
  batch of emails.)
- **Open the drawing yourself** (Clackamas County Standard Drawing P100), read
  the aisle number off it, and tell the agent. It gets encoded with a note
  that a named human read the drawing on a given date.
- **Decide that machine-reading of drawings counts as evidence.** Fastest,
  weakest — the number would carry a "read from a picture" caveat forever.

Note: the "24 ft when nobody published a number" rule from item 2 does NOT
apply here — the county *did* publish a number, in a drawing. Assuming over
the top of a published number is the one thing the system refuses to do.

## 2. One decision: may a coarser elevation map grade a lot green? — **7,972 lots**

The single biggest number on this list, and it is one yes-or-no answer.

Four whole cities — Gresham, Troutdale, Fairview, Wood Village — have produced
**zero** green lots for the life of this pipeline, and Portland's eastern third
has been quietly held back too. Not because of any zoning rule. Because the
federal government never flew the fine-resolution laser survey out there. The
screen treats "we do not know the slope" the same as "the slope is bad", so
every one of those lots sits in the human queue forever.

There is a coarser national elevation map that *does* cover all of it — about
one reading every 30 feet instead of every 3 feet. It is now wired in, and
every one of those lots has a slope number for the first time. The question is
what that number is allowed to conclude.

We measured it rather than guessing: on the 184,101 lots where **both** maps
answer, the rule we would use agrees with the fine map well enough to clear
**7,972 lots straight to green**, and it would be **wrong about 1.5% of the
time** — roughly 120 of those 7,972 would turn out, on a site visit, to be
steeper than they looked. It is wrong in the safe direction the rest of the
time: it hardly ever calls a flat lot steep.

So the trade is: **+7,972 green lots (a 78% increase on the whole corpus),
against roughly 110 of them being duds you would discover on the first visit.**

(Re-counted 2026-09-01, replacing an earlier 7,231. The new number is the strict
one: lots where the coarse map is the *only* thing holding them, with the ones
that would still be stopped by a steep reading, an odd shape, a missing sewer or
an unsigned zone rule taken out first. It breaks down as Portland 5,320, Gresham
2,428, Troutdale 126, Wood Village 96, Happy Valley 2 — and Fairview's 199,
which need item 7 as well, are not in it.)

- **Yes** — flip one setting, re-run, those lots grade green like any other,
  and a column records that their slope came from the coarse map so anyone can
  filter them back out.
- **No** — they stay in the review queue, but now with a slope number attached
  instead of a blank, which at least makes the queue sortable.

Nothing else is blocked on this; it is purely how bold to be. Same shape as the
drive-aisle call you made on 2026-08-31, and the same reason it is yours: it
trades a small chance of wasted diligence for a large amount of pipeline.

## 3. Three short emails: confirm the assumed 24 ft aisle — **8,343 greens, which is 82% of all of them**

**This entry said 985 greens until 2026-09-01. It was counting two of the three
cities.** Portland carries the identical assumption on **7,358 greens** and had
been left off. Corrected here because the number changes what the entry is: not
a tidy-up on two small cities, but the single largest thing standing between
this screen and a green list you could act on.

Portland (7,358 greens), Milwaukie (845) and Wilsonville (140) all publish a
parking stall size and **no drive-aisle width that reaches a quadplex**.
Portland's is the subtlest of the three: PCC 33.266.120 gives houses through
fourplexes a 9 × 18 stall and states no aisle, and the 20 ft aisle in Table
266-4 belongs to the *parking-tract* branch of the code, which is a different
kind of land division from the single lot we draw on.

Per your 2026-08-31 decision, all three are drawn to the national engineering
minimum (24 ft, ULI/NPA via Iowa SUDAS) and grade green, because state law
(ORS 197A.400) only lets a city apply written, objective standards to housing —
and a width nobody wrote down is not one. That reasoning is sound and it is
still an argument rather than a citation, which is exactly why it is worth
three emails rather than none.

The residual risk: all three cities have language that *could* be used to send
"drive aisle design" to a human reviewer. A one-paragraph email to each
planning department — *"your code gives a quadplex a 9 × 18 stall and states
no drive-aisle width; we intend 24 ft two-way; please confirm that is
acceptable"* — converts the assumption into a confirmation. If they answer
with a different number, the agent re-runs with theirs the same day.

Worth knowing before you send: 24 ft is the **floor**, not a comfortable
number. The corpus median and mode are also 24 (8 of the 11 cities that publish
one), and the four that go higher — Troutdale and unincorporated Multnomah at
25 — are the cities with no greens anyway. If Portland comes back with 20 ft
this gets *cheaper*, not dearer.

These lots are filterable: the `geometry_assumed` column in
`lots_results.csv`, and the greens they produce are itemized in `summary.md`.

## 4. One question for a building-code expert: accessible (ADA) parking — **every city at once**

Open question, deliberately parked: does Oregon's building code (OSSC) require
one accessible stall — 13 ft wide with its access aisle — for a **4-unit,
no-elevator building with surface parking**? 

- If **no**: closed everywhere, nothing changes.
- If **yes**: every court in every city needs one wider first stall, which
  shrinks tight lots in all 13 laid-out cities simultaneously.

One architect or code consultant can answer this in a sentence. It was parked
rather than guessed precisely because the answer moves lots everywhere at once.

## 5. Business decision: Milwaukie legally caps parking at 4 stalls — **845 greens**

Milwaukie's code caps a quadplex at **1 parking space per unit — 4 total**,
which is exactly the marketability floor. Every legal Milwaukie site plan is a
minimum-parking plan; the 1.5-per-unit and 2-per-unit tiers are not something
that city will permit at any lot size.

Decision needed: **is 1 stall per unit marketable for this product?** If not,
Milwaukie's 845 greens should be deprioritized before any diligence money is
spent on them. No agent work either way — this is a product call.

## 6. Data ask: sewer coverage in Happy Valley, unincorporated Clackamas, Tualatin

These areas' sewer districts (WES / Clean Water Services) do not publish their
sanitary main maps, so lots there can never clear the "sewer confirmed" check
from public data — they sit at review on sewer forever. District *boundaries*
partially close this in Clackamas already (outside every district = red), but
inside a district stays yellow without the mains.

The fix is a records request or data ask to the districts for their main
layers. A utility will often hand this over on request; it is not public GIS.

## 7. Start signing: the only thing between FLATS and trusted GREEN

Every zoning number in the corpus is *encoded* — transcribed with a quote —
but none is *verified*: nobody has yet sat down, read the quoted sentence
against the number, and signed it. Until values are signed, the FLATS side of
the house can't issue a fully trusted GREEN by design.

This is deliberate — signing was pointless while encoding churned. The corpus
has been stable for a while now. Decision needed: **when to start signing
sessions**, and in what order. Sensible order is by greens at stake: Gresham
and Happy Valley first, then Portland. Each session is you (or a delegate)
reading quotes against numbers — tedious, but each one is permanent.

## 8. Optional legal read: the state's "use single-family standards" rule

OAR 660-046-0220(2)(e)(E) says a quadplex's parking dimensions must be *the
same as single-family's in the same zone* — and no city writes down what its
single-family parking dimensions are, so the rule points at nothing findable.
Where single-family practice is looser (it usually is — a driveway beside a
house), our screen is **stricter than the law requires**: that costs us lots
but creates no risk. A land-use attorney could say whether it's worth pressing
in any particular city. Perfectly fine to accept as-is; listed so the
conservatism is a choice, not an accident.

## ~~9. Housekeeping: two old feature branches~~ — closed 2026-09-01

You delegated the call. Verdict: both branches (plus a third found in the
audit, `email-multi-deal-triage`) were dead — `draw-type`'s feature had
already shipped to main under a different commit, and the other two were
merged or superseded. All three were archived as patch files first
(`../vicinitideals-worktrees/archived-patches/`, so nothing is
unrecoverable), then removed. Three genuinely in-progress worktrees were
kept untouched. Four orphaned non-worktree folders were noted and left
alone.

---

## Seven of our fourteen cities have zero green lots — and each one has a single reason

Measured 2026-09-01 against the current run. Half the map is producing nothing,
which looks alarming and is not: every city on this list is blocked by exactly
one thing, and every one of those things is already an item above. Nothing new
is being asked of you here — this is the answer to "what do I actually get if I
do item 2, or item 6, or item 7."

| City | Lots waiting | The one thing holding them |
|---|---|---|
| Gresham | 2,899 | Elevation map — **item 2** |
| Troutdale | 172 | Elevation map — **item 2** |
| Wood Village | 115 | Elevation map — **item 2** |
| Fairview | 199 | Elevation map **and** signing — items 2 *and* 7 |
| Happy Valley | 731 | Sewer coverage — **item 6** |
| Tualatin | 20 | Sewer coverage — **item 6** |
| Gladstone | 145 | Signing — **item 7** |

Read across: **item 2 is worth 7,972 lots** — that is the count that would turn
green immediately, with nothing else standing in their way, and it is 5,320 in
Portland and 2,428 in Gresham. Item 6 unlocks Happy Valley outright: 722 of its
731 waiting lots are held by nothing but the missing sewer map. Gladstone is
pure signing — all 145 of its lots are sitting behind zone rules nobody has
signed off yet, and no data is missing at all.

These seven are the whole of the zero-green half of the map. The other seven
cities all produce greens today.

## Villebois turned out to be a dead end, and for an honest reason — **2,106 lots**

Wilsonville's V zone was the largest block of land the screen had been dropping
without ever looking at it: 2,508 lots in Villebois, invisible because nobody
had encoded the zone. It was read on 2026-09-01 and the full run finished the
same day. **2,106 of its lots reached the screen. None came out green.**

The reason is one number and it is quoted to the line. Villebois was platted as
a dense new-urbanist neighbourhood — Wilsonville's own table gives a single
family house there a 2,250 sq ft minimum lot. But when the city wrote its
middle-housing exception (WDC 4.125(.23)(B)(3)) it set **the minimum lot for a
quadplex at 7,000 sq ft**, three times the size of the lots the neighbourhood is
made of. 1,865 of the 2,106 are simply too small. Another 114 fit no building
and 102 can have no parking drawn.

Nothing here needs fixing. It is worth knowing because Villebois is the kind of
place that looks obviously right for this product from the street — small
attached homes, narrow lots, alleys — and the city has written a rule that
closes it to us without lot assembly. The two-and-a-half thousand lots come off
the list of places worth hoping about.

## Queued for the agent — no action needed from you, listed so nothing is invisible

- **Wire up the Clackamas environmental layers** — done everywhere a green is
  at stake, and the work turned out to be reading, not configuring. Every city publishes a
  natural-resource map; no two of them mean the same thing by it, and only the
  city's own code says which. Oregon City calls its map "a regulatory boundary"
  and forbids structures inside it, so it is subtracted from the buildable
  area. Happy Valley says its map exists "to determine whether further
  environmental review is necessary", so it sends the lot to review instead.
  Wilsonville publishes only the 25-foot ring *around* each resource and not
  the resource, so the layer had to be filled in before it screened anything —
  taken as published it would have flagged lots beside a wetland and cleared
  the one sitting in it. West Linn publishes stream centre lines and makes its
  code supply the width: 65 feet for a live stream, 15 for a seasonal one, and
  nothing at all for the 190 piped channels it maps, which are flagged rather
  than guessed at.
  Unincorporated Clackamas turned out to be the opposite of a hazard: the
  county regulates habitat and water quality at length and forbids almost
  nothing — the complete list of what you may not do in a habitat area is
  "plant invasive vegetation" and "store materials outside" — so its 598
  greens keep their verdicts and get a second look instead.
  Milwaukie is the one that had looked blocked, and it turned into the most
  interesting reading of the set: one chapter, two opposite answers. Land in
  the Willamette Greenway can only be built on by *conditional use* — a
  discretionary approval, a hearing, a decision somebody makes rather than a
  rule you can meet — so those lots come off the board entirely, the same
  treatment Portland's environmental zones get. Four sections later the natural
  resources chapter opens with what reads like the same prohibition, and it is
  not one: it forbids development "other than those allowed by this section",
  and the section then allows limited disturbance **for new dwellings
  specifically**, over the counter, no hearing. So those lots go to review, not
  off the board. A prohibition followed by "except as allowed below" is not a
  prohibition until you have read what is allowed below.
  Milwaukie also publishes the band of every property within 100 feet of a
  resource — tempting, and deliberately not used. Inside that band but outside
  the resource, all the city asks for is a construction management plan. That
  is paperwork, and paperwork is not a reason to lose a green.
  Remaining: Tualatin and Gladstone, neither of which has a green today, so
  nothing rides on them.

- **A rule that would ADD greens, found while reading the county** — Clackamas
  ZDO 706.11 says a lot containing a habitat area, inside the Portland urban
  growth boundary, has **no minimum front, rear or side yard setback at all**
  (garages still have to sit back, and fire code still applies). Every other
  environmental rule found this week takes buildable ground away; this one
  hands it back, and specifically on the lots that are hardest to fit a pod
  onto. Nothing in the screen can express "this constraint makes the lot
  easier", so it is written down here rather than acted on. Worth building the
  shape for — it can only move lots toward green, never away.

- ~~**Portland-administered pockets** (PCC 33.266 applied to the 1,489
  unincorporated-Multnomah lots Portland administers)~~ Closed 2026-09-01:
  read, and it changes nothing. Portland's chapter and the county's state the
  same 9 × 18 stall, and the county is the stricter of the two on every other
  dimension, so the pockets keep the county's numbers. The prize was also
  smaller than billed — 1,806 of those lots die on Portland's Constrained
  Sites overlay before parking is reached, leaving 39. What is genuinely open
  there is *which code administers the pockets*, which is a question for a
  planner, not a reading.
- ~~**Unencoded zone: Lake Oswego NC (93 lots)**~~ Closed 2026-09-01 as
  worthless for now: Lake Oswego is not in the lot inventory at all — the
  pipeline evaluates zero lots there — so encoding a zone in it moves nothing
  until the parcel data reaches Clackamas' western cities.
- ~~**Wilsonville Public Works Standards + Gresham's engineering manual**~~
  Closed 2026-09-01: both fetched, sliced and read. Gresham's answers in
  words — a 9 ft citywide minimum driveway approach width is now encoded (it
  equals what the site plan already assumed, so no lot moved), and the clear
  vision numbers the code kept pointing at are on file: 20 ft either side of a
  middle-housing driveway, 40 ft at a street corner, no parking allowed in
  either triangle. Not encoded, because a triangle cut across a corner is not
  a setback and nothing knows which lots are corners. Wilsonville's manual
  does *not* answer: 224 pages, and its only "aisle" is a no-parking throat at
  the mouth of a lot, not a width between two rows of cars. **The 24 ft
  assumption behind ~140 Wilsonville greens survives, and now rests on a
  search rather than on nobody having looked.** The manual does hold a 20 ft
  two-way driveway minimum — the size of number that moves lots — but the code
  only reaches it for lots fronting *solely* on collectors and arterials, and
  nothing knows what class of street a lot fronts.
- ~~**Unencoded zones**~~ **Closed 2026-09-01 — the corpus now has an entry
  for every zone the pipeline screens.** Wilsonville TC (59 lots) read the
  same afternoon and answered quickly: Town Center runs 953 lines and never
  says quadplex, middle housing, townhouse or duplex. Its one residential
  use is "multi-family", which Wilsonville has defined to exclude middle
  housing — so the only housing Town Center allows is the one thing this
  product is not. Nor does the state mandate reach it: the rule forces
  middle housing where *detached houses* are allowed, and Town Center allows
  none. Those 59 lots now screen red instead of vanishing. Wilsonville V
  closed
  2026-09-01, and it was ten times larger than the note said: **2,508 lots**,
  the biggest zone in Wilsonville and the largest block of land the screen was
  dropping. V is Villebois. Its development standards table has no row for a
  four-unit building at all, and the way in is a separate provision on
  redeveloping an existing house — which says a quadplex takes the
  *single-family* standards, with one change, a 7,000 sq ft minimum lot. The
  usual week-long argument about which row a four-plex belongs in did not
  happen here: the city's own definition of "multi-family" excludes middle
  housing in as many words, so the apartment row is closed to it by
  definition. Encoded and mirrored into the pipeline; **held at review rather
  than green** on two open questions, below.
- **Two questions before Villebois lots can go green** (2,508 lots, agent will
  ask if you want them asked): (1) Wilsonville requires 25% of a residential
  development to be open space *not counting the yards*, which no single lot
  could meet — but the same sentence says a phase inside an approved master
  plan does not have to meet it alone, and all of Villebois is inside one. The
  code reads as though the parks already did this. (2) The lot coverage cap is
  45%, 55%, 65% or 75% depending on which "lot category" the Villebois Pattern
  Book puts a lot in, and we do not have the Pattern Book. The safest of the
  four is used, which costs nothing today.
- ~~**The site plan and the code corpus were never checked against each
  other**~~ — found and **worked through on 2026-09-01**. A new audit
  (`Lot Analysis/quadfit/audit_zone_mirror.py`) compared the two files that
  carry a zone's dimensions — the pipeline screens from a hand-written config,
  FLATS reads the code and quotes every figure to a line of a stored document —
  and found 28 disagreements against 431 agreements. **All 21 real ones are
  resolved.** What is left is not disagreement, and is frozen into a test so
  nobody "fixes" it by editing a number.

  The 21 were nearly all the same mistake, and it is worth knowing because it
  will happen again: **the pipeline had been reading the detached house's row
  of a table that prints one row per housing type.** A four-plex is not a
  house, and the codes say so in the same table. Oregon City gives a quadplex
  70% lot coverage where a house gets 50; Happy Valley 60 against 50; Gladstone
  a 3,600 sq ft minimum lot where a house needs 7,200. Every one of those was
  lots thrown away for nothing. It ran the other way twice: Milwaukie R-HD was
  screened on a 5 ft front setback that the code applies only to a handful of
  mapped properties (the general rule is 20 ft), and Gladstone R-5 on the
  house's 5,000 sq ft where a quadplex needs 7,000. Those were lots called
  green that should not have been. **Green counts will move in both directions
  on the next pipeline run**, and on balance up: five of the eight corrections
  loosen the screen.

  Three things remained. **One of them closed on 2026-09-02.**
  - ~~**7 places the pipeline cannot express a rule it has no field for**~~ —
    **built and shipped 2026-09-02.** Gresham prints a 15 ft rear setback in
    five of its residential districts and then, in a different chapter, caps
    the roof at 21 ft on that line and lets it rise a foot for every foot
    further back — so our 26 ft pod has to stand at 20 ft, not 15. Milwaukie
    says the same thing about its side yards in a different shape, as a
    45-degree plane. Every Gresham LDR lot was being drawn with five feet of
    back yard it does not have, in the largest jurisdiction in the screen.

    The fix was deliberately not "edit seven numbers". Both files now hold
    exactly what the code prints, and the pipeline *derives* the setback a
    26-foot building owes from the plane the code states. Change the product's
    height and all seven move on their own. **This takes greens away in
    Gresham and Milwaukie on the next full run** — it is the same shape as the
    environmental overlays: reading a rule properly costs lots.

    One thing found while building it and deliberately left alone: Gresham
    switches the whole rule off for any lot inside its hillside or resource
    overlay. Those lots are being screened five feet stricter than the code
    asks. Giving the five feet back needs the screen to know which lots those
    are *before* it draws the envelope, which it currently does not, and it is
    not obvious the city means to hand back ground it has already protected.
    Written down in the code file rather than guessed at.
  - **1 place the pipeline is right and the corpus is merely richer.** Lake
    Oswego asks 5 ft on one side and 15 ft across both. The pipeline has one
    side-yard number and no combined one, so 7.5 is the only figure it can
    carry that obeys the rule — "correcting" it to 5 would screen a 10 ft
    combined yard against a code that demands 15.
  - **2 zones disagree about something bigger still** — whether a four-plex is
    allowed there at all: unincorporated Multnomah's LR-7 and Wilsonville's RN.
    In both, the pipeline says yes and the corpus says no. RN's five
    dimensional differences are parked behind that question rather than
    reconciled one number at a time, because if the corpus is right none of its
    lots is screened and none of those figures matters. **Checked against the
    current run and it costs nothing today**: LR-7 is 160 red and 1 review, RN
    is 492 red and 11 review, and neither zone has produced a single green lot.
    Both are legal arguments — the county never wrote HB 2001 into its own code
    and Wilsonville's RN says "quadplexes are not permitted" against a state
    preemption that is real but untested — so they belong with the optional
    legal read rather than ahead of it.

  Agent work, no action needed from you.
- **76,752 lots are thrown away for being in a zone the screen has never been
  taught** — found 2026-09-02 while building the step-back, and it is the
  largest recoverable pool anybody has measured. The screen carries its own
  hand-written table of what each zone allows. The code corpus carries a
  second, read properly and quoted to the page. Those two had been checked
  against each other **number by number** — and never **zone by zone**. Doing
  that turned up 35 zones where the corpus says a four-plex is permitted and
  the screen has no entry at all, so every lot in them is dropped before
  anything is measured.

  Nearly all of it is Portland: RM1 (19,643 lots), RM2 (12,782), EX (9,929),
  CM2 (9,520), CX (8,488), and nine more — its apartment and mixed-use zones,
  which is exactly where a four-plex is least controversial. The rest is small:
  Gresham 1,319, Happy Valley 715, Wood Village 167, Troutdale 72,
  unincorporated Multnomah 33.

  **This direction is safe** — a lot the screen never looks at cannot become a
  wrong green — and that is why it survived. It is 30% of the lot universe
  sitting behind a table nobody thought to compare as a list.

  **Ported 2026-09-02, waiting on a re-run.** All 29 in-market zones are now in
  the screen (Lake Oswego's six are left out: you have that city switched off,
  so its lots never reach a measurement either way). Every one arrives marked
  *needs verification*, which means those 76,752 lots land in the **review**
  pile, not the green one — work to look at rather than lots to buy. Nothing
  needed from you; the numbers move on the next full run.

- ~~**110 green lots may be too BIG to build only four units on**~~ —
  **fixed the same day, 2026-09-02.** Found while
  porting the zones above, measured, and small. Some cities set a *minimum*
  density as well as a maximum: build housing here and you must build at least
  so many homes per acre. Four homes clears that floor on a normal lot and
  stops clearing it on a large one. The state's middle-housing law cancels
  density *maximums* for a four-plex, which is what protects us in West Linn
  and Gresham, but it pointedly does not cancel *minimums*.

  Measured against the last full run: **110 of 10,106 greens, every one in
  Oregon City**, sit above their zone's floor. That is an upper bound — the
  cities measure the floor on developable land rather than the whole lot, which
  can only help.

  Oregon City's chapter is already read, and it is the unfriendly answer: the
  four homes do count toward the floor, and the code says outright that the
  minimum "may not be reduced". So the floor is real where it applies. The new
  screen we are building already checked this correctly; the older one still
  producing today's numbers had no column for it — a gap between our own two
  screens rather than an unread rule, which made it cheap to close.

  Now closed: the floor is carried on all 40 zones that state one, checked
  against the code corpus like every other dimension, and a lot above its floor
  goes to **review** rather than red. Review because the cities measure the
  floor against developable land and we only know the size of the whole lot —
  clearing it on the whole lot settles the question, failing on the whole lot
  only raises it. The 110 move on the next run.

  Checked at the same time and it came back clean: some cities also set a
  *maximum* front setback — build no further back than this — and the screen
  has never heard of that either. Twenty-four zones state one, twenty-two of
  them are already in the review pile for other reasons, and the two that are
  not hold **no green lots at all**. Nothing to do, written down so the next
  city somebody reads does not inherit the blind spot silently.

- **Corner-lot status — and it is the opposite of what this list said.** 14
  jurisdictions define what a corner lot is; nothing computes which lots *are*
  corners, so all 78 corner rules in the corpus are switched off and every lot
  is screened as if it were mid-block. This entry used to read "worth ~10 ft of
  buildable envelope". Checked properly on 2026-09-01 with a new audit
  (`Lot Analysis/quadfit/audit_corner_variants.py`, frozen into a test):
  **turning corner rules on can only take lots away, never add them.**

  The corpus does hold 28 corner rules that give a corner lot *more* room, and
  they are large — Gresham drops a 100 ft frontage minimum to 32 on a corner.
  Every single one of them also requires the four-lot subdivision plat, which
  is not the way we build, so none of them can ever fire. The 29 that would
  fire all go the other way: Wood Village's side yard goes from 5 ft to 10 and
  its back yard from 15 to 20 (that is where the "10 ft" came from — it is a
  cost), Gresham's frontage minimums from 35 ft to 40, and its medium-density
  lot width from 16 ft to 70.

  **And then sized, the same day: it is worth at most 20 lots today.** Of the
  29 corner rules that would fire, only four touch a setback — the rest are
  frontage and lot-width minimums in Gresham, which has no green lots at all.
  Wood Village has none either. That leaves one Wilsonville side-yard rule
  against 20 green corner lots, and some of those would survive it.

  So: real, in the dangerous direction (a lot we call green that a planner
  would not), and currently costing almost nothing. It stays on the list rather
  than getting built now, and it gets built when a city that *does* have greens
  turns out to have a corner rule — 1,321 of the 10,179 greens are corner lots,
  so the exposure is there the moment one appears. Agent work.
- ~~**quadfit/FLATS config divergences**: LR-7 front setback (20 vs 10) and
  Wood Village MR 2 minimum lot — cleanup; zero greens ride on either
  today.~~ Closed 2026-09-01: both aligned to the quoted code text and the
  report re-run. LR-7's minimum lot was the big one (7,000 → 20,000 — the
  county wants 5,000 sq ft *per unit*); nine LR-7 lots moved review → red,
  no green moved anywhere. LR-7's building envelopes still reflect the old
  smaller setbacks until the next full pipeline run; at most 15 non-green
  lots ride on that.
- **Coarse-DEM plumbing shipped 2026-09-01, and the full run confirms it moved
  nothing** — the 1/3 arc-second national DEM is fetched, warped and sampled,
  `slope_source` rides in the CSV, and the false "grade A / 1 m DEM" coverage
  claims for four cities with no elevation data at all are corrected. The
  pipeline finished at 11:22 and the verdicts are **identical to the run before
  it**: 10,179 green, 30,185 review, 208,274 red, to the lot. That is the
  designed outcome — the coarse figures are recorded but not allowed to clear a
  lot to green, so they change nothing until somebody says they may. What did
  change is that **no lot anywhere now has an unknown slope**: 184,101 read off
  1 m lidar, 64,537 off the 10 m fallback, zero with no answer, where before
  four whole cities had none. Only the green/no-green switch is left, and that
  is item 2 above.
- **The screen is measuring the wrong side of the lot in two cities** —
  988 lots (Oregon City 896, Tualatin 92). Found 2026-09-01 by chasing the 33
  numbers the zone audit said had no code behind them. All 33 turned out to be
  perfectly well read — 18 in zones that borrow another zone's rules outright,
  which the audit could not see, and 15 where the two files simply call the
  same standard by different names. But naming it differently hid the real problem: the screen
  asks "how much of this lot touches a street?" and compares the answer to a
  number the code measures **across the middle of the lot**. Oregon City spells
  it out (17.04.700: between the midpoints of the two side lot lines), and so
  does Tualatin (at the centre of the lot).

  On a plain rectangular lot those are the same and nothing is wrong. On a
  cul-de-sac wedge, a flag lot, or anything that narrows toward the street they
  are not, and 988 lots are currently being thrown out for failing a test the
  city never applied to that edge. West Linn does the same thing safely — its
  tables say "minimum lot width **at the front lot line**", which is the street
  edge — so its 739 exclusions stand, and it is the control that proves the
  other two are wrong.

  **Half fixed the same day, and now measured.** The screen says "I don't know"
  instead of "no": in those two cities a lot that falls short of the number goes
  to the review queue rather than the red pile. It cannot turn anything green —
  a lot that fails on its own merits is still red, and that is tested.

  Ran it on 2026-09-01. **1,730 lots carry the flag; 62 changed verdict.** The
  first estimate written here was 605, on the grounds that 605 of the 988 fit
  the building inside their own boundaries. That was a ceiling and it was much
  too generous: fitting the building is necessary, not sufficient. Of the 1,668
  flagged lots that stayed red, 742 are below their zone's minimum lot *area*,
  542 are lots where no parking layout can be drawn at all, and 249 have no
  buildable envelope once the setbacks come off. Frontage was never the only
  thing wrong with them. **62 lots, all in Oregon City**, is what this is worth
  until somebody measures lot width properly.

  The other half is still open and is the real fix: measure lot width the way
  the code defines it, across the middle of the lot, and judge these properly.
  Agent work. What was deliberately *not* done is simply deleting the rule in
  those two cities, which would have moved all 988 straight into the pool of
  buildable lots — buying back some we are wrongly rejecting at the price of an
  unknown number we would then be wrongly accepting. A screen that says yes
  when the answer is no is worth much less than one that says no too often.
  Which cities get the softer treatment is frozen in a test, and a city earns
  it only with a written reason, never by being left off a list.
- ~~**7,499 lots are dropped for having no street, and 4,491 of them have a
  house on them**~~ — checked 2026-09-01 and the screen is right. A lot with a
  house and a mailing address that our map says has no street looks like a bug,
  so it got measured: for each of those lots, is there *another property*
  between it and the road? For 6,947 of 7,499 — nine in ten — there is. They
  are houses reached down someone else's driveway on an old easement, and every
  code we have read says a lot has to touch a public street before anything can
  be built on it. Red is the right answer. The remaining 552 have nothing but
  road in the gap and are genuinely being missed; they are lots on very wide
  arterials. Not worth chasing: to collect 552 by relaxing the rule we would
  have to start treating a street 90 ft away across a neighbour's front garden
  as this lot's frontage for the other 6,947. Recorded in
  `audit_landlocked.py` so nobody has to ask again.
- **"Reaches with no field" refusals**: e.g. Wood Village's forward-access
  rule applies to the pod and the data model has no field to hold it — model
  extension, batched with the next such find.
