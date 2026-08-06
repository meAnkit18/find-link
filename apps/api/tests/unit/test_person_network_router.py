from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from graph_explorer_api.dependencies import get_person_network_service
from graph_explorer_api.main import create_app
from graph_explorer_api.services.person_network_service import PersonNetworkService

from tests.unit.fakes import FakeGraphClientCache

SPACE = "test_space"


@pytest.fixture
def service():
    clients = FakeGraphClientCache()
    store = clients.for_space(SPACE).store
    store.vertices.update(
        {
            "a": {"person": {"label": "Alice", "entity_type": "Person"}},
            "b": {"person": {"label": "Bob", "entity_type": "Person"}},
            "phone:1": {"phone": {"label": "+91-111", "entity_type": "Phone"}},
        }
    )
    store.edges.extend(
        [
            ("a", "phone:1", "HAS_PHONE", 0, {}),
            ("b", "phone:1", "HAS_PHONE", 0, {}),
        ]
    )
    store.edge_types["HAS_PHONE"] = object()
    return PersonNetworkService(clients, SPACE)


@pytest.fixture
def api(service):
    app = create_app()
    app.dependency_overrides[get_person_network_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def test_person_network_returns_the_projection(api):
    response = api.get("/api/entities/a/person-network?degree=1")
    assert response.status_code == 200
    body = response.json()
    assert [p["id"] for p in body["persons"]] == ["a", "b"]
    assert body["links"][0]["label"] == "shared phone"


def test_person_network_404s_on_an_unknown_person(api):
    assert api.get("/api/entities/nobody/person-network").status_code == 404


def test_person_network_404s_on_a_non_person(api):
    assert api.get("/api/entities/phone:1/person-network").status_code == 404


def test_person_network_rejects_a_degree_above_three(api):
    assert api.get("/api/entities/a/person-network?degree=4").status_code == 422


def test_person_network_defaults_to_degree_one(api):
    assert api.get("/api/entities/a/person-network").json()["degree"] == 1


def test_person_network_accepts_an_explicit_connector_list(api):
    body = api.get("/api/entities/a/person-network?connectors=RELATED_TO").json()
    assert body["links"] == []


def test_attributes_endpoint_returns_shared_details(api):
    body = api.get("/api/entities/a/attributes").json()
    assert body["attributes"][0]["id"] == "phone:1"
    assert body["attributes"][0]["shared_with"] == ["b"]


def test_endpoints_503_when_the_intelligence_graph_is_unavailable():
    """Startup couldn't reach NebulaGraph, so the service was never built.

    The unavailability is forced rather than assumed: relying on the
    lifespan failing makes this pass only on machines with no NebulaGraph
    running, and fail on any machine that has one.
    """
    app = create_app()
    with TestClient(app) as unwired:
        app.state.person_network_service = None
        assert unwired.get("/api/entities/a/person-network").status_code == 503


def test_shortest_path_is_not_shadowed_by_the_entity_id_route(service):
    """`/shortest-path` reads as an entity id, so declared after
    `/{entity_id}` it resolves to get_entity and never runs."""
    from graph_explorer_api.dependencies import get_graph_service

    reached = []

    class SpyGraphService:
        def shortest_path(self, source, target, max_steps=5):
            reached.append((source, target))
            return {"paths": []}

        def get_entity(self, entity_id):
            return {"vid": entity_id}

    app = create_app()
    app.dependency_overrides[get_graph_service] = SpyGraphService
    with TestClient(app) as client:
        response = client.get(
            "/api/entities/shortest-path", params={"source": "a", "target": "b"}
        )

    assert response.status_code == 200
    assert reached == [("a", "b")]
