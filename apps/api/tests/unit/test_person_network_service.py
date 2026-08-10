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
            # weight_for("phone") == 0.8, rarity(2) == 1.0
            "confidence": pytest.approx(0.8),
        }
    ]
    assert link["confidence"] == pytest.approx(0.8)


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
    assert links[0]["label"] == "2 connections"
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


# ------------------------------------------------- linked organisations
# Modelled on the real intel_kg_v2 data: Priya works at Meridian, Arjun at
# Nimbus, and Nimbus pays Meridian. They share nothing at all, yet they are
# plainly connected.


@pytest.fixture
def linked_employers():
    return make_service(
        {
            "p:priya": person("Priya Sharma"),
            "p:arjun": person("Arjun Mehta"),
            "co:meridian": thing("company", "Meridian Exports LLP"),
            "co:nimbus": thing("company", "Nimbus Trade Solutions Pvt Ltd"),
        },
        [
            ("p:priya", "co:meridian", "WORKS_AT"),
            ("p:arjun", "co:nimbus", "WORKS_AT"),
            ("co:nimbus", "co:meridian", "PAYS"),
        ],
    )


def test_people_at_companies_that_pay_each_other_are_connected(linked_employers):
    network = linked_employers.person_network("p:priya", degree=1)
    assert degrees(network) == {"p:priya": 0, "p:arjun": 1}
    assert link_pairs(network) == {("p:arjun", "p:priya")}


def test_a_linked_employer_link_reads_in_the_stored_direction(linked_employers):
    link = linked_employers.person_network("p:priya", degree=1)["links"][0]
    assert link["label"] == "Nimbus Trade Solutions Pvt Ltd pays Meridian Exports LLP"
    via = link["via"][0]
    assert via["kind"] == "linked_organisation"
    assert via["edge_types"] == ["PAYS"]
    assert {via["connector_label"], via["linked_label"]} == {
        "Meridian Exports LLP",
        "Nimbus Trade Solutions Pvt Ltd",
    }


def test_neither_company_becomes_a_node(linked_employers):
    assert ids(linked_employers.person_network("p:priya", degree=1)) == [
        "p:priya",
        "p:arjun",
    ]


def test_unrelated_companies_do_not_connect_their_staff():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "co:1": thing("company", "Acme"),
            "co:2": thing("company", "Globex"),
        },
        [("a", "co:1", "WORKS_AT"), ("b", "co:2", "WORKS_AT")],
    )
    assert service.person_network("a", degree=1)["links"] == []


def test_a_shared_employer_still_reads_as_shared_not_bridged():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob"), "co:1": thing("company", "Acme")},
        [("a", "co:1", "WORKS_AT"), ("b", "co:1", "WORKS_AT")],
    )
    link = service.person_network("a", degree=1)["links"][0]
    assert link["label"] == "shared company"
    assert link["via"][0]["kind"] == "shared_attribute"


def test_only_organisations_bridge_not_phones():
    # Two phones joined by RELATED_TO must not connect their owners — the
    # bridge is deliberately restricted to organisation-like connectors.
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "phone:1": thing("phone", "+91-111"),
            "phone:2": thing("phone", "+91-222"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("b", "phone:2", "HAS_PHONE"),
            ("phone:1", "phone:2", "RELATED_TO"),
        ],
    )
    assert service.person_network("a", degree=1)["links"] == []


def test_a_hub_employer_does_not_bridge_everyone_to_everyone():
    staff = {f"p{i}": person(f"P{i}") for i in range(6)}
    service = make_service(
        {**staff, "co:big": thing("company", "BigCorp"), "co:small": thing("company", "SmallCo")},
        [
            *[(f"p{i}", "co:big", "WORKS_AT") for i in range(5)],
            ("p5", "co:small", "WORKS_AT"),
            ("co:big", "co:small", "PAYS"),
        ],
    )
    network = service.person_network("p5", degree=1, max_fanout=3)
    assert all(via["kind"] != "linked_organisation" for link in network["links"] for via in link["via"])


def test_a_bridge_rediscovered_from_the_far_side_is_not_counted_twice(linked_employers):
    """Level 2 walks Arjun->Nimbus->Meridian->Priya, the same bridge level 1
    walked the other way. One reason, not two."""
    for requested in (2, 3):
        link = linked_employers.person_network("p:priya", degree=requested)["links"][0]
        assert len(link["via"]) == 1
        assert link["label"] == "Nimbus Trade Solutions Pvt Ltd pays Meridian Exports LLP"


