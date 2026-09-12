# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Commit the quadfit alley + far-side-guard patch.** Nine files under
   `Lot Analysis/quadfit/` are modified and uncommitted (common.py, rules.yaml,
   lotdims.py, s1_normalize.py, s4_edges.py, s5_envelope.py and three test
   files). Last session reported 209 quadfit tests passing with it. Carried
   from the 2026-09-11 session — re-run the quadfit tests before committing.
2. **LXC 137 `alley_run2` failed at `s6_placement.py` (missing file).** The
   pipeline re-run with the alley patch stopped at s6; the first run's s5 output
   is on disk. Find out what s6 could not find, then finish the run and publish
   the green/review/red counts (see the Quadfit memory before quoting numbers).
   Carried from 2026-09-11.
3. **Portland "end of street" arc is knowingly unhandled** in `_is_clip` — the
   one-sided clip logic was reverted because it mis-clipped corner-lot second
   fronts. Decide whether to handle it another way or record it as a refusal.
   Carried from 2026-09-11.
