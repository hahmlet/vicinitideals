# 54. Code-change reader on the Claude API credit ($100/month). Steph 2026-10-07 picked this one and DECLINED the other two offered (a second reader beside signing; moving the finance-side email/pro forma reading off local Ollama).

54. [Steph] [scan: NO (warn-only: changes no rule and no answer; the fixes it leads to land at the next weekly)] **Code-change
   reader on the Claude API credit ($100/month). Steph 2026-10-07 picked this one and
   DECLINED the other two offered (a second reader beside signing; moving the finance-side
   email/pro forma reading off local Ollama).** Why it matters: nothing re-checks the codes
   today -- `fetch --all --check` (flats/provenance/fetch.py, the corpus watch) exists but no
   schedule runs it -- and Steph has done NO sign-offs (told 2026-10-07), so the map is
   as-if-signed and an amended number keeps answering from the old words until somebody
   happens to re-read. Plan, Steph to approve before building:
   (a) Cadence: WEEKLY celery beat task on 114, built like `flats_probe_task` (warn-only,
   writes rows, changes no rule): fetch every declared document (~680) into memory, compare
   with the store in the image, store nothing. Weekly because detection costs no credit;
   daily only invites the 429s Municode already throws (pace per host; a 429 = "not checked
   this week"; 3 misses in a row = warn). Early Monday Pacific; nothing runs on 137.
   (b) Proactive poll, reactive AI: the model runs only on what the sweep finds. Free
   deterministic pass first: a value whose every cited line survives byte-for-byte
   (`repoint.survivors`) or word-for-word (`loose_line_map`, a republish) is "moved, words
   unchanged" -- no call. Only values whose own lines changed are sent, one request per
   changed document (old slice + new slice + all its affected values). One city changing
   >20 documents in a sweep is a reformat, not an amendment: no calls for that city until
   Steph says. Later, not v1: DLCD's notices of proposed amendments (cities notify DLCD
   before the first hearing -- confirm the feed is public and readable) as early warning
   that never changes an answer.
   (c) Code checks the model before anything is queued: structured output per value =
   unchanged / changed (new number) / removed / cannot_tell + the new sentence VERBATIM.
   The quote must exist in the fetched text and the new number must appear in it, else
   cannot_tell. Stricter/looser is computed from the field's min/max sense, never asked.
   The model never signs and never edits YAML.
   (d) Interim map (Steph's call; recommended): stricter or cannot_tell -> greens whose
   stored room on that check (check margins 7dc34722) is less than the change -- every
   green in the zone for cannot_tell -- get a "city changed this rule, being re-read" flag
   that shows yellow until fixed; looser -> no colour change (a missed lot, not a false
   promise); unchanged -> nothing. Display-only if the flag tables can carry a colour
   without a re-screen (check); otherwise it rides the next weekly.
   (e) Who acts: with no sign-offs every number is a draft, so a changed number is
   ENCODING work, not review: findings land on an agent work list ("do the next thing"
   picks it up), the agent re-reads, runs `fetch --refresh --repoint`, fixes the encoding,
   the next weekly moves the answers. Only a change to a number Steph HAS signed goes to a
   Steph queue (old/new sentence with the change marked, our number, the model's reading,
   greens at risk; Still right / Changed to X / Needs a closer read; stricter-with-greens
   first). Resend email only on weeks with findings, plus a Lots-page banner like the
   county probe's. A backlog is safe by construction: (d) keeps at-risk greens yellow while
   it waits, so waiting costs missed lots, never a false GREEN. For when signing starts:
   an inbox signature hashes the quote ADDRESS, not the words, so an amendment at the same
   line numbers leaves it standing -- the watch must mark those rows too.
   (f) Credit: the watch has FIRST CLAIM, always. Expected a few dollars a month (~10-15
   cents per changed document, claude-opus-5 at medium effort through the Batches API, half
   price, results within 24 h). Even every document we hold changing in one month roughly
   fits one month's credit, so the watch alone cannot carry a backlog from month to month.
   Background work (item 55) only spends above a sliding floor: $40 to day 21, $20 until 3
   days before reset, $5 in the last 3 days (last batch submitted 2 days before reset).
   Ledger row per call; hard cap = the credit, set in the Anthropic console. If the watch
   still runs dry (a mass republish): findings queue "not pre-read", count as cannot_tell
   for (d), and are read first after reset, before any background work. No Ollama
   fallback -- a missing note is safe, a wrong "unchanged" is not. Assumed: unused credit
   does not roll over -- confirm, and confirm the reset day (calendar month or billing day).
   (g) Model by test, not assumption. Steph asked whether comparing against our encoding
   lets model and effort drop. The comparison is narrower than encoding, but our errors
   live in READING the text (wrong column, short headers, footnote markers, orphaned
   numerals), which the structured side does not help, and the costly miss is one-sided
   (false "unchanged" = possible false GREEN); at this volume the saving is a dollar or two.
   Answer key: real past refreshes in git (the Gresham 4.1400 renumber etc.) + planted edits
   on real cited passages (one number changed, a table column swapped, a pure reformat,
   untouched controls). Run claude-opus-5 and claude-sonnet-5 at low/medium; ship the
   cheapest with zero missed planted changes and zero unverifiable quotes. Test costs a few
   dollars. Before any of it: confirm the credit covers an API key the app can use; key in
   VM 114 .env only.