def test_bridged_people_extend_to_the_next_degree():
    service = make_service(
        {
            "p:priya": person("Priya"),
            "p:arjun": person("Arjun"),
            "p:kiran": person("Kiran"),
            "co:meridian": thing("company", "Meridian"),
            "co:nimbus": thing("company", "Nimbus"),
            "phone:1": thing("phone", "+91-111"),
        },
        [
            ("p:priya", "co:meridian", "WORKS_AT"),
            ("p:arjun", "co:nimbus", "WORKS_AT"),
            ("co:nimbus", "co:meridian", "PAYS"),
            ("p:arjun", "phone:1", "HAS_PHONE"),
            ("p:kiran", "phone:1", "HAS_PHONE"),
        ],
    )
    network = service.person_network("p:priya", degree=2)
    assert degrees(network) == {"p:priya": 0, "p:arjun": 1, "p:kiran": 2}


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
    assert network["connectors"] == {
        "direct": ["RELATED_TO"],
        "shared": [],
        "bridge": ["RELATED_TO"],
    }
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


def test_attributes_lists_a_persons_own_details():
    """Expanding a person shows their documents — a phone is still ingested
    and still forms links, but it is not what a person opens into."""
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "doc:1": thing("document", "P1234567"),
            "phone:1": thing("phone", "+91-111"),
        },
        [
            ("a", "doc:1", "HAS_DOCUMENT"),
            ("b", "doc:1", "HAS_DOCUMENT"),
            ("a", "phone:1", "HAS_PHONE"),
        ],
    )
    result = service.attributes("a")
    assert result["entity_id"] == "a"
    assert result["attributes"] == [
        {
            "id": "doc:1",
            "tag": "document",
            "label": "P1234567",
            "edge_type": "HAS_DOCUMENT",
            # `label` is dropped: it is already this attribute's title, so a
            # property row repeating it is noise. See _INTERNAL_PROPS.
            "properties": {"entity_type": "Document"},
            "shared_with": ["b"],
        }
    ]


def test_attributes_excludes_other_people():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob"), "doc:1": thing("document", "P1234567")},
        [("a", "b", "RELATED_TO"), ("a", "doc:1", "HAS_DOCUMENT")],
    )
    assert [a["id"] for a in service.attributes("a")["attributes"]] == ["doc:1"]


def test_attributes_of_a_person_with_none_is_empty():
    service = make_service({"a": person("Alice")}, [])
    assert service.attributes("a")["attributes"] == []


def test_attributes_are_sorted_stably():
    service = make_service(
        {
            "a": person("Alice"),
            "doc:pp": thing("document", "P1234567"),
            "doc:eid": thing("document", "784199012345671"),
            "doc:dl": thing("document", "DL-99"),
        },
        [
            ("a", "doc:pp", "HAS_DOCUMENT"),
            ("a", "doc:eid", "HAS_DOCUMENT"),
            ("a", "doc:dl", "HAS_DOCUMENT"),
        ],
    )
    labels = [a["label"] for a in service.attributes("a")["attributes"]]
    assert labels == ["784199012345671", "DL-99", "P1234567"]


# ------------------------------------------------------- property unpacking


def test_props_json_blob_is_unpacked_into_real_fields():
    """Entity attributes live in one JSON `props` string column, so without
    unpacking the panel would show an opaque blob instead of the fields."""
    service = make_service(
        {
            "a": {
                "person": {
                    "label": "Alice",
                    "entity_type": "Person",
                    "props": '{"nationality": "India", "dob": "1988-11-18"}',
                }
            }
        },
        [],
    )
    props = service.person_network("a", degree=1)["persons"][0]["properties"]
    assert props["nationality"] == "India"
    assert props["dob"] == "1988-11-18"
    assert "props" not in props


def test_storage_plumbing_is_hidden_from_properties():
    service = make_service(
        {
            "a": {
                "person": {
                    "label": "Alice",
                    "entity_type": "Person",
                    "props": '{"aliases": [], "nationality": "India"}',
                    "evidence_ids": '["ev-1"]',
                    "created_at": 1754500000,
                    "updated_at": 1754500000,
                }
            }
        },
        [],
    )
    props = service.person_network("a", degree=1)["persons"][0]["properties"]
    assert props == {"entity_type": "Person", "nationality": "India"}


def test_unparseable_props_does_not_break_the_payload():
    service = make_service(
        {"a": {"person": {"label": "Alice", "entity_type": "Person", "props": "not json"}}},
        [],
    )
    network = service.person_network("a", degree=1)
    assert network["persons"][0]["properties"] == {"entity_type": "Person"}


# --------------------------------------------------------- field matching


FIELD_VALUE = "HAS_FIELD_VALUE"


def value_node(value: str) -> dict:
    return {"field_value": {"label": value, "entity_type": "field_value"}}


@pytest.fixture
def shared_father_name():
    """A and B have separate passports naming the same father."""
    return make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "value:father": value_node("ahmed al-mansouri"),
        },
        [
            ("a", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
        ],
    )


