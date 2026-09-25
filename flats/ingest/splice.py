"""Partial re-screen: re-run only the lots a change can move, splice them into the last run.

A full re-screen of every lot takes about seven hours; most changes touch one
city or a few zones. So a change declares its **scope** -- jurisdictions,
``<jurisdiction>:<zone>`` pairs, or a list of TLIDs -- the bridge screens only
those lots (``python -m flats.ingest.quadfit --jurisdiction/--zone/--tlid``),
and :func:`splice` writes a whole bridge directory: every lot the partial run
screened takes its new rows, every other lot keeps the base run's. assign,
export, load, drift and promote then run unchanged on the result, and the
drift report reads only the moves inside the scope.

A declared scope is a claim, and a claim can be wrong: a Wood Village change
also moved a Troutdale lot. So partial runs never replace full ones (Steph,
2026-09-25). Each spliced directory records its lineage -- the last FULL
bridge it descends from and every splice since -- and :func:`due` says when a
full re-screen is owed. When one runs, :func:`audit` compares it with the
spliced run it replaces:

* a move on a lot some splice re-screened is **in scope** -- the full run and
  that splice disagree on a lot the splice claimed, which only a later change
  (or a bug) explains;
* a move on a lot no splice touched is **out of scope**: some change in the
  batch reached further than it declared. It is ACCEPTED as a known unknown,
  attributed to the batch of splices since the last full run as a whole --
  not rejected, and not blamed on one change nobody can name.

Nothing here screens or measures; the rows pass through as the bridge wrote
them.

Runs on the analysis host::

    python -m flats.ingest.quadfit --zone "Wood Village:TC" --out /root/bridge_wv ...
    python -m flats.ingest.splice splice --base /root/bridge_env_full \\
        --partial /root/bridge_wv --out /root/bridge_spliced_wv --change "WV TC front 10"
    python -m flats.ingest.splice audit --spliced /root/bridge_spliced_wv \\
        --full /root/bridge_full_next --out /root/audit_next
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: A full re-screen is owed after this many splices on one full run...
MAX_SPLICES = 5
#: ...or once the full run it descends from is this old.
MAX_AGE_DAYS = 30

#: The two answers a move is read on: as screened, and if the rules were signed.
VERDICTS = ("triage", "if_signed")


def _meta(bridge: Path) -> dict[str, Any]:
    return json.loads((bridge / "meta.json").read_text(encoding="utf-8"))


def _is_partial(meta: dict[str, Any]) -> bool:
    return bool(meta.get("jurisdictions") or meta.get("zones") or meta.get("tlids"))


def _full_of(bridge: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """The full run a bridge directory descends from: itself, or its lineage's root."""
    if "lineage" in meta:
        return meta["lineage"]["full"]
    return {"bridge": str(bridge.resolve()), "finished_at": meta.get("finished_at")}


