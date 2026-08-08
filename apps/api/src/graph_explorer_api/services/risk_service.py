from __future__ import annotations

from graph_explorer_api.services.graph_service import FLAG_TAGS, GraphService
from graph_explorer_api.services.person_network_service import PersonNetworkService
from risk_engine.models import RiskResult
from risk_engine.scorer import PEP_ASSOCIATE, PEP_SELF, RiskScorer

# How far to look for exposure to a listed party. Matches the Investigation
# canvas's own ceiling, so a score can always be explained by a network the
# investigator can actually pull up and look at.
MAX_EXPOSURE_DEGREE = 3

# What a country vertex says about itself. Which jurisdictions count as
# high risk is policy that changes several times a year, so it is carried as
# data on the country — this code makes no claim about any real country, it
# only reads the classification whoever loaded the reference data supplied.
HIGH_RISK_CLASSIFICATION = "High-risk jurisdiction"

# `pep_status` is free text from whatever screening source wrote it, so it is
# matched loosely: anything that isn't plainly a "no" counts, and wording
# about family/associates downgrades a hit from the PEP themselves to an RCA.
_NOT_PEP = {"", "no", "none", "false", "not a pep", "n/a", "-"}
_ASSOCIATE_WORDS = ("family", "associate", "relative", "spouse", "rca")


def classify_pep(status: object) -> str | None:
    """A `pep_status` value as PEP_SELF, PEP_ASSOCIATE, or None."""
    text = str(status or "").strip().lower()
    if text in _NOT_PEP:
        return None
    if any(word in text for word in _ASSOCIATE_WORDS):
        return PEP_ASSOCIATE
    return PEP_SELF


class RiskService:
    def __init__(
        self,
        graph_service: GraphService,
        scorer: RiskScorer | None = None,
        person_network: PersonNetworkService | None = None,
    ) -> None:
        self.graph_service = graph_service
        self.scorer = scorer or RiskScorer()
        # Optional: without it, scoring still reports direct hits, it just
        # can't see exposure through the entity's network.
        self.person_network = person_network

    def calculate_for_entity(self, entity_id: str) -> RiskResult:
        context = self.graph_service.get_entity_context(entity_id)
        risk_context = self._build_risk_context(entity_id, context)
        return self.scorer.calculate(entity_id, risk_context)

    def _build_risk_context(self, entity_id: str, context: dict) -> dict:
        risk_context: dict = {}
        neighbors = context.get("neighbors", [])

        # Adjacency, deliberately: a listing is attached to the entity it
        # names, so only a record one hop out is *this* entity's match.
        # Reading it off a deeper traversal would report anyone standing near
        # a listed party as personally designated — the false positive an AML
        # tool can least afford.
        listings = sorted(n["id"] for n in neighbors if n["tags"] & FLAG_TAGS)
        if listings:
            risk_context["is_direct_sanction_match"] = True
            risk_context["sanction_evidence_ids"] = listings
        else:
            self._add_indirect_exposure(entity_id, risk_context)

        relationship = classify_pep(context.get("properties", {}).get("pep_status"))
        if relationship is not None:
            risk_context["pep_relationship"] = relationship
            risk_context["pep_evidence_ids"] = [entity_id]

        high_risk = sorted(
            n["id"] for n in neighbors
            if "country" in n["tags"]
            and n["properties"].get("risk_classification") == HIGH_RISK_CLASSIFICATION
        )
        if high_risk:
            risk_context["high_risk_country"] = True
            risk_context["country_evidence_ids"] = high_risk

        transfers = sum(1 for name in context.get("edge_types", []) if name == "TRANSFERRED_TO")
        if transfers:
            risk_context["shared_bank_account_count"] = transfers

        return risk_context

    def _add_indirect_exposure(self, entity_id: str, risk_context: dict) -> None:
        """Flag exposure *through* the network: not listed, but connected.

        Someone employed by a designated party's company is not themselves a
        sanctions match, and reporting them as one would be wrong. But
        scoring them as clean is the failure that matters in AML — so the
        nearest listed party in their person network is reported at the
        degree it was found, and the scorer decays the weight with distance.
        """
        if self.person_network is None:
            return
        network = self.person_network.person_network(entity_id, degree=MAX_EXPOSURE_DEGREE)
        if not network:
            return  # not a person (a company, an address) — nothing to walk

        by_degree = {
            person["id"]: person["degree"]
            for person in network["persons"]
            if person["id"] != entity_id
        }
        if not by_degree:
            return

        exposed = set(self.graph_service.find_listed_entities()) & set(by_degree)
        if not exposed:
            return

        nearest = min(by_degree[entity] for entity in exposed)
        risk_context["sanctioned_connection_degree"] = nearest
        risk_context["path_evidence_ids"] = sorted(
            entity for entity in exposed if by_degree[entity] == nearest
        )
