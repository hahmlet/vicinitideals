# Human TODO — things only Steph (or another human) can move

This is the standing list of decisions, phone calls, and readings that the
agent cannot do alone. The agent maintains it: items get added when work
surfaces them, and struck through (with a date and what happened) when they
close. Items are ordered by how many lots ride on them, biggest first.

Pipeline state when last updated (2026-09-01): **green 11,824 · review 31,912
· red 204,902** across 13 cities laid out with real site plans.

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

## 2. Two short emails: confirm the assumed 24 ft aisle — **hardens 985 greens**

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

## 3. One question for a building-code expert: accessible (ADA) parking — **every city at once**

Open question, deliberately parked: does Oregon's building code (OSSC) require
one accessible stall — 13 ft wide with its access aisle — for a **4-unit,
no-elevator building with surface parking**? 

- If **no**: closed everywhere, nothing changes.
- If **yes**: every court in every city needs one wider first stall, which
  shrinks tight lots in all 13 laid-out cities simultaneously.

One architect or code consultant can answer this in a sentence. It was parked
rather than guessed precisely because the answer moves lots everywhere at once.

## 4. Business decision: Milwaukie legally caps parking at 4 stalls — **845 greens**

Milwaukie's code caps a quadplex at **1 parking space per unit — 4 total**,
which is exactly the marketability floor. Every legal Milwaukie site plan is a
minimum-parking plan; the 1.5-per-unit and 2-per-unit tiers are not something
that city will permit at any lot size.

Decision needed: **is 1 stall per unit marketable for this product?** If not,
Milwaukie's 845 greens should be deprioritized before any diligence money is
spent on them. No agent work either way — this is a product call.

## 5. Data ask: sewer coverage in Happy Valley, unincorporated Clackamas, Tualatin

These areas' sewer districts (WES / Clean Water Services) do not publish their
sanitary main maps, so lots there can never clear the "sewer confirmed" check
from public data — they sit at review on sewer forever. District *boundaries*
partially close this in Clackamas already (outside every district = red), but
inside a district stays yellow without the mains.

The fix is a records request or data ask to the districts for their main
layers. A utility will often hand this over on request; it is not public GIS.

## 6. Start signing: the only thing between FLATS and trusted GREEN

Every zoning number in the corpus is *encoded* — transcribed with a quote —
but none is *verified*: nobody has yet sat down, read the quoted sentence
against the number, and signed it. Until values are signed, the FLATS side of
the house can't issue a fully trusted GREEN by design.

This is deliberate — signing was pointless while encoding churned. The corpus
has been stable for a while now. Decision needed: **when to start signing
sessions**, and in what order. Sensible order is by greens at stake: Gresham
and Happy Valley first, then Portland. Each session is you (or a delegate)
reading quotes against numbers — tedious, but each one is permanent.

## 7. Optional legal read: the state's "use single-family standards" rule

OAR 660-046-0220(2)(e)(E) says a quadplex's parking dimensions must be *the
same as single-family's in the same zone* — and no city writes down what its
single-family parking dimensions are, so the rule points at nothing findable.
Where single-family practice is looser (it usually is — a driveway beside a
house), our screen is **stricter than the law requires**: that costs us lots
but creates no risk. A land-use attorney could say whether it's worth pressing
in any particular city. Perfectly fine to accept as-is; listed so the
conservatism is a choice, not an accident.

## ~~8. Housekeeping: two old feature branches~~ — closed 2026-09-01

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

- **Portland-administered pockets** (PCC 33.266 applied to the 1,489
  unincorporated-Multnomah lots Portland administers) — worth ~109 lots net
  after overlays; can only add greens.
- **Wilsonville Public Works Standards + Gresham's engineering manual** —
  both hold access widths for busy-street frontages that no corpus file
  declares yet; fetch and read.
- **Unencoded zones**: Lake Oswego NC (93 lots), Wilsonville V and TC.
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
- **"Reaches with no field" refusals**: e.g. Wood Village's forward-access
  rule applies to the pod and the data model has no field to hold it — model
  extension, batched with the next such find.
