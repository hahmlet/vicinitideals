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
        "app.tasks.parcel_seed",
        "app.tasks.loopnet_ingest",
        "app.tasks.oregon_elicense",
        "app.tasks.export",
    ],
)

celery_app.conf.update(
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("scraping"),
        Queue("analysis"),
    ),
    task_routes={
        "app.tasks.scraper.*": {"queue": "scraping"},
        "app.tasks.scenario.*": {"queue": "analysis"},
        "app.tasks.loopnet_ingest.*": {"queue": "scraping"},
        "app.tasks.oregon_elicense.*": {"queue": "scraping"},
        "app.tasks.export.*": {"queue": "analysis"},
    },
    beat_schedule={
        "scrape-crexi-daily": {
            "task": "app.tasks.scraper.scrape_crexi",
            "schedule": crontab(hour=6, minute=0),
        },
        # Parcel enrichment queue: drip-enrich Prime/Target every 2 minutes
        "enrich-prime-target-parcels": {
            "task": "app.tasks.parcel_seed.enrich_prime_target_parcels",
            "schedule": crontab(minute="*/2"),
        },
        # LoopNet: weekly discovery Monday 07:00 UTC (offset from Crexi daily 06:00)
        "loopnet-weekly-sweep": {
            "task": "app.tasks.loopnet_ingest.loopnet_weekly_sweep",
            "schedule": crontab(day_of_week=1, hour=7, minute=0),
        },
        # LoopNet: flag-gated experiment daily refresh. Task self-skips when
        # LOOPNET_EXPERIMENT_ENABLED is false or today > LOOPNET_EXPERIMENT_END_DATE.
        "loopnet-experiment-daily": {
            "task": "app.tasks.loopnet_ingest.loopnet_experiment_daily_refresh",
            "schedule": crontab(hour=3, minute=0),
        },
        # LoopNet: monthly refresh on 1st at 04:00 UTC. Skips while experiment is active.
        "loopnet-monthly-refresh": {
            "task": "app.tasks.loopnet_ingest.loopnet_monthly_refresh",
            "schedule": crontab(day_of_month=1, hour=4, minute=0),
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
    },
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.tasks"])

__all__ = ["celery_app"]
