# Release Readiness Checklist

Use this go/no-go checklist before marking any release as `Released` in Plane. This is a **manual process gate**, not an automated workflow.

> A release should not move forward until every required item is checked off or a waiver is explicitly documented with an owner and rationale.

Optional helper: `python -m app.scripts.check_promotion_gates --environment staging --json` can be used to collect test/lint/compose/migration evidence, but the final go/no-go decision still requires human review.

## Release Metadata

- **Release name / tag:** 
- **Date:** 
- **Owner:** 
- **Branch / commit:** 
- **Plane work items included:** 
- **Notes / waivers:** 

---

## Testing Gate

- [ ] `python -m pytest tests/ -q` reports `0` failures (excluding any known pre-existing scraper failure, which must have its own open ticket)
- [ ] No new test failures are introduced compared to the previous release baseline
- [ ] Benchmark fixture tests pass: `tests/exporters/test_benchmark_fixtures.py`

## Code Quality Gate

- [ ] `ruff check vicinitideals/` reports `0` errors
- [ ] No new `TODO`, `FIXME`, or `HACK` comments are introduced in this release's diff

## Database Gate

- [ ] `alembic upgrade head` succeeds on a clean staging database
- [ ] Downgrade is tested if any migration in the release is destructive

## Documentation Gate

- [ ] `CHANGELOG.md` is updated with this release's changes
- [ ] Any new endpoints are documented in `docs/api/examples/`

## Plane Gate

- [ ] All work items included in this release are in the `Ready for Release` state
- [ ] There are no open P0 security items remaining in the hardening backlog

---

## Final Go / No-Go Decision

- [ ] **GO** — release approved
- [ ] **NO-GO** — release blocked

### Sign-off

- **Reviewed by:** 
- **Decision timestamp:** 
- **Blocking issues / follow-ups:** 
