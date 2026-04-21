"""Verify Phase 2 engine refactor produces byte-identical output on the
five baseline scenarios snapshot in ``tests/phase2_baseline/``.

Workflow (run ON the vicinitideals-api container after deploying the
phase-2 branch and running ``alembic upgrade head``):

    1. Re-run compute for each baseline scenario
    2. Re-snapshot to a fresh directory
    3. Diff each snapshot file against ``tests/phase2_baseline/<id>.json``
    4. Any non-empty diff = math regression — fail loudly

Everything outside the ``cash_flows`` / ``cash_flow_line_items`` /
``operational_outputs`` / ``waterfall_results`` / ``capital_modules``
shape is considered irrelevant (metadata fields, timestamps). The
snapshot format encodes what matters.

Usage::

    docker exec -w /app -e PYTHONPATH=/app vicinitideals-api \\
        python scripts/phase2_verify_byte_identical.py

Exits non-zero on any difference. Prints per-scenario summary.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import sys
from pathlib import Path
from uuid import UUID

from app.db import AsyncSessionLocal
from app.engines.cashflow import compute_cash_flows
from app.engines.waterfall import compute_waterfall

# Import the snapshot writer so we re-produce identical files to diff.
from scripts.phase2_baseline_snapshot import snapshot  # type: ignore

BASELINE_DIR = Path("tests/phase2_baseline")
OUT_DIR = Path("/tmp/phase2_postchange")

SCENARIO_IDS = [
    "5d1642c6-276f-4640-9694-dd85259dfcf9",
    "6d7c02e9-cf0c-4a57-b890-a9bd70990ea8",
    "1bf1e221-01cf-49d7-bd88-059c01b49967",
    "a3c48a70-da87-4e13-8c77-0fb8a1831aaf",
    "5e2a7e4c-dc2b-4db4-922d-5fa1c7026ee3",
]


async def _recompute_and_snapshot(sid_raw: str) -> None:
    sid = UUID(sid_raw)
    async with AsyncSessionLocal() as session:
        try:
            await compute_cash_flows(deal_model_id=sid, session=session)
            try:
                await compute_waterfall(deal_model_id=sid, session=session)
            except Exception as e:
                # Some baselines didn't have waterfall; ignore.
                print(f"  [waterfall skip] {sid_raw}: {type(e).__name__}: {e}")
            await session.commit()
        except Exception as e:
            print(f"  [compute FAIL] {sid_raw}: {type(e).__name__}: {e}")
            raise
    await snapshot(sid, OUT_DIR)


def _diff(scenario_id: str) -> list[str]:
    base = json.loads((BASELINE_DIR / f"{scenario_id}.json").read_text())
    new = json.loads((OUT_DIR / f"{scenario_id}.json").read_text())
    # Serialize canonically so minor JSON formatting differences don't show up
    base_str = json.dumps(base, indent=2, sort_keys=True)
    new_str = json.dumps(new, indent=2, sort_keys=True)
    if base_str == new_str:
        return []
    diff = list(
        difflib.unified_diff(
            base_str.splitlines(),
            new_str.splitlines(),
            fromfile=f"baseline/{scenario_id}",
            tofile=f"post/{scenario_id}",
            lineterm="",
            n=3,
        )
    )
    return diff


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Re-running compute for {len(SCENARIO_IDS)} scenarios...")
    for sid in SCENARIO_IDS:
        await _recompute_and_snapshot(sid)

    print()
    print("Diffing against baseline...")
    failures = 0
    for sid in SCENARIO_IDS:
        diff = _diff(sid)
        if not diff:
            print(f"  [OK]   {sid}")
        else:
            failures += 1
            print(f"  [DIFF] {sid}  ({len(diff)} changed lines)")
            for line in diff[:40]:
                print(f"    {line}")
            if len(diff) > 40:
                print(f"    ... ({len(diff) - 40} more lines)")

    print()
    if failures:
        print(f"FAIL: {failures} of {len(SCENARIO_IDS)} scenarios differ.")
        return 1
    print("PASS: all scenarios byte-identical.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
