# Release Rollback Runbook

> Scope: `vicinitideals` on VM `114` (`dockervm`). Appsmith is deprecated and removed.

## Verified Environment Snapshot

A **non-destructive dry-run** was validated on **2026-04-03** against VM `114` (`dockervm`). Because the current deployment uses a single shared host, the dry-run focused on command validation, service inventory, and restore-path verification without stopping production containers.

- Stack path: `/root/stacks/vicinitideals`
- Core services from `docker compose config --services`:
  `postgres`, `redis`, `api`, `beat`, `static-files`, `worker-analysis`, `worker-default`, `worker-scraping`

---

## 1. When to Roll Back

Use a rollback when a production deploy introduces one or more of these conditions:

- `api` fails health checks or returns repeated `5xx`
- Alembic migration succeeds technically but breaks runtime behavior or data access
- A new container image tag causes regression or startup failure
- Multiple `vicinitideals` services fail and root cause cannot be isolated quickly

### Rollback Decision Table

| Scenario | Rollback Type | Target |
| --- | --- | --- |
| Only FastAPI / Celery app code is broken | **Partial** | `api`, `worker-*`, `beat` |
| Schema revision must be reversed | **Partial + DB** | Alembic + `postgres` |
| Unknown blast radius or data integrity risk | **Full** | Entire stack |

---

## 2. Required Rollback Points Before Promotion

Every production promotion should create a rollback bundle **before** changing anything.

From VM `114`:

```bash
cd /root/stacks/vicinitideals
stamp=$(date +%Y%m%d%H%M%S)
mkdir -p /root/backups/vicinitideals

git rev-parse HEAD > /root/backups/vicinitideals/release-${stamp}.sha

docker compose exec api alembic current \
  > /root/backups/vicinitideals/release-${stamp}.alembic.txt

docker run --rm \
  -v re-modeling-postgres-data:/data \
  -v /root/backups/vicinitideals:/backup \
  alpine sh -lc 'cd /data && tar czf /backup/postgres-'"${stamp}"'.tgz .'
```

Do **not** deploy without knowing:

1. the last-known-good git SHA,
2. the current Alembic revision,
3. the matching Postgres backup,
4. the approved image tag or digest for any externally pulled image.

---

## 3. Immediate Safety Actions

1. Announce a **deployment freeze**.
2. Capture current evidence:

```bash
cd /root/stacks/vicinitideals

docker compose ps

docker compose logs --tail 100 api worker-default worker-analysis worker-scraping beat
```

3. Record:
   - failing SHA or release identifier,
   - incident start time,
   - whether any DB migration was included.

---

## 4. Partial Rollback Procedures

### A. API / Worker Rollback (No Schema Change)

Use this when only application code regressed and the DB schema is still compatible.

```bash
ssh root@192.168.1.28
cd /root/stacks/vicinitideals

git fetch origin

git checkout <last-known-good-sha>

docker compose build api worker-default worker-analysis worker-scraping beat

docker compose up -d api worker-default worker-analysis worker-scraping beat
```

Then verify:

```bash
docker compose ps

docker logs --tail 100 vicinitideals-api

docker exec re-modeling-postgres pg_isready -U re_modeling -d re_modeling
```

### B. Database Migration Reversal

Use this only if the migration is known to be reversible and a rollback target is documented.

1. Confirm the active revision:

```bash
cd /root/stacks/vicinitideals
docker compose exec api alembic current
docker compose exec api alembic history --verbose | tail -n 40
```

2. Downgrade to the previous known-good revision:

```bash
docker compose exec api alembic downgrade <previous_revision>
```

3. Restart the application services:

```bash
docker compose up -d api worker-default worker-analysis worker-scraping beat
```

> If the migration removed or transformed data in a non-reversible way, stop here and use the **Full Rollback** procedure with a Postgres restore.

### C. Docker Image Pin Rollback

Use this when an upstream image update caused the regression.

If `api` or worker services move from local `build:` to pinned registry images, revert those image tags in `docker-compose.yml` and run:

```bash
docker compose pull api worker-default worker-analysis worker-scraping beat
docker compose up -d api worker-default worker-analysis worker-scraping beat
```

---

## 5. Full Rollback Procedure

Use this when the failure involves both code and data risk, or when the blast radius is unclear.

### Step 1 — Stop the affected services

```bash
ssh root@192.168.1.28
cd /root/stacks/vicinitideals

docker compose stop api worker-default worker-analysis worker-scraping beat
```

### Step 2 — Revert to the last-known-good release

```bash
git fetch origin
git checkout <last-known-good-sha>
```

### Step 3 — Restore Postgres from backup

```bash
docker compose stop postgres

docker run --rm \
  -v re-modeling-postgres-data:/target \
  -v /root/backups/vicinitideals:/backup \
  alpine sh -lc 'cd /target && rm -rf ./* && tar xzf /backup/postgres-<timestamp>.tgz'
```

### Step 4 — Bring the stack back up

```bash
docker compose up -d
```

---

## 6. Post-Rollback Validation Checklist

Run all checks before declaring the incident mitigated:

```bash
cd /root/stacks/vicinitideals

docker compose ps

docker logs --tail 100 vicinitideals-api

docker exec re-modeling-postgres pg_isready -U re_modeling -d re_modeling
```

Also verify externally:

- `viciniti.deals` loads in browser
- Existing deal data is intact
- No new migration errors appear in the API logs

---

## 7. Exit Criteria

A rollback is complete only when all of the following are true:

- containers are stable for at least 10–15 minutes,
- `viciniti.deals` is accessible and functional,
- the Postgres health check is passing,
- the team has recorded the rollback SHA, restored backup timestamps, and the reason for rollback.

---

## 8. Follow-Up Actions

After recovery:

1. lock the failed release from re-promotion,
2. open a follow-up work item with root cause and remediation,
3. attach the exact failing SHA / migration revision / image tag.

## Notes

- Prefer **partial rollback** when the blast radius is well understood.
- Prefer **full rollback** when data integrity is in doubt.
- Never run a DB downgrade without a fresh backup already taken.
- For future releases, replace floating images with explicit tags/digests before promotion whenever possible.
