"""Pytest plumbing for tools/quadfit — puts the tool dir on sys.path.

quadfit is a standalone script directory (not a package), mirroring the
tools/gis_cache convention. All tests here skip cleanly when the `gis` extra
isn't installed (CI light gate doesn't sync it).
"""

from __future__ import annotations

import sys
from pathlib import Path

QUADFIT_DIR = Path(__file__).resolve().parents[1]
if str(QUADFIT_DIR) not in sys.path:
    sys.path.insert(0, str(QUADFIT_DIR))
