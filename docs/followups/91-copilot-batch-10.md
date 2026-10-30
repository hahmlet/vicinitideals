# 91. Copilot cleanup batch 10 -- QUEUED for 2026-11-01.

91. [Copilot] [scan: no] **Copilot cleanup batch 10 -- QUEUED for 2026-11-01.** Copilot's monthly quota ran
   out 2026-10-16 (HTTP 402) and resets 2026-11-01. Steph RULED 2026-10-16 (memory
   feedback_copilot_monthly_burn.md): on the 1st of each month, start Copilot on its tier of work
   right away and run it until the quota is gone; don't buy more credit and don't offer it; when
   the quota is gone the queue waits for the 1st -- Claude does not take it over. Fire briefs in
   parallel batches of 4; a 402 means stop, not retry. Before firing (reference_copilot_cli.md):
   Steph checks the real balance on github.com/settings/billing, pin a cheaper model instead of
   auto, stop at ~70% of the allowance.
   Four briefs written (docs/copilot/briefs/, runner docs/copilot/run_batch.sh), worktrees + branches left
   as-is (flats/nul-note-posts, e2e-waits, test-hygiene, flags-cache-geometry; local only, at
   main's tip; e2e-waits has a partial uncommitted edit). (a) NUL byte in the note of an otherwise
   valid /ui/flats/sign (and passage, reading, words, triage, check) POST -- likely 500, strip NUL
   before storing. (b) E2E waits that pass without checking: test_flats_reading filter-survives
   (wait_for_htmx swallows), test_flats_price ppu reload race (assert URL), test_flats_page_check
   cited-page flake (poll the scroll). (c) Test hygiene: test_permit.py:147 `or True`; five blind
   pytest.raises(Exception); test_missed temp-file leak; dead _MAX_WRAP; four unused loop
   variables. (d) Cache flags.yaml parse (64 ms/request, key on mtime) and dedupe _outline/_plan
   geometry behind a golden test.
