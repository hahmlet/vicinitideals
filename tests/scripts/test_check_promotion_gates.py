from __future__ import annotations

from pathlib import Path

from vicinitideals.scripts.check_promotion_gates import (
    GateDefinition,
    GateResult,
    build_gate_plan,
    evaluate_compose_services,
    run_gate,
    summarize_gate_results,
)


def test_build_gate_plan_includes_expected_checks_per_environment() -> None:
    dev = [gate.name for gate in build_gate_plan("dev")]
    staging = [gate.name for gate in build_gate_plan("staging")]
    production = [gate.name for gate in build_gate_plan("production")]

    assert dev == ["tests", "critical_lint", "compose_config", "migration_dry_run"]
    assert staging == [
        "tests",
        "critical_lint",
        "compose_config",
        "compose_health",
        "migration_dry_run",
    ]
    assert production == [
        "tests",
        "critical_lint",
        "compose_config",
        "compose_health",
        "migration_dry_run",
        "manual_approval",
    ]


def test_evaluate_compose_services_requires_running_and_healthy() -> None:
    healthy = [
        {"Service": "api", "State": "running", "Health": "healthy"},
        {"Service": "postgres", "State": "running", "Health": "healthy"},
        {"Service": "redis", "State": "running", "Health": "healthy"},
    ]
    unhealthy = [
        {"Service": "api", "State": "running", "Health": "starting"},
        {"Service": "postgres", "State": "exited", "Health": "unhealthy"},
    ]

    passing = evaluate_compose_services(healthy)
    failing = evaluate_compose_services(unhealthy)

    assert passing.passed is True
    assert failing.passed is False
    assert "api" in failing.detail
    assert "postgres" in failing.detail


def test_summarize_gate_results_fails_when_any_required_gate_fails() -> None:
    summary = summarize_gate_results(
        "staging",
        [
            GateResult(name="tests", passed=True, detail="73 passed, 1 skipped"),
            GateResult(name="critical_lint", passed=False, detail="F821 undefined name"),
            GateResult(name="compose_config", passed=True, detail="docker compose config --quiet"),
        ],
    )

    assert summary["environment"] == "staging"
    assert summary["passed"] is False
    assert summary["failed_gates"] == ["critical_lint"]


def test_run_gate_handles_missing_executable_without_crashing() -> None:
    result = run_gate(
        GateDefinition(
            name="compose_config",
            description="Docker Compose config validation",
            command=("definitely-not-a-real-binary",),
        ),
        Path.cwd(),
    )

    assert result.passed is False
    assert "not available" in result.detail.lower()


def test_run_gate_returns_failed_result_when_command_is_missing(tmp_path: Path) -> None:
    result = run_gate(
        GateDefinition(
            name="compose_config",
            description="Docker Compose binary is available",
            command=("definitely-not-a-real-command", "--version"),
        ),
        tmp_path,
    )

    assert result.passed is False
    assert "not found" in result.detail.lower()
