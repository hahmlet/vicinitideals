"""Firewall: FLATS work must never touch the financial engine.

FLATS and the underwriting platform share a repository and a database. They must
not share a blast radius. A change that touches ``flats/`` is screening work; if
the same change also edits the cashflow engine, the waterfall, the capital
models, or their tests, something has gone wrong — either an accidental edit or
a coupling that should not exist.

The seam is one-directional whatever shape it ends up taking: FLATS produces,
the financial side consumes. Nothing under ``flats/`` may import from
``app.engines``.

Usage::

    python scripts/check_flats_firewall.py                # diff vs origin/main
    python scripts/check_flats_firewall.py --base HEAD~1
    python scripts/check_flats_firewall.py --files a.py b.py

Exits non-zero with an explanation when the firewall is breached.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Paths the financial engine owns. A FLATS-scoped change may not modify these.
PROTECTED: tuple[str, ...] = (
    "app/engines/",
    "app/exporters/",
    "app/models/deal.py",
    "app/models/capital.py",
    "app/models/capital_draw_event.py",
    "app/models/scenario.py",
    "app/models/milestone.py",
    "app/models/cashflow.py",
    "app/schemas/capital.py",
    "app/schemas/deal.py",
    "app/api/routers/ui_model_builder.py",
    "app/api/routers/ui_model_outputs.py",
    "app/api/routers/capital.py",
    "app/api/routers/scenarios.py",
    "tests/engines/",
    "tests/e2e/test_phase_b_debt.py",
)

#: Paths that mark a change as FLATS-scoped.
FLATS_SCOPES: tuple[str, ...] = ("flats/", "Lot Analysis/")

#: FLATS source may not import from these modules.
FORBIDDEN_IMPORTS: tuple[str, ...] = ("app.engines", "app.exporters")


def _norm(p: str) -> str:
    return p.replace("\\", "/").strip()


def changed_files(base: str) -> list[str]:
    """Files changed against ``base``. Falls back to the working tree diff."""
    for args in (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", base],
        ["git", "diff", "--name-only", "HEAD"],
    ):
        try:
            out = subprocess.run(
                args, cwd=REPO_ROOT, capture_output=True, text=True, check=True
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        files = [_norm(line) for line in out.splitlines() if line.strip()]
        if files:
            return files
    return []


def touched_protected(files: list[str]) -> list[str]:
    return sorted({f for f in files if any(f.startswith(p) for p in PROTECTED)})


def is_flats_scoped(files: list[str]) -> bool:
    return any(f.startswith(s) for s in FLATS_SCOPES for f in files)


def forbidden_imports(root: Path | None = None) -> list[str]:
    """FLATS source importing the financial engine, as ``path:line`` strings."""
    root = root or (REPO_ROOT / "flats")
    if not root.exists():
        return []
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            if any(mod in stripped for mod in FORBIDDEN_IMPORTS):
                rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
                hits.append(f"{_norm(str(rel))}:{n}: {stripped}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="origin/main", help="Git ref to diff against.")
    ap.add_argument("--files", nargs="*", help="Explicit file list instead of a git diff.")
    args = ap.parse_args()

    files = [_norm(f) for f in (args.files or changed_files(args.base))]
    problems: list[str] = []

    if files and is_flats_scoped(files):
        breached = touched_protected(files)
        if breached:
            problems.append(
                "This change touches FLATS and the financial engine in the same commit.\n"
                "  Protected paths modified:\n    "
                + "\n    ".join(breached)
                + "\n  Split them: screening work and underwriting work ship separately."
            )

    imports = forbidden_imports()
    if imports:
        problems.append(
            "FLATS source imports the financial engine:\n    "
            + "\n    ".join(imports)
            + "\n  The seam is one-directional — FLATS produces, finance consumes."
        )

    if problems:
        print("FLATS FIREWALL BREACH\n", file=sys.stderr)
        for p in problems:
            print(f"- {p}\n", file=sys.stderr)
        return 1

    scope = "FLATS-scoped" if is_flats_scoped(files) else "not FLATS-scoped"
    print(f"flats firewall OK — {len(files)} changed file(s), {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