def splice(base: Path, partial: Path, out: Path, *, change: str) -> dict[str, Any]:
    """Write ``out`` = ``base`` with every lot ``partial`` screened replaced; returns its meta.

    Refuses to mix runs that measured different lots (other s4/s5o files), a
    sampled or truncated run on either side, a base that is itself partial,
    or a partial run with no declared scope -- each would splice rows that do
    not describe the same county.
    """
    import pandas as pd

    bm, pm = _meta(base), _meta(partial)
    for m, name in ((bm, "base"), (pm, "partial")):
        if m.get("sample") is not None or m.get("limit") is not None:
            raise SystemExit(f"{name} run is a sample or truncated; a splice needs every lot in its scope")
    if _is_partial(bm):
        raise SystemExit("base run is itself partial; splice onto a full or spliced run")
    if not _is_partial(pm):
        raise SystemExit("partial run declares no scope (--jurisdiction/--zone/--tlid); that is a full run")
    for key in ("s4", "s5o"):
        if Path(bm[key]).resolve() != Path(pm[key]).resolve():
            raise SystemExit(f"{key} differs: base {bm[key]} vs partial {pm[key]}")

    old = pd.read_parquet(base / "lots.parquet")
    new = pd.read_parquet(partial / "lots.parquet")
    if set(new["design"]) - set(old["design"]):
        raise SystemExit(f"partial run screened designs the base lacks: {sorted(set(new['design']) - set(old['design']))}")
    touched = set(new["TLID"])
    kept = old[~old["TLID"].isin(touched)]
    both = pd.concat([kept, new.reindex(columns=old.columns.union(new.columns, sort=False))], ignore_index=True)
    both = both[list(old.columns) + [c for c in new.columns if c not in old.columns]]

    out.mkdir(parents=True, exist_ok=True)
    both.to_parquet(out / "lots.parquet", index=False)
    lineage = bm.get("lineage") or {"full": _full_of(base, bm), "splices": []}
    entry = {
        "change": change,
        "partial": str(partial.resolve()),
        "jurisdictions": pm.get("jurisdictions") or [],
        "zones": pm.get("zones") or [],
        "tlids": pm.get("tlids") or [],
        "lots": len(touched),
        "new_lots": len(touched - set(old["TLID"])),
        "finished_at": pm.get("finished_at"),
    }
    meta = {
        **bm,
        "lots": int(both["TLID"].nunique()),
        "rows": len(both),
        "seconds": pm.get("seconds"),
        "spliced_from": str(base.resolve()),
        "lineage": {"full": lineage["full"], "splices": [*lineage["splices"], entry]},
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def due(meta: dict[str, Any], *, now: datetime | None = None) -> list[str]:
    """Why a full re-screen is owed for this run, in plain English; empty when it is not."""
    lineage = meta.get("lineage")
    if not lineage:
        return []
    why = []
    n = len(lineage["splices"])
    if n >= MAX_SPLICES:
        why.append(f"{n} partial re-screens since the last full one (limit {MAX_SPLICES})")
    finished = lineage["full"].get("finished_at")
    if finished:
        age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(finished)).days
        if age >= MAX_AGE_DAYS:
            why.append(f"the last full re-screen finished {age} days ago (limit {MAX_AGE_DAYS})")
    return why


@dataclass(frozen=True, slots=True)
class Audit:
    """A full re-screen read against the spliced run it replaces."""

    rows: int
    #: Lots some splice re-screened, and every change named in the batch.
    touched: frozenset[str]
    changes: tuple[str, ...]
    #: ``(verdict, before, after)`` -> count, split by whether a splice touched the lot.
    in_scope: Counter[tuple[str, str, str]]
    out_of_scope: Counter[tuple[str, str, str]]
    #: One row per moved lot x design: TLID, jurisdiction, zone, design, verdict, before, after, in_scope.
    moves: list[dict[str, Any]]


def audit(spliced: Path, full: Path) -> Audit:
    """Every verdict that differs between ``spliced`` and a later ``full`` re-screen."""
    import pandas as pd

    sm, fm = _meta(spliced), _meta(full)
    if _is_partial(fm) or "lineage" in fm or fm.get("sample") is not None or fm.get("limit") is not None:
        raise SystemExit(f"{full} is not a full re-screen")
    splices = (sm.get("lineage") or {}).get("splices", [])
    touched: set[str] = set()
    for s in splices:
        touched |= set(pd.read_parquet(Path(s["partial"]) / "lots.parquet", columns=["TLID"])["TLID"])

    cols = ["TLID", "jurisdiction", "zone", "design", *VERDICTS]
    a = pd.read_parquet(spliced / "lots.parquet", columns=cols)
    b = pd.read_parquet(full / "lots.parquet", columns=cols)
    m = a.merge(b, on=["TLID", "design"], how="outer", suffixes=("_was", "_now"), indicator=True)
    in_scope: Counter[tuple[str, str, str]] = Counter()
    out_of_scope: Counter[tuple[str, str, str]] = Counter()
    moves: list[dict[str, Any]] = []
    for r in m.to_dict("records"):
        for v in VERDICTS:
            was = r[f"{v}_was"] if r["_merge"] != "right_only" else "absent"
            now = r[f"{v}_now"] if r["_merge"] != "left_only" else "absent"
            if was == now:
                continue
            hit = r["TLID"] in touched
            (in_scope if hit else out_of_scope)[(v, str(was), str(now))] += 1
            moves.append(
                {
                    "TLID": r["TLID"],
                    "jurisdiction": r["jurisdiction_now"] if r["_merge"] != "left_only" else r["jurisdiction_was"],
                    "zone": r["zone_now"] if r["_merge"] != "left_only" else r["zone_was"],
                    "design": r["design"],
                    "verdict": v,
                    "before": str(was),
                    "after": str(now),
                    "in_scope": hit,
                }
            )
    return Audit(
        rows=len(m),
        touched=frozenset(touched),
        changes=tuple(s["change"] for s in splices),
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        moves=moves,
    )


