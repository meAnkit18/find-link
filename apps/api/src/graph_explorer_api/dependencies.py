"""FastAPI dependency providers, reading shared state off `app.state`.

Kept as plain functions (not a DI container) — app.state is populated once
at startup in main.py's lifespan handler; these just narrow the type for
route handlers and centralize the 404-on-unknown-graph check.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from graph_explorer_api.config import Settings
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.graph_registry import Graph, GraphRegistry
from graph_explorer_api.ingest.jobs import ImportJobRunner
from graph_explorer_api.search.index import SearchIndex
from graph_explorer_api.services.graph_service import GraphService
from graph_explorer_api.services.investigation_service import InvestigationService
from graph_explorer_api.services.person_network_service import PersonNetworkService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_registry(request: Request) -> GraphRegistry:
    return request.app.state.registry


def get_clients(request: Request) -> GraphClientCache:
    return request.app.state.clients


def get_search_index(request: Request) -> SearchIndex:
    return request.app.state.search_index


def get_jobs(request: Request) -> ImportJobRunner:
    return request.app.state.jobs


def get_graph_service(request: Request) -> GraphService:
    return request.app.state.graph_service


def get_investigation_service(request: Request) -> InvestigationService:
    return request.app.state.investigation_service


def get_person_network_service(request: Request) -> PersonNetworkService:
    service = getattr(request.app.state, "person_network_service", None)
    if service is None:
        # Startup couldn't reach the intelligence space (see main.py's
        # lifespan) — say so instead of failing with AttributeError.
        raise HTTPException(
            status_code=503,
            detail="Intelligence graph unavailable — is NebulaGraph running?",
        )
    return service


def get_graph_or_404(graph_id: str, registry: GraphRegistry) -> Graph:
    graph = registry.get(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Graph {graph_id!r} not found")
    return graph