def test_matching_field_links_two_people(shared_father_name):
    network = shared_father_name.person_network("a", degree=1)
    assert set(ids(network)) == {"a", "b"}
    assert link_pairs(network) == {("a", "b")}


def test_matching_field_link_reports_why(shared_father_name):
    network = shared_father_name.person_network("a", degree=1)
    via = network["links"][0]["via"][0]
    assert via["kind"] == "shared_field"
    assert via["field_key"] == "father_name"
    assert via["same_key"] is True
    assert via["connector_label"] == "ahmed al-mansouri"


def test_same_key_match_on_a_rare_value_is_confident(shared_father_name):
    network = shared_father_name.person_network("a", degree=1)
    # weight_for("father_name") == 0.7, rarity(2) == 1.0, same key
    assert network["links"][0]["confidence"] == pytest.approx(0.7)


def test_cross_key_match_is_penalised():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "value:x": value_node("12 main st"),
        },
        [
            ("a", "value:x", FIELD_VALUE, {"field_key": "address"}),
            ("b", "value:x", FIELD_VALUE, {"field_key": "employer_address"}),
        ],
    )
    network = service.person_network("a", degree=1)
    via = network["links"][0]["via"][0]
    assert via["same_key"] is False
    # 0.7 * 1.0 * 0.6
    assert network["links"][0]["confidence"] == pytest.approx(0.42)


def test_two_matching_fields_compound():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "value:father": value_node("ahmed"),
            "value:addr": value_node("12 main st"),
        },
        [
            ("a", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
            ("a", "value:addr", FIELD_VALUE, {"field_key": "address"}),
            ("b", "value:addr", FIELD_VALUE, {"field_key": "address"}),
        ],
    )
    network = service.person_network("a", degree=1)
    link = network["links"][0]
    assert len(link["via"]) == 2
    # noisy-OR of 0.7 and 0.7
    assert link["confidence"] == pytest.approx(0.91)


def test_a_value_shared_by_a_crowd_scores_low():
    people = {f"p{i}": person(f"P{i}") for i in range(6)}
    service = make_service(
        {**people, "value:x": value_node("dubai")},
        [(f"p{i}", "value:x", FIELD_VALUE, {"field_key": "city"}) for i in range(6)],
    )
    network = service.person_network("p0", degree=1)
    # rarity(6) == 0.2, default weight 0.5 -> 0.1
    assert network["links"][0]["confidence"] == pytest.approx(0.1)


def test_field_values_chain_into_second_degree():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "value:1": value_node("ahmed"),
            "value:2": value_node("12 main st"),
        },
        [
            ("a", "value:1", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:1", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:2", FIELD_VALUE, {"field_key": "address"}),
            ("c", "value:2", FIELD_VALUE, {"field_key": "address"}),
        ],
    )
    assert degrees(service.person_network("a", degree=2)) == {"a": 0, "b": 1, "c": 2}
    assert "c" not in ids(service.person_network("a", degree=1))


# ------------------------------------------------------- confidence filter


@pytest.fixture
def weak_then_strong():
    """A-B is a weak city match; B-C is a strong passport-number match."""
    people = {f"p{i}": person(f"P{i}") for i in range(6)}
    return make_service(
        {
            **people,
            "a": person("Alice"),
            "value:city": value_node("dubai"),
            "value:pp": value_node("p1234567"),
        },
        [
            ("a", "value:city", FIELD_VALUE, {"field_key": "city"}),
            *[(f"p{i}", "value:city", FIELD_VALUE, {"field_key": "city"}) for i in range(6)],
            ("p0", "value:pp", FIELD_VALUE, {"field_key": "passport_number"}),
        ],
    )


def test_weak_links_survive_a_zero_threshold(weak_then_strong):
    network = weak_then_strong.person_network("a", degree=1, min_confidence=0.0)
    assert ("a", "p0") in link_pairs(network)


def test_min_confidence_drops_weak_links(weak_then_strong):
    network = weak_then_strong.person_network("a", degree=1, min_confidence=0.5)
    assert link_pairs(network) == set()


def test_a_dropped_link_is_not_a_stepping_stone(weak_then_strong):
    """A confidence filter has to cut the path, not just hide one edge."""
    network = weak_then_strong.person_network("a", degree=2, min_confidence=0.5)
    assert ids(network) == ["a"]


def test_min_confidence_keeps_strong_links(shared_father_name):
    network = shared_father_name.person_network("a", degree=1, min_confidence=0.5)
    assert link_pairs(network) == {("a", "b")}


# ------------------------------------------------------- person expansion


@pytest.fixture
def person_with_everything():
    return make_service(
        {
            "a": person("Alice"),
            "doc:1": thing("document", "P1234567"),
            "phone:1": thing("phone", "+91-111"),
            "value:1": value_node("ahmed"),
        },
        [
            ("a", "doc:1", "HAS_DOCUMENT"),
            ("a", "phone:1", "HAS_PHONE"),
            ("a", "value:1", FIELD_VALUE, {"field_key": "father_name"}),
        ],
    )


