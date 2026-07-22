"""FastAPI app: wires settings, GraphClient cache, job runner, and search
index onto app.state, and mounts the routers.

Route handlers are regular `def` functions, not `async def` --- graph-core is
synchronous, and FastAPI runs sync handlers in its worker thread pool
automatically, so no async wrapping is needed anywhere in this app.
"""

from __future__ import annotations

import datetime
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env BEFORE any project import so that environment variables (notably
# EVIDENCE_DATABASE_URL) are available when SQLAlchemy builds its engine at
# module level in evidence_core.database.  Also load the repo-root .env
# explicitly so it works no matter which directory uvicorn is started from.
_dotenv_path = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=_dotenv_path, override=True)
load_dotenv(override=True)
from evidence_core.database import SessionLocal, init_db as init_evidence_db  # noqa: E402, I001
from evidence_core.db_models import Evidence  # noqa: E402, I001

from graph_explorer_api.config import load_settings  # noqa: E402, I001
from graph_explorer_api.graph_clients import GraphClientCache  # noqa: E402, I001
from graph_explorer_api.graph_registry import GraphRegistry  # noqa: E402, I001
from graph_explorer_api.routers import (  # noqa: E402, I001
    agent_tools,
    entities,
    evidence,
    explorer,
    graphs,
    investigations,
    review,
    risk,
)
from graph_explorer_api.search.index import SearchIndex  # noqa: E402, I001
from graph_explorer_api.services.graph_service import GraphService  # noqa: E402, I001
from graph_explorer_api.services.investigation_service import InvestigationService  # noqa: E402, I001

logger = logging.getLogger(__name__)

INTEL_GRAPH_NAME = "Intelligence Graph"


def _sweep_abandoned() -> None:
    """Mark evidence rows that were mid-flight when the API last stopped as
    failed, so the UI doesn't show them spinning forever."""
    init_evidence_db()
    db = SessionLocal()
    try:
        active_stati = {"uploaded", "queued", "parsed", "extracted", "resolved", "written"}
        abandoned = db.query(Evidence).filter(Evidence.status.in_(active_stati)).all()
        for ev in abandoned:
            stage = ev.status or "unknown"
            ev.status = "failed"
            ev.error = f"{stage}: interrupted by an API restart — press Retry"
            log_entry = {
                "stage": stage,
                "at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "detail": "interrupted by an API restart — press Retry",
            }
            log = list(ev.processing_log or [])
            log.append(log_entry)
            ev.processing_log = log
            db.add(ev)
        if abandoned:
            logger.info(
                "swept %d abandoned evidence row(s) to 'failed' after restart",
                len(abandoned),
            )
        db.commit()
    except Exception:
        logger.exception("error sweeping abandoned evidence rows")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _sweep_abandoned()

    settings = load_settings()
    app.state.settings = settings
    app.state.registry = GraphRegistry(settings.registry_path)
    app.state.clients = GraphClientCache(settings)
    app.state.search_index = SearchIndex()
    app.state.graph_service = None
    app.state.investigation_service = None

    init_evidence_db()

    space = settings.nebula_space
    try:
        from intelligence_schema.ingest_schema import ensure_ingest_schema

        client = app.state.clients.for_space(space)
        ensure_ingest_schema(client, space)
        app.state.registry.ensure(space, INTEL_GRAPH_NAME)
        app.state.graph_service = GraphService(client)
        app.state.investigation_service = InvestigationService(client)
        logger.info("intelligence space '%s' ready; ingest schema ensured", space)
    except Exception:
        logger.exception(
            "could not prepare intelligence space '%s' at startup "
            "(is NebulaGraph up? see docker compose ps)", space,
        )

    try:
        yield
    finally:
        app.state.clients.close_all()


def create_app() -> FastAPI:
    app = FastAPI(title="Graph Explorer API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(graphs.router)
    app.include_router(explorer.router)
    app.include_router(entities.router)
    app.include_router(investigations.router)
    app.include_router(evidence.router)
    app.include_router(risk.router)
    app.include_router(review.router)
    app.include_router(agent_tools.router)
    return app


app = create_app()
