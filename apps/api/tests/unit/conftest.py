from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from graph_explorer_api.dependencies import get_clients, get_jobs, get_registry, get_search_index, get_settings
from graph_explorer_api.graph_registry import GraphRegistry
from graph_explorer_api.main import create_app
from graph_explorer_api.search.index import SearchIndex

from tests.unit.fakes import FakeGraphClientCache, SyncImportJobRunner


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # The app's own lifespan calls load_settings() from the environment on
    # startup; pointing it at tmp_path too keeps that real (but otherwise
    # unused, since get_settings is overridden below) Settings instance from
    # touching anything outside the test's tmp dir.
    monkeypatch.setenv("GRAPH_EXPLORER_DATA_DIR", str(tmp_path))
    from graph_explorer_api.config import load_settings

    return load_settings()


@pytest.fixture
def client(settings):
    app = create_app()
    registry = GraphRegistry(settings.registry_path)
    clients = FakeGraphClientCache()
    jobs = SyncImportJobRunner()
    search_index = SearchIndex()

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_clients] = lambda: clients
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_search_index] = lambda: search_index

    with TestClient(app) as test_client:
        yield test_client
