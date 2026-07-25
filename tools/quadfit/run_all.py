"""Stage runner: executes s0..s7 in order, skipping stages whose outputs are
newer than all of their inputs. `--stage s6` starts from that stage; `--force`
re-runs everything from the starting stage.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import CONFIG_DIR, DATA_DIR, stage_path

RAW = DATA_DIR / "raw"
RULES = CONFIG_DIR / "rules.yaml"
FOOTPRINTS = CONFIG_DIR / "footprints.yaml"

# stage -> (script, inputs, outputs)
STAGES: list[tuple[str, list[Path], list[Path]]] = [
    ("s0_acquire.py", [], [RAW / "taxlots.geojson"]),
    ("s1_normalize.py", [RAW / "taxlots.geojson"], [stage_path("s1_lots")]),
    ("s2_assign.py", [stage_path("s1_lots"), RULES], [stage_path("s2_lots")]),
    ("s3_filter.py", [stage_path("s2_lots"), RULES], [stage_path("s3_lots")]),
    ("s4_edges.py", [stage_path("s3_lots"), stage_path("s1_streets")], [stage_path("s4_lots")]),
    ("s5_envelope.py", [stage_path("s4_lots"), RULES], [stage_path("s5_lots")]),
    ("s6_fit.py", [stage_path("s5_lots"), RULES, FOOTPRINTS], [stage_path("s6_lots")]),
    ("s7_report.py", [stage_path("s6_lots")], [DATA_DIR / "summary.md"]),
]


def is_fresh(inputs: list[Path], outputs: list[Path]) -> bool:
    if not outputs or not all(o.exists() for o in outputs):
        return False
    if not inputs:
        return True  # s0 handles its own skip logic; presence is enough
    newest_in = max(p.stat().st_mtime for p in inputs if p.exists())
    return min(o.stat().st_mtime for o in outputs) >= newest_in


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", help="start from this stage (e.g. s6)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    started = args.stage is None
    forced = False
    for script, inputs, outputs in STAGES:
        name = script.split("_")[0]
        if not started:
            if name == args.stage:
                started = True
            else:
                continue
        if not forced and not args.force and is_fresh(inputs, outputs):
            print(f"[skip] {script} (outputs fresh)")
            continue
        forced = True  # once one stage runs, everything downstream must too
        print(f"[run ] {script}")
        rc = subprocess.call([sys.executable, str(TOOL_DIR / script)])
        if rc != 0:
            raise SystemExit(f"{script} failed with exit code {rc}")
    print("pipeline complete.")


if __name__ == "__main__":
    main()
