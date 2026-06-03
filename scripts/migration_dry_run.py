"""Pre-deploy dry-run tool for the reserves-spec-align migrations.

The reserves-spec-align migrations (0109 bucket remap + 0110 Stabilization
backfill) plus the engine changes that shipped alongside them will change
every existing scenario's headline numbers on the next compute:

  * Total Project Cost (TPC)         expected up   (LUR-blind IR + ODR)
  * Interest Reserve (IR)            expected up   (no LUR offset)
  * Operating Deficit Reserve (ODR)  new line item (replaces CFSR)
  * Operating Reserve (OR)           ~unchanged for ds basis
  * Exit balloon                     expected down (LUR sweep)
  * Equity IRR                       small move

Per spec critique #5, the deploy is NOT a blanket silent recompute. This
script lets the operator review the change deal-by-deal against a clone
of prod data:

  1. Snapshot current state of every Scenario into a JSON file.
  2. Apply the migrations against the clone (manually, via
     ``alembic upgrade head``).
  3. Recompute every Scenario via the existing /api/scenarios/<id>/compute
     endpoint (loop in a separate script, or a one-shot SQL trigger).
  4. Snapshot the post-recompute state into a second JSON file.
  5. Run this script in ``diff`` mode to produce a CSV of every scenario
     whose headline numbers moved beyond the configured threshold.

The CSV columns are designed for spreadsheet triage: sort by tpc_delta
or irr_levered_delta descending, eyeball anything that moved more than
expected, dig into individual scenarios before flipping the migration
on prod.

USAGE
-----

Snapshot -- run against the clone before and after recompute:

  python scripts/migration_dry_run.py snapshot \\
      --db-url postgresql+asyncpg://user:pw@host/db \\
      --output /tmp/before.json

Diff -- produce the per-scenario CSV:

  python scripts/migration_dry_run.py diff \\
      --before /tmp/before.json \\
      --after  /tmp/after.json  \\
      --output /tmp/dry_run_report.csv \\
      --threshold-money 1000 \\
      --threshold-irr   0.001

A scenario lands in the CSV if ANY of these conditions hold:
  * abs(delta total_project_cost)    >= threshold_money
  * abs(delta equity_required)       >= threshold_money
  * abs(delta sum-reserves-by-label) >= threshold_money
  * abs(delta project_irr_levered)   >= threshold_irr  (decimal, 0.001 = 0.1pct)
  * abs(delta project_irr_unlevered) >= threshold_irr

The script is intentionally read-only against the DB. It never writes
ORM changes -- the snapshot is a plain SELECT, the diff is pure Python.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.cashflow import OperationalOutputs
from app.models.deal import Scenario, UseLine


# Labels we track per scenario. Order matters -- diffs emit columns in
# this order so the CSV is human-readable left-to-right.
RESERVE_LABELS = (
    "Interest Reserve",
    "Operating Deficit Reserve",
    "Operating Reserve",
    "Cash Flow Support Reserve",      # legacy -- expect to disappear post-migration
    "Construction DS Reserve",        # legacy -- expect to disappear post-migration
    "Lease-Up Reserve",               # legacy -- expect to disappear post-migration
)


def _dec_to_str(v: Any) -> str | None:
    """Serialize a Decimal-ish value to a stable string. ``None`` survives."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    try:
        return str(Decimal(str(v)))
    except (ValueError, TypeError):
        return str(v)


def _str_to_dec(v: str | None) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    try:
        return Decimal(v)
    except Exception:
        return Decimal("0")


