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
    },
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.tasks"])

__all__ = ["celery_app"]
