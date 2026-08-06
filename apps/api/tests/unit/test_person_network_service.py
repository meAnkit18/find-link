"""Person-projection tests.

These exercise the projection logic against the in-memory fake store —
whether NebulaGraph itself honors the traversal contract is graph-core's
problem, not this service's.
"""

from __future__ import annotations

import pytest

from graph_explorer_api.services.person_network_service import PersonNetworkService

from tests.unit.fakes import FakeGraphClientCache

SPACE = "test_space"


def person(label: str) -> dict:
    return {"person": {"label": label, "entity_type": "Person"}}


def thing(tag: str, label: str) -> dict:
    return {tag: {"label": label, "entity_type": tag.title()}}


def make_service(vertices, edges, edge_types=None) -> PersonNetworkService:
    """edges: (src, dst, edge_type[, props]) tuples, rank always 0."""
    clients = FakeGraphClientCache()
    client = clients.for_space(SPACE)
    client.store.vertices.update(vertices)
    for edge in edges:
        src, dst, edge_type = edge[0], edge[1], edge[2]
        props = edge[3] if len(edge) > 3 else {}
        client.store.edges.append((src, dst, edge_type, 0, props))
    for name in edge_types if edge_types is not None else {e[2] for e in edges}:
        client.store.edge_types[name] = object()
    return PersonNetworkService(clients, SPACE)


def ids(network) -> list[str]:
    return [p["id"] for p in network["persons"]]


def degrees(network) -> dict[str, int]:
    return {p["id"]: p["degree"] for p in network["persons"]}


def link_pairs(network) -> set[tuple[str, str]]:
    return {(link["source"], link["target"]) for link in network["links"]}


# --------------------------------------------------------------- fixtures


@pytest.fixture
def shared_phone():
    """A and B share one phone; nothing else."""
    return make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "phone:1": thing("phone", "+91-111"),
        },
        [("a", "phone:1", "HAS_PHONE"), ("b", "phone:1", "HAS_PHONE")],
    )


@pytest.fixture
def chain():
    """A-B share a phone, B-C an email, C-D an address: a 3-degree chain."""
    return make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "d": person("Dan"),
            "phone:1": thing("phone", "+91-111"),
            "email:1": thing("email", "b@example.com"),
            "address:1": thing("address", "12 Main St"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("b", "phone:1", "HAS_PHONE"),
            ("b", "email:1", "HAS_EMAIL"),
            ("c", "email:1", "HAS_EMAIL"),
            ("c", "address:1", "LOCATED_AT"),
            ("d", "address:1", "LOCATED_AT"),
        ],
    )


# ------------------------------------------------------------------ degree


def test_degree_one_finds_the_person_sharing_an_attribute(shared_phone):
    network = shared_phone.person_network("a", degree=1)
    assert ids(network) == ["a", "b"]
    assert degrees(network) == {"a": 0, "b": 1}
    assert link_pairs(network) == {("a", "b")}


def test_degree_one_link_carries_the_shared_attribute_as_its_reason(shared_phone):
    link = shared_phone.person_network("a", degree=1)["links"][0]
    assert link["label"] == "shared phone"
    assert link["via"] == [
        {
            "kind": "shared_attribute",
            "connector_id": "phone:1",
            "connector_tag": "phone",
            "connector_label": "+91-111",
            "edge_types": ["HAS_PHONE"],
        }
    ]


def test_degree_one_stops_at_one_connection(chain):
    assert ids(chain.person_network("a", degree=1)) == ["a", "b"]


def test_degree_two_reaches_the_second_link_in_the_chain(chain):
    network = chain.person_network("a", degree=2)
    assert degrees(network) == {"a": 0, "b": 1, "c": 2}
    assert link_pairs(network) == {("a", "b"), ("b", "c")}


def test_degree_three_reaches_the_third_link_and_is_additive(chain):
    network = chain.person_network("a", degree=3)
    assert degrees(network) == {"a": 0, "b": 1, "c": 2, "d": 3}
    assert link_pairs(network) == {("a", "b"), ("b", "c"), ("c", "d")}


def test_degree_is_capped_at_three(chain):
    assert chain.person_network("a", degree=9)["degree"] == 3


