from __future__ import annotations

from risk_engine.models import RiskFactor, RiskResult

# Being a PEP is not wrongdoing — it mandates enhanced due diligence, not
# refusal. Weighted so a PEP with nothing else against them lands in the
# middle band (review) rather than the top one (block), but combines with
# any other factor to clear the high threshold.
PEP_WEIGHT = 0.7
# Relatives and close associates carry the same category of risk at a
# discount, per the usual FATF "RCA" treatment.
PEP_ASSOCIATE_VALUE = 0.7

PEP_SELF = "self"
PEP_ASSOCIATE = "associate"


class RiskScorer:
    def calculate(self, entity_id: str, context: dict) -> RiskResult:
        factors: list[RiskFactor] = []

        if context.get("is_direct_sanction_match"):
            factors.append(
                RiskFactor(
                    code="direct_sanction_match",
                    weight=1.0,
                    value=1.0,
                    explanation="Entity directly matches a sanctions record",
                    evidence_ids=context.get("sanction_evidence_ids", []),
                )
            )

        indirect_degree = context.get("sanctioned_connection_degree")
        if indirect_degree is not None:
            propagated = max(0.0, 0.8 - (0.2 * (indirect_degree - 1)))
            factors.append(
                RiskFactor(
                    code="indirect_sanction_exposure",
                    weight=0.8,
                    value=propagated,
                    explanation=(
                        f"Entity is connected within {indirect_degree} degree(s) "
                        f"to a sanctioned entity"
                    ),
                    evidence_ids=context.get("path_evidence_ids", []),
                )
            )

        if context.get("shared_bank_account_count", 0) > 0:
            factors.append(
                RiskFactor(
                    code="shared_bank_account",
                    weight=0.5,
                    value=min(context["shared_bank_account_count"] / 3, 1.0),
                    explanation="Entity shares bank account links with flagged entities",
                    evidence_ids=context.get("shared_bank_account_evidence_ids", []),
                )
            )

        pep_relationship = context.get("pep_relationship")
        if pep_relationship in (PEP_SELF, PEP_ASSOCIATE):
            is_self = pep_relationship == PEP_SELF
            factors.append(
                RiskFactor(
                    code="pep_exposure",
                    weight=PEP_WEIGHT,
                    value=1.0 if is_self else PEP_ASSOCIATE_VALUE,
                    explanation=(
                        "Entity is a politically exposed person — enhanced due "
                        "diligence required"
                        if is_self
                        else "Entity is a relative or close associate of a "
                             "politically exposed person"
                    ),
                    evidence_ids=context.get("pep_evidence_ids", []),
                )
            )

        if context.get("high_risk_country"):
            factors.append(
                RiskFactor(
                    code="high_risk_country",
                    weight=0.3,
                    value=1.0,
                    explanation="Entity is associated with a high-risk jurisdiction",
                    evidence_ids=context.get("country_evidence_ids", []),
                )
            )

        score = sum(f.weight * f.value for f in factors)
        score = min(score, 1.0)

        if score >= 0.8:
            level = "high"
        elif score >= 0.45:
            level = "medium"
        else:
            level = "low"

        return RiskResult(entity_id=entity_id, score=score, level=level, factors=factors)
