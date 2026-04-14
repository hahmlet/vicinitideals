# Observability SLO Dashboard Spec

`REAL-41` defines the **monitoring spec** for the `re-modeling` release-ops dashboard. This is a requirements document for Grafana or an equivalent observability tool; it does **not** implement the dashboard itself.

## Purpose

The dashboard should answer three release-critical questions in under one minute:

1. **Is the platform up and responsive for users right now?**
2. **Are ingestion and model-compute pipelines fresh enough to trust?**
3. **Did the latest release introduce drift or instability that should block promotion or trigger rollback?**

This spec complements:

- `DEPLOYMENT_PROMOTION_GATES.md`
- `docs/ops/rollback.md`
- `docs/verification/baseline-2026-04-03.md`

Together, those documents form the release-ops triad: **promote safely, observe continuously, roll back quickly**.

---

## Scope and Non-Goals

### In scope

- SLO definitions and thresholds
- Required dashboard widgets and layout
- Data sources the dashboard must consume
- Alert thresholds and routing expectations

### Out of scope

- Grafana provisioning / Terraform / Docker setup
- Exporter or collector implementation details
- PagerDuty / Slack wiring specifics
---

## Service Tiers and SLOs

The dashboard must track the following service tiers.

| Tier | What it covers | Why it matters |
| --- | --- | --- |
| `Tier A — Interactive API` | FastAPI request availability, latency, error rate | User-visible uptime and responsiveness |
| `Tier B — Ingestion / scraping` | saved-search freshness, ingest success/failure, queue health | Listing data gets stale quickly if ingestion slips |
| `Tier C — Compute engine` | cashflow / waterfall / scenario run duration and failures | Underwriting work stalls if compute paths degrade |
| `Tier D — Model integrity` | nightly parity / benchmark drift status | A "healthy" app is still unsafe if the math drifts |

### SLO targets

| Tier | SLI | Target | Warning threshold | Critical threshold | Source of truth |
| --- | --- | --- | --- | --- | --- |
| `Tier A` | API availability (non-5xx success ratio for `/health`, `/projects*`, `/models*`, `/portfolios*`) | `>= 99.5%` over 30 days | `< 99.7%` over 1 hour | `< 99.5%` over 15 minutes | reverse-proxy / API request metrics |
| `Tier A` | Read-request latency (`GET` p95) | `<= 750 ms` | `> 900 ms` for 15 min | `> 1500 ms` for 5 min | request duration histogram or `X-Process-Time-Ms` aggregation |
| `Tier A` | Write / compute-trigger latency (`POST/PATCH/DELETE` p95) | `<= 1500 ms` | `> 2000 ms` for 15 min | `> 3000 ms` for 5 min | same as above |
| `Tier A` | 5xx error rate | `< 1%` of requests over 15 min | `>= 1%` | `>= 2%` | HTTP status metrics |
| `Tier B` | Scrape freshness | `>= 95%` of active saved searches refreshed in `24h` | oldest successful ingest `> 24h` | oldest successful ingest `> 48h` | `IngestJob` timestamps / scraper run logs |
| `Tier B` | Scrape success rate | `>= 90%` over rolling 24h | `< 90%` | `< 80%` | ingest job status counts |
| `Tier C` | Interactive model compute duration (`/models/{id}/compute`, waterfall/report) | p95 `<= 5s` | p95 `> 5s` for 15 min | p95 `> 10s` for 5 min | structured run timing logs / API metrics |
| `Tier C` | Scenario run duration (background jobs) | p95 `<= 120s` | p95 `> 180s` | p95 `> 300s` or queued `> 10 min` | Celery task metrics / structured logs |
| `Tier C` | Compute failure rate | `< 2%` over 1h | `>= 2%` | `>= 5%` | run outcome logs |
| `Tier D` | Benchmark drift / parity | latest nightly run passes all fixtures within `±$1.00` and `±0.01` | parity job failed once or stale `> 24h` | drift exceeds tolerance or stale `> 72h` | benchmark/parity job result |

### Notes on thresholds

- The **latency SLOs** reflect an internal underwriting tool: sub-second reads are preferred, but brief write-path spikes are acceptable.
- The **scrape freshness SLO** is intentionally tighter than a weekly ops review because stale listing data materially affects acquisition work.
- The **model-integrity SLO** uses the thresholds already documented in `docs/verification/baseline-2026-04-03.md`.

---

## Required Data Sources

The dashboard implementation may use Grafana + Prometheus/Loki or an equivalent stack, but it must expose the following logical sources:

