# 32. Windows CPU spikes (Steph 2026-10-02: "60%+ of my CPU on Python").

32. [Steph] [(B) Copilot-able after a yes] [scan: NO] **Windows CPU spikes (Steph 2026-10-02: "60%+ of my CPU on Python").**
   Measured: at idle Python uses ~2% of the PC. The bursts are (a) test runs
   on Windows -- `pytest flats/tests -n auto` starts 16 workers, one per
   thread; the Stop hook's `pytest tests/` when `app/` changed; (b) the
   code-review-graph PostToolUse hook re-parsing after every Edit/Write/Bash;
   (c) NOT vicinitideals: the claude-mem plugin's chroma-mcp leaks a copy
   per session -- 256 Python processes, 66 uvx trees (26 orphaned), 1.25 GB,
   6,260 CPU-s since 2026-09-30. County runs already happen on LXC 137.
   DONE 2026-10-02: 137 raised 12 -> 16 cores, 24 -> 32 GB (Steph); full
   re-screens capped at once a week (runbook §4c). OFFERED, PENDING:
   (A) kill the orphaned memory-plugin copies; (B) cap local test workers
   (`-n 4`) so tests never take the whole PC. Running tests on 137
   instead was DECLINED by Steph 2026-10-04 -- do not re-offer.
