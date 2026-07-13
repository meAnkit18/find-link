"""Celery wrappers over the shared pipeline steps (evidence_core.pipeline).

Only needed when INGEST_MODE=celery. The default (inline) mode runs the same
step functions in a thread pool inside the API process --- see
graph_explorer_api/routers/evidence.py.

PipelineCancelled is a *user action* (Stop button), not a failure, so tasks
must not retry on it — they swallow it and break the chain by returning None.
"""

from __future__ import annotations

import os

from celery import Celery, chain

from evidence_core.database import init_db
from evidence_core.pipeline import (
    PipelineCancelled,
    step_enrich,
    step_extract,
    step_parse,
    step_resolve,
    step_write,
)

celery_app = Celery(
    "kgpipeline",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1

init_db()


def _guarded(step, evidence_id: str) -> str | None:
    """Run a step; convert a user cancellation into a chain-stopping None."""
    try:
        step(evidence_id)
    except PipelineCancelled:
        return None
    return evidence_id


@celery_app.task(name="pipeline.parse", bind=True, max_retries=2)
def parse_task(self, evidence_id: str) -> str | None:
    return _guarded(step_parse, evidence_id)


@celery_app.task(name="pipeline.extract", bind=True, max_retries=2, default_retry_delay=30)
def extract_task(self, evidence_id: str | None) -> str | None:
    if evidence_id is None:
        return None
    return _guarded(step_extract, evidence_id)


@celery_app.task(name="pipeline.resolve", bind=True, max_retries=1)
def resolve_task(self, evidence_id: str | None) -> str | None:
    if evidence_id is None:
        return None
    return _guarded(step_resolve, evidence_id)


@celery_app.task(name="pipeline.write", bind=True, max_retries=3, default_retry_delay=15)
def write_task(self, evidence_id: str | None) -> str | None:
    if evidence_id is None:
        return None
    return _guarded(step_write, evidence_id)


@celery_app.task(name="pipeline.enrich", bind=True, max_retries=1)
def enrich_task(self, evidence_id: str | None) -> str | None:
    if evidence_id is None:
        return None
    return _guarded(step_enrich, evidence_id)


def run_pipeline(evidence_id: str) -> None:
    chain(
        parse_task.s(evidence_id),
        extract_task.s(),
        resolve_task.s(),
        write_task.s(),
        enrich_task.s(),
    ).apply_async()
