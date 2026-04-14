"""Celery task package for re-modeling."""

from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
