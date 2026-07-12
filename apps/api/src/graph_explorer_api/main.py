"""FastAPI app: wires settings, GraphClient cache, job runner, and search
index onto app.state, and mounts the graphs/imports/explorer routers.

Route handlers are regular `def` functions, not `async def` — graph-core is
synchronous, and FastAPI runs sync handlers in its worker thread pool
automatically, so no async wrapping is needed anywhere in this app.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from graph_explorer_api.config import load_settings
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.graph_registry import GraphRegistry
from graph_explorer_api.ingest.jobs import ImportJobRunner
from graph_explorer_api.routers import (
    agent_tools,
    entities,
    explorer,
    graphs,
    imports,
    ingestion,
    investigations,
    review,
    risk,
)
from graph_explorer_api.search.index import SearchIndex
from graph_explorer_api.services.graph_service import GraphService
from graph_explorer_api.services.investigation_service import InvestigationService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.state.settings = settings
    app.state.registry = GraphRegistry(settings.registry_path)
    app.state.clients = GraphClientCache(settings)
    app.state.jobs = ImportJobRunner()
    app.state.search_index = SearchIndex()

    default_client = app.state.clients.for_space("intelligence_graph")
    app.state.graph_service = GraphService(default_client)
    app.state.investigation_service = InvestigationService(default_client)

    try:
        yield
    finally:
        app.state.clients.close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="Graph Explorer API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(graphs.router)
    app.include_router(imports.router)
    app.include_router(explorer.router)
    app.include_router(entities.router)
    app.include_router(investigations.router)
    app.include_router(ingestion.router)
    app.include_router(risk.router)
    app.include_router(review.router)
    app.include_router(agent_tools.router)
    return app


app = create_app()