| Data source | Required signals |
| --- | --- |
| **HTTP / API metrics** | request count, status code, route, duration percentiles, `X-Trace-ID`, `X-Process-Time-Ms` |
| **Structured application logs** | `*_started`, `*_completed`, `*_failed` events emitted from `vicinitideals.observability` helpers |
| **Celery / Redis / worker metrics** | queue depth, task age, task success/failure counts, worker liveness |
| **Container health** | `api`, `postgres`, `redis`, `beat`, `worker-*` running/healthy state |
| **Benchmark drift / parity job output** | latest pass/fail timestamp, max dollar delta, max rate delta, fixture name |

### Current repo signals already available

The dashboard should build on signals that already exist in the codebase:

- `vicinitideals/api/main.py` adds `X-Trace-ID` and `X-Process-Time-Ms`
- `vicinitideals/observability.py` provides shared timing and structured log helpers
- `vicinitideals/tasks/scraper.py` and `vicinitideals/tasks/scenario.py` log start / success / failure observations
- benchmark drift baselines live under `docs/verification/` and `tests/exporters/test_benchmark_fixtures.py`

---

## Dashboard Layout Spec

The dashboard should fit on **one main page** with five rows.

### Row 1 — Executive status strip

Six compact stat panels, color-coded `green / yellow / red`:

| Panel | Type | Refresh |
| --- | --- | --- |
| API availability (30d) | stat / gauge | `1m` |
| 5xx error rate (15m) | stat | `1m` |
| p95 API latency | stat | `1m` |
| Oldest scrape age | stat | `5m` |
| p95 model compute duration | stat | `1m` |
| Latest benchmark drift status | stat | `15m` |

### Row 2 — API reliability and latency

| Widget | Visualization | Must show |
| --- | --- | --- |
| Request volume + 5xx overlay | time series | requests/min and 5xx % over time |
| Latency percentile chart | time series | p50 / p95 / p99 grouped by read vs write paths |
| Route hot spots | table | top slow endpoints by p95 and error count |
| Service health table | table / status history | current state of `api`, `postgres`, `redis`, `worker-*` |

### Row 3 — Ingestion and freshness

| Widget | Visualization | Must show |
| --- | --- | --- |
| Saved-search freshness by source | bar / table | `loopnet`, `crexi`, other sources with oldest successful run age |
| Ingest outcome trend | stacked bars | completed / failed / retried jobs per hour |
| Queue health | stat / time series | queued jobs, backlog age, retry spikes |
| Freshness violations | table | saved searches or projects exceeding 24h / 48h thresholds |

### Row 4 — Model compute performance

| Widget | Visualization | Must show |
| --- | --- | --- |
| Compute duration by run type | time series | cashflow, waterfall, scenario durations |
| Failure trend | stacked bars | compute failures by run type / endpoint |
| Slowest recent traces | table | trace id, project/model id, started at, duration ms |
| Scenario backlog | stat / table | queued count, longest-running job, last completed time |

### Row 5 — Integrity and release safety

| Widget | Visualization | Must show |
| --- | --- | --- |
| Benchmark parity status | table / status panel | latest run timestamp, fixture status, max deltas |
| Promotion gate summary | text / table | last `tests`, `critical_lint`, `compose_health`, `migration_dry_run` result |
| Rollback readiness panel | text | link / note to `docs/ops/rollback.md` and last-known-good release metadata |
| Alert feed | log panel | active warnings / critical alerts with timestamps |

---

## Alert Rules

The dashboard spec assumes two alert severities.

### Warning

Use for degradations that need same-day attention but do not yet justify rollback:

- API availability under `99.7%` for 1 hour
- API p95 latency above warning thresholds for 15 minutes
- oldest scrape age over `24h`
- scenario p95 duration over `180s`
- parity job stale over `24h`

### Critical

Use for conditions that should block promotion or trigger rollback review:

- API availability under `99.5%` for 15 minutes
- 5xx rate at or above `2%` for 5 minutes
- oldest scrape age over `48h`
- queued compute or scenario jobs older than `10 min`
- parity drift exceeds `±$1.00` or `±0.01`
- core service health shows `api`, `postgres`, or `redis` not `running/healthy`

---

## Implementation Acceptance Checklist

The eventual dashboard implementation should be considered complete only when:

- [ ] all `Tier A`–`Tier D` SLO widgets are present
- [ ] every widget has a named data source and refresh interval
- [ ] warning and critical thresholds match this document
- [ ] the latest benchmark parity result is surfaced directly on the dashboard
- [ ] at least one panel links operators back to `DEPLOYMENT_PROMOTION_GATES.md` and `docs/ops/rollback.md`
- [ ] the dashboard can answer: **up, fresh, fast, mathematically trustworthy**

---

## Recommended Follow-on Work

This spec should drive a separate infrastructure implementation task for:

1. metric collection / exporters,
2. Grafana dashboard provisioning,
3. alert routing configuration,
4. nightly parity-result publishing into the observability stack.
