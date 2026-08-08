"""The demo dataset really produces the scenarios DEMO_GUIDE.md promises.

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

from demo_dataset import PEOPLE  # noqa: E402
from seed_demo_data import build_plan  # noqa: E402

SPACE = "demo_space"

# The tags GraphWriter maps CamelCase entity types onto.
TAG_FOR = {
    "Person": "person", "Company": "company", "Address": "address",
    "Country": "country", "Passport": "passport", "Phone": "phone",
    "Email": "email", "BankAccount": "bank_account", "Vehicle": "vehicle",
    "sanction_entry": "sanction_entry", "watchlist_entry": "watchlist_entry",
}


@pytest.fixture(scope="module")
def service() -> PersonNetworkService:
    """The dataset loaded exactly as seed_demo_data.py would write it."""
    vertices, edges = build_plan()
    clients = FakeGraphClientCache()
    client = clients.for_space(SPACE)

    for entity_type, vid, label, attrs in vertices:
        tag = TAG_FOR[entity_type]
        client.store.vertices[vid] = {tag: {
            "label": label,
            "entity_type": entity_type,
            "props": json.dumps(attrs),
        }}
    for edge_type, src, dst, attrs, relation_label in edges:
        client.store.edges.append((src, dst, edge_type, 0, {
            **attrs, "relationship_type": relation_label or ""}))
        client.store.edge_types[edge_type] = object()

    return PersonNetworkService(clients, SPACE)


def linked_ids(network) -> set[str]:
    return {p["id"] for p in network["persons"]}


def via_kinds(network, a: str, b: str) -> set[str]:
    pair = tuple(sorted((a, b)))
    for link in network["links"]:
        if tuple(sorted((link["source"], link["target"]))) == pair:
            return {v["kind"] for v in link["via"]}
    return set()


def test_dataset_has_fifty_people():
    assert len(PEOPLE) == 50
    assert len({p["id"] for p in PEOPLE}) == 50


def test_every_person_has_details_to_fan_out(service):
    """Clicking any person on the canvas must show something."""
    for person in PEOPLE:
        attributes = service.attributes(person["id"])["attributes"]
        assert attributes, f"{person['id']} has no attributes to expand"


def test_person_properties_are_readable_not_a_json_blob(service):
    network = service.person_network("p_rashid_almazrouei", degree=1)
    root = next(p for p in network["persons"] if p["id"] == "p_rashid_almazrouei")
    assert root["properties"]["nationality"] == "United Arab Emirates"
    assert root["properties"]["sanctions_screening"] == "OFAC SDN — match"
    assert "props" not in root["properties"]


# ------------------------------------------------------------- scenarios


def test_shared_handset_links_two_unrelated_customers(service):
    """Case: one phone, two separate customer files."""
    network = service.person_network("p_mohammed_iqbal", degree=1)
    assert "p_sunil_menon" in linked_ids(network)
    assert "shared_attribute" in via_kinds(network, "p_mohammed_iqbal", "p_sunil_menon")


def test_duplicate_identity_shares_one_passport(service):
    """Case: the same passport number on two customer files."""
    attributes = service.attributes("p_mohammed_iqbal")["attributes"]
    passport = next(a for a in attributes if a["tag"] == "passport")
    assert passport["shared_with"] == ["p_mohamed_ikbal"]


def test_sanctioned_owner_reaches_his_staff(service):
    """Case: who is exposed to a designated party."""
    network = service.person_network("p_rashid_almazrouei", degree=1)
    found = linked_ids(network)
    for staff in ("p_yusuf_karimov", "p_layla_haddad", "p_elena_petrova"):
        assert staff in found


def test_nominee_director_and_his_address_cluster(service):
    """Case: six 'directors' at one office unit."""
    network = service.person_network("p_vikram_nair", degree=1)
    found = linked_ids(network)
    for co_resident in ("p_anita_desai", "p_george_mensah", "p_farid_hassan",
                        "p_wei_zhang", "p_olga_ivanova"):
        assert co_resident in found


def test_linked_organisations_bridge_people_who_share_nothing(service):
    """Case: their employers transact, they never met.

    Priya (Meridian) and Arjun (Nimbus) share no phone, email or address —
    the only thing joining them is Nimbus paying Meridian.
    """
    network = service.person_network("p_priya_sharma", degree=1)
    assert "p_arjun_kapoor" in linked_ids(network)
    assert "linked_organisation" in via_kinds(network, "p_priya_sharma", "p_arjun_kapoor")


def test_pep_family_is_a_direct_relationship(service):
    """Case: PEP by association, stated outright rather than inferred."""
    network = service.person_network("p_adebayo_okonkwo", degree=1)
    found = linked_ids(network)
    assert {"p_chidinma_okonkwo", "p_emeka_okonkwo", "p_ngozi_okonkwo"} <= found
    assert "direct" in via_kinds(network, "p_adebayo_okonkwo", "p_chidinma_okonkwo")


def test_joint_account_links_the_family(service):
    """Case: three people on one bank account."""
    attributes = service.attributes("p_rina_patel")["attributes"]
    account = next(a for a in attributes if a["tag"] == "bank_account")
    assert set(account["shared_with"]) == {"p_deepak_patel", "p_meena_patel"}


def test_registered_agent_address_is_suppressed_as_a_hub(service):
    """Case: a connector shared by 28 people is reported, not drawn.

    Otherwise it would link everyone to everyone and bury the real leads.
    """
    network = service.person_network("p_helena_rossi", degree=1)
    hubs = {hub["id"] for hub in network["suppressed_hubs"]}
    assert "ad_emirates_corp_hub" in hubs


def test_clean_customer_has_no_suspicious_links(service):
    """Case: the control — most customers are fine, and look it."""
    network = service.person_network("p_marie_dubois", degree=2)
    assert linked_ids(network) == {"p_marie_dubois"}


def test_clean_couple_are_linked_only_to_each_other(service):
    """A benign network still *has* shape — it just doesn't lead anywhere.

    Sarah's only degree-1 link is her spouse; at degree 2 she reaches his
    colleague and stops. Nothing flagged, which is the point of showing it.
    """
    one = service.person_network("p_sarah_thompson", degree=1)
    assert linked_ids(one) == {"p_sarah_thompson", "p_james_wilson"}

    two = service.person_network("p_sarah_thompson", degree=2)
    assert linked_ids(two) == {"p_sarah_thompson", "p_james_wilson", "p_daniel_kim"}


def test_clean_looking_broker_is_three_steps_from_a_designated_party(service):
    """The headline scenario: Amara Diallo's own file is unremarkable.

    Her flatmate is the sanctioned company's accountant, so widening the
    search to 3 degrees surfaces the exposure her own record never shows.
    """
    one = service.person_network("p_amara_diallo", degree=1)
    assert "p_rashid_almazrouei" not in linked_ids(one)

    three = service.person_network("p_amara_diallo", degree=3)
    reached = {p["id"]: p["degree"] for p in three["persons"]}
    assert reached["p_layla_haddad"] == 1
    assert reached["p_rashid_almazrouei"] == 2


def test_sanctions_entry_is_never_projected_as_a_person(service):
    """A sanctions record is evidence about a person, not a person."""
    network = service.person_network("p_rashid_almazrouei", degree=3)
    assert not any(p["id"].startswith("s_") for p in network["persons"])


def test_degree_widens_the_net_from_a_sanctioned_party(service):
    one = linked_ids(service.person_network("p_rashid_almazrouei", degree=1))
    three = linked_ids(service.person_network("p_rashid_almazrouei", degree=3))
    assert one < three, "degree 3 should reach further than degree 1"


# ----------------------------------------------------------- risk scoring


@pytest.fixture(scope="module")
def risk(service):
    """Risk scoring wired to the same fake store as the projection."""
    from graph_explorer_api.services.graph_service import GraphService
    from graph_explorer_api.services.risk_service import RiskService

    graph_service = GraphService(service._clients, SPACE)
    return RiskService(graph_service, person_network=service)


def test_listed_party_scores_high(risk):
    result = risk.calculate_for_entity("p_rashid_almazrouei")
    assert result.level == "high"
    assert [f.code for f in result.factors] == ["direct_sanction_match"]


def test_employee_of_a_listed_party_is_exposed_not_matched(risk):
    """Yusuf isn't listed — but scoring him clean is the failure that matters.

    He must NOT be reported as a sanctions match (that would be wrong about
    a real person), yet must still carry the exposure his employer creates.
    """
    result = risk.calculate_for_entity("p_yusuf_karimov")
    codes = [f.code for f in result.factors]
    assert codes == ["indirect_sanction_exposure"]
    assert result.level in ("medium", "high")


def test_exposure_decays_with_distance(risk):
    """Closer to a listed party scores higher, or the number says nothing.

    Yusuf is employed by the designated party's own company; Wei Zhang is a
    step further out again.
    """
    close = risk.calculate_for_entity("p_yusuf_karimov").score
    far = risk.calculate_for_entity("p_wei_zhang").score
    assert close > far > 0


def test_clean_customer_scores_low_with_no_factors(risk):
    result = risk.calculate_for_entity("p_marie_dubois")
    assert result.level == "low"
    assert result.factors == []


def test_a_flag_on_an_associate_is_not_reported_as_your_own_match(risk):
    """Amara is not listed — her former business partner is.

    Reporting her as a personal sanctions/watchlist match would be a false
    positive on a real person; the exposure belongs in the indirect factor.
    """
    result = risk.calculate_for_entity("p_amara_diallo")
    codes = [f.code for f in result.factors]
    assert "direct_sanction_match" not in codes
    assert codes == ["indirect_sanction_exposure"]


def test_pep_scores_on_their_own_file(risk):
    """A PEP with nothing else against them still warrants due diligence."""
    result = risk.calculate_for_entity("p_adebayo_okonkwo")
    codes = [f.code for f in result.factors]
    assert "pep_exposure" in codes
    assert result.level in ("medium", "high")


def test_pep_family_scores_below_the_pep_themselves(risk):
    """Relatives carry the same category of risk at a discount, not equally."""
    pep = next(
        f for f in risk.calculate_for_entity("p_adebayo_okonkwo").factors
        if f.code == "pep_exposure"
    )
    relative = next(
        f for f in risk.calculate_for_entity("p_emeka_okonkwo").factors
        if f.code == "pep_exposure"
    )
    assert pep.value > relative.value
    assert "relative or close associate" in relative.explanation


def test_high_risk_jurisdiction_is_read_from_the_country_record(risk):
    """The classification is reference data, not a list baked into the code."""
    result = risk.calculate_for_entity("p_adebayo_okonkwo")
    country = next(f for f in result.factors if f.code == "high_risk_country")
    assert country.evidence_ids == ["co_ng"]


def test_a_standard_jurisdiction_adds_no_factor(risk):
    codes = [f.code for f in risk.calculate_for_entity("p_marie_dubois").factors]
    assert "high_risk_country" not in codes


def test_clean_customer_is_still_clean_after_the_new_factors(risk):
    result = risk.calculate_for_entity("p_marie_dubois")
    assert result.level == "low"
    assert result.factors == []
