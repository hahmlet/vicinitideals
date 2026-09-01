# Human TODO — things only Steph (or another human) can move

This is the standing list of decisions, phone calls, and readings that the
agent cannot do alone. The agent maintains it: items get added when work
surfaces them, and struck through (with a date and what happened) when they
close. Items are ordered by how many lots ride on them, biggest first.

Pipeline state when last updated (2026-09-01, after the Portland parking
correction): **green 10,179 · review 30,185 · red 208,274** across 13 cities
laid out with real site plans. Portland lost 1,645 greens that morning because
we found we had been screening it against a parking table written for a
different kind of plat — its own numbers for the plat we actually draw are
bigger, so its courts are bigger, so fewer lots hold one.

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

## 2. One decision: may a coarser elevation map grade a lot green? — **7,231 lots**

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
**7,231 lots straight to green**, and it would be **wrong about 1.5% of the
time** — roughly 110 of those 7,231 would turn out, on a site visit, to be
steeper than they looked. It is wrong in the safe direction the rest of the
time: it hardly ever calls a flat lot steep.

So the trade is: **+7,231 green lots (a 71% increase on the whole corpus),
against roughly 110 of them being duds you would discover on the first visit.**

- **Yes** — flip one setting, re-run, those lots grade green like any other,
  and a column records that their slope came from the coarse map so anyone can
  filter them back out.
- **No** — they stay in the review queue, but now with a slope number attached
  instead of a blank, which at least makes the queue sortable.

Nothing else is blocked on this; it is purely how bold to be. Same shape as the
drive-aisle call you made on 2026-08-31, and the same reason it is yours: it
trades a small chance of wasted diligence for a large amount of pipeline.

## 3. Two short emails: confirm the assumed 24 ft aisle — **hardens 985 greens**

Milwaukie (845 greens) and Wilsonville (140 greens) publish a 9 × 18 parking
stall and **no drive-aisle width anywhere** — checked all the way through the
state's own "use your single-family standards" redirect. Per your 2026-08-31
decision, those lots are drawn to the national engineering minimum (24 ft,
ULI/NPA) and grade green, because state law (ORS 197A.400) only lets a city
apply written, objective standards to housing — and a width nobody wrote down
is not one.

The residual risk: both cities have language that *could* be used to send
"drive aisle design" to a human reviewer. A one-paragraph email to each
planning department — *"your code gives a quadplex a 9 × 18 stall and states
no drive-aisle width; we intend 24 ft two-way; please confirm that is
acceptable"* — converts the assumption into a confirmation. If they answer
with a different number, the agent re-runs with theirs the same day.

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

## Queued for the agent — no action needed from you, listed so nothing is invisible

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
- **Unencoded zones**: Wilsonville V and TC (Lake Oswego closed above).
- **Corner-lot status**: 14 jurisdictions now define what a corner lot is;
  nothing yet computes which lots *are* corners. Worth ~10 ft of buildable
  envelope wherever corner variants exist (e.g. all of Wood Village).
- ~~**quadfit/FLATS config divergences**: LR-7 front setback (20 vs 10) and
  Wood Village MR 2 minimum lot — cleanup; zero greens ride on either
  today.~~ Closed 2026-09-01: both aligned to the quoted code text and the
  report re-run. LR-7's minimum lot was the big one (7,000 → 20,000 — the
  county wants 5,000 sq ft *per unit*); nine LR-7 lots moved review → red,
  no green moved anywhere. LR-7's building envelopes still reflect the old
  smaller setbacks until the next full pipeline run; at most 15 non-green
  lots ride on that.
- **Coarse-DEM plumbing shipped 2026-09-01** — the 1/3 arc-second national
  DEM is fetched, warped and sampled, `slope_source` rides in the CSV, and the
  false "grade A / 1 m DEM" coverage claims for four cities with no elevation
  data at all are corrected. Only the green/no-green switch is left, and that
  is item 2 above.
- **"Reaches with no field" refusals**: e.g. Wood Village's forward-access
  rule applies to the pod and the data model has no field to hold it — model
  extension, batched with the next such find.