def test_expanding_a_person_yields_only_documents(person_with_everything):
    result = person_with_everything.attributes("a")
    assert [a["tag"] for a in result["attributes"]] == ["document"]


def test_expanding_a_person_never_leaks_index_vertices(person_with_everything):
    """field_value vertices are an index, not something to draw."""
    result = person_with_everything.attributes("a")
    assert all(a["tag"] != "field_value" for a in result["attributes"])


def test_matching_field_names_the_source_documents():
    """A reason has to be auditable back to the document that stated it."""
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "value:father": value_node("ahmed"),
        },
        [
            ("a", "value:father", FIELD_VALUE,
             {"field_key": "father_name", "document_id": "doc:a"}),
            ("b", "value:father", FIELD_VALUE,
             {"field_key": "father_name", "document_id": "doc:b"}),
        ],
    )
    via = service.person_network("a", degree=1)["links"][0]["via"][0]
    assert via["document_ids"] == ["doc:a", "doc:b"]


# ------------------------------------------------------- connection finder


def test_find_connection_returns_the_direct_link(shared_phone):
    result = shared_phone.find_connection("a", "b")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "b"]
    assert len(result["path"]["links"]) == 1
    assert result["path"]["confidence"] == pytest.approx(0.8)


def test_find_connection_walks_a_multi_hop_chain(chain):
    result = chain.find_connection("a", "d")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "b", "c", "d"]
    assert len(result["path"]["links"]) == 3


def test_find_connection_reports_not_connected():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob")},
        [],
    )
    result = service.find_connection("a", "b")
    assert result == {
        "connected": False,
        "source_id": "a",
        "target_id": "b",
        "max_degree_searched": 4,
    }


def test_find_connection_looks_one_degree_past_the_exploration_cap():
    """A 4-hop chain is out of reach for person_network's own degree=3 cap,
    but find_connection's default of 4 should still find it."""
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "d": person("Dan"),
            "e": person("Eve"),
            "phone:1": thing("phone", "+91-111"),
            "phone:2": thing("phone", "+91-222"),
            "phone:3": thing("phone", "+91-333"),
            "phone:4": thing("phone", "+91-444"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("b", "phone:1", "HAS_PHONE"),
            ("b", "phone:2", "HAS_PHONE"),
            ("c", "phone:2", "HAS_PHONE"),
            ("c", "phone:3", "HAS_PHONE"),
            ("d", "phone:3", "HAS_PHONE"),
            ("d", "phone:4", "HAS_PHONE"),
            ("e", "phone:4", "HAS_PHONE"),
        ],
    )
    assert "e" not in {p["id"] for p in service.person_network("a", degree=3)["persons"]}
    result = service.find_connection("a", "e")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "b", "c", "d", "e"]


def test_find_connection_prefers_the_stronger_of_two_equal_length_routes():
    """a-b-target is a weak city match then a direct edge; a-c-target is a
    strong passport match then the same kind of direct edge. Both routes are
    2 hops; the stronger (passport) route should win."""
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "target": person("Target"),
            "value:city": value_node("dubai"),
            "value:pp": value_node("p1234567"),
        },
        [
            ("a", "value:city", FIELD_VALUE, {"field_key": "city"}),
            ("b", "value:city", FIELD_VALUE, {"field_key": "city"}),
            ("b", "target", "RELATED_TO"),
            ("a", "value:pp", FIELD_VALUE, {"field_key": "passport_number"}),
            ("c", "value:pp", FIELD_VALUE, {"field_key": "passport_number"}),
            ("c", "target", "RELATED_TO"),
        ],
    )
    result = service.find_connection("a", "target")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "c", "target"]


def test_find_connection_rejects_the_same_person(shared_phone):
    assert shared_phone.find_connection("a", "a") == {"error": "same_person"}


def test_find_connection_rejects_an_unknown_target(shared_phone):
    assert shared_phone.find_connection("a", "nobody") == {"error": "target_not_found"}


def test_find_connection_rejects_a_non_person_target(shared_phone):
    assert shared_phone.find_connection("a", "phone:1") == {"error": "target_not_found"}


def test_find_connection_returns_none_for_an_unknown_source(shared_phone):
    assert shared_phone.find_connection("nobody", "a") is None


def test_person_network_max_degree_cap_extends_past_max_degree(chain):
    """Internal callers (find_connection) can look further than the public
    API's degree ceiling; the router never passes this, so MAX_DEGREE=3
    keeps capping every request that doesn't set it explicitly."""
    network = chain.person_network("a", degree=4, max_degree_cap=4)
    assert network["degree"] == 4
    assert chain.person_network("a", degree=9)["degree"] == 3