async def _snapshot(db_url: str, output: Path) -> None:
    """Read every Scenario's headline numbers + reserve sums into a JSON
    file. Read-only -- no ORM writes."""
    engine = create_async_engine(db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    snapshot: dict[str, dict[str, Any]] = {}

    async with Session() as session:
        scenarios = list((await session.execute(select(Scenario))).scalars())
        print(f"snapshot: {len(scenarios)} scenarios", file=sys.stderr)

        for scenario in scenarios:
            sid = str(scenario.id)
            outputs = list((await session.execute(
                select(OperationalOutputs)
                .where(OperationalOutputs.scenario_id == scenario.id)
            )).scalars())

            # A scenario may have multiple Projects (and therefore multiple
            # OperationalOutputs rows). Sum the headline numbers so the
            # snapshot tracks the scenario-level rollup the user sees.
            tpc = sum(
                (_str_to_dec(_dec_to_str(o.total_project_cost)) for o in outputs),
                Decimal("0"),
            )
            equity = sum(
                (_str_to_dec(_dec_to_str(o.equity_required)) for o in outputs),
                Decimal("0"),
            )
            noi_stab = sum(
                (_str_to_dec(_dec_to_str(o.noi_stabilized)) for o in outputs),
                Decimal("0"),
            )

            # IRR is a percent on each row; take the deal-level levered IRR
            # from the first row that has one -- single-project deals are the
            # only case today. Multi-project IRR rollup is a separate
            # responsibility of the Underwriting layer.
            irr_lev: str | None = None
            irr_unlev: str | None = None
            dscr: str | None = None
            for o in outputs:
                if o.project_irr_levered is not None and irr_lev is None:
                    irr_lev = _dec_to_str(o.project_irr_levered)
                if o.project_irr_unlevered is not None and irr_unlev is None:
                    irr_unlev = _dec_to_str(o.project_irr_unlevered)
                if o.dscr is not None and dscr is None:
                    dscr = _dec_to_str(o.dscr)

            # Reserve-bucket totals from UseLine rows. Exact-label match --
            # the migrations remap bucket keys but the engine writes labels
            # verbatim, so a pre-migration "Cash Flow Support Reserve" row
            # will appear as a non-zero entry in the before snapshot and as
            # a zero (gone, replaced by "Operating Deficit Reserve") in the
            # after snapshot.
            ul_rows = list((await session.execute(
                select(UseLine).where(UseLine.scenario_id == scenario.id)
            )).scalars())
            reserves = {label: Decimal("0") for label in RESERVE_LABELS}
            for ul in ul_rows:
                if ul.label in reserves:
                    reserves[ul.label] += _str_to_dec(_dec_to_str(ul.amount))

            # Stabilization-anchor validator output (Slice 5d) -- surface
            # any scenario where the new validator now reports an error so
            # the operator can fix the anchor before the deploy.
            anchor_status: str | None = None
            for o in outputs:
                proof = o.bank_account_proof or {}
                anchor = proof.get("stabilization_anchor") if isinstance(proof, dict) else None
                if isinstance(anchor, dict):
                    anchor_status = anchor.get("status")
                    if anchor_status == "error":
                        break

            snapshot[sid] = {
                "name": getattr(scenario, "name", None),
                "total_project_cost": _dec_to_str(tpc),
                "equity_required": _dec_to_str(equity),
                "noi_stabilized": _dec_to_str(noi_stab),
                "project_irr_levered": irr_lev,
                "project_irr_unlevered": irr_unlev,
                "dscr": dscr,
                "reserves": {k: _dec_to_str(v) for k, v in reserves.items()},
                "stabilization_anchor_status": anchor_status,
            }

    await engine.dispose()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
    print(
        f"snapshot: wrote {len(snapshot)} scenarios -> {output}",
        file=sys.stderr,
    )


def _diff(
    before: Path,
    after: Path,
    output: Path,
    threshold_money: Decimal,
    threshold_irr: Decimal,
) -> None:
    """Produce a CSV of every scenario whose numbers moved beyond the
    threshold. Pure-Python; no DB access."""
    before_data = json.loads(before.read_text())
    after_data = json.loads(after.read_text())

    columns = [
        "scenario_id",
        "name",
        "tpc_before",
        "tpc_after",
        "tpc_delta",
        "equity_before",
        "equity_after",
        "equity_delta",
        "irr_levered_before",
        "irr_levered_after",
        "irr_levered_delta",
        "irr_unlevered_before",
        "irr_unlevered_after",
        "irr_unlevered_delta",
        "noi_stab_before",
        "noi_stab_after",
        "noi_stab_delta",
        "dscr_before",
        "dscr_after",
        "dscr_delta",
    ]
    for label in RESERVE_LABELS:
        # Replace spaces and hyphens so spreadsheet column names are clean.
        slug = label.lower().replace(" ", "_").replace("-", "_")
        columns.extend([
            f"{slug}_before",
            f"{slug}_after",
            f"{slug}_delta",
        ])
    columns.extend([
        "anchor_status_before",
        "anchor_status_after",
        "trigger_reason",
    ])

    output.parent.mkdir(parents=True, exist_ok=True)
    rows_emitted = 0
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()

        all_ids = set(before_data) | set(after_data)
        for sid in sorted(all_ids):
            b = before_data.get(sid, {})
            a = after_data.get(sid, {})

            tpc_b = _str_to_dec(b.get("total_project_cost"))
            tpc_a = _str_to_dec(a.get("total_project_cost"))
            equity_b = _str_to_dec(b.get("equity_required"))
            equity_a = _str_to_dec(a.get("equity_required"))
            noi_b = _str_to_dec(b.get("noi_stabilized"))
            noi_a = _str_to_dec(a.get("noi_stabilized"))
            irr_lev_b = _str_to_dec(b.get("project_irr_levered"))
            irr_lev_a = _str_to_dec(a.get("project_irr_levered"))
            irr_unlev_b = _str_to_dec(b.get("project_irr_unlevered"))
            irr_unlev_a = _str_to_dec(a.get("project_irr_unlevered"))
            dscr_b = _str_to_dec(b.get("dscr"))
            dscr_a = _str_to_dec(a.get("dscr"))

            reserves_b = b.get("reserves", {})
            reserves_a = a.get("reserves", {})

            triggers: list[str] = []
            if abs(tpc_a - tpc_b) >= threshold_money:
                triggers.append("tpc")
            if abs(equity_a - equity_b) >= threshold_money:
                triggers.append("equity")
            if abs(irr_lev_a - irr_lev_b) >= threshold_irr:
                triggers.append("irr_levered")
            if abs(irr_unlev_a - irr_unlev_b) >= threshold_irr:
                triggers.append("irr_unlevered")
            for label in RESERVE_LABELS:
                rb = _str_to_dec(reserves_b.get(label))
                ra = _str_to_dec(reserves_a.get(label))
                if abs(ra - rb) >= threshold_money:
                    slug = label.lower().replace(" ", "_").replace("-", "_")
                    triggers.append(f"reserve:{slug}")
            anchor_b = b.get("stabilization_anchor_status")
            anchor_a = a.get("stabilization_anchor_status")
            if anchor_a == "error" and anchor_b != "error":
                triggers.append("new_anchor_error")

            if not triggers:
                continue

            row: dict[str, Any] = {
                "scenario_id": sid,
                "name": a.get("name") or b.get("name") or "",
                "tpc_before": tpc_b,
                "tpc_after": tpc_a,
                "tpc_delta": tpc_a - tpc_b,
                "equity_before": equity_b,
                "equity_after": equity_a,
                "equity_delta": equity_a - equity_b,
                "irr_levered_before": irr_lev_b,
                "irr_levered_after": irr_lev_a,
                "irr_levered_delta": irr_lev_a - irr_lev_b,
                "irr_unlevered_before": irr_unlev_b,
                "irr_unlevered_after": irr_unlev_a,
                "irr_unlevered_delta": irr_unlev_a - irr_unlev_b,
                "noi_stab_before": noi_b,
                "noi_stab_after": noi_a,
                "noi_stab_delta": noi_a - noi_b,
                "dscr_before": dscr_b,
                "dscr_after": dscr_a,
                "dscr_delta": dscr_a - dscr_b,
                "anchor_status_before": anchor_b or "",
                "anchor_status_after": anchor_a or "",
                "trigger_reason": ",".join(triggers),
            }
            for label in RESERVE_LABELS:
                rb = _str_to_dec(reserves_b.get(label))
                ra = _str_to_dec(reserves_a.get(label))
                slug = label.lower().replace(" ", "_").replace("-", "_")
                row[f"{slug}_before"] = rb
                row[f"{slug}_after"] = ra
                row[f"{slug}_delta"] = ra - rb

            writer.writerow(row)
            rows_emitted += 1

    print(
        f"diff: {rows_emitted} scenarios moved beyond threshold "
        f"(money>={threshold_money}, irr>={threshold_irr}) -> {output}",
        file=sys.stderr,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="mode", required=True)

    snap = sub.add_parser("snapshot", help="Snapshot scenario state to JSON.")
    snap.add_argument("--db-url", default=settings.database_url,
                      help="async-sqlalchemy DB URL. Defaults to settings.database_url.")
    snap.add_argument("--output", required=True, type=Path,
                      help="JSON file to write the snapshot to.")

    diff = sub.add_parser("diff", help="Diff two snapshots into a CSV.")
    diff.add_argument("--before", required=True, type=Path)
    diff.add_argument("--after", required=True, type=Path)
    diff.add_argument("--output", required=True, type=Path)
    diff.add_argument("--threshold-money", type=Decimal, default=Decimal("1000"),
                      help="Dollar threshold for flagging a delta. Default 1000.")
    diff.add_argument("--threshold-irr", type=Decimal, default=Decimal("0.001"),
                      help="Decimal IRR threshold (0.001 = 0.1pct). Default 0.001.")

    args = p.parse_args()

    if args.mode == "snapshot":
        asyncio.run(_snapshot(args.db_url, args.output))
    elif args.mode == "diff":
        _diff(
            args.before,
            args.after,
            args.output,
            args.threshold_money,
            args.threshold_irr,
        )


if __name__ == "__main__":
    main()
