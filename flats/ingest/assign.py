"""One answer for every lot in the county: the screen's where it measured, ``unknown`` with a reason where it did not.

The bridge (:mod:`flats.ingest.quadfit`) writes a row per lot x design for the
lots quadfit measured. The normalize stage (:mod:`flats.ingest.normalize`) lists
every lot in the snapshot. This stage joins the two into one run directory the
loader's ``export`` consumes, so the page can show all of the county and say,
for each lot it cannot colour, why:

* a lot the bridge screened keeps its rows, untouched;
* a lot with a **gate** from normalize (``JURISDICTION_NOT_ENCODED``,
  ``JURISDICTION_OFF``, ``OUTSIDE_UGB``, ``NO_ZONE``, ``ZONE_NOT_ENCODED``) gets
  one synthetic ``unknown`` row per design carrying that reason -- the same
  vocabulary the resolver uses when the screen itself finds a zone it cannot
  hold;
* a lot with no gate that quadfit still did not measure gets ``NOT_MEASURED``
  plus the step of quadfit's structural filter that dropped it
  (``s3_dropped.csv``: ``sliver_area``, ``too_narrow_20ft``,
  ``zone_quadplex_not_allowed``, ...), or ``unknown`` when no step claims it.

A synthetic row is ``unknown`` both as screened and ``if_signed``: signing the
rules changes nothing for a lot nobody measured. It carries no fit, no
stalls, no checks -- the loader stores exactly that, and the page reads the
reason from ``checks.reasons`` the way it reads the screen's.

Nothing here decides a verdict. The screen's rows pass through byte for byte;
the synthetic rows say only "not answered, because". If the two universes
disagree -- a lot the bridge measured that the snapshot's lot table lacks --
the count is reported in ``meta.json`` and the bridge's row is kept (the
loader takes its lot record from quadfit's stage file, as it always has).

Outputs under ``--out``: ``lots.parquet`` (the bridge's columns), ``meta.json``
(the bridge's, plus ``snapshot_date``, ``normalized``, ``new_zones``, the
funnel and the counts by reason), ``summary.md``.

Runs on the analysis host::

    python -m flats.ingest.assign --normalized data/flats/normalized/2026-09-18 \\
        --bridge /root/bridge_sep --quadfit-dir data/quadfit_2026-09-18 --out /root/assign_sep
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from flats.ingest.normalize import GATES

#: The reason on a lot that passed every gate and still has no measurement.
NOT_MEASURED = "NOT_MEASURED"
REASONS = (*GATES, NOT_MEASURED)

#: Columns a bridge row carries (``flats.ingest.quadfit.row_for``); a synthetic
#: row fills the same ones so the frame stays rectangular.
ROW_COLUMNS = (
    "TLID",
    "jurisdiction",
    "zone",
    "layer_id",
    "tier",
    "design",
    "rule_verdict",
    "triage",
    "if_signed",
    "reasons",
    "if_signed_reasons",
    "head",
    "dominant",
    "failing",
    "unchecked",
    "ask",
    "fits",
    "fit_slack_ft",
    "stalls_charged",
    "stalls_seated",
    "parking_band",
    "fit_best_depth_ft",
    "fit_required_ft",
    "fit_across_ft",
    "fit_angle_deg",
    "fit_orientation",
    "lot_sqft",
    "frontage_ft",
    "lot_width_ft",
    "lot_depth_ft",
    "observed",
    "assumed_leaning",
    "unknown_leaning",
    "angles",
    "step_deg",
)


def synthetic_row(lot: dict[str, Any], design: str, reason: str, step: str | None = None) -> dict[str, Any]:
    """The ``unknown`` row for one unmeasured lot x design."""
    reasons = reason if step is None else f"{reason},quadfit:{step}"
    return {
        **{c: None for c in ROW_COLUMNS},
        "TLID": lot["tlid"],
        "jurisdiction": lot.get("jurisdiction"),
        "zone": lot.get("zone"),
        "layer_id": lot.get("jurisdiction"),
        "design": design,
        "triage": "unknown",
        "if_signed": "unknown",
        "reasons": reasons,
        "if_signed_reasons": reasons,
        "head": "",
        "failing": "",
        "unchecked": "",
        "fits": False,
        "lot_sqft": lot.get("area_sqft"),
        "observed": "{}",
        "assumed_leaning": "",
        "unknown_leaning": "",
    }


def read_dropped(path: Path | None) -> dict[str, str]:
    """quadfit's ``s3_dropped.csv`` as TLID -> step; empty when there is none."""
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {str(r["TLID"]).rstrip(): str(r["step"]) for r in csv.DictReader(fh)}


