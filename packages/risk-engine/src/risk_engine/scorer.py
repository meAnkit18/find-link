from __future__ import annotations

from risk_engine.models import RiskFactor, RiskResult


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
