"""scripts/ci_local.py: which suites a push needs (FOLLOWUPS 128).

The selection is folder-level on purpose; the dangerous mistake is a change that
reaches a test while its suite is skipped, so most cases here pin "runs".
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ci_local", Path(__file__).resolve().parents[2] / "scripts" / "ci_local.py"
)
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)


def test_bookkeeping_only_runs_nothing():
    assert ci.suites_for([
        "docs/FOLLOWUPS.md", "docs/followups/128-ci-speed.md", ".claude/agents/x.md",
        "CLAUDE.md", ".gitignore", "docs/ops/parallel-agents.md",
    ]) == set()


def test_docs_that_tests_read_are_not_bookkeeping():
    for f in ("docs/DATA_MODEL.md", "docs/FINANCIAL_MODEL.md", "docs/feature-plans/a.md"):
        assert "app_all" in ci.suites_for([f]), f


def test_flats_change_runs_flats_quadfit_and_app_tests_that_mention_flats():
    need = ci.suites_for(["flats/config/jurisdictions/or/multnomah/portland.yaml"])
    assert {"ruff", "firewall", "flats", "quadfit", "app_flats"} <= need
    assert "app_all" not in need


def test_quadfit_data_and_flats_scripts_are_flats_side():
    for f in ("Lot Analysis/quadfit/rules.yaml", "data/flats/carry/x.json", "scripts/flats_promote.py"):
        assert "quadfit" in ci.suites_for([f]), f


def test_app_change_runs_whole_app_suite_and_flats_suite():
    need = ci.suites_for(["app/api/routers/ui_flats.py"])
    assert {"flats", "app_all"} <= need
    assert "quadfit" not in need


def test_unknown_or_shared_file_runs_everything():
    for f in ("pyproject.toml", "uv.lock", ".github/workflows/ci.yml", "docker-compose.yml"):
        need = ci.suites_for([f])
        assert {"flats", "quadfit", "app_all"} <= need, f


def test_a_bookkeeping_file_does_not_hide_a_code_file():
    assert "flats" in ci.suites_for(["docs/FOLLOWUPS.md", "flats/score/screen.py"])


def test_whole_app_suite_covers_the_flats_subset():
    assert ci.covers({"ruff", "firewall", "flats", "app_all", "quadfit"},
                     {"ruff", "firewall", "flats", "quadfit", "app_flats"})
    assert not ci.covers({"ruff", "firewall", "flats", "app_all"},
                         {"ruff", "firewall", "flats", "quadfit", "app_flats"})
