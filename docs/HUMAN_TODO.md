# Human TODO — things only Steph (or another human) can move

This is the standing list of decisions, phone calls, and readings that the
agent cannot do alone. The agent maintains it: items get added when work
surfaces them, and struck through (with a date and what happened) when they
close. Items are ordered by how many lots ride on them, biggest first.

Pipeline state when last updated (2026-09-03, after your two answers — the
Clackamas drawing and the coarse elevation map — were built and run):
**green 16,530 · review 12,901 · red 262,540** across 291,971 lots in **14**
cities laid out with real site plans. Greens by city: Portland 12,678 ·
**Gresham 1,820** · Oregon City 735 · Milwaukie 622 · West Linn 288 ·
**Troutdale 125** · unincorporated Clackamas 113 · **Wood Village 95** ·
Wilsonville 53 · unincorporated Multnomah 1.

**Fourteen is fourteen of eighteen.** Four places are switched off and never
reach the screen at all — Lake Oswego, Maywood Park, Rivergrove and Johnson
City. Lake Oswego is 16,300 lots and 96% of that excluded land, and whether it
should still be excluded is **item 16**. The other three are 556 lots between
them. Noted here because a city that is switched off does not appear in this
table as a zero; it does not appear, which is how it stayed invisible for six
weeks.

**Your two answers nearly doubled the green list and cut the review queue by
61%.** Green 9,572 → 16,530. Review 32,794 → 12,901. They did it in opposite
ways, and both are worth understanding:

- **The elevation decision produced +7,360 greens, which is the forecast to the
  lot** — Portland 5,320, Gresham 1,820, Troutdale 125, Wood Village 95, exactly
  as the estimate said on 2026-09-02. Three cities that had produced nothing for
  the life of this pipeline now produce something.
- **The Clackamas drawing produced no greens at all. It took 402 away, and that
  is the point of it.** The county had 515 greens before today and they were
  resting on a parking layout nobody had drawn — with no aisle width, the screen
  skipped the parking test for that city entirely and graded its lots on the
  building alone. Now the test runs: of 23,934 county lots, 5,342 can seat a
  legal court, 19,398 are red, 4,423 are in review, and **113 are green and mean
  it.** The 17,486 lots that had been unanswerable are answered. Losing 402
  greens that were never tested is the honest trade for being able to trust the
  113 — and the county was, before today, the only city on the map graded that
  way.

**Wiring six Clackamas cities' overlays cost 65 greens and all 65 are
Wilsonville** — 118 down to 53. Every other city came back byte-identical,
including Milwaukie, whose greenway overlay kills 131 lots outright and whose
habitat and wetland layers flag many more: none of them was green to begin
with. That is the shape to expect from an environmental screen. It is a filter
laid over land that has already passed everything else, so it either lands on
lots that were going to fail anyway, or it lands somewhere concentrated. In
Wilsonville it landed on Villebois, where more than half the greens sat inside
a resource boundary nothing had been checking.

The run before this one (the sloped setback, the 29 recovered zones and the
minimum-density floor) was measured the same way, and the results are still
worth keeping.

**The 76,752 recovered lots produced zero greens.** 41,227 of them survived the
structural filters and reached a measurement for the first time; 38,134 came
back red on a real constraint and 3,093 landed in the review queue — Portland
2,981 of them, then Gresham 79, Happy Valley 18, and single figures in
Troutdale, Wood Village and unincorporated Multnomah. Not a disappointment, and
not an accident either: every recovered zone was ported as `needs_verification`,
which routes to REVIEW by design, so a green was arithmetically impossible on
this run. What was bought is the ability to see them at all. Verifying those 29
zones against the page is what turns 3,093 review lots into an answer.

**300 greens were lost, and only 109 of them are the density floor.** Those 109
are all Oregon City, all correct, and all sitting in review rather than red
because the city divides by *net* developable area and nothing here surveys
that: a lot that fails on gross area might still pass. The other 186 are
Milwaukie, and they are the sloped setback doing its job. Milwaukie's table
prints a 5 ft side yard and, four rows below, a 45-degree height plane starting
at 20 ft above the *yard line*. A 26 ft pod therefore stands 11 ft off the side
lot line, not 5, and 183 of those lots can no longer fit a building, its
parking and its drive between the new lines. The number the table prints was
never the number that binds.

13,156 lots in total are now flagged as too big for their zone's density floor
— Portland 10,899, Gresham 1,574, Oregon City 480 — but 10,512 of those were
already red for other reasons, so the floor is the deciding factor on 2,644.

The review queue now says why each lot is in it. Of the 12,901:
sewer unconfirmed 5,713 · slope 4,640 · unverified zone 3,529 · density floor
2,644 · overlay 2,586 · tier C 894 · suspect geometry 414 · frontage unmeasured
18. A lot can be held by several at once. Slope fell 17,539 → 4,640 because the
coarse map now answers; sewer fell 18,127 → 5,713 mostly because Clackamas lots
that were waiting on a sewer answer turned out to have no legal site plan
either, and a red verdict outranks a queued one.

**The single biggest reason a lot is red now says what it is, and it is not
what it looked like.** 153,910 lots fail because no site plan can be drawn on
them — more than every other reason combined. Until 2026-09-03 that was one
undifferentiated pile. It is now broken out, and the breakdown changes the
conclusion:

| where the plan gives out | lots |
|---|---:|
| no room for the **building** | 1,203 |
| building fits, no room for a **parking court** behind it | 134,152 |
| building and court both fit, no room to **drive past the building** | 18,393 |
| a plan was drawn and rejected on stall count | 87 |
| the setbacks leave no buildable ground at all | 75 |

**The land is not too small for the product. It is too small for the parking.**
On 1,203 lots out of 153,910 the building itself does not fit. On the other
99.2% it fits and the cars have nowhere to go. That is a different problem, and
it is not one more code reading will solve.

Measured on the lots that fail for want of a court: the median lot has **23 ft
of usable ground behind the building**, and the layout needs **42** — a parked
car is 18 to 19 ft and the drive aisle to reach it is another 23 to 24. A car
fits on most of these lots. A car plus the lane you drive along to reach it
does not.

**So the obvious question was asked and answered: what if the cars backed
straight out onto the driveway, the way they do at a house, with no drive aisle
behind them?** That was run through the real layout engine on a random 20,000
of the affected lots, changing nothing else — same building, same driveway,
same open space, same four-stall minimum. **About one in eight would draw a
complete plan: roughly 17,000 lots.** Worth having, and far short of the
134,152, because a second wall stands right behind the first — of the ones that
still fail, 43% now fail for want of the 12 ft to drive *past* the building,
and 38% do not have even 20 ft behind it. Nothing here is a claim that any city
allows aisle-free parking; it is the size of the prize, so that reading the
parking chapters for it can be priced against what it would return.

**And the same question was asked of the driveway, with the same method and a
clearer answer: no.** Five cities publish two driveway widths — a wider one for
a drive cars use in both directions and a narrower one for a drive that runs
one way — and the screen draws the wider one, because a single driveway in and
out of a rear court carries traffic both ways. That is the conservative reading
and it costs real frontage: 24 ft in West Linn, 20 in Happy Valley and
Troutdale, 22 in Tualatin. So every one of those cities was re-laid out at its
own one-way figure, everything else untouched, on all 162,533 evaluated lots.

**It moves 486 lots off red, and not one of them is in Portland.** West Linn
279, Happy Valley 108, Troutdale 89, Tualatin 10 — those are the lots held by
nothing but the site plan today, so a narrower lane would release them (to
review or to green, depending on what else they want). Portland appears to
gain another 1,466, and that number is not offered: Portland's one-way figure
is 9 ft, and this project decided long ago that a car needs 12 whatever a code
says. Buying 1,466 lots by drawing a lane narrower than a car is not a trade
worth making, and it is left on the table deliberately.

**486 out of 18,393.** That is the useful part. The driveway blocks 18,393 lots
outright and would block another 66,000 if the parking aisle question ever went
our way — and reading every city's driveway rule at the narrowest width its own
code allows releases 2.6% of them. The lane is not an encoding problem. Nothing
left to read here changes the picture, which is why the next paragraph is the
only lever left.

**What this puts to you is a product question, not a code question.** Every
lever in the list below is worth what it is worth, and none of them touches
this. The screen lays out one arrangement — building across the front, one
driveway down the side, parking in a court at the back — because that is the
arrangement these codes are written for. The inventory is telling us that
arrangement wants a deeper lot than Portland-area lots have. Where the cars go
is worth more than any remaining number on this list, and it is a decision
about the building, not about the rules. Nothing needs deciding today; it is
recorded here because the screen can now prove it.

---

## If you approved every item below, could you trust a green lot?

Asked directly on 2026-09-01. The honest answer is **not yet, and the gap is
not mainly on this list.** Working the list is necessary and it is not
sufficient. Six things stand between a green verdict and a lot you could buy
on it, and only the first is a queue item:

1. **Nothing is signed.** Not one encoded number has been read and confirmed by
   a person (item 7). Every green today rests on an unreviewed reading. This is
   the biggest single item and it is *work*, not a decision — you cannot approve
   your way past it in an afternoon.

   **It got one degree less frightening on 2026-09-07 and not one degree
   shorter.** Every number in the corpus was read a second time by a machine
   reader that was shown the page and deliberately not shown our answer, and
   1,845 of the 1,845 it could score came back matching. That is real evidence
   the books are not full of typos — and it is not a signature and does not
   substitute for one. A second reading confirms two readers agree; signing is a
   person taking responsibility for the reading being right. The full result,
   the six corrections it produced and the eight questions it could not settle
   are **item 11**.

   Counted exactly, and the honest total is smaller than it looked: **2,204
   numbers across 15 code books** (re-counted 2026-09-03; it includes the two
   Clackamas aisle values added that day, and the per-city split is the table in
   item 7). The number quoted before was 2,350 across 19, which included four cities the screen does
   not cover at all — Lake Oswego (excluded by your own 2026-07-24 call on the
   Mountain Park PUD), plus Johnson City, Rivergrove and Maywood Park, which are
   too small to be under the state's fourplex mandate. Lake Oswego alone is 132
   values, most of a signing session, and the queue was cheerfully listing it.
   It now marks those four rows *switched off* rather than hiding them, so the
   decision stays visible and nobody re-does it by accident.

   Two of the fifteen books — Fairview and Happy Valley — cannot be started
   until item 10 is answered. The other thirteen, including all of Portland and
   Gresham, are ready now.
2. **84% of greens rest on one legal argument** about a parking dimension no
   city wrote down (item 3, corrected on 2026-09-01 to include Portland). The
   argument is good. It is still an argument. The share went *up* on the
   2026-09-02 run even though the count went down, because the greens that
   disappeared were mostly in cities that do publish an aisle.
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
   item any more.** Gladstone was wired on 2026-09-03 — it had no green then
   either, and that turned out to be the wrong test: all 121 of its lots are
   held by signing, 35 of them by signing alone, and 51 sit on resource land.
   Tualatin was wired the same day off the city's own adopted layers, which
   closes this item: **every jurisdiction the screen grades now has an
   environmental check**, and the exemption list is empty for the first time.

   Now measured, on a full re-run finished 2026-09-02: wiring them **cost 65
   greens**, all of them Wilsonville, where the resource boundaries fall across
   Villebois. The habitat layer in unincorporated Clackamas is by far the
   largest, touching 6,853 lots on its own; Milwaukie's four layers together
   touch 832 and its greenway kills 131 outright — and not one of those was
   green before. That is the whole of the 2,820-green exposure resolved: not
   2,820 lots lost, but 2,820 lots that had been graded blind and have now
   actually been looked at, and 65 of them did not survive the look.
4. **No green has ever been checked against a real answer.** The one back-test
   run measured the opposite direction — of fourplexes that really were
   permitted, did we flag the lot? (60%.) Nobody has taken a green lot to a
   planner and asked whether we are right. Until that happens the accuracy of
   a green is an estimate, not a measurement.
5. **A green means the lot passed the standards we test, and we test 23 of the
   47 kinds we record.** Measured 2026-09-07. The untested 24 hold 400 real
   numbers, and while some are honest inventory — the parking geometry is
   waiting on a layout stage that does not exist yet — a rule nobody checks
   cannot fail a lot that ought to fail it. The largest is the corner-lot street
   setback, and it is untested for a stated reason: nothing in our data says
   which lots are corners. This is **item 12**, and it is the one gap on this
   page that could make a green *too generous* rather than too cautious.
6. **Nine tenths of our footnote decisions are "this does not apply to us", and
   until 2026-09-07 nobody had ever checked one.** 784 decisions; the rule was
   only that a reason exists. They were read back blind that day and the news is
   mostly good — the readers agreed with 406 of 584 outright, and of the 71 they
   disputed in the direction that could hurt, nearly all reach only districts
   where a fourplex is already forbidden, or state limits our small building
   cannot come near. **Three were real, and all three failed the same way**: the
   written reason says a district is not in our files, and it is. That is a
   sentence that was true when somebody wrote it and was quietly falsified when
   somebody else encoded the district. This is **item 13**; the check that
   re-asks all 784 of those reasons now exists, so this particular rot is
   watched rather than merely fixed.

The cheapest thing that would change this, by a wide margin, is **(4)**: pull
twenty greens across three cities and have a land-use planner or attorney rule
on them. That converts every number on this page from a guess into a rate, and
it costs one person a few days.

---

## 1. ~~Read one drawing: Clackamas County's parking detail~~ — **DONE, BUILT AND RUN 2026-09-03**

**You read it. Twenty-four feet at 90 degrees.** It was the single biggest
unlock left and it was half the entire review queue.

**Measured after the run, and the result is not the one this entry predicted.**
It predicted 17,486 lots moving; 17,486 lots did move, and **none of them moved
to green.** The county went from 515 greens to 113. That is not a failure of the
reading — it is what the reading was for. Until today the screen had no aisle
width for Clackamas, so it skipped the parking test for the whole county and
graded those lots on whether the building alone would fit. 515 lots passed a
test with a hole in it. Now all 23,934 county lots get the same test every other
city gets: 5,342 can seat a legal parking court, 19,398 are red (13,651 of them
because no court can be drawn at all), 4,423 are in review, and 113 are green
on a plan that has actually been drawn. **The county stops being the one
jurisdiction on the map whose greens meant something different from everyone
else's.**

The problem was never that the county was silent. Its rule book says parking
must match the zoning code AND the standard construction drawings, the zoning
code hands the aisle to the Roadway Standards, and those hand it to Standard
Drawing P100. The chain was complete and it ended in a picture. The stall size
was readable because it is printed in the drawing's title block as text
(9 × 18 ft); the aisle is drawn inside the image, and the screen's evidence
rule is that a number has to be quotable from a line of text. So the county sat
unreadable for a month while smaller cities were finished.

It is encoded now as the first number in the corpus whose evidence is a
picture: the value carries your name and the date you read it, and it carries
no quote, because there is no line of text to point at. The system refuses to
let it carry both. That is weaker evidence than every other number in the file
and the difference is repeatability — nobody can re-check it without reopening
the drawing — so it is reported in the readiness ledger for the life of the
value rather than clearing.

What was **not** done: letting the computer read the picture. That would have
changed what a citation means everywhere in the corpus, for one number.

**The sheet also dimensions 45°, 60° and parallel, and those are not encoded.**
Not refused for lack of evidence — unbuilt. The screen lays out one shape, a
rear court with stalls square to the drive, so 90° is the only row it can use.
The angled rows buy a narrower aisle in exchange for a deeper stall, which on a
shallow lot is the difference between a plan and no plan; they become worth
encoding the day an angled layout is drawn. Written down so nobody has to
rediscover that the numbers exist on a sheet we already hold.

## 2. ~~One decision: may a coarser elevation map grade a lot green?~~ — **DECIDED YES, BUILT AND RUN 2026-09-03, +7,360 greens**

The single biggest number on this list, and it was one yes-or-no answer. You
said yes on 2026-09-03. The switch is flipped, and a column named
`slope_source` records which map answered on every lot, so any green that rests
on the coarse reading can be filtered back out in one step. Flipping it back is
a one-line change and a cheap re-run; nothing is built on it staying true.

**The run landed on the forecast exactly: 7,360 greens, split Portland 5,320 ·
Gresham 1,820 · Troutdale 125 · Wood Village 95 — the same four numbers the
estimate gave.** That is worth a moment's suspicion and it survives it: the
estimate was made by running the decision's own rule against the finished lot
table, so it was a count rather than a projection. What it could not know in
advance was whether anything downstream would take the lots back, and nothing
did. Three cities that had produced zero green lots for the life of this
pipeline now produce 2,040 between them.

The reasoning as it stood before the decision is kept below, because the 1.5%
is the number anyone will want when a coarse-map green turns out to be steep.

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
**7,360 lots straight to green**, and it would be **wrong about 1.5% of the
time** — roughly 110 of those 7,360 would turn out, on a site visit, to be
steeper than they looked. It is wrong in the safe direction the rest of the
time: it hardly ever calls a flat lot steep.

So the trade is: **+7,360 green lots (a 76% increase on the whole corpus),
against roughly 110 of them being duds you would discover on the first visit.**

