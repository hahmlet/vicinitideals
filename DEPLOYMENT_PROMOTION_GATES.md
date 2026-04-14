# Deployment Promotion Gates

`REAL-39` defines the minimum checks required before `re-modeling` can move between deployment tiers on VM 114.

## Promotion policy

| Tier | Required automated gates | Additional release controls |
| --- | --- | --- |
| `dev` | Full `pytest` suite, critical Ruff lint, `docker compose config --quiet`, Alembic SQL dry-run | None |
| `staging` | All `dev` gates, plus Docker Compose services on VM 114 must be `running/healthy` | Smoke-check `GET /health` after deploy |
| `production` | All `staging` gates | Manual approval / change ticket recorded before release |

## Local / VM 114 command

Run the same gate bundle locally or on VM 114:

```bash
cd /root/stacks/ketch-media-ai/re-modeling
python -m app.scripts.check_promotion_gates --environment dev
python -m app.scripts.check_promotion_gates --environment staging
python -m app.scripts.check_promotion_gates --environment production --manual-approval CHANGE-1234
```

## Gate details

1. **Tests** — `python -m pytest tests/ -q`
2. **Critical lint** — `python -m ruff check vicinitideals tests --select E9,F63,F7,F82`
3. **Compose validation** — `docker compose config --quiet`
4. **Compose health** — `docker compose ps --format json` must show `api`, `postgres`, and `redis` as `running` / `healthy` (the gate retries for up to 60 seconds after startup)
5. **Migration dry-run** — `python -m alembic -c alembic.ini upgrade head --sql`
6. **Production sign-off** — release owner / ticket reference recorded with the deploy

## CI/CD enforcement

The GitHub workflow at `.github/workflows/re-modeling-ci.yml` runs the automated `dev` gates on every relevant push / PR and then performs the `staging` container-health gate in CI. Production promotion stays blocked until manual approval is supplied.
