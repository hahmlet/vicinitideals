"""One answer for every lot in the county: the screen's where it measured, ``unknown`` with a reason where it did not.

The bridge (:mod:`flats.ingest.quadfit`) writes a row per lot x design for the
lots quadfit measured. The normalize stage (:mod:`flats.ingest.normalize`) lists
every lot in the snapshot. This stage joins the two into one run directory the
loader's ``export`` consumes, so the page can show all of the county and say,
for each lot it cannot colour, why:

* a lot the bridge screened keeps its rows, untouched;
* a lot with a **gate** from normalize (``JURISDICTION_NOT_ENCODED``,
  ``JURISDICTION_OFF``, ``OUTSIDE_UGB``, ``NO_ZONE``, ``ZONE_NOT_ENCODED``,
  ``ZONE_POCKET``, ``ZONE_UNENCODABLE``, ``ZONE_TO_READ``) gets one synthetic
  ``unknown`` row per design carrying that reason -- the same vocabulary the
  resolver uses when the screen itself finds a zone it cannot hold;
* a lot with no gate in a zone whose rules FORBID the building
  (``quadplex_allowed: false``, settled -- no condition turns it true) gets
  the screen's own use-gate answer without a measurement: ``if_signed`` RED
  with ``USE_PROHIBITED`` (yellow where the zone lists a conditional-use path),
  and as screened whatever the resolution's trust allows -- ``unknown`` /
  ``RULE_UNVERIFIED`` until the zone's use line is signed, exactly as a
  measured lot in that zone reads. The screen returns RED at the use gate
  before it reads a setback (:func:`flats.score.screen.screen`), so a
  measurement would have changed nothing; and quadfit's filter drops these
  lots before measuring them for the same reason;
* a lot with no gate that quadfit still did not measure gets ``NOT_MEASURED``
  plus the step of quadfit's structural filter that dropped it
  (``s3_dropped.csv``: ``sliver_area``, ``too_narrow_20ft``,
  ``zone_not_in_rules``, ...), or ``unknown`` when no step claims it.

A synthetic ``unknown`` row is ``unknown`` both as screened and ``if_signed``:
signing the rules changes nothing for a lot nobody measured. It carries no
fit, no stalls, no checks -- the loader stores exactly that, and the page
reads the reason from ``checks.reasons`` the way it reads the screen's.

Nothing here measures. The screen's rows pass through byte for byte; the
synthetic rows say "not answered, because" -- or, for a forbidden use, the
one answer the code gives without a tape measure. If the two universes
disagree -- a lot the bridge measured that the snapshot's lot table lacks --
normalize's ``excluded.csv.gz`` is asked first: a lot it names (a
condominium unit record, a right-of-way pseudo-lot, a stacked duplicate) is
not land whoever measured it, so its rows are dropped and counted by reason
in ``meta.json``; a lot it does not name is a real disagreement, reported by
count and kept (the loader takes its lot record from quadfit's stage file,
as it always has). The September copy's first assign found 2,001 of the
first kind and none of the second: quadfit's s1 keeps condominium units the
roll's property code names because its own condo test looks for stacked
geometry.

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
import gzip
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from flats.ingest.normalize import GATES, EXCLUDED_COLUMNS

#: The reason on a lot that passed every gate and still has no measurement.
NOT_MEASURED = "NOT_MEASURED"
#: The screen's own word for a zone that forbids the building (``flats.score.screen``).
USE_PROHIBITED = "USE_PROHIBITED"
REASONS = (*GATES, NOT_MEASURED, USE_PROHIBITED)

#: ``(triage as screened, its reasons, if_signed, its reasons)`` for a lot in
#: a zone that forbids the building; what :func:`use_gate` answers.
UseGate = tuple[str, str, str, str]

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


def use_gate_for(rules: Any, relief: Any) -> Callable[[str, str], UseGate | None]:
    """The screen's use gate as a function of ``(layer_id, zone)``, memoised.

    Mirrors the two lines of :func:`flats.score.screen.screen` that decide it:
    ``quadplex_allowed`` resolved ``False`` with no lever that could turn it
    true is a settled prohibition; RED unless the relief policy lists a
    conditional-use path for the use there, in which case yellow. As screened,
    the answer is the signed one only when the resolution is trusted; until
    the use line is signed it is ``unknown`` with the resolution's own reason,
    which is what every measured lot in the zone reads too.
    """
    from flats.rules.resolver import Verdict as RuleVerdict

    memo: dict[tuple[str, str], UseGate | None] = {}

    def gate(layer_id: str, zone: str) -> UseGate | None:
        key = (layer_id, zone)
        if key in memo:
            return memo[key]
        answer: UseGate | None = None
        try:
            got = rules.resolve(layer_id, zone)
        except Exception:
            got = None
        if got is not None:
            use = got.values.get("quadplex_allowed")
            if use is not None and use.value is False and not use.levers:
                signed = "yellow" if relief.for_use(layer_id).available else "red"
                if got.verdict is RuleVerdict.trusted:
                    answer = (signed, USE_PROHIBITED, signed, USE_PROHIBITED)
                else:
                    answer = ("unknown", got.reason or "RULE_UNVERIFIED", signed, USE_PROHIBITED)
        memo[key] = answer
        return answer

    return gate


def load_use_gate() -> Callable[[str, str], UseGate | None]:
    """The use gate over the corpus as the bridge loads it (trust applied)."""
    from flats.encode.load import load_trusted
    from flats.score import relief as relief_mod

    return use_gate_for(load_trusted(strict=False).rules, relief_mod.load_policy())


def prohibited_row(lot: dict[str, Any], design: str, answer: UseGate) -> dict[str, Any]:
    """The row for one lot x design in a zone that forbids the building."""
    triage, reason, signed, signed_reason = answer
    row = synthetic_row(lot, design, reason)
    row.update({"triage": triage, "if_signed": signed, "if_signed_reasons": signed_reason})
    return row


def read_dropped(path: Path | None) -> dict[str, str]:
    """quadfit's ``s3_dropped.csv`` as TLID -> step; empty when there is none."""
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {str(r["TLID"]).rstrip(): str(r["step"]) for r in csv.DictReader(fh)}


