# Copilot briefs

Cold-start briefs for the Copilot queue (docs/FOLLOWUPS.md section 3). On the
1st of each month the queue is fired in batches of 4 until the monthly quota
is gone; a quota error (HTTP 402) means stop.

- `briefs/common.txt` -- the rules appended to every brief.
- `briefs/<task>.txt` -- one task each; the file name is the worktree and
  branch slug (`flats/<task>`).
- `run_batch.sh` -- the runner used on 2026-10-16: one worktree per task off
  origin/main, Copilot runs in parallel, prints each branch's commits and
  Copilot's final message. Edit the task list in it before running.

The coordinator (Claude) reviews every branch, runs ruff, the firewall check,
the touched suites and the unit gate, merges, deploys and reads CI.