def test_degree_below_one_is_raised_to_one(shared_phone):
    assert shared_phone.person_network("a", degree=0)["degree"] == 1


# ------------------------------------------------------------ link shapes


def test_direct_person_to_person_edge_is_a_degree_one_link():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob")},
        [("a", "b", "RELATED_TO", {"relationship_type": "childhood friend"})],
    )
    link = service.person_network("a", degree=1)["links"][0]
    assert link["label"] == "childhood friend"
    assert link["via"][0]["kind"] == "direct"


def test_direct_edge_without_a_label_falls_back_to_the_edge_type():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob")},
        [("a", "b", "RELATED_TO")],
    )
    assert service.person_network("a", degree=1)["links"][0]["label"] == "related to"


def test_direct_edge_to_a_non_person_is_not_a_link():
    service = make_service(
        {"a": person("Alice"), "acme": thing("company", "Acme")},
        [("a", "acme", "RELATED_TO")],
    )
    network = service.person_network("a", degree=1)
    assert ids(network) == ["a"]
    assert network["links"] == []


def test_two_shared_attributes_between_the_same_pair_merge_into_one_link():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "phone:1": thing("phone", "+91-111"),
            "email:1": thing("email", "shared@example.com"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("b", "phone:1", "HAS_PHONE"),
            ("a", "email:1", "HAS_EMAIL"),
            ("b", "email:1", "HAS_EMAIL"),
        ],
    )
    links = service.person_network("a", degree=1)["links"]
    assert len(links) == 1
    assert links[0]["label"] == "2 shared details"
    assert {v["connector_tag"] for v in links[0]["via"]} == {"phone", "email"}


def test_one_connector_shared_by_three_people_closes_the_triangle():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "phone:1": thing("phone", "+91-111"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("b", "phone:1", "HAS_PHONE"),
            ("c", "phone:1", "HAS_PHONE"),
        ],
    )
    network = service.person_network("a", degree=1)
    assert link_pairs(network) == {("a", "b"), ("a", "c"), ("b", "c")}
    assert degrees(network) == {"a": 0, "b": 1, "c": 1}


def test_an_attribute_belonging_to_only_one_person_links_nobody():
    service = make_service(
        {"a": person("Alice"), "phone:1": thing("phone", "+91-111")},
        [("a", "phone:1", "HAS_PHONE")],
    )
    network = service.person_network("a", degree=1)
    assert ids(network) == ["a"]
    assert network["links"] == []


def test_a_shared_employer_connects_two_people():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob"), "acme": thing("company", "Acme")},
        [("a", "acme", "WORKS_AT"), ("b", "acme", "WORKS_AT")],
    )
    network = service.person_network("a", degree=1)
    assert link_pairs(network) == {("a", "b")}
    assert network["links"][0]["label"] == "shared company"
    # the company itself is a reason, never a node on the person canvas
    assert "acme" not in ids(network)


# --------------------------------------------------------------- guardrails


def test_a_high_fanout_connector_is_suppressed_not_expanded():
    people = {f"p{i}": person(f"P{i}") for i in range(6)}
    service = make_service(
        {**people, "phone:1": thing("phone", "+91-111")},
        [(f"p{i}", "phone:1", "HAS_PHONE") for i in range(6)],
    )
    network = service.person_network("p0", degree=1, max_fanout=3)
    assert network["links"] == []
    assert ids(network) == ["p0"]
    assert network["suppressed_hubs"] == [
        {"id": "phone:1", "label": "+91-111", "tag": "phone", "person_count": 6}
    ]


def test_a_connector_at_exactly_the_fanout_limit_still_links():
    people = {f"p{i}": person(f"P{i}") for i in range(3)}
    service = make_service(
        {**people, "phone:1": thing("phone", "+91-111")},
        [(f"p{i}", "phone:1", "HAS_PHONE") for i in range(3)],
    )
    network = service.person_network("p0", degree=1, max_fanout=3)
    assert network["suppressed_hubs"] == []
    assert len(network["links"]) == 3


