"""Every FLATS script answers ``--help`` without doing its work."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted(
    [*(REPO_ROOT / "scripts").glob("flats_*.py"), REPO_ROOT / "scripts" / "check_flats_firewall.py"]
)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_help_exits_zero_and_prints_usage(script: Path):
    done = subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert done.returncode == 0, done.stderr[-2000:]
    assert "usage" in done.stdout.lower()
