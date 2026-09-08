"""Pytest plumbing for tools/quadfit — puts the tool dir on sys.path.

quadfit is a standalone script directory (not a package), mirroring the
tools/gis_cache convention.

This directory ran in no CI job until 2026-09-08; the light gate now syncs
`gis` and `tools` and runs it, so nothing here should be written to skip on a
missing extra. (The docstring used to claim these tests skipped cleanly
without `gis`. Nothing implemented that, and test_s5o simply failed to import
on a machine without rasterio -- which is why it went unnoticed that the
suite was unrun.)
"""

from __future__ import annotations

import sys
from pathlib import Path

QUADFIT_DIR = Path(__file__).resolve().parents[1]
if str(QUADFIT_DIR) not in sys.path:
    sys.path.insert(0, str(QUADFIT_DIR))