def test_max_persons_truncates_and_says_so():
    people = {f"p{i}": person(f"P{i}") for i in range(6)}
    service = make_service(
        {**people, "phone:1": thing("phone", "+91-111")},
        [(f"p{i}", "phone:1", "HAS_PHONE") for i in range(6)],
    )
    network = service.person_network("p0", degree=1, max_persons=3)
    assert network["truncated"] is True
    assert len(network["persons"]) == 3
    # no link may dangle onto a person that was cut
    kept = set(ids(network))
    for link in network["links"]:
        assert link["source"] in kept and link["target"] in kept


def test_country_is_not_a_connector_by_default():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob"), "country:IN": thing("country", "India")},
        [("a", "country:IN", "CITIZEN_OF"), ("b", "country:IN", "CITIZEN_OF")],
    )
    assert service.person_network("a", degree=1)["links"] == []


def test_country_can_be_opted_into_explicitly():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob"), "country:IN": thing("country", "India")},
        [("a", "country:IN", "CITIZEN_OF"), ("b", "country:IN", "CITIZEN_OF")],
    )
    network = service.person_network("a", degree=1, connectors=["CITIZEN_OF"])
    assert link_pairs(network) == {("a", "b")}


def test_edge_types_absent_from_the_space_are_never_queried(shared_phone):
    # HAS_PHONE exists in the store's edge list; drop it and the projection
    # must come back empty instead of erroring on an unknown edge type.
    shared_phone.client.store.edge_types.clear()
    shared_phone.client.store.edge_types["RELATED_TO"] = object()
    network = shared_phone.person_network("a", degree=1)
    assert network["connectors"] == {"direct": ["RELATED_TO"], "shared": []}
    assert network["links"] == []


def test_a_cycle_does_not_loop_forever_or_duplicate():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "phone:1": thing("phone", "+91-111"),
            "email:1": thing("email", "b@example.com"),
            "address:1": thing("address", "12 Main St"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("b", "phone:1", "HAS_PHONE"),
            ("b", "email:1", "HAS_EMAIL"),
            ("c", "email:1", "HAS_EMAIL"),
            ("c", "address:1", "LOCATED_AT"),
            ("a", "address:1", "LOCATED_AT"),
        ],
    )
    network = service.person_network("a", degree=3)
    assert degrees(network) == {"a": 0, "b": 1, "c": 1}
    assert link_pairs(network) == {("a", "b"), ("a", "c"), ("b", "c")}


# -------------------------------------------------------------------- root


def test_missing_root_returns_none(shared_phone):
    assert shared_phone.person_network("nobody", degree=1) is None


def test_non_person_root_returns_none(shared_phone):
    assert shared_phone.person_network("phone:1", degree=1) is None


def test_isolated_person_returns_just_themselves():
    service = make_service({"a": person("Alice")}, [])
    network = service.person_network("a", degree=3)
    assert ids(network) == ["a"]
    assert network["links"] == []
    assert network["truncated"] is False


# -------------------------------------------------------------- attributes


def test_attributes_lists_a_persons_own_details(shared_phone):
    result = shared_phone.attributes("a")
    assert result["entity_id"] == "a"
    assert result["attributes"] == [
        {
            "id": "phone:1",
            "tag": "phone",
            "label": "+91-111",
            "edge_type": "HAS_PHONE",
            "properties": {"label": "+91-111", "entity_type": "Phone"},
            "shared_with": ["b"],
        }
    ]


def test_attributes_excludes_other_people():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob"), "phone:1": thing("phone", "+91-111")},
        [("a", "b", "RELATED_TO"), ("a", "phone:1", "HAS_PHONE")],
    )
    assert [a["id"] for a in service.attributes("a")["attributes"]] == ["phone:1"]


def test_attributes_of_a_person_with_none_is_empty():
    service = make_service({"a": person("Alice")}, [])
    assert service.attributes("a")["attributes"] == []


def test_attributes_are_sorted_stably():
    service = make_service(
        {
            "a": person("Alice"),
            "phone:1": thing("phone", "+91-111"),
            "email:1": thing("email", "a@example.com"),
            "address:1": thing("address", "12 Main St"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("a", "email:1", "HAS_EMAIL"),
            ("a", "address:1", "LOCATED_AT"),
        ],
    )
    tags = [a["tag"] for a in service.attributes("a")["attributes"]]
    assert tags == ["address", "email", "phone"]
