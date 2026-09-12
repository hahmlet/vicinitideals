# Branch and worktree convention

The primary checkout (`c:\Users\Steph\Repos\vicinitideals`) stays on `main`.
Branched work lives in worktrees at
`c:\Users\Steph\Repos\vicinitideals-worktrees\<slug>\` so parallel agent
sessions don't collide on shared working-tree state.

## When to use a worktree

- **Bug fixes, small tweaks, doc edits, config changes** → work on `main` in the
  primary checkout. No worktree.
- **New features, refactors, risky changes** → **confirm with the user first**
  before creating a worktree. Don't start branched work in the primary checkout.

## Per-worktree setup

From the primary checkout:

```bash
git worktree add ../vicinitideals-worktrees/<slug> -b feature/<slug> main
cp .env ../vicinitideals-worktrees/<slug>/.env
( cd ../vicinitideals-worktrees/<slug> && uv sync )
```

`.gitignore` excludes `.env`, `.venv/`, `.claude/` — each worktree gets its own.
The shared `.git` object DB makes worktrees cheap.

## Granularity

One branch = one shippable slice = one worktree. If a worktree's scope grows
beyond one mergeable change, split it into multiple branches/worktrees. Merge
each slice when independently deployable; gate user-visible behaviour with
feature flags rather than delaying merges.

## Cleanup

Remove a finished worktree:

```bash
git worktree remove <path> && git branch -d <branch>
```

Find stale worktrees (run from the primary checkout, safe weekly):

```bash
git worktree list --porcelain | grep '^worktree' | awk '{print $2}' | while read wt; do
  branch=$(git -C "$wt" branch --show-current)
  if [ -n "$branch" ] && [ "$branch" != "main" ] && git merge-base --is-ancestor "$branch" main 2>/dev/null; then
    echo "stale (merged): $wt on $branch"
  fi
done
```
