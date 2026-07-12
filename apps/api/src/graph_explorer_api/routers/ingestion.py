from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from graph_explorer_api.dependencies import get_graph_service
from graph_explorer_api.services.graph_service import GraphService
from graph_explorer_api.services.ingestion_service import EntityWriter

router = APIRouter(prefix="/api/imports", tags=["ingestion"])


@router.post("/csv")
def import_csv(
    file_path: str,
    source_name: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    from graph_explorer_api.repositories.search_gateway import SearchGateway
    from ingestion_core.service import IngestionService

    gateway = SearchGateway(graph_service.client)
    writer = EntityWriter(graph_service)

    from entity_resolution.resolver import EntityResolver

    resolver = EntityResolver(gateway)
    ingestion_service = IngestionService(resolver=resolver, writer=writer)
    return ingestion_service.ingest_csv(file_path, source_name)


@router.get("/{job_id}")
def get_import_job(
    job_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    result = graph_service.client.execute_raw(
        f'FETCH PROP ON background_job "{job_id}" YIELD VERTEX AS v'
    )
    if not result.rows:
        raise HTTPException(status_code=404, detail="Job not found")
    return result.rows[0]