def report(result: Audit) -> str:
    """The audit in plain English, for the promotion record."""
    lines = [
        "# Full re-screen vs the spliced run it replaces",
        "",
        f"{result.rows:,} lot x design rows; {len(result.touched):,} lots re-screened by "
        f"{len(result.changes)} partial run(s) since the last full one:",
        "",
        *[f"- {c}" for c in result.changes],
        "",
        "## Moves on lots a partial run re-screened (in scope)",
        "",
        "The full run and the partial run disagree on a lot the partial claimed. "
        "Only a later change or a bug explains one; read each.",
        "",
        *_table(result.in_scope),
        "## Moves on lots no partial run touched (out of scope)",
        "",
        "Some change in the batch reached further than it declared. Accepted as "
        "known unknowns, attributed to the batch above as a whole (Steph, 2026-09-25).",
        "",
        *_table(result.out_of_scope),
    ]
    out = [m for m in result.moves if not m["in_scope"] and m["verdict"] == "if_signed"]
    if out:
        by = Counter((m["jurisdiction"], m["zone"]) for m in out)
        lines += ["Out-of-scope if-signed moves by jurisdiction and zone:", ""]
        lines += [f"- {j} {z}: {n}" for (j, z), n in by.most_common(30)]
        lines.append("")
    return "\n".join(lines)


def _table(counts: Counter[tuple[str, str, str]]) -> list[str]:
    if not counts:
        return ["None.", ""]
    rows = ["| answer | before | after | rows |", "|---|---|---|---|"]
    rows += [f"| {v} | {a} | {b} | {n:,} |" for (v, a, b), n in sorted(counts.items(), key=lambda kv: -kv[1])]
    return [*rows, ""]


def main(argv: list[str] | None = None) -> int:
    import argparse

    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("splice", help="base run + partial run -> a whole bridge directory")
    sp.add_argument("--base", type=Path, required=True)
    sp.add_argument("--partial", type=Path, required=True)
    sp.add_argument("--out", type=Path, required=True)
    sp.add_argument("--change", required=True, help="what changed, in a line (the commit and its scope)")
    au = sub.add_parser("audit", help="a full re-screen vs the spliced run it replaces")
    au.add_argument("--spliced", type=Path, required=True)
    au.add_argument("--full", type=Path, required=True)
    au.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    if args.cmd == "splice":
        meta = splice(args.base, args.partial, args.out, change=args.change)
        last = meta["lineage"]["splices"][-1]
        print(f"spliced {last['lots']:,} lots ({last['new_lots']:,} new) into {meta['lots']:,}; "
              f"{len(meta['lineage']['splices'])} partial run(s) since the full run "
              f"{meta['lineage']['full']['bridge']}")
        for why in due(meta):
            print(f"FULL RE-SCREEN DUE: {why}")
        return 0

    result = audit(args.spliced, args.full)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audit.md").write_text(report(result), encoding="utf-8")
    pd.DataFrame(result.moves).to_csv(args.out / "moves.csv", index=False)
    print(f"in scope {sum(result.in_scope.values()):,}, out of scope {sum(result.out_of_scope.values()):,} "
          f"-> {args.out / 'audit.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
