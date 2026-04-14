# Background Tasks

## Queues

| Queue | Purpose | Current tasks |
|---|---|---|
| `default` | General-purpose background work | future housekeeping / orchestration tasks |
| `scraping` | Listing ingestion through LXC 134 Scrapling | `app.tasks.scraper.scrape_listings` |
| `analysis` | Post-ingestion modeling and analytics | `app.tasks.scenario.run_scenario`, `app.tasks.scenario.sweep_variable` |

Any task under `app.tasks.scraper` is routed to the `scraping` queue.
Any task under `app.tasks.scenario` is routed to the `analysis` queue.

---

## ProxyOn residential proxy architecture

Production listing sites such as LoopNet and Crexi commonly block datacenter IPs, so the scraper sends LXC 134 requests through **ProxyOn residential proxies** when credentials are configured.

- The Celery worker does **not** call the ProxyOn API at scrape time.
- Credentials are static subscription credentials from the ProxyOn panel.
- The worker passes a `proxy` object to the black-box Scrapling service at `LXC134_SCRAPLING_URL`.
- Local development can leave `PROXYON_RESIDENTIAL_USERNAME` and `PROXYON_RESIDENTIAL_PASSWORD` unset; the payload will omit the proxy config.

### How to obtain credentials

1. Order a residential subscription in the ProxyOn panel.
2. Copy the residential username/password from the subscription details.
3. Store them in `.env` as `PROXYON_RESIDENTIAL_USERNAME` and `PROXYON_RESIDENTIAL_PASSWORD`.

> API-key to session-token auth exists for account automation, but it is out of scope for Stage 1C because scraping uses the static residential subscription credentials directly.

---

## Manual task triggers

### Scraping

```bash
celery -A app.tasks.celery_app call app.tasks.scraper.scrape_listings --args '["loopnet", {}]'
```

### Scenario analysis

```bash
celery -A app.tasks.celery_app call app.tasks.scenario.run_scenario --args '["<scenario-uuid>"]'
celery -A app.tasks.celery_app call app.tasks.scenario.sweep_variable --args '["<scenario-uuid>"]'
```

Use `.delay()` or `.apply_async()` from application code so scrape tasks stay on `scraping` and scenario tasks stay on `analysis`.

---

## Scenario variable allow-list

Only the following keys are valid for Stage 1E sweeps:

- `operational.exit_cap_rate_pct`
- `operational.lease_up_months`
- `operational.expense_growth_rate_pct_annual`
- `operational.hold_period_years`
- `operational.hard_cost_per_unit`

---

## Beat schedule

Celery Beat runs the default LoopNet and Crexi scrape jobs on `SCRAPE_INTERVAL_HOURS`.

- Default interval: `6` hours
- Config source: `app.config.Settings.scrape_interval_hours`
- Beat sends both sources to `app.tasks.scraper.scrape_listings`