def assign(
    normalized: Path,
    bridge: Path,
    out: Path,
    *,
    quadfit_dir: Path | None = None,
    snapshot_date: str | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Join the bridge run to the normalized lot table; returns ``meta.json``'s content."""
    import pandas as pd

    say = log or (lambda _m: None)
    started = time.monotonic()
    meta = json.loads((bridge / "meta.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(bridge / "lots.parquet")
    for c in ROW_COLUMNS:
        if c not in frame.columns:
            frame[c] = None
    frame = frame[list(ROW_COLUMNS)]
    designs = sorted(set(frame["design"]))
    measured = {str(t).rstrip() for t in frame["TLID"]}
    say(f"bridge: {len(frame):,} rows, {len(measured):,} lots, designs {designs}")

    columns = ["county", "tlid", "jurisdiction", "zone", "zone_raw", "area_sqft", "gate"]
    lots = pd.read_parquet(normalized / "lots.parquet", columns=columns)
    lots = lots.astype(object).where(lots.notna(), None)
    lot_rows = lots.to_dict("records")
    by_tlid: dict[str, list[dict[str, Any]]] = {}
    for row in lot_rows:
        by_tlid.setdefault(str(row["tlid"]).rstrip(), []).append(row)
    collisions = sorted(t for t, rows in by_tlid.items() if len(rows) > 1)
    if any(t in measured for t in collisions):
        raise SystemExit(f"a TLID the bridge measured names lots in two counties: {[t for t in collisions if t in measured][:5]}")
    say(f"normalized: {len(lot_rows):,} lots ({len(collisions)} TLIDs shared across counties)")

    dropped = read_dropped(quadfit_dir / "s3_dropped.csv" if quadfit_dir else None)
    summary = json.loads((normalized / "summary.json").read_text(encoding="utf-8")) if (normalized / "summary.json").is_file() else {}

    synthetic: list[dict[str, Any]] = []
    by_reason: Counter[str] = Counter()
    by_step: Counter[str] = Counter()
    for row in lot_rows:
        tlid = str(row["tlid"]).rstrip()
        if tlid in measured:
            continue
        reason = row.get("gate") or NOT_MEASURED
        step = dropped.get(tlid, "unknown") if reason == NOT_MEASURED else None
        by_reason[reason] += 1
        if step is not None:
            by_step[step] += 1
        for design in designs:
            synthetic.append(synthetic_row(row, design, reason, step))
    normalized_tlids = set(by_tlid)
    measured_not_in_lots = sorted(measured - normalized_tlids)
    say(f"synthetic: {len(synthetic):,} rows for {sum(by_reason.values()):,} unmeasured lots; {len(measured_not_in_lots):,} measured lots not in the lot table")

    out.mkdir(parents=True, exist_ok=True)
    extra = pd.DataFrame(synthetic, columns=list(ROW_COLUMNS))
    both = pd.concat([frame, extra], ignore_index=True) if len(extra) else frame
    both.to_parquet(out / "lots.parquet", index=False)

    result = {
        **meta,
        "caller": "flats.ingest.assign",
        "bridge_dir": str(bridge.resolve()),
        "snapshot_date": snapshot_date or summary.get("snapshot"),
        "normalized": str(normalized.resolve()),
        "quadfit_dir": str(quadfit_dir.resolve()) if quadfit_dir else None,
        "new_zones": summary.get("new_zones", {}),
        "funnel": summary.get("funnel", []),
        "lots": len(normalized_tlids | measured),
        "rows": int(len(both)),
        "assign": {
            "measured": len(measured),
            "unmeasured": sum(by_reason.values()),
            "by_reason": dict(sorted(by_reason.items())),
            "not_measured_by_step": dict(sorted(by_step.items())),
            "measured_not_in_lots": len(measured_not_in_lots),
            "measured_not_in_lots_examples": measured_not_in_lots[:20],
            "tlids_shared_across_counties": len(collisions),
            "designs": designs,
            "seconds": round(time.monotonic() - started, 1),
        },
    }
    (out / "meta.json").write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (out / "summary.md").write_text("\n".join(describe(result)) + "\n", encoding="utf-8")
    say(f"wrote {len(both):,} rows for {result['lots']:,} lots to {out}")
    return result


def describe(meta: dict[str, Any]) -> list[str]:
    a = meta["assign"]
    out = [f"# Every lot answered ({meta.get('snapshot_date') or 'undated'}): {meta['lots']:,} lots, {meta['rows']:,} rows", ""]
    out.append(f"- measured and screened: {a['measured']:,}")
    out.append(f"- not screened: {a['unmeasured']:,}")
    for reason, n in a["by_reason"].items():
        out.append(f"  - {reason}: {n:,}")
    if a["not_measured_by_step"]:
        out.append("  - NOT_MEASURED, by quadfit's step: " + ", ".join(f"{k} {v:,}" for k, v in a["not_measured_by_step"].items()))
    if a["measured_not_in_lots"]:
        out.append(f"- measured but not in the snapshot's lot table (kept from quadfit's record): {a['measured_not_in_lots']:,}")
    if meta.get("new_zones"):
        out.append("")
        out.append("Zone codes the rules do not hold:")
        for layer_id, codes in meta["new_zones"].items():
            out.append(f"- {layer_id}: " + ", ".join(f"{c} ({n:,})" for c, n in codes.items()))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--normalized", type=Path, required=True, help="the normalize stage's output directory")
    ap.add_argument("--bridge", type=Path, required=True, help="the bridge run directory (lots.parquet + meta.json)")
    ap.add_argument("--out", type=Path, required=True, help="run directory to write for the loader's export")
    ap.add_argument("--quadfit-dir", type=Path, default=None, help="quadfit data tree, for s3_dropped.csv")
    ap.add_argument("--snapshot-date", default=None, help="YYYY-MM-DD (default: the normalized summary's)")
    args = ap.parse_args(argv)
    meta = assign(
        args.normalized,
        args.bridge,
        args.out,
        quadfit_dir=args.quadfit_dir,
        snapshot_date=args.snapshot_date,
        log=lambda m: print(m, flush=True),
    )
    print()
    for line in describe(meta):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
