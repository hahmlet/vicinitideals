# Cloud brief: drafting a new county

For a cloud session (claude.ai/code) asked to draft a new county's FLATS
layers. Read [ENCODING_RULEBOOK.md](ENCODING_RULEBOOK.md) first; this file
only says what is different when you run away from the home network.

## What you cannot reach

The county map, the app database, the deploy script, Docspell and every MCP
server live on a home network you cannot see. So:

- **You cannot re-screen, bound, promote or deploy.** Rulebook checklist
  steps 11 (overlay data) and 13 (re-screen and read the losses) are the
  local agent's. Step 14 (signing) is Steph's.
- **CLAUDE.md's "done means deployed" does not apply to you.** Done means a
  pushed draft branch and a handoff note (below). Never push to `main`,
  never merge, never open the branch as ready for review.
- **Hook noise is expected.** The repo's hooks call `pwsh` and
  `code_review_graph`; if they fail in your environment, carry on.

## Scope

- **Yours:** rulebook checklist steps 1-10 and 12, for the county you were
  given, as `draft` values only.
- **Not yours:** `app/` (the underwriting product), `Lot Analysis/quadfit/`
  (the county map runs on the home network), and every existing county's
  layers and footnote files. If a test fails because quadfit holds no rules
  for your county, record it in the handoff; do not edit quadfit.
- **Not yours either:** `docs/FOLLOWUPS.md` and `docs/HUMAN_TODO.md`. Local
  sessions edit them daily and you would collide. Put everything you would
  have written there in the handoff note.

## How to work

- **Branch:** `flats/<county>-draft`. Commit per city, largest city first,
  and push after every commit. A cloud session can end without warning.
- **One city at a time**, each to the checklist's step 10 before the next.
  A half-read county spread across every city is worth less than three
  finished cities.
- **Tests:** targeted tests while you build; the full
  `uv run pytest flats/tests -q -n auto` once before each push. Report the
  result honestly in the handoff, failures included.
- **A site that refuses you** (codifiers sometimes block cloud addresses):
  record the URL and what you tried, and move on. Never substitute a mirror,
  a search-engine cache or a page that re-renders the code. The rulebook's
  "store the adopted document" rule has no cloud exception.
- **An owner decision** (the rulebook's §10 kind): do not stop. Take the
  conservative reading, mark it in the layer's comment, and list it in the
  handoff as a question.
- **Doubt about which row, column or noun:** the conservative reading, plus
  a line in the handoff. The local agent re-reads every number blind before
  anything is screened, so a flagged doubt costs minutes and a hidden one
  can cost a false GREEN.

## The handoff note

`docs/flats/handoff/<county>.md`, updated with every commit. The local agent
starts from it, so write it for someone who has not seen your session.

1. **Cities:** done, partly done (to which checklist step), not started.
2. **Documents:** every chapter stored, and every one that failed to fetch
   with its URL.
3. **Zones:** per city, the list and where it came from (use table, map
   legend), and any zone you could not place.
4. **Refusals and absences:** every NOT ENCODED and every "the code states
   nothing", each with the grep that supports it.
5. **Doubts:** every conservative reading you took in place of a decision,
   and every number you would want checked against real lots.
6. **Questions for Steph**, in plain English with no code terms: what the
   code says, the two readings, and what each would mean for which lots.
7. **Tests:** the last full-suite result, and every failure with your
   reading of why.
8. **Owed locally:** quadfit rules for the county, the county map and
   overlay data, the blind second reading, re-screen and promotion.
