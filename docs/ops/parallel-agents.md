# Parallel agent sessions

Steph runs several agent sessions at once (2026-10-04). Each session owns one
FOLLOWUPS item, called a lane. Read this file before you start, and again
before every merge. It sits on top of [worktrees.md](worktrees.md) and
CLAUDE.md, and does not replace them.

## Lanes

Update this table when a lane opens or closes. Commit it on `main` by
explicit path.

| Lane | FOLLOWUPS | Worktree (`../vicinitideals-worktrees/`) / branch | Owns |
|---|---|---|---|
| street-class | 41 | `street-class` / `flats/street-class` | Street functional class per lot line. It owns the class column(s) in `Lot Analysis/quadfit/s4_edges.py` and their reading in the bridge; the `local_street` fact; `lowest_class` access on corner and through lots (`flats/score/paper.py` `SIDE_STREET_ACCESS`, the access choice in `flats/ingest/quadfit.py`). |
| check-margins | 37(ii) | `check-margins` / `flats/check-margins` | Storing each check's margin on PASSING lots: the margin fields on screen results, the bridge's output columns, the loader, and the pod report `/flats/flags/report`. Data only: no lot colour may move. |
| fire-curb | 29 | `fire-curb` / `flats/fire-curb` | Where the fire truck stands: the curb/pavement-width source, its own new stage or file, and the truck offset in `flats/fit/fire.py`. It does NOT own `s4_edges.py`; it adds a separate file. |
| water | 42 | `flats-tigard` / `flats/net-area` | Water, wetland and flood ground before placement. Now: Portland's Constrained Sites "z" overlay (the `constrained_sites_overlay` fact, its bridge answer, the 33.418 variants in the Portland and Multnomah layers). Next: ruling each quadfit `flag` overlay (no-build carve / permit flag / ignore), the FEMA fringe, and wetland maps for the cities that have none (`Lot Analysis/quadfit/config/overlays.yaml` actions, `flats/rules/net_area.py`). |

## Rules

1. **One worktree per lane.** Make it with the worktrees.md recipe. Never edit
   code in the primary checkout. The one exception is `docs/FOLLOWUPS.md`,
   which goes through the index trick (rule 9).
2. **Shared files are edited narrowly.** These are the shared files:
   - `flats/ingest/quadfit.py`
   - `flats/score/screen.py`
   - `flats/rules/fields.py`
   - `flats/rules/conditions.py`
   - `flats/config/flags.yaml`
   - `Lot Analysis/quadfit/s4_edges.py`
   - `app/api/routers/ui_flats.py`

   In these files, change only what your lane needs. Put new code in new
   functions or new files. Never reformat, rename, reorder or move code you
   do not own. Rebase on `origin/main` often (`git pull --rebase`). Whoever
   lands second resolves the conflict, and keeps the other lane's code
   intact.
3. **Merging.** Rebase onto `origin/main`, then run all of these:
   - the full `flats/tests` suite;
   - `uv run pytest tests/ -q -m unit --ignore=tests/e2e`. It holds
     `test_every_screen_reason_is_said_in_words`: a new screen reason needs
     a sentence in `_REASON_WORDS`.
   - `uv run ruff check app/ tests/ flats/ scripts/`;
   - `uv run python scripts/check_flats_firewall.py --base origin/main`.

   Then push fast-forward: `git push origin HEAD:main`. Never force-push
   `main`. Never commit `.claude/settings.json`.
4. **Migrations.** Take the next free number at merge time. If another lane
   landed one first, renumber yours. `alembic heads` must show exactly one
   head.
5. **LXC 137: one heavy job at a time, for all lanes.** Two bridge runs at
   once have OOM-killed 137 twice; the pool then hangs forever. Wrap every
   job that loads lots in the lock: a bridge run, a bound, a quadfit stage,
   even a one-lot probe (big lots reach 3-7 GB):

   ```bash
   nohup flock /root/heavy.lock <command> > /root/<lane>_<what>.log 2>&1 &
   ```

   `flock` waits its turn. Do not route around it.
   - Use at most 14 processes per run.
   - Put your checkout at `/root/code/<lane>`, a worktree of
     `/root/code/vicinitideals`. Put outputs in `/root/<lane>_*`.
   - Never change `/root/code/vicinitideals`. It is the weekly run's
     checkout.
   - Never change shared `data/` files in place; write new ones beside
     them.
   - Kill only PIDs you started. Never `pkill -f` a pattern: it matches
     your own ssh command.
   - Washington TLID lists: drop right-of-way polygons first
     (`grep -v ' ROW$'`). They are roads, not lots, and one chunk of them
     ran over an hour at 7 GB.
6. **The weekly full re-screen (~2026-10-08) belongs to no lane.** No lane
   starts a full re-screen, a partial re-screen, or a promotion. A lane
   that wants its change in that run must be merged and deployed by the
   end of 2026-10-07.
7. **Deploy through the lock.** Run
   `ssh -o BatchMode=yes root@192.168.1.28 "flock /tmp/vicinitideals-deploy.lock bash /root/deploy-vicinitideals.sh"`,
   then read the smoke output. A deploy ships all of merged `main`, other
   lanes' work included; that is expected.
8. **CI.** Read CI after every push (`gh run list --workflow "vicinitideals CI"`).
   If another lane's commit turned CI red, tell Steph and that lane's
   session. Fix it yourself only if the fix is one obvious line.
9. **FOLLOWUPS.** Edit only your own item, through the index trick:
   - `git show origin/main:docs/FOLLOWUPS.md` to a file, then edit it;
   - `git hash-object -w --no-filters` that file;
   - `git update-index --cacheinfo 100644,<sha>,docs/FOLLOWUPS.md`;
   - `git commit` with no pathspec.

   Never `git checkout` the working copy. A new item takes the next number
   after re-reading `origin/main`.
10. **Memory.** Write your own new memory files. In `MEMORY.md`, re-read it,
    then add or change only your own line.
11. **Steph.** Plain English, no jargon. Each lane asks its own questions.
    Before shipping, report how many lots move and in which direction. Any
    change that could turn a lot GREEN needs a bound whose gains are read
    one by one. Never a false GREEN.
