"""The demo dataset really produces the scenarios it claims to.

These run the real PersonNetworkService over the in-memory fake store, so a
change to either the dataset or the projection that would break a live
demo fails here first — no NebulaGraph needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from graph_explorer_api.services.person_network_service import PersonNetworkService

from tests.unit.fakes import FakeGraphClientCache

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

from demo_graph_data import (  # noqa: E402
    PEOPLE,
    all_documents,
    document_by_id,
    holdings,
    index_entries,
)
from intelligence_schema.field_index import value_vid  # noqa: E402

SPACE = "demo_space"


@pytest.fixture(scope="module")
def service() -> PersonNetworkService:
    """The dataset loaded exactly as seed_demo_graph.py would write it."""
    clients = FakeGraphClientCache()
    store = clients.for_space(SPACE).store

    for person in PEOPLE:
        store.vertices[person["id"]] = {"person": {
            "label": person["name"],
            "entity_type": "Person",
            "props": json.dumps(person["attributes"]),
        }}

    for document in document_by_id().values():
        store.vertices[document["id"]] = {"document": {
            "label": document["number"],
            "entity_type": "Document",
            "props": json.dumps({
                **document["attributes"],
                "number": document["number"],
                "document_type": document["document_type"],
            }),
        }}

    for person_id, document_id in holdings():
        store.edges.append((person_id, document_id, "HAS_DOCUMENT", 0, {}))

    for person_id, field_key, value, document_id, document_type in index_entries():
        vid = value_vid(value)
        store.vertices.setdefault(vid, {"field_value": {
            "label": value, "entity_type": "field_value", "value": value,
        }})
        store.edges.append((person_id, vid, "HAS_FIELD_VALUE", 0, {
            "field_key": field_key,
            "document_id": document_id,
            "document_type": document_type,
        }))

    for edge_type in ("HAS_DOCUMENT", "HAS_FIELD_VALUE"):
        store.edge_types[edge_type] = object()

    return PersonNetworkService(clients, SPACE)


def linked_ids(network) -> set[str]:
    return {p["id"] for p in network["persons"]}


def link_between(network, a: str, b: str) -> dict | None:
    pair = tuple(sorted((a, b)))
    for link in network["links"]:
        if tuple(sorted((link["source"], link["target"]))) == pair:
            return link
    return None


# ----------------------------------------------------------------- shape


def test_every_person_can_be_expanded(service):
    """Clicking any person on the canvas must show something."""
    for person in PEOPLE:
        attributes = service.attributes(person["id"])["attributes"]
        assert attributes, f"{person['id']} has no documents to expand"


def test_expanding_a_person_shows_documents_only(service):
    tags = {a["tag"] for p in PEOPLE for a in service.attributes(p["id"])["attributes"]}
    assert tags == {"document"}


def test_documents_carry_readable_fields_not_a_json_blob(service):
    attributes = service.attributes("demo_p_amina_rahman")["attributes"]
    passport = next(a for a in attributes if a["id"] == "demo_doc_amina_pp")
    assert passport["properties"]["father_name"] == "Ibrahim Rahman"
    assert passport["properties"]["document_type"] == "passport"
    assert "props" not in passport["properties"]


# ------------------------------------------------------------- scenarios


def test_siblings_are_linked_by_their_fathers_name(service):
    """The headline case: two separate passports naming one father."""
    network = service.person_network("demo_p_amina_rahman", degree=1)
    assert "demo_p_yusuf_rahman" in linked_ids(network)
    link = link_between(network, "demo_p_amina_rahman", "demo_p_yusuf_rahman")
    matched = {v["field_key"] for v in link["via"] if v["kind"] == "shared_field"}
    assert {"father_name", "mother_name"} <= matched


def test_two_matching_fields_score_above_either_alone(service):
    """Noisy-OR: agreeing twice is stronger than agreeing once."""
    network = service.person_network("demo_p_amina_rahman", degree=1)
    siblings = link_between(network, "demo_p_amina_rahman", "demo_p_yusuf_rahman")
    assert siblings["confidence"] > 0.9


def test_the_chain_widens_one_degree_at_a_time(service):
    """Amina -> Yusuf -> Khalid -> Sofia, a different field at each hop."""
    reached = {
        p["id"]: p["degree"]
        for p in service.person_network("demo_p_amina_rahman", degree=3)["persons"]
    }
    assert reached["demo_p_yusuf_rahman"] == 1
    assert reached["demo_p_khalid_nasser"] == 2
    assert reached["demo_p_sofia_castro"] == 3


def test_degree_one_stops_before_the_rest_of_the_chain(service):
    found = linked_ids(service.person_network("demo_p_amina_rahman", degree=1))
    assert "demo_p_khalid_nasser" not in found
    assert "demo_p_sofia_castro" not in found


def test_cross_key_match_is_found_and_marked(service):
    """Omar's passport address equals Lina's Emirates ID residence_address."""
    network = service.person_network("demo_p_omar_haddad", degree=1)
    assert "demo_p_lina_farouk" in linked_ids(network)
    via = link_between(network, "demo_p_omar_haddad", "demo_p_lina_farouk")["via"][0]
    assert via["same_key"] is False
    assert set(via["field_keys"]) == {"address", "residence_address"}


def test_cross_key_scores_below_an_equivalent_same_key_match(service):
    cross = link_between(
        service.person_network("demo_p_omar_haddad", degree=1),
        "demo_p_omar_haddad", "demo_p_lina_farouk",
    )
    same = link_between(
        service.person_network("demo_p_yusuf_rahman", degree=1),
        "demo_p_yusuf_rahman", "demo_p_khalid_nasser",
    )
    assert cross["confidence"] < same["confidence"]


def test_duplicate_identity_shares_one_passport(service):
    """Two customer files, one passport vertex."""
    attributes = service.attributes("demo_p_mohammed_iqbal")["attributes"]
    passport = next(a for a in attributes if a["id"] == "demo_doc_duplicate_pp")
    assert passport["shared_with"] == ["demo_p_mohamed_ikbal"]


def test_duplicate_identity_is_the_strongest_link_in_the_dataset(service):
    network = service.person_network("demo_p_mohammed_iqbal", degree=1)
    link = link_between(network, "demo_p_mohammed_iqbal", "demo_p_mohamed_ikbal")
    assert link["confidence"] > 0.95


def test_a_common_birthplace_links_people_but_barely(service):
    """Six people born in Dubai: a real match, worth almost nothing."""
    network = service.person_network("demo_p_amina_rahman", degree=1)
    crowd = link_between(network, "demo_p_amina_rahman", "demo_p_rami_aziz")
    assert crowd is not None
    assert crowd["confidence"] < 0.2


def test_the_confidence_filter_removes_the_noise_and_keeps_the_lead(service):
    """The filter has to separate these two, or it is not worth having."""
    filtered = service.person_network("demo_p_amina_rahman", degree=1, min_confidence=0.3)
    found = linked_ids(filtered)
    assert "demo_p_yusuf_rahman" in found
    assert "demo_p_rami_aziz" not in found


def test_nationality_connects_nobody(service):
    """Every person here is a UAE national. If that linked them, the whole
    dataset would be one blob and no lead would be visible."""
    network = service.person_network("demo_p_clara_dubois", degree=3)
    assert linked_ids(network) == {"demo_p_clara_dubois"}


def test_the_control_customer_has_a_document_but_no_links(service):
    """Most customers look like this, and the canvas should show that."""
    assert service.attributes("demo_p_clara_dubois")["attributes"]
    assert service.person_network("demo_p_clara_dubois", degree=1)["links"] == []


def test_index_vertices_are_never_returned_as_people(service):
    network = service.person_network("demo_p_amina_rahman", degree=3)
    assert not any(p["id"].startswith("value:") for p in network["persons"])


def test_every_document_belongs_to_someone(service):
    holders = {person_id for person_id, _ in holdings()}
    assert holders <= {p["id"] for p in PEOPLE}
    assert len(all_documents()) + 1 == len(document_by_id())
