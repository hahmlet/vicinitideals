"""Celery app configuration for re-modeling background work."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from app.config import settings

SCRAPE_INTERVAL_SECONDS = max(int(settings.scrape_interval_hours), 1) * 60 * 60

celery_app = Celery(
    "vicinitideals",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.scraper",
        "app.tasks.scenario",
        "app.tasks.oregon_elicense",
        "app.tasks.export",
        "app.tasks.proforma_parse",
        "app.tasks.email_ingest",
        "app.tasks.maintenance",
        "app.tasks.document_preview",
    ],
)

celery_app.conf.update(
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("analysis"),
    ),
    task_routes={
        "app.tasks.scenario.*": {"queue": "analysis"},
        "app.tasks.proforma_parse.*": {"queue": "analysis"},
        "app.tasks.export.*": {"queue": "analysis"},
        "app.tasks.email_ingest.*": {"queue": "analysis"},
        "app.tasks.document_preview.*": {"queue": "analysis"},
    },
    beat_schedule={
        "scrape-crexi-daily": {
            "task": "app.tasks.scraper.scrape_crexi",
            "schedule": crontab(hour=6, minute=0),
        },
        # Crexi listing lifecycle: archive de-listed listings daily at 07:00 UTC
        # (after the 06:00 scrape, so freshly re-seen listings are excluded).
        # Self-protecting — no-ops if the scraper itself has gone stale.
        "archive-stale-crexi-daily": {
            "task": "app.tasks.scraper.archive_stale_crexi_listings",
            "schedule": crontab(hour=7, minute=0),
        },
        # Oregon eLicense: monthly enrichment sweep on 2nd at 05:00 UTC.
        # Re-enriches brokers whose license data is >30d old or never pulled.
        "oregon-elicense-monthly-sweep": {
            "task": "app.tasks.oregon_elicense.oregon_elicense_sweep",
            "schedule": crontab(day_of_month=2, hour=5, minute=0),
        },
        # Broker dedup: daily 06:00 UTC. Runs after enrichment windows so
        # license-based grouping has fresh Oregon legal-name data.
        # Idempotent — no-op when no dupes present.
        "broker-dedup-daily": {
            "task": "app.tasks.oregon_elicense.broker_dedup_sweep",
            "schedule": crontab(hour=6, minute=0),
        },
        # Test-deal janitor: daily 08:00 UTC. Hard-deletes accumulated E2E /
        # regression test deals (anything Hide-Test hides) older than the age
        # guard, so they stop piling up. Scoped to the test-name pattern only —
        # never touches a real deal. Idempotent: no-op when nothing matches.
        "purge-test-deals-daily": {
            "task": "app.tasks.maintenance.purge_test_deals_task",
            "schedule": crontab(hour=8, minute=0),
        },
    },
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.tasks"])

__all__ = ["celery_app"]
