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
| utility-easement | 43 | `.claude/worktrees/bridge-cse_013p9pShugj6MCoHZD7G4bso` / `flats/utility-easement` | Steph's 2026-10-01 utility easement rule (Beaverton BDC 20.05/20.22 note 7; Oregon City if ruled): the street-yard floor the bridge fits a lot at where the code forbids building on a utility easement nobody maps, the `utility_easement` answer that floor gives, `flats/config/easements.yaml`, `flats/fit/easement.py`, and the UTILITY-EASEMENT-ASSUMED flag. In shared files only: one LotFacts field + the flag in `screen.py`, the floor in `envelope_for` and one wrapper around `_screen_lot_once` in `quadfit.py`. |
| scan-throughput | 46 | `.claude/worktrees/bridge-cse_01Jy7PvJ5jpm4MaSvtZGhgCw` / `worktree-bridge-cse_01Jy7PvJ5jpm4MaSvtZGhgCw` | How the bridge runs, never what it answers: `flats/ingest/batch.py` (costliest lots first, chunks started as free memory allows, a dead worker costing one lot, the answer cache and the book of lot costs beside it, `timings.parquet`). In `quadfit.py` only the one call in `run()` that hands the lots to it, and the `--cache` flag. Must move no answer. |

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
   nohup flock -o /root/heavy.lock <command> > /root/<lane>_<what>.log 2>&1 &
   ```

   `flock` waits its turn. Do not route around it.
   - Always `flock -o`, launched from a plain shell. Without `-o` the
     command inherits the lock. A job it then chains (`flock ... &` at the
     end of a script) waits for a lock its own parent holds, forever. On
     2026-10-06 that left 137 idle for 70 minutes. Never start a heavy job
     from inside a lock hold: put every pass in one script instead.
   - Use at most 14 processes per run.
   - Put your checkout at `/root/code/<lane>`, a worktree of
     `/root/code/vicinitideals`. Put outputs in `/root/<lane>_*`.
   - One fixed worktree per commit you run:
     `git -C /root/code/vicinitideals worktree add --detach /root/code/<lane>_<sha> <sha>`.
     Never `git checkout` to switch commits inside a script. `git worktree
     add` silently prunes the entry of any worktree whose folder was moved
     or renamed. That folder loses its git link the moment any lane adds a
     worktree, and a script that switches commits in it keeps running the
     old files. Before each pass, the script asserts
     `git -C <tree> rev-parse --short=8 HEAD` is the sha it wants and the
     tree is clean (or, for a patched tree, that the patched files' md5
     match).
   - Pass `--cache /root/bridge_cache` to every bridge run (FOLLOWUPS 46).
     A lot whose row, code, config and input files are all unchanged is
     read back instead of screened again. That makes the second "before"
     run of the same commit nearly free, and a run re-launched after a
     crash picks up where it stopped. Any change under `flats/` (tests
     aside) misses for every lot: the cache saves repeats, not first runs.
     Folders unused for 14 days are deleted by the next run. Since
     FOLLOWUPS 48 the bridge keeps a cache without being asked, in
     `bridge_cache` beside `--out` (`/root/bridge_cache` for a run in
     `/root`); keep passing the flag, because a base tree from before then
     does not. `--no-cache` turns it off, to time a cold run.
   - Each bridge run writes `timings.parquet` beside `lots.parquet`: one
     row per lot screened, with seconds and memory. Read it before
     guessing why a run was slow.
   - Since FOLLOWUPS 46, a bridge run starts a chunk only while the
     machine's free memory covers what it and the chunks already running
     may still grow into, plus 3 GB. What each lot cost the last time
     (seconds and peak memory) is kept in `book.parquet` in the cache
     directory, so a repeat run orders and sizes the lots by what they
     really took; a lot it has never seen is guessed from its area.
   - A worker the kernel kills anyway costs one lot, not the run: the
     lots it finished are kept, the lot it was on runs again with nothing
     heavy beside it, and the log says `a worker died ... screening <TLID>`.
     The same lot dying twice ends the run with an error naming it, and
     the same command with `--cache` resumes. A tree older than that
     hangs forever and keeps the lock: the parts count stops climbing
     while the workers sit at 0% CPU (rank-colour bound3, 2026-10-06,
     2 h 20 min). When you watch an old tree, compare the parts count
     against the clock and read `oom_kill` in
     `/sys/fs/cgroup/memory.events`.
   - Never change `/root/code/vicinitideals`. It is the weekly run's
     checkout.
   - Never change shared `data/` files in place; write new ones beside
     them.
   - Kill only PIDs you started. Never `pkill -f` a pattern: it matches
     your own ssh command.
   - Institutional land (schools, parks, hospitals, utilities, rail...) is
     left out of EVERY bridge run, a test scan included (Steph 2026-10-06,
     FOLLOWUPS 47), and a run that cannot read it is refused. The bridge
     reads it from `--sources` when that snapshot holds `osm_land_use` and
     `rlis_orca`; until the weekly run's snapshot does, pass
     `--institutional /root/institutional_sources/2026-10-06`. A bound
     whose base arm predates this sees those lots as missing rows -- assign
     answers them RED.
   - Washington TLID lists: drop right-of-way polygons first
     (`grep -v ' ROW$'`). They are roads, not lots, and one chunk of them
     ran over an hour at 7 GB.
6. **The weekly full re-screen belongs to no lane.** No lane starts a full
   re-screen, a partial re-screen, or a promotion. The 2026-10-07 run was
   moved EARLY (Steph 2026-10-06): it takes heavy.lock once rank-colour's
   bound and scan-throughput's proof are done, on origin/main at that
   moment (`/root/weekly_chain.sh`, log `/root/weekly_chain.log`, sources
   `data/flats/sources/2026-10-07`). A change merged after it starts rides
   the next weekly run.
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
12. **Iterate on a sample; bound the whole scope once.** While the code is
    still changing, bound a fixed sample of the scope. Pass
    `--tlid-file <scope> --sample 2000 --seed 1` to both the base and the
    new tree; the sample is cut after the scope, so the same lots come
    back every time. Read the moves, fix, and repeat. With `--cache`, the
    base tree's answers are kept between rounds, so each round costs only
    the new tree's run. Bound the whole scope once, when the code is
    final, right before merge, and read that bound's gains one by one
    (rule 11). The sample is for finding bugs fast. Only the full bound is
    the proof.