(Re-counted 2026-09-02 against the current run, replacing 7,972 and, before
that, 7,231. The number is the strict one: lots where the coarse map is the
*only* thing holding them, with the ones that would still be stopped by a steep
reading, an odd shape, a missing sewer or an unsigned zone rule taken out first.
It breaks down as Portland 5,320, Gresham 1,820, Troutdale 125, Wood Village
95 — and Fairview's 198, which need item 7 as well, are not in it. Gresham lost
608 of them to the new minimum-density floor and to zone rules nobody has signed
yet; both are items on this list, so those lots are not gone, they are queued
behind something else. Portland's 5,320 did not move at all.)

- **Yes** ← *chosen* — flip one setting, re-run, those lots grade green like
  any other, and a column records that their slope came from the coarse map so
  anyone can filter them back out.
- **No** — they stay in the review queue, but now with a slope number attached
  instead of a blank, which at least makes the queue sortable.

Nothing else was blocked on this; it was purely how bold to be. Same shape as
the drive-aisle call of 2026-08-31, and the same reason it was yours: it trades
a small chance of wasted diligence for a large amount of pipeline. The error it
buys is cheap and self-correcting — one wasted site visit, discovered on that
visit — which is what made yes the cheaper mistake than holding 7,360 lots.

## 3. Three short emails: confirm the assumed 24 ft aisle — **13,353 greens, which is 81% of all of them**

**This entry said 985 greens until 2026-09-01. It was counting two of the three
cities.** Portland carries the identical assumption and had been left off.
Corrected here because the number changes what the entry is: not a tidy-up on
two small cities, but the single largest thing standing between this screen and
a green list you could act on. Re-counted after the 2026-09-03 run: Portland's
share rose from 7,358 to 12,678 because the elevation decision (item 2) turned
5,320 more Portland lots green, and every one of them is drawn to the assumed
aisle. **Answering item 2 made this item bigger.** It is now the largest single
item on the list by lots at stake, and it is three emails.

Portland (12,678 greens), Milwaukie (622) and Wilsonville (53) all publish a
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
number. Eleven cities now publish an aisle — Clackamas County joined them on
2026-09-03 at 24 ft — and 24 is the median, the mode and eight of the eleven.
Only two go higher, Troutdale and unincorporated Multnomah at 25, and between
them they hold 126 greens. If Portland comes back with 20 ft this gets
*cheaper*, not dearer.

These lots are filterable: the `geometry_assumed` column in
`lots_results.csv`, and the greens they produce are itemized in `summary.md`.

## 4. ~~One question for a building-code expert: accessible (ADA) parking~~ — **ANSWERED FROM THE CODE 2026-09-03: nothing is required, nothing moves**

The worry was that Oregon's building code makes one of this building's four
stalls an accessible one. If it did, that stall plus its striped aisle would eat
extra feet out of every parking court in all fourteen cities at once, and tight
lots everywhere would go red on the same day. **It does not.** Read end to end,
the code lets this exact building out of the requirement — and it is unusually
clear about it, clear enough that this did not need an expert to answer. No lot
moves. No court gets wider.

**Why, in one sentence.** A building only owes accessible *parking* if it owes
accessible *units*; a four-unit building normally would owe them, but the code
excuses any unit that is two storeys and has no elevator, which is every unit we
build — so this building owes no accessible units, and therefore no accessible
stall.

**The one fact the whole answer rests on: every unit is two storeys and there is
no elevator.** That is the product as designed (`footprints.yaml`: 1,000 sqft
two-storey townhomes, ~500 sqft on the ground, four side by side). If the
product ever becomes single-storey flats, the answer flips and the cost is
real — see "What would reopen this" below. Nothing else matters here: not the
lot, not the city, not the number of stalls.

**The chain, for whoever checks it later.** Oregon is on the **2025 Structural
Specialty Code (OSSC)**, which is the 2024 International Building Code plus
state amendments, mandatory since 2026-04-01. Three sections, in order:

| § (2025 OSSC) | older books | what it says |
|---|---|---|
| **1106.3** | 1106.2 | Accessible parking — 2%, never fewer than one — is required in Groups R-2, R-3 and R-4 only where the building is *"required to have Accessible, Type A or Type B dwelling units."* |
| **1108.6.2.2.2** | 1107.6.2.2.2 | Four or more dwelling units in a single structure → every unit must be a **Type B** unit. *"Exception: … reduced in accordance with Section 1108.7."* |
| **1108.7.2** | 1107.7.2 | *"A multistory dwelling unit or sleeping unit that is not provided with elevator service is not required to be a Type B unit."* |

Run our building through it: four units, so 1108.6.2.2.2 catches it; every unit
is multistory with no elevator, so 1108.7.2 releases every one of them; zero
Type B units are required, so 1106.3 never fires. **Zero accessible spaces.**

**Three other doors, all tried, all closed.**

- **The residential code, if the permit goes that way.** A group of three or
  more attached units, each running foundation to roof, with a yard on at least
  two sides, is a *townhouse*, and townhouses up to three storeys are built
  under the **Oregon Residential Specialty Code (ORSC, 2023 edition; a 2026
  edition is expected 2026-10-01)**. The ORSC is based on the International
  Residential Code, which **has no accessibility chapter at all**. This is a
  second, fully independent route to the same answer — but it depends on how
  the building is designed and permitted, so the OSSC chain above is the one to
  rely on. It holds either way.
- **The federal Fair Housing Act.** It covers buildings of four or more units
  *with an elevator*, and the ground-floor units of buildings without one. HUD's
  own design manual says a multistory townhouse in a non-elevator building is
  not covered. Ours is not covered.
- **Oregon's own statute, ORS 447.233**, which sets accessible-parking counts
  independently of the building code. It reaches only *"affected buildings,"* and
  **ORS 447.210** excludes residential dwellings from that definition except for
  covered multifamily dwellings as the Fair Housing Act defines them — which,
  per the line above, we are not.

**What the fourteen cities say — every one of them read, none of them a
problem.** The pattern is uniform: cities set the *dimensions* and the
*placement* of an accessible stall and hand the *count* to the building code.
With the building code asking for none, none of these fire.

| city | what its code does | why it does not reach us |
|---|---|---|
| Happy Valley 16.43(G) | *"shall be provided for all uses consistent with the requirements of the Oregon State Structural Specialty Code and/or Federal requirements, whichever is more restrictive"* | "for all uses" is the strongest local wording anywhere in the corpus, and it still takes its number from the OSSC — which is zero |
| Gresham 9.0826(A) | *"All parking areas shall provide accessible parking spaces and accessible aisles as outlined in the Building Code, Chapter XI"* | same shape: universal-sounding, count deferred |
| Gresham 9.0852 (plan districts) | *"Minimum off-street parking for all uses is zero. If required by the Building Code, accessible parking spaces shall be provided regardless of the provisions of this subsection."* | explicitly conditional on the Building Code |
| Troutdale 9.105 | *"The required number of accessible parking spaces shall be in conformance with the applicable provisions of the State of Oregon Structural Specialty Code."* | count deferred outright |
| Milwaukie 19.600(E) | conform to the ADA, *"subject to review and approval by the Building Official"* | deferred to the Building Official. Note for item 5: a disabled space would count against Milwaukie's 4-stall **maximum**, not sit on top of it |
| Wood Village 350.065(D)(3) | *"Where required by this Code, Chapter 31 of the Uniform Building Code or the Americans With Disabilities Act, disabled parking spaces must meet the dimension standards…"* | conditional on a requirement stated somewhere else, and no row of Table 350-1A states one for Household Living |
| Tualatin 73C(7) | *"Accessible parking spaces must meet federal and state building code"* | deferred |
| Wilsonville def. 223 | its own ratio — one accessible space per 50 standard — but only in *"parking areas which contain ten or more parking spaces"* | the only city with an independent number, and our court is 4–8 stalls, below its own floor |
| unincorporated Clackamas, Roadway 320 | accessible spaces meet the Oregon Transportation Commission's standards | a dimension rule, not a count |
| West Linn 46.150(B) | its own count table — but only *"if any parking is provided for the public or visitors"* | resident parking is not visitor parking. **See the warning below** |
| Portland 33.266, Oregon City 17.zoning, Fairview 19.162, unincorporated Multnomah | accessible parking appears only in passing — where carpool stalls may sit, what a pathway must connect to, what a site plan must label | no count, no trigger |

**Two things to keep an eye on.**

- **West Linn is one design decision away from a real requirement.** Its rule
  turns on *"if any parking is provided for the public or visitors."* Our courts
  are resident parking, so it does not fire — but the moment a plan stripes a
  single guest stall in West Linn, the first row of its table (1–25 spaces)
  demands one accessible space *and* that it be van-accessible. That is a 17 ft
  bay in a court that is already the tightest thing on the lot. **Do not add a
  marked visitor space in West Linn without pricing it.**
- **Troutdale pays you to do it anyway.** Troutdale 9.100(G) reduces required
  parking by one space for every two units that are fully accessible. Not
  relevant while minimums are near zero, but it is the one city that treats
  accessibility as a credit rather than a cost.

**What it would have cost, had the answer been yes — and the parked question was
worse than this list thought.** The old version of this item guessed 13 ft,
taken from Wood Village's own Table 350-3. That is the wrong number. Under
ORS 447.233 and Gresham 9.0826(B)(1) alike, an accessible space is 9 ft with a
6 ft aisle, a van-accessible space is 9 ft with an **8 ft** aisle, and where
only one accessible space is provided **it must be the van-accessible one**. So
the real figure was a **17 ft first bay against a standard 9 ft — eight extra
feet**, not four, in every court in every city. Both West Linn 46.150(B)(4) and
the state statute say federal dimensions prevail where a local table differs, so
Wood Village's 13 ft would have been superseded anyway.

**What would reopen this.** Exactly one thing: **a single-storey unit.** OSSC
1108.7.1 is the other half of 1108.7 — in a building with no elevator, the units
on the *ground* storey still have to be Type B. Every unit of our pod is two
storeys, so no unit is a ground-storey unit in that sense. Change the product to
flats and those units become Type B, 1106.3 fires, and one van-accessible 17 ft
bay lands in every court on the map. A second, smaller trigger: an on-site
rental or leasing office would be a place of public accommodation with its own
accessible-parking duty under the ADA.

**Honest limit on this answer.** This is a reading of the published code, not a
determination by a building official, and the building official has the last
word at permit. It is closed here because the sections are explicit and the
whole chain is quotable, and because leaving it open was distorting a screen
across fourteen cities. Worth one line of confirmation from the plans examiner
on the first real permit set — as a check, not a blocker.

**Sources.** 2025 OSSC §§1106.3, 1108.6.2.2.2, 1108.7.1–1108.7.2 (IBC 2024
base; same text and numbering confirmed against the IBC 2024 sections). 2023
ORSC scope and the IRC townhouse definition. 42 U.S.C. §3604(f) and HUD's Fair
Housing Act Design Manual on covered multifamily dwellings. ORS 447.210
(definitions) and ORS 447.233 (counts and dimensions). City text as quoted
above, all of it from the stored provenance corpus under
`flats/provenance/docs/or/`.

## 5. Business decision: Milwaukie legally caps parking at 4 stalls — **622 greens**

Milwaukie's code caps a quadplex at **1 parking space per unit — 4 total**,
which is exactly the marketability floor. Every legal Milwaukie site plan is a
minimum-parking plan; the 1.5-per-unit and 2-per-unit tiers are not something
that city will permit at any lot size.

Decision needed: **is 1 stall per unit marketable for this product?** If not,
Milwaukie's 622 greens should be deprioritized before any diligence money is
spent on them. No agent work either way — this is a product call. (Was 845
until the 2026-09-02 run; 186 of those lots turned out not to fit a legal site
plan once Milwaukie's side yard was read as a *sloping* height plane rather
than a flat 5 ft, which is a correctness gain, not a loss.)

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
sessions**, and in what order. Each session is you (or a delegate) reading
quotes against numbers — tedious, but each one is permanent.

**The order was wrong here until 2026-09-02, and it changed again on
2026-09-03.** It originally said "by greens at stake: Gresham and Happy Valley
first", which was wrong then because both cities had zero greens. Gresham now
has 1,820 — your elevation decision gave it them — so the reason it sits low on
the table has changed completely: not "nothing to reassure" any more, but "525
numbers, the largest book in the corpus, for 21 new greens". The table below is
re-measured against the 2026-09-03 run throughout.

Worked out properly — and signing turns out to do **two** different jobs, which
is why the order was easy to get wrong:

- **It makes today's greens trustworthy.** 16,530 lots are green on readings
  nobody has checked. Signing does not move them; it makes them worth acting on.
- **It creates new greens.** 1,129 lots sit in the review queue held by *nothing
  but* an unverified zone rule. Confirm the rule and they go green. (Or red, if
  the reading was wrong — which is the point of checking.)

  One caveat, checked 2026-09-02 rather than assumed: your signature does not
  reach the screen by itself. The screen reads a separate confidence flag on
  each zone, and flipping that flag plus re-running the last stage is a second
  step. It is a small mechanical one and it is agent work, not yours — but it
  does have to happen, and "signed" and "screening green" are not the same
  state on the same day.

| City | Numbers to sign | Greens it would make trustworthy | New greens it would release |
|---|---:|---:|---:|
| *state layer* | 3 | every city depends on it | — |
| **Portland** | 333 | 12,678 | 849 |
| **Fairview** | 154 | 0 | 150 |
| **Gladstone** | 41 | 0 | 49 |
| **Milwaukie** | 44 | 622 | 36 |
| Gresham | 525 | 1,820 | 21 |
| Wilsonville | 198 | 53 | 14 |
| unincorporated Multnomah | 134 | 1 | 8 |
| Oregon City | 72 | 735 | 0 |
| West Linn | 112 | 288 | 1 |
| unincorporated Clackamas | 91 | 113 | 0 |
| Troutdale · Wood Village | 233 | 220 | 1 |
| Happy Valley | 225 | 0 | 0 |
| Tualatin | 39 | 0 | 0 |

**Portland first, and it is not close** — 333 numbers covering 12,678 existing
greens (77% of all of them) and 849 new ones (75%), in a single code book.

**Spend the first hour of a Portland session on 21 words, not on 333 numbers.**
New on 2026-09-06, at `/flats/words`. Signing asks whether a number matches the
sentence it was taken from; that is the right question and it is not the first
one. These codes define ordinary words their own way — four of them give four
incompatible tests for "corner lot", and seven subtract seven different lists
from a "net acre" — so a number read perfectly out of its sentence is still the
wrong number if this city measures the sentence's words differently. Portland
has 21 such words, and 758 of its encoded values are measured in them. Answer
those first and the 333 signatures underneath them stand; answer them after,
and a single "they measure it from the building line" costs you the session.
The other three cities on the short list are 26, 19 and 23 words. Nothing here
is a code reading in the usual sense — most cards are a glossary entry beside
our own standard, and the answer is usually "yes, the same thing".

**One document stands behind 118 of that session's numbers: Portland's
Chapter 33.930, Measurements.** The word cards now show the lines of a city's own code
that hand a word to another chapter, and Portland's point at 33.930 from five
of its 21 words — 118 distinct encoded values, including every setback Portland
holds. Two of those words, *lot width* and *building height*, are defined
nowhere in the 296-entry definitions chapter we do hold; the code's answer to
both is "see Chapter 33.930". We do not have that chapter. Unincorporated
Multnomah defers to the same one for another 43 values.

**Fetched 2026-09-06, and it is now in the store** — 548 lines at
`or/multnomah/portland/33.930.txt`, declared in the Portland rule file. Nothing
to go and get. It reached the top of fetch triage the same day by the route
that queue had been blind to: it stands beside no standard anywhere in the
corpus, so it scored zero on everything the feed counted and sat 69th of 75,
and what actually reaches it is being handed the words 186,888 lots' worth of
numbers are measured in.

**What the Portland word session now does with it.** Five cards point at it —
*lot width* (5 values), *building height* (22), *setback* (90), *building* (12)
and *street* (26). Two of them, *lot width* and *building height*, are the ones
Portland's 296-entry definitions chapter is silent on, and 33.930 is the code's
own answer to both: §33.930.050 Measuring Height and §33.930.100 Measuring Lot
Widths. Rule those two against the chapter rather than parking them.

Note that Portland mostly does not cite a section. Seventeen lines across the
corpus name 33.930, and twelve of them say only "See Chapter 33.930,
Measurements" — the chapter has eighteen sections and the reader is left to
find the right one. Five name a section: 33.930.100 for a cottage cluster's
lot width (33.110 and 33.120, and unincorporated Multnomah's copy of 33.110),
and 33.930.150, Measuring Top of Bank, twice inside the definitions chapter.

**Then Fairview, which the elevation decision promoted from nowhere to second
place — with a catch.** It was on the previous version of this table at zero and
zero, because its lots were held by the coarse elevation map *and* by unsigned
zone rules and the map came first. The map is answered, and all 198 of
Fairview's waiting lots are now held by the signature alone — 150 of them by
nothing else whatsoever. 154 numbers for 150 lots is the best ratio on the
table by a distance.

The catch is that **Fairview cannot be signed today.** Two of its zone codes,
`R/SFLD` and `RM/TOZ`, are not in any code book, so two of its values have no
sentence to read against — that is item 10, one phone call, and it now gates
the second-best signing session on this list. Item 10 was described below as
blocking two cities that were "nowhere near the top of this table". After
2026-09-03 that is no longer true of Fairview.

Then Gladstone, the same shape at smaller scale and with nothing in the way: no
greens today, 41 numbers, 49 lots, and every one of its values already quoted.
Then Milwaukie. **Those four are 572 numbers — a quarter of the job — and they
carry 13,300 of the 16,530 existing greens and 1,084 of the 1,129 new ones.**

Everything below that can wait for a reason. Gresham is the interesting case
and the reason has flipped: it used to be "525 numbers that reassure nothing",
and now it has 1,820 greens to reassure. But its *review* queue has drained
from 2,549 to 729 and only 21 of those are held by a signature, so the case for
Gresham is now purely about trusting greens it already has — a real reason, and
a weaker one than Portland's identical case at seven times the size.

**Item 10 used to be irrelevant to this table and stopped being so on
2026-09-03.** It blocks Fairview and Happy Valley from signing at all, and
Fairview is now second on this list. Happy Valley is still far down it.

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

## 10. Three zone codes nobody can look up — **454 lots, and after 2026-09-03 the gate on the second-best signing session**

**This item was promoted by the elevation decision.** It used to be a tidy-up on
two cities with nothing at stake. Fairview's 198 waiting lots are now held by
their unsigned zone rules and nothing else, and Fairview cannot be signed while
two of its zone codes have no page to read — so one phone call to one city
stands between item 7's second session and 150 green lots.

Every lot on the county map carries a zone code, and for all but three of them
we can open the city's code book and find that code written down. These three
are not in any code book:

| Code | Where | Lots | What we assumed | Green today |
|---|---|---|---|---|
| `R/SFLD` | Fairview | 228 | it means the city's R-10 zone | 0 |
| `RM/TOZ` | Fairview | 225 | it means the city's RM zone | 0 |
| `R20CC` | Happy Valley | 1 | it means the city's R-20 zone | 0 |

`R/SFLD` looks like a leftover from before Fairview rewrote its code in 2024 —
the regional map still prints the old label. `R20CC` is Happy Valley's R-20
with two extra letters nobody here can account for. Both are plain
what-does-this-mean questions for a city planner, and one phone call to each
city probably closes both.

`RM/TOZ` is the one that is actually interesting, and it got worse the more we
read. `TOZ` is real and it is in the code — Fairview's **Townhouse Overlay** —
so this is not a mystery label, it is a base zone with an overlay painted on
top. The problem is what the overlay does. Fairview's dimensional table gives
the Townhouse Overlay its own column, and in the row for a four-unit building
that column reads **"NA"** — the overlay states no lot size for our building at
all. The code says overlays exist to *"add or limit uses in the underlying base
district"*, and **limit** is the word that decides this: either the overlay
simply has nothing to say about a fourplex and the RM zone underneath governs
(what we assumed), or the overlay takes the fourplex away and those 225 lots
are not developable at all. The page supports both readings.

**Cost of getting it wrong:** none today, and that is luck rather than design.
All three codes are flagged *needs verification*, which sends every one of
their 454 lots to review no matter what else they clear, so not one of them is
green and none can become green while the flag stands. The flag is what is
holding it — not the reading.

**What we need from you:** one call or email to each city.
- *Fairview* — two questions in the same message: what does the `R/SFLD` label
  on the county map correspond to in the 2024 code, and does the Townhouse
  Overlay permit a quadplex on an RM-zoned lot or take it away?
- *Happy Valley* — one question: what is `R20CC`, and does the `CC` change any
  standard from plain R-20?

**Why an agent cannot do this.** We have read the whole code book for both
cities. The answer is not in it — a map label is not something an ordinance
defines, and the overlay question is a reading the city itself has to give.
Every other kind of gap in this project closes by finding the right document;
this one does not.

## 11. Eight readings a person has to make — the leftovers of a machine that re-read every number we hold

**On 2026-09-07 every encoded number in the corpus was read a second time, by a
reader who was shown the page, the zone and the standard and *not* shown the
number we hold.** 1,902 citations. 1,845 of them could be scored against what
we hold, and **1,845 agreed.** Not one confirmed wrong number in the whole
corpus.

That sentence needs its caveat said plainly, because it is easy to over-read:
this is a *second reading*, not a signature. It says two independent readings of
the same page landed on the same number. It does not say the page is the right
page, and it is not the thing item 7 is about. But it is the first evidence
anybody has that the corpus is not full of transcription errors, and it cost no
human time.

**What it did find was six corrections, and they were all the same mistake.**
In every case a number was quoted from a sentence that states an *exception*,
and held as though it were the rule:

- **Oregon City** — five zones' garage setback came from a cottage-cluster
  drawing note about how wide a garage *door* may be. The city prints a real
  garage setback row two tables away; the citation moved onto it, and picked up
  a 5 ft alley exception that had been hidden behind the wrong sentence.
- **Gladstone** — three zones had the identical misreading of the identical
  sentence, and Gladstone has no real garage row to move to. Reading the whole
  chapter for the word "garage" returns five more sentences and not one of them
  sets a garage back from anything, so the number came out.
- **Portland** — seven zones asked every site for 48 square feet of outdoor area
  per home, which is the figure for sites over 20,000 square feet. Under that
  size the code asks 36. A four-unit lot is almost never over 20,000, so nearly
  every Portland site was being asked for a third more open space than the city
  requires.
- **Gresham** — two zones were missing the looser setbacks the city prints for
  townhouses in a row that names them out loud; four downtown zones had the
  opposite problem and were claiming a party-wall relief the city gives to a
  building type that, by Gresham's own definition, ours is not.
- **West Linn** — four zones print two minimum lot sizes, one for detached and
  one for attached, and only the detached one was held. The city's definitions
  say which is which and the answer is the *plat*, not the walls.
- **Fairview** — one zone's front setback was a figure the code states for a
  single street, held across the whole zone.

**None of the six changed a single lot's verdict, and the reason is not luck.**
Three of them are on standards the screen records and does not yet test at all
-- the garage door and the outdoor area. The other three only apply if the four
homes are sold on four separate lots, and the two building designs we screen
with are both drawn on one. So the corpus was wrong in exactly the places
nothing currently reads.

That cuts both ways and both halves are worth saying. The good half: an audit
of this size usually turns up transcription errors by the dozen and this one
found none. The uncomfortable half: **six of the standards we carefully
transcribe are standards the screen never asks about**, which is its own
finding, and it is why (h) below is last on the list and still on it.

### What is left for you

Eight questions the machine could not answer without ruling on something. The
honest headline is that **not one of them is holding a green lot today** — they
are debts that come due when signing starts, which is item 7.

| # | The question | Where | How much land the chapter reaches |
|---|---|---|---|
| a | Does splitting the plat move our building into the "townhouse" rules? | Gresham | 28,873 lots citywide |
| b | Is a menu of three permitted distances a minimum? | Fairview VA | 2,456 lots citywide |
| c | Which column of the Frog Pond table governs an RN lot? | Wilsonville | the city's 53 greens |
| d | A zoning code that asks a building to be at least 25 ft *tall* | Troutdale MU-3 | 5,139 lots citywide |
| e | Three rural lot minimums whose cited page prints no figure | unincorporated Multnomah | 2,855 lots |
| f | A setback stated only on a map we have never opened | Milwaukie R-HD | one zone of 622 greens |
| g | One table cell answering three different questions | Portland IR | one zone |
| h | Portland's either/or garage rule | Portland RM2-RX | four zones of 195,708 lots |

The right-hand column is how big the *chapter* is, not how many lots the answer
would move -- which is zero today, for every row. It is there so the eight can
be ranked against each other, not against item 3.

**(a) Gresham — does splitting the plat move us into the townhouse rules?**
Gresham prints two sets of standards, one for a quadplex and a looser one for
townhouses, and the looser set matters: it is the difference between a 10-foot
side yard and a 5-foot one. Gresham's own dictionary says a quadplex split onto
four lots "is considered a quadplex" — so the split does *not* buy the townhouse
numbers. Three places in our Gresham file say exactly that. One place, the
Springwater district, encodes the opposite. Both readings are defensible from
the page and they cannot both be right. **This is the largest of the eight and
the only one where our file currently contradicts itself.**

**(b) Fairview VA — is a menu a minimum?** The code says front facades "shall be
set back from right-of-way a distance of either zero feet or 10 feet or 15
feet." That is a choice of three, not a floor, and 20 — the number we hold — is
not one of them; it is the next sentence's rule for lots on NE Halsey Street.
Two questions in one: does a menu like this bind us at all, and can anyone tell
us which VA lots front Halsey? Nothing in our data marks a parcel as being on a
named street.

**(c) Wilsonville RN — which column?** Seven of Frog Pond's numbers are quoted
from a 57-line table that has no row called RN. It has three: Large Lot, Medium
Lot and Small Lot, and the seven we hold are the Large Lot column throughout —
the strictest, which is the right way to guess but is still a guess. The same
city's Village zone has a street-side setback taken from a table with no
street-side column, off a row headed "Commercial Buildings." Wilsonville has 53
greens and this is the cheapest of the eight to settle.

**(d) Troutdale MU-3 — the only rule in Oregon a pod can fail by being too
short.** "Middle housing dwelling units shall have a minimum building height of
twenty-five (25) feet." Aimed by name at this building, in a district that
permits it. Our pod stands 26 feet — and that 26 is a number the design catalog
itself marks as *not taken from a drawing set*. One foot of margin on an
unconfirmed dimension. Two ways out and both are yours: confirm the pod's real
height, or accept that Troutdale's mixed-use district wants a taller building
than we make.

**(e) Three rural Multnomah lot sizes.** The cited sentence says the minimum lot
size is one acre "except as provided in" a list of other sections, one of which
is the planned-development chapter — and then prints no planned-development
figure at all. We hold one. Either somebody read the other chapter and the
citation never followed, or the number came from nowhere. Rural land we are
unlikely to build on, listed so it is not invisible.

**(f) Milwaukie R-HD — a setback that lives on a map.** The table's front yard
is 20 feet "except for properties identified in Figure 19.302.4," which get 5.
We hold the 20, which is the safe end. The map is a picture in a PDF and nothing
here can read it. If those 15 feet matter to a Milwaukie deal, somebody opens
the figure.

**(g) Portland IR.** Already known and already on the record: one table cell is
merged across three rows, so the same sentence has to answer front, side and
rear, and the rule inside it is "one foot for every two feet of building height,
but not less than ten." Our model holds a single number per yard and cannot say
that. Unchanged; repeated here because the second reading independently walked
into it.

**(h) Portland's either/or garage rule.** In four multi-dwelling zones the
garage entrance "must be either 5 feet or closer to the street lot line, or 18
feet or farther." Two permitted zones with a forbidden gap between them, and
which one a building takes is the architect's choice, not a fact about the site.
We hold 18 — the branch a building that cannot pull its garage flush must meet.
It is last on this list for a reason: **this standard is captured and never
tested**, in every city, so no lot anywhere has ever been graded on a garage
door. That is also why it should be settled before it ever is.

**What we need from you.** (a), (b) and (d) are readings — a planner or a
land-use attorney, thirty minutes each. (c) is one email to Wilsonville. (f) is
one PDF someone has to open. (e), (g) and (h) are ours, not yours, and are
recorded so they are not lost.

**A second machine pass, later the same day, walked into (c) and (g) on its
own.** The first reading had a blind spot: footnotes print *below* the table
they qualify, so no reader ever saw one. Seven hundred and thirty-one of the
numbers we hold sit under a footnote that does something, and those were read
again — this time with the footnote text on the card. The readers agreed with
every number, and two of the places they could not read at all were Wilsonville
RN and Portland IR, arrived at from a different direction with no knowledge of
this list. Two independent readings landing on the same two questions is the
best evidence available that the eight are the real leftovers and not an
artefact of how one reader was asked.

**It closed nothing new that costs you anything.** Of the 731, a footnote moves
the number on 299. Every one of those either already has the exception encoded,
already caps the lot at REVIEW instead of GREEN, sits in a zone where a fourplex
is forbidden outright, or loosens a standard we hold at its strict end — which
costs lots, never correctness. Twelve notes were left over and eleven of those
are relaxations we can afford to ignore. The twelfth is the subject of item 12.

---

## 12. One decision: a fifth of everything we have read cannot change an answer

**The finding.** We hold 1,775 zoning standards, each one quoted from a city's
own page and each one costing somebody — a machine or a person — the same care
to get right. **Four hundred of them are never asked for.** Nothing in the
screen reads them. A wrong number in any of the 400 would produce no wrong
answer, because no answer is computed from it.

Ninety-five of the 400 are deliberate and say so: the corner-lot street setback,
which the fit report names out loud as something it does not cost, because
nothing in our data yet tells us which lots are corners. That leaves **305
standards in 23 different kinds, across 14 cities, that are unread and where
nothing anywhere says so.** Roughly half of those 305 are parking geometry —
stall sizes, aisle widths, driveway approaches — waiting on a stage of the
screen that has not been built. The rest are scattered.

**Why this is on your list and not ours.** Twice now a machine audit has come
back with the same shape of answer: the corpus is sound, and the handful of
mistakes in it are in fields nothing reads. That is not luck. A reader gives a
citation the same care whether or not it matters, because nothing on the page
tells them which is which — so the errors accumulate exactly where nobody would
ever notice, and the effort accumulates there too.

**The concrete case, found this week.** Milwaukie caps middle housing at half a
parking space per unit on arterial and collector streets. We hold one space per
unit. Half a space is *stricter* than what we hold — on those streets a fourplex
is allowed two stalls, not four — so this is the one kind of mistake that can
call a lot green when it is not. It cannot do that today for a single reason:
the screen never looks at a parking **maximum**. It looks at the minimum beside
it. The number is right, the reading was right, the footnote was right, and it
sits in a drawer.

**Three ways to go, and the choice is yours:**

1. **Teach the screen to read them.** The cheapest three are the parking
   ceiling, the maximum front setback (27 standards in 8 cities — a rule that
   the building must sit *close* to the street, and in Wilsonville V, Portland
   CI2 and Troutdale MU-3 it pins the front setback to one exact distance), and
   minimum lot depth (32 standards in 6 cities). Each is about a day's work and
   each turns a drawer of numbers into a real check. Worth saying plainly: for
   our pod, with its parking court behind it, the maximum front setback would
   usually be satisfiable by sliding the building forward — nobody has checked
   that it always is, and "usually" is the reason it is on this list rather
   than settled. Adding checks makes the screen stricter, so expect *fewer*
   green lots, not more.
2. **Stop reading them.** Mark the 305 as inventory, exclude them from the
   review queues, and spend the reviewer's hours on the 1,375 that decide
   something. Fastest, and it means accepting that if we later build the check,
   those numbers get read again from scratch.
3. **Leave it and just make it visible.** Already done: the ledger is built and
   runs, so the list can never go quietly stale again. Nothing more happens.

**Our recommendation is (1) for the three named fields and (2) for the rest** —
the maximum front setback in particular is a rule our building can fail on a
real lot, and eight cities have one.

**No lot is wrong today because of any of this.** It is about where the next
hundred hours of reading go.

---

## 13. Three readings where our own written reason turns out to be false

**What was checked.** When a footnote in a zoning code does not apply to our
building, somebody writes down why and the note stops being mentioned. There
are **784 of those** on the record — nine tenths of every footnote decision we
have made — and until 2026-09-07 nothing had ever checked one. The rule was
only that a reason exists, never that it is right.

That is the one mistake that can call a lot buildable when it is not. A note
nobody has read *blocks* the lot. A note read and encoded leaves a number
somebody can compare against the page. A note waved away leaves nothing at all:
the standard underneath it keeps whatever value it had, one condition looser
than the code actually allows, and there is nothing left on the screen to
notice.

**How.** 584 of those decisions sit over at least one number we hold. Each was
turned into a card carrying the footnote's own words, the page of code around
it, and the list of standards it stands over — **and not our reason for
dismissing it**, because a reader shown "detached dwellings only" agrees with
it. Twenty-four readers worked them in parallel. Two questions each: does this
sentence reach a four-unit attached townhome, and if it does, does it make a
standard *harder* or *easier* to meet. Dismissing an easier rule costs lots and
never correctness — that is the trade this whole project makes. Dismissing a
harder one is the bug.

**The result.** The readers agreed with 406 and disputed 178. Of those, **71
were disputed in the direction that matters** — a restriction we waved away.
Every one of the 71 was then checked back against the code and against our own
encoding, and they sort into three piles:

- **Forty-odd close on the spot** because the note only reaches districts where
  we already record that a fourplex is *not allowed* — Gresham's industrial,
  commercial and two corridor districts, Troutdale's two commercial zones,
  Wood Village NC, Happy Valley MUR-M, Pleasant Valley NC-PV. A lot in those
  districts is already red on use, so nothing the note says can make it green.
- **Most of the rest cannot bind the building we build.** Footprint caps of
  40,000 and 100,000 square feet against our 2,000; storey caps of four and six
  against our two; height reductions that bottom out at 30 feet against our 26.
  The readers said so themselves.
- **Three are real, and all three are the same failure**: our written reason
  says a zone or a district is *not encoded here*, and it is.

### The three

**(i) Happy Valley SFA — a buffer we said we do not model, in a zone we do.**
The city's note reads: *"Where the SFA district abuts lower density residential
districts, the abutting yards shall have a 10-foot landscaped buffer area."*
Our reason for waving it away is "scoped to SFA, which this layer does not
encode." **SFA is encoded**, with sixteen standards, and it holds a five-foot
side yard. Where the buffer applies that yard is really ten. This is the only
one of the three that could make a green lot wrong, and the thing standing
between it and a wrong answer is that nothing in our data yet says which lots
abut a lower-density zone — the same missing fact as the corner-lot question in
item 11. **What we need:** a ruling on whether a "landscaped buffer area" is a
building setback. We are not encoding that reading on our own, because turning
prose into a number without being asked is exactly the habit this project
refuses.

**(ii) Gresham, the Rockwood mapped area.** A note says *all buildings* on
parcels with at least 100 feet of frontage on Stark, within 500 feet of two
named intersections, must have non-residential uses at the ground floor. Our
reason: "it marks a cell in a district this layer does not encode." All seven
districts it stands over are encoded, and four of them permit a fourplex. The
note is not scoped by use at all — it is scoped by a map we have never opened.
**What we need:** whether any land inside that mapped area sits in one of the
four. If it does, an all-residential pod is barred there and we would not know.

**(iii) Troutdale's mixed-use districts.** A note raises the street-side
setback from zero to eighteen feet on a corner lot whose driveway comes off the
side street. Our reason names two table columns "neither of which is encoded
here" — true of those exact columns, but the note reaches the mixed-use zones,
two of which permit a fourplex. Corner lots are the unmeasured fact from item
11 again; this is a third road to the same door.

### What was fixed without asking

One thing was unambiguous enough to correct outright. Gresham's residential
table carries a note reading *"Maximum front and street-side setbacks apply in
MDR-12, MDR-24, OFR, as provided for the Corridor Multi-family (CMF) District
in Table 4.0430."* The dismissal quotes the number that pointer lands on — 20
feet — and then declines it, leaving those three districts with no maximum
front setback while CMF, the district the sentence points at, carries one. The
20 is now recorded in all three, unsigned, pointing at both the note and the
row it borrows from. It changes no verdict today, for the reason item 12
exists: **nothing reads a maximum front setback.**

### What this says about the corpus

Worth saying, because it is the reassuring half. Six of the seventy-one turned
out to be the *reader* misreading and our written reason being better than the
challenge to it: unincorporated Clackamas requires covered parking above 3,500
feet *of elevation*, not 3,500 square feet; two districts the reader thought we
had skipped genuinely do not exist in that county's code; Lake Oswego's
sloping-lot height rule lands exactly on the number we already hold. A reason
written months ago survived a hostile reading it could not see coming.

**And the shape of the three failures is one shape.** Every one is a sentence
that was true when it was written — the district really was not encoded then —
and quietly stopped being true when somebody encoded the district and never
came back to the footnote. One of the reasons we read says so out loud: *"This
used to be dismissed on the grounds that CC and MC were not encoded here, which
stopped being true when both were encoded on 2026-08-21 and nobody came back to
the sentence."* Somebody caught it once, for one note, by hand.

**Now something watches for the rest.** Of the 784 dismissals, 49 argue about
our own files rather than about Oregon — those are the only ones that can go
stale — and ten of them name a district the corpus holds today. Seven of those
ten stand over land where a fourplex is actually permitted, which is the only
way a false sentence can turn into a wrong answer; the other three are wrong
sentences over districts already closed on use. That list is rebuilt from the
register every time it is asked, so it cannot quietly rot the way the reasons
it audits did. It is the agent's to work, not yours; the three above are on
this page because each needs a ruling only a person can give.

The full ledgers are `data/flats/dismissal_reading_2026_09_07.csv` (584 rows)
and `data/flats/stale_reasons_2026_09_07.csv` (49).

---

## 14. Two blind readings of the sentences nobody ever decided anything about

**What was checked.** Item 13 read back decisions we had *made*. This one reads
the sentences nobody ever decided anything about. In the fifteen code books we
hold there are about a thousand lines that state a measurement and that not one
of our numbers was taken from. Read end to end they are unworkable — most are
the second column of a table we took the first column of, or the same standard
written for a detached house.

So the machine did the one thing it is better at than a person: for every one
of those lines it compared the number printed on it against **every number
that city holds for that kind of standard, in any of its zones**. A line
saying 35 feet in a city that records a 35 somewhere is bookkeeping — our
reader took it off a neighbouring row. A line saying 24 feet in a city that
records no 24 for height anywhere is a number this system has never seen, and
that is either a rule we skipped or a rule for a building that is not ours.
**542 lines came back in that second pile.**

That pile was then worked in two passes — different halves of it, and two
different shapes of question — by readers who were shown the page and,
deliberately, neither our number nor even which standard we thought the line was
about.

**Reading one — the near ones, line by line.** The 185 lines sitting in a
section we had already taken that very standard from. **150 agreed the line
does not apply to us, 6 could not tell, and 29 said it states a requirement our
building would have to meet.**

**Reading two — the unopened sections, whole.** The 347 measuring lines in
sections *nobody has ever quoted a single word of*. Asked one line at a time
these are unanswerable, because the sentence above the line is usually what
says which building it is about. Grouped into whole sections they are **144
questions**, and six readers answered all of them. **116 said nothing in the
section touches our building. 26 said something does. 2 could not tell.**

**All 29 and all 28 were then checked back against the code and against our own
files.** Fifty of the fifty-seven closed on the evidence. What follows is the
seven that did not, and then — because it is the more useful half — the shapes
the fifty closed in.

### ~~The one ruling that closes sixty-six numbers~~ — ANSWERED 2026-09-08

Three of the seven findings are about a **garage**, and all three stop existing
the moment you answer one question.

**Both of our two building designs park in a rear court. Neither has a
garage.** That is on the record in the design files and always has been. What
is not on the record anywhere is what follows from it: **we hold 66 garage
setback numbers, measured out of ten different cities' codes, and no part of
the screen reads a single one of them.** It is the largest such block in the
system — more than twice the next one — and every hour anyone has ever spent
reading a garage standard has bought nothing.

Two cities came back with the same gap, found two different ways:

- **West Linn** requires *"a minimum of 20 feet in length between the garage
  door and the back of sidewalk"*. We record nothing for it in West Linn, while
  Gresham and Wilsonville both record exactly 20 feet for the same standard.
  A reader raised it off the page.
- **Fairview** requires, in the VSF district — which does permit a fourplex and
  where we hold only nine numbers — a garage set 20 feet back from the front
  face of the building. Nobody read that page. It surfaced from a new check
  that asks which standards most of a city's neighbours regulate and this city
  does not.

**You ruled: no garage.** The exclusion is now written down where the screen
states what it does and does not charge a lot for — alongside the two standards
it already declared it leaves out — rather than being a silence anyone would
have to notice. Three consequences, all live:

- The 66 garage numbers are retired. They stay on the books, because they are
  correctly measured and cost nothing to keep, but nothing is owed on them.
- Both gaps above are closed: West Linn's driveway length and Fairview's
  garage setback are garage standards and do not reach a pod without one.
- The neighbours' check no longer raises garage standards, so its remaining
  output is signal rather than the same finding ten more times.

**The safety net you were owed.** The worry with this ruling was that it is a
statement about our product, not about Oregon, and would go silently wrong the
day the product changed. So it does not depend on anyone remembering: a test now
reads the building catalogue and fails the moment a design appears that parks
under the building. The ruling cannot outlive the thing it was about.

### One more that still needs you

*(Numbered as they were first written. (i), (ii) and (iii) are answered, below.)*

**(iv) Fairview: the front setback has to match the neighbours.** In an
"established residential area" — the parts of town platted before a date the
code names — *"When an existing single-unit dwelling on the same street is
located within 30 feet of the subject site, a front yard setback similar to
that of the nearest single-unit dwelling shall"* apply, never less than 10 feet
and never more than 40. Every Fairview zone that permits a fourplex holds a flat
10-foot front setback with us, which is the floor of that rule. So the rule can
only ever push our building further back — up to thirty feet further.

**What we need:** a ruling that this reaches a fourplex, and then it joins the
list of things we cannot answer without data — where the neighbouring houses
actually sit, which is the same missing fact as the corner-lot question in
item 11 and the abutting-zone question in item 13. It does not block anything
today; it is here so the third road to that same door is on the record.

### The three that are answered

**Fairview's ten percent open space — you said yes, and it is encoded.** The
number is on the record against Fairview's RM district, quoting the sentence
that states it, and it loads under the strict reader. It fails no lot: the pod
leaves ten percent of the site free on anything above about 2,240 square feet.
It carries a signature request like every new number, so it is a draft until
somebody signs it on screen.

One thing in it is worth knowing, because it is the kind of detail that decides
a case. Fairview's own driveway table distinguishes a *"quadplex"* from a
*"multiple-unit use of between four and seven dwelling units"* — the same
building, filed under two names, with a 10-foot minimum driveway under one and
20 feet under the other. The open-space rule says "multiple-unit developments",
and reading that to include our fourplex is the strict reading, which is the one
taken. The argument is written beside the number rather than left implied.

**Milwaukie's parking table — I reported this wrongly, and the correction
matters more than the finding.** I told you Milwaukie prints an aisle table we
never took. Our own files already contain a reasoned refusal of exactly that
table, and of Portland's and Wilsonville's, each one quoting the sentence in
the city's own code that puts our building outside it. Milwaukie's parking
chapter opens by excluding middle housing, and a quadplex is middle housing
there. Portland's aisle table sits in a section whose applicability excludes the
very standard our building is judged under. Three cities, three exclusion
sentences, all already on the record.

This is the failure this project has a standing rule against — *"the code states
nothing here" needs a whole-document search* — turned around and pointed at our
own corpus. The reading that produced the finding never looked at what we had
already decided. Nothing in Oregon changed; a claim about us did.

**And you ruled on the real question underneath it: incorporate the aisle.**
That is now done, and it is the largest correctness change in this system in
weeks. See below.

**Oregon City's R-2 — you asked the right question, and it answers itself.** You
said we should be able to pull the definitions of those terms and see whether
our building meets them. We can, and it does:

> **17.04.989** — *"Quadplex" means four attached dwelling units on a lot.*
> **17.04.780** — *"Multi-family residential" is a structure or structures
> located on one lot and containing **five or more** total dwelling units.*

Our pod is four attached units on a lot. It **is** a quadplex by the first
definition and is **excluded** from the second by the unit count. And R-2 lists
*"D. Quadplexes"* among its **permitted** uses — not conditional, and not a
multi-family-only district; it is simply Oregon City's high density residential
zone. So the one-word reason the district was thrown out on — "that is the
multi-family zone" — was not a judgement call we needed to make. It was a wrong
premise, and the city's own dictionary settles it.

**R-2 is now encoded**, fourteen numbers off Table 17.12.040 and 17.12.050, each
quoting the row it came from, in both the FLATS corpus and the older pipeline
that does the county runs. It is a permissive district on paper: 6,000 sq ft
minimum lot, 85 percent coverage, 35 feet, a 5-foot front yard and a 10-foot
rear yard — looser than any Oregon City district we already screen.

**One thing in it is genuinely new, and it runs backwards.** R-2 sets a minimum
density of 17.4 homes per acre. Four homes at that rate means the lot has to be
**no bigger than about 10,000 square feet** — so in R-2 a lot can be *too large*
for a fourplex, which is the opposite of every constraint in this system. The
usable window is roughly 6,000 to 10,000 square feet. Its matching 21.8-per-acre
*maximum* would have squeezed from the other side, and R-2 is the one Oregon
City district whose code forgot to exempt fourplexes from it — but state law
bars a city from applying a density ceiling to a quadplex at all, and we already
carry that rule, so it never reaches a lot.

**What this does not tell you** is how much land it opens up. Our lot inventory
does not currently carry Oregon City parcels, so nobody can count R-2 lots yet.
The district is ready for the day it does.

**And it will show amber, not green, until somebody signs it.** Every number in
it is a draft — read once, by me, off the table. The screen is set to send R-2
lots to *review* rather than let them come back buildable, which is how the
thirty-five districts added last week were treated and for the same reason: one
reading is not a check. It flips to green-capable when the signatures land.


### Two more that are real and are in a city nobody screens

Both are Lake Oswego, which you switched off on 2026-07-24 over the Mountain
Park PUD. They change nothing today. They are worth writing down because they
are the price of switching it back on:

- **Lake Oswego caps the total floor area of the whole project**, by a formula
  printed in all three of its residential tables: 3,000 square feet, plus 19%
  of however much the lot exceeds 5,800 square feet, plus an extra 600 to 850
  square feet for each unit that has a garage. Our building is about 4,000
  square feet of floor across two storeys. On a minimum-size R-7.5 lot the
  allowance is **3,323 square feet**, so the pod does not fit unless every
  unit has a garage. **We have no field for a floor-area cap of that shape at
  all** — the nearest thing we hold is a floor-area *ratio*, which four other
  cities use and this is not.
- **Lake Oswego sets an 18-foot front setback on steeply sloped lots**, and it
  says so three times, once per density band, each time naming "middle
  housing" — which in Oregon includes a fourplex. In six of its zones we hold
  a front setback of 10 feet or none, so this is stricter than what we have.
  It also turns on a phrase — "steeply sloped" — that **the Lake Oswego code
  we hold never defines**, so it would go to the word queue before it could go
  anywhere else.

### The fifty that closed, and how

These are the useful half, because they are what a person reading a page cannot
see and a file can. Between the two readings the same six shapes closed almost
everything:

- **A different table in the same chapter.** Two unincorporated Clackamas notes
  raising the side setback to 10 and 15 feet turned out to be footnotes to
  Table 315-4 — the table for seven districts we take no numbers from. We read
  315-2 and 315-3.
- **A district we do not hold.** Troutdale's 20-foot street-side setback is in
  the HDR (TC) column. Four of Milwaukie's five findings are in its downtown
  and innovation-area districts. Multnomah County's alarming *"buildings must
  be set back from all property lines a minimum of 1 foot for each foot of
  building height"* — 26 feet on every side, for us — is the **Open Space
  zone**, where a fourplex is not allowed at all.
- **A purpose paragraph, not a standard.** All four Gresham density findings
  quote the sentence describing what a district is *for*. Gresham's actual
  table prints **no maximum density** against "Duplex, Triplex, Quadplex,
  Cottage Cluster"; the 25 homes per acre the readers found belongs to
  townhouses on their own lots, and we already hold it that way, with the
  quote.
- **A menu, not a requirement.** Gladstone appears to require a minimum roof
  pitch and a garage or carport, which would have been serious — a
  factory-built module does not necessarily have either. It requires *"at least
  four of the following"* from a list of eleven, and porches, eaves, gables,
  offsets and street-facing windows are also on it.
- **A choice the applicant makes.** Portland's tree code appears to demand 40%
  of the site be tree area. The applicant may instead choose *"site area minus
  building coverage"* — which is whatever the building does not use, so it can
  never limit the building.
- **Already ruled, just not where the reader was looking.** Fairview's 70-foot
  no-build strip along Fairview Creek is real, and our file already says the
  creek corridors are handled as mapped ground rather than as a number. The
  reasoning quoted the narrower Clear Creek half and not this one, which is why
  it came back. It now quotes both.

And two that closed simply because we were already right: Gresham's 24-homes-
per-acre corridor rule was considered and declined on the record months ago;
Portland's 25-foot fourplex height sits inside the *affordable* option, which
requires half the units let at 60% of area median income.

### What your parking ruling turned into — and the false GREEN it uncovered

You said: *we need to incorporate parking aisle width.* Doing it turned out to
be the largest correctness change in this system in weeks, and it found a
separate bug on the way in.

**What was wrong.** When we worked out how much land a pod needs, we counted
the building and its front and rear yards and **nothing at all for the six
cars**. Both our designs park in a court behind the building, and that court —
a row of stalls plus the lane that serves them — is about **42 feet deep in most
of Oregon, deeper than the building itself**. We were sizing lots as though the
cars parked nowhere.

**What it costs.** Every one of the **120 zones where a fourplex is allowed now
needs 12 to 42 more feet of depth** than we were saying — 27 feet on average, and
not one zone escapes it. The range is the rear yard: a required rear yard is land
you are allowed to park on, in every Oregon code read for this, so the yard and
the court overlap rather than stack. A zone asking for a 25-foot rear yard is
charged only the 17 feet of court that reaches past it; a zone asking for no rear
yard is charged the whole 42.

**Where the number comes from, city by city.** Where a city states a stall depth
or a two-way lane width, we use the city's number and it can only push the
figure up. Where a city states none — Portland, Milwaukie and Wilsonville each
dimension a parking space for this building and deliberately state no lane, all
three on the record with the exclusion sentence quoted — we use the building's
own: an 18-foot stall and a 24-foot lane, which is the same figure our site
plans have always been drawn to. Refusing to answer for those three would have
been the wrong kind of caution. The pod still has to turn round.

**What is still not charged, and which way it errs.** The court's *width*. Six
stalls need about 54 feet across, and the driveway reaching them needs its own.
Both are unmeasured, and both can only make a lot need **more** than this now
says — so the figures above remain the optimistic end.

**The false GREEN found on the way in.** Separately, and worse: when a pod fits
a lot only by turning sideways, the screen was comparing the wrong two numbers.
It read the space actually available against the building's *narrow* dimension
instead of the long one it needed — passing a lot with 50 feet of room as
comfortable when the building wanted 56 and the lot held no such run anywhere.
That is exactly the failure this project exists to prevent, and it was live.
Fixed, with a test that reproduces the lot it happened on.

**Honest scope.** The per-lot grader is not yet the thing doing the county runs
— the older pipeline still does those — so **no lot changed colour today**. What
changed is that the planning view and the grader now answer the parking question
the same way, and the grader is right on the day it takes over.

### What was fixed without asking

Nothing in the code books, and one sentence in ours: Fairview's creek reasoning
now quotes the wider of its two no-build strips as well as the narrower, so the
next reader does not raise it a third time.

The rest is about how we work rather than about Oregon. **The reading list did
not know which cities the screen covers.** 26 of the 185 readings, and 8 of the
29 findings, were Lake Oswego and Rivergrove — an hour of reading with no lot
behind it. Every other queue in this system already drops or marks excluded
cities; this one, three days old, did not. It does now, and the count still
reports them, because a list that hides what it has excluded cannot be told
apart from a list that has finished.

A second check was built and run for the first time: **a standard that most of
a city's neighbours regulate and this city does not.** It found seven, of which
two were real — West Linn's driveway and Fairview's garage setback. Both are
garage standards, which is how the sixty-six numbers above came to be counted
at all.

One more thing about how we work, and it is the uncomfortable one. The
Milwaukie finding above was **my error, not a gap in Oregon**: I reported an
aisle table as untaken without checking what our own files already said about
it, and they said, in three cities, exactly why it does not reach us. The rule
this project has for reading Oregon — a claim that nothing states something
needs a search of the whole document — applies to our own corpus, and I did not
apply it. The blindness is deliberate and is what makes these readings worth
anything: the reader never sees our answer, so it cannot be talked into
agreeing. But that puts the whole burden of checking on the step *after* the
reading, and on this one I skipped it. No tooling change fixes that; the
discipline is to search our own files before writing "we hold nothing".

The full ledger is `data/flats/missed.csv` (1,206 lines). The readings are
`data/flats/missed_reading_2026_09_08.csv` (185 lines) and
`data/flats/chapter_reading_2026_09_08.csv` (144 sections).

---

## 15. One decision: our reader throws away a city's empty boxes, and fixing it moves every page reference we have saved

Found 2026-09-08, while checking which zones each city has that we have not
written down. Nothing here needs a phone call — it needs you to say whether it
is worth the disruption.

**What is broken.** Cities write their rules as tables: a row for each kind of
building, a column for each zone, and a letter in each box. In some cities an
**empty box is not missing information — it means "not allowed here"**. Lake
Oswego says exactly that in its own opening paragraph.

When our reader pulls a table off a web page, it usually keeps the shape and an
empty box stays empty. But when a table is very wide it gives up on the shape
and writes the boxes out one to a line — **and it throws the empty ones away
instead of leaving a gap.** That is worse than losing them. Every box after the
missing one slides up a place, so an answer that belongs to one zone can end up
filed under its neighbour.

**How far it reaches, and how far we can see.** We checked every use table in
every document we hold. **Exactly one is damaged** — Lake Oswego's, where about
two thirds of the rows are short — and every other one is intact. That is good
news and it is also the limit of what we can check: the test only sees tables
full of one-letter answers. A table of measurements with a blank in it would be
damaged the same way and would not show up.

**Why it is not just a fix.** Every number we have encoded points at a line in a
stored document — "this figure is on line 4,579". Re-reading the documents with
a corrected reader changes where the lines fall, so a share of those pointers
have to be walked to their new homes. We have a tool that does that walking, and
it deliberately refuses to touch a pointer that lives inside a test, because a
tool that edits an assertion until it passes has removed the reason for the
assertion. So some of it lands as hand work.

We also cannot tell you the exact size in advance. We keep the *cleaned-up text*
of each document, not the original web page, so the only way to learn how many
documents move is to re-fetch them and look. What we can say: **178 documents,
of which 129 came from web pages and could move; 49 came from PDFs and cannot.**
A rougher check — looking for the same wide-table shape anywhere in a document
rather than only in a yes/no table — narrows it to **44 documents that contain
such a table at all, 20 with uneven rows.** Treat those as an upper bound rather
than a finding: that looser check also accuses a Clackamas table we know to be
intact, because it cannot tell a box in a table from a short line of writing.
And the corpus is already carrying this debt — 173 of the 178 were read by a
version of the reader we have since replaced twice, so *something* will move the
next time anything is re-fetched regardless.

**What it costs to leave it — and this moved twice in one day, the second time
against us.** The damaged table is Lake Oswego's, and the first draft of this
item said it costs 93 lots today. Rebuilding the lot ledger the same afternoon
showed Lake Oswego is not being screened at all — **the whole city, 16,300
lots, is switched off**, for reasons that are now item 16 below — so the cost
looked like *nothing today* and the item looked cheap to leave alone.

Then encoding Clackamas County's medium-density districts the same evening
found the second one, and it is the kind the check above **cannot see**. This
item says in the paragraph above that a table of measurements with a blank in
it would be damaged the same way and would not show up. One has. Clackamas
County's Table 315-3 sets out standards for three zones side by side, and
several of its rows — including the one giving the required distance from the
back of the building to the rear property line — print **two** figures under
**three** headings. Either the third zone has no such requirement, or its
figure was thrown away and the other two slid over into the wrong columns. The
text we stored cannot tell us which.

**So the cost is no longer nothing.** It is **115 lots we cannot screen at
all**, in a zone that permits our building, blocked today, and we cannot even
confirm the reader is at fault without re-fetching the page — which is the
thing this item is asking you to decide. Everything else about that district
was readable and is now written down; this one row stopped it.

**The choice.**

- **Fix it and re-read everything.** Safest end state, and it also clears the
  two-versions-behind debt in the same pass. Costs a re-fetch of 129 documents,
  an unknown share of page references to walk over, and some hand work where
  those references sit inside tests.
- **Fix it and re-read only Lake Oswego.** Cheap, moves almost nothing, and
  makes the city's commercial half readable before anybody needs it. Leaves the
  rest of the corpus exactly as it is — including any measurement table that
  lost a blank without our being able to see it.
- **Fix it and re-read only the two documents we know are affected** — Lake
  Oswego's and Clackamas County's zoning ordinance. Cheap, moves little, and
  unblocks the 115 lots as well as making Lake Oswego's commercial half
  readable before anybody needs it.
- **Leave it.** Costs 115 lots that stay unscreenable, plus whatever the next
  wide table costs us silently.

**The middle option is now what I would do.** Yesterday I would have said wait
for item 16, because the only known damage was in a city we are not screening.
That is no longer true: there is damage in a county we *are* screening, it is
blocking real lots, and two documents is a small enough re-read to learn what a
re-fetch actually disturbs before committing to the other 127.

---

## 16. One decision: the largest city we have switched off was switched off for a reason about one tenth of it

Found 2026-09-08, in the same afternoon as item 15 and by the same mistake
being corrected. This one is worth reading even though nothing is broken —
because it is a decision you already made, made against a picture that has
since changed underneath it.

**What is switched off.** Lake Oswego. On 2026-07-24 it was excluded from the
screen, and the reason written into the file at the time is this: the zoning
permits our building, but the part of the city we could see is the Mountain
Park planned development, where 1968 neighbourhood covenants and design review
predate the state housing law and remain a real private gate. That is a good
reason and I am not second-guessing it.

**What has changed is which part of the city we could see.** At the time, our
land data covered one county, and Lake Oswego straddles two. The part inside
that county — the part the exclusion was reasoned about — is about **1,500
lots**. The city we hold today is **16,300 lots**, and the Mountain Park
argument was never made about the other 14,800. Three other places are switched
off as well — all three together are 556 lots. Lake Oswego is roughly **96% of
everything we have decided not to look at.**

**What being switched off actually does.** More than gating a report. The
screening pipeline skips assigning a zone to any lot in an excluded city, so
those lots never reach the part of the pipeline that measures anything. Lake
Oswego does not appear in the results as zero greens; it does not appear. This
is also why an old note in our own tests saying the exclusion "only affects the
final report" is wrong, and it has been corrected: turning the city back on
means re-running the land stages, not flipping a flag.

**Why it is a question and not a fix.** Our stated market is the whole state
and no jurisdiction is excluded — that policy was written four days after this
exclusion and does not mention it. So the two are in tension and only you can
say which wins. I have not changed anything.

**The choice.**

- **Turn the whole city back on.** Biggest single block of land we could add,
  and the covenant risk you named in July applies to a minority of it. Costs a
  pipeline re-run and puts sixteen unencoded commercial zones plus a damaged
  table (item 15) on the critical path.
- **Turn on everything except Mountain Park.** Keeps your original judgement
  exactly and drops only what it was about. Needs a boundary for the planned
  development, which we do not currently hold and would have to find.
- **Leave it off and write down the reason in today's terms.** Costs nothing,
  and the value is real: the file would then say *we exclude 16,300 lots*
  rather than a sentence about a slice, so the next person to read it is not
  misled the way I was.

The second is what I would do, and the third is the honest fallback if the
boundary turns out to be hard to get. Doing nothing at all is the one option I
would argue against, because the reason on file now reads as smaller than the
decision it is making.

---

## ~~Seven~~ Four of our fourteen cities have zero green lots — and each one has a single reason

Re-measured 2026-09-03 after your two answers ran, and again on 2026-09-04 once
Gladstone's and Tualatin's overlays were wired. **Three of the seven came off
this list in one afternoon, and all three came off through item 2** — Gresham
(0 → 1,820 greens), Troutdale (0 → 125) and Wood Village (0 → 95). Ten of the
fourteen cities now produce greens. What is left:

| City | Lots waiting | What is holding them |
|---|---|---|
| Happy Valley | 749 | Sewer **and** an environmental overlay — see below |
| Fairview | 198 | Signing — **item 7**, gated by **item 10**. Signing alone releases 150 |
| Gladstone | 121 | Signing — **item 7**, nothing in the way of doing it. Signing alone releases 35 |
| Tualatin | 19 | Sewer coverage — **item 6**. Sewer alone releases 6 |

**Fairview simplified.** It was the one city on the old list held by two things
at once, elevation *and* signing. The elevation half is answered, and all 198 of
its waiting lots are now held by an unverified zone rule — 150 of them by that
alone. Gladstone is the same shape: all 121 of its waiting lots want a signature
too.

**But signing is necessary for all 319 and sufficient for 185.** An earlier
version of this section said the two cities were "319 lots that need no data and
no decision", and that was too strong. A lot in the review queue is held by
*every* reason listed against it, so a lot wanting both a signature and a sewer
answer does not move when it gets one of them. Signing alone releases 150 of
Fairview's 198 and 35 of Gladstone's 121. The other 134 want a signature **and**
something else — 86 in Gladstone, 48 in Fairview. What is still true, and is the
reason both cities are on this list: nothing but a person reading a page stands
between us and the 185, and Gladstone can be read today. Fairview needs one
phone call first (item 10), because two of its zone codes have no page.

The old read-across is now history rather than forecast: **item 2 was worth
7,360 lots and delivered 7,360**, 5,320 of them in Portland and 1,820 in
Gresham.

**Happy Valley stopped being a one-thing city.** On 2026-09-01 it was 722 of 731
lots held by nothing but the missing sewer map. Wiring its environmental
overlays put a second blocker on top: of 749 waiting lots, 740 want a sewer
answer, **725 now also sit on mapped natural resource**, and 331 want a better
slope reading. Only 21 are held by sewer alone. (Slope was 603 and sewer-alone
was 6 when this was written on 09-01; the coarse-DEM fill has since answered the
elevation question for 72,188 lots the 1 m DEM could not reach, which is where
the difference went.) That is not a regression — the overlay check was simply
absent before, and 725 lots were being graded as if their resource land were not
there. It does mean **item 6 no longer unlocks
Happy Valley by itself**, and the overlay half looked like agent work: Happy
Valley *flags* resource land rather than carving it out of the buildable area,
so each flagged lot could have its mapped resource compared against the actual
envelope instead of against the whole lot.

**Measured 2026-09-03, and it releases nothing today — not built.** Comparing
the resource against the buildable envelope rather than the lot boundary drops
**279 of 3,914** natural-resource flags and 314 of 7,301 slope flags — about
one in fourteen. But only **two** of Happy Valley's 749 waiting lots are held by
the overlay alone: every other one of the 725 flagged lots wants something else
as well, usually a sewer answer (740 of the 749 do), and 331 want a better slope
reading. Refining the overlay test would move **at most two** lots to green
while it stands behind item 6. It becomes worth building the day the sewer
answer arrives, and not before.

**Gladstone gained an overlay on 2026-09-03, the same way Happy Valley did.**
Until that day Clackamas County had no environmental screening at all, and an
absent overlay grades as clear land. Wiring Gladstone's habitat-conservation and
water-quality layers put a flag on **51 of its 121** waiting lots (HCA 51, water
quality 23; FEMA floodway 9 and special flood hazard 19 were already there and
overlap). Not one of the 51 changes what has to happen first — every one of them
wants the signature as well — but it does move 21 lots out of reach of the
signature alone: **56 before the layer existed, 35 after**. The rest of the gap
between 35 and the 121 this list used to claim was never the overlay's doing.
Sewer and slope were already holding 65 of the 121 and the list was simply
overstating what one afternoon of reading would buy. The habitat layer is
Metro's regional Title 13 inventory standing in for an HCA map the city does not
publish as GIS, so it is a **flag**: the cost of the proxy is a lot read by a
person, not a lot thrown away.

These four are the whole of the silent part of the map, and they are 1,087 lots
between them — unchanged by the 2026-09-04 run, which moved lots between reasons
rather than out of the queue. The other ten cities all produce greens today.

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

- **The lot ledger could not see Clackamas County, and it nearly hid item 15's
  neighbours** — found *and fixed* 2026-09-08. Two different counts of the same
  land existed.
  The screening pipeline runs on **291,971 lots across fourteen cities**, and
  Oregon City (735 greens), Milwaukie (622), unincorporated Clackamas (113) and
  Wilsonville (53) are all in it. The ledger that answers *"how many lots ride
  on this zone"* was built on **Multnomah only** — 236,889 lots, 195,708 of them
  Portland, and the sole Clackamas entry is 758 Lake Oswego parcels.

  This is not a small bookkeeping difference. An audit the same day found
  fourteen districts across five cities that permit our building and that we
  have never encoded, and asked the ledger how much land was behind them. The
  ledger said **zero**, for all fourteen, because four of the five cities are in
  a county it has never counted. Written up as "not worth doing" it would have
  closed the whole queue on a number that meant nothing.

  What saved it is a rule already written down here: **lots is a sort, not a
  filter.** Used as a filter, a zero closes a card. Used as a sort, a zero only
  puts it last — which is why this was recoverable by re-reading the ledger's
  own header rather than by noticing the mistake.

  The fix was plumbing, not judgement, and it is done: the ledger has been
  rebuilt over the parcels the screening pipeline already holds, and now counts
  **334,959 lots across eighteen jurisdictions** instead of 236,889 across
  fourteen. The mirror check that reports cities nothing has ever counted lots
  against now comes back empty for the first time. Three things fell out of it
  in the same pass — a real ranking for the queue below, the discovery behind
  item 16, and two zones that turn out to owe a measurement nobody had noticed,
  both of them owed on purpose and both now written down as such.

- **Fourteen districts to encode and five documents to fetch**, from the same
  2026-09-08 audit — every one settled by the city's own use table, none needing
  a ruling from you. Now ranked, since the ledger can see them: **2,095 lots**,
  more than half of it in unincorporated Clackamas, led by `MR-1` at 839, Oregon
  City's `MUC-1` at 402 and `MUD` at 278. Oregon City's commercial zones permit our building nearly
  everywhere; unincorporated Clackamas permits it in ten of eleven residential
  districts; Tualatin's medium-high-density chapter turns out to be missing from
  our files entirely, ending at its own heading on the last line of the document
  that should have carried it.

  **Five of the fourteen are done, the same evening — 1,046 lots including the
  839.** Clackamas County's `MR-1`, `MR-2`, `PMD` and `VA` are encoded, and
  `R-2.5` turned out to refuse our building outright, which is an answer rather
  than work. Three things came back with them that were not the point of the
  errand: the county states a density limit on all four that no Oregon
  jurisdiction is allowed to apply — nearly missed, because the state rule's
  own scope sentence says it does not cover counties and its definitions
  section says it does; sixteen footnote decisions decayed exactly as the
  2026-09-07 re-read predicted they would, one week early, because encoding a
  district is what makes "we do not have that district" stop being true; and
  the empty-box bug of item 15 turned up in a second document, where it now
  blocks 115 lots. That last one changed my recommendation on item 15 and is
  written up there.

  **Of the nine then left, the one I called cheapest is not.** Three more
  Clackamas districts — 286 lots — send their setbacks to one chapter of the
  county ordinance that is not in our store, and I wrote here that fetching it
  was the cheapest work left in the layer. Then I read the page, which is
  public, and it is not: the setback it supplies is a **sun rule**. How far the
  building must stand off a lot line depends on which line faces north, because
  the point is to stop the building shading the land behind it. We hold no
  compass direction for any lot line, so there is nothing to put the number in.

  That is a better problem than it sounds. The four site facts that have
  blocked us before — is there a bus stop, is it a corner, is there an alley,
  is there sewer — all have to be bought or asked for. This one can be
  **computed from the lot shapes we already have**, and it is the first of its
  kind on that list. It is a piece of work, not a purchase. Nothing for you to
  decide; noted here because the earlier line said the opposite.

  **Oregon City's whole commercial side is read — 1,150 lots, the same
  evening.** This was the last untouched part of that city: eleven districts,
  everything that is not a plain residential neighbourhood. Six of them turn
  out to prohibit our building and five permit it, so **798 lots on 986 acres
  are newly in play** and 352 are newly and definitively out. Both halves are
  worth the same to us — a district we have read and that says no is off the
  list for good, where a district nobody has opened just sits there looking
  like a maybe forever.

  One thing came back that you should know about, because it changes what
  "in play" means for those 798. **Downtown-style zoning here lets you build
  right up to the property line — unless the property next door is houses,
  in which case you must stand twenty feet back.** That is the whole ball
  game on a small commercial lot, and which of the two applies depends
  entirely on what the neighbouring parcel is zoned. We have never needed to
  know that before, so nothing in the system looks it up, and until it does
  every one of these 798 lots will come out as "needs a look" rather than a
  clean pass.

  The good news is the same as the good news two paragraphs up: this is
  another one we can **work out from maps we already own** rather than buy.
  It is the second such item in a row, after the sun rule, and the two of
  them together are starting to look like one piece of work — teaching the
  system to answer questions about the parcel *next door* — rather than two
  unrelated gaps. Nothing for you to decide. I am flagging it because "798
  lots in play" and "798 lots we can actually grade today" are not the same
  sentence, and I do not want the first one quoted as if it were the second.

  Two smaller notes from the same reading. One district's permitted-use list
  contains the word "quadplex" and the district prohibits quadplexes — the
  word is there because you may *convert* an existing house into one, which
  is not what we do. Thirty-seven lots that a quick search would have called
  open. And Oregon City's own parking table does not say whether its numbers
  are per unit or per building; we read it the middle way and have been
  relying on a state rule to cap it, and that state rule may not reach
  commercial land. It is written down as the first thing to check before any
  of these 798 lots is signed off. Neither needs anything from you now.

  One more, and it is the kind of thing worth knowing we keep finding. Our
  own checker — the one whose job is to confirm that every number we hold is
  actually printed on the page we cite — reported three of these standards as
  wrong. They were not. It could not read them: the scan had broken one word
  across a line, put a space in the middle of another, and the checker's
  vocabulary for numbers spelled out in words simply stopped at ninety-nine,
  so "one hundred percent" was a number it had never learned. All three are
  fixed and every number in the whole corpus now checks out. The reason this
  keeps happening is worth stating plainly: **a checker that cannot see
  something reports it as fine**, so these only ever surface when somebody
  writes a number into the part of the page it was blind to.

  **And the rural half of Clackamas County is read — 3,676 lots, later the
  same night.** This was the biggest single unread block of land anywhere in
  either county, bigger than the whole Oregon City commercial side, and it is
  the countryside rather than a town: five districts of one-, two-, five- and
  ten-acre lots outside any city. **All five say no.** The county's rural
  chapter lists what may be built on a rural lot — a house, a manufactured
  home, and in exactly one district a duplex if you ask permission — and then
  says in as many words that one lot of record gets *one* of those. There is
  no fourplex row anywhere in it.

  Nothing here needs a decision from you. What is worth knowing is that this
  is the good kind of closure. Six thousand acres that had been sitting in the
  "we have not looked" pile are now definitively out, on the page, with the
  sentence quoted — rather than sitting there for another year looking like
  they might be worth something. **The land left unread in the unincorporated
  county drops from 6,257 lots to 2,581**, and what remains is mostly
  commercial and industrial ground.

  One thing I checked rather than assumed, because it would have been easy to
  get backwards. The state law that forces Oregon cities to allow fourplexes
  is the reason most of this corpus reads the way it does, and the instinct is
  that it applies to anything inside the Portland urban growth boundary — and
  some of this rural land *is* inside it. It does not apply, and the rule says
  so twice: it binds cities and county land with city-level services, which
  this is not, and it separately and by name excuses unincorporated land held
  in a "future urban" holding zone, which is exactly one of the five. Had I
  taken the shortcut and refused these on the word "rural", the answer would
  have been right for the wrong reason and would have broken the first time
  somebody looked closely.

  **And then the commercial half of the same county, an hour later — and this
  one goes the other way.** The rural chapter said no five times, which makes
  it easy to expect the next chapter to say no too. It does not. The county's
  urban commercial and mixed-use chapter covers eleven districts, and **nine of
  the eleven permit our building outright.** Shopping-street land, office
  land, the mixed-use ground around the Clackamas Town Center — most of it is
  open to us on the use question.

  Three of the eleven are now settled and all three are closed, because those
  are the three the table itself closes: two prohibit our building flatly, and
  the third — an office-apartment district — allows a fourplex only *inside*
  an office building, as up to 40% of its floor space. Ours is a building of
  its own on a lot of its own, so that is a no. Sixty-six lots.

  There was a door I had to check before believing any of that, and it is
  worth knowing it exists because it is a real option rather than a
  technicality. Printed above the dwelling rows, in small type that applies to
  all of them, is a rule that says a kind of housing the district otherwise
  prohibits **may be built anyway if it is built as affordable housing** under
  the county's affordable-housing chapter. That would put our building back
  into both prohibited districts. It turns on what we choose to build rather
  than on anything about the land, and our product is market rate, so the
  answer for us is still no — but it is written into the file beside the
  refusal so nobody re-reads it later and thinks we missed something.

  **The other eight districts are not refused and are not finished, and they
  are all waiting on the same two words.** The county says that a *freestanding*
  fourplex — "as opposed to" one inside a mixed-use building, which is their
  phrase, not mine — is measured by the rules of a high-density *residential*
  district rather than by the commercial district it sits in. Ours is only ever
  freestanding. So **896 lots of commercial land, including the county's
  largest commercial district at 470 lots, hang on two residential districts we
  have never worked out** — and those two are the ones stuck behind the sun
  rule two entries above.

  That connection is the useful part of the night. I fetched the chapter the
  sun rule lives in, which we had never held, and read it. It is what I
  described from a distance last time and slightly worse: the distance a
  building must stand off a boundary is calculated by drawing an angle from the
  top of the building — steeply to the north, shallowly east and west — so the
  answer depends both on how tall the building is and on which way each
  boundary faces. The chapter also says explicitly that these particular
  distances cannot be relaxed through the usual height-exception process, so
  there is no way around it. **The compass-direction job is now worth 1,182
  lots rather than 286** — the three residential districts that name it
  outright, plus the 896 commercial lots that get sent there. It is still a
  piece of work rather than a purchase, and it is now the single highest-value
  piece of plumbing left in this county.

  Two smaller things worth recording, both of the same family we keep finding.

  A decision we had written down about one page turned out to be **quietly
  answering a second page it was never about.** Our footnote file remembers
  decisions by the *sentence* they were made about, so when a county repeats a
  sentence in another chapter, the old answer applies automatically — which is
  usually exactly right and saved reading eight notes tonight. But one of those
  reused answers said, in effect, "this door does not matter because every
  district here permits our building anyway." True where it was written. False
  in the chapter it silently travelled to, where two districts prohibit it and
  that door is the only way back in. The conclusion happened not to change;
  the *reason* would not have survived being read aloud. Four such reasons are
  rewritten to be about the sentence rather than about one table, and the rule
  is written down.

  And our own checkers again. The one built this morning to catch tables that
  lost cells on the way into our files reported this chapter as 29% broken —
  twenty-five bad rows. Not one was actually broken. This chapter uses a fifth
  permission letter that every other chapter we hold does without, and the
  checker had never seen it, so every time it appeared the checker thought the
  row had ended. It is a milder version of the same lesson as always: **a
  checker that cannot see something does not stay silent, it makes things
  up** — and twenty-five false alarms is exactly where a real broken row would
  have gone unnoticed. Fixed, and the chapter now reads clean.

  **And one line in that chapter is worth flagging to you, because it is
  probably a real cost on real sites and we have nowhere to put it yet.** In
  the middle of a rule about outdoor storage, the county says a site must keep
  a place for **rubbish and recycling collection** — it points at its own
  chapter on the subject, which we have never read. That is not a permission,
  it is a requirement, and a requirement of that kind takes up *ground*. We
  have been here before: the space a car needs to back out of a parking stall
  was assumed away for months, and when it was finally measured it took
  between twelve and forty-two feet of depth off every lot we screen. A bin
  enclosure is much smaller than that, but it is the same kind of thing, and
  right now our model has no place to record it at all. Reading that chapter
  is on the agent's list. Nothing for you to do; recorded so that if a site we
  pass ends up short of room for the bins, we know where that came from.

  **Then I built a check for the travelling-decision problem described further
  up -- the one where a decision quietly answered a second page -- and it found
  the same problem twice more.** The thing that went wrong was this: we record a
  decision about a footnote by the *sentence* it was made about, so when a city
  repeats a sentence in another chapter the old decision applies automatically.
  That is usually right and saves a lot of reading. But the *reason* comes
  along with it, and a reason can be about the table it was written under
  rather than about the sentence — in which case it quietly answers a page it
  was never read on.

  The new check asks one question of every decision that covers more than one
  chapter: **does the written reason mention only some of the places the
  sentence appears?** Two live cases, both harmless in their conclusion and
  both wrong in their reasoning. One was in this county's own rules — a
  decision about minimum lot size that named one table when the sentence is
  printed word for word in two. The other was Gresham's affordable-housing
  note, decided on a fact about the commercial chapter's table and quietly
  governing the same sentence in the Pleasant Valley and Springwater chapters
  as well.

  **Underneath it was a simpler and slightly worse thing.** Where two decisions
  had been written about the same sentence, only one of them was ever read —
  whichever happened to be later in the file. Nine of those. In every one the
  *answer* agreed, so nothing was decided by accident. But in four of them the
  half we kept was the weaker half, and in one, in Happy Valley, what survived
  said literally "left here as a pointer only" while the entry that recorded
  what we encoded and why — including a real disagreement between the chapter's
  wording and its own footnote — was the one thrown away.

  Ten reasons rewritten, none of them changing an answer. Fixing them meant
  going back to each city's tables and tracing every footnote marker to the row
  it is actually printed on — transitional housing in three tables, cottage
  clusters in two, schools in five, one cross-reference printed ten times
  across seven chapters. All of them landed where the old reason said they did;
  the reason just had not been written in a way anybody could check twice.
  Both checks now sit at zero and run with the rest.

  The reason this is worth your time to know about, in one line: **we are
  increasingly finding our mistakes in the arguments rather than in the
  numbers.** The numbers have now been re-read twice, blind, with nothing
  wrong. What is left is whether the written reasoning would survive somebody
  reading it back to us — and twice this week it would not have.

  A second thing checked rather than assumed, back in the rural chapter. Under the
  county's rural use table sit thirty-five footnotes, and one of them is the
  only sentence in the chapter that could have undone the whole answer: it
  says a use *similar* to the one on that line may be approved anyway. If that
  footnote had been attached to the duplex line, "there is no fourplex row"
  would have stopped being a refusal, because a fourplex is plainly similar to
  a duplex. So every one of the thirty-five was traced back to the line it is
  actually printed on — which the county's own web page makes deliberately
  hard, because each cell of the table lands on its own line with nothing
  beside it. That footnote turns out to sit on lodges, government buildings,
  broadcast towers, parks, campgrounds and utilities. Not one dwelling. The
  refusal holds, and now it holds for a reason somebody can check.

  **Three of our own ledgers were quietly blaming the state of Oregon for
  every city's unread references.** Found on the way in, unrelated to the
  errand, and it is the same shape as the checker problem in the paragraph
  above. The queue that tracks "chapters our documents point at that we have
  never fetched" had 1,348 entries, and **591 of them — 44 percent — were
  filed against Oregon itself**, which points at nothing of the sort. Every
  one of those rows was a real reference from some city, misattributed. The
  fault had already been found and fixed twice in other parts of the system
  back on 4 September; both fixes left a note in the code saying "the other
  one is its twin", and neither of them looked here. The queue is now 758 real
  rows. Nothing for you to do; noted because "how much unread code is left"
  is a number you have been quoted, and it was nearly half wrong.

  **And one number I shipped yesterday was wrong.** The coverage ledger — the
  file that says, per zone, what we hold and what we still owe — is rebuilt on
  a separate machine because that is where the lot data lives. Yesterday I
  built it from files hand-copied across mid-edit, so six Oregon City
  districts came out saying they owed nothing when they owe five standards
  each. Rebuilt properly today it tells the truth. It changes no verdict —
  those six districts prohibit our building anyway — but the guard that exists
  precisely to catch this kind of staleness passed on it, because it can only
  check the file it is handed. Every ledger in this system now gets rebuilt
  before it is trusted, not read as a committed artefact.

  The one thing that came out of tonight and *is* real work: the county's
  rural chapter points at a tree-removal rule for land inside the Portland
  growth boundary — "a development restriction that may apply if excessive
  tree removal occurs". That is the same shape as Portland's tree code, which
  turned out to cost real money per tree, and we have never fetched the
  chapter. It is queued as a fetch rather than waved away, and it is mine to
  do, not yours.

  **Five districts and five documents left across all cities**, down from
  fourteen and five this morning. Two of the five districts are in Lake
  Oswego, which is switched off — see item 16 — so in practice it is three:
  one in Wilsonville and two in Gresham. Oregon City has a single zone left
  and it is not a reading at all: twelve lots that our map labels with the
  county's zoning instead of the city's.

- **The 784 footnote dismissals were read back, blind, on 2026-09-07** — the
  run behind item 13, and the third of the three checks that stand over the
  footnote register. The other two were already built: one asks, of every
  number we hold, which notes sit over it and has anybody ruled on them; the
  second takes the 45 rulings that say "we encoded this" and checks the figure
  they claim to have become. Neither ever touched a dismissal, which is nine
  tenths of the register.

  The mechanism is the one item 11 describes, with the reason stripped instead
  of the number, and it needs saying that a *good* dismissal usually quotes the
  note before arguing with it — so the quoted half belongs on the card and the
  argued half must never be, and telling those apart is what the test in
  `flats/tests/test_waved.py` does. Cards are one footnote, not one number: the
  same sentence standing over eleven zones is one decision, and re-reading it
  eleven times would buy eleven copies of one answer.

  **The gap it found is now closed, and that is the part worth keeping.** All
  three of item 13's failures are the same failure: a reason that was true when
  written and was quietly falsified by somebody else doing their job. So the
  register is now asked, in bulk, the question a person had asked once by hand
  — *does this reason still say something true about our own files?* Of the 784
  dismissals, **49 argue about our corpus rather than about Oregon**, and those
  are the only ones that can decay; a reason that says "this sentence is about a
  detached house" is as durable as the page it read. Ten of the 49 name a zone
  the layer holds today, one says in its own words that somebody already came
  back and fixed it, and thirty-eight name nothing anybody can re-ask — which
  is not a bug but is worth knowing about a claim with a shelf life.

  **The ledger sorts itself by consequence, which is the part that makes it
  workable.** A false sentence about a district where we already record that a
  fourplex is forbidden cannot make a lot green wrongly — the lot is red on use
  long before any footnote is reached. So each row carries the zones the note
  stands over and how many of those permit the building, and the report leads
  with the seven that can still bite. Reading those seven by hand the same day,
  five gave a *second* ground that survives on its own and only the Happy Valley
  buffer changes what a lot must satisfy. That ratio is the point: the screen is
  cheap and the reading is short.

  The ledger is `data/flats/stale_reasons_2026_09_07.csv` and it deliberately
  over-reports: a reason can name a live zone for its own reasons — "120 feet
  from a lot zoned R-6" is a measurement, not a claim that R-6 is missing — and
  a person sees that in a second. The opposite error cannot be seen at all,
  because a stale reason reads exactly like a sound one. Seven rows to read out
  of 784 is the right price for that.

- **The thousand lines nobody ever quoted were sorted by arithmetic, and the
  nearest 185 were read blind, on 2026-09-08** — the run behind item 14. Every
  other check in this system reads back a decision somebody made. This is the
  first one that reads the sentences nobody decided anything about, which is
  the harder half: a standard we simply never took looks exactly like the nine
  hundred lines around it, and Milwaukie's side-yard height plane was found by
  hand because nothing was going to find the next one.

  The lever is a comparison a machine can do and a person should not have to.
  For each unquoted line stating a measurement, the number printed on it is
  compared against **every number that city holds for that kind of standard, in
  any zone**. 174 lines state a figure we already carry somewhere — bookkeeping,
  our reader took it off a neighbouring row. 490 state nothing comparable. 542
  state a figure the city's whole file has never held, and those are the only
  ones worth a reading. What counts as a number is kept deliberately narrow:
  section numbers, ordinance numbers and the years in an amendment trail are
  masked out first, and each standard's kind supplies a sanity range, because a
  height of 40,000 is a floor area that wandered into the sentence.

  **It is a sort, not a verdict, and the first run measured the price of that
  honestly.** Of the 29 lines the readers said would bind us, 25 closed on the
  evidence within the hour — wrong table, wrong district, an option nobody has
  to take, a city where a fourplex is already refused on use. Two need you and
  are in item 14; two more are real and are in Lake Oswego, which is switched
  off. That ratio is the queue working, not failing: the cost of the 25 is
  minutes, and the thing it is protecting against is a standard sitting unread
  in a document we have held for months.

  **Then the same ledger was asked its harder question**, the same day: the 347
  measuring lines that sit in sections nobody has ever quoted a single word of.
  One line at a time those are unanswerable, because the sentence above the line
  is usually what says which building it is about — so the card became the whole
  section, and 347 lines became **144 questions**. 116 came back with nothing in
  them for us; 26 with something; 2 undecided. Twenty-five of those 28 closed on
  the evidence, and the shapes are worth naming because a person reading a page
  cannot see any of them: a paragraph describing what a district is *for*
  mistaken for a standard, a menu of eleven design features of which any four
  will do, a tree rule the applicant may satisfy with whatever land the building
  does not use, and the Open Space zone. Three are in item 14, and one of those
  is a whole district — Oregon City's R-2, which prints *"Triplex, quadplex and
  multi-family — 6,000 square feet"* in its own table and was left out of our
  screen with the single word "excluded".

  **A third check was built and run for the first time**: for each city, which
  standards do most of its neighbours regulate and it does not. Seven rows, two
  of them real, and both were garage standards — which is what led to counting
  the 66 garage numbers, in ten cities, that no part of the screen has ever
  read.

  **One defect in our own machinery came out of it**, and it is the reason the
  run is written up rather than just filed: the reading list did not know which
  cities the screen covers, so a seventh of it was Lake Oswego and Rivergrove.
  Every other queue here already drops or marks excluded land. This one does
  now, while the ledger keeps counting them, because a list that hides what it
  has excluded cannot be told apart from a list that has finished.

  **Three of the four questions are answered, and the answers cost more work
  than the questions did.** The fourth, Oregon City's R-2, closed on Steph's
  own suggestion: pull the city's definitions and see whether the building
  meets them. It does -- 17.04.989 makes a quadplex four attached units on a
  lot and 17.04.780 makes multi-family five or more -- so the district's
  one-word exclusion rested on a wrong premise rather than a judgement, and
  R-2 is now encoded in both the corpus and the older pipeline. The lesson is
  the cheap one: a decision recorded as a category ("the multi-family zone")
  can be checked against the code's own dictionary, and this one took minutes.
  Its density floor is the first standard in this corpus that makes a lot too
  LARGE to qualify. Ruling that the pod has no garage retired
  66 numbers and closed both garage findings — and the exclusion is written into
  the screen's own list of what it declines to charge, with a test that fails the
  day a design with a garage enters the catalogue, so the ruling cannot outlive
  the building it was about. Ruling to incorporate the parking aisle turned out
  to be much larger: **nothing here had ever charged a lot for the ground the
  cars stand on**, and the court behind the pod is deeper than the pod. Every
  quadplex-permitting zone now needs 12 to 42 more feet than we were saying, and
  wiring it uncovered a live false GREEN — a pod that fits only sideways was
  being measured against its own narrow dimension. Both are written up under
  item 14.

  **And one of the four findings was mine, not Oregon's.** I reported Milwaukie's
  aisle table as a standard we never took. Our own files already refuse it, and
  Portland's and Wilsonville's, each with the city's own exclusion sentence
  quoted. The blindness that makes these readings worth having — the reader never
  sees our answer — puts the whole burden of checking on the triage step after
  it, and I did not search our own corpus before writing "we hold nothing".

  The ledger is `data/flats/missed.csv` (1,206 lines). The readings are
  `data/flats/missed_reading_2026_09_08.csv` (185 lines) and
  `data/flats/chapter_reading_2026_09_08.csv` (144 sections).

  **And encoding R-2 turned up something you should know about, which is that
  a set of our checks was not running.** The older screening pipeline — the one
  that actually produces the county numbers — keeps its own folder of tests,
  and none of our automatic checks had ever been pointed at it. Nobody had
  noticed, because an unrun test and a passing test look exactly alike from
  outside.

  Two of those tests had been failing for days, and one of them is the check I
  would least like to lose: it is the **only** thing that compares the numbers
  the screen actually runs on against the numbers we read off the page. Two
  earlier corrections this week walked straight past it and shipped. Nothing
  was wrong on the ground — both corrections were right — but for a few days
  the one instrument that would have caught a mismatch was switched off and
  silent.

  Both are fixed, and more to the point the folder now runs on every push, so
  it cannot go quiet again. The general lesson is uncomfortable and cheap:
  **ask which folders no automatic check names.** A failing test shouts; a test
  nobody runs says nothing at all.

- **Every number we hold has now been read twice, and the second reader was
  not allowed to see the first one's answer** — run 2026-09-07, and the result
  is item 11. Worth knowing here is how it was done, because it is repeatable
  and it cost nothing but machine time. Each of the 1,902 citations was turned
  into a card carrying the passage of code, the zone and the name of the
  standard, with the number we hold **stripped out**. Forty-eight readers worked
  them in parallel, wrote down what the page says, and only afterwards were the
  answers joined back to ours. A reader who cannot see the answer cannot drift
  toward it.

  Both ledgers are in the repository — `data/flats/second_reading_2026_09_07.csv`
  (1,902 rows, one per number) and `data/flats/missed_reading_2026_09_07.csv`
  (221 rows, the separate sweep of sentences that state a standard nothing of
  ours quotes). Every fix made from them says so in the code file, with the date
  and the sentence it now rests on, so a signer meets the reasoning rather than
  a changed number.

  Three of the readings it flagged turned out to be the *reader* being wrong,
  and all three were the same defect on our side: the card showed six lines
  either side of the citation, which is not enough to reach the column headings
  of Gresham's eleven-column setback table. The reader said honestly that it
  could not tell which cell was which. That window is now twenty lines wide and
  a card also reaches back to the caption of the table it is standing in.

  **It had a second blind spot and it is the more serious one: the readers were
  never shown a footnote.** Notes print below the table they qualify, past any
  window a citation can carry, so a reader was handed "5 ft" and never saw
  "except on a corner lot" underneath it. That affected **1,480 of the 1,919
  numbers**, and for **731 of them the footnote is one we have ruled actually
  does something** — it changes the figure, or it turns on something about the
  lot nobody has measured. The card now carries the text of every note over the
  lines it cites, so the first run's clean result should be read as "clean on
  the cell", not "clean on the rule".

- **Those 731 were read again the same day, with the footnote on the card** —
  run 2026-09-07, nineteen readers, no human time. Same rules as before: the
  reader sees the page, the zone, the standard and now every note that governs
  the lines, and never the number we hold. Two jobs per card — what does the
  cell say, and does each note reach a four-unit attached townhome. The ledger
  is `data/flats/footnote_reading_2026_09_07.csv`, 731 rows.

  **On the cell: 714 agreed, 11 read a defensible alternative, 6 could not be
  read at all, and nothing disagreed.** All six unreadable are Wilsonville RN —
  item 11(c), arrived at from a different direction by a reader who had never
  seen that list.

  **On the rules: a footnote moves the number on 299 of the 731.** The question
  that matters is whether any of those 299 has a live route to a wrong answer,
  and for 271 of them it does not — the exception is already encoded, or the
  note already caps that lot at REVIEW instead of GREEN, or the zone forbids a
  fourplex outright so nothing there can grade green anyway. That leaves 28
  numbers behind twelve notes, every one of them in Clackamas County. Eleven of
  the twelve *loosen* a standard we hold at its strict end: Happy Valley lets a
  townhome take the greater of the table's coverage percent or 1,000 square
  feet, and lets side and rear walls reach 49 feet where the front is capped at
  45. Holding the strict end costs lots and cannot cost correctness, which is
  the trade this project has chosen everywhere else.

  **The twelfth is Milwaukie's parking ceiling and it became item 12.**

- **Both directions of the footnote check now run** — built 2026-09-07. The
  system was only ever half-built and the missing half was the unsafe one.

  Going one way, it always worked: for every number we hold, which footnotes
  sit over the lines it was read from, and has anybody ruled on them. An
  unruled footnote blocks the value from ever being signed. 1,792 numbers sit
  under a footnote and nothing is blocked.

  Going the other way, nothing ran at all. When somebody rules a footnote
  "encoded", they write down what it became — which zone, which standard, which
  figure. Forty-five of those sentences were on the record and **not one had
  ever been checked against the encoding.** So a rule could be deleted, renamed
  or moved out from under a closed decision and the decision would sit there
  looking settled. That is not hypothetical: four party-wall setbacks were
  deleted from Gresham the same week, and if a footnote had been standing on
  one, nothing would have said so.

  Checked for the first time: **44 of the 45 confirmed, one benign, and two
  errors** — both the same one, in two cities. Gresham and Wilsonville each
  encode a band as "up to 10,999" and "up to 19,999" where their codes say
  "less than 11,000" and "less than 20,000", and each file explains in writing
  that it did so because the model had no way to say "less than". The model has
  had one for months, and both notes were carrying their own excuse forward. A
  square foot of error each, in the safe direction, now exact. The check runs in
  the test suite, so the next one goes red instead of quiet.

- **The 4,693-item reading list is now four queues you can actually sit down
  with** — built 2026-09-04, live at **`/flats/reading`**. The list below was
  right and unusable: one line per sentence, grouped by city, ten shown per
  city and "and 2,431 more" underneath. Grouping by city cannot help, because
  every city says the same word. And a sentence is not what anybody decides
  about — a *section* is, and the same 4,693 sentences are **649 sections**.

  So the queue now sorts by what kind of reading each one wants, and you pick
  the kind before you pick the card:

  | Queue | What you are asking, over and over | To check |
  |---|---|---:|
  | **Missed standards** | "This is a plain rule for something we screen on, in a chapter we already read. Why didn't we take it?" | 185 |
  | **Conditions** | "This moves a number we hold, when something is true of the site. Is it true of ours?" | 136 |
  | **Unopened chapters** | "Nobody has ever quoted a line of this chapter. Is there anything in it for us?" | 84 |
  | **No field for it** | "We have nowhere to put this. Is it a gap in the model, or not our problem?" | 244 |

  Each screen asks its one question and offers only the answers to that one,
  so there is no vocabulary to re-read between cards. The missed-standards
  queue leads with the cards where **the code's number is not the number we
  hold** — those are alarms, and everything behind them is bookkeeping.

  Two things keep it from going stale, which has bitten this project twice.
  Cards are worked out fresh every time the page loads, so encoding a value
  makes its card disappear with nobody having to remember to retire it. And
  each decision remembers the words it was made about: when a city republishes
  a chapter and the section moves, the card **reopens flagged** instead of
  staying quietly closed on a page that no longer says that.

- **A day of reading now turns into the next day's work** — built 2026-09-04,
  live at **`/flats/feedback`**, and there is a **Hand-off** item in the
  sidebar for it. Answering a card was already recorded properly. What was
  missing is that five of those answers are not *decisions*, they are *orders*
  — "encode this one", "open this chapter", "we need somewhere to put this",
  "this depends on a site fact nothing measures", "our reader mangled this
  line" — and each one sat in the queue that asked the question. Right place
  for the decision, wrong place for the job: the work was spread over five
  screens, written as answers, and invisible to anyone sitting down to do it.

  The page now carries two blocks instead of one. **Problems found** is what
  it always was — values you marked wrong. **Work ordered** is new: every
  decision that asked for something, grouped by the kind of work, with the
  document, the section, the sentences and your reason travelling with it, so
  it can be handed to someone who was not there. Each block copies on its own.

  Nothing on it has to be ticked off. A job leaves the list when the work
  lands — encode the value and the sentence stops being unread, so the card it
  came from stops existing and takes the order with it. The list is always
  what is still true rather than what was once decided.

  One of the five is honest about needing a person: "depends on a site fact
  nothing measures". Registering that fact means saying which zones it reaches,
  and a section of code is not addressed to a zone. The list makes it visible;
  it cannot answer it.

- **Our "what has nobody read yet" list was wrong in both directions** — found
  and fixed 2026-09-04, straight after the driveway find below. We keep a list
  of every sentence in the codes we hold that states a measurement no rule of
  ours quotes. It is how we know what reading is still owed. It was lying twice.

  It could not see a number written the way lawyers write them. Ordinance
  drafters put the figure in words and then repeat it in brackets — "a minimum
  driveway apron width of twelve (12) feet" — and the bracket sat between the
  number and the word "feet", so the list saw no measurement at all. Milwaukie's
  entire street chapter, the one that had *just* answered the driveway question
  below, read to us as containing nothing measurable. Troutdale writes its whole
  code that way, and nine other cities do in places: 304 sentences invisible.

  And half of it was a duplicate. Every city's code was also being checked
  against Oregon's own state rules, which quote almost nothing in a city
  chapter, so nearly every unread line was filed a second time under the state's
  name. The list read 9,650 items; 4,686 of them were that shadow. It is 4,693
  now — about half as long and, for the first time, all of it real.

  Nothing here changes a lot's colour. What it changes is how much reading we
  think is left, which is the number this list exists to give you. Two of the
  newly visible sentences were worth chasing on the spot and both came back
  clean: Wilsonville's 30 ft setbacks are in an industrial zone we don't build
  in, and Gresham's corridor setbacks were already encoded off a different page.

- **Milwaukie's driveway width was in the code all along, in the wrong book** —
  found and fixed 2026-09-04. Our notes said Milwaukie never states how wide a
  driveway has to be where it meets the street, and treated that as a fact
  about the city. It was a fact about which chapters we had read. Milwaukie
  keeps its zoning rules in one part of the code and its street rules in
  another, and the width is in the street part: a four-unit building gets a
  12 ft opening on a quiet street, 16 ft on a busier one, 20 ft at the most
  anywhere. The zoning chapters point at that street chapter three separate
  times and never repeat the number.

  Nothing about this needs you, and it has now been run rather than assumed:
  every one of Milwaukie's 919 drawn site plans widened its driveway mouth from
  12 ft to 16 ft, and not one lot changed colour. Milwaukie stays at 622 green,
  188 in review, and the county-wide total stays at 16,530 green. What stops a
  Milwaukie lot is depth, not the width of the opening, and the lots that fit
  had the four extra feet to give. Taking the cautious figure turned out to be
  free — but free is something you can only know by running it.

  Two things worth knowing anyway. First, our own to-read list had been
  flagging that chapter as important for weeks and nobody opened it — the list
  was right and the reading was late, which is the failure worth fixing.
  Second, two rules in it are real and we still cannot apply them: the city
  keeps a driveway 5 ft clear of the neighbour's line, and it keeps a
  sight-line triangle clear at every driveway and corner without ever saying
  how big the triangle is (it points at a national engineering manual we do
  not have). Both take room off a lot in a way nothing measures, so they are
  recorded as known blind spots rather than guessed at.

- **The work queues were pointing at four cities we don't screen** — found and
  fixed 2026-09-02, and it is the same mistake in three places. Lake Oswego,
  Johnson City, Rivergrove and Maywood Park are all switched off: three are too
  small to be under the state's fourplex mandate or have no multi-dwelling
  zoning, and Lake Oswego is your own call on the Mountain Park PUD. Their rules
  stay in the file, which is right — a decision you can reverse is worth more
  than one that deleted the evidence. But every queue built on top of those
  files was quietly counting them as work: the signing plan listed 138 values to
  read, the command that hands out signing cards handed out Lake Oswego's 132
  without a word, and the ledger of unread chapter references had Lake Oswego's
  near the top of a list of six.

  All three now say *switched off* next to the row instead of dropping it. That
  is deliberate and it is the same principle as the environmental note below:
  hiding a decided row makes a queue that has finished look identical to one
  that was never asked, and the reader loses the ability to disagree. Net
  effect: the real signing job is **2,204 numbers, not 2,350**, and one of the
  six outstanding chapter-reads is not a job at all.

- **A guard on the step between signing and the screen** — added 2026-09-02,
  before it was needed rather than after. Your signature lands in one file and
  the screen reads a different one, so a zone can be fully read, fully signed,
  and still send its lots to the review queue because nobody flipped the second
  switch. Both files would report themselves finished and both would be telling
  the truth. There is now a check that lists exactly those zones, and it runs
  with the rest. It reports zero today because nothing is signed; the point is
  that it will not report zero on the day it matters.

- **A number can sit on the right line and still be the wrong number** — found
  and fixed 2026-09-02. Gresham prints its zoning standards as a wide table: one
  row per kind of building, one column per district. The townhouse row of the
  street-frontage table reads *16 ft / 16 ft / 16 ft / None / None / 16 ft /
  None* across seven districts, and 16 had been copied onto all six of the ones
  we hold. Two of them say None — no frontage requirement at all.

  Every existing check passed it, and this is the part worth knowing: they all
  ask whether the number appears somewhere on the quoted line, and "16 ft."
  appears on that line three times. Nothing was asking which *column* it came
  from. There is now a check that counts columns and compares each district
  against its own cell. It found the two frontage misreads and five more of the
  same species — a minimum lot size written as zero where the table says None,
  which are different claims even though the screen treats them alike.

  None of the seven moves a lot today: they all sit on the townhouse-plat path,
  which this screen does not model, and each error was in the direction that
  costs lots rather than inventing them. What they would have cost is you — each
  one is a number you would have opened the code to sign and found the page
  saying something else. Two things the check taught while being built, both now
  written into it: it initially read 29 citations and pronounced the corpus
  clean, missing an entire city because its table prints *R-40* where our file
  says *R40*; and the first version compared numbers only, so "None" was
  invisible to it — it would have walked straight past the misread it was
  written for.

  It was then taught the citation shapes it had been skipping — most citations
  name several lines, not one — and now reads 518 of them where it started at
  29. It stays quiet about one whole class on purpose: when a citation points
  at a footnote as well as the table, the footnote is usually the thing that
  *replaces* the number in the cell, so the check leaves it alone rather than
  reporting a correct reading as an error. Gresham's downtown corridor is the
  example — the table says a ten-foot maximum front setback and the footnote
  makes it five on most street types, and five is what we encoded.

  A second pass the same day found it was skipping the *careful* citations. Two
  cities quote the header row beside the value, which is how a file says which
  of six columns a number came from — and the check was treating that header as
  a line it had failed to read, so Troutdale and Happy Valley were almost
  entirely unexamined. It now reads 751 citations and can compare 378 of them,
  up from 154, and still finds nothing wrong.

  It also found a silent hole in itself, which is the more useful kind. Four of
  Wood Village's districts are named with a space in them — *LR 7.5*, *MR 2* —
  and the check did not skip those four, it read their numbers as though they
  belonged to whichever district was listed above them. So it went looking for
  them in another district's columns, found nothing, and reported all clear.
  Fixed, and their numbers are now genuinely checked.

  And one more, the same shape in the other direction: some values say *how*
  they are measured, and that explanation carries its own page reference. Happy
  Valley's density is per *net* acre, and the note explaining what a net acre is
  points four sections away into the land-division chapter. The check had been
  reading that reference as though it were the density's own, which would
  compare a number against a definition. 103 references in the corpus are of
  that kind; none of them was producing a false alarm yet, and now none of them
  can.

  It also now says what it *cannot* read, which matters more than the count: a
  clean report from a narrow reader looks exactly like a clean corpus. Five
  shapes of page defeat a machine that finds columns by looking for gaps, and
  three of those are nothing to check anyway — plain prose, a table with only
  one district in it, a table whose columns are building types rather than
  districts. Two were real gaps, and both have since been closed as far as the
  page allows.

  The first was the table printed *down* the page instead of across it, one
  cell per line: Happy Valley, unincorporated Clackamas, Fairview and Lake
  Oswego all do this. Happy Valley was the one that mattered, and it shows why
  a quiet check is worth distrusting — its three attached-housing districts
  were being looked for in the wrong table's headings entirely, so 78 numbers
  came back the same way a table with nothing wrong in it comes back. They are
  read now. The trick is making the file prove where one row ends: the districts
  listed under the heading are only believed once two rows below turn out to
  have exactly that many lines, and if any row runs *long* the whole table is
  put down, because a row that ran long means the boundary between two rows was
  lost and a row of the right length after that is luck rather than evidence.
  Fairview is the table put down. It numbers its row labels — “1. Minimum Lot
  Size (sq. ft.)” — so every label reads as a number, its rows run together
  eighteen lines at a stretch under three districts, and a machine counting
  down that block would be guessing. It stays hand-read.

  The second was the table whose columns are a single space apart rather
  than several, which is how Gresham's two plan districts print and how half of
  Oregon City's scanned chapter comes out. There is no gap to find, so the
  check reads those rows by grammar instead: a value starts at a number and
  runs through the words that measure it — *5,000 sq. ft.* — and the reading
  stops at the first word that is neither. That is 92 more numbers checked, 57
  of them against a printed figure, and nothing wrong in any of them. Two
  things stop it inventing errors: every cell in a row has to be the same kind
  of measurement, so a row that begins “Lots over 5,000 sq. ft.” cannot hand
  its own number to the first district; and a line only counts as a column
  heading once a real row of numbers turns up beneath it, which is what keeps a
  row of a permitted-use table from being mistaken for one.

  What still refuses is the rest of Oregon City, where the scan puts the same
  single space between the columns as between the halves of its broken words —
  *Quad pl ex a nd co t tage 1 0 , 000 squ are*. All of it was read by hand on
  2026-09-02 anyway, every dimensional number against its own column, about 250
  values across five jurisdictions — Fairview, Oregon City, Lake Oswego,
  unincorporated Clackamas, and Gresham's two plan districts. All correct.
  Where the check now reads them, that hand audit has become a floor. Where it
  still cannot, it stays what it was: a reading of today's files, not a check
  that will notice if they change.

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
  "plant invasive vegetation" and "store materials outside" — so its greens
  keep their verdicts and get a second look instead. (That was 598 greens when
  written on 2026-09-02 and is 113 after the 2026-09-03 run, for reasons that
  have nothing to do with the overlay: see item 1.)
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
  **Gladstone, wired 2026-09-03 — and the reason it was still on this list was
  wrong.** The line that used to sit here said Tualatin and Gladstone had no
  greens between them, so nothing rode on them. That is true and it is not the
  question. Nothing stands in the way of *doing* the signing in Gladstone — no
  missing chapter, no unanswered phone call, no decision waiting on you. So "no
  greens today" was measuring the wrong day.

  **Corrected 2026-09-04.** This paragraph said all 121 review lots go green the
  day item 7 is signed. They do not: **35 do.** A lot in the review queue is
  held by every reason listed against it, and 86 of the 121 want something else
  as well — 51 an overlay reading, 40 a sewer answer, 34 a better slope reading.
  Only 21 of that gap is the overlay wired below; sewer and slope were holding
  65 of them before any of this, and were not being counted. Gladstone is still
  the cheapest city on the board to advance and still the one you can start
  today. It is not a city where one signature finishes the job.

  Measured before wiring anything: **51 of those 121 lots sit on mapped habitat
  and 23 on mapped water-quality resource — 51 of 121 between them, two in
  five.** Signing Gladstone with no environmental screen would have graded two
  lots in five as clear land. That is the exact failure this whole item exists
  to prevent, and it would have landed on the cleanest-looking city we have.

  Gladstone runs four environmental districts, each its own chapter, and the
  city's own definition of a buildable acre names them together. Two are now
  screened, both as **flags** — the lot keeps its verdict and goes to a person.
  Not as carves, for two reasons. The city adopts its habitat map inside its
  Comprehensive Plan and does not publish it as a map file, so what the screen
  actually uses is Metro's regional layer standing in for it — close, not the
  same boundary. And the code does not refuse: the complete list of what you
  may not do in a Gladstone habitat area is *plant invasive vegetation* and
  *store materials outside*, word for word the county's list, with a permit
  that the code says "shall be approved" on evidence. Taking a lot off the
  board on a borrowed boundary for a rule that does not say no is not a trade
  worth making.

  One number in that chapter is worth your attention even so, because it is the
  strongest argument anyone will make for going further. A habitat permit on
  low-density residential land caps the **total disturbed area** — building,
  parking, staging, everything, and it must be contiguous — at 5,000 to 6,000
  square feet. Our pod plus its court runs about 7,030. So on that land the
  in-habitat path is closed by arithmetic, not by judgement. It is not encoded
  as a kill because the cap only applies to one comprehensive-plan designation
  and the screen does not carry the designation that tells them apart. If the
  designation is ever loaded, this becomes a real decision.

  Two things are still not screened in Gladstone and both are written down
  rather than guessed at. The **greenway** along the Willamette is a kill we
  cannot draw: every development in it needs a conditional use, and the code
  sets the setback "on a case-by-case basis", but the state publishes the
  greenway boundary as a *line* and the city publishes no map of it at all, so
  there is nothing to take the shape from. Building it from a line and a
  riverbank would be inventing geometry. The **flood** district is already
  screened by the FEMA layers everywhere; the piece not screened is Gladstone's
  own extension of it to land that flooded in February 1996, which the city
  admits its own map shows only "generally".

  **Tualatin, wired the same day, and it closes this item completely — every
  jurisdiction the screen grades now has an environmental check.** Tualatin was
  the last name on the list and it had sat there for a month behind a note
  saying its map service was "confirmed, layers not enumerated". The note
  pointed at the wrong path. The city's layers are there, and they are the best
  environmental data anyone in this project has published: not a regional map
  borrowed as a stand-in, but the adopted overlay itself, split into exactly the
  pieces its own code names. Worth remembering the shape of that mistake — "the
  city doesn't publish it" and "our address for it is wrong" look identical from
  the outside, and only one of them is a real gap.

  Five layers, and Tualatin is the only city so far where the code is clear
  enough to *subtract* land rather than send it to a person. Its Chapter 72
  says plainly that no building, grading, fill or impervious surface may go in
  a greenway or natural area, and the list of what may is paths, streets,
  utilities, parks and landscaping — nothing anyone lives in. So those areas
  come off the buildable part of the lot, along with the 50-foot strip along
  each stream, which the code writes into the definition of a natural area
  rather than leaving to be inferred. The wetlands district splits in two and
  the split is the city's own: the protected pond and its 40-foot setback are
  no-build and are subtracted; the fringe around them is land the code
  explicitly expects to be developed, so it keeps its verdict and only picks up
  a flag, because building there needs an engineer's signed certification.

  One sentence in Tualatin's code is worth more than the layers. Chapter 71
  says its district boundaries "are hereby fixed and established" as shown on
  its map. No other city in the fourteen says that. Milwaukie calls its map a
  general indicator, Gladstone adopts a map it does not publish, West Linn
  publishes lines and makes the code supply the width. When a city says the map
  *is* the boundary, a screen can stand on it — and that is the difference
  between subtracting land and merely flagging it.

  Nothing moves today: 7 of Tualatin's 19 waiting lots touch this, and all 19
  are blocked on the sewer question in item 6 anyway, so unlike Gladstone,
  signing alone will not turn them green.

- **A rule that hands buildable ground back** — Clackamas ZDO 706.11 says a lot
  containing a habitat area, inside the Portland urban growth boundary, has
  **no minimum front, rear or side yard setback at all** (garages still have to
  sit back, and fire code still applies). Every other environmental rule found
  this week takes buildable ground away; this one gives it back, and
  specifically on the lots that are hardest to fit a pod onto.

  **Measured 2026-09-02, and it is worth less than it looked — deferred, not
  dropped.** The habitat layer touches 6,853 lots in unincorporated Clackamas.
  4,419 of them are already in the review queue and 2,434 are red; of the red,
  1,053 fail because the building will not fit and 521 because there is no
  buildable area left at all. So the rule can reach at most **1,574 lots**.

  It cannot reach a single *green* one, and the reason is that the same chapter
  pulls both ways: 706.10 requires a habitat development permit, which is why
  every lot in the layer is sent to a person for review in the first place. A
  lot cannot be flagged for review and cleared green at the same time. So the
  honest prize is 1,574 lots moving from *discarded* to *worth a look* — real,
  but it grows a queue rather than the buy list.

  And every one of those lots is in the one jurisdiction that cannot be drawn
  at all, because its parking aisle width is locked inside the drawing in item
  1 above. Building this before that question is answered puts 1,574 lots into
  a queue that cannot move. **Trigger: build it when item 1 is answered**, in
  the same pass that puts unincorporated Clackamas back through the site-plan
  generator. Nothing is lost by waiting — the screen recomputes every lot from
  scratch on each run.

  **The trigger fired on 2026-09-03, and re-measuring tripled the prize.** With
  the county laid out for the first time, 4,915 of its 6,853 habitat lots are
  now red on something the missing setbacks would touch — 3,335 because no
  parking court can be drawn, 1,053 because the building will not fit, 521
  because nothing is buildable at all — against 1,574 when it was measured on a
  county the screen was not testing. The conclusion does not change with the
  size: **still no greens.** 706.10's habitat permit puts every one of these
  lots in front of a person regardless, so the prize is 4,915 lots moving from
  discarded to worth-a-look, and it is still a queue rather than a buy list.
  Two things now argue for *not* doing it next. It needs the four-hour envelope
  stage re-run, not the cheap end of the pipeline, because setbacks are cut
  before anything else. And it would relax a rule on the strength of a map we
  do not have: the habitat layer here is Metro's regional inventory standing in
  for the county's adopted map, graded C. Using a proxy to take ground away is
  cautious; using one to hand ground back is not. **Re-triggered: build it when
  the county's own adopted HCA map is in hand, or when somebody wants the 4,915
  in the queue badly enough to accept a C-grade boundary.**

- ~~**Portland's tree code — the biggest unread cross-reference in the city**~~
  Closed 2026-09-02: read, and it costs money rather than land. Four separate
  places in Portland's zoning code say tree requirements "are specified in
  Title 11" and then stop — and they say it in the same breath as building
  coverage and minimum landscaped area, which is why the ledger ranked it the
  largest unread reference standing next to a number we screen on. Now fetched
  and read.

  It does apply to us. But every number in it can be paid off. The
  preservation rule asks for a third of the twelve-inch trees and *all* of the
  twenty-inch ones, and then says in as many words that any tree not preserved
  "may be removed" on payment of a per-inch fee; a tree three feet thick adds
  only a posted notice that carries no comment period and no appeal, and the
  permit issues the next business day. The planting rule looks alarming — 40%
  of the site as "required tree area" — but that percentage only sets *how many
  trees*, and the ground each one actually needs is 50 to 150 square feet. On a
  7,000 sq ft lot the whole obligation is about 450 square feet of planting, and
  the city will take a cheque for any of it, at no cap.

  So no lot moves, and nothing goes on your list. What it does produce is a
  **cost line nobody had**: every Portland site now in play — and Portland is
  where the 74,446 newly-screened lots are — carries a tree fee that scales
  with the trees standing on it today. That belongs in the pro forma.

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
  - **13 standards the code states and the screen has no column for — all
    thirteen now have a reason, checked rather than assumed.** Six of them had
    only a place on the list. Walked on 2026-09-02, and the answers split in
    two. Three can never matter, because of the pod's own arithmetic: Gladstone
    caps units at *four* and the pod is four; the minimum-density triggers in
    Portland and unincorporated Multnomah ask for *two* homes and four clears
    two; and a ten-foot gap between buildings means nothing to a single
    building. Those three are now pinned by a test, so a future re-reading that
    changes one of the numbers cannot leave the reasoning standing.

    The other three are safe today rather than safe forever, which is a
    different sentence and worth keeping separate. A minimum *landscaped area*
    — 20% in Fairview and Happy Valley, 30% in Portland's apartment zones — is
    the one that would genuinely compete with the building for ground, and it
    sits on 50,132 lots of which **not one is green**. A minimum lot *depth*
    reaches 28 zones, and only one green-producing zone states one at all:
    Wilsonville's R, at 70 feet, against twelve greens whose shallowest is 120.
    Neither moves a verdict as things stand, and both would need a column
    before those zones could be trusted green.

    Walking the list also turned up **one zone the screen had made impossible
    to build in**, which is the opposite of the failure everyone watches for.
    Portland's IR is the only zone in the whole corpus whose front setback is
    written as a formula — one foot back for every two feet of building height
    — and for our 26-foot building that comes to 13 feet. The same table also
    caps the front setback at 10 feet. Held side by side those two say no
    building can legally stand there at all. They do not: a footnote says that
    on the frontages where the cap applies there is no minimum, and the cap's
    own heading limits it to transit streets and pedestrian districts. So it is
    13 feet back on an ordinary street with no cap, or right up to the street
    on a transit one — both buildable. Fixed, and a check now runs across every
    zone in the corpus so a rule that forbids everything cannot hide as a
    strict reading. No lot moves: IR has no greens and the screen has no column
    for a maximum setback yet.

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

    **Guarded 2026-09-02.** Both rows are marked *needs verification*, which
    means the screen sends every one of their 664 lots to review no matter what
    else the lot clears — so the looser permission buys those zones a
    measurement and cannot buy them a green. That is the whole reason they are
    allowed to stand while the legal question waits. The audit used to print
    them exactly like a dispute that *could* produce a wrong green, which read
    as an alarm that was not sounding; it now says which kind each one is, and
    a test goes red if anybody promotes either row to "verified" without
    settling the argument behind it.

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

  **Ported and run, 2026-09-02 — and now measured, which is the part that
  matters.** All 29 in-market zones are in the screen (Lake Oswego's six are
  left out: you have that city switched off, so its lots never reach a
  measurement either way). Every one arrives marked *needs verification*, which
  means none of them can come back green until somebody reads the numbers on
  the page.

  The run finished and **41,227 lots were measured that had never been looked
  at before**. Of those, **3,093 are in the review queue and 38,134 are red.
  None is green, by design.**

  So the pool was real and the prize is much smaller than the pool, which is
  worth being blunt about: most of that land fails a hard test the moment you
  look at it. The reasons, in order, are that the site plan will not lay out on
  it (12,848), it already holds a commercial building (8,023), the lot is
  smaller than its own zone's minimum (7,796), the pod does not fit (4,983),
  and it already holds an apartment building (3,077). These are Portland's
  apartment and mixed-use zones — dense, mostly built on, and mostly narrow.

  The honest result: **3,093 lots to look at, and a 30% blind spot closed.**
  Nothing needed from you.

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
  only raises it.

  **Run and measured 2026-09-02.** The floor now touches **2,644 lots** in the
  review queue — more than the 110 first estimated, because the newly-screened
  zones above brought their own floors with them — and **109 of those are held
  by the floor and nothing else**. Those 109 are the honest size of the
  question: one measurement of developable land on each would settle every one
  of them.

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
  turns out to have a corner rule.

  **That trigger fired on 2026-09-03 and the answer is still no — re-measured,
  10 lots.** Gresham was the city this clause was waiting for: it holds 30 of
  the 37 firing corner rules and it went from zero greens to 1,820. 95 of those
  greens are corner lots, 55 of them in a zone whose frontage or lot-width
  minimum rises on a corner — and **not one of the 55 falls below the raised
  number.** Gresham's corner minimums go 35 ft to 40, and every corner green it
  has is already wider than 40. The exposure is 10 lots: Wood Village's LR 12,
  where a corner takes the rear setback from 15 ft to 20, and a shrunken
  envelope is the one kind of corner rule this arithmetic cannot settle from the
  results file — it needs the geometry re-run. 10 lots does not buy a four-hour
  stage. Wilsonville's single rule (RN side yard) touches none of its 6 corner
  greens, and unincorporated Multnomah has no corner greens at all.

  Corner greens corpus-wide are now 1,596 of 16,530, so the exposure is still
  there the moment a city with a *setback* corner rule starts producing greens.
  Frontage and width rules can now be checked without building anything, which
  is the cheap half of this and is what was done here.
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
- ~~**Are the steep lots actually steep, or are we measuring the ravine at the
  back?**~~ **Asked and answered 2026-09-02, and the answer is no — closed.**
  A fair objection to every slope verdict in this screen: it grades a lot on
  the slope of its whole buildable envelope, and on a hillside lot that
  envelope includes ground the building will never touch. The question the
  product actually cares about is narrower — is the ground *under the
  building, its parking and its driveway* flat enough to set a fixed pod on?

  So it was measured, on the 2,275 lots that are held out of green by slope
  alone, on real fine-resolution lidar, with a complete site plan already
  drawn. The improvement footprints are a median 7,030 sq ft. Sampling slope on
  those instead of the whole envelope moves the typical reading from **26.8%
  to 26.3% — half a percentage point**, and clears **150 lots of 2,275 (7%)**.

  These lots are on genuinely steep ground. The measurement is not the problem
  and there is no cheap 2,000-lot win hiding in it. Worth knowing because the
  objection is a good one and will be raised again; it is now answered with a
  number rather than an opinion. (Working file `spike_footprint_slope.csv` on
  the compute box holds the per-lot readings if anyone wants to check.)

- ~~**The screen is measuring the wrong side of the lot in two cities**~~ —
  closed 2026-09-03; the measurement is taken and the numbers are below.
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

  **The other half shipped 2026-09-03, and the screen now takes the
  measurement.** Each city gets its own, because the two codes do not describe
  the same line: Oregon City draws it between the midpoints of the two
  principal opposite side lot lines, Tualatin draws it parallel to the street
  through the centre of the lot. 7,870 lots are measured — 7,262 of Oregon
  City's 10,863 and 608 of Tualatin's 952 — and the rest are refused rather
  than guessed at. The refusals are mostly corner lots, whose second street
  edge leaves only one side lot line to measure from, and which Tualatin's code
  sends to a different definition anyway.

  **It decides 34 lots: 8 out of the queue and green, 25 out of the queue and
  red, and 1 that had been passing.** The last one is the direction nobody was
  looking — a lot with generous street frontage that is pinched behind it and
  fails the standard the city actually wrote. It is the reason this rules in
  both directions rather than only rescuing lots; a measurement that could only
  say yes would be an amnesty.

  34 is far short of the 988 the item opens with, and that is the honest
  answer, not a disappointment. It is the same finding as the paragraph above:
  frontage was never the only thing wrong with these lots, and once you stop
  judging them on the wrong edge, most of them are still red for their area,
  their parking, or their envelope. What is now true is that **18 lots in
  Oregon City and none in Tualatin** are still held for a width nobody could
  measure, against 1,730 carrying the flag before.

  Where the measurement declines, the lot keeps exactly the treatment it had —
  short on frontage goes to review, and a lot clearing the number on frontage
  is left alone. Without that fallback the fix would have pushed 3,291 passing
  lots into the queue on the grounds that nobody had measured them, which was
  true of every lot in both cities the day before. What was deliberately *not*
  done is simply deleting the rule in those two cities, which would have moved
  all 988 straight into the pool of buildable lots — buying back some we are wrongly rejecting at the price of an
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