def read_excluded(path: Path | None) -> dict[str, tuple[str, str]]:
    """normalize's ``excluded.csv.gz`` as TLID -> (step, reason); empty when there is none."""
    if path is None or not path.is_file():
        return {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = set(EXCLUDED_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise SystemExit(f"{path} lacks {sorted(missing)}")
        return {str(r["tlid"]).rstrip(): (str(r["step"]), str(r["reason"])) for r in reader}


def assign(
    normalized: Path,
    bridge: Path,
    out: Path,
    *,
    quadfit_dir: Path | None = None,
    snapshot_date: str | None = None,
    log: Callable[[str], None] | None = None,
    use_gate: Callable[[str, str], UseGate | None] | None = None,
) -> dict[str, Any]:
    """Join the bridge run to the normalized lot table; returns ``meta.json``'s content.

    ``use_gate`` answers for an unmeasured lot in a held zone whether that
    zone forbids the building (:func:`use_gate_for`); the command line passes
    :func:`load_use_gate`, the corpus as the bridge reads it. Without one, no
    lot is answered at the use gate -- the stage stays a pure join.
    """
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
    prohibited_zones: Counter[str] = Counter()
    for row in lot_rows:
        tlid = str(row["tlid"]).rstrip()
        if tlid in measured:
            continue
        reason = row.get("gate") or NOT_MEASURED
        if use_gate is not None and reason == NOT_MEASURED and row.get("jurisdiction") and row.get("zone"):
            answer = use_gate(str(row["jurisdiction"]), str(row["zone"]))
            if answer is not None:
                by_reason[USE_PROHIBITED] += 1
                prohibited_zones[f"{row['jurisdiction']}/{row['zone']}"] += 1
                for design in designs:
                    synthetic.append(prohibited_row(row, design, answer))
                continue
        step = dropped.get(tlid, "unknown") if reason == NOT_MEASURED else None
        by_reason[reason] += 1
        if step is not None:
            by_step[step] += 1
        for design in designs:
            synthetic.append(synthetic_row(row, design, reason, step))
    normalized_tlids = set(by_tlid)
    excluded = read_excluded(normalized / "excluded.csv.gz")
    not_land = {t for t in measured - normalized_tlids if t in excluded}
    measured_but_excluded: Counter[str] = Counter(excluded[t][1] or excluded[t][0] for t in not_land)
    measured -= not_land
    if not_land:
        frame = frame[~frame["TLID"].map(lambda t: str(t).rstrip() in not_land)].reset_index(drop=True)
    measured_not_in_lots = sorted(measured - normalized_tlids)
    say(
        f"synthetic: {len(synthetic):,} rows for {sum(by_reason.values()):,} unmeasured lots; "
        f"{len(not_land):,} measured lots the lot table excluded as not land, dropped; "
        f"{len(measured_not_in_lots):,} measured lots not in the lot table, kept"
    )

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
        "ruled_zones": summary.get("ruled_zones", {}),
        "funnel": summary.get("funnel", []),
        "lots": len(normalized_tlids | measured),
        "rows": int(len(both)),
        "assign": {
            "measured": len(measured),
            "unmeasured": sum(by_reason.values()),
            "by_reason": dict(sorted(by_reason.items())),
            "not_measured_by_step": dict(sorted(by_step.items())),
            "prohibited_by_zone": dict(sorted(prohibited_zones.items())),
            "measured_not_in_lots": len(measured_not_in_lots),
            "measured_not_in_lots_examples": measured_not_in_lots[:20],
            "measured_but_excluded": dict(sorted(measured_but_excluded.items())),
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
    if a.get("prohibited_by_zone"):
        out.append(
            "  - USE_PROHIBITED, by zone (red at the use gate, no measurement needed): "
            + ", ".join(f"{k} {v:,}" for k, v in a["prohibited_by_zone"].items())
        )
    if a.get("measured_but_excluded"):
        out.append(
            f"- measured by quadfit but not land by the snapshot's reading (dropped): {sum(a['measured_but_excluded'].values()):,} -- "
            + ", ".join(f"{k} {v:,}" for k, v in a["measured_but_excluded"].items())
        )
    if a["measured_not_in_lots"]:
        out.append(f"- measured but not in the snapshot's lot table (kept from quadfit's record): {a['measured_not_in_lots']:,}")
    if meta.get("new_zones"):
        out.append("")
        out.append("Zone codes nobody has ruled on -- new since the map was last read:")
        for layer_id, codes in meta["new_zones"].items():
            out.append(f"- {layer_id}: " + ", ".join(f"{c} ({n:,})" for c, n in codes.items()))
    if meta.get("ruled_zones"):
        out.append("")
        out.append("Zone codes ruled:")
        for layer_id, by_outcome in meta["ruled_zones"].items():
            for outcome, codes in by_outcome.items():
                out.append(f"- {layer_id} {outcome}: " + ", ".join(f"{c} ({n:,})" for c, n in codes.items()))
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
        use_gate=load_use_gate(),
    )
    print()
    for line in describe(meta):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
