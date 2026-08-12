"""The financial engine is untouchable from FLATS work.

Steph's instruction was explicit: do not impact the financial engines. This is
the enforcement, and these tests are its contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_flats_firewall import (  # noqa: E402
    PROTECTED,
    forbidden_imports,
    is_flats_scoped,
    touched_protected,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_flats_change_alone_passes() -> None:
    files = ["flats/rules/loader.py", "flats/tests/test_rules.py"]

    assert is_flats_scoped(files)
    assert touched_protected(files) == []


def test_engine_change_alone_is_not_flats_scoped() -> None:
    # Ordinary underwriting work is untouched by this guard.
    files = ["app/engines/cashflow.py", "tests/engines/test_cashflow.py"]

    assert not is_flats_scoped(files)


@pytest.mark.parametrize(
    "protected",
    [
        "app/engines/cashflow.py",
        "app/engines/waterfall.py",
        "app/models/deal.py",
        "app/models/capital.py",
        "app/schemas/capital.py",
        "app/api/routers/ui_model_builder.py",
        "app/exporters/excel.py",
        "tests/engines/test_underwriting.py",
        "tests/e2e/test_phase_b_debt.py",
    ],
)
def test_mixing_flats_with_a_protected_path_is_caught(protected: str) -> None:
    files = ["flats/fit/rectangle.py", protected]

    assert is_flats_scoped(files)
    assert touched_protected(files) == [protected]


def test_quadfit_counts_as_flats_scoped() -> None:
    # The old tree is FLATS' predecessor and gets the same firewall until it goes.
    assert is_flats_scoped(["Lot Analysis/quadfit/s6_fit.py"])


def test_protected_paths_exist_on_disk() -> None:
    # A guard listing paths that no longer exist protects nothing. This catches
    # a rename that silently opens a hole.
    missing = [p for p in PROTECTED if not (REPO_ROOT / p).exists()]
    assert missing == [], f"protected paths no longer present: {missing}"


def test_flats_does_not_import_the_financial_engine() -> None:
    assert forbidden_imports() == []


def test_forbidden_import_is_detected(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("from app.engines.cashflow import compute\n", encoding="utf-8")

    hits = forbidden_imports(tmp_path)

    assert len(hits) == 1
    assert "app.engines.cashflow" in hits[0]
