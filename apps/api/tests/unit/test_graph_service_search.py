"""Search must not offer the matching index as if it were entities."""

from __future__ import annotations

from graph_explorer_api.services.graph_service import GraphService

from tests.unit.fakes import FakeGraphClientCache

SPACE = "test_space"


def make_service(vertices) -> GraphService:
    clients = FakeGraphClientCache()
    store = clients.for_space(SPACE).store
    store.vertices.update(vertices)
    # list_tags() reads the registered schema, not the stored rows.
    for tags in vertices.values():
        for tag in tags:
            store.tags.setdefault(tag, object())
    return GraphService(clients, SPACE)


def test_search_finds_a_person_by_label():
    service = make_service(
        {"a": {"person": {"label": "Amina Rahman", "entity_type": "Person"}}}
    )
    assert [hit["entity_id"] for hit in service.search_entities("amina")] == ["a"]


def test_search_never_returns_field_value_vertices():
    """`field_value` holds one vertex per indexed value. Returning them would
    offer "dubai" as a searchable entity — and, because the tag carries no
    index, scanning it fails outright."""
    service = make_service(
        {
            "a": {"person": {"label": "Amina Rahman", "entity_type": "Person"}},
            "value:1": {"field_value": {"label": "dubai", "entity_type": "field_value"}},
        }
    )
    hits = service.search_entities("dubai")
    assert hits == []


def test_searching_a_person_is_unaffected_by_the_index_being_present():
    service = make_service(
        {
            "a": {"person": {"label": "Rami Aziz", "entity_type": "Person"}},
            "value:1": {"field_value": {"label": "rami aziz", "entity_type": "field_value"}},
        }
    )
    assert [hit["entity_id"] for hit in service.search_entities("rami")] == ["a"]
