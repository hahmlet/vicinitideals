# Completeness of the reading — and where a classifier would serve it

**Status: theoretical. Not queued, not scheduled, nothing built.** Parked
2026-09-21 for possible inclusion in a FLATS encoding refactor or a v2. This is
deliberately *not* in [FOLLOWUPS.md](../FOLLOWUPS.md) — that file is a queue of
work offered and awaiting a yes, and "do the next thing" means its item 1.
Nothing here is next.

The prompt was a cheap classification model (Jev, TypeSafe AI: a typed choice
plus a calibrated probability, no prose rationale, ~$0.042/1M input tokens and
$0 output, 70–500 ms, context contract 64K for state plus all questions and 32K
for state plus the single longest question — so many questions against one
loaded state cost barely more than one). The conclusions below are mostly about
this subsystem's epistemics rather than about that model, and outlive it.

The goal assumed throughout: **accuracy, determinism, and knowing 100% of what
there is to know.** Not fewer review hours. More hours are acceptable where the
reading gets more complete, and that reorders every recommendation.

---

## Two kinds of incompleteness, and only one is measured

**Known-field** — a value we have a field for and have not encoded.
`readiness.py` measures this exactly: eleven rungs in blocking order
(`no_zones` → `ready`), with `eligible` carried alongside so a switched-off
jurisdiction stays visible rather than filtered out. The instrument is good and
this document proposes nothing for it.

**Unknown-field** — a standard the code states that we have no field for.
Measured by nothing, by construction. `uncited.py` states the reason in one
line:

> a coverage ledger counts fields, and there is no field for the slope of a
> plane.

Milwaukie's Table 19.301.4 side yard height plane (20 ft at the required depth,
45° slope — an 11 ft side yard for a 26 ft building, not the encoded 5 ft) sat
on the same page as an encoded number since August, and every ledger reported
clean. Completeness cannot be measured against our own schema, because the
schema is the thing that is incomplete.

`uncited.py`'s subtraction — every line stating a measure, minus every line an
encoded value quotes — is the only instrument that can see this class.

---

## 1. Recall at the reading boundary

The subtraction above is only as complete as its recogniser for *"a line
stating a measure."* When that recogniser under-fires the unread pile is
understated **and nothing can tell**: the missed line is invisible to the
coverage ledger and to the subtraction alike.

The job: ask of every line of all 299 stored documents, independent of whether
a field exists for it — *does this sentence state a dimensional requirement
that could bear on placing this building?* Run it as a second opinion against
the existing recogniser and reconcile the disagreements. The output is never a
decision; it is an addition to the pile that `uncited.py` must then account for
deterministically. Order of $0.25 for a full pass, re-runnable per commit.

Two smaller instances of the same pattern, useful as warm-ups because both have
a known false negative to validate against:

- `routing.py` matches one sentence shape on purpose ("what keeps this ledger a
  page rather than a corpus"). Its miss is Portland 33.266.120 → 33.266.130,
  where the aisle standard was in a file already in the store.
- `footnotes.py` rests on the `NOTES_HEAD` / `NOTES_LEAD` / `LEGEND_LINE`
  family. Nine notes blocks hid in Gresham's Civic Neighborhood chapter behind
  a caption cell that split `Table 4.1220(` from `A) Notes:`; exactly one line
  in the corpus matches `NOTES_LEAD`, and twenty-four notes sit behind it.
- `extract.py`'s `tag_of()` returns `None` on an unclear sentence, and an
  untagged line is a gap.

## 2. Reconciliation with a named residual, as the proof

`footnotes.py` already has the right epistemic shape and should be the
template. It turns *"we captured the footnotes"* into *"we captured them, or
the document is on a named list"* — `unmarked` for a body nobody points at,
`unbodied` for a marker nothing defines. A weaker claim, and a checkable one.

**Completeness is claimable only where the residual is named rather than
assumed empty.** The work is an audit: which subsystems produce a claim of that
shape (footnotes, readiness, uncited and gaps do), and giving a named residual
to the ones that do not.

## 3. Golden results — what neither of the above catches

Neither recall nor reconciliation catches a rule the resolver applies wrongly
*everywhere*. Reading `preempts: cap` as a substitute handed every Portland lot
four stalls — uniform across every lot, no outlier anywhere to detect. Reading
more does not find it; only pinned expected outputs do.

There are 179 test files, many named for the lot or city that produced them,
and no committed golden result set — which FLATS_PLAN §"how rows get made"
calls "the only control" on a silent encoding error, because a silent encoding
error fails identically across all lots at once. Probably the largest single
exposure in this list, and not a classifier item at all.

---

## What was considered and dropped

**Corpus-relative anomaly ranking** — feeding each encoded value with its
quote, its neighbouring zones in the same layer and the same zone class across
other layers, and asking `typical / locally-justified / anomalous /
contradicts-its-own-quote` over the ~1,792 qualified values. This is how
`words.py` and `glossary.py` found their classes (four cities with four
incompatible corner-lot tests; seven with seven net-acre subtraction lists —
nobody predicted those, the comparison surfaced them), and `missed.py` already
does it arithmetically.

It was the most interesting idea here under a *cost* goal and it is not a
completeness instrument: it reorders a queue so the weird rows float, which
matters when you cannot read everything. The decision is to read everything.
Keep it in mind as a sequencing convenience, not as a way of knowing more.

**Footnote presence and disposition lookups.** "Does this data point have a
footnote" and "have we encoded it" are a census and a register lookup.
`qualified.py` scopes a note to its whole *region* deliberately — "an
over-scoped footnote costs a review, an under-scoped one costs a false GREEN" —
and `dispositions.py` defaults to `unread`, which blocks. A probability can
only narrow the region, which is the unsafe direction. These stay deterministic.

**One genuine gap found in passing, worth keeping whatever happens to the rest:**
`applied.py` checks that an `encoded_as` claim's *tokens* exist in the layer
(field names, registry conditions, zone codes, figures → `confirmed` /
`elsewhere` / `broken` / `unreadable`). It does not compare meaning. A note
stating a **maximum** front setback encoded as a **minimum** passes every token
check there is, silently. `FieldDef.is_maximum` is ground truth for a large
share of that, which makes it a free calibration set for any polarity check —
and the cheapest available test of whether a classifier's probabilities mean
anything on this corpus, before one is trusted to widen anything.

---

## Standing constraints

- Nothing probabilistic may reach a value, a verdict, or a signature.
  `extract.py`: *"Nothing here can produce a trusted number."* `verify.py` is a
  hash over jurisdiction, zone, field, value, citation and quote. A classifier
  may widen a candidate set that a deterministic pass then accounts for, and
  nothing else.
- A model that returns a probability and no rationale cannot be cited, and this
  system's auditability is citation all the way down.
- An exhaustive ledger nobody works becomes wallpaper. `triage.py` exists
  because `crossrefs.py` is "a good ledger and a bad worklist" — 1,468 rows
  sorted by loudness. Anything added here ships with a queue sorted by lots at
  stake.
- The FLATS firewall applies: none of this may touch `app/engines/` in the same
  commit, and nothing under `flats/` imports `app.engines`.

## The honest limit on "100%"

The source cannot be made deterministic — 299 declared documents, 19 layer
files, prose and grids from as many codifiers. What is achievable is **closure
over a frozen corpus**: the same input always produces the same reading, every
reading is either signed or explicitly named unsigned, and drift is caught when
the corpus moves. The nightly re-fetch and the `stale` rung already do the last
part. That is the real version of the goal, and it is the one the subsystem is
already built toward.
