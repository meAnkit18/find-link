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
from graph_explorer_api.imports.jobs import ImportJobRunner
from graph_explorer_api.search.index import SearchIndex


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_registry(request: Request) -> GraphRegistry:
    return request.app.state.registry


def get_clients(request: Request) -> GraphClientCache:
    return request.app.state.clients


def get_jobs(request: Request) -> ImportJobRunner:
    return request.app.state.jobs


def get_search_index(request: Request) -> SearchIndex:
    return request.app.state.search_index


def get_graph_or_404(graph_id: str, registry: GraphRegistry) -> Graph:
    graph = registry.get(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Graph {graph_id!r} not found")
    return graph
