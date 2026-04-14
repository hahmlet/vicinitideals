from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


ENVIRONMENT_ALIASES = {
    "dev": "dev",
    "development": "dev",
    "stage": "staging",
    "staging": "staging",
    "prod": "production",
    "production": "production",
}


def _normalize_environment(environment: str) -> str:
    normalized = ENVIRONMENT_ALIASES.get(environment.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported environment: {environment}")
    return normalized


@dataclass(frozen=True)
class GateDefinition:
    name: str
    description: str
    command: tuple[str, ...] | None = None
    manual_only: bool = False


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str
    command: str | None = None
    manual_only: bool = False


def build_gate_plan(environment: str) -> list[GateDefinition]:
    normalized = _normalize_environment(environment)

    python = sys.executable
    plan = [
        GateDefinition(
            name="tests",
            description="Full pytest suite passes",
            command=(python, "-m", "pytest", "tests/", "-q"),
        ),
        GateDefinition(
            name="critical_lint",
            description="No critical Ruff lint errors (syntax / undefined names)",
            command=(python, "-m", "ruff", "check", "vicinitideals", "tests", "--select", "E9,F63,F7,F82"),
        ),
        GateDefinition(
            name="compose_config",
            description="Docker Compose file validates cleanly",
            command=("docker", "compose", "config", "--quiet"),
        ),
    ]

    if normalized in {"staging", "production"}:
        plan.append(
            GateDefinition(
                name="compose_health",
                description="Required Docker Compose services are running and healthy",
                command=("docker", "compose", "ps", "--format", "json"),
            )
        )

    plan.append(
        GateDefinition(
            name="migration_dry_run",
            description="Alembic migration dry-run renders SQL successfully",
            command=(python, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head", "--sql"),
        )
    )

    if normalized == "production":
        plan.append(
            GateDefinition(
                name="manual_approval",
                description="Release owner approval / change ticket recorded",
                manual_only=True,
            )
        )

    return plan


def _parse_compose_ps_output(output: str) -> list[dict[str, Any]]:
    payload = output.strip()
    if not payload:
        return []

    if payload.startswith("["):
        decoded = json.loads(payload)
        return decoded if isinstance(decoded, list) else [decoded]

    services: list[dict[str, Any]] = []
    for line in payload.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        services.append(json.loads(stripped))
    return services


def evaluate_compose_services(services: list[dict[str, Any]]) -> GateResult:
    if not services:
        return GateResult(
            name="compose_health",
            passed=False,
            detail="No Docker Compose services were reported by `docker compose ps --format json`.",
        )

    failing: list[str] = []
    detail_parts: list[str] = []

    for service in services:
        name = str(service.get("Service") or service.get("Name") or "unknown")
        state = str(service.get("State") or "").strip().lower()
        health = str(service.get("Health") or "").strip().lower()
        status = str(service.get("Status") or "").strip().lower()

        if not state and status:
            state = "running" if "running" in status else status

        if not health and status:
            if "healthy" in status:
                health = "healthy"
            elif "unhealthy" in status:
                health = "unhealthy"
            elif "starting" in status:
                health = "starting"

        detail_parts.append(f"{name}={state or 'unknown'}/{health or 'n/a'}")

        if state != "running":
            failing.append(name)
            continue
        if health and health != "healthy":
            failing.append(name)

    return GateResult(
        name="compose_health",
        passed=not failing,
        detail="; ".join(detail_parts),
        command="docker compose ps --format json",
    )


def _run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _trim_output(output: str, fallback: str) -> str:
    text = output.strip()
    if not text:
        return fallback
    lines = text.splitlines()
    if len(lines) > 12:
        return "\n".join(lines[-12:])
    return text


def _missing_command_result(definition: GateDefinition) -> GateResult:
    command = definition.command or ()
    executable = command[0] if command else "unknown"
    command_text = " ".join(command) if command else None
    return GateResult(
        name=definition.name,
        passed=False,
        detail=f"Required executable not available or not found: {executable}",
        command=command_text,
        manual_only=definition.manual_only,
    )


def run_gate(
    definition: GateDefinition,
    repo_root: Path,
    *,
    manual_approval: str | None = None,
) -> GateResult:
    if definition.manual_only:
        if manual_approval:
            return GateResult(
                name=definition.name,
                passed=True,
                detail=f"Approved via {manual_approval}",
                manual_only=True,
            )
        return GateResult(
            name=definition.name,
            passed=False,
            detail="Production promotion requires `--manual-approval <ticket-or-approver>`.",
            manual_only=True,
        )

    assert definition.command is not None
    command_text = " ".join(definition.command)

    try:
        completed = _run_command(definition.command, repo_root)
    except FileNotFoundError:
        return _missing_command_result(definition)

    if completed.returncode != 0:
        return GateResult(
            name=definition.name,
            passed=False,
            detail=_trim_output(completed.stderr or completed.stdout, f"{definition.name} failed"),
            command=command_text,
        )

    if definition.name == "compose_health":
        result = evaluate_compose_services(_parse_compose_ps_output(completed.stdout))
        for _ in range(11):
            if result.passed or "starting" not in result.detail.lower():
                break
            time.sleep(5)
            try:
                completed = _run_command(definition.command, repo_root)
            except FileNotFoundError:
                return _missing_command_result(definition)
            if completed.returncode != 0:
                return GateResult(
                    name=definition.name,
                    passed=False,
                    detail=_trim_output(completed.stderr or completed.stdout, f"{definition.name} failed"),
                    command=command_text,
                )
            result = evaluate_compose_services(_parse_compose_ps_output(completed.stdout))

        return GateResult(
            name=result.name,
            passed=result.passed,
            detail=result.detail,
            command=command_text,
        )

    return GateResult(
        name=definition.name,
        passed=True,
        detail=_trim_output(completed.stdout, f"{definition.name} passed"),
        command=command_text,
    )


def summarize_gate_results(environment: str, results: Sequence[GateResult]) -> dict[str, Any]:
    failed_gates = [result.name for result in results if not result.passed]
    normalized = _normalize_environment(environment)
    return {
        "environment": normalized,
        "passed": not failed_gates,
        "failed_gates": failed_gates,
        "results": [asdict(result) for result in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run re-modeling deployment promotion gates.")
    parser.add_argument(
        "--environment",
        choices=["dev", "staging", "production"],
        default="dev",
        help="Promotion tier to validate.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Path to the re-modeling repository root.",
    )
    parser.add_argument(
        "--manual-approval",
        help="Change ticket, approver, or release note reference required for production promotion.",
    )
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    results = [
        run_gate(gate, repo_root, manual_approval=args.manual_approval)
        for gate in build_gate_plan(args.environment)
    ]
    summary = summarize_gate_results(args.environment, results)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Promotion gates for {args.environment}:")
        for result in results:
            marker = "PASS" if result.passed else "FAIL"
            print(f"[{marker}] {result.name}: {result.detail}")
        print()
        if summary["passed"]:
            print(f"{args.environment.title()} promotion gates passed.")
        else:
            failed = ", ".join(summary["failed_gates"])
            print(f"{args.environment.title()} promotion blocked by: {failed}")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "GateDefinition",
    "GateResult",
    "build_gate_plan",
    "evaluate_compose_services",
    "run_gate",
    "summarize_gate_results",
]
