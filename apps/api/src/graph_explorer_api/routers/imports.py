"""CSV upload -> background import job."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from graph_explorer_api.dependencies import (
    get_clients,
    get_graph_or_404,
    get_jobs,
    get_registry,
    get_search_index,
    get_settings,
)
from graph_explorer_api.config import Settings
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.graph_registry import GraphRegistry
from graph_explorer_api.ingest.report import ImportReport
from graph_explorer_api.ingest.jobs import ImportJob, ImportJobRunner
from graph_explorer_api.search.index import SearchIndex

router = APIRouter(prefix="/api/graphs/{graph_id}/imports", tags=["imports"])


class ImportReportOut(BaseModel):
    filename: str
    structure_kind: str
    tag: str | None
    edge_type: str | None
    rows_read: int
    vertices_created: int
    edges_created: int
    duplicates_skipped: int
    validation_errors: list[str]
    elapsed_seconds: float

    @classmethod
    def from_report(cls, report: ImportReport) -> "ImportReportOut":
        return cls(**report.__dict__)


class ImportJobOut(BaseModel):
    job_id: str
    graph_id: str
    filename: str
    status: str
    report: ImportReportOut | None
    error: str | None

    @classmethod
    def from_job(cls, job: ImportJob) -> "ImportJobOut":
        return cls(
            job_id=job.id,
            graph_id=job.graph_id,
            filename=job.filename,
            status=job.status,
            report=ImportReportOut.from_report(job.report) if job.report else None,
            error=job.error,
        )


@router.post("", response_model=ImportJobOut, status_code=202)
def start_import(
    graph_id: str,
    file: UploadFile,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
    jobs: ImportJobRunner = Depends(get_jobs),
    search_index: SearchIndex = Depends(get_search_index),
    settings: Settings = Depends(get_settings),
) -> ImportJobOut:
    graph = get_graph_or_404(graph_id, registry)
    if not file.filename:
        raise HTTPException(status_code=422, detail="file must have a filename")

    dest = settings.uploads_dir / f"{graph_id}_{uuid.uuid4().hex[:8]}_{file.filename}"
    with open(dest, "wb") as out:
        out.write(file.file.read())

    client = clients.for_space(graph.space)

    def on_complete(report: ImportReport) -> None:
        registry.add_stats(graph_id, report.vertices_created, report.edges_created)
        search_index.invalidate(graph_id)

    job = jobs.start(graph_id, file.filename, dest, client, on_complete=on_complete)
    return ImportJobOut.from_job(job)


@router.get("/{job_id}", response_model=ImportJobOut)
def get_import_job(
    graph_id: str,
    job_id: str,
    registry: GraphRegistry = Depends(get_registry),
    jobs: ImportJobRunner = Depends(get_jobs),
) -> ImportJobOut:
    get_graph_or_404(graph_id, registry)
    job = jobs.get(job_id)
    if job is None or job.graph_id != graph_id:
        raise HTTPException(status_code=404, detail=f"Import job {job_id!r} not found")
    return ImportJobOut.from_job(job)
